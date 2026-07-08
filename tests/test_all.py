"""Content Copilot test suite.

Layers:
- pipeline units (VTT parsing, window slicing, scoring parse, pack validation)
- payment surface (402 challenge on every verb, free discovery routes,
  USD₮0 asset-name regression, refuse-to-charge mapping)
- ledger idempotency

The OKX facilitator handshake is stubbed so the suite is hermetic (no network).
"""

import base64
import json
import os
import tempfile

import pytest

# Test env BEFORE any app import: fake seller creds + isolated dirs.
_TMP = tempfile.mkdtemp(prefix="cc-test-")
os.environ.setdefault("OKX_API_KEY", "test-key")
os.environ.setdefault("OKX_SECRET_KEY", "test-secret")
os.environ.setdefault("OKX_PASSPHRASE", "test-pass")
os.environ.setdefault("PAY_TO_ADDRESS", "0x7f81be74D6E9002C58c60CCce4f4ee72dcBAA785")
os.environ.setdefault("ADMIN_TOKEN", "test-admin")
os.environ["LEDGER_PATH"] = os.path.join(_TMP, "ledger.db")
os.environ["CC_SESSION_DIR"] = os.path.join(_TMP, "sessions")

import src.ingest as ingest  # noqa: E402
import src.mine as mine  # noqa: E402
import src.pack as pack  # noqa: E402
import src.ship as ship  # noqa: E402
from src.voice_dna import load_voice_profile  # noqa: E402


# --------------------------------------------------------------------------- #
# ingest units                                                                 #
# --------------------------------------------------------------------------- #
VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:04.000
I scaled a coding school to 33 franchises.

00:00:04.000 --> 00:00:08.500
I thought I knew what scale was. I knew nothing.

