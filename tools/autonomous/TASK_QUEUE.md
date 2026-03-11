# Task Queue — Autonomous Dale

*Dale works through tasks sequentially, top to bottom. Finish each one properly*
*before moving on. If you run out of time, note where you stopped.*

---

## Tonight's Tasks (2026-03-12) — In Priority Order

### 1. State-Based Shipping Filters (CRITICAL — Benedict posting to FB tomorrow)

Benedict is posting treestock.com.au to WA fruit FB groups tomorrow. The site needs
to be useful for ALL Australians, not just WA buyers. Implement state-based shipping
filters so anyone can find nurseries that ship to their state.

**Background:**
Australia has state-level plant quarantine restrictions. Three "quarantine states"
(WA, TAS, NT) have strict rules — many nurseries refuse to ship there. SA is moderate.
NSW/VIC/QLD/ACT are generally easy (most nurseries ship there).

**What to build:**

**1a. Replace `ships_to_wa` with `ships_to` state list in each scraper config:**

Research each nursery's actual shipping policy (check their websites) and set:
```python
"ships_to": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]
```

Known shipping data to verify/expand:
- Daleys: Ships WA (seasonal windows only), likely most states. Check TAS/NT.
- Ross Creek Tropicals: Doesn't ship WA. Check others.
- Ladybird: Doesn't ship WA. Likely doesn't ship TAS/NT/SA. Check.
- Fruitopia: Doesn't ship WA. Check others.
- Fruit Salad Trees: Ships WA (1st Tue of month). Likely most states. Check.
- Diggers: Ships WA (weekly). Likely all states. Check.
- Primal Fruits Perth: WA-based, local only / ships within WA.
- Guildford Garden Centre: WA-based, likely WA only.

**1b. Update build-dashboard.py:**
- Replace `WA_SHIPPING_OVERRIDES` with a `SHIPPING_MAP` dict per nursery
- Add a state selector dropdown (default: "All states") instead of the WA checkbox
- When a state is selected, filter to nurseries that ship there
- Show shipping badges like "Ships to WA" / "Ships to TAS" etc.
- Keep compact data format but change `"w": bool` to `"s": ["WA","NSW",...]`

**1c. Update daily_digest.py:**
- Replace `WA_NURSERIES` set and `--wa-only` flag with `--state XX` flag
- Support `--state WA`, `--state TAS`, etc.
- Keep `--wa-only` as an alias for backwards compatibility
- Generate state-specific digest pages: /digest-wa.html, /digest-tas.html, etc.
- At minimum generate WA and "all" versions (those are the current ones)

**1d. Update build_history.py if it has WA-specific logic.**

**1e. Update the email signup copy** in build-dashboard.py:
- Currently says "price drop & back-in-stock alerts for WA"
- Change to "for Australian fruit tree collectors" (or similar)
- The signup form should match the expanded state-based scope

**1f. Rebuild dashboard and deploy.** Run the full pipeline after changes:
- Update scrapers on server (copy to /opt/dale/scrapers/)
- Rebuild dashboard
- Rebuild digests
- Verify the site looks good

---

### 2. Enable Hetzner Server Backups

The scraped dataset is our real asset and it's not backed up.

- Use the Hetzner API to enable automatic backups on server ID 122794972
- API token is in /opt/dale/secrets/hetzner.env
- Cost: ~€0.76/month for daily rolling 7-day backups
- API call: `POST /servers/{id}/actions/enable_backup`
- This is within Dale's autonomous spending authority (< $10/month)
- Log as a decision in decision-log.md

---

### 3. Build Email Digest Sending

The signup form collects addresses but doesn't send anything — we need to
deliver on the promise before Benedict drives traffic from FB.

- Use Resend API (already configured, 100/day free tier)
- Subscribers are in /opt/dale/data/subscribers.json
- Send the daily WA digest HTML as the email body
- Add a send-digest.py script to the daily cron pipeline (runs after digest generation)
- Include unsubscribe link (required by CAN-SPAM / AU spam law)
- Test with Benedict's email (b@bjnoel.com) before going live
- Log as a decision

