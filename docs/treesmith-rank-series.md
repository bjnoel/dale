# TreeSmith ASO rank series (DAL-257)

Wire the two existing rank readers into a series, a diff, a digest section, a cron line and a
published artefact.

## Context

We renamed the app from "TreeSmith: Plant Graft Tracker" to "TreeSmith: Fruit Tree Tracker".
Play changed 2026-08-13; iOS rode 1.0.10 and went live 2026-08-19 13:13 UTC. The rename traded
exact-match dominance for breadth, and the Play day-0 capture proves the loss side arrives
*gradually*: "graft tracker" was still rank 1 an hour after the Play edit and gone a week later.
iOS is one day post-launch, so **iOS has not finished paying the cost yet.**

`appstore_rank.py` and `playstore_rank.py` both exist and both work. Nothing schedules them,
nothing accumulates their output, and nothing pushes movement at Benedict. Every comparison to
date has been a manual two-file diff, and the 13 August pre-rename baseline nearly went to waste
because there was no series for it to be the start of.

DAL-257 asks for a re-measure four weeks after the rename (due ~2026-09-10) with predictions
recorded in advance. This branch builds the instrument that makes that re-measure automatic and
comparable rather than a hand-run script and a two-file diff.

## The three semantics the series must preserve

Neither reader has a `status` field today. DEC-249 is enforced *structurally*: an errored row
carries `error` and **omits `rank`, `result_count`, `truncated` and `top3` entirely**
(`tests/test_appstore_rank.py:72` pins `assertNotIn("rank", rows[0])`). Flattening to CSV forces
those states to be named, because a CSV cell cannot be "absent" — only empty.

A four-value `status` column, with `truncated` kept alongside as the raw boolean:

| status | rank | result_count | truncated | means |
|---|---|---|---|---|
| `ranked` | int | int | bool | we are at that position |
| `absent` | *(empty)* | int | `false` | DEC-255: absence **proven** — the store ran out of results before the cap |
| `absent_window_capped` | *(empty)* | int | `true` | DEC-255: absence **not proven** — we could be at 31 |
| `error` | *(empty)* | *(empty)* | *(empty)* | DEC-249: nothing was measured. Not a zero. |

`playstore_rank.saturated()` is `>=` WINDOW, not `==` — real AU data contains `result_count: 50`
still flagged truncated. Reuse the function; do not re-derive the comparison.

Apple has no `truncated` concept. Rather than leave the column blank and let a future capped iOS
window read as proven absence, derive it as `result_count >= appstore_rank.LIMIT` (LIMIT = 200,
pinned by a test). Observed iOS counts are 37-193, so this is `false` everywhere today and only
ever becomes `true` if Apple starts capping us.

## Worked examples, on the real rows already in `data/`

### 1. A drop where nobody took the slot — iOS AU `graft tracker`, 1 -> 11

Baseline row (`treesmith-appstore-rank-baseline.json`, AU):

```
rank=1  result_count=184
top3 = ['TreeSmith: Plant Graft Tracker', 'Peptide Tracker - PeptideKit', 'Blood Sugar Tracker-AI Health']
```

US is the same story with different neighbours: `['TreeSmith', 'StoryGraph: Reading Tracker',
'Case Tracker for USCIS & NVC']`.

The two apps behind us are a peptide tracker and a blood-sugar tracker. When we fall to 11, those
two shift up. `newcomers = curr_top3 - prev_top3` is empty, `held` is non-empty, so the diff must
say **vacated** — we stopped matching the term — and must *not* say a competitor beat us. This is
the finding the whole `top3` column exists to support.

### 2. A drop where a real competitor arrives

Same shape, opposite classification: if `curr_top3` were `['Fruit Tree Tracker - Grove',
'Peptide Tracker - PeptideKit', ...]` — one newcomer, the rest holding station — the diff says
**displaced by Fruit Tree Tracker - Grove**. Grove is a real competitor (DEC-237) and that is a
different business fact from example 1, which is why the two must not render identically.

Third case, both empty: none of `prev_top3` survives. Label **result set turned over** — the term
re-indexed wholesale and neither reading is about us.

### 3. Entry from a *proven* absence — iOS AU `fruit tree`, absent -> 36

```
baseline: rank=None  result_count=174  (iOS, 174 < LIMIT 200, so absence is proven)
                     -> status=absent
now:      rank=36                      -> status=ranked
```

