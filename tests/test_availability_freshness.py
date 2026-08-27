"""
Regression tests for the availability_tracker freshness guard.

update_nursery() used to read latest.json unconditionally and stamp
date.today() on every row. A failed scrape does not overwrite latest.json, so
yesterday's stock went into the permanent history as today's observation,
prices included, and the run said so without anyone noticing:

    2026-08-26  engalls: failed - HTTP 509 ...
    2026-08-26  Engall's Nursery: 70 updated, 0 new, 144 days tracked

70 rows written on a night nothing was fetched. 52 such nursery-days and
24,567 such rows had accumulated by 2026-08-27, and one of them reached the
public site: /variety/apple-coxs-orange-pippin.html claimed a 20 August
last-seen when Garden Express was last reachable on 17 August.

The fix takes the day from the snapshot's own scraped_at rather than from the
clock, and skips anything that is not today's.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import availability_tracker as at  # noqa: E402

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def _snapshot(scraped_at, available=True, price=65.0):
    return {
        "nursery": "engalls",
        "nursery_name": "Engall's Nursery",
        "scraped_at": scraped_at,
        "products": [{
            "title": "Thorny Mandarin - 200mm Pot",
            "url": "https://www.engalls.com.au/product/thorny-mandarin-200mm-pot/",
            "variants": [{"title": "Default", "available": available,
                          "price": price}],
        }],
    }


class FreshnessGuardTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "engalls"
        self.dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _write_latest(self, snapshot):
        (self.dir / "latest.json").write_text(json.dumps(snapshot))

    def _history(self):
        f = self.dir / "availability.json"
        if not f.exists():
            return None
        return json.loads(f.read_text())

    def _days(self):
        h = self._history()
        if not h:
            return {}
        (prod,) = h["products"].values()
        return prod["days"]

    def test_fresh_snapshot_is_recorded(self):
        self._write_latest(_snapshot(f"{TODAY}T00:18:48.364540"))
        at.update_nursery(self.dir)
        self.assertIn(TODAY, self._days())

    def test_stale_snapshot_is_not_recorded(self):
        """The engalls 2026-08-26 case: the scrape failed, so latest.json is
        still yesterday's file."""
        self._write_latest(_snapshot(f"{YESTERDAY}T00:19:24.000000"))
        at.update_nursery(self.dir)
        self.assertIsNone(self._history())

    def test_stale_snapshot_leaves_existing_history_untouched(self):
        """Yesterday recorded normally, today's scrape failed. The history must
        end at yesterday, with no row invented for today."""
        self._write_latest(_snapshot(f"{YESTERDAY}T00:19:24.000000"))
        # What yesterday's successful run would have left behind.
        history = {
            "nursery": "engalls",
            "nursery_name": "Engall's Nursery",
            "products": {
                "https://www.engalls.com.au/product/thorny-mandarin-200mm-pot/|v:Default": {
                    "title": "Thorny Mandarin - 200mm Pot",
                    "first_seen": YESTERDAY,
                    "days": {YESTERDAY: {"a": True, "p": 65.0}},
                }
            },
        }
        (self.dir / "availability.json").write_text(json.dumps(history))

        at.update_nursery(self.dir)

        days = self._days()
        self.assertEqual(list(days), [YESTERDAY])
        self.assertNotIn(TODAY, days)

    def test_missing_scraped_at_is_skipped(self):
        snap = _snapshot(f"{TODAY}T00:18:48")
        del snap["scraped_at"]
        self._write_latest(snap)
        at.update_nursery(self.dir)
        self.assertIsNone(self._history())

    def test_malformed_scraped_at_is_skipped(self):
        self._write_latest(_snapshot("not-a-timestamp"))
        at.update_nursery(self.dir)
        self.assertIsNone(self._history())

    def test_impossible_date_is_skipped(self):
        self._write_latest(_snapshot("2026-13-45T00:00:00"))
        at.update_nursery(self.dir)
        self.assertIsNone(self._history())

    def test_first_seen_uses_the_snapshot_day_not_the_clock(self):
        self._write_latest(_snapshot(f"{TODAY}T00:18:48.364540"))
        at.update_nursery(self.dir)
        (prod,) = self._history()["products"].values()
        self.assertEqual(prod["first_seen"], TODAY)

    def test_no_latest_file_is_a_noop(self):
        at.update_nursery(self.dir)
        self.assertIsNone(self._history())


class SnapshotDayTest(unittest.TestCase):
    def test_reads_the_date_portion(self):
        self.assertEqual(
            at.snapshot_day({"scraped_at": "2026-08-27T00:18:48.364540"}),
            "2026-08-27")

    def test_bare_date_is_accepted(self):
        self.assertEqual(at.snapshot_day({"scraped_at": "2026-08-27"}),
                         "2026-08-27")

    def test_unusable_values_return_none(self):
        for bad in ({}, {"scraped_at": None}, {"scraped_at": ""},
                    {"scraped_at": "2026-08"}, {"scraped_at": 20260827},
                    {"scraped_at": "2026-02-30T00:00:00"}):
            self.assertIsNone(at.snapshot_day(bad), bad)


if __name__ == "__main__":
    unittest.main()
