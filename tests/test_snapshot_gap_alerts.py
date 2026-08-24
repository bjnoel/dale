"""Regression tests for snapshot gaps producing phantom restock alerts.

send_variety_alerts.py fires when a watched variety goes from 0 in-stock
listings yesterday to some today. Until 2026-08-13 a nursery with no dated
snapshot for the comparison day was skipped entirely, which fed the comparison
"this nursery had nothing in stock" when the truth was "this nursery did not
report". Every watched variety it stocked then looked like a fresh restock.

That was live: Heritage Fruit Trees had been 503ing for two days and Ladybird
had failed once, and a dry run on the night this was found had 10 phantom
restocks queued against 98 real subscriber watches, for varieties that had
never gone out of stock.

The fix is stocklib.snapshots.snapshot_path_for_date, which falls back to the
most recent snapshot at or before the target date. These tests pin both the
resolver and the no-phantom-alert property it exists to provide.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib.snapshots import snapshot_path_for_date


def write_snapshot(nursery_dir: Path, day: str, titles_in_stock):
    nursery_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "nursery_name": nursery_dir.name,
        "products": [
            {"title": t, "url": f"https://example.com/{i}",
             "any_available": True, "min_price": 25.0}
            for i, t in enumerate(titles_in_stock)
        ],
    }
    (nursery_dir / f"{day}.json").write_text(json.dumps(payload))
    return payload


class SnapshotForDateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.nursery = Path(self.tmp.name) / "ladybird"
        self.nursery.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_date_wins(self):
        write_snapshot(self.nursery, "2026-08-12", ["Apple Sundowner"])
        write_snapshot(self.nursery, "2026-08-13", ["Apple Sundowner"])
        got = snapshot_path_for_date(self.nursery, "2026-08-13", today="2026-08-14")
        self.assertEqual(got.name, "2026-08-13.json")

    def test_missing_date_falls_back_to_most_recent_prior(self):
        """The bug. Ladybird failed on 08-13, so 08-13 must resolve to 08-12
        rather than to nothing."""
        write_snapshot(self.nursery, "2026-08-11", ["Apple Sundowner"])
        write_snapshot(self.nursery, "2026-08-12", ["Apple Sundowner"])
        got = snapshot_path_for_date(self.nursery, "2026-08-13", today="2026-08-14")
        self.assertIsNotNone(got, "a failed scrape must not read as empty shelves")
        self.assertEqual(got.name, "2026-08-12.json")

    def test_never_falls_forward(self):
        """A later snapshot must not be used to describe an earlier day."""
        write_snapshot(self.nursery, "2026-08-14", ["Apple Sundowner"])
        got = snapshot_path_for_date(self.nursery, "2026-08-13", today="2026-08-14")
        self.assertIsNone(got)

    def test_today_prefers_latest_json(self):
        write_snapshot(self.nursery, "2026-08-12", ["Apple Sundowner"])
        (self.nursery / "latest.json").write_text(json.dumps({"products": []}))
        got = snapshot_path_for_date(self.nursery, "2026-08-14", today="2026-08-14")
        self.assertEqual(got.name, "latest.json")

    def test_no_history_returns_none(self):
        self.assertIsNone(
            snapshot_path_for_date(self.nursery, "2026-08-13", today="2026-08-14"))

    def test_ignores_non_dated_json(self):
        (self.nursery / "needs-review.json").write_text("{}")
        self.assertIsNone(
            snapshot_path_for_date(self.nursery, "2026-08-13", today="2026-08-14"))


class NoPhantomRestockTest(unittest.TestCase):
    """End to end through the alert script's own loader and grouper."""

    def setUp(self):
        import importlib.util
        repo = Path(__file__).resolve().parent.parent
        path = repo / "tools" / "scrapers" / "send_variety_alerts.py"
        spec = importlib.util.spec_from_file_location("sva_mod", path)
        self.sva = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sva)

        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def restocks(self, today_date, yesterday_date):
        """Slugs that would fire, using the script's real comparison."""
        today = self.sva.load_nursery_data(self.data, today_date)
        yesterday = self.sva.load_nursery_data(self.data, yesterday_date)
        t = self.sva.in_stock_by_variety_slug(today)
        y = self.sva.in_stock_by_variety_slug(yesterday)
        return {s for s in t if len(t[s]) > 0 and len(y.get(s, [])) == 0}

    def test_gap_does_not_fabricate_a_restock(self):
        """Ladybird stocked the same variety throughout and simply missed one
        night's scrape. Nothing came back in stock, so nothing may fire."""
        lb = self.data / "ladybird"
        write_snapshot(lb, "2026-08-12", ["Apple Sundowner"])
        # no 2026-08-13 snapshot: the scrape failed
        write_snapshot(lb, "2026-08-14", ["Apple Sundowner"])

        self.assertEqual(self.restocks("2026-08-14", "2026-08-13"), set())

    def test_genuine_restock_still_fires(self):
        """The fix must not silence real alerts."""
        lb = self.data / "ladybird"
        write_snapshot(lb, "2026-08-13", [])
        write_snapshot(lb, "2026-08-14", ["Apple Sundowner"])

        fired = self.restocks("2026-08-14", "2026-08-13")
        self.assertTrue(fired, "a real 0 -> in-stock transition must still alert")

    def test_restock_across_a_gap_fires_once_against_last_known_state(self):
        """Heritage was out of stock when last seen, went dark, and came back
        with the variety available. That is a real restock."""
        h = self.data / "heritage-fruit-trees"
        write_snapshot(h, "2026-08-11", [])
        write_snapshot(h, "2026-08-14", ["Apple Gravenstein"])

        self.assertTrue(self.restocks("2026-08-14", "2026-08-13"))


