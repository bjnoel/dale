# Questions for Benedict

*Answer inline and mark [ANSWERED]. Dale reads this at the start of each session.
Keep answers short — a few words is fine. Dale will figure out the rest.*

**Rules:**
- This file is for async QUESTIONS only (things Benedict needs to answer)
- Action items and work requests go in Linear tickets, not here
- Archive answered questions periodically to keep this file short

---

## Open Questions

**Q48** [BLOCKING] Did we actually sell two copies of Treesmith Pro in July?

I opened Treesmith's PostHog for the first time tonight. `purchase_succeeded` carries an
`environment` property, and it has three events all time: a sandbox cloud-backup sub on
1 July, then **A$39.99 Pro on 6 July (production)** and **US$24.99 Pro on 23 July
(production)**. Three different people, none of them the sandbox one, and the 23 July
buyer is on a US storefront so it is not you.

Our state file says 0 sales and $0 revenue, and every strategy note I have written since
DEC-237 is reasoned from that zero.

**One lookup, not a decision.** Faster route than I first suggested: the app ships
`purchases_flutter`, so **RevenueCat's dashboard** shows this directly and separates sandbox
from production for you. App Store Connect > Sales and Trends, July 2026 also works.
Did those two land? If yes we have made roughly A$66 net and this business is not at zero.

Since I asked, I fixed the tool that hid them (DAL-266, DEC-253). It now reports purchases
all-time as well as weekly, so a sale can no longer age out of your Monday email. It also
turned out to be wrong in the *other* direction: it counted any untagged purchase as
production, and there are 13 untagged ones from the April-May TestFlight period. On a
cumulative view the old code would have told us we had made 12 sales. Both fixed.

I have deliberately not edited the revenue figure. Client-side telemetry is not a receipt.
DAL-264.

**Update 2026-07-31: this question is now worth much more than A$66.** I finally computed
an install-to-purchase rate, period-matched to the day `purchase_succeeded` started existing
(2026-07-01, so the all-time denominator would have been wrong): **2 production purchases /
49 installs = 4.1%**, 95% interval 1.1% to 13.7%. At roughly A$38 net that is **A$1.32 per
install**, which means about **6 installs a month covers the server bill** and about **123
covers your Claude spend too**. July had 49.

Every one of those numbers has your two receipts as its numerator. If they are real, Track A
has a working unit economic and growth is worth funding. If they are not, this whole
paragraph evaporates and so does DAL-271. One lookup settles it.

**Also, two things came off your plate rather than onto it:**
- **DAL-242 closed.** Both levers it asked you to decide are settled. The review prompt is
  built and enabled (build 56); it just is not in the released build (52), so it needs a
  submission, not a decision. And cutting the free tier 30 to 15 (DAL-224) is dead:
  181 of 186 people have never had a single plant, three have ever passed 15, two have
  passed 30. Recommend cancelling DAL-224.
- ~~The real constraint is that **97% of installs never add a plant.**~~ **Withdrawn.**
  That was a reporting artefact and I retracted it the next night (DEC-254). The event
  started 44 days after the installs it was divided by. Real figure is 27% for the July
  cohort, which is fine. Retention is the honest worry, not activation.

**Update 2026-08-03 (DEC-259): the ask has narrowed to one credential, and this question
now lives on DAL-265 with everything else about reporting accuracy.**

You told me the digest was wrong and you were right twice over. `plant_added` only fires
from the plant form, so import and restore create plants silently: **291 plants actually
held against 165 add events ever recorded, 43% invisible.** Your own record is 113 events
against a plant count that reached 160. Separately, every headcount was counting device
ids rather than people: **348 ids, 297 people**, one person carrying 27 of them, which
inflates installs 17% and is exactly how a returning buyer drops out of the active count
in the week they pay us. Both fixed and live.

**What I need is one thing: a read-only RevenueCat API key** (Project settings > API keys
> secret key, read-only). Both keys in the app are `String.fromEnvironment` at build time
so nothing is readable from the mirror; I checked and stopped looking. With it I report
money from receipts instead of telemetry and this question closes permanently instead of
once. While you are in there, confirming the A$39.99 on 6 July and US$24.99 on 23 July
answers the original question in ten seconds.

Until that key exists, every dollar figure in your Monday email stays labelled
directional, because it is.


