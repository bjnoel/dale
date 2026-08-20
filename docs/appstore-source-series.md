# App Store discovery source series (search vs browse)

`tools/autonomous/appstore_sources.py` pulls the App Store Discovery and Engagement report from
the App Store Connect Analytics API, aggregates impressions by `Source Type`, splits on the iOS
rename date, and appends to a series the Monday digest reads.

## Context

The rename went live on Play 2026-08-13 and on iOS with 1.0.10 on 2026-08-19 13:13 UTC:

| | before | after |
|---|---|---|
| App Store name | TreeSmith: Plant Graft Tracker | **TreeSmith: Fruit Tree Tracker** |

Confirmed live from the API on 2026-08-20: `6761506742 | TreeSmith: Fruit Tree Tracker | app.treesmith`.

`appstore_rank.py` and `rank_history.py` (DAL-257, DEC-306) can already score the rank half of
DEC-247's theory. They found iOS AU lost both graft crowns (1 -> 11, 1 -> 12) while iOS US kept
them. What none of that can say is whether anybody was looking. A rank is a position in a list.
This series is the denominator: how many impressions arrived, and what share of them came through
App Store **search** rather than **browse**.

That share is what the whole ASO programme is scored against. If browse supplies most of our
impressions, keyword rank is not our lever however well we rank, and we should say so.

## What the API does and does not have

Enumerated against the live API on 2026-08-20 and re-confirmed by `--list-reports`. The entire
`APP_STORE_ENGAGEMENT` category is five reports:

```
r14-<request>    App Store Discovery and Engagement Standard
r15-<request>    App Store Discovery and Engagement Detailed
r179-<request>   App Store Web Preview Engagement Standard
r180-<request>   App Store Web Preview Engagement Detailed
r320-<request>   Retention Messaging
```

**There is no per-search-term report.** Claims that Apple's July 2026 per-search-term metrics are
API-exportable refer to the App Store Connect web UI. `Source Type` is as close as the API gets,
and it is the thing to pull. Do not go looking for a search-term report.

Report ids are **scoped to the request that created them**. `r15-<request-uuid>` is only valid for
that request, so the script stores the REQUEST id and the report NAME in config and rediscovers the
id on every run. A hardcoded id would keep working right up until a second request exists, and then
read a report that no longer does.

## Worked examples — what actually lands in the Monday email

### 1. The state today: not ready, and that is not zero

Run live on 2026-08-20, roughly six hours after the request was created:

```
$ appstore_sources.py --dry-run
NOT READY: no DAILY instances for report r15-... yet. Apple takes roughly 24-48h to
generate a snapshot; a ONE_TIME_SNAPSHOT then stops producing new ones. This is not
zero traffic.
Nothing written. This is not zero traffic.
EXIT=0
```

Exit 0, nothing written, no email alarm. An empty instances list raises `NotReady` rather than
returning an empty list, because every caller of that function is about to sum something and an
empty sum is zero. Summed as zero, this would say the rename killed our impressions.

### 2. A pull on 2026-08-24: baseline, deliberately with no comparison

The digest section, rendered by the real code (impression counts below are illustrative — Apple
has not generated the snapshot yet):

```
App Store discovery (search vs browse)
--------------------------------------
  Data through               2026-08-21 (the last 3 days excluded as incomplete, so this is never a drop)
  No post-rename window yet  the iOS listing changed 2026-08-19 and no later day is complete. Below is the PRE-RENAME BASELINE, not a result.
  Search share of impressions 17.9% across 17 days (2026-08-01 to 2026-08-17)
    App Store browse       10,370 impressions (78.2%)
    App Store search        2,380 impressions (17.9%)
    Web referrer              510 impressions (3.8%)
    2026-08-19 is part one listing and part the other; its 770 impressions are in neither window.
```

Three things are doing work here:

- **No delta is rendered at all.** Two partial post-rename days against seventeen pre-rename days
  would read as the rename's result. The section says BASELINE and shows one number.
- **2026-08-19 is in neither window.** 1.0.10 went live at 13:13 UTC, so the day is part one
  listing and part the other. Assigning it to either side would flatter or damn the rename by
  accident, so it gets its own line.
- **"Data through" is stated, and the reason is stated.** The series stops three days short on
  every single pull. Without that line, every week ends on a cliff that looks like a collapse.

### 3. A pull on 2026-09-14: the comparison that is actually worth reading

```
App Store discovery (search vs browse)
--------------------------------------
  Data through               2026-09-11 (the last 3 days excluded as incomplete, so this is never a drop)
  Search share of impressions 17.9% -> 30.3% (+12.4 points)
  Impressions (pre / post)   13,260 over 17d  ->  19,396 over 22d
    App Store browse       12,930 impressions (66.7%)
    App Store search        5,870 impressions (30.3%)
    Web referrer              596 impressions (3.1%)
```

Green when search share grows, red when it falls, because search share is the metric the rename was
supposed to move.