def write_health(health_dir: Path, day: str, records):
    """One scraper-health JSONL line per nursery for a day."""
    health_dir.mkdir(parents=True, exist_ok=True)
    with open(health_dir / f"{day}.jsonl", "a") as fh:
        for nursery, ok, products in records:
            fh.write(json.dumps({"nursery": nursery, "ok": ok,
                                 "products": products, "ts": f"{day}T00:30:00"}) + "\n")


class DistrustedSnapshotTest(unittest.TestCase):
    """The second shape of the same bug: a scrape that SUCCEEDS but truncated.

    snapshot_path_for_date's original fix covered the nursery that failed to
    report. It did not cover Heritage Fruit Trees on 2026-08-15, which reported
    fine while republishing 210 of its 375 products and deleting every
    out-of-stock line rather than marking it. untrusted_nurseries() caught that
    the same night and the page ledger acted on it; the alert path never asked.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.nursery = Path(self.tmp.name) / "heritage-fruit-trees"
        self.nursery.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def distrust(self, *days):
        bad = set(days)
        return lambda day: day in bad

    def test_distrusted_day_falls_back_to_last_trusted_snapshot(self):
        write_snapshot(self.nursery, "2026-08-11", ["Apple Bramley's Seedling"])
        write_snapshot(self.nursery, "2026-08-15", ["Apple Bramley's Seedling"])
        got = snapshot_path_for_date(self.nursery, "2026-08-15", today="2026-08-16",
                                     distrusted=self.distrust("2026-08-15"))
        self.assertEqual(got.name, "2026-08-11.json")

    def test_walks_back_past_consecutive_distrusted_days(self):
        for day in ("2026-08-11", "2026-08-15", "2026-08-16"):
            write_snapshot(self.nursery, day, ["Apple Bramley's Seedling"])
        got = snapshot_path_for_date(self.nursery, "2026-08-16", today="2026-08-17",
                                     distrusted=self.distrust("2026-08-15", "2026-08-16"))
        self.assertEqual(got.name, "2026-08-11.json")

    def test_distrusted_today_does_not_fall_through_to_latest_json(self):
        """latest.json is written by the last good scrape, so on a distrusted
        day it is the very data being distrusted."""
        write_snapshot(self.nursery, "2026-08-11", ["Apple Bramley's Seedling"])
        (self.nursery / "latest.json").write_text(json.dumps({"products": []}))
        got = snapshot_path_for_date(self.nursery, "2026-08-16", today="2026-08-16",
                                     distrusted=self.distrust("2026-08-16"))
        self.assertEqual(got.name, "2026-08-11.json")

    def test_no_trusted_history_returns_none(self):
        write_snapshot(self.nursery, "2026-08-15", ["Apple Bramley's Seedling"])
        self.assertIsNone(
            snapshot_path_for_date(self.nursery, "2026-08-15", today="2026-08-16",
                                   distrusted=self.distrust("2026-08-15")))

    def test_default_trusts_everything(self):
        """Absent the argument this module must behave exactly as before."""
        write_snapshot(self.nursery, "2026-08-15", ["Apple Bramley's Seedling"])
        got = snapshot_path_for_date(self.nursery, "2026-08-15", today="2026-08-16")
        self.assertEqual(got.name, "2026-08-15.json")


class PurgedCatalogueTest(unittest.TestCase):
    """End to end, reproducing 2026-08-15 through the alert script's own loader."""

    def setUp(self):
        import importlib.util
        repo = Path(__file__).resolve().parent.parent
        path = repo / "tools" / "scrapers" / "send_variety_alerts.py"
        spec = importlib.util.spec_from_file_location("sva_purge_mod", path)
        self.sva = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sva)

        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data = root / "nursery-stock"
        self.health = root / "scraper-health"
        self.data.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def restocks(self, today_date, yesterday_date):
        today = self.sva.load_nursery_data(self.data, today_date)
        yesterday = self.sva.load_nursery_data(self.data, yesterday_date)
        t = self.sva.in_stock_by_variety_slug(today)
        y = self.sva.in_stock_by_variety_slug(yesterday)
        return {s for s in t if len(t[s]) > 0 and len(y.get(s, [])) == 0}

    def seed_heritage(self):
        """375 products with Bramley's out of stock, then a 210-product
        republish with everything marked available."""
        h = self.data / "heritage-fruit-trees"
        h.mkdir(parents=True)
        wide = {"nursery_name": "Heritage Fruit Trees", "products": (
            [{"title": "Apple Bramley's Seedling", "url": "https://x/b",
              "any_available": False, "min_price": 25.0}]
            + [{"title": f"Apple Filler {i}", "url": f"https://x/{i}",
                "any_available": False, "min_price": 25.0} for i in range(374)])}
        (h / "2026-08-11.json").write_text(json.dumps(wide))
        narrow = {"nursery_name": "Heritage Fruit Trees", "products": (
            [{"title": "Apple Bramley's Seedling", "url": "https://x/b",
              "any_available": True, "min_price": 25.0}]
            + [{"title": f"Apple Filler {i}", "url": f"https://x/{i}",
                "any_available": True, "min_price": 25.0} for i in range(209)])}
        (h / "2026-08-15.json").write_text(json.dumps(narrow))
        for day in ("2026-08-08", "2026-08-09", "2026-08-10", "2026-08-11"):
            write_health(self.health, day, [("heritage-fruit-trees", True, 375)])

    def test_purged_catalogue_does_not_fabricate_a_restock(self):
        """The live failure. Bramley's was never restocked: the store simply
        stopped publishing out-of-stock lines."""
        self.seed_heritage()
        write_health(self.health, "2026-08-15", [("heritage-fruit-trees", True, 210)])
        self.assertEqual(self.restocks("2026-08-15", "2026-08-14"), set())

    def test_same_data_without_the_health_signal_still_fires(self):
        """Pins that the health record is what does the work here, so this test
        fails if the guard is ever disconnected rather than passing vacuously."""
        self.seed_heritage()
        write_health(self.health, "2026-08-15", [("heritage-fruit-trees", True, 375)])
        self.assertIn("apple-bramley-s", self.restocks("2026-08-15", "2026-08-14"))

    def test_trusted_nursery_restock_still_fires(self):
        """The guard must only ever suppress, never invent or over-reach."""
        lb = self.data / "ladybird"
        lb.mkdir(parents=True)
        write_snapshot(lb, "2026-08-15", ["Tamarillo Red"])
        (lb / "2026-08-14.json").write_text(json.dumps({"products": []}))
        for day in ("2026-08-12", "2026-08-13", "2026-08-14", "2026-08-15"):
            write_health(self.health, day, [("ladybird", True, 7000)])
        self.assertIn("tamarillo-red", self.restocks("2026-08-15", "2026-08-14"))


if __name__ == "__main__":
    unittest.main()
