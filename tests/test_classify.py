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
    """The substring offenders must stay out of the list."""
    def test_pot_bag_class_tool_not_in_list(self):
        for kw in ("pot", "bag", "class", "tool"):
            self.assertNotIn(kw, NON_PLANT_KEYWORDS)

    def test_toolangi_strawberry_is_real(self):  # 'tool' used to hit 'Toolangi'
        self.assertTrue(is_real_product("Strawberry - Toolangi Choice"))
        self.assertFalse(is_real_product(
            "Dwarfing Tool for Cincturing or Girdling Fruit Trees"))
        self.assertFalse(is_real_product("Garden Tools Set"))

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


class DashboardJunkDeforkTest(unittest.TestCase):
    """build-dashboard derives its junk filter from the shared halves
    (DAL-194 P1.5): true junk + ornamental/vegetable keywords, with native
    keywords deliberately exempt so the live melaleuca/wattle dashboard rows
    survive as unclassified search results."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "build_dashboard", SCRAPERS / "build-dashboard.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cls.dashboard_junk = mod.DASHBOARD_JUNK_KEYWORDS

    def test_upstreamed_dashboard_keywords_in_true_junk(self):
        for kw in ("combo pack", "starter kit", "tree sealant",
                   "end stop terminator"):
            self.assertIn(kw, TRUE_JUNK, kw)

    def test_dashboard_filter_composition(self):
        self.assertTrue(TRUE_JUNK <= self.dashboard_junk)
        for kw in ("ornamental", "cordyline", "asparagus"):
            self.assertIn(kw, self.dashboard_junk, kw)

    def test_native_keywords_exempt_from_dashboard_filter(self):
        for kw, cat in CATEGORY_KEYWORDS.items():
            if cat == "native":
                self.assertNotIn(kw, self.dashboard_junk, kw)


class SeedPacketTest(unittest.TestCase):
    def test_seed_packets_excluded_but_not_seedlings(self):
        self.assertTrue(is_seed_packet("Tomato Seeds"))
        self.assertFalse(is_seed_packet("Mango Seedling"))
        self.assertFalse(is_seed_packet("Seedless Grape"))
        self.assertFalse(is_real_product("Chilli Seeds Packet"))



class WordAwareJunkTest(unittest.TestCase):
    """1.3: junk keywords matched as substrings, junking real plants whose
    names merely contain one. Precedent: bare "tool" was removed once because
    it ate "Strawberry - Toolangi Choice"; the fix was never generalised.
    Every title below was live on 2026-08-20.
    """

    def test_substring_casualties_are_kept(self):
        for title in ("Grevillea 'Ellabella' - Large",              # label
                      "Peperomia Red Stem (Peperomia glabella)",    # label
                      "Black Locust Frisia (Robinia pseudoacacia)", # acacia
                      "Jack Pine (Pinus banksiana)",                # banksia
                      "Flax Lily Seaspray (Dianella revoluta)"):    # spray
            with self.subTest(title=title):
                self.assertTrue(is_real_product(title))

    def test_toolangi_still_safe(self):
        self.assertTrue(is_real_product("Strawberry - Toolangi Choice"))

    def test_plural_junk_still_junked(self):
        """The optional plural is load-bearing. Word boundaries alone would
        have leaked these seven back onto the site, because the keywords are
        singular and the products are not.
        """
        for title in ("Bonsai Bags 15 litre", "Bonsai Bags 75 litre",
                      "Planter Bags - 4 Litre x 25", "Woven Planter Grow Bags",
                      "Grow Bag With Handles 45 Litre"):
            with self.subTest(title=title):
                self.assertFalse(is_real_product(title))

    def test_multi_word_entries_stay_phrase_matches(self):
        for title in ("$100 Gift Card", "Good Earth Premium Potting Mix",
                      "Exclusion Net - 6m x 6m", "Mushroom Kit - Blue Oyster",
                      "Grafting Tape - Parafilm"):
            with self.subTest(title=title):
                self.assertFalse(is_real_product(title))

    def test_ordinary_junk_unaffected(self):
        for title in ("Irrigation 12mm connector", "Grafting Workshop",
                      "1L Searles Ecofend", "Bug Beater - Natural Pyrethrum Spray 1L",
                      "Biochar (1L)", "Dinofert Organic Complete Fertilizer"):
            with self.subTest(title=title):
                self.assertFalse(is_real_product(title))


class PostageKeywordTest(unittest.TestCase):
    """"postage" had a 100% false-positive rate on the live catalogue: all 13
    matches were real citrus trees at heaven-on-earth, which suffixes titles
    with "QLD POSTAGE ONLY" as a shipping note.

    Word boundaries do NOT fix this one, because "postage" is a whole word
    there. That is the point of pinning it separately: 1.3's word-awareness
    and 1.3's keyword removal are two different fixes for two different bugs,
    and the audit doc originally attributed all four of its casualties to the
    first.
    """

    def test_qld_postage_only_citrus_recovered(self):
        for title in (
            "Blood Orange Fruit Tree Cara Cara (Already Fruiting) QLD POSTAGE ONLY",
            "Finger Lime Tree Jali Red MARCOT (QLD POSTAGE ONLY)",
            "Imperial Mandarin (Already Fruiting) QLD POSTAGE ONLY",
            "Key Lime Tree (Already Fruiting) QLD POSTAGE ONLY",
            "Lemon Tree Meyer (Already Fruiting) QLD POSTAGE ONLY",
            "Lime Tree KAFFIR Already Fruiting (QLD POSTAGE ONLY)",
            "Pink Pomelo Fruit Tree (Already Fruiting) QLD POSTAGE ONLY",
            "Tangelo Minneola Tree (Already Fruiting) QLD POSTAGE ONLY",
        ):
            with self.subTest(title=title):
                self.assertTrue(is_real_product(title))

    def test_actual_shipping_line_items_still_junked(self):
        """The keywords that earn their place stay."""
        for title in ("Same Day Delivery", "Shipping", "Freight Charge",
                      "Delivery Charge"):
            with self.subTest(title=title):
                self.assertFalse(is_real_product(title))

    def test_sea_spray_and_wire_vine_are_not_fixed_by_word_awareness(self):
        """Honest record of what 1.3 does NOT do. The audit listed these as
        substring casualties, but "spray" and "wire" are whole words in them.

        "spray" stays in TRUE_JUNK: it has four genuine junk matches (White
        Oil Spray, Bug Beater, Ecofend) and its false positives are
        ornamentals that the per-nursery fruit filter drops anyway.
        "wire" was removed, because all four of its live matches were real
        plants, but they are ornamentals so nothing new reaches the site.
        """
        self.assertFalse(is_real_product("Grevillea 'Sea Spray'"))
        self.assertTrue(is_real_product("Wire Vine (Muehlenbeckia complexa)"))


class DashboardJunkSiteTest(unittest.TestCase):
    """The second junk site. build-dashboard.py:474 inlined its own substring
    test over its own keyword set and never called is_real_product, so fixing
    classify.py alone left the homepage dropping the same products.
    """

    def test_dashboard_uses_the_shared_predicate(self):
        import importlib
        dashboard = importlib.import_module("build-dashboard")
        from stocklib.classify import matches_keyword
        self.assertIs(dashboard.matches_keyword, matches_keyword)

    def test_dashboard_keyword_set_is_word_aware_too(self):
        import importlib
        dashboard = importlib.import_module("build-dashboard")
        from stocklib.classify import matches_keyword
        kws = dashboard.DASHBOARD_JUNK_KEYWORDS
        # freed by word-awareness on the dashboard path specifically
        self.assertFalse(matches_keyword("Grevillea 'Ellabella' - Large", kws))
        self.assertFalse(matches_keyword("Peperomia Red Stem (Peperomia glabella)", kws))
        # recovered by the postage removal, on the dashboard path
        self.assertFalse(matches_keyword(
            "Lemon Tree Meyer (Already Fruiting) QLD POSTAGE ONLY", kws))
        # still junk, including the plural
        self.assertTrue(matches_keyword("Bonsai Bags 15 litre", kws))
        self.assertTrue(matches_keyword("$100 Gift Card", kws))



class SeedDescriptorTest(unittest.TestCase):
    """1.4, first half. `\\bseeds?\\b` deleted any title containing the word,
    including titles where "seed" describes how a plant was raised, names a
    trait, or is part of the plant's own name. Six live casualties on
    2026-08-20; the other 100 seed-matching titles are genuine packets and are
    unaffected.

    The second half of 1.4 (splitting the seed test out of is_real_product and
    carrying a per-product seed flag through 13 consumers) is NOT done here.
    See docs/scraper-category-audit.md.
    """

    def test_seed_as_a_trait_is_not_a_packet(self):
        """Small-seed is a prized lychee trait, which is why it is in the
        title at all."""
        self.assertFalse(is_seed_packet("Lychee Lin San Sue (Small Seed)"))
        self.assertTrue(is_real_product("Lychee Lin San Sue (Small Seed)"))

    def test_seed_as_propagation_method_is_not_a_packet(self):
        for title in ("Seed Grown Mango",
                      "Grass Tree seed grown (Xanthorrhoea latifolia)",
                      "Pomegranate Shepards Special Organic -60-80cm "
                      "(Option For Seed Grown Also)",
                      "Custard Apple grown from seed",
                      "Mango seed-raised"):
            with self.subTest(title=title):
                self.assertFalse(is_seed_packet(title))
                self.assertTrue(is_real_product(title))

    def test_seed_in_the_plants_own_name_is_not_a_packet(self):
        for title in ("Seed of Heaven",
                      "Seed of Heaven - Aframomum sp uganda",
                      "Seed of Paradise Ginger"):
            with self.subTest(title=title):
                self.assertFalse(is_seed_packet(title))

    def test_real_seed_packets_are_still_packets(self):
        """100 live titles, the bulk of them guildford and forever-seeds."""
        for title in ("CHESTNUT TREE ( Castana Sativa ) Seed",
                      "BLACKBERRY  ( Rubus x Species) Seed",
                      "CURRANT RED ( Ribes Rubrum )  Seeds",
                      "Basil Seeds", "Apple Seeds", "Tomato Seed Packet",
                      "FINGER LIME - NATIVE AUSTRALIAN CITRUS CAVIAR "
                      "(Citrus Australiasica) Seed \" RICKS RED \""):
            with self.subTest(title=title):
                self.assertTrue(is_seed_packet(title))
                self.assertFalse(is_real_product(title))

    def test_seedling_and_seedless_still_exempt(self):
        for title in ("Mango Seedling", "Watermelon Seedless",
                      "Hazelnut Seedling (Corylus avellana)"):
            with self.subTest(title=title):
                self.assertFalse(is_seed_packet(title))


if __name__ == "__main__":
    unittest.main()
