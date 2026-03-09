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
**Status:** APPROVED — Benedict delegated pricing decision to Dale

## DEC-011 — 2026-03-05 — Track A Pricing: $199 Confirmed
**Decided by:** Dale (delegated authority from Benedict)
**Decision:** Lock in $199 for standard assessment. $149/month for implementation retainer.
**Rationale:** Benedict said "you decide." $199 is the right number because:
- $149 risks looking cheap, especially for trades and professional services
- $199 is still an impulse-level spend for a business owner
- If first prospects balk, we can always drop to $149 — easier to lower than raise
- Landing page already shows $199
**Kill criteria:** If first 3 prospects all say too expensive, drop to $149.
**Status:** EXECUTED

## DEC-012 — 2026-03-05 — Track B: Build Separate from scion-app
**Decided by:** Joint
**Decision:** Build Track B stock dashboard as a new web app, not in the existing
React Native scion-app. Can use scion.exchange domain or subdomain.
**Rationale:** Benedict not keen on the React Native stack. A simple web dashboard
is faster to build, easier to share in FB groups, and doesn't require app installation.
Existing app stays as-is.
**Status:** APPROVED

## DEC-013 — 2026-03-05 — First Audit Targets
**Decided by:** Joint
**Decision:** Three warm prospects for first audits:
1. PBR Plumbing (West Leederville) — Benedict knows the plumber
2. Wembley Cycles — Benedict did previous SEO audit
3. Gather Ceramics — Benedict helped them before
**Rationale:** Warm leads reduce friction. Mix of trades + retail gives us diverse
portfolio pieces. Wembley Cycles is interesting because Benedict has history there.
**Next step:** Dale runs automated analysis on all three, Benedict approaches with results.
**Status:** EXECUTED — prospect briefs created (deliverables/prospect-briefs/)

## DEC-014 — 2026-03-05 — Add Primal Fruits to Nursery Monitoring
**Decided by:** Dale
**Decision:** Build an Ecwid scraper for Primal Fruits Perth (primalfruits.com.au) and add
them to daily monitoring on the Hetzner server.
**Rationale:** Primal Fruits is a Perth-based nursery (Parkwood, WA) that ships to WA —
making it uniquely valuable in our dataset since most nurseries can't ship to WA due to
quarantine restrictions. Benedict knows the owner (Cyrus). They have 139 products including
high-value rare varieties (sapodilla at $72.75, pulasan at $99, alphonso mango at $242.50).
Uses Ecwid e-commerce with JSON-LD structured data on product pages.
**Status:** EXECUTED — scraper built (ecwid_scraper.py), deployed to server, first scrape running

## DEC-015 — 2026-03-05 — Approach Sequence for First Clients
**Decided by:** Dale (recommendation for Benedict)
**Decision:** Recommended approach order:
1. Wembley Cycles first (strongest existing relationship, clearest opportunity)
2. PBR Plumbing second (warm lead, different vertical for portfolio diversity)
3. Gather Ceramics third or packaged with Wembley (possible family connection — Felicity)
**Rationale:** Wembley Cycles has the most actionable findings (no online service booking,
workshop quality reviews, Lightspeed integration gap). PBR Plumbing has a strong strata
portal angle. Gather Ceramics may be too small for a paid engagement — better as a portfolio
piece or package deal. The Wembley-Gather connection (Felicity appears connected to both)
means sequencing matters.
**Status:** APPROVED — Benedict confirmed approach order

## DEC-016 — 2026-03-05 — First Three Audits as Free Portfolio Pieces
**Decided by:** Joint
**Decision:** All three warm prospects (Wembley Cycles, PBR Plumbing, Gather Ceramics)
will be done as free portfolio pieces, not paid engagements.
**Rationale:** All three are friends of Benedict. Charging $199 each ($597 total) is
awkward and risks the relationships for minimal revenue. The real value is:
1. Three diverse case studies (bike shop, commercial plumber, solo ceramicist) for
   walkthrough.au — worth far more than $597 in credibility with strangers
2. Honest feedback on the process from people who'll tell Benedict the truth
3. Word-of-mouth referrals: friends telling other Perth businesses "Ben did this and
   it was actually useful" is the best marketing we can get
**Trade:** Free assessment in exchange for (a) honest feedback, (b) permission to use
as a case study on walkthrough.au, (c) referral if they find it useful.
**Retainer opportunity:** If any of them want ongoing implementation help ($149/mo),
that's genuine recurring revenue earned on merit, not friendship.
**Status:** APPROVED

## DEC-017 — 2026-03-05 — Stock Dashboard: Static HTML on Hetzner
**Decided by:** Dale
**Decision:** Build Track B stock dashboard as a static HTML file generated after
each daily scrape, served via Caddy on the Hetzner VPS (178.104.20.9).
**Rationale:** Simplest possible architecture — no JS framework, no build pipeline,
no running server process. Python script reads nursery JSON, outputs single HTML
with embedded data and client-side search. Caddy serves static files with zero config.
**Alternatives rejected:**
- Astro site on CF Pages — needs Node.js build, deploy pipeline, complexity
- API server + SPA — over-engineered for a daily-updating dataset
- React Native app (existing scion-app) — Benedict didn't want that stack
**Status:** EXECUTED — live at http://178.104.20.9/

