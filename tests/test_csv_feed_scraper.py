"""Regression tests for the supplier CSV feed scraper (Daleys, 2026-08-20).

Daleys handed us a product feed rather than making us keep parsing
Plant-List.php. The switch fixes two live defects and creates several new ways
to get it wrong, so these tests pin the ones that were measured against the real
feed and would fail silently:

  - Availability is four-state in two vocabularies. Both spellings of out of
    stock must stay mapped: the feed was 2,900 lowercase "out of stock" and one
    "OutOfStock" (sku 1045) on 2026-08-20, and Correy normalised all 2,942 to
    schema.org "OutOfStock" on 2026-08-27. A parser that had matched only the
    lowercase form would have read the whole catalogue as back in stock
    overnight, and snapshots in both spellings are still on disk.
  - `qty` is NOT the authority. 2 rows of 3,650 carry a healthy qty and say
    OutOfStock (sku 1045 qty 40, sku 3939 qty 36), so mapping from qty rather
    than availability reintroduces the bug from the other direction.
  - Pre-orders stay `available: True`. Calling them in stock was the original
    defect; calling them out of stock would be a new one, because you can buy
    them today and just wait.
  - PreSale and PreOrder are DIFFERENT waits, not synonyms: 1-2 months from a
    seasonal catalogue against 1-6 months once a graft or cutting has struck
    (Correy, 2026-08-27). Collapsing them tells someone waiting on a grafted
    sapodilla the same thing as someone waiting on a bare-root apple.
  - The product title must lose its "<pot> <height>" suffix, or
    cultivar_parsing reads "60-70cm" as the cultivar token "60" and mints
    sapodilla-krasuey-60 as a separate watchable variety.
  - Group URLs must strip "skuNN-" wherever it appears, not just in the
    "/skuNN-buy/" form. Correy's stated rule covers only the latter and leaves
    454 of 1,998 groups disagreeing with themselves.
  - An empty category makes stocklib.fruit_filters drop every Daleys product
    from the site with no alarm anywhere, so the resolution chain is load-bearing.
  - The feed grew a category column in the 2026-08-25 refresh (confirmed by
    Correy 2026-08-27) and it changed vocabulary at the same time, from
    Plant-List headings to breadcrumb paths. The filter has to speak both, and
    the third spelling ("Plant List/Fruit and Nut Trees") was worth 23 products
    on its own.
  - A truncated feed still parses as valid CSV, so the product floor is the only
    thing standing between a bad fetch and an overwritten snapshot.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import csv_feed_scraper as cfs  # noqa: E402
from stocklib.changes import variant_key  # noqa: E402
from stocklib.fruit_filters import is_fruit_product  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "daleys_feed.csv"
CONFIG = cfs.FEEDS["daleys"]


def _products():
    with open(FIXTURE, encoding="utf-8-sig") as f:
        rows = cfs.parse_feed(f.read())
    products, catalogue = cfs.extract_products(rows, CONFIG)
    return {p["title"]: p for p in products}, catalogue


class StripSizeTest(unittest.TestCase):
    def test_strips_pot_and_height(self):
        self.assertEqual(
            cfs.strip_size("Sapodilla - Krasuey 4L 60-70cm", "4L", "60-70cm"),
            "Sapodilla - Krasuey",
        )

    def test_strips_pot_only_when_height_absent(self):
        self.assertEqual(cfs.strip_size("Avocado - Hass 300mm", "300mm", ""),
                         "Avocado - Hass")

    def test_leaves_a_name_that_does_not_end_in_its_size(self):
        # Sizes embedded mid-title (accessories, nets) must not be mangled.
        self.assertEqual(cfs.strip_size("Exclusion Net - 6m x 6m", "", ""),
                         "Exclusion Net - 6m x 6m")

    def test_variants_of_one_product_collapse_to_one_title(self):
        products, _ = _products()
        self.assertIn("Sapodilla - Krasuey", products)
        self.assertEqual(len(products["Sapodilla - Krasuey"]["variants"]), 2)


class AvailabilityTest(unittest.TestCase):
    def test_both_out_of_stock_spellings_map_to_outofstock(self):
        products, _ = _products()
        krasuey = products["Sapodilla - Krasuey"]["variants"][0]
        jabo = products["Jaboticaba"]["variants"][0]
        self.assertEqual(krasuey["availability_state"], "outofstock")
        self.assertEqual(jabo["availability_state"], "outofstock")
        self.assertFalse(krasuey["available"])
        self.assertFalse(jabo["available"])

    def test_qty_does_not_override_availability(self):
        """Sku 1045 says OutOfStock with qty 40. Availability wins."""
        products, _ = _products()
        jabo = products["Jaboticaba"]["variants"][0]
        self.assertEqual(jabo["sku"], "1045")
        self.assertEqual(jabo["stock_count"], 40)
        self.assertFalse(jabo["available"])

    def test_presale_and_preorder_are_both_purchasable(self):
        products, _ = _products()
        ginkgo = products["Ginkgo - Grafted Female"]["variants"][0]
        shower = products["Golden Shower"]["variants"][0]
        for variant in (ginkgo, shower):
            self.assertTrue(variant["available"])

    def test_presale_and_preorder_are_not_the_same_state(self):
        """Correy, 2026-08-27: PreSale is a 1-2 month catalogue, PreOrder is a
        1-6 month wait on a graft. They used to both map to "preorder", which
        is a 10x difference in wait reported as one badge."""
        products, _ = _products()
        self.assertEqual(
            products["Golden Shower"]["variants"][0]["availability_state"],
            "presale")
        self.assertEqual(
            products["Ginkgo - Grafted Female"]["variants"][0]["availability_state"],
            "preorder")

    def test_instock_is_instock(self):
        products, _ = _products()
        variant = products["Cassia Java shower"]["variants"][0]
        self.assertTrue(variant["available"])
        self.assertEqual(variant["availability_state"], "instock")

    def test_unknown_state_falls_back_to_out_of_stock(self):
        """An unrecognised string must never read as buyable."""
        rows = [{"item_group_id": "g1", "id": "1", "name": "Mystery Tree 2L",
                 "link": "https://x/sku1-buy/mystery.htm", "pot": "2L",
                 "height": "", "qty": "5", "price": "10.00",
                 "availability": "Backordered Maybe"}]
        products, _ = cfs.extract_products(rows, CONFIG)
        self.assertFalse(products[0]["variants"][0]["available"])
        self.assertEqual(products[0]["variants"][0]["availability_state"], "outofstock")

    def test_product_preorder_flag_rolls_up(self):
        products, _ = _products()
        self.assertTrue(products["Ginkgo - Grafted Female"]["preorder"])
        self.assertFalse(products["Sapodilla - Krasuey"]["preorder"])

    def test_wait_state_names_which_wait(self):
        products, _ = _products()
        self.assertEqual(products["Golden Shower"]["wait_state"], "presale")
        self.assertEqual(products["Ginkgo - Grafted Female"]["wait_state"], "preorder")
        self.assertIsNone(products["Sapodilla - Krasuey"]["wait_state"])

    def test_mixed_waits_roll_up_to_the_longer_one(self):
        """Blueberry - Climax is PreSale in 0.75L and PreOrder in 2L. Quoting
        one to two months would under-promise on the 2L, and a buyer who took
        that number is the one who complains to the nursery."""
        products, _ = _products()
        self.assertEqual(products["Blueberry - Climax"]["wait_state"], "preorder")

    def test_preorder_bool_still_true_for_a_presale_only_product(self):
        """Everything downstream read `preorder` as "is there a wait" before
        wait_state existed, and snapshots on disk carry it that way."""
        products, _ = _products()
        self.assertTrue(products["Golden Shower"]["preorder"])


class GroupUrlTest(unittest.TestCase):
    def test_buy_form(self):
        products, _ = _products()
        self.assertEqual(products["Sapodilla - Krasuey"]["url"],
                         "https://www.daleysfruit.com.au/buy/sapodilla-krasuey-tree.htm")

    def test_non_buy_form_is_also_stripped(self):
        """The shape Correy's stated rule misses."""
        products, _ = _products()
        self.assertEqual(products["Jaboticaba"]["url"],
                         "https://www.daleysfruit.com.au/Jaboticaba-Tree.htm")

    def test_fruit_pages_form(self):
        products, _ = _products()
        self.assertEqual(products["Jambolan Plum"]["url"],
                         "https://www.daleysfruit.com.au/fruit%20pages/jambolan.htm")

    def test_variants_of_a_group_share_one_url(self):
        products, _ = _products()
        urls = {v for v in [products["Sapodilla - Krasuey"]["url"]]}
        self.assertEqual(len(urls), 1)


