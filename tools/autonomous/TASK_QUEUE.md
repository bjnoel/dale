# Task Queue — Autonomous Dale

*Dale works through tasks sequentially, top to bottom. Finish each one properly*
*before moving on. If you run out of time, note where you stopped.*

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

## Tomorrow's Tasks (2026-03-17 UTC) — In Priority Order

### 1. Verify Ladybird and Fruitopia shipping states

These are currently estimated. Check their websites to confirm which states they ship to.
- Ladybird (ladybirdnursery.com.au): currently listed as NSW/VIC/QLD/ACT
- Fruitopia (fruitopianursery.com.au): currently listed as NSW/VIC/QLD/SA/ACT
- If wrong, update shipping.py and rebuild affected pages
- This affects accuracy of location pages for QLD/NSW/VIC visitors

### 2. Investigate Whirlpool referral traffic

4 Whirlpool referrals this week (2026-03-16). Someone posted treestock.com.au on
Australia's largest tech/lifestyle forums. Find the thread and:
- Try fetching https://forums.whirlpool.net.au search to find the thread
- If found, assess whether Dale should respond or Benedict should engage
- Note: Whirlpool has strict rules about self-promotion, so be careful

### 3. Reddit/forum engagement strategy

Build a concrete list of:
- Active Australian gardening subreddits (r/AusGardening size, activity)
- Specific threads where treestock data would be genuinely useful to answer
- Draft 2-3 example responses Benedict could post (not spammy, genuinely helpful)
Benedict posts, not Dale. Dale drafts.

### 4. Benedict actions (not for Dale):
- Visit Leeming Fruit Trees (4a Westmorland Dr, Leeming, Wed-Sat 8:30am-2pm)
  Show them: treestock.com.au/buy-fruit-trees-wa.html (already listed there)
  Pitch: free listing today, website build for $199+
- Send Tass1 Trees cold email (deliverables/tass1-trees-cold-outreach.md)
  hello@walkthrough.au to joe@tass1trees.com.au
- Send Heritage Fruit Trees outreach (deliverables/heritage-fruit-trees-outreach-2026-03-16.md)
  WA shipping season opens May — timing is now
- WhatsApp Cyrus at Primal Fruits re: featured listing

### 3. Subscribe-server restart (Q32 — needs Benedict)

The watch/notify-me endpoint is deployed but the service hasn't been restarted.
Benedict to run: `sudo systemctl restart subscribe-server`
Watch signups will start accumulating once restarted.

### 4. Weekly data backup setup

Set up a simple weekly tar + local archive of /opt/dale/data/:
- cron: `0 2 * * 0 tar -czf /opt/dale/backups/data-$(date +\%Y-\%W).tar.gz /opt/dale/data/`
- Keep last 4 weeks
- No external dependency needed — pure local backup
- Future: add rsync to Benedict's machine or S3

---

## Backlog — Future Sessions

### Ops & Infrastructure
- [ ] Set up weekly data backup: tar /opt/dale/data/ and rsync offsite (free) ← task 4 above
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
- [ ] Verify Ladybird and Fruitopia shipping states (currently estimated)
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
