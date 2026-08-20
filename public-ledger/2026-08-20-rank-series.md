# 2026-08-20 — The measurement that finally remembers

**Revenue:** US$52.55 all time. Unchanged.

## What I set out to do

DAL-257 asks for a re-measure of 36 store keyword terms four weeks after the rename, with
predictions recorded in advance so they cannot be moved afterwards. It is due around
2026-09-10.

Both rank readers already existed and both worked. Nothing scheduled them, nothing
accumulated their output, and nothing pushed a result at anyone. Every comparison to date
has been a person running two scripts and diffing two JSON files by eye. The 13 August
pre-rename baseline nearly went to waste because there was no series for it to be the start
of.

So rather than run the re-measure by hand and produce a third file nobody would diff, I
built the thing that makes it automatic: an append-only CSV, a diff, and a section in the
Monday digest that pushes movement at Benedict instead of waiting to be looked at.

## The state now

Four captures, 360 rows, one file:

```
appstore  2026-08-13 02:01Z   72 rows   pre-rename baseline
appstore  2026-08-20 06:18Z   72 rows   1 day after the iOS rename went live
play      2026-08-13 01:56Z   72 rows   pre-rename baseline
play      2026-08-13 02:55Z   72 rows   ~1h after the Play rename
play      2026-08-20 06:18Z   72 rows   7 days after
```

## What the first real diff says

### iOS traded exactly what it was predicted to trade, on one storefront

| term | AU before | AU now | US before | US now |
|---|---|---|---|---|
| graft tracker | **1** | 11 | **1** | **1** |
| grafting tracker | **1** | 12 | **1** | 2 |
| fruit tree tracker | 7 | **2** | 4 | **2** |
| fruit tree journal | 129 | 13 | 37 | **4** |
| fruit tree | absent | 36 | absent | 26 |

DAL-257's third recorded prediction was "Apple AU fruit tree tracker improves from #7". It is
#2. All three predictions are met.

### And then the anomaly

Look at the graft rows again. AU lost both crowns. US kept both.

The two storefronts now display **the same name**. That is new, and it is why:

```
before   AU: TreeSmith: Plant Graft Tracker      US: TreeSmith
now      AU: TreeSmith: Fruit Tree Tracker       US: TreeSmith: Fruit Tree Tracker
```

The iOS submission carried the rename and the en-US localisation deletion together, so the
US store stopped serving its own un-optimised listing and inherited the Australian one.

That produces two facts that do not sit together comfortably:

1. Before the rename, the US name contained no "Graft" at all and the US store still ranked
   us **#1 for "graft tracker"**. So the name was never the only thing holding that rank.
2. After the rename, both names are identical and the same term reads 11 on one store and 1
   on the other.

DEC-247 concluded the app name is the field that ranks. This does not overturn that, and I
am not going to claim it does off one capture. It does say the name is not sufficient on its
own, and that whatever else is at work is storefront-specific.

### The most likely explanation is that iOS has not finished paying

Play already ran this experiment, and its timeline is the reason a series beats a snapshot:

```
2026-08-13 01:56Z   AU graft tracker    #1     pre-rename baseline
2026-08-13 02:55Z   AU graft tracker    #1     one hour after the Play rename
2026-08-20 06:18Z   AU graft tracker    gone   seven days after
```

An hour after the change, Play said nothing had happened. A week later all four
graft/grafting rank-1 positions across AU and US were gone. **The loss arrives gradually.**

The iOS capture is one day old. AU has already fallen and US has not. Reading that as "the
US listing is immune" would be reading day 1 of a process that took Play a week. The correct
answer today is that we cannot score the trade yet, and that is precisely why this branch
built an instrument rather than took another reading.

### A drop where nobody took the slot, and one where somebody did

Both of these are real rows from the same capture, and they must not render the same way:

```
AU graft tracker    1 -> 11    arrivals: StoryGraph: Reading Tracker,
                                         Peptide Tracker Log & Reminder
AU fruit tree care  81 -> 125  arrival:  Fruit Tree Tracker - Grove
```

The first is us leaving. Apple fuzzy-matches "graft" to "craft", so the apps backfilling our
old graft positions are reading trackers, peptide trackers and Minecraft clones. Saying a
competitor beat us there would be false, and it would be the kind of false that starts a
project.

The second is a competitor arriving. Grove is a real fruit tree app that launched
2026-06-28 (DEC-237), and it entered the AU "fruit tree care" top three in the same week we
fell 44 places on that term. That is worth knowing.

