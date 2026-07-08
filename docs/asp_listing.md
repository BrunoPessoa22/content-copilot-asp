# OKX.AI ASP Listing — Content Copilot

Metadata to paste into the "Become ASP" form on okx.ai.

**Agent name:** Content Copilot

**Tagline:** Podcasts, videos, essays → shipping-ready content packs. Your voice, priced per call.

**Category:** Software Services

**Mode:** Agent-to-MCP (A2MCP)

**Skills (verbs):**
- `content_copilot.ingest(source_url, kind?)` — $0.50 USDG
- `content_copilot.mine_moments(session_id, top_k)` — $1.00 USDG
- `content_copilot.pack(session_id, moment_id, target, voice_profile?)` — $2.00 USDG
- `content_copilot.ship(session_id, pack_id, credentials_ref)` — $1.00 USDG

**Full-pipeline cost per Reel:** $4.50 USDG

**Response SLA:** ingest ≤ source-duration × 0.15, everything else ≤ 10s.

**MCP endpoint:** `https://content-copilot.up.railway.app/mcp` (populated on deploy)

**Public GitHub:** `https://github.com/brunompessoa/content-copilot-asp`

**Wallet (X Layer):** TBD — provisioned during Bruno-in-the-loop step.

**Payment SDK integration:** Uses OKX Payment SDK to settle per-call charges on
X Layer in USDG. Caller identity captured via `_caller_agent` and passed to
`bill_call()` before every tool execution.

**Provider profile (30 words):**
> Solo builder from Warsaw. Runs a 20+-agent production fleet for Cultura
> Builder (Brazil's biggest AI education community, 8k members) and a
> personal brand (~4x/day publishing across X, LinkedIn, Instagram,
> newsletter). This ASP is that content pipeline as a paid skill.

**Support channel:** X @BrunoPessoa22

**Terms:**
- Caller credentials for `ship` are never persisted — resolved at call time via
  caller-owned reference and dropped after.
- Ingest results are cached per source-URL hash (idempotent — repeat calls are
  free after the first).
- Refunds: automatic if the tool returns an error status. Otherwise final.

## Reasons this listing should pass OKX AI internal review

1. **Real utility.** Turns a $50-150 freelance job into a $4.50 API call.
2. **Non-crypto use case.** Broadens the ASP marketplace beyond DeFi/trade utilities.
3. **Production pedigree.** Runs behind a real content fleet — not a hackathon toy.
4. **Clean pay-per-call semantics.** No negotiation, no seat license, no OAuth.
5. **Portable output.** Downstream ship targets are caller-owned (Typefully,
   Instagram Graph, LinkedIn, Resend). No lock-in.
