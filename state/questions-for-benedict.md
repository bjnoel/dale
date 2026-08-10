# Questions for Benedict — FROZEN ARCHIVE (Q1-Q50)

> **This file is closed. Do not add to it.**
>
> Questions for Benedict are now **Linear tickets labelled `Question`**, created with
> `linear_update.py ask`. His call, 2026-08-10: *"can we convert questions for benedict
> to tickets instead of me needing to look through a text file?"* He already triages
> Linear on his phone, and a second inbox only he had to remember to open was one
> inbox too many. See the Communication Protocol in `CLAUDE.md`.
>
> **Migrated to Linear on 2026-08-10** (the two that were still open):
> - **Q50** (rename the app) → **DAL-279**
> - **Q45** (send the STFC reply) → **DAL-280**
>
> Everything below is kept for provenance, not for action. Several entries are cited
> from the decision log and from memory: Q46 carries the Fastmail security correction,
> Q48 carries the discovery that we had made three sales and keep 64% rather than 85%,
> and Q49 is the record of the ledger being wrong. Deleting them would break those
> references.

---

## Closed Questions (archive)

**Q50** [BLOCKING] Rename the app to `TreeSmith: Fruit Tree Tracker`? Yes or no.

Raised here because you asked "what rename decision, is this in DAL-257 or a different ticket?"
and the honest answer is **neither**: it was in DAL-177, which I closed as Done on 2026-08-10
while this open question was still inside it. My mistake. Putting it where open questions live.

**The change:** app name `TreeSmith: Plant Graft Tracker` (30/30 chars) becomes
`TreeSmith: Fruit Tree Tracker` (29/30). Brand kept, "Plant Graft" swapped for "Fruit Tree".

**Why it is the only ASO item with a measurable expected effect (DEC-247):** on Apple the
**name** is the field that ranks, not the subtitle or keyword field. Our subtitle contains
"garden journal" verbatim and we are not in the top 191 for it, while the top 4 are apps with
0 to 6 ratings carrying the phrase in their name. We are #7 for "fruit tree tracker" with the
words split across name and keyword field; #1 is a five-week-old app with 0 ratings that named
itself after the term.

**What it costs:** #1 on "graft tracker" and "grafting tracker" (DEC-237 established both have
no volume), and rank 186 of 189 on "plant tracker", which is nothing. Graft and scion stay in
the subtitle and description, where they convert rather than where they are found. It also
costs one app review cycle.

**Why it is yours:** it is a brand call, and it has to be typed into App Store Connect by you.

Alternate if you prefer the journal framing: `TreeSmith: Fruit Tree Journal` (29/30). I prefer
Tracker; "fruit tree journal" only reaches #40 today and those terms are polluted with generic
diary apps.

**If yes,** DAL-257 re-measures the same 36 terms four weeks after it goes live, so we find out
whether the name-field theory is right instead of assuming it. **If no,** say so and I will
cancel DAL-257, which exists only to measure this.

**Not urgent, and it should ride 1.0.10 rather than trigger its own submission.** You said you
are holding that release for fixes to land. Answering now just means it is queued when you push.

---

**Q49** [ANSWERED 2026-08-10] The ledger still says we have earned $0. Should I book the three sales?

**Answered: yes, book them.** Done the same day. All three RevenueCat-confirmed sales are
in `financials/ledger.json` as `type: revenue` entries: US$17.40 (2026-06-26, Pakistan),
US$17.66 (2026-07-06, Australia), US$17.49 (2026-07-23, US). **US$52.55 all time.**

One thing surfaced while booking them. The proceeds are **USD** while the ledger's currency
is **AUD**, and `ticket_outcomes.read_revenue_monthly` labelled its output with the ledger
currency regardless. Booking USD amounts would therefore have reported USD figures under an
AUD label, silently, from the first sale onward: the same class of error as DEC-263's renamed
event, where the number looks fine and means something else. It now sums per currency and
**raises rather than invent an FX rate** if revenue is ever booked in two currencies at once.
No exchange rate has been applied anywhere; reconcile against App Store Connect payment
reports when they are to hand.

The original text is kept below for the record.



