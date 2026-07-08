# Google Form — pre-filled answers

Form: https://forms.gle/mddEUagmDbyV37ws8 (from the hackathon page).
Deadline: **2026-07-17 22:59 UTC** (submit a day early; the page lists 22:59
for the window and 23:59 for the form — don't gamble on the later one).

---

**Project name:** Content Copilot

**One-line description:** Any raw source (podcast, video, article) becomes
shipping-ready multi-channel content packs — in the author's own voice —
through a pay-per-call ASP settled on-chain via x402 on X Layer.

**Track(s) applied:** Creative Genius, Social Buzz

**ASP mode:** Agent-to-MCP (A2MCP)

**Pricing:** $0.10 (ingest) + $0.25 (mine) + $0.50 (pack) + $0.25 (ship),
settled per call in USDT0 on X Layer. Full pipeline for one finished post:
~$1.10 — versus $50–150 freelance short-form editing.

**OKX.AI ASP listing URL:** `<populated once the listing is approved>`

**Live endpoint:** https://copilot.brunopessoa.com (free discovery: /catalog)

**GitHub repo:** https://github.com/BrunoPessoa22/content-copilot-asp

**X post URL:** `<populated after posting>`

**Demo video URL:** embedded in the X post, ≤90s.

**Team:** Bruno Pessoa (solo builder). Reuses the content pipeline pattern
already running in production for Cultura Builder (8k+ member AI community).

**Contact email:** bmpessoa22@gmail.com

**X handle:** @BrunoPessoa22

---

## Long-form: "Why this ASP" (500-word cap)

Every founder and creator sits on hours of raw source material — podcasts,
YouTube episodes, live streams, essays — that never becomes distributed
content, because turning it into channel-native output is slow, tedious, and
expensive.

Content Copilot is that last mile as a paid agent skill: four verbs (ingest →
mine → pack → ship), each priced per call and settled on-chain. It runs on the
same production pipeline pattern that powers a real 8k-member AI education
community's content ops (~4x/day publishing across X, LinkedIn, Instagram, and
newsletter for over a year).

The moment-mining rubric (novelty, tension, stakes, quote-density,
hookability) was tuned on ~1200 real human rejections captured through a
human-in-the-loop approval gate. The channel rules inside pack are equally
battle-tested: subtitle position math for vertical Reels, hook rules for X,
banned-word lists per channel. Each rule started as a post a human rejected.

Two things make this a serious ASP rather than a demo:

1. **The payments are real.** Every verb sits behind an x402 payment wall on
X Layer. The response is buffered and released only after the OKX Broker
confirms on-chain settlement — no pay, no data. Failed or empty results
return an error status and are never billed. We even found and fixed an
upstream SDK bug where the USDT0 EIP-712 domain name ("USD₮0", not "USDT")
would have rejected every buyer signature — the fix ships in the repo with a
regression test, and real on-chain settles prove the full path.

2. **The economics are honest.** ~$1.10 for a finished, published post versus
$50–150 freelance — a genuine 50–100x cost reduction with instant turnaround.
The A2MCP fit is exact: standardized skill call, posted price, instant
settlement, no subscription, no login. Any calling agent — a personal ops
agent, a marketing agent, another creator's agent — pays per pack.

The 10× cost cut is the wedge. The voice DNA is the moat.

---

## FAQ answers

**Q: Is my ASP crypto-related?**
A: No — it's a non-crypto service (content generation for creators and
operators). The payment rail is the only crypto element, which fits the
"crypto and non-crypto services welcome" scope.

**Q: What does the X participation post include?**
A: A ≤90s demo showing a full paid pipeline call (402 challenge → on-chain
settle → delivered pack → live post), the marketplace listing link, and #OKXAI.

**Q: Team size?**
A: Solo builder, reusing production infrastructure from a live agent fleet.

**Q: Deployment status?**
A: Live at https://copilot.brunopessoa.com with real on-chain settlement
verified end-to-end (transactions visible on OKLink / X Layer).
