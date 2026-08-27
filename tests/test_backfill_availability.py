"""
Regression tests for backfill_availability's snapshot file filter.

The rebuild is the repair tool for a contaminated availability history, so it
has to be safe to run against a real nursery directory. It was not: it treated
every *.json that was not latest.json or availability.json as a dated
snapshot, and daleys/catalogue.json (products keyed by id, not a list) raised

    AttributeError: 'str' object has no attribute 'get'

part-way through a real rebuild on 2026-08-27, after three nurseries had
already been overwritten. A partial rebuild is the one outcome a repair tool
must not have.

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

import backfill_availability as bf  # noqa: E402

URL = "https://www.daleysfruit.com.au/buy/jaboticaba.htm"


def _snapshot(day, available=True):
    return {
        "nursery": "daleys",
        "nursery_name": "Daleys Fruit Tree Nursery",
        "scraped_at": f"{day}T00:05:00",
        "products": [{
            "title": "Jaboticaba",
            "url": URL,
            "variants": [{"title": "Small", "available": available,
                          "price": 49.0}],
        }],
    }


class SnapshotFilterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "daleys"
        self.dir.mkdir()
        for day in ("2026-08-25", "2026-08-26", "2026-08-27"):
            (self.dir / f"{day}.json").write_text(json.dumps(_snapshot(day)))
        (self.dir / "latest.json").write_text(json.dumps(_snapshot("2026-08-27")))

    def tearDown(self):
        self._tmp.cleanup()

    def _days(self):
        h = json.loads((self.dir / "availability.json").read_text())
        (prod,) = h["products"].values()
        return sorted(prod["days"])

    def test_rebuilds_from_dated_snapshots(self):
        bf.backfill_nursery(self.dir)
        self.assertEqual(self._days(),
                         ["2026-08-25", "2026-08-26", "2026-08-27"])

    def test_catalogue_json_is_not_a_snapshot(self):
        """The real shape that broke it: products is a dict keyed by id."""
        (self.dir / "catalogue.json").write_text(json.dumps({
            "nursery": "daleys",
            "captured_at": "2026-08-27T00:05:00",
            "products": {"daleys_58": {"title": "Golden Shower", "url": "x"}},
        }))
        bf.backfill_nursery(self.dir)   # must not raise
        self.assertEqual(self._days(),
                         ["2026-08-25", "2026-08-26", "2026-08-27"])

    def test_other_stray_json_is_ignored(self):
        for name in ("availability.json.bak", "notes.json", "2026-08.json",
                     "2026-8-27.json", "latest.json"):
            (self.dir / name).write_text('{"products": ["not a product"]}')
        bf.backfill_nursery(self.dir)   # must not raise
        self.assertEqual(self._days(),
                         ["2026-08-25", "2026-08-26", "2026-08-27"])

    def test_no_snapshots_writes_nothing(self):
        empty = Path(self._tmp.name) / "brandnew"
        empty.mkdir()
        (empty / "latest.json").write_text(json.dumps(_snapshot("2026-08-27")))
        bf.backfill_nursery(empty)
        self.assertFalse((empty / "availability.json").exists())

    def test_rebuild_only_contains_days_with_snapshots(self):
        """The invariant the repair exists to establish."""
        bf.backfill_nursery(self.dir)
        snap_days = {f.name[:-5] for f in self.dir.glob("*.json")
                     if bf.SNAPSHOT_NAME.match(f.name)}
        self.assertEqual(set(self._days()), snap_days)


if __name__ == "__main__":
    unittest.main()
