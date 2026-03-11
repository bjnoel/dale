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

## Tonight's Task (2026-03-12) — PRIORITY: State-Based Shipping Filters

Benedict is posting treestock.com.au to WA fruit FB groups tomorrow. The site needs
to be useful for ALL Australians, not just WA buyers. Implement state-based shipping
filters so anyone can find nurseries that ship to their state.

### Background
Australia has state-level plant quarantine restrictions. Three "quarantine states"
(WA, TAS, NT) have strict rules — many nurseries refuse to ship there. SA is moderate.
NSW/VIC/QLD/ACT are generally easy (most nurseries ship there).

### What to build

**1. Replace `ships_to_wa` with `ships_to` state list in each scraper config:**

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

**2. Update build-dashboard.py:**
- Replace `WA_SHIPPING_OVERRIDES` with a `SHIPPING_MAP` dict per nursery
- Add a state selector dropdown (default: "All states") instead of the WA checkbox
- When a state is selected, filter to nurseries that ship there
- Show shipping badges like "Ships to WA" / "Ships to TAS" etc.
- Keep compact data format but change `"w": bool` to `"s": ["WA","NSW",...]`

**3. Update daily_digest.py:**
- Replace `WA_NURSERIES` set and `--wa-only` flag with `--state XX` flag
- Support `--state WA`, `--state TAS`, etc.
- Keep `--wa-only` as an alias for backwards compatibility
- Generate state-specific digest pages: /digest-wa.html, /digest-tas.html, etc.
- At minimum generate WA and "all" versions (those are the current ones)

**4. Update build_history.py if it has WA-specific logic.**

**5. Rebuild dashboard and deploy.** Run the full pipeline after changes:
- Update scrapers on server
- Rebuild dashboard
- Rebuild digests
- Verify the site looks good

### Secondary task: Build email digest sending
If time permits after the shipping filter work:
- Use Resend API (already configured) to send daily digest to subscribers
- Subscribers are in /opt/dale/data/subscribers.json
- 100 emails/day free tier
- This makes the signup form actually deliver on its promise

### Do NOT do tonight
- Don't change pricing or business direction
- Don't approach new nurseries or sponsors
- Don't restructure scraper architecture beyond what's needed for state shipping

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