## DEC-018 — 2026-03-05 — WA Shipping Research
**Decided by:** Dale
**Decision:** Verified WA shipping status for all 5 monitored nurseries:
- Daleys: YES (seasonal windows, extra $25+ quarantine fee)
- Primal Fruits: YES (WA-based)
- Ross Creek: NO (ships QLD/NSW/ACT/VIC only)
- Ladybird: NO (ships QLD/NSW/VIC/ACT only)
- Fruitopia: NO (likely, no WA mention in policy)
**Rationale:** WA shipping is a key value prop — most nurseries can't/won't ship to WA
due to quarantine. Accurate tagging matters for user trust.
**Status:** EXECUTED — dashboard updated with correct WA shipping data

## DEC-019 — 2026-03-05 — Defer Heaven on Earth & Heritage Fruit Trees
**Decided by:** Dale
**Decision:** Defer adding these two nurseries to monitoring.
- Heaven on Earth (Wix, FNQ): Doesn't ship to WA, Wix is hard to scrape
- Heritage Fruit Trees (BigCommerce, VIC): 541 products, bare-root seasonal
  (March-Aug only). Worth adding later but needs custom BigCommerce scraper.
**Rationale:** Five nurseries with ~9,000 products is a solid MVP. Adding more
nurseries is incremental value vs. getting the dashboard in front of users.
**Kill criteria:** If community feedback says "you're missing X nursery", add it.
**Status:** DEFERRED

## DEC-020 — 2026-03-05 — Add Fruit Salad Trees & Diggers Club
**Decided by:** Dale
**Decision:** Add two new WA-shipping Shopify nurseries to monitoring:
- Fruit Salad Trees (fruitsaladtrees.com): 88 products, all multi-graft fruit trees.
  Ships to WA on 1st Tuesday of each month. Based in Emmaville, NSW.
- The Diggers Club (diggers.com.au): 113 fruit/nut products (filtered from 1,799
  total using "All fruit & nuts" + "all berries" + "fruit trees" + "nuts" tags).
  Ships to WA weekly. Based in Dromana, VIC.
**Rationale:** Both ship to WA (our key differentiator). Both are Shopify so
existing scraper works with zero new code. Diggers is a well-known Australian
gardening institution — adds credibility. Fruit Salad Trees is unique (multi-graft
trees not available elsewhere).
**Also researched but deferred:**
- Garden Express (WooCommerce): Mostly bulbs/flowers, minimal fruit content
- Fernview Nurseries: Website unreachable
- Rare Plants Australia: Website unreachable
**Status:** EXECUTED — both scraping on server, dashboard updated

## DEC-021 — 2026-03-05 — Price History Infrastructure
**Decided by:** Dale
**Decision:** Build price/stock change detection into the dashboard builder.
Compares today's snapshot with the previous day's to show: price drops (green),
price increases (red), new products, back-in-stock alerts, and just-sold-out items.
Added "Changes only" filter checkbox.
**Rationale:** Benedict requested price history in Q14. With only 1 day of data,
no changes visible yet, but infrastructure is ready. Tomorrow's cron run will
produce the first comparison. This is the foundation for future email alerts.
**Status:** EXECUTED — will show changes starting with second daily scrape

## DEC-022 — 2026-03-05 — Taxonomy Expansion (137 → 164 species)
**Decided by:** Dale
**Decision:** Added 27 new species to fruit_species.json including: achacha,
tangelo, chinotto, quandong, walnut, bunya nut, hazelnut, pecan, pistachio,
chestnut, elderberry, boysenberry, loganberry, jostaberry, dragonfruit (as
separate entry), Japanese raisin, Chinese bayberry, cacao, cardamom, and more.
Also fixed nursery summary counts to show filtered (fruit-only) numbers.
**Rationale:** Taxonomy matching improved from 66% to 68%. Remaining 32%
unmatched are mostly the long tail of ornamental varieties from nurseries with
mixed stock. Diminishing returns — better to focus on adding nurseries and
getting the dashboard shared.
**Status:** EXECUTED

## DEC-023 — 2026-03-09 — Daily Digest for Community Sharing
**Decided by:** Dale
**Decision:** Build a daily digest script (daily_digest.py) that compares consecutive
snapshots and generates human-readable summaries of stock changes. Outputs plain text
(for FB groups) and HTML (for email). Includes --wa-only flag for WA-focused content.
Integrated into daily cron — generates digest.txt, digest-wa.txt, digest.html in
dashboard directory after each scrape.
**Rationale:** The dashboard has real data now (price drops, back-in-stock alerts) but
nobody outside us knows about it. Benedict needs copy-pasteable content to share in WA
fruit FB groups. The digest is the vehicle for community awareness.
**Status:** EXECUTED

## DEC-024 — 2026-03-09 — Email Subscriber Collection
**Decided by:** Dale
**Decision:** Add email signup form to dashboard + minimal subscriber API (subscribe_server.py
running as systemd service on port 8099, Caddy reverse-proxying /api/subscribe).
Subscribers stored in /opt/dale/data/subscribers.json.
**Rationale:** Email alerts are the path to recurring engagement. Collecting addresses now
means we can start sending digests as soon as we have a sending mechanism. Building the
simplest possible thing — no email sending yet, just collection.
**Next:** Need SMTP credentials or a sending service to actually send alerts. Will propose
when we have subscribers.
**Status:** EXECUTED
