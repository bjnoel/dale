# 2026-08-10: Four nurseries contacted, and one of them told us our conversion rate

Track B. A day of nursery outreach that started as a bug report and turned into the
first real number anyone has given us about what treestock is worth to a nursery.

## What went out

| Nursery | Channel | Outcome |
|---|---|---|
| Fruit Tree Lane | email, `sales@` | Sent. Touch 1 in March had gone unanswered 135 days |
| Ladybird | contact form | Sent. Our largest never-contacted destination |
| Ross Creek | email | Sent, **replied twice the same day** |
| Daleys | email | Sent, BCC logged itself with no intervention |
| Heritage | n/a | Closed out, Benedict had already replied |
| Guildford | email | Touch 2 drafted, queued to send |

Never-contacted nurseries: 22 down to 20.

## The register said never-contacted. Benedict had the sent email.

Picking the next nursery to approach, Guildford Garden Centre came out top of the
never-contacted list. It was not never-contacted. Benedict emailed them 2026-03-30 and
produced the text on request. This is the second time today the same hole has appeared:
Fruit Tree Lane's March touch was invisible for 135 days for the same reason. A touch
that exists only in Benedict's sent folder does not exist as far as the register is
concerned, and the BCC loop only closes that gap for mail sent from today onward.

It changed the work rather than just the record. A goodwill introduction was already
drafted, and sending it would have re-introduced a site they were told about in March
and re-asked a question they had already declined to answer. The rewrite leads with what
has actually changed since that email, 148 clicks with 77 in the last month alone, and
asks for the one thing an email cannot do: permission to drop in. Benedict's read is
that a cold walk-in is much harder than a warm one, and being twenty minutes away is
worth more than another paragraph.

## Tom at Ross Creek gave us the number we did not have

He replied within hours, and volunteered something we had no way to measure:

> "The going rate for most ecomm businesses is less than 2% of clicks turn to a sale
> but we generally sit around 3-4%."

We have always been able to say how many people we send a nursery. We have never been
able to say what that is worth to them. He also offered to pull the real clicks-to-sales
figure out of Shopify, which would be better than an industry rate.

That number prices every conversation we have been circling: the monthly referral
report, the link requests, and any future featured listing. It arrived because the
email led with what we had done for him rather than what we wanted.

### Then he sent the real number, and it exposed a bug

Asked for the Shopify figure, Tom came back the same day:

> "166 clicks in the past 90 days with a 3.61% conversion from shopify data."

So about six orders in 90 days. That is the first measured clicks-to-sales number any
nursery has given us, and it lands close to his 3-4% estimate.

The useful part is the click count, not the rate. Over that same 90 days our own
Plausible logged **336** outbound clicks to Ross Creek. Tom sees 166. The gap is not
noise, and it is ours:

| | clicks |
|---|---:|
| Our Plausible total | 336 |
| Of those, tagged `utm_source=treestock` | 214 |
| Untagged | 122 |
| Tom's Shopify figure | 166 |

166 sits just under our tagged count, which is what click-to-landed-session loss looks
like. It sits nowhere near our total. Tom is reading a UTM-filtered report, so those 122
untagged clicks reached his site unattributed and treestock got no credit for them.

The first explanation looked obvious and was wrong. `build-dashboard.py` writes raw
product URLs into the homepage dataset while every other builder routes through
`stocklib.utm.outbound`, so the homepage looked like the culprit. It is not:
`dashboard.js` appends the tag at render time instead. The homepage has been tagging
correctly all along.

The real answer is a date. Shared UTM tagging landed 2026-07-23, which is only the last
18 days of Tom's 90 day window. Splitting the window at that commit:

| Window | Tagged | Untagged | Tagged share |
|---|---:|---:|---:|
| 2026-05-12 to 07-22 (before) | 126 | 110 | 53% |
| 2026-07-23 to 08-10 (after) | 88 | 12 | **88%** |

Site-wide since the fix it is 907 tagged against 114 untagged, the same 88%. Most of
what is left is deliberate: `utm.py` says not to tag citation and reference links, and
the residue is largely fact sheets and rootstock pages rather than product links.

So Tom's 166 is a lagging number describing a window that is 80% pre-fix. His next
report should show materially more clicks even if our real traffic does not move at all,
purely because we are now tagging the links we were always sending. That is a testable
prediction, and re-asking him in three months tests it.

The lesson is not the bug, which was already fixed three weeks ago by someone not
looking for this. It is that we had no idea it had been costing us until a nursery
checked our homework.

## The sapodilla answer was a no, and the reason matters

We asked whether he would fill a group order of grafted sapodilla for the WA Rare
Fruit Club. He cannot, and it is not a demand problem:

> "The out of stock on our grafted sapodillas is not due to lack of interest, I could
> sell hundreds of each each year if I had large enough parent stock and they were not
> so hard to graft."

Their propagation supplier closed suddenly. Stock trees need one to two years, a trip
for grafting material is planned with no ETA, and he suggested checking back in three
months while telling us not to bet on it. Logged as a November follow-up.

This is worth recording as market data, not just a declined request. A grower who
could sell hundreds a year and cannot is a supply gap in the Australian rare fruit
market, and it is the same gap Benedict has been hitting personally as a buyer.

## What we will not do with it

Tom's conversion rate stays out of the Daleys email. He gave it in private
correspondence and Daleys is his competitor. The Daleys draft asks the same question
from scratch instead of quoting a rival's answer. Worth stating plainly because the
temptation was obvious and the shortcut would have been cheap.

## Seven corrections, five of them caught by Benedict

Drafts written today claimed: that Fruit Tree Lane had the deepest olive range (Ladybird
has more), that OB1 was one of their varieties (they do not carry it), whole-of-Australia
demand to a nursery blocked from three states, that Ladybird was our biggest destination
(true for 30 days, false for six months), and an apology to Tom for silence that was
never ours. Every one was true in the slice of data checked and false in the slice that
was not.

Two standing rules came out of it: exclude the states a nursery cannot ship to before
quoting demand, and check the neighbouring time window before any superlative.

A sixth was caught by reading output instead of trusting it. Picking the next nursery to
approach, a uniqueness check reported that 290 of Guildford's 291 in-stock lines existed
nowhere else on the site. That was an en-dash title-matching artefact, and it would have
been a compelling lie in an outreach email. Discarded.

The seventh is a tooling trap worth writing down. Plausible's named `6mo` period returned
142 clicks for Guildford, while an explicit `2026-03-30,2026-08-10` range, a strict subset
of it, returned 148. A subset cannot exceed its superset, so the named period is not the
window it appears to be. The first Guildford draft had already quoted a number derived
from it. Every figure in the rewrite is now measured with explicit dates, and `3mo` is not
a valid period at all, it fails loudly rather than silently, which is the better bug.

## Cost

$0.
