"""Regression tests for bigcommerce_scraper.in_scope / extract_breadcrumbs --
the scope filter for the Heritage Fruit Trees sitemap-driven scrape.

The bug (DEC-209): the scraper walked three top-level category listings
(fruit-trees / nut-trees / berries-and-vine-fruit) and relied on them rolling up
their subcategories. They don't, so ~150 real fruit were silently dropped -- ALL
blueberries, walnuts, chestnuts, kiwi-fruit, grapes, medlar, loquat, plus ~50
apples and a chunk of pears/cherries living in deeper subcategories.

The fix drives discovery from the complete products sitemap and decides scope
from each product's breadcrumb (the store's own authoritative category), with a
taxonomy fallback for products whose primary breadcrumb is a cross-cut like
"Specials".

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from bigcommerce_scraper import in_scope, extract_breadcrumbs  # noqa: E402


class TestExtractBreadcrumbs(unittest.TestCase):
    SAMPLE = (
        '<nav class="breadcrumbs" itemscope itemtype="http://schema.org/BreadcrumbList">'
        '<li class="breadcrumb" itemprop="itemListElement"><a itemprop="item">'
        '<span itemprop="name">Home</span></a></li>'
        '<li class="breadcrumb"><a itemprop="item"><span itemprop="name">Shop</span></a></li>'
        '<li class="breadcrumb"><a itemprop="item"><span itemprop="name">Nut Trees</span></a></li>'
        '<li class="breadcrumb"><a itemprop="item"><span itemprop="name">Walnuts</span></a></li>'
        '<li class="breadcrumb"><span itemprop="name">Chandler Walnut</span></li></ul>'
    )

    def test_drops_home_and_shop(self):
        self.assertEqual(extract_breadcrumbs(self.SAMPLE),
                         ["Nut Trees", "Walnuts", "Chandler Walnut"])

    def test_empty_html(self):
        self.assertEqual(extract_breadcrumbs(""), [])
        self.assertEqual(extract_breadcrumbs(None), [])


class TestInScopeFruitCategories(unittest.TestCase):
    """The exact categories the old scraper missed must now be kept."""

    KEPT = [
        ("Bluecrop Blueberry", ["Berries and Vine Fruit", "Blueberries",
                                "Northern Highbush (high chill requirement)", "Bluecrop Blueberry"]),
        ("Chandler Walnut", ["Nut Trees", "Walnuts", "Chandler Walnut"]),
        ("Wandiligong Wonder Chestnut", ["Nut Trees", "Chestnuts", "Wandiligong Wonder Chestnut"]),
        ("Hayward Kiwi Fruit (female)", ["Berries and Vine Fruit", "Kiwi Fruit", "Hayward Kiwi Fruit (female)"]),
        ("Akane Apple (medium)", ["Fruit Trees", "Apple Trees", "Eating Apples", "Akane Apple (medium)"]),
        ("White Genoa Fig", ["Fruit Trees", "Fig Trees", "White Genoa Fig"]),
        ("Dutch Medlar", ["Fruit Trees", "Medlar", "Dutch Medlar"]),
    ]

    def test_fruit_breadcrumbs_kept(self):
        for title, crumbs in self.KEPT:
            with self.subTest(title=title):
                self.assertTrue(in_scope(title, crumbs))


class TestInScopeExcluded(unittest.TestCase):
    """Ornamentals / non-plant / workshops / rootstocks must stay excluded."""

    DROPPED = [
        ("Autumn Blaze Maple", ["Ornamental Plants", "Avenue Trees", "Autumn Blaze Maple"]),
        ("Acoma Crepe Myrtle", ["Ornamental Plants", "Flowering Trees and Shrubs", "Crepe Myrtle", "Acoma Crepe Myrtle"]),
        ("Almond Orchard Labels", ["Non Plant Products", "Plant Labels", "Orchard Labels", "Almond Orchard Labels"]),
        ("Bushfire Preparation Workshop", ["Workshops", "Bushfire Preparation Workshop (half day)"]),
        ("Bud 9 Rootstock", ["Rootstocks", "Bud 9"]),
    ]

    def test_excluded_breadcrumbs(self):
        for title, crumbs in self.DROPPED:
            with self.subTest(title=title):
                self.assertFalse(in_scope(title, crumbs))


class TestInScopeSpecialsFallback(unittest.TestCase):
    """Products whose primary breadcrumb is a cross-cut (Specials/Almost Sold
    Out) carry no fruit category -- fall back to the taxonomy, but keep out
    ornamental look-alikes."""

    def test_specials_apple_kept_via_taxonomy(self):
        self.assertTrue(in_scope(
            "Bramley's Seedling Apple (medium)",
            ["SPECIALS", "Almost Sold Out", "Bramley's Seedling Apple (medium)"]))

    def test_specials_crabapple_dropped_by_ornamental_guard(self):
        self.assertFalse(in_scope(
            "Craig Hall Crabapple (Malus 'Craig Hall')",
            ["SPECIALS", "Almost Sold Out", "Craig Hall Crabapple (Malus 'Craig Hall')"]))

    def test_no_breadcrumb_fruit_title_kept(self):
        self.assertTrue(in_scope("Akane Apple", []))

    def test_no_breadcrumb_nonfruit_dropped(self):
        self.assertFalse(in_scope("Left-handed Budding Knife", []))


if __name__ == "__main__":
    unittest.main()
