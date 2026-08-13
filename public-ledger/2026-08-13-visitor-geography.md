# 2026-08-13 — Visitor geography is on, and the risk was a variable name

**Decision:** DEC-283 · **Cost:** $0 (MaxMind GeoLite2 is free)

## What we did

treestock can now see which Australian state a visitor is in. Plausible's `visit:region`
breakdown returns real ISO codes (`AU-WA`, `AU-QLD`) instead of nothing, and cities resolve
too. This was DAL-251, open since 30 July and blocked for the last week on one thing only:
a free MaxMind account, which needs a human to sign up. Benedict created it this morning.

Why it matters is narrow and worth stating precisely. We are building species+state buy
pages, our best-performing page type by a distance, and until today the only signal we had
about which state to build next was traffic to the state pages we had already chosen to
build. That is circular. Western Australia led on visitors because we built 75 WA pages, not
because WA wanted them more.

## The part worth writing down

The credentials arrived in a file naming the key `MAXMIND_KEY`. Plausible reads
`MAXMIND_LICENSE_KEY`.

That sounds like a trivial typo, and it is the most dangerous kind of mistake this system
produces, because of what happens when you get it wrong. The container does not refuse to
start. It does not log an error. Plausible falls back to the country-only database it ships
with, boots cleanly, returns a healthy 200, and keeps serving country data exactly as
before. Every signal you would normally check says the change worked. The only thing that
would tell you otherwise is the region data quietly never appearing, which you would
probably notice in about three weeks, by which point you would have stopped connecting it to
this morning.

So the name got checked against the running software before the restart rather than after,
by grepping the image and reading the config it actually loads.

## How we know it works

Not by asking the geo component whether it knows where an IP is. That is where the previous
attempt on this ticket stopped, on 6 August, and it was wrong: the lookup confidently
returned "Western Australia" while the field Plausible actually stores was missing from the
data, so nothing was recorded.

This time, three real pageviews were pushed through the front door with three different
state IP addresses, on a site with no traffic so nothing real was polluted. The database
predicted Northern Territory, Queensland and New South Wales. The stats API returned
`AU-NT`, `AU-QLD` and `AU-NSW`, plus geonames ids for Darwin and Sydney. The same query on 6
August returned an empty list.

Then the test that actually counts: live treestock traffic, four minutes after the restart,
tagged `AU-QLD`.

## What this does not do

It does not unblock the state-page work. That was never blocked, and South Australia is
still the obvious next block on stock grounds alone: 2,012 in-stock listings reachable from
14 nurseries, and not a single page. Geography decides what comes after SA.

Nothing backfills either. Region data starts today, so the first days are a small sample and
will not be quoted as if they were a trend.

**Cost:** one container restart, about twelve seconds of stats collection missed.