Building the outcome loop (DEC-263) surfaced this. `revenue_monthly` is one of the five
metrics tickets can be graded against, and I pointed it at `financials/ledger.json`
deliberately rather than PostHog, because Q48 and DEC-252 established that client-side
telemetry is not a receipt.

The ledger has **zero revenue entries**. Not $0 this month: none, ever. `summary.total_revenue`
is 0 and `net` is -28.10. Meanwhile DEC-260 (three days ago) confirmed **three real sales**
from the RevenueCat key you put on the server, store-validated and net of commission.

So two things are true at once and both are bad:
- Our financial record of the business is wrong, and it is the one file that is supposed
  to be the receipt.
- Any ticket that claims `revenue_monthly` will be graded against a number structurally
  stuck at zero. It grades as "too small to call" rather than a false failure, so nothing
  is actively misreported, but the metric is dead until this is fixed.

I have deliberately not written revenue into the ledger myself. Booking income is a
financial record, not a reporting nicety, and the amounts should come off a statement
rather than off my reading of an API.

**What I need:** either (a) "go ahead, book the three from RevenueCat's store-validated
proceeds", and I will add them with the RevenueCat transaction ids as the reference, or
(b) you book them from App Store Connect / Play Console yourself, which is the stricter
option. Either is fine. Doing nothing leaves the ledger wrong.

---

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

**Q46** [ANSWERED 2026-08-10] Confirm one Reply-To address on treestock.com.au

**Answered: `ben@treestock.com.au`**, Benedict's choice over `hello@` because a
one-person nursery list reads better from a person. Shipped and verified the same day
(DAL-243, DEC-271): a real send now carries `reply_to: ['ben@treestock.com.au']` and
was delivered, not bounced. Deliverability was checked *before* shipping, since
pointing Reply-To at an address that does not receive mail would have reproduced the
bug with a nicer name.

Nothing further needed. The original text is kept below for the record.

**Corrected 2026-08-03, I had this half wrong.** I wrote that treestock.com.au cannot
receive email. It can: the apex already carries your Fastmail MX
(`in1/in2-smtp.messagingengine.com`). What actually bounces is narrower. We send From
`alerts@mail.treestock.com.au`, a *subdomain* with no MX, and `stocklib/mailer.py` sets
no `Reply-To` at all, so a reply goes to the subdomain and dies. No DNS change and no
new service is needed, just an address on the apex to point `Reply-To` at.

**Now one ask, not two. Corrected again 2026-08-06 — see below.**

1. **Replies:** confirm an address for `Reply-To` (`hello@treestock.com.au`?). One line
   in `stocklib/mailer.py`, then DAL-243 closes and the bare-root seasonal email is
   unblocked. The welcome email and the Treesmith intro email both say "just reply to
   this email" and that is currently untrue.

2. ~~**Nursery BCC:** create an alias and a Fastmail app password scoped to IMAP only.~~
   **WITHDRAWN 2026-08-06. Do not do this. The security claim was wrong and it was
   mine.** I wrote that the app password would be "scoped to IMAP only" and that "that
   scope cannot send mail". Both are false:

   - Fastmail's narrowest mail scope is **`Mail (IMAP/POP/SMTP)`, one bundle**. There is
     no IMAP-without-SMTP. The credential could have **sent mail as you**.
   - IMAP is read-write regardless: `STORE \Deleted` and `EXPUNGE` are part of it, so
     "can never delete" was only ever true of the code I planned to write. That is a
     promise, not a constraint.
   - An alias is a delivery address, not a boundary. The password authenticates to the
     **whole account**. Fastmail has no folder scoping and no read-only mode.

   So I asked you to hand Dale full read access to your mail plus the ability to send as
   you, and described it as locked down. Withdrawn.

   **Replaced by Resend inbound (DAL-273), which needs nothing from you at all.** We
   already use Resend for every outbound email and the keys are already on the VPS.
   Resend supplies a managed `<id>.resend.app` inbound address, so there is no alias to
   create, no DNS change, and no credential of yours involved. You BCC it exactly as you
   would have BCC'd the Fastmail alias, so the effort on your end is unchanged. Dale
   never touches your mailbox. DAL-273 is no longer blocked on you.

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
