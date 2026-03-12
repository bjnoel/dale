# Task Queue — Autonomous Dale

*Dale works through tasks sequentially, top to bottom. Finish each one properly*
*before moving on. If you run out of time, note where you stopped.*

---

## Completed This Session (2026-03-12 UTC)

- [x] State-based shipping filters — DONE (DEC-035)
- [x] Hetzner backups — script ready, blocked on API token (Q27 for Benedict)
- [x] FB post for Benedict — DONE (deliverables/fb-post-treestock.md)
- [x] Species pages (start) — DONE (DEC-036, 50 pages live at /species/)

---

## Tomorrow's Tasks (2026-03-13 UTC) — In Priority Order

### 1. Monitor FB Launch + First Subscribers

If Benedict has posted to WA FB groups (expected today), monitor for:
- New subscribers (check /opt/dale/data/subscribers.json)
- Plausible analytics hits to treestock.com.au (if available)
- Any questions/comments Benedict reports from groups

If subscriber count > 5: consider personalising the email digest further.
If subscriber count > 20: email list is viable — plan paid tier announcement.

### 2. Species Pages: Add to Dashboard Search

Currently species pages only link from the footer. Make them discoverable:
- Add a "Browse by species" section to the main dashboard (below nursery summary)
- Show top 10-12 species with in-stock counts as clickable cards
- Style consistently with the existing dashboard

### 3. SEO: Add Sitemap

Generate /sitemap.xml for the species pages so Google can find them.
- Include: /, /species/index.html, /species/[slug].html (one per species)
- Include: /history.html, /digest.html
- Add to daily cron in run-all-scrapers.sh

### 4. Species Pages: Improve Taxonomy Matching

Currently showing "Species matched: 0/4965 (0%)" because build-dashboard.py and
fruit_species.json are separate. Wire them up:
- build-dashboard.py already tries to load SPECIES_FILE (fruit_species.json)
- The file now exists — deploy it and rebuild to get species matching working
- After rebuild, check match rate (should be ~40-60% with 50 species)

### 5. Revenue: Analyse First Subscriber Behaviour

If any subscribers have signed up via the FB post:
- Check what state they're from (wa_only field in subscribers.json)
- Are they clicking through to the dashboard? (Plausible)
- What's the unsubscribe rate after 3 days?
- This data informs whether to build the paid tier or continue growing free

---

## Backlog — Future Sessions

### Ops & Infrastructure
- [ ] Set up weekly data backup: tar /opt/dale/data/ and rsync offsite (free)
- [ ] Add uptime monitoring for treestock.com.au (free tier: UptimeRobot or similar)
- [ ] Review Caddy access logs for traffic patterns once FB post is live
- [ ] Hetzner backups: run enable-hetzner-backups.sh once Q27 is answered

### SEO & Content
- [ ] Nursery profile pages (/nursery/daleys, /nursery/ross-creek, etc.)
- [ ] Variety-level pages (deeper than species — individual cultivars)
- [ ] "Compare prices" pages (e.g., /compare/mango-prices)
- [ ] Location pages (/wa-fruit-trees, /tas-fruit-trees) for state-based SEO
- [ ] Submit sitemap to Google Search Console
- [ ] Submit to Australian business directories (Hotfrog, StartLocal, True Local)

### Revenue Experiments
- [ ] Stock alert signups — "email me when [variety] is back in stock" (monetisable)
- [ ] Nursery affiliate outreach drafts (check if Daleys, Ross Creek etc have programs)
- [ ] Cold outreach audit: pick a Perth business, run analyse-business.py, draft email
- [ ] Approach Daleys for sponsored listing once Primal Fruits result is in
- [ ] Cross-sell Track A+B: approach WA nurseries without websites (Tass1, Leeming)

### Community & Growth
- [ ] Draft weekly "what's new in stock" post template for FB groups
- [ ] Create a "Fruit Tree Finder" search tool (postcode + variety → results)
- [ ] Identify Reddit threads to answer with treestock data (r/AustralianPlants etc)
- [ ] Reach out to rare fruit societies about listing as a resource

### Data Quality
- [ ] Verify Ladybird and Fruitopia shipping states (currently estimated)
- [ ] Analyse scraper data trends (price/stock changes over the week)
- [ ] Look for other Perth-area nurseries with online stock

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