**Q47** [BLOCKING] You have 8 open items from me. Here they are ranked, and two I want to withdraw.

I counted before starting work today: 8 Linear items assigned to you plus 2 questions here.
That is the actual bottleneck, not my throughput, so this is a ranking rather than a new ask.

**If you only do three things:**

1. **DAL-177** — paste the corrected Pro / cloud backup block into both store listings.
   Ten minutes. Right now both purchase pages say Pro includes cloud backup; it is a
   separate A$9.99/yr add-on. Someone can pay A$39.99 for a feature they did not buy.
   This outranks everything else because it is a live factual error, not an opportunity.
2. **DAL-245** — yes or no to *performance referral* on treestock (commission on a sale,
   no ads, no change to result ordering), plus the free Primal Fruits affiliate signup.
   I had the arithmetic 10x too low: full referral coverage is worth roughly $85-209/mo
   at today's traffic, not $21-62, and the top 3 nurseries alone cover the A$8.20/mo
   server bill about 4x. Detail on the ticket and in DEC-248.
3. **Q46** below — one email address.

**Answered 2026-08-03, both closed out:**
- **DAL-260** — you said yes. Both subscribers restored to "fruit" and verified against
  a live dry run of the digest; they start receiving from the 2026-08-04 send. Done.
- **DAL-80** — your two questions are answered on the ticket. The contact status and
  history view is live at **treestock.com.au/admin** behind the Access gate you already
  have. The BCC idea needs no new infrastructure (see Q46); it needs an alias and an
  IMAP app password from you, then DAL-273 builds the reader.

Then, when you have time: DAL-115 (community post), DAL-167 (send the RFSA email).

**Withdrawing three, unless you object:**
- **DAL-165** — your permaculture directory question is answered (no, DEC-245). Nothing
  left for you to do. Recommend closing.
- **DAL-173** — superseded by the subscriber drip (DEC-240) and DAL-221, and aimed at 13
  subscribers on a path measured at ~0 conversions. Recommend cancelling.
- **DAL-192** — long-tail /variety/ taxonomy records. DEC-249 measured a variety page at
  0.17 outbound clicks per page built against a state page's 2.85, with 1,014 of our
  1,659 variety pages taking zero visitors in 30 days. This ticket adds more of the
  thinnest part of that tail. Recommend cancelling, or say the word and I will rewrite
  it to follow GSC impressions instead of guessing.

**Q46** [BLOCKING] Confirm two Fastmail addresses on treestock.com.au

**Corrected 2026-08-03, I had this half wrong.** I wrote that treestock.com.au cannot
receive email. It can: the apex already carries your Fastmail MX
(`in1/in2-smtp.messagingengine.com`). What actually bounces is narrower. We send From
`alerts@mail.treestock.com.au`, a *subdomain* with no MX, and `stocklib/mailer.py` sets
no `Reply-To` at all, so a reply goes to the subdomain and dies. No DNS change and no
new service is needed, just an address on the apex to point `Reply-To` at.

Two asks, both on the mailbox you already pay for:

1. **Replies:** confirm an address for `Reply-To` (`hello@treestock.com.au`?). One line
   in `stocklib/mailer.py`, then DAL-243 closes and the bare-root seasonal email is
   unblocked. The welcome email and the Treesmith intro email both say "just reply to
   this email" and that is currently untrue.
2. **Nursery BCC (your DAL-80 idea):** create an alias, say `nursery-log@treestock.com.au`,
   and generate a Fastmail **app password scoped to IMAP only** into
   `/opt/dale/secrets/fastmail.env`. App passwords are individually revocable and that
   scope cannot send mail. Then BCC'ing that alias auto-logs the touch to the nursery
   register (DAL-273) and you never log anything from your phone.

This server can already reach `imap.fastmail.com:993`; I checked.

**Q45** [BLOCKING] STFC reply is drafted and shortened, ready for you to send

Preview: **https://stfc-preview.pages.dev** (A/B switch at the top of every page).
Draft: `docs/stfc-reply-draft.md`, now 384 words. I cannot send it and would not
want to.

*2026-07-28: you said you prefer B (reference library), so the draft now leans
that way in question 1, phrased as a lean rather than a verdict so the committee
still has an easy out. The preview itself stays neutral, A listed first, neither
marked as recommended.*

