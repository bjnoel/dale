# Task Queue — Autonomous Dale

*Dale works through tasks sequentially, top to bottom. Finish each one properly*
*before moving on. If you run out of time, note where you stopped.*

---

## Completed This Session (2026-03-13 UTC, session 3 — 14:08 UTC)

- [x] Notion task: Vergeside bjnoel.com footer link — DONE in local clone of bjnoel/vergeside-htmx.
      All 8 HTML pages updated. Can't push (server token lacks write access to vergeside repo).
      Marked as "Question" in Notion — Benedict needs to push from his machine (see Q33).
- [x] Nursery affiliate research — DONE (no programs exist): Daleys, Diggers, Fruit Salad Trees
      all checked. None have affiliate/referral programs. Not a viable revenue path currently.
- [x] Nursery profile pages — DONE (DEC-041): 10 nursery pages + index at /nursery/. build_nursery_pages.py
      written, added to cron pipeline. Sitemap updated to 65 URLs. Dashboard has ?nursery= URL param
      support + "Nurseries" footer link.

---

## Tomorrow's Tasks (2026-03-14 UTC) — In Priority Order

### 1. Track alert signup growth

Now that the notify-me feature is live (after Benedict restarts the service), monitor:
- How many species alert signups arrive in the next 24-48 hours
- Which species are most watched (sapodilla, jaboticaba, annonas expected)
- Log first watch signup in decision log as a milestone

### 2. Uptime monitoring setup

Research free self-hosted uptime monitoring options for Hetzner:
- Option A: Uptime Kuma (self-hosted, Docker) — can run on Hetzner, alerts via email
- Option B: UptimeRobot free tier — Benedict needs to sign up
- Preference: self-hosted on Hetzner if Docker is available (dale is in docker group)
- Set up whichever is easier; alert on treestock.com.au + walkthrough.au

### 3. Cold outreach Track A

Pick a Perth business, run analyse-business.py, draft a short cold email:
- Target: retail or professional services with weak digital presence
- Provide the analysis and email draft ready for Benedict to send
- This is the next step toward Track A revenue

---

## Backlog — Future Sessions

### Ops & Infrastructure
- [ ] Set up weekly data backup: tar /opt/dale/data/ and rsync offsite (free)
- [ ] Add uptime monitoring for treestock.com.au (free tier: UptimeRobot or similar) ← see task 4 above

### SEO & Content
- [x] Nursery profile pages — DONE 2026-03-13 (DEC-041)
- [ ] Variety-level pages (deeper than species — individual cultivars)
- [ ] "Compare prices" pages (e.g., /compare/mango-prices)
- [ ] Location pages (/wa-fruit-trees, /tas-fruit-trees) for state-based SEO
- [ ] Submit to Australian business directories (Hotfrog, StartLocal, True Local)

### Revenue Experiments
- [x] Nursery affiliate programs — DONE 2026-03-13: None of Daleys/Diggers/Fruit Salad Trees have programs
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
- [x] 2026-03-13: Nursery profile pages (10 pages + index, DEC-041) — /nursery/ live
- [x] 2026-03-13: Sitemap updated to 65 URLs (was 54, +11 nursery pages)
