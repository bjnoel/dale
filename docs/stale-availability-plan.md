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

1. **Add 509 to `RETRYABLE_HTTP`**, with a regression test that a 509 is retried and a
   non-retryable code is not.
2. **Freshness guard in `availability_tracker.py`**: skip a nursery whose `latest.json`
   is not dated today, and say so in the run output rather than silently. Regression
   test covering the stale case, the fresh case, and a snapshot with no date field.
3. **Rebuild the 27 availability files from the dated snapshots** on the server, using
   `backfill_availability.py`, which reconstructs purely from snapshots so orphan days
   drop out by construction rather than by a delete script. Verify row counts against
   the numbers above before and after. Backups: `/opt/dale/backups/data-2026-W*.tar.gz`
   are weekly and `availability.json` is cumulative, so W34 holds everything to 23 Aug.
4. **Correct the `apple-coxs-orange-pippin` ledger entry** to `last_seen 2026-08-17` /
   `live_days 139`, and rebuild the tombstone so the published sentence matches.

## Done means

- `python3 -m unittest discover tests/` passes.
- A 509 retries; a stale `latest.json` does not enter the history.
- No availability day exists without a corresponding dated snapshot, for every nursery.
- `/variety/apple-coxs-orange-pippin.html` reads "between 24 March and 17 August 2026,
  in stock on 0 of those 139 days".
- Decision logged in `decisions/decision-log.md` and a public-ledger entry written.
