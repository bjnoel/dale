# Questions for Benedict

*Answer inline and mark [ANSWERED]. Dale reads this at the start of each session.
Keep answers short — a few words is fine. Dale will figure out the rest.*

**Rules:**
- This file is for async QUESTIONS only (things Benedict needs to answer)
- Action items and work requests go in Linear tickets, not here
- Archive answered questions periodically to keep this file short

---

## Open Questions

**Q48** [ANSWERED 2026-08-03] Did we actually sell two copies of Treesmith Pro in July?

**Yes, and there were three, not two.** Answered from the RevenueCat key you put on the
server. Store-validated proceeds, net of commission and tax:

| when | store | country | proceeds |
|---|---|---|---|
| 2026-06-26 | App Store | Pakistan | US$17.40 |
| 2026-07-06 | App Store | Australia | US$17.66 |
| 2026-07-23 | App Store | US | US$17.49 |

**US$52.55 all time.** Five other purchases are sandbox and are excluded. `revenue_monthly`
is off zero for the first time, at US$35.15 (July's proceeds).

Two things you should know came out of it. Our own `purchase_succeeded` event never existed
before 1 July, so it never saw the Pakistan sale at all: PostHog says 2, the receipts say 3.
And **we keep 64% of the sticker price, not 85%** (A$39.99 Pro is US$27.74 gross and US$17.66
in proceeds), so every "net per sale" figure I have written was about 40% too high.

The Monday digest now reads money from RevenueCat and flags the disagreement. No action needed.

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
