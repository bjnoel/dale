# Decision Log

*Append-only. Never edit past entries — only add new ones.*

---

## DEC-050 — 2026-03-15 — 4x Nightly Cron Sessions (Benedict Notion Task)
**Decided by:** Dale (Benedict requested)
**Decision:** Updated crontab to run Dale 4 times per night: 18:00, 19:00, 20:00, 21:00 UTC (2am, 3am, 4am, 5am AWST).
**Rationale:** Benedict requested this via Notion to get more work done overnight. Each session
runs independently — the session prompt pulls fresh state each time, so sessions build on each other's commits.
**Change:** Replaced single `0 18 * * *` cron entry with 4 entries at 18, 19, 20, 21 UTC.
**Status:** LIVE

---

## DEC-049 — 2026-03-15 — ausforums.bjnoel.com Dead Link Cleanup (Benedict Notion Task)
**Decided by:** Dale (Benedict requested)
**Decision:** Fix dead links, URL typo, and add bjnoel.com footer to ausforums.bjnoel.com.
**What was done:**
- Cloned bjnoel/ausforums repo from GitHub
- Removed 12 dead/404 links: Alfa Romeo Forums, GMH-Torana, Prelude Australia, Pulsar Group,
  AE86 Driving Club, Oz Celica, CAD Forum, OzSportBikes, Yamaha IT, Bikes MoveUs, DTV Forum, Railpage
- Fixed Toyota Owners Club URL typo: `hhttps://` → `https://`
- Added footer: "A project by Benedict Noel · Contact" linking to bjnoel.com
- Fixed missing #outdoors option in navbar dropdown
- Pushed to GitHub — Netlify auto-deploys on push
**Status:** DEPLOYED — live at ausforums.bjnoel.com

---

