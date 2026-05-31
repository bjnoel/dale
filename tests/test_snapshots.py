"""
Tests for stocklib.snapshots -- the shared snapshot-loading mechanics that the
page builders share (extracted from four inline copies).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
FIXTURE = Path(__file__).resolve().parent / "golden" / "fixture" / "nursery-stock"
sys.path.insert(0, str(SCRAPERS))

from stocklib.snapshots import iter_nursery_snapshots, snapshot_path, variant_min_price


class IterNurserySnapshotsTest(unittest.TestCase):
    def test_yields_all_nurseries_in_sorted_order(self):
        seen = list(iter_nursery_snapshots(FIXTURE))
        keys = [k for k, _ in seen]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(set(keys), {"daleys", "ross-creek", "primal-fruits"})

    def test_yields_loaded_snapshot_dicts(self):
        by_key = dict(iter_nursery_snapshots(FIXTURE))
        self.assertEqual(by_key["daleys"]["nursery"], "daleys")
        self.assertTrue(by_key["daleys"]["products"])
        # falls back to latest.json (no dated file in the fixture)
        self.assertIn("scraped_at", by_key["ross-creek"])

    def test_missing_dir_yields_nothing(self):
        self.assertEqual(list(iter_nursery_snapshots(FIXTURE / "does-not-exist")
                              if (FIXTURE / "does-not-exist").exists() else []), [])


class SnapshotPathTest(unittest.TestCase):
    def test_falls_back_to_latest_when_no_dated_file(self):
        p = snapshot_path(FIXTURE / "daleys", today="1999-01-01")
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "latest.json")

    def test_none_when_nothing_present(self):
        self.assertIsNone(snapshot_path(FIXTURE / "daleys" / "nope", today="1999-01-01"))


class VariantMinPriceTest(unittest.TestCase):
    def test_all_priced_variants(self):
        p = {"variants": [{"price": 20.0, "available": True}, {"price": 12.0, "available": False}]}
        self.assertEqual(variant_min_price(p), 12.0)

    def test_prefer_available_uses_available_prices(self):
        p = {"variants": [{"price": 20.0, "available": True}, {"price": 12.0, "available": False}]}
        self.assertEqual(variant_min_price(p, prefer_available=True), 20.0)

    def test_prefer_available_falls_back_to_all_when_none_available(self):
        p = {"variants": [{"price": 20.0, "available": False}, {"price": 12.0, "available": False}]}
        self.assertEqual(variant_min_price(p, prefer_available=True), 12.0)

    def test_no_priced_variants_returns_none(self):
        self.assertIsNone(variant_min_price({"variants": [{"available": True}]}))
        self.assertIsNone(variant_min_price({}))


if __name__ == "__main__":
    unittest.main()
