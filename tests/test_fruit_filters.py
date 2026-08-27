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

    # --- 1.2: build-time audit of the other configured filters -------------
    # Of the 12 configured nurseries only three are restrictive (ladybird
    # tags, daleys categories, forever-seeds title_include); the other nine
    # are mode "all" and cannot drop anything. Measured against live
    # snapshots on 2026-08-20.

    def test_daleys_specials_is_a_merchandising_bucket_not_a_category(self):
        """Daleys' "Specials" REPLACES the taxonomy category rather than
        adding to it, so a fruit tree put on special dropped off treestock
        entirely. That is backwards: a discounted rare fruit tree is the most
        interesting event we have, and it is what feeds the price-drop alerts.

        Live on 2026-08-20 the bucket held 5 products, one of them a real
        tree ("Papaya - Broad Leaf", which resolves to Papaya).
        """
        self.assertTrue(is_fruit_product(
            {"title": "Papaya - Broad Leaf", "category": "Specials"}, "daleys"))

    def test_daleys_specials_junk_still_dropped_downstream(self):
        """Specials is a mixed bucket, so it leans on the junk gate rather
        than on the category filter. The other four live members must not
        reach the site.
        """
        import daily_digest
        for title in ("$50 Gift Voucher by Email",
                      "End Stop Terminator 12mm",
                      "Eucalyptus - River Red Gum"):
            with self.subTest(title=title):
                self.assertFalse(daily_digest._digest_product_filter(
                    {"title": title, "category": "Specials"}, "daleys"))
        self.assertTrue(daily_digest._digest_product_filter(
            {"title": "Papaya - Broad Leaf", "category": "Specials"}, "daleys"))

    def test_daleys_rainforest_trees_stays_excluded(self):
        """Deliberately NOT included, and the reason is a landmine.

        "Rainforest Trees" holds 36 products including Blue Quandong, Candle
        Nut and Native Ginger, which look in scope. It also holds
        "Fig - Small Leaved" and "Fig - White", rainforest shade figs
        (Ficus obliqua, Ficus virens) that species_match resolves to **Fig**.
        Including the bucket would mint them as edible-fig cultivars on
        /variety/fig. Same bug class as the ornamental crabapple in 1.6a:
        an ornamental whose common name contains a fruit species name.

        Revisit only behind an ornamental guard on the species_match path.
        """
        for title in ("Fig - Small Leaved", "Fig - White", "Blue Quandong",
                      "Native Ginger", "Bleeding Heart", "Red Cedar"):
            with self.subTest(title=title):
                self.assertFalse(is_fruit_product(
                    {"title": title, "category": "Rainforest Trees"}, "daleys"))

    def test_daleys_out_of_scope_buckets_stay_excluded(self):
        """The remaining dropped vocabulary is correctly dropped."""
        for cat in ("Ornamental Native & Exotic", "Gardening Accessories",
                    "Farm and Forestry Trees",
                    "Trees and Plants/Shade and Ornamental Trees/Palm Trees"):
            with self.subTest(cat=cat):
                self.assertFalse(is_fruit_product(
                    {"title": "Whatever", "category": cat}, "daleys"))

    def test_daleys_empty_category_is_the_registry_gap_not_a_filter_gap(self):
        """Was 602 of the 1,998 live daleys rows before Correy added a category
        column on 2026-08-27; now 0. The rule stays anyway.

        The fix was never to include "" here (that would admit gift vouchers,
        Agapanthus and Aspen along with the fruit), and the cost of having
        leaned on the guessing fallbacks instead is now measurable: they filed
        32 scion-wood cuttings and 26 rainforest ornamentals as "Fruit and Nut
        Trees". If the column ever disappears, the alarm is
        csv_feed_scraper's min_feed_category_share, not a loosened rule here.
        """
        self.assertFalse(is_fruit_product(
            {"title": "Achacha", "category": ""}, "daleys"))
        self.assertFalse(is_fruit_product(
            {"title": "$100 Gift Voucher - By Email", "category": ""}, "daleys"))

    def test_daleys_speaks_the_feeds_plant_list_vocabulary(self):
        """The feed spells the same three buckets a third way. Leaving
        "Plant List/" out cost 23 products: 5 buyable, and 18 out of stock but
        watchable, which is the half that matters more. A variety absent from
        the filtered set cannot restock, so a watch on it can never fire."""
        for title, cat in (
            ("Orange - Navelina", "Plant List/Fruit and Nut Trees"),
            ("Kaffir Plum", "Plant List/Fruit and Nut Trees"),
            ("Nectarine - OkeeDokee cv Mesembrine", "Plant List/Fruit and Nut Trees"),
            ("Wongai Plum", "Plant List/Bush Food Plants"),
            ("Cacao", "Plant List/Herbs, Spices & Perennial Vegetables"),
        ):
            with self.subTest(cat=cat):
                self.assertTrue(is_fruit_product(
                    {"title": title, "category": cat}, "daleys"))

    def test_daleys_plant_list_still_drops_what_is_not_fruit(self):
        """"Plant List/" is not a blanket pass: it is a prefix on the same
        three buckets, and its other children are correctly out of scope."""
        for cat in ("Plant List/Gardening Accessories",
                    "Plant List/Ornamental Plants Australia",
                    "Plant List/Farm Trees"):
            with self.subTest(cat=cat):
                self.assertFalse(is_fruit_product(
                    {"title": "Whatever", "category": cat}, "daleys"))

    def test_daleys_scion_wood_is_not_a_fruit_tree(self):
        """32 groups of 15cm grafting stick at $9.75, named by cultivar.
        species_match resolves "Scion Wood Apple - Pink Lady" to Apple, so
        while the species fallback was filing them as fruit they sat on the
        species and state pages as the cheapest listing for their fruit,
        undercutting real trees 3-5x on pages that rank by price (DEC-314).

        They mint no variety slug (product_variety_slug returns None), so the
        damage never reached /variety. Price rank was the whole of it, and
        price rank is what those pages are for.
        """
        for title in ("Scion Wood Apple - Pink Lady",
                      "Scion Wood Cherry - Stella",
                      "Scion Wood Wampee - Guy Sam"):
            with self.subTest(title=title):
                self.assertFalse(is_fruit_product(
                    {"title": title,
                     "category": "Gardening Tools - Accessories/Scion Wood"},
                    "daleys"))

    def test_daleys_feed_rainforest_paths_stay_excluded(self):
        """Same landmine as the bare "Rainforest Trees" heading above, in the
        breadcrumb vocabulary the feed uses since 2026-08-27."""
        for cat in ("Trees and Plants/Rainforest Trees/Secondary/Mature",
                    "Trees and Plants/Rainforest Trees/Understorey Plants",
                    "Trees and Plants/Rainforest Trees/Pioneer Plants"):
            with self.subTest(cat=cat):
                self.assertFalse(is_fruit_product(
                    {"title": "Fig - Small Leaved", "category": cat}, "daleys"))

    def test_forever_seeds_whitelist_drops_only_herbs(self):
        """forever-seeds is the third restrictive filter. Live: 82 products,
        36 pass. Everything it drops that is also a real product is a herb
        (spearmint, oregano, patchouli, sawtooth coriander), which is out of
        scope for a fruit site and is Phase 2's question, not Phase 1's.
        """
        for title in ("SPEARMINT HERB (Mentha spicata) Organic Plant",
                      "OREGANO (Origanum vulgare) Organic Herb Plant"):
            with self.subTest(title=title):
                self.assertFalse(is_fruit_product({"title": title},
                                                  "forever-seeds"))

    def test_only_three_nurseries_have_a_restrictive_filter(self):
        """The other nine configured entries are mode "all" and the 15
        unconfigured nurseries default open, so neither can drop fruit. If a
        fourth restrictive entry is added, audit it the way 1.1/1.2 did
        before this test is updated.
        """
        restrictive = sorted(k for k, v in FRUIT_FILTERS.items()
                             if v.get("mode") != "all")
        self.assertEqual(restrictive, ["daleys", "forever-seeds", "ladybird"])


if __name__ == "__main__":
    unittest.main()
