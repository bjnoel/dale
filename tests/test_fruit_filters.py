"""
Tests for stocklib.fruit_filters — the per-nursery fruit-only filter shared by
the dashboard and the daily digest.

Regression: build-dashboard.py and daily_digest.py each carried their own
FRUIT_FILTERS dict and is_fruit_product(). The digest's dict had only 2 of the
dashboard's 12 nurseries, and its is_fruit_product was missing the
"categories" mode that daleys relies on, so digest emails could include
products the dashboard excludes (and vice versa).
"""
import importlib
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib.fruit_filters import FRUIT_FILTERS, is_fruit_product


class FruitFiltersTest(unittest.TestCase):
    def test_dashboard_and_digest_share_the_same_objects(self):
        dashboard = importlib.import_module("build-dashboard")
        import daily_digest
        self.assertIs(dashboard.FRUIT_FILTERS, FRUIT_FILTERS)
        self.assertIs(dashboard.is_fruit_product, is_fruit_product)
        self.assertIs(daily_digest.FRUIT_FILTERS, FRUIT_FILTERS)
        self.assertIs(daily_digest.is_fruit_product, is_fruit_product)

    def test_categories_mode(self):
        # daleys is the only categories-mode nursery; the digest's old fork
        # didn't implement this mode at all.
        self.assertTrue(is_fruit_product(
            {"title": "Avocado Hass", "product_type": "Fruit and Nut Trees"},
            "daleys"))
        self.assertFalse(is_fruit_product(
            {"title": "Eucalyptus Grandis", "product_type": "Windbreaks"},
            "daleys"))

    def test_tags_mode(self):
        self.assertTrue(is_fruit_product(
            {"title": "Fig Brown Turkey", "tags": ["Fruit Trees & Edibles"]},
            "ladybird"))
        self.assertFalse(is_fruit_product(
            {"title": "Rose Iceberg", "tags": ["Ornamentals"]}, "ladybird"))

    def test_title_include_mode(self):
        self.assertTrue(is_fruit_product(
            {"title": "Dwarf Mulberry Fruit Tree"}, "forever-seeds"))
        self.assertFalse(is_fruit_product(
            {"title": "Basil Seeds"}, "forever-seeds"))

    def test_unknown_nursery_defaults_to_include(self):
        self.assertTrue(is_fruit_product({"title": "Anything"}, "all-rare-herbs"))

    def test_digest_filter_excludes_junk_in_every_mode(self):
        # The old digest fork only junk-filtered "all"-mode nurseries; a junk
        # product passing a tag/category filter slipped into digest emails.
        import daily_digest
        self.assertFalse(daily_digest._digest_product_filter(
            {"title": "Grafting Tape 25mm", "product_type": "Fruit and Nut Trees"},
            "daleys"))
        self.assertFalse(daily_digest._digest_product_filter(
            {"title": "Apple Seeds", "tags": ["Fruit Trees & Edibles"]},
            "ladybird"))
        self.assertTrue(daily_digest._digest_product_filter(
            {"title": "Apple Pink Lady", "product_type": "Fruit and Nut Trees"},
            "daleys"))


if __name__ == "__main__":
    unittest.main()