## DEC-048 — 2026-03-15 — Add Fruit Tree Cottage to treestock.com.au (Benedict Notion Task)
**Decided by:** Dale (Benedict requested via Notion)
**Decision:** Add Fruit Tree Cottage (www.fruittreecottage.com.au) to the treestock.com.au scraper.
**Rationale:** Benedict assigned this via Notion. Fruit Tree Cottage is a Shopify-based nursery
on the Sunshine Coast QLD specialising in tropical/subtropical fruit trees. Confirmed it does NOT
ship to WA, NT, or TAS (as noted in the task).
**What was built:**
- Added to shopify_scraper.py NURSERIES dict (domain: www.fruittreecottage.com.au)
- Added to shipping.py SHIPPING_MAP: ["NSW", "VIC", "QLD", "SA", "ACT"]
- Added to shipping.py NURSERY_NAMES: "Fruit Tree Cottage"
- Added to build-dashboard.py FRUIT_FILTERS (mode: all — dedicated fruit nursery)
- First scrape: 185 products, 108 in stock (notable: Grumichama, Lychee x6 vars, Soursop, Guava x3, Fig x4, Persimmon/Black Sapote)
- Created build_nursery_pages.py (was missing from repo) — generates all /nursery/*.html + index
- Nursery profile page live: /nursery/fruit-tree-cottage.html
- Nursery index updated to 11 nurseries
- Sitemap updated: 70 URLs (was 54, now includes nursery pages + location pages)
- build_nursery_pages.py added to run-all-scrapers.sh pipeline (daily rebuild)
- build_nursery_pages.py added to run-all-scrapers-server.sh
- All files deployed to /opt/dale/scrapers/
**Status:** LIVE

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

## DEC-025 — 2026-03-09 — Shareable Digest Pages + Price History
**Decided by:** Dale
**Decision:** Build three new web features for the stock tracker:
1. **Shareable digest page** (`/digest.html`, `/digest-wa.html`) — proper web pages with
   navigation, OG meta tags, and styled layout. Replaces raw email HTML as the primary
   shareable link. Benedict can drop a URL into FB groups instead of walls of text.
2. **Price history timeline** (`/history.html`, `/history-wa.html`) — browsable daily
   change history across all nurseries. Expand/collapse each day, filter quiet days.
   Shows 1,450 total changes across 5 days of data — compelling proof of value.
3. **Dated digest archives** (`/archive/digest-YYYY-MM-DD.html`) — each day's digest
   preserved. Shows the service is active and ongoing.

Also fixed bugs: Daleys and Ecwid scrapers had hardcoded data paths that broke on
the server (used `DALE_DATA_DIR` env var like the other scrapers). Added nav links
(Today's Digest, History) to the main dashboard header.

**Files changed:** daily_digest.py (added `--page` flag, refactored HTML builders),
build_history.py (new), run-all-scrapers.sh (generates all new outputs),
build-dashboard.py (nav links), daleys_scraper.py (path fix), ecwid_scraper.py (path fix).

**Rationale:** The digest text was designed for copy-paste into FB groups but a shareable
URL is more versatile — it works in any context (FB, WhatsApp, email, forums). The price
history page builds the data moat and gives people a reason to return. Both features are
zero-cost to operate (static HTML served by existing Caddy).
**Status:** EXECUTED

## DEC-026 — 2026-03-09 — Variant-Level Price Tracking
**Decided by:** Dale
**Decision:** Refactor price/stock change detection from product-level to variant-level
comparison. Multi-variant products (e.g. Daleys trees with Small/Medium/Large pot sizes)
are now tracked as individual entries keyed by SKU (Daleys/Ecwid), variant ID (Shopify),
or variant title (fallback). Single-variant products unchanged.
**Rationale:** The old code keyed products by URL and compared `min_price` across all
variants. When a cheap variant went out of stock, the `min_price` shifted to a more
expensive variant, creating false "price increase" reports. Daleys alone had **162 false
price increases** in one day due to this. After the fix: only **3 real price changes**.
This was undermining trust in the data.
**Files changed:** daily_digest.py (load_snapshot, new _variant_key/_variant_display_title
helpers), availability_tracker.py, backfill_availability.py. build_history.py inherits
the fix automatically via imported functions.
**Impact:** Daleys products expanded from 676 to ~1,032 tracked entries (variants
flattened). Digest entries now show variant info: "Acerola (Large)" instead of "Acerola".
**Status:** EXECUTED — deployed to server, history + digest pages rebuilt

## DEC-027 — 2026-03-09 — Autonomous Dale (Cron-Based Self-Invocation)
**Decided by:** Joint
**Decision:** Build an autonomous execution system where Dale self-invokes via cron
on the Hetzner VPS, performs business tasks overnight, and emails Benedict a summary.
All spending requires email approval. Token usage is tracked and budgeted.
**Architecture:**
- `dale-runner.sh` cron wrapper runs at 2am AWST (18:00 UTC) nightly
- `claude -p` headless mode using Benedict's Max $100 subscription
- Token budget tracker ensures no contention with daytime interactive use
- Resend API for email notifications to b@bjnoel.com (dale@mail.walkthrough.au)
- Wise virtual card ($50 AUD/month cap) for any approved spending
- STOP file + circuit breakers for safety
- Approval flow: Dale proposes spending via email, Benedict approves/denies async
- Learning mode first 2 weeks: 15-minute session cap to establish baseline
**Benedict provides:** Resend API key, Claude Code auth on Hetzner, git deploy key.
**Hard safety limits:** Wise card cap ($50 AUD/mo), STOP file, circuit breakers,
spending approval flow, git-reversible changes only.
**Full plan:** docs/autonomous-dale-plan.md
**Status:** EXECUTED — pipeline tested, cron enabled 2026-03-09

## DEC-028 — 2026-03-09 — Autonomous Dale Build Complete
**Decided by:** Dale
**Decision:** Deployed the autonomous Dale pipeline to Hetzner. All components tested:
- `dale-runner.sh`: Pre-checks (STOP file, failure count, time window, git health), runs Claude, pushes commits, sends email
- `budget-tracker.py`: Token/cost/duration logging from Claude JSON output, failure tracking
- `notify.py`: Resend API emails (summary, alert, approval) from dale@mail.walkthrough.au
- `session-prompt.py`: Builds context from repo state files + scraper data + task queue
- `config.json`: 15-min cap, 50 max turns, learning mode
- `TASK_QUEUE.md`: Initial tasks (data analysis, taxonomy, nursery research)
**Test results:**
- Email: Working (had to add User-Agent header — Resend/Cloudflare blocks Python-urllib default)
- Claude CLI: Working (Sonnet 4.6, ~837k tokens in, ~12k out for full session)
- Budget logging: Working (tracks tokens, cost, duration, turns, stop reason)
- Git: Working (repo cloned via gh, credential helper configured, push tested)
- Full pipeline: Working (cron wrapper → prompt build → claude → log → email → git push)
**First real session:** Test session used 26 turns / 339s / $0.94 but hit max_turns before finishing.
Increased max_turns from 25 to 50. 15-min timeout is the real safety net.
**Status:** EXECUTED — cron live at 18:00 UTC

## DEC-029 — 2026-03-10 — Track B Domain: leafscan.com.au
**Decided by:** Joint
**Decision:** Register leafscan.com.au as the public-facing domain for the fruit tree
stock tracker (Track B). Replaces stock.scion.exchange as primary URL.
**Cost:** $9.95 AUD first year, $22.95/year after (VentraIP).
**Rationale:** stock.scion.exchange had multiple problems:
- Too long and hard to share verbally
- `.exchange` TLD reads as crypto/fintech to non-tech audience
- No Australian SEO signal (target audience is 100% Australian)
- `.com.au` is universally recognised as Australian
- "leafscan" is short, snappy, and descriptive enough
Considered and rejected: fruitstock, rarefruits, orchardprices, plantstock (taken),
plantwatch (taken), growlist (taken), treefinder (taken), various grow/leaf combos.
scion.exchange kept as redirect. stock.scion.exchange continues working as alias.
**Status:** EXECUTED — domain registered, DNS setup pending

## DEC-030 — 2026-03-10 — Autonomous Dale: Add --dangerously-skip-permissions
**Decided by:** Joint
**Decision:** Add `--dangerously-skip-permissions` flag to the `claude -p` invocation
in dale-runner.sh. Without this, Claude Code in headless mode cannot use tools that
require permissions (file editing, bash commands, etc.), making autonomous sessions
effectively non-functional.
**Status:** EXECUTED — runner script updated, pending deploy to server

## DEC-031 — 2026-03-10 — Revenue Experiment: Nursery Sponsored Listings
**Decided by:** Dale
**Decision:** Run first revenue experiment: pitch Primal Fruits (primalfruits.com.au)
on a $49/month sponsored listing on leafscan.com.au. Benedict knows Cyrus (owner)
personally — warm lead. Drafted pitch document at docs/pitch-primal-fruits-sponsorship.md
with WhatsApp message, email follow-up, and objection handling.
**Rationale:** Primal Fruits tracks as best first target:
- WA-based nursery (exact geographic match for audience)
- Benedict has a personal relationship with owner Cyrus
- They sell the most expensive/rare items we track ($250 Mamoncillo, $242 Alphonso Mango)
- $49/month = less than one tree = very low ask
- If yes: repeatable model, approach Daleys next
- If no: learn objections, iterate
**Technical preparation:**
- Updated leafscan.com.au branding across dashboard + digest (was still "scion.exchange")
- Added FEATURED_NURSERIES config to build-dashboard.py (activates yellow highlight + star badge)
- Ready to activate instantly when Cyrus says yes — just add "primal-fruits" to the set
**Expected conversion:** 30-50% (warm lead, low price, relevant product)
**Status:** EXECUTED — pitch ready, awaiting Benedict to send message to Cyrus

## DEC-032 — 2026-03-11 — Comprehensive leafscan.com.au Branding Fix
**Decided by:** Dale
**Decision:** Fix all remaining scion.exchange references across source files. DEC-031
claimed to update branding but only partially succeeded — the Python source files that
generate the dashboard, digest, and history pages still contained scion.exchange throughout.
**Files changed:** build-dashboard.py (x2, dashboard + scrapers copies), daily_digest.py,
build_history.py, subscribe_server.py, daleys_scraper.py, ecwid_scraper.py,
shopify_scraper.py, woocommerce_scraper.py (user-agent strings).
Also fixed `stock.scion.exchange` URLs → `leafscan.com.au` (no subdomain needed).
**Deployed:** All files synced to server, dashboard + digest + history pages rebuilt.
leafscan.com.au DNS confirmed pointing to 178.104.20.9, Caddy already configured.
**Status:** EXECUTED — superseded by DEC-033 (treestock.com.au) same day

## DEC-033 — 2026-03-11 — Track B Domain: treestock.com.au (replaces leafscan.com.au)
**Decided by:** Benedict
**Decision:** Rebrand Track B domain from leafscan.com.au to treestock.com.au.
Third domain iteration (scion.exchange → leafscan.com.au → treestock.com.au).
**Cost:** Benedict's personal expense, not counted towards ledger.
**Changes:**
- DNS: treestock.com.au A record → 178.104.20.9 (via Cloudflare API)
- Caddy: treestock.com.au serves dashboard, stock.scion.exchange + leafscan.com.au
  now 301 redirect to treestock.com.au
- All source files updated (build-dashboard.py x2, daily_digest.py, build_history.py,
  all 4 scrapers, subscribe_server.py, pitch doc, task queue)
- Dashboard + digest + history pages rebuilt and deployed
- Cloudflare zone ID for treestock: 87880cb83388c52cf86b0a7037845cb3
**Status:** EXECUTED

## DEC-034 — 2026-03-11 — Email Digest Sending Live (Track B)
**Decided by:** Dale
**Decision:** Complete and deploy the email digest sending pipeline for treestock.com.au.
send_digest.py was already written but not committed or tested. Built out the complete
system and resolved the unsubscribe routing problem without needing Caddy changes.

**What was built/fixed:**
- send_digest.py: reads pre-generated digest-wa-email.html, sends via Resend to all
  wa_only subscribers. Idempotent (digest_sends.json tracks sends). --dry-run and
  --test EMAIL flags for safe operation. Tested successfully.
- subscribe_server.py: added POST action=unsubscribe handler so browser form POSTs
  from unsubscribe.html can remove subscribers (validates HMAC token).
- /opt/dale/dashboard/unsubscribe.html: static page served by Caddy. JavaScript reads
  email+token from URL params, pre-fills hidden form fields, user clicks confirm.
  Form POSTs to /api/subscribe (already Caddy-proxied) with action=unsubscribe.
  This avoids needing a new /api/unsubscribe Caddy route.
- run-all-scrapers.sh: calls send_digest.py after daily build (non-fatal).
- deploy.sh: rsync from repo → /opt/dale/scrapers + /opt/dale/autonomous.
- dale-runner.sh: calls deploy.sh after git pull so code deploys automatically.

**Status:** EXECUTED — all committed, pushed, deployed. First email will send tonight
after the 6am UTC scrape cron (currently only test@test.com subscribed).

## DEC-035 — 2026-03-12 — State-Based Shipping Filters (replaces WA-only)
**Decided by:** Dale
**Decision:** Replace the WA-only shipping checkbox on treestock.com.au with a
state dropdown (All states / NSW / VIC / QLD / SA / WA / TAS / NT / ACT).
**Rationale:** Benedict is posting to WA FB groups but the site should be useful
for ALL Australian fruit collectors. A state dropdown lets anyone filter to nurseries
that ship to them. Research confirmed Ross Creek ships to QLD/NSW/VIC/ACT only;
Diggers ships nationally; Fruit Salad Trees ships to WA+TAS on 1st Tuesday/month.
**Changes:**
- build-dashboard.py: SHIPPING_MAP replaces WA_SHIPPING_OVERRIDES. Per-nursery
  `ships_to` state list added to nursery data. State dropdown in JS filters products
  by nursery. Email signup copy updated to "Australian fruit tree collectors".
- daily_digest.py: SHIPPING_MAP + WA_NURSERIES computed set. nursery_ships_to()
  helper. --state XX flag added; --wa-only kept as alias for --state WA.
- build_history.py: No changes (WA_NURSERIES still exported from daily_digest).
**Shipping data (March 2026):**
- Daleys (NSW): NSW, VIC, QLD, SA, WA, ACT (WA: seasonal window + extra fee)
- Ross Creek (QLD): NSW, VIC, QLD, ACT only (confirmed from website)
- Ladybird (QLD): NSW, VIC, QLD, ACT (estimated, similar to Ross Creek)
- Fruitopia (QLD): NSW, VIC, QLD, SA, ACT (estimated)
- Primal Fruits (WA): WA only (local)
- Guildford (WA): WA only (local)
- Fruit Salad Trees (NSW): NSW, VIC, QLD, SA, WA, TAS, ACT (WA+TAS 1st Tue/month — confirmed)
- Diggers (VIC): All states including NT (confirmed — ships nationwide)
**Status:** EXECUTED — deployed to server, dashboard rebuilt

## DEC-036 — 2026-03-12 — Programmatic SEO: Species Pages
**Decided by:** Dale
**Decision:** Build auto-generated species pages at /species/[slug].html showing
all varieties, prices, nurseries, and shipping for each fruit species.
**Rationale:** Highest long-term growth lever for treestock.com.au. Target keywords:
"buy [species] tree online Australia", "[species] tree price Australia". No competitor
aggregates this data across nurseries — the data IS the content. 50 species × 8
nurseries = 400 unique price comparison data points per day.
**What was built:**
- fruit_species.json: 50-species taxonomy with common names, Latin names, synonyms,
  region, and slug. Covers all major commercially available fruit species in Australia.
- build_species_pages.py: Reads latest nursery data, matches products to species using
  title-based lookup, generates /species/[slug].html per species + /species/index.html.
  Each page: Latin name, in-stock count, price range, nursery availability table,
  full variety listing with prices + shipping badges.
- run-all-scrapers.sh: Species page build added after history page (non-fatal).
- Dashboard footer: Added "Browse by species" link.
**Initial results:** 50 pages generated. Top species: Mango, Avocado, Fig, Lychee,
Apple. All include price range, nursery breakdown, WA shipping badges.
**Status:** EXECUTED — 50 pages live at treestock.com.au/species/

## DEC-037 — 2026-03-12 — Hetzner Backups: Deferred (token not available)
**Decided by:** Dale
**Decision:** Enable Hetzner backups is approved and desired (~€0.76/month) but
/opt/dale/secrets/hetzner.env doesn't exist — the API token hasn't been provisioned.
**Action:** Created enable-hetzner-backups.sh ready to run once token is added.
**Status:** BLOCKED — see Q26 for Benedict

## DEC-038 — 2026-03-12 — Plausible Analytics Integration for Autonomous Dale
**Decided by:** Dale + Benedict
**Decision:** Add Plausible API integration so autonomous Dale can monitor traffic
and include analytics in nightly session summaries.
**Reasoning:** Benedict posted treestock.com.au to 2 FB groups on 2026-03-12. Need
to track impact: traffic, referrers, page popularity, and subscriber conversions.
Self-hosted Plausible at data.bjnoel.com already tracks all pages. API access is
read-only and low-risk.
**Action:** Built plausible_stats.py (queries aggregate, breakdown, realtime endpoints).
Integrated into session-prompt.py so autonomous Dale sees traffic data each night.
**Status:** Script ready. Waiting for Benedict to provision API key (Q30).

## DEC-039 — 2026-03-13 — Dashboard Species Grid + Sitemap
**Decided by:** Dale
**Decision:** Add species browsing grid to main dashboard and generate sitemap.xml daily.
**Rationale:** FB post drove 268 visitors on day 1, mostly landing on homepage. Adding the
species grid makes the site immediately more useful (users can browse by type not just search).
Sitemap enables Google to index all 50+ species pages — currently invisible to search engines.
**What was built:**
- build-dashboard.py: species slug stored per product ("sl" field). After main product loop,
  aggregates top 16 species by in-stock count with price data. Passed to build_html() as
  top_species. Dashboard shows species grid between nursery summary and results, hidden during search.
- build_sitemap.py: generates sitemap.xml covering /, digest.html, history.html, species/index,
  and one entry per species slug.html (54 URLs total). Runs daily after species page build.
- run-all-scrapers.sh: sitemap build added as final step (non-fatal).
**FB launch results (day 1):** 268 visitors, 211 from Facebook, 2 subscribers (1 real: hellojojo@myyahoo.com).
87% bounce rate is high but expected for a quick-check tool. Avg 60s on site = people did engage.
**Status:** EXECUTED — sitemap and dashboard live

## DEC-040 — 2026-03-13 — Species Restock Alerts ("Notify Me")
**Decided by:** Dale
**Decision:** Build per-species restock alert system. Users enter email on any species page
and get emailed when that species comes back in stock across any monitored nursery.
**Rationale:** This is the clearest monetisation path visible from current data. The email
subscription list is growing (2 real subscribers after day 1 of FB launch). A species alert
feature gives people a reason to subscribe who wouldn't subscribe for a daily digest. It's
also directly useful — if you're hunting sapodilla, you want to know the moment one appears.
Future: premium tier for rare species (sapodilla, annonas) once we have enough alert signups
to prove demand.
**What was built:**
- subscribe_server.py: New `action=watch` handler in POST /subscribe. Accepts
  {email, action: "watch", species: "slug"}. Creates subscriber if new, adds species to
  watch_species list. Returns 201 "Alert set!" or 200 "Already watching".
- build_species_pages.py: Each species page now has a "Notify me" form. Shows amber
  warning if in_stock_count == 0 ("out of stock, notify me when back"). Shows green
  "get restock alerts" form otherwise. Posts to /api/subscribe with action=watch.
- send_species_alerts.py: New script. Runs after each daily scrape. Compares today's
  in-stock counts vs yesterday's for each watched species. If a species goes 0→>0,
  sends targeted email to all watchers. Idempotent (tracks sends in species_alert_sends.json).
- run-all-scrapers.sh: send_species_alerts.py added as final step (non-fatal).
**Deployment note:** subscribe_server.py needs a service restart to pick up the watch
endpoint (needs Benedict: Q32).
**Status:** EXECUTED — deployed, species pages rebuilt. Service restart pending.

## DEC-041 — 2026-03-13 — Nursery Profile Pages
**Decided by:** Dale
**Decision:** Build /nursery/[slug].html profile pages for all 10 monitored nurseries.
**Rationale:** Low-effort SEO pages targeting "daleys fruit trees review", "ross creek tropicals stock", etc. Each nursery page shows: blurb, location, shipping states, species they carry, in-stock count, sample products, and link to filtered dashboard view. All data is already available — this is just presenting it differently for search engines. 10 pages × potential search traffic = worth building.
**What was built:**
- build_nursery_pages.py: Generates /nursery/[slug].html per nursery + /nursery/index.html.
  Each page: full blurb, WA shipping badge, stat cards (in-stock/total/species/WA-ships),
  species table with in-stock counts, in-stock product table with prices, link to dashboard.
- NURSERY_META: Rich metadata for all 10 nurseries (location, blurb, specialties, WA notes).
- build-dashboard.py: Added "Nurseries" link to footer nav. Added ?nursery= URL param support
  so nursery pages can deep-link into filtered dashboard view.
- build_sitemap.py: Now includes /nursery/ index + all 10 nursery pages (65 total URLs, was 54).
- run-all-scrapers.sh: Nursery page build added before sitemap step (non-fatal).
**Results:** 10 nursery profile pages + index generated. Sitemap updated to 65 URLs.
**Status:** EXECUTED — live at treestock.com.au/nursery/

## DEC-042 — 2026-03-13 — Uptime Monitoring (Self-hosted, Cron-based)
**Decided by:** Dale
**Decision:** Build lightweight uptime monitor instead of running Uptime Kuma in Docker.
**Rationale:** Server has 1.6GB available RAM but Plausible already uses ~3 containers.
A Python cron script costs zero overhead vs Docker service. Resend is already integrated.
Uptime Kuma is overkill for monitoring 3 endpoints with 1 recipient.
**What was built:**
- autonomous/uptime_monitor.py: checks treestock.com.au, walkthrough.au, Subscribe API
  every 5 minutes via cron. State tracked in /opt/dale/data/uptime_state.json.
  Alerts once on first confirmed down, sends recovery email when back up.
- Added to crontab: `*/5 * * * * /usr/bin/python3 /opt/dale/autonomous/uptime_monitor.py`
**Results:** Tested — all 3 sites currently UP.
**Status:** EXECUTED — live

## DEC-043 — 2026-03-13 — Tass1 Trees Cold Outreach (Track A+B Crossover)
**Decided by:** Dale
**Decision:** Target Tass1 Trees (Middle Swan, WA) as first cold outreach prospect for Track A.
**Rationale:** Identified during nursery research. Two HIGH-severity issues found:
1. No HTTPS — every customer sees "Not Secure" browser warning
2. No mobile viewport — site broken on phones, critical since most traffic is Facebook/mobile
Additional issues: no online shop, no social links despite 7,000 Facebook followers.
This is also a Track A+B crossover — WA-based specialist fruit nursery that should be on
treestock.com.au. Benedict knows the WA fruit community, creating natural warm intro.
**Deliverable:** deliverables/tass1-trees-cold-outreach.md — full brief + cold email ready to send.
**Email to:** joe@tass1trees.com.au
**Next action:** Benedict to send email from hello@walkthrough.au.
**Status:** READY — awaiting Benedict to send

---

## DEC-044 — 2026-03-14 — Tass1 Trees: Not Trackable for treestock.com.au
**Decided by:** Dale
**Decision:** Do NOT build a Tass1 Trees scraper. Add to "researched, not trackable" list.
**Rationale:** Investigated tass1trees.com.au thoroughly. Site has no prices, no stock status,
no online shop — it's a static HTML catalog of variety names only (e.g., "GRAPEFRUIT; Marsh-seedless,
Thompson pink, Star-Ruby"). There is nothing to scrape or track. This is actually a selling
point for the Track A cold outreach — they have no ecommerce at all, which is one of the problems
we'd help them solve.
**Result:** No scraper built. tass1trees.com.au noted as "researched, not trackable" in business state.
The Track A cold outreach value (DEC-043) is unaffected — in fact reinforced.
**Status:** LOGGED

---

## DEC-045 — 2026-03-14 — Weekly Data Backup
**Decided by:** Dale
**Decision:** Set up weekly local backup of /opt/dale/data/ to /opt/dale/backups/.
**Rationale:** 9 days of price/stock history accumulated. This data is the core moat for Track B —
losing it would be painful. A simple weekly tar backup costs nothing and protects against accidental
deletion or disk corruption. 4-week rolling window keeps ~28 days of recovery points.
**What was built:**
- autonomous/weekly_backup.sh: creates data-YYYY-WW.tar.gz weekly, prunes to last 4 backups.
- Crontab: `0 2 * * 0 /opt/dale/autonomous/weekly_backup.sh` (Sundays 02:00 UTC = 10:00 AWST)
- First backup created: data-2026-W11.tar.gz (6.8MB)
**Status:** LIVE

---

## DEC-046 — 2026-03-14 — Location SEO Pages
**Decided by:** Dale
**Decision:** Build state-based location pages (/buy-fruit-trees-wa.html etc.) for SEO.
**Rationale:** Google is driving only 10 visitors/week despite good content. Location-based queries
("buy fruit trees online wa", "fruit trees that ship to western australia") are high-intent searches
with no existing aggregator page. We have the data to answer these queries perfectly — 1,060 in-stock
products at 6 WA-shipping nurseries. Four pages (WA, QLD, NSW, VIC) each target a specific state's
buyers with live stock data, nursery summaries, subscribe form, and cross-links.
**What was built:**
- build_location_pages.py: generates 4 pages with nursery summary, in-stock products (capped 60),
  WA-specific notes (quarantine info, shipping schedules), subscribe form.
- Pages: /buy-fruit-trees-wa.html (1060 in-stock), /buy-fruit-trees-qld.html (3251),
  /buy-fruit-trees-nsw.html (3251), /buy-fruit-trees-vic.html (3251)
- run-all-scrapers.sh: location page build added before sitemap step (non-fatal)
- build_sitemap.py: 4 location pages added to STATIC_PAGES + nursery sub-pages now scanned dynamically
- Sitemap: 69 URLs (was 65)
**Status:** LIVE — deployed to /opt/dale/dashboard/

---

## DEC-047 — 2026-03-14 — ausforums.bjnoel.com Audit (Benedict Notion Task)
**Decided by:** Dale (Benedict requested)
**Decision:** Audited ausforums.bjnoel.com for link validity and hosting suitability.
**Findings:**
- Site is live on Netlify + Cloudflare (ausforums.bjnoel.com), static HTML directory of 150+ Australian forums
- ~12-13 confirmed dead links (no connection): Yamaha IT, Pulsar Group, OzSportBikes, Bikes Move Us,
  GMH-Torana, Oz Celica, Alfa Romeo Forums, Railpage, AE86 Driving Club, Prelude Australia
- 2 additional 404s: CAD Forum (caddit.net), DTV Forum (dtvforum.info)
- 1 URL typo: Toyota Owners Club has "hhttps://" prefix
- Majority of remaining links appear live
- Hosting recommendation: keep ausforums.bjnoel.com subdomain on Netlify — setup is solid (HTTPS, CDN, free)
**Deliverable:** deliverables/ausforums-audit-2026-03-14.md — full link-by-link breakdown
**Action for Benedict:** Remove dead links, fix Toyota URL typo
**Status:** REPORTED — awaiting Benedict to update the site
