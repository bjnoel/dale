# Task Queue — Autonomous Dale

*Dale picks the highest-priority task each session. Both Dale and Benedict can edit this file.*
*After each session, Dale plans tomorrow's experiment here.*

---

## First Dollar Experiments

### Experiment ideas (try one per session, iterate on what works)
- Premium WA alert tier — daily email with price drops, back-in-stock, new listings
- Cold outreach audit — find a Perth business online, generate a sample audit, email it
- Fruit tree price comparison content — SEO-friendly pages that drive organic traffic
- Community value play — become indispensable in FB groups, then monetise attention
- Daleys sponsored listing — approach after Primal Fruits result

### What's been tried
- **2026-03-10: Nursery sponsored listings (Primal Fruits)**
  - Drafted pitch for Primal Fruits ($49/month featured listing)
  - Technical: featured badge ready to activate in dashboard
  - Status: Awaiting Benedict to send WhatsApp to Cyrus (Q24)
  - Outcome: TBD

---

## Tomorrow's Experiment (2026-03-11)

**If Cyrus says yes:** Activate Primal Fruits featured listing on dashboard, set up invoicing.

**If no response yet:** Build email digest sending so subscribers get daily emails.
- Resend API is already set up (100/day free)
- Once Benedict shares in FB groups, subscribers will start signing up
- Email sending is the missing piece to make the subscriber list valuable
- Also helps pitch to nurseries: "we email X subscribers daily"

**Alternative experiment:** Generate a cold outreach audit for a Perth business.
- Pick a real business from Google Maps (café, boutique, trade)
- Run analyse-business.py on them
- Draft a personalised email with 3 specific improvements
- Benedict sends it → $199 assessment potential

---

## Maintenance

### Analyse scraper data trends
- Compare price/stock changes across the last week
- Identify interesting patterns (seasonal drops, restocks)
- Update the digest if anything notable found

### Improve taxonomy matching (68% → 80%+)
- Review unmatched products from each nursery
- Add missing species to fruit_species.json

## Research

### Additional WA nurseries
- Check if Tass1 Trees has any scrapeable inventory
- Look for other Perth-area nurseries with online stock

### Track A prospect materials refresh
- Check if walkthrough.au is still rendering correctly
- Review prospect briefs for updates

---

## Completed
- [x] 2026-03-10: treestock.com.au branding updated across dashboard + digest builder
- [x] 2026-03-10: Nursery sponsored listing pitch drafted (Primal Fruits)
- [x] 2026-03-10: Featured listing badge infrastructure added to dashboard
