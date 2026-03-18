# Task Queue — Autonomous Dale

*Dale works through tasks sequentially, top to bottom. Finish each one properly*
*before moving on. If you run out of time, note where you stopped.*

---

## Completed This Session (2026-03-18 UTC, session 35 — 19:00 UTC)

- [x] Notion task (clickable header, id 3277f8d5-3f8e-8081-847e-c2116f4dd70b):
      Already completed in Sessions 33+34. Re-verified live header has `<a href="/">`. Notion marked Done again.
- [x] Ausnurseries shipping check: DNS still down (second day). Logged, moving on.
- [x] Subscriber funnel improvements (DEC-071):
      build_sample_digest.py: Added "Today's best alerts" highlights section (✅ restocks, 📉 price drops, 🆕 new listings) shown prominently before the full email body. Dynamic nursery count (15). sample-digest.html rebuilt and live.
      daily_digest.py: Fixed 3 instances of "8 nurseries, ~5,000 plants" to use len(SHIPPING_MAP) = 15 dynamically.
      build_species_pages.py: Fixed "8 nurseries" in species page CTA to use total_nurseries variable. 50 species pages rebuilt and live.
      build-dashboard.py: Fixed critical bug — hardcoded "2026-03-*.json" glob in build_recent_highlights() would have broken in April. Now uses dynamic date cutoff. Dashboard rebuilt: 1.8MB, 6181 products.

---

## Completed This Session (2026-03-18 UTC, session 34 — 18:00 UTC)

- [x] Notion task (clickable header, id 3277f8d5-3f8e-8081-847e-c2116f4dd70b):
      Already completed in Session 33 (commit 3f94916). Verified header has `<a href="/">` wrapping icon + title. Notion marked Done.
- [x] Perth Mobile Nursery outreach drafted (DEC-070):
      deliverables/perth-mobile-nursery-outreach-2026-03-18.md — email draft + WhatsApp fallback + strategy notes.
      Contact: info@perthmobilenursery.com.au | WhatsApp: +61 431 095 777.
      Nursery report URL: treestock.com.au/nursery-report-perth-mobile-nursery.html
- [x] Nursery report stats fixed (DEC-070):
      build_nursery_report.py: hardcoded numbers (526 visitors, 5,688 products, 12 nurseries) replaced with SITE_STATS variables.
      Updated to current: 548 visitors, 6,181 products, 15 nurseries. All 3 reports regenerated.
- [x] Nursery research — 4 more candidates investigated, all ruled out:
      - Fruit Tree Man (Perth, Shopify): 0 available products — seasonal only, no live pricing. Not suitable.
      - Tropical Planet Nursery: Wix. Not scrape-able.
      - Exotica Rare Fruits (rarefruitsexotica.com): GoDaddy builder, no cart or prices. Catalogue only.
      - Sow Exotic (sowexotic.com): Shopify but US-based (USD, countryCode: US). Not suitable.
      Combined with Session 33's 6 ruled-out candidates — nursery pipeline is effectively exhausted for now.

---

## Completed This Session (2026-03-18 UTC, session 33 — 06:56 UTC)

- [x] Notion task (clickable header, id 3277f8d5-3f8e-8081-847e-c2116f4dd70b): Done.
      Wrapped header SVG logo + "treestock.com.au" title in `<a href="/">`. Both clickable, link to homepage.
- [x] Nursery research — 6 more candidates investigated, all ruled out:
      Engall's (citrus only, no WA shipping), Woodbridge (CLOSED mid-2025), Mount Martin (click-and-collect only),
      El Arish (Neto, ornamentals), South Eden (US), Birdwood (B2B wholesale confirmed).
- [x] Data trend analysis (7-day, 2026-03-11 to 2026-03-18):
      Net: -101 in-stock items (autumn/end-of-season pattern). Daleys -47, Ladybird -40, Fruitopia -13.
      Ross Creek +16 (unusual). Primal Fruits: active inventory management (11 price increases).
