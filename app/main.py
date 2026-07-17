"""Content Copilot — paid x402 gateway (OKX.AI A2MCP surface).

The x402 payment IS the access. An unpaid request to a /v1/* verb receives
HTTP 402 with a PAYMENT-REQUIRED challenge; only a request carrying a verified
EIP-3009 signature reaches the pipeline, and the response body is released ONLY
after the OKX Broker confirms on-chain settlement (sync settle) in USDT0 on
X Layer (eip155:196).

Refuse-to-charge policy: any pipeline failure or empty result returns a non-2xx
status, which skips settlement — the buyer is never billed for a bad payload.

Run:  uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""

import asyncio
import inspect
import json
import logging
import os
import re
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import alerts, ledger, ratelimit
from .config import settings

from src import ingest, mine, pack, ship
from src.llm import LlmUnavailable
from src.voice_dna import load_voice_profile

# OKX x402 seller SDK (pip install "okxweb3-app-x402[fastapi,evm,httpx]").
from x402.http import (
    OKXAuthConfig,
    OKXFacilitatorClient,
    OKXFacilitatorConfig,
    PaymentOption,
)
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact.server import ExactEvmScheme
from x402.server import x402ResourceServer

# --- OKX SDK bug workaround (verified on-chain) --------------------------------
# okxweb3-app-x402's NETWORK_CONFIGS labels the X Layer (eip155:196) asset as
# "USDT", but the on-chain token name() is "USD₮0" (U+20AE tugrik). EIP-3009
# signs over the token's EIP-712 domain, whose `name` MUST equal the contract's
# name — otherwise every payment is rejected with "invalid_signature". Verified:
# reconstructing DOMAIN_SEPARATOR with name="USD₮0", version="1" matches the
# contract's DOMAIN_SEPARATOR(); name="USDT" does not.
from x402.mechanisms.evm.constants import NETWORK_CONFIGS as _NETWORK_CONFIGS

_xl_asset = _NETWORK_CONFIGS.get("eip155:196", {}).get("default_asset")
if _xl_asset is not None and _xl_asset.get("name") != "USD₮0":
    _xl_asset["name"] = "USD₮0"

# FAIL-FAST: if an SDK bump renamed/relocated `default_asset`, the override above
# silently no-ops and EVERY EIP-3009 signature would be rejected. Crash the
# deploy here instead of failing every sale.
if _xl_asset is None or _xl_asset.get("name") != "USD₮0":
    raise RuntimeError(
        "x402 SDK X Layer asset override failed: expected default_asset.name == 'USD₮0' "
        f"(got {_xl_asset!r}). The okxweb3-app-x402 NETWORK_CONFIGS shape changed — "
        "every payment signature would break. Fix the override before deploying."
    )

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("content_copilot_gateway")

_AVATAR_PATH = os.path.join(os.path.dirname(__file__), "static", "avatar.png")

_PIPELINE_ERRORS = (ingest.IngestError, mine.MineError, pack.PackError, ship.ShipError)


# Every verb accepts GET (query params) AND POST (JSON body) — the OKX platform
# validator and its buyer agents call registered A2MCP endpoints with POST, so a
# GET-only route would answer their probe with a bare 405 instead of the 402
# challenge and fail x402 standard validation.
VERB_METHODS = ("GET", "POST")


@dataclass(frozen=True)
class Verb:
    slug: str
    price: str           # display price, e.g. "$0.10"
    timeout: int         # payment window advertised in the 402 challenge
    description: str


VERBS: dict[str, Verb] = {
    v.slug: v
    for v in (
        Verb(
            "ingest", settings.price_ingest, settings.ingest_timeout_seconds,
            "Download + transcribe a source (YouTube, podcast, MP3/MP4 URL, article). "
            "Params: source_url (required), kind. Returns session_id.",
        ),
        Verb(
            "mine", settings.price_mine, settings.max_timeout_seconds,
            "Rank 10-40s segments of an ingested source by novelty/tension/stakes/"
            "quote-density. Params: session_id (required), top_k. Returns ranked moments.",
        ),
        Verb(
            "pack", settings.price_pack, settings.max_timeout_seconds,
            "Generate a channel-native content pack from one mined moment. Params: "
            "session_id, moment_id, target (x|linkedin|ig_reel|newsletter), voice_profile.",
        ),
        Verb(
            "ship", settings.price_ship, settings.max_timeout_seconds,
            "Publish a pack via a server-registered downstream credential. Params: "
            "session_id, pack_id, credentials_ref. Returns provider id + permalink.",
        ),
    )
}


def _public_path(slug: str) -> str:
    return f"/v1/{slug}"


def _build_facilitator() -> OKXFacilitatorClient:
    """Construct the OKX Broker/Facilitator client (seller credentials)."""
    settings.require_seller_creds()
    return OKXFacilitatorClient(
        OKXFacilitatorConfig(
            auth=OKXAuthConfig(
                api_key=settings.okx_api_key,
                secret_key=settings.okx_secret_key,
                passphrase=settings.okx_passphrase,
            ),
            base_url=settings.okx_base_url,
            sync_settle=settings.sync_settle,
            timeout=settings.facilitator_timeout_seconds,
        )
    )


def _accepts(verb: Verb) -> list[PaymentOption]:
    """Payment options: 'exact' (EIP-3009) ONLY.

    'exact' buffers the response and settles SYNCHRONOUSLY on-chain before the
    data is released, and fails closed on every edge case (underpay / expired /
    wrong-net / bad-sig / facilitator timeout) — proven in production on the
    FanTokenIntel gateway. Deferred schemes deliver on OKX-acceptance, not
    on-chain finality; we don't advertise a path we haven't proven.
    """
    return [
        PaymentOption(
            scheme="exact",
            price=verb.price,
            network=settings.network,
            pay_to=settings.pay_to_address,
            max_timeout_seconds=verb.timeout,
        )
    ]


# --- ledger hooks (settlement outcomes) -----------------------------------------

def _nonce_of(payment_payload: object) -> Optional[str]:
    if payment_payload is None:
        return None
    d = payment_payload.model_dump() if hasattr(payment_payload, "model_dump") else {}
    return ((d.get("payload") or {}).get("authorization") or {}).get("nonce")


async def _on_after_settle(ctx) -> None:
    try:
        nonce = _nonce_of(getattr(ctx, "payment_payload", None))
        result = getattr(ctx, "result", None)
        tx = None
        if result is not None:
            tx = getattr(result, "transaction", None)
            if tx is None and hasattr(result, "model_dump"):
                tx = result.model_dump().get("transaction")
        if nonce:
            await ledger.mark_settled(nonce, tx)
    except Exception as exc:  # noqa: BLE001 - hook must never break settlement
        logger.error("after_settle_hook_error: %s", exc)


async def _on_settle_failure(ctx) -> None:
    try:
        nonce = _nonce_of(getattr(ctx, "payment_payload", None))
        reason = str(getattr(ctx, "error", "settlement failed"))[:300]
        if nonce:
            await ledger.mark_failed(nonce)
        await alerts.alert("settlement_failed", nonce=nonce, reason=reason)
    except Exception as exc:  # noqa: BLE001
        logger.error("settle_failure_hook_error: %s", exc)


# --- paid handlers ----------------------------------------------------------------

async def _request_params(request: Request) -> dict[str, Any]:
    """Caller params: query string merged with an optional JSON-object body
    (body wins). Callers are LLM agents that may GET with query params or POST
    a JSON body — both must work on every verb."""
    params: dict[str, Any] = dict(request.query_params)
    body = await request.body()
    if body and body.strip():
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=422, detail="request body must be valid JSON")
        if isinstance(parsed, dict):
            params.update(parsed)
        else:
            raise HTTPException(status_code=422, detail="JSON body must be an object")
    return params


def _pick(params: dict[str, Any], *names: str) -> Optional[str]:
    """First non-empty value under any accepted alias, as a string."""
    for name in names:
        val = params.get(name)
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def _sniff_url(params: dict[str, Any]) -> Optional[str]:
    """Fallback for ingest: agent callers don't always guess the param name
    right — if exactly one http(s) URL appears anywhere in the params, use it."""
    urls: list[str] = []
    for val in params.values():
        if isinstance(val, str):
            urls.extend(_URL_RE.findall(val))
    unique = list(dict.fromkeys(urls))
    return unique[0] if len(unique) == 1 else None


def _payment_info(request: Request) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract (nonce, payer, amount) from the verified payment on request.state."""
    pp = getattr(request.state, "payment_payload", None)
    if pp is None:
        return None, None, None
    d = pp.model_dump() if hasattr(pp, "model_dump") else {}
    auth = (d.get("payload") or {}).get("authorization") or {}
    return auth.get("nonce"), auth.get("from"), auth.get("value")