### 4. The case that goes wrong: the job stops and the numbers keep looking fine

This is the failure mode that matters most here, and it is **expected rather than hypothetical**.
The existing request is `ONE_TIME_SNAPSHOT`, which by Apple's documentation is one-time: it
produces its history and then stops. The weekly cron would go on reading the same frozen instance
forever, and a frozen search share is indistinguishable from a stable one.

```
App Store discovery (search vs browse)
--------------------------------------
  !! NO PULL                 the App Store Connect series was last written 38 days ago; the weekly job may have stopped, or the ONE_TIME_SNAPSHOT has stopped producing instances. Figures below are older news.
  Data through               2026-09-11 ...
  Search share of impressions 17.9% -> 30.3% (+12.4 points)
```

The figures still print, because deleting them would lose information, but nothing below the NO
PULL line is this week's news and the section says so. Same rule as the rank section's stale flag,
and the same underlying failure as the renamed PostHog event that reported 0 as fact for eleven
days.

**To keep the series moving, an ONGOING request is needed.** Apple: ONGOING "generates reports on a
recurring basis (daily, weekly, and monthly)", ONE_TIME_SNAPSHOT returns "all historical data" once.
As of 2026-08-20 the account has exactly one request and it is the snapshot. Creating an ONGOING one
is a `POST /v1/analyticsReportRequests` against Benedict's Apple account, so it has not been done
here. Once it exists, point `ASC_REQUEST_ID` at it — the report is found by name, so nothing else
changes.

## The two timing rules

**Completeness.** Apple publishes the lag twice and not identically:

> "Data for a given day is considered complete two days after the reporting date."
> — Analytics reports API help page

> "Completeness: Within three days."
> — the App Store Discovery and Engagement report page

`INCOMPLETE_TAIL_DAYS = 3` satisfies both. It also matches the observed consequence: the first
complete post-rename day (2026-08-20) becomes readable on 2026-08-23, which is when a post-rename
window first exists at all.

**Restatement.** Apple splits late-arriving events and corrections into extra batches, so a day
legitimately changes after we first read it. The series carries `pulled_at` on every row and the
newest observation of a `(date, source_type)` wins. Older rows stay in the file as the record of
what we believed at the time. A day already recorded as `complete` is never re-appended, which is
what keeps the file from growing by ~600 identical rows a year.

## Standard vs Detailed

`Source Type` is in **both** reports. The fields unique to Detailed are Page Title, Source Info and
Campaign, none of which this reads. Apple's own guidance:

> "Download the standard report unless you need to analyze the unique fields in the detailed
> report."

Detailed carries extra privacy measures, and at TreeSmith's volume (43 MAU) those could suppress
rows we need. Detailed is the default here because it is the report the existing request was built
around. Switching is one line in `appstoreconnect.env`, and `--list-reports` prints the id to
switch to. If the Detailed pull comes back sparser than the app's own PostHog numbers suggest it
should, try Standard before concluding anything about traffic.

## Config, and why nothing is committed

This repo is public, and `snapshot-server-config.sh` runs `config_scan.py`, which aborts the whole
weekly run on a single literal credential. So: **no key material and no key ids in anything
committed**, here or in the module. Everything comes from the environment, with
`/opt/dale/secrets/appstoreconnect.env` as the file behind it, following `posthog.env`,
`revenuecat.env` and `lodgify.env`. Real environment variables win over the file, so a local run
needs no secrets directory at all.

```
ASC_KEY_ID            App Store Connect API key id
ASC_ISSUER_ID         issuer id (per team, so it matches the treesmith-app Fastfile deploy key)
ASC_PRIVATE_KEY_PATH  path to the PKCS#8 .p8, mode 600, owned by the cron user
ASC_REQUEST_ID        the analyticsReportRequests record to read
ASC_REPORT_NAME       optional, defaults to the Detailed report
ASC_GRANULARITY       optional, DAILY (default) / WEEKLY / MONTHLY
ASC_SERIES_PATH       optional, overrides where the series is written
```

`tests/test_appstore_sources.py::TestConfig::test_no_credential_is_hardcoded_in_the_module` is the
standing check that this stays true.

## Where the series lives, and why not in git

`/opt/dale/data/treesmith-appstore-sources.csv` on the box, the repo's `data/` directory locally
(gitignored). **Deliberately not committed**, unlike the rank series.

The two are not the same kind of artefact. `data/treesmith-rank-history.csv` records iTunes search
results, which no API will ever hand back — if we lose it, that history is gone. This is a cache of
a report Apple holds for us back to 2024-01-01 and will regenerate on request. Committing it would
leave `/opt/dale/repo`'s working tree dirty every week, which breaks the next autonomous session's
pull, in exchange for a recovery path we already have. `weekly_backup.sh` covers `/opt/dale/data`,
and Hetzner's snapshots cover the volume.

