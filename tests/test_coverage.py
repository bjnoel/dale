"""
Tests for stocklib/coverage.py -- the snapshot-coverage guard that drops
broken/partial scrape days from the trends and history pages.

The guard is deliberately LOCAL (compares a day to its neighbours) rather than
global, because the site grew from 8 nurseries (March 2026) to ~25. The key
regression here is the full-history case: a global-median guard would wrongly
drop the legitimate low-coverage early days; the local guard must keep them and
drop only the days that collapse relative to their neighbours (the 2026-07-04
disk-full incident's single-nursery days).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib.coverage import nursery_coverage, usable_dates


class UsableDatesTests(unittest.TestCase):
    def test_drops_the_incident_days(self):
        # Six single-nursery days (the 2026-07-04 damage) among ~22-nursery days.
        good = ["2026-06-21", "2026-06-22", "2026-06-23", "2026-06-25",
                "2026-06-27", "2026-06-28", "2026-07-01", "2026-07-04",
                "2026-07-05", "2026-07-06"]
        bad = ["2026-06-24", "2026-06-26", "2026-06-29", "2026-06-30",
               "2026-07-02", "2026-07-03"]
        dates = sorted(good + bad, reverse=True)  # newest first, as the builders pass
        coverage = {d: (1 if d in bad else 22) for d in dates}
        kept = usable_dates(dates, coverage)
        self.assertEqual(sorted(kept), sorted(good))
        for d in bad:
            self.assertNotIn(d, kept)

    def test_keeps_legitimate_early_low_coverage_ramp(self):
        # THE regression that motivates a local (not global) guard. Coverage ramps
        # 8 -> 25 as nurseries onboard, then one day collapses to 1. A global-median
        # guard (median ~19, threshold ~9.5) would wrongly drop every 8-coverage
        # early day. The local guard must keep the whole ramp and drop only the
        # collapsed day.
        ramp = [8, 8, 8, 9, 10, 12, 15, 18, 19, 19, 19, 22, 22, 25, 25]
        dates = [f"2026-03-{i + 1:02d}" for i in range(len(ramp))]
        # Inject a single collapsed day in the middle of the healthy tail.
        collapse_idx = 12  # coverage would be 22; make it 1
        coverage = {d: c for d, c in zip(dates, ramp)}
        collapsed_day = dates[collapse_idx]
        coverage[collapsed_day] = 1
        kept = usable_dates(dates, coverage)
        self.assertNotIn(collapsed_day, kept)
        for d in dates:
            if d != collapsed_day:
                self.assertIn(d, kept, f"legitimate day {d} (cov {coverage[d]}) was dropped")

    def test_keeps_a_modest_dip(self):
        # A day where a few nurseries just did not scrape is not a broken day.
        dates = ["2026-07-03", "2026-07-02", "2026-07-01"]
        coverage = {"2026-07-01": 22, "2026-07-02": 15, "2026-07-03": 21}
        self.assertEqual(set(usable_dates(dates, coverage)), set(dates))

    def test_uniform_small_dataset_all_kept(self):
        dates = ["2026-07-06", "2026-07-05", "2026-07-04"]
        coverage = {d: 2 for d in dates}
        self.assertEqual(usable_dates(dates, coverage), dates)

    def test_empty_and_zero_coverage_passthrough(self):
        self.assertEqual(usable_dates(["2026-07-06", "2026-07-05"], {}), ["2026-07-06", "2026-07-05"])
        self.assertEqual(usable_dates([], {}), [])

    def test_order_is_preserved(self):
        dates = ["2026-07-06", "2026-07-05", "2026-07-04"]
        coverage = {d: 20 for d in dates}
        self.assertEqual(usable_dates(dates, coverage), dates)


class NurseryCoverageTests(unittest.TestCase):
    def test_counts_files_per_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            for nursery, days in {
                "daleys": ["2026-07-05", "2026-07-06"],
                "ross-creek": ["2026-07-05", "2026-07-06"],
                "primal-fruits": ["2026-07-06"],
            }.items():
                nd = data / nursery
                nd.mkdir()
                for d in days:
                    (nd / f"{d}.json").write_text(json.dumps({"products": []}))
            (data / "latest.json").write_text("{}")  # non-directory: ignored
            cov = nursery_coverage(data, ["2026-07-05", "2026-07-06"])
            self.assertEqual(cov, {"2026-07-05": 2, "2026-07-06": 3})


if __name__ == "__main__":
    unittest.main()
