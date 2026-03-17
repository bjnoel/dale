# Task Queue — Autonomous Dale

*Dale works through tasks sequentially, top to bottom. Finish each one properly*
*before moving on. If you run out of time, note where you stopped.*

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

## Tomorrow's Tasks (2026-03-18 UTC) — In Priority Order

### 1. Benedict actions (priority — not for Dale)
- **Search Whirlpool for treestock.com.au** — find the thread, post a reply (Q34). 19 visitors today!
- **Post on Daley's Fruit Tree Forum** — see deliverables/community-engagement-2026-03-16.md (Task 2: new thread)
- **Post in Heritage and Rare Fruit Network** national FB group (Task 4 in same file)
- **Email Rare Fruit Society SA** to request links listing (Task 3 in same file)
- Visit Leeming Fruit Trees (4a Westmorland Dr, Leeming, Wed-Sat 8:30am-2pm)
- Send Heritage Fruit Trees outreach (deliverables/heritage-fruit-trees-outreach-2026-03-16.md)
- Send Tass1 Trees cold email (deliverables/tass1-trees-cold-outreach.md)
- WhatsApp Cyrus at Primal Fruits re: featured listing

### 2. Dale: Revenue experiment — nursery value report for sponsorship pitch

Build a simple "here's how treestock.com.au promotes your nursery" PDF or HTML report
that Benedict can attach to the Heritage Fruit Trees or Primal Fruits outreach email.
Content: page views for their nursery page, species they uniquely carry, what WA buyers
are searching for (mango, sapodilla, etc.). Makes the $49/month ask concrete and evidence-based.

### 3. Dale: Weekly FB post (2026-03-17 week)

Draft the weekly FB post for Benedict to post Sunday morning.
Use this week's most interesting changes: new listings, restocks, price drops.
Check the digest data for compelling hooks.

### 4. Dale: Check Reddit + Whirlpool gardening threads

r/AustralianPlants, r/GardeningAustralia — any threads where treestock.com.au is useful?
Draft responses for Benedict to post (can't sign up for services, but can draft the posts).

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
- [ ] Google Search Console submission — Benedict to add treestock.com.au (Q31 still open)

### Revenue Experiments
- [x] Nursery affiliate programs — DONE 2026-03-13: None of Daleys/Diggers/Fruit Salad Trees have programs
- [x] Cold outreach audit — DONE 2026-03-13: Tass1 Trees analysis + email ready
- [ ] Benedict to send Tass1 Trees cold email ← see task 2 above (Benedict's action)
- [ ] Approach Daleys for sponsored listing once Primal Fruits result is in
- [x] Cross-sell Track A+B: Leeming Fruit Trees researched — DONE 2026-03-16. Brief ready, listed on WA page. Benedict to visit.
- [ ] Species alerts paid tier: once 10+ watchers on a rare species, consider $2/month premium

### Community & Growth
- [ ] Identify Reddit threads to answer with treestock data (r/AustralianPlants etc)
- [ ] Reach out to rare fruit societies about listing as a resource

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
