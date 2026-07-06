"""
Tests for tools/scrapers/build_species_trends.py -- the /trends.html market
trends page.

Focus: the nursery-coverage guard (usable_dates / nursery_coverage). Regression
for the 2026-07-04 disk-full incident, which left six days with a single nursery
snapshot and made every species' sparkline draw the same phantom crash-and-recover
sawtooth. Days far below the window's typical coverage must be dropped so the trend
plots real data only.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


trends = _load(SCRAPERS / "build_species_trends.py")


class UsableDatesTests(unittest.TestCase):
    def test_drops_the_incident_days(self):
        # The real 2026-07-04 damage: 6 single-nursery days among ~22-nursery days.
        good = ["2026-06-21", "2026-06-22", "2026-06-23", "2026-06-25",
                "2026-06-27", "2026-06-28", "2026-07-01", "2026-07-04",
                "2026-07-05", "2026-07-06"]
        bad = ["2026-06-24", "2026-06-26", "2026-06-29", "2026-06-30",
               "2026-07-02", "2026-07-03"]
        dates = sorted(good + bad)
        coverage = {d: (1 if d in bad else 22) for d in dates}
        kept = trends.usable_dates(dates, coverage)
        self.assertEqual(kept, good)
        for d in bad:
            self.assertNotIn(d, kept)

    def test_keeps_a_modest_dip(self):
        # A real day where a few nurseries just did not scrape (15/22) is NOT a
        # broken day -- only clearly-broken days (< half the median) are dropped.
        dates = ["2026-07-01", "2026-07-02", "2026-07-03"]
        coverage = {"2026-07-01": 22, "2026-07-02": 15, "2026-07-03": 21}
        self.assertEqual(trends.usable_dates(dates, coverage), dates)

    def test_uniform_small_coverage_all_kept(self):
        # The golden fixture / any consistent small dataset: median == coverage,
        # threshold == median/2, everything passes. The guard never empties a
        # window that is merely small.
        dates = ["2026-07-04", "2026-07-05", "2026-07-06"]
        coverage = {d: 2 for d in dates}
        self.assertEqual(trends.usable_dates(dates, coverage), dates)

    def test_empty_coverage_is_passthrough(self):
        dates = ["2026-07-05", "2026-07-06"]
        self.assertEqual(trends.usable_dates(dates, {}), dates)
        self.assertEqual(trends.usable_dates([], {}), [])


class NurseryCoverageTests(unittest.TestCase):
    def test_counts_files_per_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            # Two nurseries scrape both days; a third only scrapes one day.
            for nursery, days in {
                "daleys": ["2026-07-05", "2026-07-06"],
                "ross-creek": ["2026-07-05", "2026-07-06"],
                "primal-fruits": ["2026-07-06"],
            }.items():
                nd = data / nursery
                nd.mkdir()
                for d in days:
                    (nd / f"{d}.json").write_text(json.dumps({"products": []}))
            # A stray non-directory should be ignored.
            (data / "latest.json").write_text("{}")
            cov = trends.nursery_coverage(data, ["2026-07-05", "2026-07-06"])
            self.assertEqual(cov, {"2026-07-05": 2, "2026-07-06": 3})


if __name__ == "__main__":
    unittest.main()
