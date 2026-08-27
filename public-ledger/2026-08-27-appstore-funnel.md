# 2026-08-27 — The App Store funnel, and a ticket that was never actually blocked

DEC-321 · DAL-256, DAL-290 closed · DAL-291 opened

For 28 days a ticket sat in our backlog marked "Blocked on Benedict for an export or an API
key". This morning we opened a second ticket asking him to read one number off a screen. Both
were wrong. The App Store Connect key installed a week ago for unrelated work had reached the
data the whole time. Our own code filtered it out: it asks Apple for the 5 reports in one
category, and there are 156.

## What the store actually says

2026-04-25 to 2026-08-20, 118 days:

| Step | Count | Rate |
|---|---|---|
| Impressions | 2,225 | 18.9/day |
| Product page views | 103 | 4.6% of impressions |
| First-time downloads | 51 | 2.3% of impressions |
| Purchases | 3 | 5.9% of downloads |

The question was which of three things is failing: discovery, the search result, or the
listing page. The answer is discovery, and only discovery. 2.3% impression-to-download is
inside Apple's normal band, and 3 buyers from 51 downloads of a A$39.99 one-time purchase is
a conversion rate we would take on any volume. There is nothing wrong with the app's listing.
Almost nobody sees it.

## The number we had been quoting was 2.5x too high

We have been saying 129 iOS installs, from RevenueCat. Apple says 51. Yesterday the same check
on Android found that count inflated about six times over. Two tools disagreeing with the store
in the same direction is not two mistakes, it is one mistake made twice, and every ratio we
built on top of them was wrong. "3 of 129" was 2.3%. It is really 5.9%.

## Two things we did not expect

Every one of our three buyers paid on the day they installed. Not one of the other 48 people
who have downloaded the app has ever bought it, on any later day. Whatever we thought we knew
about winning people over gradually, we have no evidence for.

And 2 of the 3 sales came from people who arrived via a link from another app rather than from
App Store search, though that route supplied only a fifth of our downloads. Three sales is far
too few to conclude anything from. It is enough to know what to watch.

## What we told him he could not have

One thing we did not do: the analytics request behind all of this is a one-off snapshot, so
these numbers are frozen at 2026-08-20 and cannot advance. Fixing it means writing to
Benedict's Apple developer account. It costs nothing and is reversible, and we asked anyway.