That is also why this job needs no commit-and-push wrapper and no `git_sync.sh`: cron calls the
Python directly, the way `resend_report.py` and `gsc_analysis.py` do.

## The cron line (handed over, not installed)

`infrastructure/crontab.txt` is a **recording**, captured server-to-repo by
`snapshot-server-config.sh` Mondays 04:20 UTC. Editing it changes nothing on the box and would fake
an install. **It has not been touched.** The Monday snapshot records the line back into the repo
once Benedict has genuinely installed it.

```
# TreeSmith App Store source split -- Sundays 22:40 UTC (06:40 AWST Monday), ahead of the Monday 00:00 digest
40 22 * * 0 /usr/bin/python3 /opt/dale/repo/tools/autonomous/appstore_sources.py >> /opt/dale/autonomous/logs/appstore_sources.log 2>&1
```

Why that slot: **weekly**, because the underlying data only completes every two to three days and
the signal moves over weeks. **Sundays 22:40 UTC**, which is 1h20m ahead of `treesmith_analytics.py`
at Monday 00:00, so the digest reads a series written the same night. After the 22:00 daily digest
and before the 23:00 weekly stock digest; nothing else occupies 22:40. **Minute 40, off the top of
the hour**, so it does not race the hourly `dale-runner` push at `0 * * * *` — the same reason the
config snapshot sits at 04:20 and the rank capture at 21:40. Absolute path under `/opt/dale`, UTC,
its own log under `/opt/dale/autonomous/logs/`, matching the existing conventions.

It sits one hour after the DAL-257 rank capture, which is **already installed** on the box at
Sundays 21:40 UTC (verified 2026-08-20). That is the right order: the rank capture measures where we
sit, this measures whether anybody was looking, and the Monday digest at 00:00 renders them as
adjacent sections.

### Dependencies — checked, nothing to install

Verified on the box on 2026-08-20, against the interpreter cron actually invokes:

```
$ /usr/bin/python3 -c "import jwt, cryptography; print(jwt.__version__, cryptography.__version__)"
2.7.0 41.0.7
```

Both already present, so there is no install step. If that ever changes, install with **apt, not
pip**: the VPS is an externally-managed environment (PEP 668) and `requirements.txt` says so.

```
sudo apt install python3-jwt python3-cryptography
```

`requests` is not needed. Every module in `tools/autonomous/` uses `urllib`, and this one does too.

### The one thing Benedict has to do by hand

The `.p8` exists only on Benedict's Mac and cannot be re-downloaded from Apple once created, so it
is copied by hand rather than by any script here:

```
scp ~/.appstoreconnect/private_keys/API_TreeSmith_Analytics_AuthKey_<KEYID>.p8 \
    dale-server:/opt/dale/secrets/appstoreconnect.p8
ssh dale-server 'chmod 600 /opt/dale/secrets/appstoreconnect.p8 && \
                 chown dale:dale /opt/dale/secrets/appstoreconnect.p8'
```

`dale` is the cron user, and every other file in `/opt/dale/secrets/` is `dale:dale` mode 600.
Then the env file beside it, same mode, with the real values in place of the placeholders. The key
id and issuer id are deliberately not written down in this repo.

## Files

| file | what |
|---|---|
| `tools/autonomous/appstore_sources.py` | the puller: JWT, discovery, TSV parse, aggregate, split, series |
| `tools/autonomous/treesmith_analytics.py` | `m_appstore_sources` + the "App Store discovery" section |
| `tests/test_appstore_sources.py` | 39 tests, no network |
| `tests/test_treesmith_sources_section.py` | 11 tests on the digest section |
| `requirements.txt` | pyjwt, cryptography (apt on the VPS, not pip) |
| `/opt/dale/data/treesmith-appstore-sources.csv` | the series, not in git |

## The series format

One row per pull x day x source type, append-only, stable header:

```
pulled_at, date, source_type, impressions, impressions_unique,
page_views, page_views_unique, taps, taps_unique, complete
```

`complete` is whether the date was final at `pulled_at`, so the file records not just the numbers
but which of them Apple had finished counting. Territory, Page Title, Source Info, Campaign, Device
and Platform Version are all dropped: they would multiply every day by ~20 rows forever to answer a
question we are not asking weekly, and the source is re-fetchable.

## The general rule, now that the examples have made it concrete

Three states must never look alike, and each of them would otherwise render as a number:

| state | what it means | what it must never render as |
|---|---|---|
| no instances | Apple has not generated the snapshot | zero impressions |
| the trailing 3 days | Apple has not finished counting | a decline |
| no complete post-rename day | too early to score the rename | a result |

Same lineage as DEC-249 (an absence of measurement and a measured zero must not look alike) and
DEC-255 (the denominator has to reach the reader). The tests pin all three, plus a fourth: a
renamed TSV column raises and names the header it actually got, rather than defaulting to zero and
producing a clean-looking series of nothing.