- [x] Forever Seeds added (DEC-069):
      82 products, 76 in stock. NSW. Ships QLD/NSW/VIC/SA/ACT only. Rare tropicals specialist.
      Rollinia, Canistel, Black Sapote, Soursop, Vanilla Bean Orchid, Jackfruit, Longan, Cocoa, Coffee.
      Dashboard: 6,099 products, 15 nurseries. Nursery page: /nursery/forever-seeds.html.

---

## Completed This Session (2026-03-18 UTC, session 32 — 05:26 UTC)

- [x] Notion task (GSC sitemap blocker, id 3277f8d5-3f8e-80ad-b90a-d4538352be21):
      Benedict confirmed Google crawled sitemap on 2026-03-17. Removed blocker from task queue + backlog.
      Notion updated to Done.
- [x] Ross Creek Tropicals shipping confirmed (2026-03-18):
      Ships QLD/NSW/VIC/ACT only (Mon/Tue). No WA/NT/TAS. Already correct in shipping.py. Updated comment.
- [x] Ausnurseries shipping: site DNS is down/unreachable. Could not verify. Estimate retained (NSW/VIC/QLD/SA/ACT).
- [x] Yalca eastern states outreach content drafted:
      deliverables/yalca-eastern-states-outreach-2026-03-18.md — 6 ready-to-post pieces:
      1. Daley's Forum reply (heritage apple/Yalca thread)
      2. Daley's Forum new thread — treestock.com.au for planning bare-root 2026 season
      3. r/GardeningAustralia post — site intro, bare-root season angle
      4. r/AustralianPlants comment
      5. Heritage & Rare Fruit Network contact form (request listing on their sources page)
      6. Heritage Fruits Society VIC — worth investigating for listing
      Key insight: Heritage & Rare Fruit Network already lists Yalca on their sources page.
      treestock.com.au is not listed. This is a valuable backlink + credibility opportunity.

---

## Completed This Session (2026-03-18 UTC, session 31 — 05:02 UTC)

- [x] Notion task (URGENT): JS SyntaxError + blank prices (DEC-066):
      Root cause: Python f-strings consume backslashes, so `tomorrow\'s` in JS single-quoted strings
      was written as `tomorrow's` to the HTML. Unescaped apostrophe in JS single-quoted string = SyntaxError.
      This crashed the entire page script, leaving prices blank (prices are JS-rendered via render()).
      Plausible script "Loading failed" was a browser cascade from the page crash, not a DNS issue.
      Fixed both instances in build-dashboard.py by switching to JS template literals.
      Dashboard rebuilt and redeployed. Notion task updated to Done.
- [x] Notion task (empty, id 3277f8d5-3f8e-80ad-b90a-d4538352be21): No description. Marked Done.
- [x] Perth Mobile Nursery nursery report (DEC-066):
      build_nursery_report.py: Perth Mobile Nursery metadata added. normalize_product() schema normalizer
      added to handle Shopify (any_available/min_price) vs Ecwid/BC (available/price) schema differences.
      Site stats updated to current (539 visitors, 14 nurseries, 6,099 products).
      All 3 nursery reports regenerated. Perth Mobile report shows $770-880 mangoes prominently.
      URL: treestock.com.au/nursery-report-perth-mobile-nursery.html
- [x] Weekly FB post updated (fb-post-week12-2026.md):
      New angle: Perth Mobile Nursery just added. Lead hook: Bambaroo Mango $880, Nam Dok Mai $770,
      Longan Kohala $650, Black Sapote $550. Secondary: Primal Fruits Sapodilla $75, Lychee price drop.
- [x] Yalca Fruit Trees added to treestock.com.au (DEC-067):
      201 products (heritage/dwarf apples, pears, stone fruit, figs, quince, berry), 125 in stock.
      WooCommerce with public API. VIC-based. Seasonal: late June to Sep 15 only. No WA/NT/TAS shipping.
      Birdwood Nursery: wholesale B2B only. Not suitable for treestock.com.au.
      Dashboard: 6,099 products, 14 nurseries. Nursery page: /nursery/yalca-fruit-trees.html. Sitemap: 2,518 URLs.

---

## Completed This Session (2026-03-18 UTC, session 30 — 04:10 UTC)