Reported plainly: **entered at 36 from absent**.

### 4. Entry from an *unproven* absence — Play AU `fruit tree care`, absent -> 1

```
baseline: rank=None  result_count=30  truncated=true  -> status=absent_window_capped
day0:     rank=1     result_count=30  truncated=true  -> status=ranked
```

Identical arrow to example 3, but the "before" is not a measured absence — we may have been at
31. The diff must render this as **entered at 1 (previously outside a capped window, absence was
never proven)**. Collapsing 3 and 4 into one "newly entered" bucket is precisely the DEC-255 error.

### 5. Entry that shifts everyone down — Play AU `fruit tree tracker`, 26 -> 1

```
baseline: rank=26  top3 = [com.zht.fruit_trees, org.greenstand.android.TreeTracker, com.PlayMore.FruitTree]
day0:     rank=1   top3 = [app.treesmith,       com.zht.fruit_trees, org.greenstand.android.TreeTracker]
```

We take slot 1 and the previous top 3 slides down one. `newcomers` empty. The competitive field
did not change; our own matching did. This is DAL-257's first recorded prediction, already met.

### 6. Noise, not movement

Two runs 20 minutes apart already disagreed by one position. The 2026-08-06 ledger measured up to
8 positions of drift in 7 days with the listing untouched. Anything with `|delta| <= 3` renders
as **flat**, and is counted but not listed. Entries and exits are always listed regardless of
magnitude — crossing the ranked/absent boundary is an event, not a drift.

### 7. The primary-key collision the backfill must survive

Two of the three baselines are the same store, same date, same countries, same 36 terms:

```
treesmith-play-rank-baseline.json        Play, 2026-08-13, pre-rename
treesmith-play-rank-day0-postchange.json Play, 2026-08-13, ~1h post-change
```

So `captured_at` must be a full UTC timestamp, not a date, or day 0 overwrites the baseline and we
lose the single most informative pair in the dataset. **None of the three files contains a
timestamp** — provenance is only filename, mtime and the decision log. mtimes do not survive a
clone, so the backfill map hardcodes them, sourced from mtime + git commit time:

| file | captured_at | derivation |
|---|---|---|
| `treesmith-play-rank-baseline.json` | `2026-08-13T01:56:00Z` | mtime 09:56 AWST; commit `feat: Play rank reader...` 10:04 AWST |
| `treesmith-appstore-rank-baseline.json` | `2026-08-13T02:01:00Z` | mtime 10:01 AWST; same commit |
| `treesmith-play-rank-day0-postchange.json` | `2026-08-13T02:55:00Z` | mtime 10:55 AWST; commit `data: Play rename is live...` 10:56 AWST |

## The CSV

`data/treesmith-rank-history.csv`, long format, one row per capture x store x country x term.
72 rows per store-run (2 countries x 36 terms). Header row, `csv` stdlib module.

```
captured_at,store,country,group,term,rank,result_count,truncated,status,name_match_top5,top3_1,top3_2,top3_3,error
2026-08-13T02:01:00Z,appstore,AU,niche_tracker,fruit tree tracker,7,158,false,ranked,0.2,Fruit Tree Tracker - Grove,FruitForest: Orchard Mapping,Fruit Juice Farm,
2026-08-13T01:56:00Z,play,AU,niche_tracker,orchard tracker,,12,false,absent,,com.habadigital.obstgarten,com.theorchard.OrchardGo,com.orchardthieves,
2026-08-13T01:56:00Z,play,US,niche_tracker,fruit tree tracker,,30,true,absent_window_capped,,com.zht.fruit_trees,com.dictionary.fruittrees.fruit.trees,com.PlayMore.FruitTree,
```

- `top3` is store-shaped — `{name, ratings}` dicts on Apple, bare package strings on Play. Three
  flat columns holding the **identifier** (trackName / package id) avoids separator escaping and
  is what the diff joins on. Apple ratings are dropped from the series; they are in the render
  path already and are not needed for movement.
- `name_match_top5` is Apple-only, empty for Play.
- `error` carries the exception text. **Neither reader authenticates** — public iTunes Search and
  the public Play search page, no keys, no secrets — so no credential can reach this column.
  (`config_scan.py` scans only what `snapshot-server-config.sh` captures: crontab, Caddyfile,
  systemd units, compose, ClickHouse XML. `data/` is not in its path, so the fail-closed gate is
  not a control here; the control is that there is nothing to leak.)

