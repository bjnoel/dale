# Stale availability rows: retry gap, freshness guard, and the history rebuild

Investigated 2026-08-27 after Engall's failed a nightly scrape. Engall's itself was
a one-night HTTP 509 that recovered on its own. The investigation found two real
defects underneath it, and one wrong sentence already published because of them.

## What is wrong

### 1. HTTP 509 is never retried

`stocklib/retry.py` has `RETRYABLE_HTTP = {429, 503}`. Engall's runs LiteSpeed, and
509 (Bandwidth Limit Exceeded) is what LiteSpeed and cPanel emit when an account
hits its bandwidth or concurrent-connection cap. It is transient by construction.

The 2026-08-26 failure took 0.88s: one attempt, no backoff, no retry. The endpoint
returned 200 in 1.45s when probed the next morning. Compare rayners, which hit a 429
the same week and got the full retry ladder.

The module's own docstring says it exists because "a transient platform hiccup became
a missing snapshot day". 509 is exactly that class and is not on the list.

### 2. `availability_tracker.py` has no freshness guard

`update_nursery()` reads `latest.json` unconditionally and stamps `date.today()`. It
never checks the snapshot's own date, and never consults the untrusted-nursery signal
that the same pipeline run has already computed.

When a scrape fails, `latest.json` is not overwritten, so yesterday's stock is written
into the history as today's observation, prices included. On 2026-08-26 that produced
70 engalls rows on a night nothing was fetched, and the run logged
`Engall's Nursery: 70 updated, 0 new` to say so.

It is not engalls-specific:

```
orphan days (availability rows with no snapshot)   52   (53 including rayners 2026-08-27)
  explained by a logged scrape failure             36
  predating health logging (starts 2026-06-11)     16
rows on those days                             24,567   (1.04% of 2,365,530)
products that exist ONLY on orphan days             0
products whose first_seen is an orphan day          0
```

The 16 that predate health logging are the same bug, proved a different way:
primal-fruits has an 11-day hole from 2026-05-19 to 05-29 with no snapshots, and of
the 891 availability rows inside it, 891 match 2026-05-18 exactly and 0 differ.

### 3. One published sentence is already wrong

Live on `/variety/apple-coxs-orange-pippin.html`:

> We tracked it at 1 nursery between 24 March and 20 August 2026, in stock on 0 of
> those 143 days.

Garden Express's last successful snapshot is 2026-08-17; the 18th, 19th and 20th are
the Shopify-migration 400s. Truth is 17 August and 139 days. The page is a tombstone,
so it is frozen and will keep saying 20 August. Live pages rebuild nightly and
self-correct; tombstones and redirects do not.

That asymmetry is why this is worth fixing rather than noting.

## What is deliberately not being changed

**The rarity scores.** `build_species_pages.py` divides `in_stock_days / total_days`,
so it does inherit a persistence bias from the carried-forward rows. Recomputing all
122 species with and without the orphan days gives **0 hard_to_find badge flips** and a
largest score move of **0.526 points** against a threshold of 65. The scores are not
the reason to clean this up; the published claim is.

**Marking rows instead of deleting them.** Keeping the rows with a `"c": true` carried
flag preserves the record of what we believed at the time, and was rejected: it makes
every consumer opt in to honesty, and the two that exist today would keep counting the
rows until each is changed. Deleting makes honest the default for code nobody has
written yet, which is most of the code that will ever read this file.

**The price-recording quirk.** `availability_tracker.py` says "only record price if it
changed from most recent entry" but compares against the most recent *day*, not the
most recent *recorded price*. Since most days omit `p`, `last_price` is None every
other day and it re-records: Thorny Mandarin carries a price on 73 of 144 days for a
price that has been 65.0 every single time. Nothing reads `p` as a change signal today
(price-drop alerts use `daily_digest`'s variant compare per CLAUDE.md rule 3), so this
is noted and left alone rather than fixed alongside a data migration.

## Work list

All four done 2026-08-27. Logged as DEC-316.

1. **DONE, and bigger than written.** Adding 509 to `RETRYABLE_HTTP` would not have
   saved Engall's on its own: `woocommerce_scraper.fetch_json` was a private copy of
   the fetch that never called the shared helper, so it retried nothing at all. The
   failure durations prove it (plantnet 503 in 1.62s, engalls 509 in 0.88s, rayners
   429 in 1.31s, against a 2.0s first backoff), and two of those three codes were
   already retryable. Wired through `request_with_retry` and added 509.
   `bigcommerce_scraper` and `daleys_scraper` have the same shape and are NOT fixed
   here.
2. **DONE.** The day now comes from the snapshot's own `scraped_at` rather than from
   `date.today()`, and anything that is not today's is skipped and reported. Fails
   closed when `scraped_at` is missing or unparseable.
3. **DONE.** Rebuilt all 27 files. Result: **2,368,964 rows, zero days without a
   snapshot.** Removed the 53 fabricated days and recovered **47 real days that had
   never been recorded**, chiefly 2026-08-12, when 26 nurseries scraped cleanly and
   the availability stage did not run. Cost one row (a Federation Daisy, ornamental,
   seen once on 2026-08-20). Pre-rebuild copies in
   `/opt/dale/backups/availability-pre-rebuild-2026-08-27/`.
   `backfill_availability.py` had to be fixed first: it treated every `*.json` as a
   dated snapshot and died on `daleys/catalogue.json` after writing three nurseries.
4. **DONE, with a wider check than planned.** Re-derived all 334 frozen ledger entries
   from the rebuilt history rather than hand-editing one. Six disagreed; two are
   tombstones and were corrected (`apple-coxs-orange-pippin` to 23 March / 17 August /
   141 days, not the 139 estimated above, because the slug aggregates several titles
   and picked up recovered days; `mulberry-black-classic` 166 to 165 days).
   The other four are redirects, which publish no dated copy, and whose differences
   come from re-parsing titles under today's slug parser, the archaeology
   `build_variety_pages` explicitly warns against writing back. Left alone.
   The pages themselves re-render on the next nightly, which re-renders every
   tombstone by design. Not forced mid-day: `absent_nights` increments per run, so an
   extra run would count today twice for every page mid-exit-guard.

## Done means

- `python3 -m unittest discover tests/` passes.
- A 509 retries; a stale `latest.json` does not enter the history.
- No availability day exists without a corresponding dated snapshot, for every nursery.
- `/variety/apple-coxs-orange-pippin.html` reads "between 23 March and 17 August 2026,
  in stock on 0 of those 141 days" (re-derived from the rebuilt history, which both
  removed fabricated days and recovered real ones; the 139 guessed above counted only
  one product's rows, and the slug aggregates several titles).
- Decision logged in `decisions/decision-log.md` and a public-ledger entry written.
