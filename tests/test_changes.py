"""
Tests for stocklib.changes -- the shared stock-change engine extracted from the
treestock/beestock digest fork.

Builds tiny dated snapshots in a temp dir and exercises variant keying, the
product_filter (treestock filters fruit; bee keeps all), variant flattening, the
prev-vs-curr categorisation, and the keys restriction (bee's RETAILERS).

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

from stocklib.changes import (
    variant_key, variant_display_title, load_snapshot, compare_snapshots, load_all_changes,
)


def _prod(title, sku, price, available):
    return {"title": title, "url": f"https://x/{sku}",
            "variants": [{"sku": sku, "price": price, "available": available}]}


def _snapshot(products):
    return {"nursery": "n", "products": products}


class VariantKeyTest(unittest.TestCase):
    def test_precedence_sku_id_title(self):
        self.assertEqual(variant_key("u", {"sku": "S", "id": "I", "title": "T"}), "u|sku:S")
        self.assertEqual(variant_key("u", {"id": "I", "title": "T"}), "u|id:I")
        self.assertEqual(variant_key("u", {"title": "T"}), "u|v:T")
        self.assertEqual(variant_key("u", {}), "u|v:Default")

    def test_display_title(self):
        self.assertEqual(variant_display_title("Mango", "Large"), "Mango (Large)")
        self.assertEqual(variant_display_title("Mango", "Default"), "Mango")
        self.assertEqual(variant_display_title("Mango", ""), "Mango")


class LoadSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "nurseryA"
        self.dir.mkdir(parents=True)
        snap = _snapshot([
            _prod("Mango", "MG", 30.0, True),
            _prod("Slow Release Fertiliser", "FERT", 20.0, True),
        ])
        (self.dir / "2026-03-05.json").write_text(json.dumps(snap))

    def test_no_filter_keeps_all_flattened_to_variants(self):
        snap = load_snapshot(self.dir, "2026-03-05")
        self.assertEqual(len(snap), 2)
        self.assertIn("https://x/MG|sku:MG", snap)
        self.assertEqual(snap["https://x/MG|sku:MG"]["min_price"], 30.0)

    def test_product_filter_excludes(self):
        keep_fruit = lambda p, k: "fertiliser" not in p["title"].lower()
        snap = load_snapshot(self.dir, "2026-03-05", product_filter=keep_fruit)
        self.assertEqual(len(snap), 1)
        self.assertNotIn("https://x/FERT|sku:FERT", snap)

    def test_missing_date_returns_empty(self):
        self.assertEqual(load_snapshot(self.dir, "1999-01-01"), {})


class CompareSnapshotsTest(unittest.TestCase):
    def test_categories(self):
        prev = {
            "a": {"title": "Mango", "min_price": 30.0, "any_available": True},
            "b": {"title": "Lychee", "min_price": 50.0, "any_available": False},
            "c": {"title": "Apple", "min_price": 40.0, "any_available": True},
        }
        curr = {
            "a": {"title": "Mango", "min_price": 25.0, "any_available": True},   # price drop
            "b": {"title": "Lychee", "min_price": 50.0, "any_available": True},  # back in stock
            "c": {"title": "Apple", "min_price": 40.0, "any_available": True},   # unchanged
            "d": {"title": "Fig", "min_price": 35.0, "any_available": True},     # new
        }
        ch = compare_snapshots(prev, curr)
        self.assertEqual([p["title"] for p in ch["price_drops"]], ["Mango"])
        self.assertEqual([p["title"] for p in ch["back_in_stock"]], ["Lychee"])
        self.assertEqual([p["title"] for p in ch["new_products"]], ["Fig"])

    def test_price_rise_not_reported(self):
        prev = {"a": {"title": "M", "min_price": 20.0, "any_available": True}}
        curr = {"a": {"title": "M", "min_price": 25.0, "any_available": True}}
        self.assertEqual(compare_snapshots(prev, curr)["price_drops"], [])


class LoadAllChangesTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        for nursery in ("nurseryA", "nurseryB"):
            d = self.root / nursery
            d.mkdir()
            (d / "2026-03-04.json").write_text(json.dumps(_snapshot([_prod("Mango", "MG", 30.0, True)])))
            (d / "2026-03-05.json").write_text(json.dumps(_snapshot([_prod("Mango", "MG", 25.0, True)])))

    def test_scans_all_dirs_by_default(self):
        all_changes, total = load_all_changes(self.root, "2026-03-05")
        self.assertEqual(set(all_changes), {"nurseryA", "nurseryB"})
        self.assertEqual(total, 2)  # one price drop each

    def test_keys_restricts_dirs(self):
        all_changes, total = load_all_changes(self.root, "2026-03-05", keys={"nurseryA"})
        self.assertEqual(set(all_changes), {"nurseryA"})
        self.assertEqual(total, 1)


if __name__ == "__main__":
    unittest.main()