## Task 1 — the append-only series

**`tools/autonomous/rank_history.py`** (new). The shared layer both readers call.

- `CSV_COLUMNS` — the header, single source of truth.
- `to_records(store, rows_by_country, captured_at)` — normalises one `measure()` result to CSV
  dicts. Derives `status` from row shape: `error` key present -> `error`; `rank` not None ->
  `ranked`; else `absent_window_capped` if truncated else `absent`. Truncation comes from
  `playstore_rank.saturated()` for Play and `result_count >= appstore_rank.LIMIT` for Apple.
- `append(path, records)` — writes the header only when creating the file, then appends.
- `read(path)` — parses back to typed records (rank/result_count int-or-None, truncated bool-or-None).
- `captures(records, store)` — distinct `captured_at` for a store, newest first.

**`appstore_rank.py`** and **`playstore_rank.py`**: add `--csv PATH` and `--captured-at ISO8601`
to each argparse block. Purely additive — `--json`, `--save`, `--term`, `--country` and both
`render()` paths are untouched. Follow the existing `--save` template: do the work, then confirm
to **stderr** so stdout stays pipeable. `appstore_rank.py` gains no `--save`; out of scope.

`playstore_rank.py` must keep importing `TERMS, all_terms` from `appstore_rank` —
`tests/test_playstore_rank.py::TestSharedTermSet` scans the source and fails on a restated
`^TERMS\s*[:=]`. `rank_history.py` imports `TERMS` for group ordering only, and the same guard
gets extended to cover it.

**Backfill:** `rank_history.py backfill [--write]`. Hardcoded map of the three files to the
timestamps in the table above. Idempotent — skips any `(captured_at, store)` already present, so a
re-run cannot double the series. Dry-run by default.

## Task 2 — the diff

`rank_history.py diff [--store appstore|play] [--against <captured_at>] [--noise 3]`, plus a
`diff_captures(prev, curr, noise=3)` function the digest imports.

**Capture selection is per store**, not global: the two most recent distinct `captured_at` *for
that store*. iOS and Play were baselined 5 minutes apart and Play has an extra day-0 capture, so a
global "last two" would compare Play against Apple. Going forward the wrapper stamps both stores
with one shared `captured_at`, so this is belt-and-braces — but the backfilled rows need it today.
`--against` lets the pre-rename baseline stay reachable in one command once the series is long.

Joins on `(store, country, group, term)` and classifies into four buckets, each sorted by size:

| bucket | rule | sort |
|---|---|---|
| `moved` | both `ranked`, `abs(delta) > noise` | `abs(delta)` desc |
| `entered` | prev absent/capped -> now `ranked` | new rank asc |
| `dropped` | prev `ranked` -> now absent/capped | prev rank asc |
| `flat` | both `ranked`, `abs(delta) <= noise` | counted, not listed |

Rows where either side is `status=error` go to a separate `unmeasured` list and are **never**
folded into a movement — a term that failed to fetch has not moved.

`dropped` and `moved`-downward rows carry the example-1/2 attribution computed from `top3_*`:
`vacated` (no newcomers), `displaced by <names>` (newcomers + survivors), `result set turned over`
(no survivors). A drop into `absent_window_capped` is additionally tagged "absence not proven".

## Task 3 — the digest section

**`tools/autonomous/treesmith_analytics.py`**:

- `m_rank(_host=None, _key=None)` beside `m_revenuecat`, same "external system" template:
  underscore-defaulted args, `sys.path.insert(0, SCRIPT_DIR)` then a deferred `import rank_history`
  inside the function so a missing CSV surfaces through `run_metric` rather than at import time.
  Returns per-store `{prev, curr, moved, entered, dropped, flat_n, unmeasured_n}` plus a top-level
  `stale` flag when the newest capture is older than 10 days.
- Register as `"rank": run_metric(m_rank)` in the `main()` metrics dict.
- A `section("Search rank (ASO)")` in `render()`, placed after Growth and before Activation.
  **Must use `metrics.get("rank")`, not `metrics["rank"]`** — `tests/test_treesmith_analytics_revenue.py`
  builds a hand-written `_metrics()` dict containing every key except `liveness`, and a direct
  index would `KeyError` all 8 of those tests.
