# Google Form — pre-filled answers (draft)

The actual Google Form URL is revealed after registering on hackquest.io. These
are the answers to paste when the form appears. All fields drafted to the volume
mandate ("say more, not less"). Bruno can trim on submission.

---

**Project name:** Content Copilot

**One-line description:** Any raw source (podcast, video, article) becomes
shipping-ready multi-channel content packs — in the caller's own voice — through
a pay-per-call MCP ASP on OKX.AI.

**Track(s) applied:** Creative Genius, Social Buzz

**Category (for track-tier prize):** Software Services

**ASP mode:** Agent-to-MCP (A2MCP)

**Pricing:** $0.50 (ingest) + $1.00 (mine) + $2.00 (pack) + $1.00 (ship). Full
pipeline for one Reel: $4.50. Compared to $50-150 freelance short-form edit ≈ 10×
cost reduction.

**OKX.AI ASP listing URL:** `https://okx.ai/agents/content-copilot` (populated once
listing is approved)

**GitHub repo:** `https://github.com/brunompessoa/content-copilot-asp`

**X post URL:** `https://x.com/BrunoPessoa22/status/<id>` (populated after posting)

**Demo video URL:** embedded in X post above, ≤90s.

**Team:** Bruno Pessoa (solo builder). Reused the Falcao/Tucano pipeline already
running in production for Cultura Builder (8k+ member AI community).

**Contact email:** bmpessoa22@gmail.com

**X handle:** @BrunoPessoa22

---

## Long-form: "Why this ASP" (500-word cap)

Every founder and creator sits on hours of raw source material — podcasts,
YouTube episodes, live streams, essays — that never becomes distributed content
because turning it into channel-native output is slow, tedious, and expensive.

Content Copilot is that last mile as a paid agent skill. Four MCP verbs, priced
per call, running on the same production pipeline that powers a real 8k-member
AI education community's content ops (Cultura Builder + Bruno Pessoa's personal
brand, ~4x/day publishing across X / LinkedIn / Instagram / newsletter for over
a year).

The scoring weights inside `mine_moments` were learned from ~1200 real
rejection notes captured through a human-in-the-loop approval gate. That data
isn't reproducible from a weekend build — it's what makes the output feel like
the author wrote it, not like an LLM wrote it.

The channel rules inside `pack` are equally battle-tested: subtitle position
math for IG Reels (FontSize 12 Bold 0 Alignment 2 MarginV 280-320 for
1080x1920 vertical), hook rules for X (first-person stake, never "Tem gente que
acha…"), speaker-verification for Reel crops (identify actual speaker by name-tag
+ mouth movement before 9:16 crop, panorama letterbox as safe fallback). Each
rule started as a post that Bruno rejected on his phone.

The A2MCP fit is exact: standardized skill call, no negotiation, price is
posted, payment settles instantly on X Layer through the OKX Payment SDK. Any
calling agent — a personal ops agent, a marketing SDR agent, another creator's
agent — pays per pack. No subscription, no seat license, no login. Just calls.

The 10× cost reduction versus freelance short-form editing ($4.50 vs $50-150
per Reel) is the wedge. The voice DNA is the moat.

---

## FAQ answers

**Q: Is my ASP crypto-related?**
A: No — it's non-crypto by design (content generation for creators and
operators). Payment rails are the only crypto element. This makes it eligible
for the "crypto and non-crypto services welcome" scope.

**Q: What does the X participation post include?**
A: A ≤90s demo video showing a full pipeline call (ingest → mine → pack → ship),
the ASP marketplace link, GitHub repo link, and `#OKXAI` tag.

**Q: Team size?**
A: Solo builder, reusing production infrastructure from a live agent fleet.

**Q: Deployment status?**
A: MCP server built. Pending OKX Payment SDK integration + wallet provisioning
before listing goes live on `okx.ai/agents`.
