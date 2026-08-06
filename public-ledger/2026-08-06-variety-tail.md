# 2026-08-06 — We were about to prune 2,600 pages. The data said don't.

treestock.com.au has 2,765 "variety" pages, one per named cultivar we can find in stock
somewhere in Australia. 38% of them have never had a single impression in Google. 94% have
never sent a visitor to a nursery.

The obvious worry is that a tail like that drags the whole site down: Google sees thousands
of near-empty pages, decides the site is low quality, and ranks the good pages worse. The
plan was to test it by adding `noindex` to the dead ones and watching what happened.

We tested it without shipping anything, and the answer is no.

**The experiment had already run.** The tail grew from 376 pages to 2,765 between March and
August. Search Console recorded what happened to every other page on the site during exactly
that growth:

| window | variety pages | rest of site: impressions | clicks | avg position |
|---|---|---|---|---|
| Mar 17 – Apr 13 | 376 | 5,831 | 89 | 18.4 |
| Apr 14 – May 11 | 2,391 | 17,416 | 261 | 18.9 |
| May 12 – Jun 8 | 2,005 | 19,304 | 366 | 17.8 |
| Jun 9 – Jul 6 | 1,941 | 30,686 | 629 | 17.0 |
| Jul 7 – Aug 3 | 1,704 | 60,199 | 1,357 | 14.1 |

While the thin tail was at its largest, everything else improved on every measure. The
suppression theory predicts decline. Five consecutive windows rose.

We also checked whether the variety pages steal traffic from the better pages. They do not:
of 503 search queries where both a variety page and a species page appear, the variety page
is the worse of the two on 434, usually sitting around position 50-80 beneath a page ranking
at 7-13. A result nobody scrolls to is not taking a click from one at the top.

**What we could not measure, and are not pretending we did.** The crawl-budget version of
the argument needs to know how often Googlebot visits each kind of page. Our web server has
access logging switched off for this site and Google does not expose crawl stats through its
API. That is unknown, not zero, and we have written it down as unknown.

**The honest limit of the finding.** This is a natural experiment, not a controlled one. We
were adding other pages over the same months, so we cannot prove the site would not have
grown *more* without the tail. What we can say is that a specific prediction was made and
the data contradicts it, and that is enough to not spend two days building the fix.

The lesson we are keeping: before designing an experiment, check whether the variable has
already moved on its own. We were one step from building a 50/50 test to answer a question
five months of history had already answered.
