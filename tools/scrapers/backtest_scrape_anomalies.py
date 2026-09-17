#!/usr/bin/env python3
"""Replay the scrape-health alarm over every night of records we hold (DAL-292).

The alarm's thresholds were all hand-picked and none had ever been scored. This
replays `detect_anomalies` and `detect_panel_coverage` day by day against the
real record sequence, INCLUDING failure days and days where most of the panel
never ran, because that is where the interesting failures were (a rule that
compares against yesterday has a blind spot exactly where yesterday is broken).

There is a labelled ground truth to score against, which there was not when the
ticket was written: DEC-324 identified six nights on which the whole tracked
panel reported one nursery. They are the six worst nights in the dataset and
every one of them must alarm.

Usage:
    python3 backtest_scrape_anomalies.py [health_dir] [--verbose]

Read only. Prints a per-condition table, the firing rate, and the ground-truth
score. Exits 1 if any known outage night fails to alarm.
"""

import collections
import sys
from datetime import date, timedelta
from pathlib import Path

import detect_scrape_anomalies as dsa
from stocklib.scrape_health import default_health_dir, latest_by_nursery, read_records

# DEC-324 / DAL-254. Reconstructing panel size per day across the availability
# history surfaced six nights on which exactly one nursery reported. They are
# labelled here rather than re-derived so the score cannot drift with the rule
# being scored, which is the same reason tests/test_shipping_reachability.py
# pins observed values instead of asserting its constant.
KNOWN_OUTAGE_NIGHTS = (
    "2026-06-24", "2026-06-26", "2026-06-29",
    "2026-06-30", "2026-07-02", "2026-07-03",
)


def available_days(health_dir):
    return sorted(p.stem for p in Path(health_dir).glob("*.jsonl"))


def replay(health_dir):
    """Return {day: [anomalies]} for every day of records held."""
    out = {}
    for day in available_days(health_dir):
        days = [
            read_records((date.fromisoformat(day) - timedelta(days=n)).isoformat(),
                         health_dir)
            for n in range(dsa.STREAK_DAYS)
        ]
        if not days[0]:
            continue
        anomalies = dsa.detect_anomalies(days)
        panel = dsa.detect_panel_coverage(day, days, health_dir)
        if panel:
            anomalies.insert(0, panel)
        out[day] = anomalies
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    positional = [a for a in argv if not a.startswith("--")]
    health_dir = positional[0] if positional else default_health_dir()
    verbose = "--verbose" in argv

    nights = replay(health_dir)
    if not nights:
        print(f"No health records under {health_dir}.")
        return 0

    fired = {d: a for d, a in nights.items() if a}
    days = sorted(nights)
    print(f"Replayed {len(nights)} nights, {days[0]} to {days[-1]}.")
    print(f"Emailed on {len(fired)} of them ({len(fired) / len(nights):.0%}).")

    by_type = collections.Counter()
    nights_by_type = collections.Counter()
    for anomalies in nights.values():
        seen = set()
        for a in anomalies:
            by_type[a["type"]] += 1
            seen.add(a["type"])
        for t in seen:
            nights_by_type[t] += 1

    print(f"\n{'condition':<18} {'rows':>6} {'nights':>7}")
    for t in dsa.CONDITION_LABELS:
        print(f"{t:<18} {by_type[t]:>6} {nights_by_type[t]:>7}"
              + ("   (never fired)" if not by_type[t] else ""))

    # Rows that say something about a nursery already reported failed the same
    # night. This is the number that made the alarm feel noisy: it is volume
    # without information.
    dup = 0
    for anomalies in nights.values():
        failed = {a["nursery"] for a in anomalies if a["type"] == "failed"}
        dup += sum(1 for a in anomalies
                   if a["type"] not in ("failed", "panel_coverage")
                   and a["nursery"] in failed)
    total = sum(by_type.values())
    if total:
        print(f"\nRows about a nursery already reported failed the same night: "
              f"{dup} of {total} ({dup / total:.0%}).")

    print("\nGround truth (DEC-324), six nights the whole panel collapsed:")
    misses = []
    for night in KNOWN_OUTAGE_NIGHTS:
        anomalies = nights.get(night)
        if anomalies is None:
            print(f"  {night}  no records held, cannot score")
            continue
        panel = next((a for a in anomalies if a["type"] == "panel_coverage"), None)
        if panel:
            print(f"  {night}  ALARMED as an outage: {panel['detail']}")
        else:
            misses.append(night)
            print(f"  {night}  MISSED as an outage "
                  f"({len(anomalies)} ordinary anomalies, reads as a routine night)")

    if verbose:
        print("\nEvery night that fired:")
        for day in days:
            if nights[day]:
                print(f"  {day}: " + "; ".join(
                    f"{a['nursery']}/{a['type']}" for a in nights[day]))

    if misses:
        print(f"\nFAIL: {len(misses)} known outage nights did not alarm as outages.")
        return 1
    print("\nOK: every known outage night alarms as an outage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
