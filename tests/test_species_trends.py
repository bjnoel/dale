"""
Wiring test for tools/scrapers/build_species_trends.py -- the /trends.html page.

The coverage guard itself (drop broken/partial scrape days) is tested in
tests/test_coverage.py; here we only assert the trends builder actually imports
and exposes that shared guard (it must not re-implement or bypass it), so the
2026-07-04 incident's single-nursery days stay off the sparklines.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib import coverage as stock_coverage


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


trends = _load(SCRAPERS / "build_species_trends.py")


class TrendsUsesSharedGuardTests(unittest.TestCase):
    def test_reexports_the_stocklib_guard(self):
        # Same function objects, not a re-implemented fork.
        self.assertIs(trends.usable_dates, stock_coverage.usable_dates)
        self.assertIs(trends.nursery_coverage, stock_coverage.nursery_coverage)

    def test_incident_days_are_dropped(self):
        good = ["2026-07-01", "2026-07-04", "2026-07-05", "2026-07-06"]
        bad = ["2026-07-02", "2026-07-03"]
        dates = sorted(good + bad, reverse=True)
        coverage = {d: (1 if d in bad else 22) for d in dates}
        kept = trends.usable_dates(dates, coverage)
        self.assertEqual(sorted(kept), sorted(good))


if __name__ == "__main__":
    unittest.main()