- Renders movement, not 36 numbers: top 5 per bucket per store, then counts. When nothing crossed
  the noise band, one line saying so. `stale` renders loudly in `RED` — a stopped cron job must
  read as "no capture", never as "no movement", which is the digest-liveness failure mode.
- The script rejects unknown argv rather than ignoring it; no new flag is added, so nothing to
  update there.

## Task 4 — the cron line (handed over, not installed)

`infrastructure/crontab.txt` is a **recording**, captured server-to-repo by
`snapshot-server-config.sh` Mondays 04:20 UTC. Editing it changes nothing on the box and would
fake an install. **It will not be touched.** The Monday snapshot records the line back into the
repo once Benedict has genuinely installed it.

**`tools/autonomous/capture-treesmith-rank.sh`** (new), modelled directly on
`merge-nursery-inbound.sh`: compute one shared `captured_at`, run both readers with `--csv`, and if
`data/treesmith-rank-history.csv` actually changed, commit and push via `git_sync_push` from
`tools/autonomous/git_sync.sh`. A push failure alerts through `notify.py` with the manual fix, the
way the register merge and the config snapshot both do.

Line for Benedict to install with `crontab -e`:

```
# TreeSmith ASO rank capture -- Sundays 21:40 UTC (05:40 AWST Monday), ahead of the Monday 00:00 digest
40 21 * * 0 /opt/dale/repo/tools/autonomous/capture-treesmith-rank.sh >> /opt/dale/autonomous/logs/treesmith_rank.log 2>&1
```

Why that slot: weekly, because the signal moves over weeks and daily is noise. Sundays, 2h20m
ahead of `treesmith_analytics.py` at Monday 00:00, with margin for a ~5 minute run (72 Play page
fetches at a 1.0s pause dominate). Minute 40, off the top of the hour, so it does not race the
hourly `dale-runner` push at `0 * * * *` — the same reason the config snapshot sits at 04:20.
Nothing else in the crontab occupies the 21:00 hour. Absolute path under `/opt/dale`, UTC, its own
log file under `/opt/dale/autonomous/logs/`, matching the existing conventions.

`tools/deploy.sh` gains one `chmod +x /opt/dale/autonomous/capture-treesmith-rank.sh` line beside
the existing six, so the rsynced copy stays executable. (The cron line targets the
`/opt/dale/repo/...` path — the modern form used by the newer jobs — where git already carries the
exec bit.)

## Task 5 — publish

`data/treesmith-rank-history.csv` is the artefact. It lands in this repo on every run via the
wrapper's commit-and-push, alongside the three baselines that are already committed here. The repo
is public (`bjnoel/dale`), so the admin worker can fetch it at
`https://raw.githubusercontent.com/bjnoel/dale/main/data/treesmith-rank-history.csv` with no
credential and no new endpoint. Stable header, append-only, one row per term per capture. No
worker changes in this task.

**Verified 2026-08-20.** The repo is public and raw.githubusercontent serves it unauthenticated:
`data/nursery-contacts.json` returns HTTP 200 / 31,598 bytes with no credential. The series URL
itself is a 404 until this branch merges, which is the expected before-state and the only part
that cannot be checked from the branch.

**One thing the worker must not copy from itself.** `panels/googleplay.js` parses its Play install
CSVs with a naive `line.split(',')`, and its own comment says that is fine *for those files*. It is
not fine for this one. Apple's top3 identifier is the app name, and app names contain commas:
`Journey - Diary, Journal` is in our real iOS top 3 today, so the file genuinely carries
RFC-quoted cells. A naive split shifts every column after that name and reads a competitor's name
as a rank. Whatever renders this series needs a real CSV parser. Pinned by
`tests/test_rank_history.py::TestAppendOnly::test_a_comma_inside_an_app_name_survives`.

## Files

