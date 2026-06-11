"""
Tests for stocklib.classify -- the canonical junk filter that replaced 10
drifted NON_PLANT_KEYWORDS copies.

These pin the vetting decisions as regressions: the substring false-positives
(pot/bag/class) must NOT reappear (they wrongly dropped real fruit), while the
native/ornamental/consumable keywords must stay (fruit-stock site).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib.classify import (
    CATEGORY_KEYWORDS, NON_PLANT_KEYWORDS, TRUE_JUNK,
    derived_non_plant_keywords, is_real_product, is_seed_packet,
)
from stocklib.taxonomy import KNOWN_CATEGORIES


class FalsePositivesRemovedTest(unittest.TestCase):
    """The three substring offenders must stay out of the list."""
    def test_pot_bag_class_not_in_list(self):
        for kw in ("pot", "bag", "class"):
            self.assertNotIn(kw, NON_PLANT_KEYWORDS)

    def test_sapote_is_a_real_product(self):  # 'pot' used to hit 'sapote'
        self.assertTrue(is_real_product("Black Sapote 'Maher' (Dwarf)"))
        self.assertTrue(is_real_product("White Sapote Suebelle"))

    def test_potted_fruit_kept(self):  # 'pot' used to hit '400mm Pot'
        self.assertTrue(is_real_product("Blood Orange 400mm pot PICK UP ONLY"))
        self.assertTrue(is_real_product("Blueberry Advanced in 200mm Pots"))

    def test_bag_and_class_false_positives_kept(self):
        self.assertTrue(is_real_product("Fraser Island Apple 'Vista' 45Ltr Bag"))
        self.assertTrue(is_real_product("Mulberry Black Classic"))


class JunkStillFilteredTest(unittest.TestCase):
    def test_native_and_ornamental_trees_filtered(self):
        for t in ("Banksia 'Giant Candles'", "Eucalyptus Baby Orange",
                  "Bottlebrush (Callistemon salignus)", "Ornamental Pear Red Spire",
                  "Black Tea-tree (Melaleuca bracteata)"):
            self.assertFalse(is_real_product(t), t)

    def test_consumables_and_merch_filtered(self):
        for t in ("Slow Release Fertiliser 5kg", "Gift Voucher $50",
                  "Seasol 2L", "Garden Gloves", "Book Jaboticaba Revealed"):
            self.assertFalse(is_real_product(t), t)


class RealFruitKeptTest(unittest.TestCase):
    def test_fruit_trees_pass(self):
        for t in ("Mango - Kensington Pride", "Avocado - Hass",
                  "Lychee 'Kwai May Pink'", "Fig - Black Genoa", "Apple Pink Lady"):
            self.assertTrue(is_real_product(t), t)


class JunkPartitionTest(unittest.TestCase):
    """The DEC-200 split: TRUE_JUNK (junk forever) + CATEGORY_KEYWORDS (real
    plants of disabled categories). NON_PLANT_KEYWORDS is derived from them
    and must stay set-equal to the pre-split list while only fruit is enabled."""

    def test_partition_is_disjoint(self):
        overlap = TRUE_JUNK & set(CATEGORY_KEYWORDS)
        self.assertFalse(overlap, f"keywords in both halves: {overlap}")

    def test_union_equals_public_set_today(self):
        # Only "fruit" is enabled, so every category keyword is still junk.
        self.assertEqual(NON_PLANT_KEYWORDS, TRUE_JUNK | set(CATEGORY_KEYWORDS))

    def test_category_hints_are_known_non_fruit_categories(self):
        for kw, cat in CATEGORY_KEYWORDS.items():
            self.assertIn(cat, KNOWN_CATEGORIES, f"{kw}: unknown category {cat}")
            self.assertNotEqual(cat, "fruit", f"{kw}: a fruit keyword cannot be junk")

    def test_enabling_native_unjunks_its_keywords(self):
        derived = derived_non_plant_keywords(("fruit", "native"))
        for kw in ("banksia", "eucalyptus", "melaleuca", "wattle", "acacia",
                   "callistemon", "lomandra"):
            self.assertNotIn(kw, derived, kw)
        # Other disabled categories and true junk stay filtered.
        self.assertIn("cordyline", derived)
        self.assertIn("asparagus", derived)
        self.assertIn("fertiliser", derived)
        self.assertIn("gift voucher", derived)

    def test_native_keyword_evidence_pinned(self):
        # The natives enable should return the ~311 junk-filtered products via
        # these keywords (design doc section 2); pin which keywords are native.
        native = {kw for kw, cat in CATEGORY_KEYWORDS.items() if cat == "native"}
        for kw in ("banksia", "callistemon", "melaleuca", "eucalyptus",
                   "wattle", "acacia", "lomandra", "sheoak", "kurrajong"):
            self.assertIn(kw, native)


class SeedPacketTest(unittest.TestCase):
    def test_seed_packets_excluded_but_not_seedlings(self):
        self.assertTrue(is_seed_packet("Tomato Seeds"))
        self.assertFalse(is_seed_packet("Mango Seedling"))
        self.assertFalse(is_seed_packet("Seedless Grape"))
        self.assertFalse(is_real_product("Chilli Seeds Packet"))


if __name__ == "__main__":
    unittest.main()