*Also 2026-07-28: stfc.org.au was briefly unreachable for you. Not us. The
harvest made 9 requests in total, rate limited to one a second, and the site
answers normally from your connection with no VPN.*

Only thing left: **read it and send it, or tell me what to change.**

Everything else about this is decided and logged as DEC-234.

**Q44** [RESOLVED 2026-06-12: Benedict approved the checkbox labels as-is, and the
public /digest.html stays fruit-only for now. No changes needed. DAL-202 review
scheduled for 2026-07-23.]

Bush tucker digest is now opt-in (DAL-199)

You asked for this to be opt-in at confirmation, off by default, with a choice of
categories (bush tucker / fruit trees, more later). Built and shipped that way:

- Each subscriber now has a plant-category preference. Default is **fruit trees
  only**, so every existing subscriber and anyone who does nothing keeps getting
  exactly the fruit digest. Bush tucker reaches no one unless they tick the box.
- The choice appears right after they confirm their email (the confirmation
  success page already had a preferences picker, so the category checkboxes sit
  there: Fruit trees pre-ticked, Bush tucker unticked), and again on the manage
  page reachable from any email.
- If they tick bush tucker, the digest gains a clearly labelled "🌿 Bush tucker"
  section (restocks / price drops / new), variant-level only, with the nursery
  shown after each item. The cross-listed fruits you already track (finger lime,
  desert lime, macadamia, lilly pilly, davidson's plum, kakadu plum, muntries,
  midyim) always stay in the fruit flow, so the rare-fruit feel is unchanged.

This is safe to be live: no bush tucker email content goes to anyone who has not
opted in. There is no global flag to flip any more, the opt-in itself is the gate.

Two small things to confirm when you get a sec (not blocking, easy to change):
1. The checkbox labels: "🍑 Fruit trees" and "🌿 Bush tucker" ok, or reword?
2. The public /digest.html page (the shareable one, not an email) currently shows
   fruit only, matching the default. Happy to keep it fruit-only, or show both as
   a discovery teaser. Which do you prefer?

---

**Q43** [RESOLVED 2026-06-11: Benedict sent the email; beewise replied declining to be
listed. Removed from beestock same day (DEC-198). Do not re-add without their explicit OK.]

Beewise's firewall has blocked the VPS IP (178.104.20.9) since May 24: every request
403s, even with a browser user-agent, while the same bot UA works fine from a
residential IP. They also added rate limiting (429 after ~100 fast requests). So the
nightly beewise scrape has failed silently for 19 days; I did a one-time slow scrape
from your machine today to fix the prices (they were also ex-GST, now fixed, DEC-192).

Beewise is a Perth business. Options:
- **(a)** You email them: beestock.com.au lists their products with referral links
  (utm_source=beestock), our monitor IP got caught in their May firewall change,
  ask them to allowlist 178.104.20.9. I can draft the email.
- **(b)** Drop beewise from beestock (data goes stale otherwise).
- **(c)** Leave as-is, I re-scrape manually from your machine occasionally.

a / b / c?

*Update 2026-06-11: the 403 is generated by their hosting stack's security layer
(Apache ErrorDocument behind Cloudflare, classic Imunify360/CSF-style automated
datacenter-IP blocklist), enabled May 24 along with generic rate limiting. So this
is automated, not the owner's doing; he likely can't lift it himself, only forward
the request to his host/agency (the site is agency-grade Magento 2). If you pick
(a), I'll write the email to be forwardable: IP, UA string, start date, symptom.*

**Q42** [SUPERSEDED 2026-04-27 by DEC-104]

Original question proposed three monetisation paths (B nursery sponsorship, C treestock paid tier, A walkthrough audits). DEC-104 selected a fourth path that was not on the original list: **Treesmith Pro subscriptions, with treestock as the funnel**. Walkthrough (option A) is paused. Options B and C remain on the table as future moves but are no longer blocking.

New revenue work belongs in Linear tickets (Treesmith ASO, treestock to Treesmith cross-promotion design, Stripe/RevenueCat decision, etc.), not in this file.

---

## Archive

Batches 1-16 archived (2026-03-05 to 2026-03-24, Q1-Q41). See git history for full text.
