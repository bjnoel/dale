#!/usr/bin/env python3
"""
Track how many search queries treestock answers with TWO of its own pages.

The DEC-309 measurement found 414 queries across 27 species returning BOTH
/species/<slug>.html and /compare/<slug>-prices.html, converting at 1.57%,
below both parents. The fix shipped 2026-08-20. This is what tells us whether
it worked, and it exists because a single before-and-after reading could not.

Two things would have made that reading meaningless, and both are handled here:

- **A 90-day window barely moves week to week.** 89 of its 90 days are shared
  with last week's, so a real change shows up as a rounding error for a month.
  Readings are taken over SHORT trailing windows (7 and 28 days by default).
- **One post-change point has nothing to compare against.** `backfill` walks GSC
  history to build a pre-change series, so "it fell" can be checked against how
  much this number moves on its own. Without that, any reading is a story.

The headline is `contested_share`, contested queries over all queries, not the
raw count. Total query volume swings with the season (bare root runs late June
to August, which is exactly the pre-change window), and a raw count would move
with it whether or not anything we did mattered.

Usage:
    contested_queries.py record [--windows 7,28] [--end YYYY-MM-DD]
    contested_queries.py backfill --weeks 16
    contested_queries.py report [--alert-only]
"""

import argparse
import csv
import os
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
from pathlib import Path

# The GSC plumbing already exists and is paginated (a single request silently
# truncates). Import it; tests/test_no_forking.py fails on a second copy.
from gsc_analysis import SITE_URL, get_service, query_gsc

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CSV = REPO_ROOT / "data" / "contested-queries.csv"

# GSC finalises slowly; anything inside this is still filling in.
GSC_LAG_DAYS = 3

# The night the differentiation shipped (DEC-309). Readings whose window ends
# before this are the "before" arm; the split is stored, not guessed at read time.
CHANGE_DATE = "2026-08-20"

# How many of the most recent pre-change readings form the comparison band.
#
# NOT the whole history, and this is the difference between a measurement and a
# decoration. The 2026-08-20 backfill showed the series is strongly
# non-stationary: contested share was 0.00% every week through May, first moved
# on 2026-06-08, and reached ~2% by August. That is not noise, it is the growing
# guides and variety descriptions landing 2026-06-01 to 06-12 and lifting species
# pages into SERPs the compare pages already held.
#
# Over all 16 backfilled weeks the 7d band is -0.94% to 3.50%. A lower bound
# below zero cannot be crossed, so no drop of any size could ever have been
# flagged and the check would have reported "normal" forever. Over the most
# recent 8 it is 1.01% to 3.49%, which a real drop can leave.
BAND_READINGS = 8

FIELDS = [
    "captured_at", "window_days", "start", "end",
    "total_queries", "contested_queries", "contested_share",
    "contested_impressions", "contested_clicks", "contested_ctr",
    "species_better", "compare_better",
]


def is_species(url):
    return "/species/" in url and url.endswith(".html")


def is_compare(url):
    return "/compare/" in url and url.endswith("-prices.html")


def measure(service, start, end):
    """One reading over [start, end]. Every field is derived from one GSC call."""
    rows = query_gsc(service, SITE_URL, start, end, ["query", "page"])
    by_query = defaultdict(list)
    for r in rows:
        by_query[r["keys"][0]].append((r["keys"][1], r["clicks"], r["impressions"],
                                       r["position"]))

    contested = 0
    impressions = clicks = 0
    species_better = compare_better = 0
    for hits in by_query.values():
        sp = [h for h in hits if is_species(h[0])]
        cp = [h for h in hits if is_compare(h[0])]
        if not (sp and cp):
            continue
        contested += 1
        impressions += sum(h[2] for h in hits)
        clicks += sum(h[1] for h in hits)
        # Impression-weighted position, so a page shown once at 3 does not
        # outrank one shown 200 times at 11.
        def wpos(group):
            imp = sum(h[2] for h in group) or 1
            return sum(h[3] * h[2] for h in group) / imp
        if wpos(sp) <= wpos(cp):
            species_better += 1
        else:
            compare_better += 1

    total = len(by_query)
    return {
        "window_days": (date.fromisoformat(end) - date.fromisoformat(start)).days + 1,
        "start": start,
        "end": end,
        "total_queries": total,
        "contested_queries": contested,
        "contested_share": round(contested / total, 6) if total else 0.0,
        "contested_impressions": impressions,
        "contested_clicks": clicks,
        "contested_ctr": round(clicks / impressions, 6) if impressions else 0.0,
        "species_better": species_better,
        "compare_better": compare_better,
    }


