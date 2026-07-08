# Content Copilot — a paid ASP for OKX.AI

Turn any raw source (podcast, YouTube episode, long-form article) into
shipping-ready, channel-native content packs — in the author's own voice —
priced per call and settled on-chain.

> Submission for the **OKX.AI Genesis Hackathon** — Creative Genius + Social Buzz tracks.
>
> **Live gateway:** https://copilot.brunopessoa.com (catalog: [`/catalog`](https://copilot.brunopessoa.com/catalog))

## Why it exists

Every founder, operator, and creator sits on a pile of raw material — hours of
podcast audio, half-finished essays, live stream replays. Turning that into
distributed content (X threads, LinkedIn posts, IG Reel cutdowns, newsletter
blurbs) is the last-mile bottleneck. Content Copilot is that last mile as a
paid agent skill.

Behind the ASP is the pipeline pattern that runs the Cultura Builder / Bruno
Pessoa content fleet in production: caption-first transcription, LLM moment
mining tuned on real engagement data, voice-DNA rewriting, and per-channel
formatting rules (subtitle position math, hook shapes, banned-word lists)
learned from ~1200 real human rejections.

## The payment IS the access

No accounts, no API keys, no sign-up. Every verb sits behind an
**x402 payment wall** on OKX X Layer (`eip155:196`):

```
GET /v1/mine?session_id=…      -> HTTP 402 + PAYMENT-REQUIRED challenge
   (buyer agent signs an EIP-3009 authorization for USDT0)
GET /v1/mine + PAYMENT-SIGNATURE -> verb runs
   -> OKX Broker settles ON-CHAIN
   -> only then is the result released      (sync settle: no pay, no data)
```

Two properties we consider non-negotiable on a non-refundable rail:

- **Settle-before-deliver.** The response body is buffered and released only
  after on-chain settlement confirms (`exact` scheme only — no deferred paths).
- **Refuse-to-charge.** Any pipeline failure or empty result returns a non-2xx
  status, which skips settlement entirely. A buyer is never billed for a bad
  payload. (`X error — not billed` in every error detail.)

This includes a verified fix for an upstream SDK bug: the X Layer USDT0
contract's EIP-712 domain name is `USD₮0` (U+20AE), not `USDT` — without the
override in `app/main.py`, **every** buyer signature would be rejected as
`invalid_signature`.

## The four verbs

| Verb | Price | What it does |
|---|---|---|
| `GET /v1/ingest` | $0.10 | Download + transcribe a source. Caption-first (no compute when subtitles exist), faster-whisper fallback, article extraction. Returns `session_id`. |
| `GET /v1/mine` | $0.25 | Rank 10–40s segments by novelty, tension, stakes, quote-density, hookability. Returns ranked moments with verbatim quotes + confidence. |
| `GET /v1/pack` | $0.50 | Generate a channel-native pack from one moment: `x`, `linkedin`, `ig_reel` (ffmpeg cut spec + ASS subtitles), `newsletter`. Voice-profile pinned. |
| `POST /v1/ship` | $0.25 | Publish a pack via a server-registered downstream credential (Typefully, LinkedIn, Instagram Graph, Resend). Returns permalink. |

Full pipeline: **~$1.10 per finished, published post** — versus $50–150 for a
freelance short-form edit. Free discovery: [`/catalog`](https://copilot.brunopessoa.com/catalog),
[`/terms`](https://copilot.brunopessoa.com/terms), `/services.json` (A2MCP manifest).

## Repo layout

```
app/                  # the PAID surface (FastAPI + x402 payment middleware)
  main.py             #   verbs, 402 challenges, refuse-to-charge mapping, USD₮0 fix
  ledger.py           #   settlement ledger: per-nonce idempotency + revenue audit
  config.py           #   env-driven settings (pricing, network, credentials)
src/                  # the pipeline engine
  ingest.py           #   caption-first transcription + article extraction
  mine.py             #   LLM moment scoring (weighted 5-dimension rubric)
  pack.py             #   per-channel generation with voice DNA + hard validation
  ship.py             #   downstream publish adapters
  llm.py              #   dispatch-first LLM backend abstraction
  server.py           #   MCP stdio server (unmetered local mode)
tests/                # 37 tests: pipeline units, 402 challenge shape, ledger
scripts/
  live_settle_test.py # real buyer: full paid pipeline with on-chain settles
```

## Run it locally

```bash
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt

# unmetered local MCP mode (plug into Claude Code / any MCP client)
.venv/bin/python -m src.server

# paid gateway (needs OKX seller creds — see .env.example)
.venv/bin/uvicorn app.main:app --port 8788

# tests
.venv/bin/python -m pytest tests/ -q
```

## Buy it like an agent would

```bash
# funded X Layer wallet JSON: {"private_key": "0x..."}
BUYER_WALLET_JSON=./buyer.json \
  .venv/bin/python scripts/live_settle_test.py https://paulgraham.com/greatwork.html
```

Each step 402-challenges, signs, settles on-chain in USD₮0, and prints the
delivered payload. Transaction hashes land in the operator ledger
(`/admin/transactions`) and on [OKLink](https://www.oklink.com/x-layer).

## Status vs hackathon rules

| Rule | Status |
|---|---|
| Build an ASP solving a real use case | ✅ live paid pipeline |
| Pass OKX AI internal review + go live | ⏳ listing in progress |
| X post with #OKXAI + ≤90s demo | ⏳ storyboard + live-settle demo ready |
| Google Form by 2026-07-17 22:59 UTC | ⏳ answers drafted |
