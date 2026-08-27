# 2026-08-27 — The scraper that failed was fine. The one that "worked" had been making things up.

## What happened

Benedict reported the Engall's scraper failing. It was not failing. It returned HTTP 509 once, on
2026-08-26, and came back the next night with exactly the numbers it had the night before: 70
products, 43 in stock, 3.0 seconds. Engall's runs on LiteSpeed, and 509 is what shared hosting
sends when an account hits its bandwidth cap. The endpoint served 200 in 1.45s the next morning.

The guards built in DEC-293 all did their job that night. The anomaly email went out, the nursery
was marked untrusted, the dashboard held the last good snapshot, and nobody got a false restock
alert.

So the reported problem was a non-problem. The two problems underneath it were not.

## The scraper had never retried anything

The retry helper exists because of a Shopify-wide blip in July that cost ten nurseries a snapshot
in one run. Engall's is on WooCommerce, and the WooCommerce scraper had its own private copy of
the fetch with no retry in it at all. The copy reproduced the shared helper's log lines and its
health-recording exactly, so the scrape log looked identical to a scraper that had tried three
times and given up.

The durations were the only thing that gave it away:

```
2026-08-21  plantnet  HTTP 503  1.62s
2026-08-26  engalls   HTTP 509  0.88s
2026-08-27  rayners   HTTP 429  1.31s
```

The first backoff alone is two seconds. None of those was retried. Two of those three codes had
been on the retryable list for over a month; the scraper simply never asked. The paths that do use
the shared helper look like this instead: ladybird 33 seconds, heritage 1093 seconds.

## And the history had been quietly filling with days that never happened

A failed scrape does not overwrite `latest.json`. The availability tracker read that file
unconditionally and stamped today's date on every row it found, so on a night a nursery could not
be reached, yesterday's stock went into the permanent history as today's observation, prices
included. The run said so out loud and nobody heard it:

```
2026-08-26  engalls: failed - HTTP 509 ...
2026-08-26  Engall's Nursery: 70 updated, 0 new, 144 days tracked
```

Seventy rows recorded on a night nothing was fetched.

Across the whole dataset that came to 52 nursery-days and 24,567 rows since March, about one
percent of 2.37 million. Thirty-six of those days line up with a logged scrape failure. The other
sixteen predate the health log, so there was no record to check them against, but they proved
themselves another way: Primal Fruits has an eleven-day hole in May with no snapshots at all, and
of the 891 rows sitting inside it, 891 match the day before exactly and none differs.

## The part that had reached the public

One of those fabricated days had made it onto the live site. This sentence was on
`/variety/apple-coxs-orange-pippin.html`:

> We tracked it at 1 nursery between 24 March and 20 August 2026, in stock on 0 of those 143 days.

Garden Express was last reachable on 17 August. The 18th, 19th and 20th are the days its shop
moved to Shopify and every old API call started failing. The window and the day count were both
wrong.

That page is a tombstone, which is why it mattered. A live page carrying a bad date rebuilds
itself the next night and the error evaporates. A tombstone freezes, and would have gone on saying
20 August indefinitely.

## Why bother, when nothing measurably broke

The only automated consumer of this history is the rarity scoring that decides which species get a
"hard to find" badge. Recomputing all 122 species with and without the fabricated days moves zero
badges, and the largest score change is half a point against a threshold of 65.

The scores were never the reason. The accumulated price and availability record is the thing
nobody else in Australia has, and the plan has always been to eventually sell access to it. A row
we did not actually observe is not a thing that can honestly be sold, whether or not anyone would
notice.

## What was done

The WooCommerce scraper now uses the shared retry helper, and 509 has been added to the codes worth
retrying. The tracker now takes the date from the snapshot's own timestamp rather than from the
clock, and refuses to record anything that is not today's, saying so in the run output.

The history was rebuilt from the dated snapshots rather than patched, so that it is now a pure
function of the raw record: every day in it is a day we actually fetched. That removed the 53
fabricated days, and unexpectedly recovered 47 real ones that had never been recorded, mostly 12
August, when 26 nurseries scraped perfectly and the tracker stage never ran. Total cost: one row,
an ornamental daisy seen once in August that the current filters exclude anyway.

The two frozen tombstones carrying wrong numbers were corrected. They pick up the new text on
tonight's rebuild, which re-renders every tombstone by design.

The repair tool turned out to have a bug of its own, found the hard way: it treated every JSON file
in a nursery folder as a daily snapshot, and choked on the Daleys catalogue file part-way through
the real run, after three nurseries had already been rewritten. A tool whose job is to repair data
must not be able to stop halfway. It now checks that a filename is a date before believing it.

## The lesson

Both defects survived for months for the same reason: each produced output that looked exactly like
the correct output. The scraper logged like something that had retried. The tracker logged "70
updated" on a night it fetched nothing.

A log line that reads the same whether the work happened or not is not evidence that it happened.
