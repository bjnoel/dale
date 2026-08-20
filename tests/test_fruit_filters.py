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

    def test_ladybird_nut_trees_are_fruit(self):
        """Ladybird files nuts under its own top-level 'Nut Trees' tag, which
        the include list left out, so 14 real trees were dropped nightly. Live
        titles from ladybird/latest.json on 2026-08-20.
        """
        for title in ("Walnut 'English'",
                      "Pecan Wichita (B) (PICK UP ONLY)",
                      "Advanced Almond Self Pollinating",
                      "Hazelnut Seedling (Corylus avellana)",
                      "Corkscrew Hazel Contorta (Corylus avellana)",
                      "Kaffir Plum",
                      "Diploglottis australis - Large Leaved Tamarind (Tucker Bush\u2122)"):
            with self.subTest(title=title):
                self.assertTrue(is_fruit_product(
                    {"title": title, "tags": ["Nut Trees"]}, "ladybird"))

    def test_ladybird_nut_trees_counter_case_sour_cherry(self):
        """Ladybird files 'Sour Cherry Morello' under Nut Trees. Store taxonomy
        is a strong signal, not an authoritative one: we want the tree either
        way, and the categorize ladder (not the tag) decides what it is.
        """
        self.assertTrue(is_fruit_product(
            {"title": "Sour Cherry Morello (Prunus cerasus)", "tags": ["Nut Trees"]},
            "ladybird"))

    def test_ladybird_ornamentals_still_excluded_after_widening(self):
        """The widening is one tag, not a general loosening. Ladybird's other
        top-level tags carry 5,300 ornamentals and must stay out.
        """
        for tag in ("Flowering Plants", "Natives", "Indoor Plants", "Roses",
                    "Cacti & Succulents", "Palms & Tropical Plants", "Proteas"):
            with self.subTest(tag=tag):
                self.assertFalse(is_fruit_product(
                    {"title": "Rose Iceberg", "tags": [tag]}, "ladybird"))

    def test_ladybird_nut_trees_fertiliser_still_junked(self):
        """'Organic Plant Food Pellets' carries the Nut Trees tag among eleven
        others, so widening the filter let a bag of fertiliser through. The
        junk gate has to catch up with the filter, or kept rises for the wrong
        reason.
        """
        import daily_digest
        self.assertFalse(daily_digest._digest_product_filter(
            {"title": "Organic Plant Food Pellets", "tags": ["Nut Trees"]},
            "ladybird"))
        self.assertTrue(daily_digest._digest_product_filter(
            {"title": "Pecan Riverside", "tags": ["Nut Trees"]},
            "ladybird"))


if __name__ == "__main__":
    unittest.main()
