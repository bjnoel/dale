# Questions for Benedict

*Answer inline and mark [ANSWERED]. Dale reads this at the start of each session.
Keep answers short — a few words is fine. Dale will figure out the rest.*

---

## Batch 1 — 2026-03-05 — Setup Decisions

### Q1 [ANSWERED] — Business Name
walkthrough.au registered for Track A. scion.exchange exists for Track B.

### Q2 [ANSWERED] — GitHub Repo
Done.

### Q3 [ANSWERED] — Rare Fruit Priorities
Benedict: Sapodilla (named varieties very hard to get in WA), annonas are personal
interest. Check Primal Fruits website (Benedict knows Cyrus) for expensive/rare
varieties — price is a good proxy for rarity. Benedict to search FB groups for
community demand signals.
Dale action: Scrape Primal Fruits, analyse pricing data across nurseries to identify
high-value/rare varieties algorithmically.

### Q4 [ANSWERED] — First Audit Prospects
Three warm leads:
1. PBR Plumbing (West Leederville) — Benedict knows the plumber
2. Wembley Cycles — Benedict did a previous SEO audit for them
3. Gather Ceramics (gatherceramics.com.au) — Benedict helped them before
Dale action: Run automated analysis on all three, prepare draft reports.

### Q5 [ANSWERED] — Blog Setup
Done. Astro deployed to Cloudflare Pages.

---

## Batch 2 — 2026-03-05 — Infrastructure & Next Steps

### Q6 [ANSWERED] — Cloudflare API Access
Done. Token provided, walkthrough.au deployed, DNS configured.

### Q7 [ANSWERED] — Track A Pricing Lock-In
Benedict: "You decide."
Dale decision (DEC-011): $199 for assessment. Reasoning: $149 risks looking
too cheap for trades/professional services. $199 is still an easy yes.
If friction is too high with first prospects, we drop to $149. Landing page
already shows $199.

### Q8 [ANSWERED] — scion.exchange Status
App is deployed (GitHub Actions + Cloudflare). Benedict not a fan of the React
Native stack. Build Track B dashboard separately — can use scion.exchange domain
or a subdomain (e.g. stock.scion.exchange). Keep existing app as-is for now.

---

## Batch 3 — 2026-03-05 — Prospect Approach & Track B

### Q9 [ANSWERED] — Wembley Cycles / Gather Ceramics Connection
Benedict: Felicity and John are friends (not partners). Paul (PBR) is also
a friend. All three are friends of Benedict.

### Q10 [ANSWERED] — Approach Order
Benedict: Confirmed. All three as free portfolio pieces (DEC-016).

### Q11 [ANSWERED] — All Three: Portfolio Pieces
Benedict: Do all three free in exchange for case studies and referrals.
Logged as DEC-016.

### Q12 [INFO] — Primal Fruits / Cyrus
I've built a scraper for Primal Fruits and it's running now (~139 products).
They ship to WA (rare!) and have some high-value items (Alphonso grafted
mango $242.50, Burdekin plum $145, sapodilla $72.75). When you see Cyrus,
worth mentioning we're building a stock tracker — could be good exposure
for his nursery if he's keen.

---

## Batch 4 — 2026-03-05 — Dashboard & DNS

### Q13 [ANSWERED] — scion.exchange DNS
Benedict added A record, but it's being caught by a wildcard rule
(*.scion.exchange) pointing to CF Pages. The `stock` subdomain
resolves to Cloudflare's proxy IPs and serves the existing scion-exchange
app instead of our dashboard.
**Fix needed:** Either:
(a) Set the `stock` A record to DNS-only (grey cloud, not proxied)
    pointing to 178.104.20.9 — Caddy handles HTTPS directly
(b) Or delete any wildcard CNAME/A record that's overriding the `stock` record
The dashboard works at http://178.104.20.9/ in the meantime.

Re: API token — yes, if you want me to manage scion.exchange DNS from
here, I'd need a new token with scion.exchange zone permissions added.
Not urgent since you can toggle the proxy setting in the CF dashboard.

### Q14 [ANSWERED] — Dashboard Feedback
Benedict feedback: taxonomy (genus/species/cultivar), historical prices,
more WA nursery research. Working on all three now.

### Q15 [ANSWERED] — Track A Prospect Status
Benedict: Will make contact over the next week. No action needed from Dale.

### Q16 [INFO] — WA Nurseries + Track A Crossover
Great idea mixing tracks. Found these WA fruit nurseries:
- **Guildford Garden Centre** — WooCommerce site, can scrape (50+ fruit trees)
- **Tass1 Trees** (Joe, Baskerville) — basic HTML site, no online shop. Open Sat-Sun. **Track A candidate.**
- **Leeming Fruit Trees** — no website found at all! Phone/address only. **Track A candidate.**
- **Perth Mobile Nursery** — has site, worth checking
- **Lena Nursery** (Wangara) — large range, worth checking

Tass1 and Leeming are perfect: show them the stock tracker,
offer to list their inventory for free, upsell Walkthrough for a proper
site/shop. Would you visit any of these?

### Q17 — Dashboard: Ornamental Filtering
I've filtered out ornamentals (roses, grevilleas, azaleas, etc.).
Dashboard now shows 4,141 fruit/nut/edible products (was 8,950).
Taxonomy matching at 64%. Latin names now show next to products.
Refresh http://178.104.20.9/ to see the update.