| file | change |
|---|---|
| `tools/autonomous/rank_history.py` | **new** — CSV schema, writer, reader, backfill, diff, CLI |
| `tools/autonomous/capture-treesmith-rank.sh` | **new** — weekly wrapper, commit + `git_sync_push` |
| `tools/autonomous/appstore_rank.py` | `--csv` / `--captured-at`; nothing existing altered |
| `tools/autonomous/playstore_rank.py` | `--csv` / `--captured-at`; nothing existing altered |
| `tools/autonomous/treesmith_analytics.py` | `m_rank`, metrics-dict entry, `render()` section |
| `tools/deploy.sh` | one `chmod +x` line |
| `data/treesmith-rank-history.csv` | **new** — backfilled 08-13 + a live 08-20 capture |
| `tests/test_rank_history.py` | **new** |
| `tests/test_appstore_rank.py`, `tests/test_playstore_rank.py` | extend for `--csv` + the anti-fork guard |
| `public-ledger/2026-08-20-rank-series.md` | **new** |
| `decisions/decision-log.md` | DEC-306 (append-only) |

**Not touched:** `infrastructure/crontab.txt` (a recording, see Task 4).

## Tests — `tests/test_rank_history.py`

Same house style as the two existing rank tests: stdlib `unittest`, `importlib` load with
registration in `sys.modules`, dependency injection over the `searcher`/`fetcher` seams, no
transport mocking, `pause=0`.

- All four statuses round-trip through write -> read, from hand-built `measure()`-shaped rows.
- An `error` row writes `status=error` with `rank`, `result_count` and `truncated` **all empty**,
  and reads back distinguishable from `absent` (DEC-249).
- `absent` and `absent_window_capped` never compare equal and never render the same (DEC-255).
- Apple truncation derives from `LIMIT`; a `result_count=200` iOS row is `absent_window_capped`,
  a `result_count=174` one is `absent`.
- Header written once; a second `append` adds rows without a second header.
- Backfill is idempotent — running it twice yields the same row count.
- Diff: `abs(delta) <= 3` is flat; 4 is a move; entered/dropped classified correctly from both
  absence kinds; an `error` on either side lands in `unmeasured`, never in `moved`.
- Attribution: no newcomers -> `vacated`; one newcomer + survivors -> `displaced`; no survivors ->
  `turned over`. Built from the real `graft tracker` top3 above.
- Capture selection is per store, proven against a fixture holding Play's two 08-13 captures.
- Anti-fork: `rank_history.py` does not restate `^TERMS\s*[:=]`.

Plus `--csv` flag tests in the two existing files, and a `m_rank` render test confirming the
section survives a metrics dict that has no `"rank"` key.

## Also

- **Linear ticket** (`linear_update.py ask`, `Question` label, Track A): whether the rename was a
  *good* trade cannot be scored without search volume, and neither store exposes it free via API.
  An Apple Search Ads account is free, needs no ad spend to show the Search Popularity index, and
  is an account signup so it needs Benedict. Terms that matter: graft tracker, grafting tracker,
  fruit tree, fruit tree tracker, fruit tree journal, fruit tree care.
- **Ledger** `public-ledger/2026-08-20-rank-series.md` in the `2026-08-06.md` shape. The honest
  note is that the iOS cost is one day old and the series exists precisely because we cannot yet
  score the trade.
- **DEC-306** in `decisions/decision-log.md` (append-only; DEC-305 is current).
- **Commit locally, do not push.**

## Verification

1. `python3 -m unittest discover tests/` from the repo root — full suite, not just the new file.
   (`.venv/bin/python` if `requests` is missing on bare `python3`.)
2. `python3 tools/autonomous/rank_history.py backfill --write` -> CSV has 216 data rows across 3
   captures; re-run -> still 216.
3. Live capture, both stores, one shared `captured_at`, into the same CSV. Confirm 360 rows and
   that `graft tracker` iOS AU shows the 1 -> 11 drop.
4. `python3 tools/autonomous/rank_history.py diff` -> check against the movements already known
   from the manual re-measure: `fruit tree` absent -> 36 (AU) / 26 (US) iOS, `fruit tree journal`
   129 -> 13 (AU) / 37 -> 4 (US), `graft tracker` 1 -> 11 iOS AU classified **vacated** and not
   "displaced", `fruit tree care` 36 -> 111 iOS US. Also check DAL-257's own recorded predictions.
5. `python3 tools/autonomous/treesmith_analytics.py --dry-run` -> the new section renders real
   movement and no email is sent. Then confirm it still renders sanely with the CSV moved aside
   (the `stale` / missing-capture path).
6. `bash -n tools/autonomous/capture-treesmith-rank.sh`, and a dry run with `DALE_REPO` pointed at
   a scratch clone to confirm it commits without pushing anything real.