---

### 4. Generate FB Group Post for Benedict

Benedict is posting tomorrow. Draft a ready-to-paste Facebook post for him.

- Write to /opt/dale/repo/deliverables/fb-post-treestock.md
- Tone: casual, helpful, community-first. NOT salesy.
- Angle: "I've been building a tool that tracks fruit tree stock across 8 Australian
  nurseries — shows what's available, price changes, and which ones ship to WA.
  Free to use, thought it might be useful for the group."
- Include the treestock.com.au link and maybe the WA digest link
- Keep it short — FB group posts that are 3-5 sentences perform best
- Maybe mention the state filter if it's built by then

---

### 5. Programmatic SEO — Species Pages (Start)

This is the biggest long-term growth lever. Auto-generate one page per species
from the existing 164-species taxonomy + live scraper data.

**Each page (e.g., /species/mango.html) should show:**
- Species name + common names
- All varieties currently in stock across nurseries
- Price range (cheapest to most expensive)
- Which nurseries stock it + shipping states
- Current availability (in stock / out of stock counts)

**Target keywords:** "buy [species] tree online Australia", "[species] tree price Australia"

**Implementation:**
- Add a `build_species_pages.py` script
- Read taxonomy from fruit_species.json + latest nursery data
- Generate static HTML pages with the same Tailwind styling as the dashboard
- Include Plausible analytics tag
- Add to the daily cron so pages update with fresh data
- Start with a few pages to validate the approach, then scale

**Important:** Each page must have genuinely useful content, not thin auto-generated
filler. The unique data (prices, stock, shipping) IS the value — make it prominent.

---

## Backlog — Future Sessions

### Ops & Infrastructure
- [ ] Set up weekly data backup: tar /opt/dale/data/ and rsync offsite (free)
- [ ] Add uptime monitoring for treestock.com.au (free tier: UptimeRobot or similar)
- [ ] Review Caddy access logs for traffic patterns once FB post is live

### SEO & Content
- [ ] Nursery profile pages (/nursery/daleys, /nursery/ross-creek, etc.)
- [ ] Variety-level pages (deeper than species — individual cultivars)
- [ ] "Compare prices" pages (e.g., /compare/mango-prices)
- [ ] Location pages (/wa-fruit-trees, /tas-fruit-trees) for state-based SEO
- [ ] Submit to Australian business directories (Hotfrog, StartLocal, True Local)
- [ ] Submit to startup directories (Product Hunt, BetaList, SaaSHub, Indie Hackers)
- [ ] "Built in public" story post draft for Hacker News / Indie Hackers

### Revenue Experiments
- [ ] Stock alert signups — "email me when [variety] is back in stock" (monetisable)
- [ ] Nursery affiliate outreach drafts (check if Daleys, Ross Creek etc have programs)
- [ ] Cold outreach audit: pick a Perth business, run analyse-business.py, draft email
- [ ] Loom-style audit approach: draft script for Benedict to record video walkthroughs
- [ ] Approach Daleys for sponsored listing once Primal Fruits result is in
- [ ] Cross-sell Track A+B: approach WA nurseries without websites (Tass1, Leeming)

### Community & Growth
- [ ] Draft weekly "what's new in stock" post template for FB groups
- [ ] Create a "Fruit Tree Finder" search tool (postcode + variety → results)
- [ ] Identify Reddit threads to answer with treestock data (r/AustralianPlants etc)
- [ ] Reach out to rare fruit societies about listing as a resource
- [ ] "2026 Australian Fruit Tree Buying Season Calendar" — free PDF lead magnet

### Data Quality
- [ ] Improve taxonomy matching (68% → 80%+)
- [ ] Analyse scraper data trends (price/stock changes over the week)
- [ ] Check if Tass1 Trees has any scrapeable inventory
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
