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
- [x] Build shareable digest web pages + price history (DEC-025)
- [x] Fix Daleys/Ecwid scraper data path bugs
- [x] Benedict shared treestock.com.au in 2 WA fruit FB groups (2026-03-12)
- [x] Build email sending for subscribers (DEC-034) — live, sends after each 6am scrape

### Infrastructure (Both Tracks)
- [x] Set up GitHub repo
- [x] Set up project directory structure and state files
- [x] Set up Cloudflare Pages for landing page
- [x] Set up email (hello@walkthrough.au via Fastmail)
- [x] Provision Hetzner VPS for scrapers
- [x] Install Caddy web server on Hetzner for dashboard
- [ ] Set up question dashboard (simple web page for Benedict Q&A)
- [ ] Set up Stripe (when first client is ready to pay)

### Autonomous Dale (DEC-027, DEC-028)
- [x] Benedict: Set up Resend API key on Hetzner (Q23) — done
- [x] Benedict: Install Claude Code CLI + auth on Hetzner (Q23) — done
- [x] Benedict: Set up git push access from Hetzner (Q23) — done (gh auth)
- [x] Build dale-runner.sh (cron wrapper) — deployed
- [x] Build budget-tracker.py (token usage tracking) — deployed
- [x] Build notify.py (Resend email notifications) — deployed, tested
- [x] Build session-prompt.py (autonomous session context builder) — deployed
- [x] Create config.json + TASK_QUEUE.md — deployed
- [x] Test pipeline manually, then enable cron — tested + cron live at 18:00 UTC
- [ ] Verify walkthrough.au domain in Resend (currently using mail.walkthrough.au subdomain)
- [ ] Monitor first 3 nightly runs for issues
- [ ] Graduate from 15-min to 20-min cap after 2 weeks if stable

### Blockers
- Waiting for Benedict to approach first prospect
- ~~Waiting for Benedict to share digest in WA fruit FB groups~~ DONE 2026-03-12
- ~~Waiting for Plausible API key on server~~ DONE (Q30, deployed + tested)

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

### Session 13 Completed (2026-03-12 UTC)
- State-based shipping filters (DEC-035):
  - Replaced WA-only checkbox with state dropdown (All/NSW/VIC/QLD/SA/WA/TAS/NT/ACT)
  - SHIPPING_MAP replaces WA_SHIPPING_OVERRIDES — ships_to state lists per nursery
  - Research confirmed: Ross Creek ships QLD/NSW/VIC/ACT; Fruit Salad Trees ships WA+TAS; Diggers ships all states
  - daily_digest.py: --state XX flag added; --wa-only kept as alias
  - Email signup copy updated: "Australian fruit tree collectors" (not WA-specific)
- Species pages launched (DEC-036):
  - fruit_species.json: 50-species taxonomy (common name, Latin name, synonyms, region, slug)
  - build_species_pages.py: auto-generates /species/[slug].html + /species/index.html
  - 50 pages live at treestock.com.au/species/ targeting "buy X tree online Australia" keywords
  - Added to daily cron in run-all-scrapers.sh
  - Dashboard footer links to /species/ index
- Hetzner backups: script ready (enable-hetzner-backups.sh), blocked on API token (Q27)
- FB post for Benedict ready at deliverables/fb-post-treestock.md
- All deployed, dashboard rebuilt

### Session 12 Completed (2026-03-11)
- Email digest sending fully wired up (DEC-034):
  - send_digest.py committed + deployed (was written but not committed)
  - subscribe_server.py updated: POST action=unsubscribe removes subscribers
  - /unsubscribe.html static page: clean two-step unsubscribe flow (no Caddy changes needed)
  - run-all-scrapers.sh now calls send_digest.py after each daily build
  - deploy.sh created: rsync repo → /opt/dale/scrapers + autonomous
  - dale-runner.sh: auto-deploys on each session start after git pull
- First email will go out at next 6am UTC scrape (currently test@test.com only)
- All changes committed + pushed to GitHub

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

### Session 21 Completed (2026-03-16 UTC, 18:00 UTC)
- Notion task: 4x cron verified already live (DEC-050). Marked Done.
- Built BigCommerce scraper for Heritage Fruit Trees (DEC-056):
  - heritagefruittrees.com.au — VIC-based, 300+ heritage/heirloom temperate fruit trees
  - Ships to WA in winter/dormant season (May-Sep)
  - Scraper: HTML parsing of category pages + individual product pages for price/stock
  - Added to daily pipeline, shipping.py, nursery profile pages
  - First scrape: 332 products (295 fruit trees + 17 nuts + 20 berries)
- Built nursery partnership page (/advertise.html):
  - Landing page for nurseries to understand the Featured Partner offering ($49/month)
  - Shows traffic stats (490 visitors/week), audience profile, package comparison
  - Added to sitemap. Dashboard footer now links to /advertise.html
  - Benedict: share this URL when approaching Primal Fruits about sponsorship
