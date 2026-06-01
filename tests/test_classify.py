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

from stocklib.classify import NON_PLANT_KEYWORDS, is_real_product, is_seed_packet


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


class SeedPacketTest(unittest.TestCase):
    def test_seed_packets_excluded_but_not_seedlings(self):
        self.assertTrue(is_seed_packet("Tomato Seeds"))
        self.assertFalse(is_seed_packet("Mango Seedling"))
        self.assertFalse(is_seed_packet("Seedless Grape"))
        self.assertFalse(is_real_product("Chilli Seeds Packet"))


if __name__ == "__main__":
    unittest.main()