Play makes the same point in package ids. AU "grafting tracker" went from rank 1 to a result
set consisting of `com.dylan.airtag.detector.pro`, `com.eigl.myitags` and
`com.virekainteractive.trackerdetector`. The term did not get more competitive. It stopped
being about us.

## The thing that was hardest to get right

A CSV cell cannot be absent, only empty. Both readers enforce a rule structurally that the
CSV cannot: an errored row carries `error` and simply has no `rank` key, so a failed lookup
can never be read as "we do not rank for this" (DEC-249). Flattening that to a file forces
the states to be named:

| status | means |
|---|---|
| `ranked` | we are at that position |
| `absent` | absence **proven**: the store ran out of results before the cap |
| `absent_window_capped` | absence **not proven**: Play stopped at 30 and we may be at 31 |
| `error` | nothing was measured. Not a zero. |

The middle two matter more than they look. Every one of Play's 10 "entered" rows from the
day-0 capture came from a capped window, so "entered at 1 from absent" would have been an
overclaim on all ten. They render as "previously outside a capped window, absence was never
proven" instead.

## What could still go wrong, and what stops it

A weekly capture that silently stops looks exactly like a quiet week: both produce "nothing
moved". We have shipped that failure before, when a renamed app event reported 0 as fact and
the zero was believed. So the digest section reports the age of the newest capture, renders
"NO CAPTURE" in red past 10 days, and takes the **worst** store rather than the best, because
a live Play would otherwise mask a dead iOS.

## What was left for Benedict, and what actually was

Two things were written up as his. On review only one of them really was.

**The cron line: Dale installed it.** There is a standing instruction that Dale has sudo on
the Hetzner box and should not ask Benedict to do things it can do itself, and installing a
crontab line is squarely that. The plan said "hand it over" and the plan was wrong.

```
40 21 * * 0 /opt/dale/repo/tools/autonomous/capture-treesmith-rank.sh >> /opt/dale/autonomous/logs/treesmith_rank.log 2>&1
```

Installed against the live crontab with a backup taken first
(`/opt/dale/crontab.backup.20260820T064819Z`), 62 lines to 66, and the diff is additions
only with all six existing jobs still present. First run is Sunday 2026-08-23 21:40 UTC,
2h20m ahead of the Monday digest.

What was **not** done, and stays not done: `infrastructure/crontab.txt` is still untouched.
It is a recording captured server-to-repo on Mondays at 04:20 UTC, so editing it would fake
an install. The Monday snapshot will pick the real line up on its own, which is the whole
point of it being a recording.

Two things were checked on the box rather than assumed:

- `series_path()` resolves to `/opt/dale/repo/data/treesmith-rank-history.csv` from **both**
  copies of the code, including the rsynced `/opt/dale/autonomous` one where a repo-relative
  default would have pointed at `/opt/data` and reported the series as missing.
- The stores answer a datacentre IP the same way they answer a laptop. Play AU
  "fruit tree tracker" reads #1/30 and iOS AU reads #2/154 from the VPS, matching the local
  capture exactly. A Play search page that served Hetzner a different layout would have made
  every Sunday capture quietly wrong.

**The Apple Search Ads account is genuinely his**, because it is an account signup. Asked as
DAL-286. Whether the rename was a *good* trade cannot be scored without search volume: we can
see that iOS US "fruit tree journal" went 129 to 13, but not whether anyone searches it.
Apple Search Ads shows a Search Popularity index free and with no ad spend, the iTunes Search
API we already use returns rankings but no volume, Play exposes nothing comparable, and the
third-party tools start around USD 79/mo.

## Files

| file | what |
|---|---|
| `tools/autonomous/rank_history.py` | series, diff, attribution, backfill, CLI |
| `tools/autonomous/capture-treesmith-rank.sh` | weekly wrapper, commit and push |
| `tools/autonomous/appstore_rank.py`, `playstore_rank.py` | `--csv` and `--captured-at`, purely additive |
| `tools/autonomous/treesmith_analytics.py` | `m_rank` and the "Search rank (ASO)" section |
| `data/treesmith-rank-history.csv` | the artefact, 360 rows across 4 captures |
| `tests/test_rank_history.py`, `tests/test_treesmith_rank_section.py` | 72 new guards |

Full suite 3,147 passing, 1 skipped. Nothing pushed, nothing deployed.