- [x] Notion task: treestock.com.au still missing data (id: 3277f8d5) — investigated and marked Done.
      Site is healthy: 5,898 products, 13 nurseries, 1.73MB dashboard built at 04:11 UTC.
      Session 29's fix was effective. The Notion task was created before the fix resolved the issue.
      Notion updated to Done.
- [x] robots.txt created (was missing!):
      /opt/dale/dashboard/robots.txt — allows all crawlers, points to sitemap.xml.
      Now live at treestock.com.au/robots.txt. This helps Google discover all 2,500+ URLs.
- [x] Nursery pitch materials improved (DEC-065):
      featured-demo.html: rebuilt with sticky amber banner ("This is what Primal Fruits Perth looks like as Featured Partner").
      advertise.html: stats updated (490 → 537 visitors, 11k → 5,600+ fruit trees), "See a live demo" button added.
      build_nursery_report.py: stats updated, "See a live demo" link added to Primal Fruits report CTA.
      Nursery reports regenerated.
- [x] Perth Mobile Nursery added to treestock.com.au (DEC-065):
      220 products, 160 in stock. WA-based (Perth metro delivery).
      Premium pricing: mangoes $770-880, figs, pomegranates, dragon fruit, lychees.
      Scraped first snapshot. Nursery profile page live at treestock.com.au/nursery/perth-mobile-nursery.html
      Dashboard rebuilt: 5,898 products, 13 nurseries. Species/compare/location pages rebuilt. Sitemap: 2,504 URLs.
- [x] Traffic analysis completed:
      98% of 537 visitors/week go to homepage. Species pages get trickle (Whirlpool visitors explore species).
      13 Google visitors/week — lychee species page ranked for 1 Google query. Site is 13 days old.
      CVR: 0.7% (4/537). Expected at this stage; will improve with reputation/time.

---

## Completed This Session (2026-03-18 UTC, session 29 — 03:36 UTC, URGENT)

- [x] Notion task: treestock.com.au listing outage — DEC-064 (FIXED):
      Root cause: session 28 built featured-demo.html by modifying the live build script,
      which rebuilt index.html with Primal Fruits featured (reordered listings, amber styling).
      Fixed with:
      1. build-dashboard.py: --featured + --output-name flags (safe demo builds, never touch index.html)
      2. build-dashboard.py: atomic writes (tmp file → rename, no partial HTML served)
      3. build-dashboard.py: post-build verification (exit 2 if <500KB or <1000 products)
      4. run-all-scrapers.sh: pre-build backup + automatic rollback on failure
      5. deploy.sh: post-deploy size check with warning
      Tested: build works, --featured primal-fruits --output-name featured-demo.html works.
      Notion task updated to Done.

---

## Completed This Session (2026-03-17 UTC, session 27 — 20:00 UTC)

- [x] Notion task: 4x cron confirmed (again). Marked Done in Notion (id: 3247f8d5).
- [x] Heritage Fruit Trees species matching fix (DEC-062):
      match_species() and match_title() both improved with fallback that matches species
      at any position in the title (not just first N words).
      Heritage "Variety Species (size)" format now works: 0% → 82% (273/332 products tagged).
      Apple now top species in grid (Heritage adds 90 apples, 46 pears, 36 plums, etc.).
      Compare pages with Heritage: 2 → 13. Apple compare page: 92 Heritage listings.