def read_series(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def append(path, records):
    """Append-only, header written once. Never rewrites an existing row."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    have = {(r["window_days"], r["end"]) for r in read_series(path)}
    fresh = [r for r in records if (str(r["window_days"]), r["end"]) not in have]
    if not fresh:
        return 0
    with path.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        for r in fresh:
            w.writerow(r)
    return len(fresh)


def latest_end():
    return date.today() - timedelta(days=GSC_LAG_DAYS)


def cmd_record(args):
    service = get_service()
    end = date.fromisoformat(args.end) if args.end else latest_end()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for w in [int(x) for x in args.windows.split(",")]:
        rec = measure(service, str(end - timedelta(days=w - 1)), str(end))
        rec["captured_at"] = stamp
        out.append(rec)
        print(f"{w}d to {end}: {rec['contested_queries']}/{rec['total_queries']} queries "
              f"contested ({rec['contested_share'] * 100:.2f}%), "
              f"CTR {rec['contested_ctr'] * 100:.2f}%")
    n = append(args.csv, out)
    print(f"appended {n} row(s) to {args.csv}", file=sys.stderr)
    return 0


def cmd_backfill(args):
    """Walk back one week at a time to build the pre-change arm.

    Windows overlap between adjacent readings, which is fine: the point is the
    spread of the number, not independent samples.
    """
    service = get_service()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for i in range(args.weeks):
        end = latest_end() - timedelta(days=7 * i)
        for w in [int(x) for x in args.windows.split(",")]:
            rec = measure(service, str(end - timedelta(days=w - 1)), str(end))
            rec["captured_at"] = stamp
            out.append(rec)
            print(f"  {w}d to {end}: {rec['contested_queries']}/{rec['total_queries']} "
                  f"({rec['contested_share'] * 100:.2f}%)")
    n = append(args.csv, out)
    print(f"appended {n} row(s) to {args.csv}", file=sys.stderr)
    return 0


def summarise(series, window):
    """Latest reading against the spread of the pre-change arm.

    Returns None when there is nothing to say yet: no post-change reading, or
    fewer than three before-readings, which is too few to call anything unusual.
    """
    rows = sorted((r for r in series if int(r["window_days"]) == window),
                  key=lambda r: r["end"])
    # Only the most recent BAND_READINGS before the change: the series trends,
    # so the full history describes 2026-05 rather than the state we changed.
    before = [float(r["contested_share"]) for r in rows
              if r["end"] < CHANGE_DATE][-BAND_READINGS:]
    after = [r for r in rows if r["end"] >= CHANGE_DATE]
    if not after or len(before) < 3:
        return None
    latest = after[-1]
    share = float(latest["contested_share"])
    mean = statistics.fmean(before)
    sd = statistics.pstdev(before)
    # Two standard deviations of the page's own week-to-week noise. Anything
    # inside it is the number doing what it always did.
    outside = sd > 0 and abs(share - mean) > 2 * sd
    return {
        "window": window, "end": latest["end"], "share": share,
        "before_mean": mean, "before_sd": sd, "outside": outside,
        "band_low": max(0.0, mean - 2 * sd), "band_high": mean + 2 * sd,
        "direction": "down" if share < mean else "up",
        "n_before": len(before),
        "species_better": int(latest["species_better"]),
        "compare_better": int(latest["compare_better"]),
    }


def describe(s):
    band = (f"pre-change band {s['band_low'] * 100:.2f}% to {s['band_high'] * 100:.2f}% "
            f"(last {s['n_before']} readings before the change)")
    verdict = (f"OUTSIDE the band, {s['direction']}" if s["outside"]
               else "inside normal week-to-week variation")
    return (f"[{s['window']}d to {s['end']}] contested share {s['share'] * 100:.2f}%, "
            f"{band}: {verdict}. "
            f"Of the contested queries, species ranks better on {s['species_better']}, "
            f"compare on {s['compare_better']}.")


def cmd_report(args):
    series = read_series(args.csv)
    if not series:
        print("no readings yet", file=sys.stderr)
        return 1
    said = False
    for w in sorted({int(r["window_days"]) for r in series}):
        s = summarise(series, w)
        if not s:
            continue
        if args.alert_only and not s["outside"]:
            continue
        print(describe(s))
        said = True
    if not said and not args.alert_only:
        print("not enough history to judge yet: need 3+ pre-change readings "
              "and at least one after.")
    # Exit 0 only when something was printed under --alert-only, so a cron can
    # test it and stay silent on a quiet week.
    return 0 if said or not args.alert_only else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", default=os.environ.get("CONTESTED_CSV", str(DEFAULT_CSV)))
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="take today's reading")
    r.add_argument("--windows", default="7,28")
    r.add_argument("--end", default=None, help="window end (default: today minus GSC lag)")
    r.set_defaults(fn=cmd_record)

    b = sub.add_parser("backfill", help="build the pre-change arm from GSC history")
    b.add_argument("--weeks", type=int, default=16)
    b.add_argument("--windows", default="7,28")
    b.set_defaults(fn=cmd_backfill)

    o = sub.add_parser("report", help="latest reading against the pre-change spread")
    o.add_argument("--alert-only", action="store_true",
                   help="print (and exit 0) only when a reading leaves the band")
    o.set_defaults(fn=cmd_report)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