---

## Batch 5 — 2026-03-09 — Sharing & Alerts

### Q18 [BLOCKING] — Share Digest in WA Fruit FB Groups
The daily digest is ready with links to each product. Daleys dropped prices
on ~20 items (figs, chestnuts, starfruit, pomegranate, blueberries) and
restocked them. This is exactly what the WA rare fruit community wants to see.

**Can you share this in WA fruit FB groups this week?**
Copy-paste from: https://stock.scion.exchange/digest-wa.txt

The dashboard (https://stock.scion.exchange) now also has an email signup
form so people can subscribe for daily alerts.

### Q19 [INFO] — Track A Prospect Status Check
How's the approach going? Any conversations started with Wembley Cycles,
PBR Plumbing, or Gather Ceramics? No rush — just want to know if anything
has shifted.

### Q20 [ANSWERED] — scion.exchange DNS
stock.scion.exchange is live with HTTPS! Caddy auto-provisioned the cert.
Dashboard now accessible at https://stock.scion.exchange. Q13 resolved.

### Q21 [ANSWERED] — walkthrough.au DNS was missing
The CNAME records for walkthrough.au were never created — only email (Fastmail)
records existed. Dale fixed it via Cloudflare API. Both walkthrough.au and
www.walkthrough.au now resolve correctly to CF Pages.

### Q22 [INFO] — Miles Noel Studio Audit Complete
Full online presence audit for milesnoelstudio.com.au is ready at:
deliverables/miles-noel-studio-audit-2026-03-09.html
Key findings: no Google Business Profile, no meta descriptions, milesnoel.com
is down, zero reviews, no pricing on site. 10-step action plan included.
Most fixes CAN be done within Adobe Portfolio. Shall we send it to Miles?

---

## Batch 6 — 2026-03-09 — Autonomous Dale Setup

### Q23 [ANSWERED] — Pre-build checklist for autonomous Dale
All done! Resend API key, Claude CLI, and gh auth all set up on Hetzner.
Pipeline built and tested. Cron enabled at 18:00 UTC (2am AWST).
First autonomous session runs tonight.

---

## Batch 7 — 2026-03-10 — Revenue Experiment

### Q24 [IN PROGRESS] — Primal Fruits Sponsorship Pitch
First WhatsApp sent, no reply. Cyrus engaged with FB post though (aware of treestock).
Benedict can try another channel but has only met him once — low-pressure relationship.

WhatsApp to send:
> Hey Cyrus, hope you're well! Random one — I've been building a tool that
> scrapes nursery stock daily across Australia and alerts fruit collectors
> to what's new or back in stock. Launched at treestock.com.au — Primal
> Fruits is already in there. Wondering if you'd be interested in a small
> featured placement on it? Happy to chat or send details.

Full pitch details: docs/pitch-primal-fruits-sponsorship.md

### Q25 [ANSWERED] — FB Group Sharing
Benedict posted to 2 rare fruit FB groups on 2026-03-12. Live!

### Q26 — Plausible Analytics ✅
Plausible at data.bjnoel.com — tracking added to all pages.

---

## Batch 8 — 2026-03-12 — Post-FB-Launch Prep

### Q27 [ANSWERED] — Hetzner Backups
Enabled via API from local token. Backup window: 06-10 UTC. ~€0.76/month.

### Q28 [INFO] — FB Post for treestock.com.au
The FB post is ready at deliverables/fb-post-treestock.md. Three versions — primary
recommended. Site now has state-based shipping filters (not just WA) so it's useful
for all Australians. Post whenever you're ready.

### Q29 [INFO] — Shipping Data Verification
Filled in shipping states for all 8 nurseries based on website research. Two gaps:
- Ladybird Nursery: set as QLD/NSW/VIC/ACT (couldn't confirm SA)
- Fruitopia: set as QLD/NSW/VIC/SA/ACT (estimation)
If you notice these are wrong, let me know and I'll fix.

---

## Batch 9 — 2026-03-12 — Post-FB-Launch

### Q30 [ANSWERED] — Plausible API Key for Server
Done. Key from local secrets copied to /opt/dale/secrets/plausible.env.
plausible_stats.py deployed and tested. First results: 15 visitors today, 13 from Facebook.

---

## Batch 10 — 2026-03-13 — Post-FB Launch Day 1

### Q31 [ANSWERED] — Google Search Console for Sitemap
Benedict set up GSC for treestock.com.au on 2026-03-13. Sitemap submitted.
SEO for species pages now unlocked. Will monitor impressions in coming weeks.

---

## Batch 11 — 2026-03-13 — Species Alert Deployment

### Q32 [ANSWERED] — Restart subscribe-server service
Done. Restarted 2026-03-15. Species alert signups now working.

---

## Batch 12 — 2026-03-13 — Vergeside Footer Link

### Q33 [ANSWERED] — Push Vergeside bjnoel.com changes
Done. Pushed from server 2026-03-15. The GitHub token did have write access to all repos.
Netlify auto-deploys from main.

---

## Batch 13 — 2026-03-17 — Whirlpool Thread

### Q34 [INFO] — Whirlpool Traffic Source
19 visitors came from forums.whirlpool.net.au today (vs. usual near-zero).
Someone posted a link to treestock.com.au in a Whirlpool thread.
Can you search Whirlpool for "treestock.com.au" and find the thread?
If you do, worth posting a reply there — it's an active audience.
