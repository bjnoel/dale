"""
Tests for stocklib.model -- the typed snapshot model + validator.

Covers the two scraper dialects (variant-based vs flat/Ecwid), the validator's
problem detection, and a round-trip of the committed golden fixtures (proves the
model matches real snapshot shape).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
FIXTURE = Path(__file__).resolve().parent / "golden" / "fixture" / "nursery-stock"
sys.path.insert(0, str(SCRAPERS))

from stocklib.model import Product, Snapshot, normalize_product, validate_snapshot, validate_and_warn


class NormalizeVariantDialectTest(unittest.TestCase):
    def test_variant_based_with_aggregates(self):
        raw = {
            "title": "Avocado - Hass", "url": "https://x/av", "category": "Fruit and Nut Trees",
            "variants": [
                {"title": "Large", "price": 46.95, "available": True, "sku": "L"},
                {"title": "Medium", "price": 34.95, "available": True, "sku": "M"},
            ],
            "min_price": 34.95, "max_price": 46.95, "any_available": True,
        }
        p = normalize_product(raw, "daleys")
        self.assertEqual(p.title, "Avocado - Hass")
        self.assertEqual(p.nursery, "daleys")
        self.assertTrue(p.available)
        self.assertEqual(p.min_price, 34.95)
        self.assertEqual(p.max_price, 46.95)
        self.assertEqual(p.category_raw, "Fruit and Nut Trees")
        self.assertEqual(len(p.variants), 2)

    def test_out_of_stock_from_any_available(self):
        raw = {"title": "Apple", "url": "https://x/a",
               "variants": [{"price": 39.95, "available": False}],
               "min_price": 39.95, "max_price": 39.95, "any_available": False}
        self.assertFalse(normalize_product(raw, "daleys").available)

    def test_min_price_computed_from_variants_when_absent(self):
        raw = {"title": "X", "url": "https://x",
               "variants": [{"price": 20.0, "available": True}, {"price": 12.0, "available": True}]}
        p = normalize_product(raw, "n")
        self.assertEqual(p.min_price, 12.0)
        self.assertEqual(p.max_price, 20.0)
        self.assertTrue(p.available)  # derived from variants when no any_available


class NormalizeFlatDialectTest(unittest.TestCase):
    def test_flat_ecwid_synthesises_default_variant(self):
        raw = {"title": "Jaboticaba", "url": "https://x/j", "sku": "J1",
               "price": 89.0, "currency": "AUD", "available": True}
        p = normalize_product(raw, "primal-fruits")
        self.assertTrue(p.available)
        self.assertEqual(p.min_price, 89.0)
        self.assertEqual(p.max_price, 89.0)
        self.assertEqual(len(p.variants), 1)
        self.assertEqual(p.variants[0].title, "Default")
        self.assertEqual(p.variants[0].sku, "J1")

    def test_flat_out_of_stock(self):
        raw = {"title": "Y", "url": "https://y", "price": 10.0, "available": False}
        self.assertFalse(normalize_product(raw, "n").available)

    def test_flat_no_price(self):
        raw = {"title": "Z", "url": "https://z", "price": None, "available": True}
        p = normalize_product(raw, "n")
        self.assertIsNone(p.min_price)
        self.assertTrue(p.available)


class ValidateSnapshotTest(unittest.TestCase):
    def _good(self):
        return {"nursery": "n", "nursery_name": "N", "scraped_at": "t",
                "products": [{"title": "Mango", "url": "https://m", "any_available": True, "min_price": 10}]}

    def test_good_snapshot_has_no_problems(self):
        self.assertEqual(validate_snapshot(self._good()), [])

    def test_missing_nursery(self):
        s = self._good(); del s["nursery"]
        self.assertIn("missing 'nursery' key", validate_snapshot(s))

    def test_missing_products_key(self):
        self.assertIn("missing 'products' key", validate_snapshot({"nursery": "n"}))

    def test_product_missing_title_and_url(self):
        s = self._good(); s["products"] = [{"any_available": True}]
        probs = validate_snapshot(s)
        self.assertTrue(any("missing title" in p for p in probs))
        self.assertTrue(any("missing url" in p for p in probs))

    def test_no_availability_signal(self):
        s = self._good(); s["products"] = [{"title": "T", "url": "https://t"}]
        self.assertTrue(any("no availability signal" in p for p in validate_snapshot(s)))

    def test_negative_price_flagged(self):
        s = self._good(); s["products"] = [{"title": "T", "url": "https://t", "available": True, "min_price": -5}]
        self.assertTrue(any("invalid price" in p for p in validate_snapshot(s)))

    def test_validate_and_warn_is_warn_only(self):
        import io
        buf = io.StringIO()
        probs = validate_and_warn({"products": [{}]}, source="test", stream=buf)
        self.assertTrue(probs)                       # returned the problems
        self.assertIn("WARN[test]", buf.getvalue())  # logged them
        # did not raise


class FixtureRoundTripTest(unittest.TestCase):
    """Every committed fixture snapshot is valid and normalises cleanly."""
    def test_fixtures_valid_and_normalise(self):
        files = sorted(FIXTURE.glob("*/latest.json"))
        self.assertTrue(files, "no fixture snapshots found")
        for f in files:
            raw = json.loads(f.read_text())
            self.assertEqual(validate_snapshot(raw), [], f"{f} should be valid")
            snap = Snapshot.from_raw(raw)
            self.assertTrue(snap.products)
            for p in snap.products:
                self.assertIsInstance(p, Product)
                self.assertTrue(p.title and p.url and p.nursery)
                self.assertTrue(p.variants, f"{p.title} should have >=1 variant")


if __name__ == "__main__":
    unittest.main()