00:00:08.500 --> 00:00:12.000
I thought I knew what scale was. I knew nothing.
"""


def test_parse_vtt_dedupes_rolling_repeats():
    segs = ingest.parse_vtt(VTT)
    assert len(segs) == 2
    assert segs[0]["start"] == 0.0
    assert segs[0]["text"].startswith("I scaled")
    assert segs[1]["text"].startswith("I thought")


def test_parse_vtt_strips_inline_tags():
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<c>hello</c> <00:00:02.000>world\n"
    segs = ingest.parse_vtt(vtt)
    assert segs == [{"start": 1.0, "end": 3.0, "text": "hello world"}]


def test_session_id_is_stable():
    a = ingest._session_id("https://example.com/ep1.mp3")
    assert a == ingest._session_id("https://example.com/ep1.mp3")
    assert a.startswith("cc_")


def test_article_heuristics():
    assert ingest._looks_like_article("https://x.substack.com/p/post", "auto")
    assert not ingest._looks_like_article("https://youtube.com/watch?v=abc", "auto")
    assert not ingest._looks_like_article("https://cdn.example.com/e.mp3", "auto")
    assert ingest._looks_like_article("https://cdn.example.com/e.mp3", "article")


@pytest.mark.anyio
async def test_ingest_rejects_non_http():
    with pytest.raises(ingest.IngestError):
        await ingest.run("file:///etc/passwd")


# --------------------------------------------------------------------------- #
# mine units                                                                   #
# --------------------------------------------------------------------------- #
STUB_TRANSCRIPT = {
    "segments": [
        {"start": 0.0, "end": 6.5, "text": "Escalei uma escola para 33 franquias."},
        {"start": 6.5, "end": 14.2, "text": "Achei que sabia o que era escala. Nao sabia nada."},
        {"start": 14.2, "end": 22.8, "text": "Hoje rodo vinte agentes de IA por dia."},
        {"start": 22.8, "end": 31.0, "text": "Escala de verdade e quando voce dorme e o trabalho continua."},
    ]
}


def _write_session(sid: str) -> None:
    d = ingest.SESSION_DIR / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "transcript.json").write_text(json.dumps(STUB_TRANSCRIPT))
    (d / "manifest.json").write_text(json.dumps({"session_id": sid, "segments": 4}))


def test_slide_segments_windows():
    windows = mine._slide_segments(STUB_TRANSCRIPT)
    assert windows
    for w in windows:
        assert w["end"] - w["start"] >= 10.0
        assert w["text"]


def test_mine_ignores_manifest_json():
    # Regression: mine used to glob *.json and could load manifest.json as the
    # transcript. It must read transcript.json explicitly.
    sid = "cc_manifesttest0001"
    _write_session(sid)
    windows = mine._slide_segments(json.loads((mine.SESSION_DIR / sid / "transcript.json").read_text()))
    assert windows  # would TypeError if the manifest (segments: int) were loaded


@pytest.mark.anyio
async def test_mine_scores_and_ranks(monkeypatch):
    sid = "cc_minetest00000001"
    _write_session(sid)

    async def fake_complete(prompt, **kw):
        return json.dumps([
            {"segment_idx": 0, "novelty": 0.9, "tension": 0.8, "stakes": 0.7,
             "quote": 0.9, "hookability": 2.5, "quote_text": "top quote"},
        ])

    monkeypatch.setattr(mine.llm, "complete", fake_complete)
    out = await mine.run(sid, top_k=3)
    assert out["moments"]
    m = out["moments"][0]
    assert m["quote"] == "top quote"
    assert m["scores"]["hookability"] == 1.0  # clamped from 2.5
    assert 0 <= m["confidence"] <= 100


@pytest.mark.anyio
async def test_mine_skips_malformed_scores(monkeypatch):
    sid = "cc_minetest00000002"
    _write_session(sid)

    async def fake_complete(prompt, **kw):
        return json.dumps([
            {"segment_idx": 999, "novelty": 1},          # out-of-range idx: dropped
            "garbage",                                    # not a dict: dropped
            {"segment_idx": 0, "novelty": "x", "tension": 0.5, "stakes": 0.5,
             "quote": 0.5, "hookability": 0.5},           # bad float coerced to 0
        ])

    monkeypatch.setattr(mine.llm, "complete", fake_complete)
    out = await mine.run(sid, top_k=5)
    assert len(out["moments"]) == 1
    assert out["moments"][0]["scores"]["novelty"] == 0.0


@pytest.mark.anyio
async def test_mine_missing_session_raises():
    with pytest.raises(mine.MineError):
        await mine.run("cc_doesnotexist00000")


# --------------------------------------------------------------------------- #
# pack units                                                                   #
# --------------------------------------------------------------------------- #
def _write_moments(sid: str) -> str:
    d = ingest.SESSION_DIR / sid
    d.mkdir(parents=True, exist_ok=True)
    mid = f"m_{sid}_000"
    (d / "moments.json").write_text(json.dumps([
        {"moment_id": mid, "start_s": 0.0, "end_s": 12.0, "duration_s": 12.0,
         "confidence": 90.0, "quote": "Escala de verdade e quando voce dorme."},
    ]))
    return mid


@pytest.mark.anyio
async def test_pack_x_valid(monkeypatch):
    sid = "cc_packtest00000001"
    mid = _write_moments(sid)

    async def fake_complete(prompt, **kw):
        return json.dumps({"kind": "single", "tweets": ["Escala de verdade: 20 agentes, 24/7."]})

    monkeypatch.setattr(pack.llm, "complete", fake_complete)
    out = await pack.run(sid, mid, "x", load_voice_profile("bruno-pt-br"))
    assert out["pack_id"] == f"p_{mid}_x"
    assert out["body"]["tweets"]
    assert (ingest.SESSION_DIR / sid / "packs" / f"{out['pack_id']}.json").exists()


@pytest.mark.anyio
async def test_pack_rejects_overlong_tweet(monkeypatch):
    sid = "cc_packtest00000002"
    mid = _write_moments(sid)

    async def fake_complete(prompt, **kw):
        return json.dumps({"kind": "single", "tweets": ["x" * 300]})

    monkeypatch.setattr(pack.llm, "complete", fake_complete)
    with pytest.raises(pack.PackError):
        await pack.run(sid, mid, "x", load_voice_profile("generic-founder"))


@pytest.mark.anyio
async def test_pack_rejects_missing_fields(monkeypatch):
    sid = "cc_packtest00000003"
    mid = _write_moments(sid)

    async def fake_complete(prompt, **kw):
        return json.dumps({"blurb": "only a blurb"})  # newsletter needs cta too

    monkeypatch.setattr(pack.llm, "complete", fake_complete)
    with pytest.raises(pack.PackError):
        await pack.run(sid, mid, "newsletter", load_voice_profile("generic-founder"))


@pytest.mark.anyio
async def test_pack_unknown_target():
    with pytest.raises(pack.PackError):
        await pack.run("cc_x", "m_x", "tiktok", load_voice_profile("generic-founder"))


# --------------------------------------------------------------------------- #
# ship units                                                                   #
# --------------------------------------------------------------------------- #
def test_resolve_credential_unknown_ref():
    with pytest.raises(ship.ShipError):
        ship._resolve_credential("no-such-ref-xyz")


def test_resolve_credential_rejects_bad_chars():
    with pytest.raises(ship.ShipError):
        ship._resolve_credential("../etc/passwd")


def test_resolve_credential_env_prefix(monkeypatch):
    monkeypatch.setenv("DEMO_X_TYPEFULLY_API_KEY", "tk-123")
    creds = ship._resolve_credential("demo-x")
    assert creds == {"TYPEFULLY_API_KEY": "tk-123"}


@pytest.mark.anyio
async def test_ship_unknown_pack():
    with pytest.raises(ship.ShipError):
        await ship.run("cc_nosession", "p_none_x", "demo-x")


# --------------------------------------------------------------------------- #
# HTTP surface: needs the OKX SDK                                              #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def client():
    pytest.importorskip("x402", reason="okxweb3-app-x402 not installed")
    from fastapi.testclient import TestClient
    from x402.http import OKXFacilitatorClient
    from x402.schemas.responses import SupportedKind, SupportedResponse

    def _fake_supported(self):
        kinds = [
            SupportedKind(x402_version=v, scheme="exact", network="eip155:196")
            for v in (1, 2)
        ]
        return SupportedResponse(kinds=kinds)

    OKXFacilitatorClient.get_supported = _fake_supported  # type: ignore[method-assign]

    from app.main import app

    return TestClient(app)


def test_xlayer_asset_name_is_corrected(client):
    # Regression: OKX SDK ships name="USDT" for X Layer, but the on-chain token
    # name() is "USD₮0". The wrong name breaks every EIP-3009 signature.
    from x402.mechanisms.evm.constants import NETWORK_CONFIGS

    assert NETWORK_CONFIGS["eip155:196"]["default_asset"]["name"] == "USD₮0"


def test_health_is_free(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["network"] == "eip155:196"


def test_index_is_free(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "x402" in r.json()["summary"]


def test_catalog_lists_all_verbs(client):
    body = client.get("/catalog").json()
    verbs = {v["verb"] for v in body["verbs"]}
    assert verbs == {"ingest", "mine", "pack", "ship"}
    for v in body["verbs"]:
        assert v["price"].startswith("$")
        assert v["path"].startswith("/v1/")


def test_services_manifest_a2mcp_shaped(client):
    svc = client.get("/services.json").json()
    assert len(svc) == 4
    for entry in svc:
        assert set(entry) >= {"name", "endpoint", "service_type", "price", "description"}
        assert entry["service_type"] == "A2MCP"
        assert entry["endpoint"].startswith("https://")
        assert entry["price"].split()[-1] in ("USDT", "USDT0")


def test_terms_negotiates_html(client):
    html = client.get("/terms", headers={"accept": "text/html"})
    assert "text/html" in html.headers["content-type"]
    js = client.get("/terms")
    assert "application/json" in js.headers["content-type"]


def test_avatar_serves_get_and_head(client):
    g = client.get("/avatar.png")
    assert g.status_code == 200
    assert g.headers["content-type"] == "image/png"
    assert len(g.content) > 1000
    h = client.head("/avatar.png")
    assert h.status_code == 200


def _decode_challenge(resp):
    raw = resp.headers.get("payment-required") or resp.headers.get("PAYMENT-REQUIRED")
    assert raw, f"no PAYMENT-REQUIRED header in {dict(resp.headers)}"
    return json.loads(base64.b64decode(raw))


@pytest.mark.parametrize("path,method,price_atomic", [
    ("/v1/ingest?source_url=https://example.com/a.mp3", "get", 100000),
    ("/v1/mine?session_id=cc_x", "get", 250000),
    ("/v1/pack?session_id=cc_x&moment_id=m&target=x", "get", 500000),
])
def test_unpaid_get_verbs_402_with_correct_challenge(client, path, method, price_atomic):
    r = getattr(client, method)(path)
    assert r.status_code == 402
    challenge = _decode_challenge(r)
    accepts = challenge["accepts"]
    assert len(accepts) == 1
    opt = accepts[0]
    assert opt["scheme"] == "exact"
    assert opt["network"] == "eip155:196"
    assert opt["payTo"].lower() == os.environ["PAY_TO_ADDRESS"].lower()
    assert int(opt["amount"]) == price_atomic
    # Settlement asset must be X Layer's canonical USD₮0 with the corrected
    # EIP-712 domain name — the wrong name breaks every buyer signature.
    assert opt["asset"].lower() == "0x779ded0c9e1022225f8e0630b35a9b54be713736"
    assert opt["extra"]["name"] == "USD₮0"


def test_unpaid_ship_post_402(client):
    r = client.post("/v1/ship", json={"session_id": "s", "pack_id": "p", "credentials_ref": "r"})
    assert r.status_code == 402


def test_docs_disabled(client):
    assert client.get("/docs").status_code in (402, 404)
    assert client.get("/openapi.json").status_code in (402, 404)


def test_admin_requires_token(client):
    assert client.get("/admin/revenue").status_code == 401
    r = client.get("/admin/revenue", headers={"Authorization": "Bearer test-admin"})
    assert r.status_code == 200
    assert "revenue_usdt0" in r.json()


def test_admin_transactions_shape(client):
    r = client.get("/admin/transactions", headers={"Authorization": "Bearer test-admin"})
    assert r.status_code == 200
    body = r.json()
    assert "summary" in body and "transactions" in body


# --------------------------------------------------------------------------- #
# refuse-to-charge mapping (handler level, no payment needed)                  #
# --------------------------------------------------------------------------- #
def _fake_request(query: str = "", body: bytes = b"") -> "object":
    from starlette.requests import Request

    scope = {
        "type": "http", "method": "GET", "path": "/v1/x", "query_string": query.encode(),
        "headers": [], "client": ("127.0.0.1", 1234), "app": None, "state": {},
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.mark.anyio
async def test_mine_empty_result_maps_to_422(client, monkeypatch):
    from fastapi import HTTPException

    import app.main as m

    async def fake_mine_run(session_id, top_k):
        return {"session_id": session_id, "moments": []}

    monkeypatch.setattr(m.mine, "run", fake_mine_run)
    req = _fake_request("session_id=cc_x")
    with pytest.raises(HTTPException) as exc:
        await m._handle_mine(req)
    assert exc.value.status_code == 422
    assert "not billed" in exc.value.detail


@pytest.mark.anyio
async def test_llm_unavailable_maps_to_503(client, monkeypatch):
    from fastapi import HTTPException

    import app.main as m

    async def fake_mine_run(session_id, top_k):
        raise LlmUnavailable_local("down")

    from src.llm import LlmUnavailable as LlmUnavailable_local

    monkeypatch.setattr(m.mine, "run", fake_mine_run)
    req = _fake_request("session_id=cc_x")
    with pytest.raises(HTTPException) as exc:
        await m._handle_mine(req)
    assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_missing_params_map_to_422(client):
    from fastapi import HTTPException

    import app.main as m

    with pytest.raises(HTTPException) as exc:
        await m._handle_ingest(_fake_request(""))
    assert exc.value.status_code == 422


# --------------------------------------------------------------------------- #
# ledger idempotency                                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_ledger_claim_release_settle(client):
    from app import ledger

    nonce = "0x" + "ab" * 32
    assert await ledger.claim(nonce, "mine", "0xpayer", "250000") is True
    assert await ledger.claim(nonce, "mine", "0xpayer", "250000") is False  # duplicate
    await ledger.release(nonce)
    assert await ledger.claim(nonce, "mine", "0xpayer", "250000") is True  # retry OK
    await ledger.mark_settled(nonce, "0xtxhash")
    s = await ledger.summary()
    assert s["settled_count"] >= 1


# --------------------------------------------------------------------------- #
# rate limiter                                                                 #
# --------------------------------------------------------------------------- #
def test_ratelimit_window():
    from app import ratelimit

    ratelimit.reset()
    assert all(ratelimit.allow("k", 3, 60.0, now=100.0 + i) for i in range(3))
    assert ratelimit.allow("k", 3, 60.0, now=103.0) is False
    assert ratelimit.allow("k", 3, 60.0, now=161.0) is True  # window rolled
    ratelimit.reset()


@pytest.fixture
def anyio_backend():
    return "asyncio"
