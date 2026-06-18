"""Regression tests for shopify_scraper.product_in_scope -- the include-filter
that decides whether a Shopify product is kept.

The bug (DEC-209, follow-up to the WooCommerce leaf-category gap DEC-207):
nurseries that filter their catalogue were silently dropping real fruit the
store had tagged/typed inconsistently. The fix turns the filter into an OR over
three signals (product_types / fruit_tags / fruit_handles):

  - Garden World files some edible stock under product_type "NATIVE" but tags it
    "Fruit Online" (Finger Lime, Blackberry 'Chester') -- the type filter alone
    dropped them.
  - Diggers tags fruit inconsistently; a hand-verified `fruit_handles` allow-list
    rescues the ~30 dropped fruit (e.g. Loquat, which is essentially untagged).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from shopify_scraper import product_in_scope, product_tags, NURSERIES  # noqa: E402

GW = NURSERIES["garden-world"]
DIGGERS = NURSERIES["diggers"]
FOREVER = NURSERIES["forever-seeds"]


class TestProductTags(unittest.TestCase):
    def test_list_tags_lowercased(self):
        self.assertEqual(product_tags({"tags": ["Fruit Online", "X"]}), ["fruit online", "x"])

    def test_string_tags_split_and_lowercased(self):
        self.assertEqual(product_tags({"tags": "Fruit Online, Berry"}), ["fruit online", "berry"])

    def test_missing_tags(self):
        self.assertEqual(product_tags({}), [])


class TestNoFilterKeepsEverything(unittest.TestCase):
    def test_unfiltered_nursery(self):
        # ross-creek has no product_types/fruit_tags/fruit_handles
        self.assertTrue(product_in_scope({"title": "Anything", "product_type": "", "tags": []},
                                          NURSERIES["ross-creek"]))


class TestGardenWorldRegression(unittest.TestCase):
    """FOOD PLANTS type, PLUS a "Fruit Online" tag rescue for NATIVE-typed fruit."""

    # The products the type-only filter used to drop (DEC-209).
    DROPPED_BEFORE = [
        ("Finger Lime 'Rainforest Pearl' 17cm", "NATIVE",
         ["Edible Australian Natives", "Fruit Online"]),
        ("Finger Lime 'D'Emerald' Dwarf 15cm", "NATIVE",
         ["Edible Australian Natives", "Fruit Online"]),
        ("Blackberry Chester Thornless 14cm", "NATIVE", ["Fruit Online"]),
    ]

    def test_rescued_by_fruit_online_tag(self):
        for title, ptype, tags in self.DROPPED_BEFORE:
            with self.subTest(title=title):
                self.assertTrue(product_in_scope(
                    {"title": title, "product_type": ptype, "tags": tags}, GW))

    def test_food_plants_still_kept(self):
        self.assertTrue(product_in_scope(
            {"title": "Fig Black Genoa", "product_type": "FOOD PLANTS", "tags": []}, GW))

    def test_ornamental_named_after_fruit_still_dropped(self):
        # Grass "Little Plum", fertiliser, pot etc. -- no FOOD PLANTS, no Fruit Online tag.
        for title, ptype, tags in [
            ("Pennisetum Little Plum Fountain 14cm", "PLANTS", ["Grasses Online"]),
            ("Harrys Citrus Food 5kg", "FERTILISERS", ["Fertiliser Online"]),
            ("Pot Lemon Tall", "POTS INDOOR", ["Indoor Pots Online"]),
        ]:
            with self.subTest(title=title):
                self.assertFalse(product_in_scope(
                    {"title": title, "product_type": ptype, "tags": tags}, GW))

    def test_edible_native_herb_not_rescued(self):
        # "Edible Australian Natives" without "Fruit Online" is NOT a rescue tag
        # (it also covers native culinary herbs we don't track).
        self.assertFalse(product_in_scope(
            {"title": "Prostanthera Cool Mint 14cm", "product_type": "NATIVE",
             "tags": ["Edible Australian Natives"]}, GW))


class TestDiggersRegression(unittest.TestCase):
    """fruit_tags PLUS a curated fruit_handles allow-list for untagged fruit."""

    def test_fruit_tag_match_still_kept(self):
        self.assertTrue(product_in_scope(
            {"title": "Apricot 'Trevatt'", "product_type": "Plants",
             "tags": ["All fruit & nuts"]}, DIGGERS))

    def test_handle_allowlist_rescues_untagged_fruit(self):
        # Loquat is essentially untagged at Diggers; rescued by handle.
        for handle in ("loquat", "walnut-black", "blueberry-brightwell",
                       "raspberry-heritage", "jaboticaba"):
            with self.subTest(handle=handle):
                self.assertTrue(product_in_scope(
                    {"title": "x", "product_type": "Plants", "tags": [], "handle": handle},
                    DIGGERS))

    def test_herb_not_in_allowlist_dropped(self):
        # Thyme/Asparagus carry IsEd but no fruit tag and are not allow-listed.
        for title, handle in [("Thyme", "thyme"), ("Asparagus 'Mary Washington'", "asparagus-mary-washington")]:
            with self.subTest(title=title):
                self.assertFalse(product_in_scope(
                    {"title": title, "product_type": "Plants",
                     "tags": ["IsEd :: True"], "handle": handle}, DIGGERS))


class TestForeverSeedsRegression(unittest.TestCase):
    """Confirmed clean: the only drops are non-fruit (agarwood oil tree, patchouli)."""

    def test_fruit_tag_kept(self):
        self.assertTrue(product_in_scope(
            {"title": "Citrus seed", "product_type": "", "tags": ["citrus"], "handle": "x"}, FOREVER))

    def test_non_fruit_dropped(self):
        self.assertFalse(product_in_scope(
            {"title": "Patchouli CABLIN Herb Plant", "product_type": "",
             "tags": ["essential oil", "Fragrant", "Herb", "Herb Plant", "Plant"], "handle": "patchouli"},
            FOREVER))


if __name__ == "__main__":
    unittest.main()
