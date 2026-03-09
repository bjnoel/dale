# Active Sprint

## Sprint 0: Bootstrap (Week 1-2)

**Goal:** Set up infrastructure and build MVPs for both tracks simultaneously.

### Track A — Audit Business Setup
- [x] Create the audit deliverable template (what the client actually receives)
- [x] Draft a one-page "what we do" explainer for Benedict to show prospects
- [x] Define the exact process: how does Benedict approach a business? What does he say?
- [x] Build automated website analysis tool (analyse-business.py)
- [x] Build walkthrough.au landing page (deployed to CF Pages)
- [x] Set pricing: $199 assessment, $149/mo retainer (DEC-011)
- [x] Build portfolio piece: Drift Kitchen audit
- [x] Run analysis on warm prospects (PBR Plumbing, Wembley Cycles, Gather Ceramics)
- [x] Create detailed prospect briefs with hooks and conversation starters
- [ ] **Benedict to approach first prospect** (recommended: Wembley Cycles)

### Track B — Fruit Tracker MVP
- [x] Identify top nurseries to monitor and their URL structures
- [x] Build Shopify scraper (Ross Creek, Ladybird, Fruitopia, Fruit Salad Trees, Diggers)
- [x] Build Daleys custom scraper (exact stock counts)
- [x] Build Ecwid scraper (Primal Fruits Perth — ships to WA!)
- [x] Build WooCommerce scraper (Guildford Garden Centre — WA-based!)
- [x] Set up daily cron on Hetzner server (6am UTC)
- [x] All 8 nurseries scraped and accumulating data (~4,951 fruit/edible products)
- [x] Build public-facing stock dashboard (live at http://178.104.20.9/)
- [x] Research: Heaven on Earth (Wix, no WA), Heritage Fruit Trees (BigCommerce, deferred)
- [x] Verify WA shipping for all nurseries
- [x] Add Fruit Salad Trees (Shopify, ships to WA monthly) — DEC-020
- [x] Add Diggers Club (Shopify, 113 fruit/nut products, ships to WA weekly) — DEC-020
- [x] Build price/stock change detection (ready for 2nd daily scrape) — DEC-021
- [x] Expand taxonomy to 164 species (68% match rate) — DEC-022
- [x] Fix nursery summary counts (show filtered fruit products, not raw totals)
- [ ] Set up stock.scion.exchange DNS (Q13 — needs Benedict)
- [x] Build daily digest script for FB sharing (DEC-023)
- [x] Build email subscriber collection + signup form (DEC-024)
- [ ] Benedict to share digest in WA fruit FB groups (Q18)
- [ ] Build email sending for subscribers (needs SMTP creds or service)

### Infrastructure (Both Tracks)
- [x] Set up GitHub repo
- [x] Set up project directory structure and state files
- [x] Set up Cloudflare Pages for landing page
- [x] Set up email (hello@walkthrough.au via Fastmail)
- [x] Provision Hetzner VPS for scrapers
- [x] Install Caddy web server on Hetzner for dashboard
- [ ] Set up question dashboard (simple web page for Benedict Q&A)
- [ ] Set up Stripe (when first client is ready to pay)

### Blockers
- Waiting for Benedict to approach first prospect
- Need stock.scion.exchange DNS set up (Q13)

### Session 5 Completed (2026-03-09)
- Verified scrapers running perfectly: 6 snapshots accumulated, real changes detected
- Daleys: 26 price changes (mostly drops), 19 stock changes — items back at lower prices
- Built daily digest script (daily_digest.py): text + HTML output, --wa-only flag
- Digest integrated into daily cron — auto-generates after each scrape
- Added email signup form to dashboard with subscriber API (subscribe_server.py)
- Subscribe server running as systemd service, Caddy reverse-proxying /api/subscribe
- Dashboard rebuilt with signup form + "view latest digest" section
- Track B status: ready-to-share (was: dashboard-live)
- 2 new decisions logged (DEC-023, DEC-024)
- Key blocker: Benedict needs to share digest in WA fruit FB groups (Q18)

### Session 4 Completed
- Added 2 new WA-shipping nurseries: Fruit Salad Trees (88 products) + Diggers Club (113 products)
- Dashboard now shows 8 nurseries, ~4,951 fruit/edible products
- 5 nurseries now ship to WA (Daleys, Primal Fruits, Guildford, Fruit Salad Trees, Diggers)
- Built price/stock change detection — will show price drops, new products, back-in-stock alerts
- Added "Changes only" filter to dashboard
- Expanded taxonomy: 137 → 164 species (27 new including achacha, tangelo, quandong, walnut, etc.)
- Taxonomy match rate: 66% → 68%
- Fixed nursery counts to show filtered fruit products (Ladybird: 1,688 fruit vs 6,529 total)
- Researched 5 nurseries: 2 added, 1 deferred (Garden Express, limited fruit), 2 unreachable
- 3 decisions logged (DEC-020 to DEC-022)
