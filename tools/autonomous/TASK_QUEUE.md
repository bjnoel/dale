# Task Queue — Autonomous Dale

*Dale works through tasks sequentially, top to bottom. Finish each one properly*
*before moving on. If you run out of time, note where you stopped.*

---

## Completed This Session (2026-03-13 UTC, session 2 — 13:12 UTC)

- [x] Species restock alerts ("Notify Me") — DONE (DEC-040): notify-me forms on all species pages,
      subscribe_server.py extended with action=watch, send_species_alerts.py written, added to cron pipeline.
      Service restart needed for watch endpoint to activate (Q32 for Benedict).
- [x] Email signup copy — Already correct ("Daily stock alerts — price drops & restocks, free."), no change needed
- [x] Day 2 traffic monitoring — 94 visitors today (still FB-driven), 32 direct (bookmarks = high intent!)
- [x] Weekly FB post template — DONE: deliverables/fb-weekly-template.md (3 templates: What's New, Price Drop, Species Spotlight)

---

## Tomorrow's Tasks (2026-03-14 UTC) — In Priority Order

### 1. Track alert signup growth

Now that the notify-me feature is live (after Benedict restarts the service), monitor:
- How many species alert signups arrive in the next 24-48 hours
- Which species are most watched (sapodilla, jaboticaba, annonas expected)
- Log first watch signup in decision log as a milestone

### 2. Nursery affiliate research

Check if these nurseries have affiliate programs:
- Daleys Fruit Trees (daleysfruit.com.au) — biggest national nursery in our data
- The Diggers Club (diggers.com.au) — large subscriber base, may have affiliate
- Fruit Salad Trees (fruitsaladtrees.com.au)

Research: look for /affiliates, /referral, /partners pages on each site.
If Daleys has one: draft a short pitch for Benedict to submit.
This is potentially $10-30/month in passive commission with zero ongoing work.

### 3. Nursery profile pages

Build /nursery/[slug].html pages for each nursery (SEO + context):
- Nursery name, location, what they specialise in
- List of all species they carry
- Shipping states
- Link to their products on dashboard (filtered view)
- Target keywords: "daleys fruit trees review", "ross creek tropicals stock"

These are lower-traffic but high-intent pages. 8 nurseries × decent search volume = worth building.

### 4. Uptime monitoring setup

Add UptimeRobot free tier monitoring for treestock.com.au:
- Benedict needs to create account at uptimerobot.com
- Add http(s) monitor for https://treestock.com.au
- Set alert email to hello@walkthrough.au or Benedict's personal email
- Or: research if there's a free self-hosted option on the Hetzner server

---

## Backlog — Future Sessions

### Ops & Infrastructure
- [ ] Set up weekly data backup: tar /opt/dale/data/ and rsync offsite (free)
- [ ] Add uptime monitoring for treestock.com.au (free tier: UptimeRobot or similar) ← see task 4 above

### SEO & Content
- [ ] Nursery profile pages (/nursery/daleys, /nursery/ross-creek, etc.) ← see task 3 above
- [ ] Variety-level pages (deeper than species — individual cultivars)
- [ ] "Compare prices" pages (e.g., /compare/mango-prices)
- [ ] Location pages (/wa-fruit-trees, /tas-fruit-trees) for state-based SEO
- [ ] Submit to Australian business directories (Hotfrog, StartLocal, True Local)

### Revenue Experiments
- [ ] Nursery affiliate programs — check Daleys, Diggers, Fruit Salad Trees ← see task 2 above
- [ ] Cold outreach audit: pick a Perth business, run analyse-business.py, draft email
- [ ] Approach Daleys for sponsored listing once Primal Fruits result is in
- [ ] Cross-sell Track A+B: approach WA nurseries without websites (Tass1, Leeming)
- [ ] Species alerts paid tier: once 10+ watchers on a rare species, consider $2/month premium

### Community & Growth
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
- [x] 2026-03-13: Species grid on dashboard (top 16 species, live stock counts)
- [x] 2026-03-13: Sitemap.xml generated daily (54 URLs, needs GSC submission — Q31)
- [x] 2026-03-13: FB launch analysis: 268 visitors, 211 from Facebook, 2 subscribers day 1
- [x] 2026-03-13: Per-species restock alerts (notify-me forms + alert email pipeline) — DEC-040
- [x] 2026-03-13: Weekly FB post template — deliverables/fb-weekly-template.md