- [x] Floating subscribe bar improved (DEC-062):
      Scroll threshold: 300px → 150px (shows sooner to users who don't scroll far).
      Time-based fallback: shows after 40 seconds even without scrolling.
      Dismiss: sessionStorage (per-session) → 3-day localStorage cooldown.
- [x] Welcome email confirmed working (dry-run tested).
- [x] Synced live files back to repo: subscribe_server.py, send_welcome_email.py, build-dashboard.py.
- [x] Dashboard + compare + variety + location pages all rebuilt and deployed.

---

## Completed This Session (2026-03-17 UTC, session 26 — 19:00 UTC)

- [x] Notion task: 4x cron confirmed (again). Marked Done in Notion (id: 3247f8d5).
- [x] Nursery value reports (DEC-061):
      scrapers/build_nursery_report.py — generates HTML sponsorship pitch per nursery.
      Reports live at treestock.com.au/nursery-report-primal-fruits.html and /nursery-report-heritage-fruit-trees.html.
      Shows: product counts, avg price, 526 visitor/7d audience, traffic sources, top products, basic vs featured comparison, $49/month CTA.
      Benedict: attach these URLs to Heritage Fruit Trees outreach + Cyrus WhatsApp.
- [x] Weekly FB post (deliverables/fb-post-week12-2026.md):
      Hooks: Sapodilla $75 Primal Fruits, Lemon Cempedak (rare), Jaboticaba Sabara $150, Ackee $95.
      Benedict: post Sunday morning 2026-03-22 in WA rare fruit FB groups.
- [x] Reddit + Whirlpool drafts (deliverables/reddit-whirlpool-drafts-2026-03-17.md):
      5 posts: Whirlpool thread reply, Whirlpool new thread, r/AustralianPlants comment, r/GardeningAustralia comment, Daley's Forum link.
      Priority: find existing Whirlpool thread (19 visitors from there today), reply to it.

---

## Completed This Session (2026-03-17 UTC, session 25 — 18:00 UTC)

- [x] Notion task: 4x cron confirmed already done (again). Marked Done in Notion (id: 3247f8d5).
- [x] Welcome email for new subscribers (DEC-060):
      scrapers/send_welcome_email.py — HTML welcome email via Resend.
      subscribe_server.py updated to fire it on each new signup (non-blocking Popen).
      subscribe-server restarted. Tested live — sent to ben@walkthrough.au OK.
- [x] All Season Plants WA scraper check: already in scraper since 2026-03-12. Not pending.
      Updated task queue to reflect this.
- [x] Fruitopia shipping: policy says "up to 3 weeks for other locations" — no explicit exclusions.
      Current estimate (NSW/VIC/QLD/SA/ACT) retained unchanged.
- [x] Dynamic subscribe CTA on homepage (DEC-060):
      When user searches "sapodilla", CTA reads "Get alerted when Sapodilla prices change"
      + link to species restock alert page. Falls back to query-specific copy for unknown terms.
      Uses SPECIES_MAP JS object (50 species + 150+ synonyms). Dashboard rebuilt + deployed.
- [x] Whirlpool traffic spike: 19 visitors from Whirlpool today. Added Q34 for Benedict
      (find the thread, post a response).

---

## Completed This Session (2026-03-16 UTC, session 24 — 21:00 UTC)

- [x] Notion task: 4x cron confirmed already done (again). Marked Done in Notion (id: 3247f8d5).
- [x] Verified Ladybird shipping states: Confirmed QLD/NSW/VIC/ACT only (not WA/NT/TAS).
      shipping.py updated with confirmed annotation.
- [x] Fruitopia shipping states: Could not confirm definitively. Current estimate (NSW/VIC/QLD/SA/ACT)
      remains. Their shipping policy doesn't list states explicitly.
- [x] Community engagement content drafted (DEC-059):
      deliverables/community-engagement-2026-03-16.md — 4 ready-to-post pieces:
      1. Daley's Forum thread reply (Fruit trees in Perth WA) — mentions All Season Plants WA, Primal Fruits
      2. Daley's Forum new thread — launch post for treestock.com.au in the community
      3. Rare Fruit Society SA listing request email
      4. Heritage and Rare Fruit Network national FB post
      Benedict: 30 min of posting. Priority: new Daley's Forum thread + Heritage FB group.

---

## Completed This Session (2026-03-16 UTC, sessions 22-23 — 18:00-20:00 UTC)

- [x] Notion task: 4x cron confirmed already done (DEC-050 from session 8). Marked Done.
- [x] Heritage Fruit Trees (BigCommerce) added to treestock.com.au (DEC-056, session 22).
      332 products scraped, 331 in stock. First temperate/heritage nursery.
- [x] Location pages script rebuilt (DEC-057/058):
      build_location_pages.py created with fruit_species.json filtering.
      Old pages showed irrigation connectors. New: 491 WA in-stock, 1,349 QLD/NSW/VIC.
      Added to run-all-scrapers.sh. Products sorted by price descending (interesting first).
- [x] Leeming Fruit Trees prospect research (session 23, DEC-058):
      - Address: 4a Westmorland Dr, Leeming, WA 6149. Phone: 0413 062 856. Wed-Sat 8:30am-2pm.
      - 10,148 Facebook followers. No website. Rare tropicals (rambutan, mangosteen, durian, etc.)
      - Better Track A+B prospect than Tass1 Trees — WA-based, exact treestock audience.
      - Full brief: deliverables/leeming-fruit-trees-cold-outreach.md
      - Already listed on treestock.com.au/buy-fruit-trees-wa.html (local pickup section).
      - Benedict to visit in person Wed-Sat.

---

## Completed This Session (2026-03-15 UTC, session 10 — 21:00 UTC)

- [x] Notion task: 4x cron verified already done (DEC-050 from session 8). Marked Done in Notion.
- [x] Homepage "Recent Highlights" section (DEC-055).
      Adds "What subscribers got alerted to this week" between species browser and subscribe CTA.
      Shows top 4 restocks + 3 price drops from last 7 days, WA shipping badges, real prices.
      281 restocks + 100 price changes this week — now visible to visitors before they subscribe.
      Subscribe CTA copy improved: "Get tomorrow's changes in your inbox".
      Dashboard rebuilt and deployed.
- [x] Weekly FB post prepared: deliverables/fb-post-week11-2026.md.
      Hook: Sapodilla back at Primal Fruits ($75), Jaboticaba 81% off at Daleys ($13).
      Benedict: post Sunday morning in WA rare fruit FB groups.

---

## Completed This Session (2026-03-15 UTC, session 8 — 13:52 UTC)

- [x] Notion task: 4x nightly cron sessions (DEC-050).
      Updated crontab: Dale now runs at 18:00, 19:00, 20:00, 21:00 UTC (2am-5am AWST).
      Notion task marked Done.
- [x] Compare price pages (DEC-051).
      50 pages at treestock.com.au/compare/ — cross-nursery price comparison per species.
      Shows cheapest nursery, price-sorted listings, email alert CTAs.
      Added to run-all-scrapers.sh. Sitemap updated: 121 URLs (was 70).
      Dashboard footer links to /compare/.
- [x] Business state updated: 11 nurseries, 10,426 products, 3,547 in stock, 3 subscribers.

---

## Completed This Session (2026-03-15 UTC, session 7 — 05:22 UTC)

- [x] Notion task: Add Fruit Tree Cottage to treestock.com.au scraper (DEC-048).
      Shopify confirmed. Shipping: NSW/VIC/QLD/SA/ACT (not WA/NT/TAS).
      First scrape: 185 products, 108 in stock. Great tropical selection.
      Profile page live: treestock.com.au/nursery/fruit-tree-cottage.html
      Rebuilt build_nursery_pages.py (was missing from repo) — all 11 nursery pages regenerated.
      Sitemap updated: 70 URLs (now includes nursery + location pages).
      All changes deployed. Notion task marked Done.

---

## Completed (2026-03-13 UTC, session 4 — 18:00 UTC)

- [x] Notion task: Vergeside bjnoel.com footer link — re-confirmed status in Notion as "Question".
      Work was done in session 3 (commit b347873). Patch at deliverables/vergeside-bjnoel-footer.patch.
      Benedict still needs to push from his machine (Q33).
- [x] Alert signup growth tracking — 3 subscribers, 0 watch signups. Expected: subscribe-server
      hasn't been restarted (Q32 still pending). Watch endpoint deployed but not running yet.
- [x] Uptime monitoring — built uptime_monitor.py. Checks treestock.com.au + walkthrough.au + Subscribe API
      every 5 minutes via cron. Sends email via Resend on down/recovery. All 3 endpoints currently UP.
- [x] Cold outreach Track A — analysed Tass1 Trees (Middle Swan, Perth specialist fruit nursery).
      Found: no HTTPS (browsers show "Not Secure"), no mobile support, no online shop, no social links.
      Full brief + cold email draft at deliverables/tass1-trees-cold-outreach.md.
      This is also a Track A+B crossover — potential treestock.com.au nursery addition.

---

## Tomorrow's Tasks (2026-03-20 UTC) — In Priority Order

### 1. Benedict actions (PRIORITY — not for Dale)

**Revenue outreach (highest priority):**
- **Email Perth Mobile Nursery** — info@perthmobilenursery.com.au — see deliverables/perth-mobile-nursery-outreach-2026-03-18.md. Send with nursery report: treestock.com.au/nursery-report-perth-mobile-nursery.html
- **WhatsApp Cyrus (Primal Fruits)** about featured listing — see deliverables/perth-mobile-nursery-outreach-2026-03-18.md for framing. Share: treestock.com.au/nursery-report-primal-fruits.html and treestock.com.au/featured-demo.html
- **Send Heritage Fruit Trees outreach** — see deliverables/heritage-fruit-trees-outreach-2026-03-16.md. Share: treestock.com.au/nursery-report-heritage-fruit-trees.html

**Community outreach (do after revenue):**
- **Find Whirlpool thread** (search "treestock.com.au" on forums.whirlpool.net.au), reply — see deliverables/reddit-whirlpool-drafts-2026-03-17.md
- **Post on Daley's Fruit Tree Forum** — new thread, see deliverables/community-engagement-2026-03-16.md (Task 2)
- **Post in Heritage and Rare Fruit Network** national FB group (Task 4 in same file)
- **Email Rare Fruit Society SA** to request links listing (Task 3 in same file)
- Visit Leeming Fruit Trees (4a Westmorland Dr, Leeming, Wed-Sat 8:30am-2pm)
- Post weekly FB post Sunday morning (deliverables/fb-post-week12-2026.md)
- Send Tass1 Trees cold email (deliverables/tass1-trees-cold-outreach.md)

### 2. Benedict actions — Eastern States Outreach (Yalca)

Content is ready in deliverables/yalca-eastern-states-outreach-2026-03-18.md. Priority order:
1. **Daley's Forum new thread** (20 min) — "planning bare-root 2026 season?" + treestock link
2. **r/GardeningAustralia post** (5 min) — site intro, bare-root season angle
3. **Heritage & Rare Fruit Network contact form** (5 min) — request listing on heritageandrarefruits.weebly.com/sources-of-fruit-trees.html (they already list Yalca — we aggregate them)
4. **r/AustralianPlants comment** (5 min) — find a relevant thread

### 3. Dale: Revenue experiment — subscriber growth (continued)

Session 35 tackled the funnel (sample digest improved, stale counts fixed, April glob bug fixed).
Next subscriber growth levers to explore:
- **"New to rare fruit trees?" landing page** — educational intro page targeting Google searches like "where to buy rare fruit trees Australia". Would serve as SEO content + subscriber funnel entry point for users unfamiliar with the site. Target URL: /guide.html or /start.html.
- **Ausnurseries shipping check** — DNS was down 2 days in a row. Try again, or drop them from listed nurseries if still down.
- **Google ranking check** — what queries are we now ranking for? Check Search Console via Benedict if possible.

### 4. Dale: Ausnurseries shipping check

Site DNS has been down 2+ days (2026-03-18, 2026-03-19). Try again next session — if still down, consider removing from dashboard or marking as unreachable.

---

## Backlog — Future Sessions

### Ops & Infrastructure
- [x] Set up weekly data backup — DONE: weekly_backup.sh + cron Sundays 02:00 UTC, 4-week rolling
- [x] Add uptime monitoring — DONE 2026-03-13: uptime_monitor.py, cron every 5 min

### SEO & Content
- [x] Nursery profile pages — DONE 2026-03-13 (DEC-041)
- [x] Variety-level pages — DONE 2026-03-15 (DEC-053): 2,308 pages at /variety/
- [x] "Compare prices" pages — DONE 2026-03-15: 50 pages at /compare/ (DEC-051)
- [x] Location pages — DONE 2026-03-14 (DEC-046): WA/QLD/NSW/VIC pages live
- [ ] Submit to Australian business directories (Hotfrog, StartLocal, True Local) — Benedict to do, can't sign up for services
- [x] Google Search Console submission — DONE 2026-03-17: sitemap crawled by Google.

### Revenue Experiments
- [x] Nursery affiliate programs — DONE 2026-03-13: None of Daleys/Diggers/Fruit Salad Trees have programs
- [x] Cold outreach audit — DONE 2026-03-13: Tass1 Trees analysis + email ready
- [ ] Benedict to send Tass1 Trees cold email ← see task 2 above (Benedict's action)
- [ ] Approach Daleys for sponsored listing once Primal Fruits result is in
- [x] Cross-sell Track A+B: Leeming Fruit Trees researched — DONE 2026-03-16. Brief ready, listed on WA page. Benedict to visit.
- [ ] Species alerts paid tier: once 10+ watchers on a rare species, consider $2/month premium

### Community & Growth
- [ ] Identify Reddit threads to answer with treestock data (r/AustralianPlants etc) — content drafted in yalca-eastern-states-outreach-2026-03-18.md
- [ ] Reach out to rare fruit societies about listing as a resource — Heritage & Rare Fruit Network contact form ready (yalca-eastern-states-outreach-2026-03-18.md task 5)

### Data Quality
- [x] Ladybird shipping states — DONE 2026-03-16: Confirmed QLD/NSW/VIC/ACT only (shipping.py updated)
- [x] Fruitopia shipping states — DONE 2026-03-17: Policy confirms national shipping, no explicit exclusions. Estimate retained (NSW/VIC/QLD/SA/ACT). QLD biosecurity rules apply by default.
- [ ] Analyse scraper data trends (price/stock changes over the week)
- [x] Add Tass1 Trees to treestock.com.au — DONE 2026-03-14: not scrapeable (no prices, no stock, static catalog only)
- [x] Add Fruit Tree Cottage to treestock.com.au — DONE 2026-03-15 (DEC-048)

---

## What's Been Tried
- **2026-03-10: Nursery sponsored listings (Primal Fruits)**
  - Drafted pitch for Primal Fruits ($49/month featured listing)
  - Technical: featured badge ready to activate in dashboard
  - Status: Awaiting Benedict to send WhatsApp to Cyrus (Q24)
  - Outcome: TBD

---

## Completed
- [x] 2026-03-10: treestock.com.au branding updated across dashboard + digest builder
- [x] 2026-03-10: Nursery sponsored listing pitch drafted (Primal Fruits)
- [x] 2026-03-10: Featured listing badge infrastructure added to dashboard
- [x] 2026-03-11: Email digest sending live (send_digest.py + subscribe_server unsubscribe + unsubscribe.html)
- [x] 2026-03-12: State-based shipping filters (replaces WA-only checkbox)
- [x] 2026-03-12: Species pages (50 pages at /species/, daily SEO content)
- [x] 2026-03-12: FB post drafted for Benedict (deliverables/fb-post-treestock.md)
- [x] 2026-03-12: Hetzner backup script ready (waiting on API token, Q27)
- [x] 2026-03-13: Species grid on dashboard (top 16 species, live stock counts)
- [x] 2026-03-13: Sitemap.xml generated daily (54 URLs, needs GSC submission — Q31)
- [x] 2026-03-13: FB launch analysis: 268 visitors, 211 from Facebook, 2 subscribers day 1
- [x] 2026-03-13: Per-species restock alerts (notify-me forms + alert email pipeline) — DEC-040
- [x] 2026-03-13: Weekly FB post template — deliverables/fb-weekly-template.md
- [x] 2026-03-13: Nursery profile pages (10 pages + index, DEC-041) — /nursery/ live
- [x] 2026-03-13: Sitemap updated to 65 URLs (was 54, +11 nursery pages)
- [x] 2026-03-13: Uptime monitor (uptime_monitor.py) — cron every 5 min, all sites UP
- [x] 2026-03-13: Tass1 Trees cold outreach brief + email (deliverables/tass1-trees-cold-outreach.md)