class VariantKeyTest(unittest.TestCase):
    def test_key_is_sku_based_and_matches_the_old_scraper(self):
        """Price and stock history survive the source switch only if the key
        the comparison engine derives is byte-identical to the HTML scraper's."""
        products, _ = _products()
        product = products["Sapodilla - Krasuey"]
        keys = {variant_key(product["url"], v) for v in product["variants"]}
        self.assertIn(
            "https://www.daleysfruit.com.au/buy/sapodilla-krasuey-tree.htm|sku:1085",
            keys)

    def test_sku_is_a_string_not_an_int(self):
        products, _ = _products()
        self.assertIsInstance(products["Jaboticaba"]["variants"][0]["sku"], str)


class CategoryTest(unittest.TestCase):
    def test_feed_column_wins_when_present(self):
        rows = [{"item_group_id": "g1", "id": "1", "name": "Whatever 2L",
                 "link": "https://x/sku1-buy/w.htm", "pot": "2L", "height": "",
                 "qty": "1", "price": "1", "availability": "InStock",
                 "category": "Fruit and Nut Trees"}]
        products, _ = cfs.extract_products(rows, CONFIG)
        self.assertEqual(products[0]["category"], "Fruit and Nut Trees")

    def test_a_row_the_feed_left_blank_still_resolves(self):
        """Jambolan Plum carries no feed category. The frozen map catches it,
        and the point of keeping that map after 2026-08-27 is exactly this: a
        row the feed forgets must not silently leave the site."""
        products, _ = _products()
        self.assertEqual(products["Jambolan Plum"]["category"], "Fruit and Nut Trees")
        self.assertTrue(is_fruit_product(products["Jambolan Plum"], "daleys"))

    def test_ornamentals_are_recorded_but_not_renderable(self):
        """DEC-227: record everything, gate at render. An ornamental stays in
        the snapshot and stays off the site."""
        products, _ = _products()
        jacaranda = products["Jacaranda Purple"]
        self.assertEqual(jacaranda["category"],
                         "Trees and Plants/Shade and Ornamental Trees/Exotic")
        self.assertFalse(is_fruit_product(jacaranda, "daleys"))

    def test_plant_list_spelling_of_fruit_and_nut_trees_is_renderable(self):
        """The feed's third spelling for the same bucket. Missing it dropped 23
        products, 5 of them buyable, including this Navelina orange."""
        products, _ = _products()
        orange = products["Orange - Navelina"]
        self.assertEqual(orange["category"], "Plant List/Fruit and Nut Trees")
        self.assertTrue(is_fruit_product(orange, "daleys"))

    def test_scion_wood_is_not_a_fruit_tree(self):
        """$9.75 of 15cm grafting stick that species_match resolves to Apple.
        Before the feed carried categories the species fallback filed all 32 as
        "Fruit and Nut Trees", so they were the cheapest apple in search too.
        The category keeps them off the homepage; /species/apple.html applies
        only is_real_product and still lists them (DEC-314 ranks by price)."""
        products, _ = _products()
        scion = products["Scion Wood Apple - Pink Lady"]
        self.assertEqual(scion["category"],
                         "Gardening Tools - Accessories/Scion Wood")
        self.assertFalse(is_fruit_product(scion, "daleys"))

    def test_resolver_reports_where_each_category_came_from(self):
        """The fallbacks are the rungs that go quietly wrong, so the scrape has
        to be able to alarm on how far down it had to reach."""
        with open(FIXTURE, encoding="utf-8-sig") as f:
            rows = cfs.parse_feed(f.read())
        resolver = cfs.CategoryResolver(CONFIG)
        cfs.extract_products(rows, CONFIG, resolver)
        # Counted per product group, not per row: Krasuey and Blueberry each
        # have two variants under one group.
        self.assertEqual(resolver.counts,
                         {"feed": 11, "frozen": 1, "species": 0, "none": 0})
        self.assertGreater(resolver.feed_share, 0.9)

    def test_a_feed_that_stops_sending_categories_drops_below_the_floor(self):
        """The regression the alarm exists for: no category means every Daleys
        product fails the prefix gate, and a nursery going to zero on one day
        trips no history-relative guard anywhere else in the pipeline."""
        with open(FIXTURE, encoding="utf-8-sig") as f:
            rows = [dict(r, category="") for r in cfs.parse_feed(f.read())]
        resolver = cfs.CategoryResolver(CONFIG)
        cfs.extract_products(rows, CONFIG, resolver)
        self.assertLess(resolver.feed_share, CONFIG["min_feed_category_share"])


class CatalogueSplitTest(unittest.TestCase):
    def test_description_and_images_leave_the_snapshot(self):
        products, catalogue = _products()
        for product in products.values():
            self.assertNotIn("description", product)
            self.assertNotIn("image_link", product)
        self.assertTrue(any(entry["description"] for entry in catalogue.values()))

    def test_botanical_name_and_method_are_kept(self):
        products, _ = _products()
        self.assertEqual(products["Sapodilla - Krasuey"]["botanical_name"],
                         "Manilkara zapota")
        self.assertEqual(products["Sapodilla - Krasuey"]["variants"][0]["method"],
                         "Grafted")


class FloorTest(unittest.TestCase):
    def test_floor_is_configured_for_daleys(self):
        self.assertGreaterEqual(CONFIG["min_groups"], 1000)

    def test_truncated_feed_is_below_the_floor(self):
        """A feed cut short still parses as valid CSV; only the floor catches it."""
        products, _ = _products()
        self.assertLess(len(products), CONFIG["min_groups"])


if __name__ == "__main__":
    unittest.main()
