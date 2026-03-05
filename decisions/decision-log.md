# Decision Log

*Append-only. Never edit past entries — only add new ones.*

---

## DEC-001 — 2026-03-05 — Project Framework
**Decided by:** Joint
**Decision:** Adopt the Dale framework with file-based state, public ledger, ethics charter.
**Rationale:** Need structured context persistence across sessions. Git history = long-term memory.
**Status:** EXECUTED

## DEC-002 — 2026-03-05 — Agent Name
**Decided by:** Benedict
**Decision:** Name the AI agent "Dale" after The Castle (1997).
**Rationale:** Australian, memorable, has built-in language for failed ideas ("tell him he's dreaming").
**Status:** EXECUTED

## DEC-003 — 2026-03-05 — Dual Track Strategy
**Decided by:** Joint
**Decision:** Run two tracks simultaneously:
- Track A: Perth AI Efficiency Audits (revenue track, target $100/mo by month 3)
- Track B: Rare Fruit Stock Tracker (moat track, long-term data play)
**Rationale:** Track A is fastest path to revenue. Track B has strongest moat and keeps
Benedict engaged (personal interest). Running both from day 1 because Track B needs
data accumulation time.
**Alternatives rejected:**
- Mining/FIFO monitoring — existing competitors (Projectory, TenderSearch) too entrenched
- Newsletter — slow time to first dollar, weak moat
- Website change monitoring — generic, no moat
- Technical documentation service — linear scaling, no leverage
**Status:** EXECUTED

## DEC-004 — 2026-03-05 — Track A Pricing Model
**Decided by:** Joint
**Decision:** Hybrid pricing for audit business:
- Assessment fee: $149-299 upfront
- Implementation retainer: $99-199/month (optional)
- Revenue share: selective, only for larger clients with measurable impact
**Rationale:** Pure revenue share has attribution problems and cash flow delay that would
burn our entire runway before first payment. Upfront fee ensures revenue from month 1.
Retainer creates recurring revenue. Revenue share is an upsell, not the base.
**Status:** APPROVED — exact price points to be finalised

## DEC-005 — 2026-03-05 — Target Verticals
**Decided by:** Joint
**Decision:** Target in order: (1) Retail, (2) Professional services, (3) Trades (carefully).
**Rationale:** Benedict can credibly walk into retail and professional services. Trades are
"an interesting bunch" (Benedict's words) — approach once we have case studies.
**Status:** APPROVED

## DEC-006 — 2026-03-05 — Public Transparency via Blog
**Decided by:** Joint
**Decision:** Publish public ledger as an Astro blog on Cloudflare Pages.
**Rationale:** Doubles as transparency commitment and marketing channel.
The "AI running a business" narrative is itself a customer acquisition tool.
**Status:** PENDING — needs domain and setup

## DEC-007 — 2026-03-05 — Track A Brand: walkthrough.au
**Decided by:** Benedict
**Decision:** Use walkthrough.au as Track A domain. Client-facing name: "Walkthrough."
Benedict referred to as "Ben" in all conversational/outreach contexts, "Benedict" in formal attributions.
**Rationale:** walkthrough.au is descriptive, memorable, and .au builds local trust.
**Status:** EXECUTED

## DEC-008 — 2026-03-05 — Track B: Start with Shopify Nurseries
**Decided by:** Dale
**Decision:** Begin nursery monitoring with the three Shopify-based nurseries first
(Ross Creek Tropicals, Ladybird Nursery, Fruitopia) using their public JSON APIs.
Daleys (custom PHP) is next priority due to its data richness.
**Rationale:** Shopify nurseries have a public `/products.json` endpoint — zero HTML
parsing needed, full price + stock data available. Gets data accumulating on day 1.
**Alternatives rejected:**
- Starting with all nurseries at once — too much custom work for session 1
- Starting with Daleys — higher value data but requires custom scraper
**Kill criteria:** If any nursery blocks our user agent, switch to less frequent polling.
**Status:** EXECUTED — first scrapes completed

## DEC-009 — 2026-03-05 — Drop "Exotica" from Nursery List
**Decided by:** Dale
**Decision:** Tell him he's dreaming. "Exotica Rare Fruits Nursery" is based in
Vista, California, USA — not an Australian nursery. Removed from monitoring list.
**Rationale:** Research confirmed it's at rarefruitsexotica.com, a US business.
**Status:** EXECUTED

## DEC-010 — 2026-03-05 — Track A Proposed Pricing: $199 Assessment
**Decided by:** Dale (proposed, pending Benedict approval)
**Decision:** Propose $199 for standard assessment, $149/month for implementation retainer.
**Rationale:** $199 is low enough to be an easy yes for a business owner, high enough
to not feel cheap. Landing page and deliverable template built around this price point.
Benedict to confirm (Q7).
**Status:** PROPOSED
