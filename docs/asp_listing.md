# OKX.AI ASP Listing — Content Copilot

Registration happens through the `onchainos` CLI (`agent pre-check --role asp`
→ field collection → `validate-listing` → `agent create` → `activate #id`),
authenticated by the OKX Agentic Wallet. The values below are pre-drafted to
the CLI's ACTUAL validation rules (verified against okx/onchainos-skills
`identity-register.md`):

- Agent name: EN 3–25 chars, brand-like, no celebrity/test markers
- Agent description: one sentence, ≤500 chars
- Avatar: **image file upload required** (1:1; links rejected) — use
  `app/static/avatar.png` from this repo (also served at
  https://copilot.brunopessoa.com/avatar.png for the marketplace icon)
- Service name: 5–30 chars, descriptive noun phrase, no price in name
- Service description: **two parts on separate lines** — ① core capability
  (what + for whom) ② what the caller must provide. Each ≤200 chars, total
  ≤400. **No GitHub/wallet links, no tech-stack details, no disclaimers.**
- Type: `A2MCP` (API service) · Fee: plain number string, **USDT**, no symbol
- Endpoint: public https URL, already deployed (permanent on-chain)

---

## Step 1 · Identity

**Name:** Content Copilot

**Description (≤500):**
Turns any podcast, video, or article link into ready-to-publish social content
— ranked shareable moments, then finished posts for X, LinkedIn, Instagram
Reels, or newsletters, written in the author's own voice and priced per call.

**Avatar:** upload `app/static/avatar.png` (1024×1024 PNG).

## Step 2 · Services (4 — complete the add-another loop, then Done)

### Service 1
- **Name:** Source Transcript Ingestion
- **Description:**
  Turns a public podcast, video, or article link into a timestamped transcript
  session, ready for moment mining and content creation.
  Provide: 1. source link (podcast, video, or article URL)
- **Type:** A2MCP
- **Fee:** `0.1`
- **Endpoint:** `https://copilot.brunopessoa.com/v1/ingest`

### Service 2
- **Name:** Shareable Moment Mining
- **Description:**
  Finds and ranks the most shareable 10-40 second moments of an ingested
  source by novelty, tension, stakes, and quotability, for creators and
  marketing teams.
  Provide: 1. session id from ingestion 2. how many moments you want
- **Type:** A2MCP
- **Fee:** `0.25`
- **Endpoint:** `https://copilot.brunopessoa.com/v1/mine`

### Service 3
- **Name:** Channel Content Pack Writing
- **Description:**
  Writes a ready-to-publish post from one mined moment for X, LinkedIn,
  Instagram Reel, or newsletter, matched to the author's voice and each
  channel's format rules.
  Provide: 1. session id 2. moment id 3. target channel 4. voice profile
- **Type:** A2MCP
- **Fee:** `0.5`
- **Endpoint:** `https://copilot.brunopessoa.com/v1/pack`

### Service 4
- **Name:** Content Pack Publishing
- **Description:**
  Publishes a finished content pack to the destination channel and returns
  the live post link.
  Provide: 1. session id 2. pack id 3. registered publishing credential name
- **Type:** A2MCP
- **Fee:** `0.25`
- **Endpoint:** `https://copilot.brunopessoa.com/v1/ship`

---

## Reasons this listing should pass OKX AI internal review

1. **Real utility, non-crypto use case.** Turns a $50–150 freelance job into a
   ~$1.10 pipeline; broadens the marketplace beyond DeFi utilities.
2. **The endpoint is LIVE and actually settles.** Full x402 flow proven with
   real on-chain USDT0 settles on X Layer — not a stub.
3. **Buyer-protective billing.** Sync settle (no pay, no data) + refuse-to-
   charge (failed/empty results return non-2xx and are never billed).
4. **Clean pay-per-call semantics.** No negotiation, no subscription, no OAuth.
5. **Production pedigree.** Built on a content pipeline pattern running in
   production for a real 8k-member community's content ops.
