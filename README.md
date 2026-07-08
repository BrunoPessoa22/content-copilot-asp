# Content Copilot — an OKX.AI ASP

Turn any raw source (podcast, YouTube episode, long-form article, tweet-thread) into
shipping-ready multi-channel content packs in the caller's own voice.

> Submission for the **OKX.AI Genesis Hackathon** — Creative Genius + Social Buzz tracks.

## Why it exists

Every founder, operator, and creator sits on a pile of raw material — hours of podcast
audio, half-finished essays, screen recordings, live stream replays. Turning that into
distributed content (X threads, LinkedIn posts, IG Reel cutdowns, newsletter blurbs) is
the last-mile bottleneck. Content Copilot is that last mile as a paid agent skill.

Behind the ASP is the pipeline that already runs the Cultura Builder / Bruno Pessoa
content fleet in production: Whisper transcription, LLM moment-mining tuned on real
engagement data, voice-DNA rewriting, and per-channel formatting rules (subtitle
positions, hook shapes, tone banned-word lists) that were learned from thousands of
rejection notes.

## The four verbs (MCP surface)

Every ASP call is idempotent and priced separately.

| Tool | What it does | Price (draft) |
|---|---|---|
| `content_copilot.ingest(source_url, kind?)` | Downloads + transcribes (Whisper) + diarizes. Returns `session_id`. | $0.50 |
| `content_copilot.mine_moments(session_id, top_k=10)` | LLM-ranks 10-40s segments by novelty, tension, stakes, quote-density. Returns ranked moments with confidence + verbatim quote. | $1.00 |
| `content_copilot.pack(session_id, moment_id, target, voice_profile?)` | Generates a channel-native content pack. Targets: `x` (tweet or thread), `linkedin` (long-form post), `ig_reel` (ffmpeg cut spec + ASS subtitles + hook), `newsletter` (blurb + CTA). | $2.00 |
| `content_copilot.ship(session_id, pack_id, credentials_ref)` | Publishes via caller-supplied downstream (Typefully, Instagram Graph, LinkedIn, Resend). Returns permalink. | $1.00 |

Total pipeline cost for one Reel: ~$4.50. Compared to a $50-150 freelance short-form
edit + $30 caption edit, that's a ~10× cost reduction with instant turnaround.

## Marketplace mode

**A2MCP (Agent-to-MCP)** — pay-per-call, no negotiation, requires OKX Payment SDK.
Fits standardized skill-call semantics: any calling agent invokes a verb and pays.

## Track fit

- **Creative Genius ($20K)** — the pipeline turns dead-weight source material into
  shippable creative output. That's the whole track.
- **Social Buzz ($10K)** — the ASP itself will publish real content demoing itself.
  Recursive social proof: every demo pack it ships is also its marketing.
- **Software Utility ($7.5K, secondary)** — clean MCP surface, priced per call.

## Repo layout

```
src/
  server.py           # MCP server exposing the 4 verbs
  ingest.py           # Whisper + yt-dlp source download
  mine.py             # LLM moment scoring
  pack.py             # Per-channel generation with voice DNA
  ship.py             # Downstream publisher adapters
  voice_dna.py        # Bruno-voice + generic voice profile loader
demo/
  storyboard.md       # 90s X demo shot list
  test_call.py        # End-to-end call script for demo
docs/
  asp_listing.md      # OKX.AI listing metadata (name, tagline, pricing)
  google_form.md      # Pre-filled hackquest.io Google Form answers
```

## Quick start (local, no OKX SDK yet)

```bash
pip install -r requirements.txt
python -m src.server --port 8787
# In another shell — full pipeline call:
python demo/test_call.py https://www.youtube.com/watch?v=DX6s6NGgLj2
```

## Deployment target

- **Runtime:** Railway (same infra pattern as fan-token-intel MCP server).
- **Marketplace listing:** OKX.AI ASP, mode A2MCP.
- **Payment:** X Layer USDT/USDG per call, settled through OKX Payment SDK.

## Status vs hackathon rules

| Rule | Status |
|---|---|
| Build an ASP solving a real-world use case | ✅ shipping pipeline behind it |
| Pass OKX AI internal review + go live | ⏳ pending wallet + SDK integration |
| X post with #OKXAI + ≤90s demo | ✅ storyboard drafted in `demo/storyboard.md` |
| Google Form by 2026-07-17 22:59 UTC | ⏳ answers drafted in `docs/google_form.md` |
