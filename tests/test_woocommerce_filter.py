"""
Regression tests for woocommerce_scraper.category_matches -- the include-filter
that decides whether a product is kept based on its WooCommerce category slugs.

The bug: Guildford Garden Centre tags many fruit trees with only a leaf category
(e.g. "Fig - Peter Good" carries exotic-tropical-fruit-trees + fig-tree) and
omits the "fruits-nuts"/"edibles" parent. The old config filtered on the parent
slugs only, so ~225 real fruit/nut trees were silently dropped from the dataset.
The fix lists the leaf categories too and relies on substring matching.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from woocommerce_scraper import category_matches, NURSERIES  # noqa: E402

GUILDFORD_CATS = NURSERIES["guildford"]["fruit_categories"]
ENGALLS_CATS = NURSERIES["engalls"]["fruit_categories"]
YALCA_CATS = NURSERIES["yalca-fruit-trees"]["fruit_categories"]


class TestCategoryMatches(unittest.TestCase):
    def test_empty_filter_keeps_everything(self):
        self.assertTrue(category_matches(["pots", "gift-cards"], []))

    def test_exact_parent_match(self):
        self.assertTrue(category_matches(["fruits-nuts", "fig-tree"], ["fruits-nuts"]))

    def test_substring_match_catches_bare_root_leaf(self):
        # "stone-fruit" must match the bare-root leaf variant via substring.
        self.assertTrue(
            category_matches(
                ["stone-fruit-trees-bare-root-stock", "plum"], ["stone-fruit"]
            )
        )

    def test_non_fruit_is_excluded(self):
        self.assertFalse(category_matches(["pots", "tools"], ["fruits-nuts", "edibles"]))


class TestGuildfordRegression(unittest.TestCase):
    """The exact products that the parent-only filter used to drop."""

    # (name, category slugs as returned by the store API)
    DROPPED_BEFORE = [
        ("Fig - Peter Good", ["exotic-tropical-fruit-trees", "fig-tree"]),
        ("Mango - Alphonso - Grafted", ["trees", "exotic-tropical-fruit-trees", "mango"]),
        ("Plum - Satsuma", ["stone-fruit", "plum"]),
        ("Finger Lime - Red Caviar", ["citrus", "finger-lime"]),
        ("Avocado - Jala Grafted (B)", ["trees", "exotic-tropical-fruit-trees", "avocado"]),
        ("Blueberry - Burst", ["berries-vines", "blueberry"]),
        ("Passionfruit - Big Boppa", ["berries-vines", "passion-fruit"]),
        ("Mulberry - Pakistan - Bare Root",
         ["trees", "berries-and-vines-bare-root-stock", "berries-vines", "mulberry"]),
    ]

    def test_old_parent_only_filter_dropped_these(self):
        # Documents the bug: none of these carried the parent slugs.
        for name, cats in self.DROPPED_BEFORE:
            with self.subTest(name=name):
                self.assertFalse(
                    category_matches(cats, ["fruits-nuts", "edibles"]),
                    f"{name} unexpectedly matched the old parent-only filter",
                )

    def test_new_filter_keeps_these(self):
        for name, cats in self.DROPPED_BEFORE:
            with self.subTest(name=name):
                self.assertTrue(
                    category_matches(cats, GUILDFORD_CATS),
                    f"{name} should be kept by the broadened Guildford filter",
                )

    def test_new_filter_still_keeps_parent_tagged_products(self):
        # Products that already carried the parent must not regress.
        cats = ["fruits-nuts", "exotic-tropical-fruit-trees", "fig-tree"]
        self.assertTrue(category_matches(cats, GUILDFORD_CATS))


class TestEngallsRegression(unittest.TestCase):
    """Engall's (citrus/olive specialist) tagged fruit by type, not "citrus"."""

    DROPPED_BEFORE = [
        ("Dwarf Arnold Blood Orange", ["dwarf-orange"]),
        ("Imperial Mandarin", ["mandarin"]),
        ("Dwarf Emperor Mandarin", ["dwarf-mandarin"]),
        ("Tahitian Lime", ["lime"]),
        ("Manzanillo Olive", ["olives"]),
        ("Frantoio Olive", ["olives"]),
    ]

    def test_old_citrus_only_filter_dropped_these(self):
        for name, cats in self.DROPPED_BEFORE:
            with self.subTest(name=name):
                self.assertFalse(category_matches(cats, ["citrus", "dwarf-citrus"]))

    def test_new_filter_keeps_these(self):
        for name, cats in self.DROPPED_BEFORE:
            with self.subTest(name=name):
                self.assertTrue(category_matches(cats, ENGALLS_CATS))

    def test_still_keeps_plain_citrus(self):
        self.assertTrue(category_matches(["citrus", "speciality-citrus"], ENGALLS_CATS))


class TestYalcaRegression(unittest.TestCase):
    """Yalca missed nuts/fruit tagged with their own leaf category only."""

    DROPPED_BEFORE = [
        ("Chandler walnut", ["walnut-trees"]),
        ("Barcelona hazelnut", ["hazel-nuts"]),
        ("Azerbaijani pomegranate", ["pomegranate-trees"]),
        ("Tayberry", ["blackberry-plants"]),
    ]

    def test_new_filter_keeps_these(self):
        for name, cats in self.DROPPED_BEFORE:
            with self.subTest(name=name):
                self.assertTrue(category_matches(cats, YALCA_CATS))

    def test_ornamentals_stay_excluded(self):
        # Maples/ash/elm carry only "ornamental-trees" -- must NOT be pulled in.
        for cats in (["ornamental-trees"], ["ornamental-trees", "sugar-maple-trees"]):
            with self.subTest(cats=cats):
                self.assertFalse(category_matches(cats, YALCA_CATS))


if __name__ == "__main__":
    unittest.main()
