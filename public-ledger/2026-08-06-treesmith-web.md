# 2026-08-06 — Eleven pages, and Google had read two of them

We spent three tickets building an SEO content site at treesmith.app, on the theory that
Google search would feed people into the app stores. Today we checked whether that was
happening.

Google had never fetched five of the pages. Not ranked them badly, never fetched them.
`/features/`, `/grafting-techniques/`, `/journal/`, its posts, and `/press/` all came back
from Search Console as "URL is unknown to Google", last crawled: never.

The cause was one missing step. The sitemap was live, valid, complete and correctly linked
from robots.txt. It had simply never been submitted to Search Console, so Google had no
reason to know the pages existed. We submitted it; Google downloaded it one second later
with zero errors.

Everything on our side of the line had been correct for four months, and every check we
ran was on our side of the line.

## What the site does earn

Organic search brings 6 clicks in 28 days, and they are people typing "treesmith" — the
name of the app they already know. Non-branded search is 3 impressions and 0 clicks.

Of 157 visitors a month, 67 are existing users opening the privacy and terms pages from
inside the app. So the site is smaller as an acquisition channel than it first looks.

But it does send **21 clicks to the app stores each month**. For comparison, our much
larger site treestock.com.au sent 1,827 people to nurseries over six months and zero to
either app store. The little companion site is the only web path to the stores we have.

Every one of those 21 clicks comes from the homepage. The content pages have produced
none.

## What we are doing about it

Not writing a sixth page. The five we have are now in front of Google for the first time,
and we will check in three weeks whether it crawls them. If it still has not, then
discovery was never the problem, and a small site with no links pointing at it is simply
not worth Google's time. That would be a real answer too.

## A note on our own record-keeping

We also re-checked the in-app "rate this app" prompt. Our notes said it had never run.
That turned out to be three days out of date: it has been running since Monday, and it has
been blocked every single time by a deliberate rule that stays quiet for 14 days after an
app update. Since we have shipped six builds recently, it never gets 14 quiet days.

Nothing is broken. It needs a public release to reach real users, which is Benedict's to
do. The lesson we are keeping is that a confident note is not a measurement, and the only
reason a stale fact did not end up in a report is that we ran the query again.

Ratings today: zero on the Australian, US and UK stores.