async def _run_paid(
    slug: str, request: Request, work: Callable[[], Awaitable[dict[str, Any]]]
) -> JSONResponse:
    """Idempotency-claim + refuse-to-charge wrapper shared by all verbs.

    Any non-2xx return skips settlement, so mapping every pipeline failure to
    4xx/5xx IS the no-charge guarantee on this non-refundable rail.
    """
    nonce, payer, amount = _payment_info(request)
    if getattr(request.state, "payment_payload", None) is not None and not nonce:
        await alerts.alert(
            "payment_without_nonce", slug=slug,
            reason="verified payment had no extractable nonce; idempotency degraded",
        )

    claimed = False
    if nonce:
        claimed = await ledger.claim(nonce, slug, payer, amount)
        if not claimed:
            raise HTTPException(status_code=409, detail="payment already processed (duplicate)")

    delivered = False
    try:
        # Hard response deadline: the caller is an agent task with its own
        # timeout — a hung pipeline must become a fast, unbilled error, never
        # silence (non-2xx skips settlement).
        result = await asyncio.wait_for(work(), timeout=settings.work_deadline_seconds)
        delivered = True
        return JSONResponse(result)
    except asyncio.TimeoutError:
        logger.error("work_deadline_exceeded slug=%s deadline=%ss", slug, settings.work_deadline_seconds)
        await alerts.alert("work_deadline_exceeded", slug=slug)
        raise HTTPException(
            status_code=504,
            detail=f"processing exceeded {settings.work_deadline_seconds}s — not billed; "
                   "try a shorter source or retry later",
        )
    except LlmUnavailable as exc:
        logger.error("llm_unavailable slug=%s: %s", slug, exc)
        await alerts.alert("llm_unavailable", slug=slug)
        raise HTTPException(status_code=503, detail="generation backend unavailable — not billed")
    except _PIPELINE_ERRORS as exc:
        raise HTTPException(status_code=422, detail=f"{exc} — not billed")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - unknown failure: refuse to charge
        logger.exception("verb_failed slug=%s", slug)
        raise HTTPException(status_code=502, detail=f"internal failure ({type(exc).__name__}) — not billed")
    finally:
        if claimed and not delivered:
            await ledger.release(nonce)


