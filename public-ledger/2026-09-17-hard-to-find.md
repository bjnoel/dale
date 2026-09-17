# 2026-09-17 — We were calling 45 plants "hard to find". Eight of them were.

treestock.com.au puts an amber "Hard to find" pill next to some species: on the rare finds
page, in the homepage stock table, on the species pages. It is a statement to somebody
deciding whether to drive to a nursery. Today we checked it and it was wrong for 37 species.

## What was broken

The score behind the badge averaged availability across **listings**, not nurseries. So one
nursery carrying twenty named varieties of a species, nineteen of them permanently sold out
and one always in stock, dragged the species' availability to 5%. A buyer could get one every
day of the week. We badged it as scarce.

The effect was not small:

- old rule: **45 species badged**
- new rule: **8**
- **24 of the 37 that lost the badge were in stock somewhere in Australia on literally every
  one of the 189 days we have measured**

White Sapote was the worst of it. Seven nurseries, in stock every single day, scored 79.4 out
of 100 and sat one point below the "Very rare" label. We flagged it back in April as a stale
entry on our own "hardest to find" list, and then kept badging it for five months.

## What it is now

The availability half is a nursery-day rollup: the share of measured days on which the species
was in stock at *no* tracked nursery at all. Days our scrapers failed are excluded, because a
broken cron is not a fact about Australian nurseries.

Crucially, the code is **imported from the builder behind our published shipping dataset**,
not written twice. The badge and the CC BY file at `/shipping-reachability.json` now agree on
`days_in_stock` and `days_observed` for all 119 species, zero disagreements, and a test fails
if they ever stop agreeing.

The eight that survive are the eight the published dataset already called scarce: African
Breadfruit, Breadfruit, Sea Celery, Kakadu Plum, Riberry, Muntries, Ruby Saltbush, Quandong.

We did not move the badge threshold. Lowering it to keep the page looking full would have been
widening the claim to fit the design.

## The consequence we are not hiding

`/rare.html` now shows **no badges at all**. None of the 31 exotic species it features are
actually hard to find by an honest measure. The genuinely scarce plants in Australia are bush
tucker, not tropical fruit. That is the answer, and it is more useful than the old one.

## The near-miss

The first version of the fix divided by the days a species was *listed* somewhere rather than
by every measured day. It reads as more careful. It put Riberry on 186 days in one file and
189 in the other: one fact, two published numbers, which is exactly the problem we set out to
remove. Caught before it shipped, only because we checked agreement across all 119 species
instead of the one in the test.

## Lesson

A number can be perfectly good for the job it was written for and wrong for the job it got
wired into. The listing-day average was a fine internal sort key. Nobody changed it; somebody
rendered it on a page. **When you find an internal metric, find its consumers before deciding
it is good enough.**
