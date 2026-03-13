# Task Queue — Autonomous Dale

*Dale works through tasks sequentially, top to bottom. Finish each one properly*
*before moving on. If you run out of time, note where you stopped.*

---

## Completed This Session (2026-03-13 UTC)

- [x] Monitor FB launch — DONE: 268 visitors (211 FB), 2 subscribers, 87% bounce, 60s avg
- [x] Species grid on dashboard — DONE (DEC-039): top 16 species shown as clickable cards
- [x] Sitemap.xml — DONE (DEC-039): 54 URLs, daily auto-generated, Q31 for Benedict re: GSC
- [x] Species taxonomy matching — Already working at 59% (2943/4968 products), was a stale task
- [x] Subscriber analysis — 1 real subscriber (hellojojo@myyahoo.com, WA), 0.5% FB→sub conversion

---

## Tomorrow's Tasks (2026-03-14 UTC) — In Priority Order

### 1. Revenue Experiment: "Notify Me" Stock Alerts

**Context:** The email signup currently says "Get notified when daily email alerts launch" but
daily emails are already live. The form text is misleading — fix it. More importantly, build a
per-species "notify me when back in stock" feature. This is the clearest monetisation path:

- Change signup copy to: "Get daily stock alerts — free for Australian fruit collectors"
- Build per-species alert signups: user enters email + selects species, gets emailed when
  any variety of that species comes back in stock
- This can be a **paid feature** for rare/high-demand species (e.g., Sapodilla, Annonas)
- Architecture: extend subscribers.json to include `watch_species: ["sapodilla", "jackfruit"]`
  - Or create separate watch_list.json
  - send_digest.py already has email infrastructure — extend it to send species alerts

### 2. Fix Email Signup Copy on Dashboard

The current copy "Get notified when daily email alerts launch" is wrong — emails are already live.
Fix in build-dashboard.py:
- Change to: "Get daily stock alerts — free"
- Subtext: "Price drops and back-in-stock alerts for Australian fruit tree collectors."
- Button: "Subscribe free"

### 3. Monitor Day 2 Traffic

Check Plausible for day 2 numbers:
- Did people return directly (direct traffic increase = high intent users bookmarking)
- Any more subscribers?
- Did the species grid increase engagement with species pages?
- If subscriber count reaches 5: consider personalising the digest (add "top picks for WA")

### 4. Weekly FB Post Template

Benedict should post a weekly "what's new" update to the FB groups to keep the community engaged.
Draft a template:
- Format: brief (2-3 lines), link to digest.html, highlight 2-3 specific items
- Keep it non-spammy (weekly max, not daily)
- Save to deliverables/fb-weekly-template.md

---

## Backlog — Future Sessions

### Ops & Infrastructure
- [ ] Set up weekly data backup: tar /opt/dale/data/ and rsync offsite (free)
- [ ] Add uptime monitoring for treestock.com.au (free tier: UptimeRobot or similar)
- [ ] Hetzner backups: run enable-hetzner-backups.sh once Q27 is answered

### SEO & Content
- [ ] Nursery profile pages (/nursery/daleys, /nursery/ross-creek, etc.)
- [ ] Variety-level pages (deeper than species — individual cultivars)
- [ ] "Compare prices" pages (e.g., /compare/mango-prices)
- [ ] Location pages (/wa-fruit-trees, /tas-fruit-trees) for state-based SEO
- [ ] Submit to Australian business directories (Hotfrog, StartLocal, True Local)

### Revenue Experiments
- [ ] Species alert signups — "notify me when [species] back in stock" (premium tier)
- [ ] Nursery affiliate outreach drafts (check if Daleys, Ross Creek etc have programs)
- [ ] Cold outreach audit: pick a Perth business, run analyse-business.py, draft email
- [ ] Approach Daleys for sponsored listing once Primal Fruits result is in
- [ ] Cross-sell Track A+B: approach WA nurseries without websites (Tass1, Leeming)

### Community & Growth
- [ ] Weekly "what's new" FB post template — TOP PRIORITY, see task 4 above
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
- [x] 2026-03-13: Species grid on dashboard (top 16 species, live stock counts)
- [x] 2026-03-13: Sitemap.xml generated daily (54 URLs, needs GSC submission — Q31)
- [x] 2026-03-13: FB launch analysis: 268 visitors, 211 from Facebook, 2 subscribers day 1