async def _handle_ingest(request: Request) -> JSONResponse:
    p = await _request_params(request)
    source_url = _pick(p, "source_url", "url", "source", "link") or _sniff_url(p)
    if not source_url:
        raise HTTPException(
            status_code=422,
            detail="source_url is required (query param or JSON body): "
                   "the public URL of the podcast, video, or article to ingest",
        )
    kind = _pick(p, "kind", "type") or "auto"

    async def work() -> dict[str, Any]:
        return await ingest.run(source_url, kind)

    return await _run_paid("ingest", request, work)


async def _handle_mine(request: Request) -> JSONResponse:
    p = await _request_params(request)
    session_id = _pick(p, "session_id", "sessionId", "session")
    if not session_id:
        raise HTTPException(
            status_code=422,
            detail="session_id is required (query param or JSON body): "
                   "the id returned by the ingest service",
        )
    try:
        top_k = int(_pick(p, "top_k", "topK", "count") or "10")
    except ValueError:
        raise HTTPException(status_code=422, detail="top_k must be an integer")

    async def work() -> dict[str, Any]:
        result = await mine.run(session_id, top_k)
        if not result.get("moments"):
            # Refuse-to-charge: an empty mining result is not a billable payload.
            raise mine.MineError("no mineable moments found in this source")
        return result

    return await _run_paid("mine", request, work)


async def _handle_pack(request: Request) -> JSONResponse:
    p = await _request_params(request)
    session_id = _pick(p, "session_id", "sessionId", "session")
    moment_id = _pick(p, "moment_id", "momentId", "moment")
    target = _pick(p, "target", "channel", "platform")
    missing = [n for n, v in (("session_id", session_id), ("moment_id", moment_id),
                              ("target", target)) if not v]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"missing params (query or JSON body): {missing}; "
                   "target is one of x|linkedin|ig_reel|newsletter",
        )
    voice = load_voice_profile(_pick(p, "voice_profile", "voiceProfile", "voice") or "generic-founder")

    async def work() -> dict[str, Any]:
        return await pack.run(session_id, moment_id, target, voice)

    return await _run_paid("pack", request, work)


async def _handle_ship(request: Request) -> JSONResponse:
    p = await _request_params(request)
    session_id = _pick(p, "session_id", "sessionId", "session")
    pack_id = _pick(p, "pack_id", "packId", "pack")
    credentials_ref = _pick(p, "credentials_ref", "credentialsRef", "credential", "credentials")
    missing = [n for n, v in (("session_id", session_id), ("pack_id", pack_id),
                              ("credentials_ref", credentials_ref)) if not v]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"missing params (query or JSON body): {missing}",
        )

    async def work() -> dict[str, Any]:
        return await ship.run(session_id, pack_id, credentials_ref)

    return await _run_paid("ship", request, work)


_HANDLERS: dict[str, Callable[[Request], Awaitable[JSONResponse]]] = {
    "ingest": _handle_ingest,
    "mine": _handle_mine,
    "pack": _handle_pack,
    "ship": _handle_ship,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail-fast + warm: validate OKX creds and warm the Broker connection at boot
    # so a bad/rotated credential surfaces in deploy logs, not on the first sale.
    fac = getattr(app.state, "facilitator", None)
    if fac is not None:
        try:
            res = fac.get_supported()
            if inspect.iscoroutine(res):
                res = await res
            logger.info("okx_broker_ready kinds=%d", len(getattr(res, "kinds", []) or []))
        except Exception as exc:  # noqa: BLE001 - boot diagnostic, must not crash startup
            logger.error("okx_broker_handshake_failed: %s", exc)
    logger.info(
        "gateway_start network=%s verbs=%d pay_to=%s",
        settings.network, len(VERBS), settings.pay_to_address,
    )
    yield


TERMS = (
    "Content Copilot turns raw sources (podcasts, videos, articles) into "
    "channel-native content packs. Payments settle on-chain via x402 and are "
    "non-refundable; any failed or empty result returns an error status and is "
    "NOT billed. Generated content is provided as-is — review before publishing. "
    "The ship verb requires a downstream credential pre-registered with the "
    "operator; caller credentials are never persisted."
)

PRICE_TOKEN = os.environ.get("OKX_PRICE_TOKEN", "USDT0")


def _price_amount(price: str) -> str:
    return price.lstrip("$").strip()


def a2mcp_services() -> list[dict]:
    """A2MCP service manifest — one entry per verb, endpoint absolute."""
    base = settings.public_base_url.rstrip("/")
    return [
        {
            "name": f"Content Copilot: {slug}",
            "endpoint": f"{base}{_public_path(slug)}",
            "service_type": "A2MCP",
            "methods": list(VERB_METHODS),
            "price": f"{_price_amount(v.price)} {PRICE_TOKEN}",
            "description": v.description,
        }
        for slug, v in VERBS.items()
    ]


def _require_admin(authorization: str) -> None:
    token = authorization[7:] if authorization.startswith("Bearer ") else authorization
    if not settings.admin_token or not secrets.compare_digest(token, settings.admin_token):
        raise HTTPException(status_code=401, detail="admin token required")


def create_app() -> FastAPI:
    # FAIL-FAST: async settle (sync_settle=False) would release the data BEFORE
    # on-chain nonce consumption -> replay / serve-before-pay. Refuse to boot.
    if not settings.sync_settle:
        raise RuntimeError(
            "SYNC_SETTLE must be true: async settlement delivers data before the "
            "payment is consumed on-chain, enabling replay/double-spend. Refusing to start."
        )
    facilitator = _build_facilitator()
    server = x402ResourceServer(facilitator)
    server.register(settings.network, ExactEvmScheme())
    server.on_after_settle(_on_after_settle)
    server.on_settle_failure(_on_settle_failure)

    app = FastAPI(
        title="Content Copilot",
        version="1.0.0",
        description="Raw sources in, channel-native content packs out — pay per call via x402 on X Layer.",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.facilitator = facilitator

    routes: dict[str, RouteConfig] = {}
    for slug, verb in VERBS.items():
        cfg = RouteConfig(
            accepts=_accepts(verb),
            description=f"Content Copilot: {verb.description}",
            mime_type="application/json",
        )
        # Paywall EVERY method that can reach the handler. Starlette auto-adds
        # HEAD to GET routes, so a missing "HEAD ..." key would let an unpaid
        # HEAD run the full pipeline with the body stripped.
        for method in (*VERB_METHODS, "HEAD"):
            routes[f"{method} {_public_path(slug)}"] = cfg
        app.add_api_route(
            _public_path(slug),
            _HANDLERS[slug],
            methods=list(VERB_METHODS),
            name=f"verb_{slug}",
            summary=verb.description,
        )

    # x402 paywall. Routes NOT in `routes` (/, /health, /catalog, ...) stay free.
    app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)

    # Rate limiter AFTER the paywall middleware -> sits OUTERMOST: floods get 429
    # before any payment verification. /health exempt for uptime monitors.
    @app.middleware("http")
    async def _rate_limit(request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        key = f"ip:{client_ip}"
        if not ratelimit.allow(key, settings.rate_limit_requests,
                               settings.rate_limit_window_seconds):
            retry = ratelimit.retry_after(key, settings.rate_limit_window_seconds)
            logger.warning("rate_limited ip=%s path=%s", client_ip, request.url.path)
            return JSONResponse(
                {"error": "rate_limited", "detail": "too many requests; slow down"},
                status_code=429, headers={"Retry-After": str(retry)},
            )
        return await call_next(request)

    @app.get("/")
    async def index() -> dict:
        base = settings.public_base_url.rstrip("/")
        return {
            "service": "Content Copilot",
            "icon": f"{base}/avatar.png",
            "summary": "Turn any raw source (podcast, video, article) into shipping-ready, "
                       "channel-native content packs — in the author's voice. Four verbs: "
                       "ingest -> mine -> pack -> ship. The x402 payment (USDT0 on OKX "
                       "X Layer) IS the access — no account or API key needed.",
            "network": settings.network,
            "how_it_works": "call /v1/<verb> (GET query params or POST JSON body) -> "
                            "HTTP 402 -> sign an x402 payment -> the verb runs; the "
                            "result is released after on-chain settlement.",
            "endpoints": {
                "catalog": "/catalog (free: verbs + prices)",
                "terms": "/terms (free)",
                "health": "/health",
                "verbs": "/v1/{ingest|mine|pack|ship} (paid; GET or POST)",
            },
        }

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "network": settings.network, "verbs": len(VERBS)}

    @app.api_route("/avatar.png", methods=["GET", "HEAD"], include_in_schema=False)
    async def avatar() -> FileResponse:
        # Marketplace/link-preview fetchers commonly probe HEAD first; a 405
        # there reads as "image missing". Serve both with open CORS + caching.
        return FileResponse(
            _AVATAR_PATH,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*",
            },
        )

    @app.get("/terms")
    async def terms(request: Request):
        body = {
            "terms": TERMS,
            "refunds": "failed or empty results are never billed (non-2xx skips settlement); "
                       "completed on-chain settlements are final",
            "network": settings.network,
            "asset": "USDT0",
        }
        if "text/html" in request.headers.get("accept", ""):
            html = (
                "<!doctype html><meta charset=utf-8>"
                "<title>Content Copilot — Terms</title>"
                "<body style=\"font:16px/1.6 system-ui;max-width:640px;margin:48px auto;"
                "padding:0 20px;color:#111\">"
                "<h1>Content Copilot — Terms</h1>"
                f"<p>{TERMS}</p>"
                f"<p><b>Network:</b> {settings.network} (X Layer) &nbsp;"
                "<b>Settlement asset:</b> USD₮0.</p></body>"
            )
            return HTMLResponse(html)
        return JSONResponse(body)

    @app.get("/services.json")
    async def services() -> JSONResponse:
        return JSONResponse(a2mcp_services())

    @app.get("/catalog")
    async def catalog() -> dict:
        base = settings.public_base_url.rstrip("/")
        return {
            "network": settings.network,
            "asset": "USDT0 (X Layer)",
            "pay_to": settings.pay_to_address,
            "icon": f"{base}/avatar.png",
            "terms_url": f"{base}/terms",
            "services_manifest": f"{base}/services.json",
            "full_pipeline_price": "$1.10 (ingest 0.10 + mine 0.25 + pack 0.50 + ship 0.25)",
            "verbs": [
                {
                    "verb": slug,
                    "methods": list(VERB_METHODS),
                    "path": _public_path(slug),
                    "price": v.price,
                    "description": v.description,
                    "params_via": "query string (GET) or JSON body (POST)",
                }
                for slug, v in VERBS.items()
            ],
        }

    @app.get("/admin/revenue", include_in_schema=False)
    async def admin_revenue(authorization: str = Header(default="")) -> dict:
        _require_admin(authorization)
        return await ledger.summary()

    @app.get("/admin/transactions", include_in_schema=False)
    async def admin_transactions(
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        authorization: str = Header(default=""),
    ) -> dict:
        _require_admin(authorization)
        summary = await ledger.summary()
        page = await ledger.transactions(limit=limit, offset=offset, status=status)
        return {
            "summary": summary,
            "network": settings.network,
            "asset": "USDT0 (X Layer)",
            **page,
        }

    return app


app = create_app()
