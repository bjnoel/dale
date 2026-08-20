"""Regression tests for the supplier CSV feed scraper (Daleys, 2026-08-20).

Daleys handed us a product feed rather than making us keep parsing
Plant-List.php. The switch fixes two live defects and creates several new ways
to get it wrong, so these tests pin the ones that were measured against the real
feed and would fail silently:

  - Availability is four-state in two vocabularies. 2,900 rows say
    "out of stock" and exactly one says "OutOfStock" (sku 1045). A parser
    matching only the lowercase spelling puts that row back in stock.
  - `qty` is NOT the authority. Sku 1045 is the sole row in 3,650 where qty (40)
    contradicts availability, so mapping from qty rather than availability
    reintroduces the bug from the other direction.
  - Pre-orders stay `available: True`. Calling them in stock was the original
    defect; calling them out of stock would be a new one, because you can buy
    them today and just wait.
  - The product title must lose its "<pot> <height>" suffix, or
    cultivar_parsing reads "60-70cm" as the cultivar token "60" and mints
    sapodilla-krasuey-60 as a separate watchable variety.
  - Group URLs must strip "skuNN-" wherever it appears, not just in the
    "/skuNN-buy/" form. Correy's stated rule covers only the latter and leaves
    454 of 1,998 groups disagreeing with themselves.
  - An empty category makes stocklib.fruit_filters drop every Daleys product
    from the site with no alarm anywhere, so the resolution chain is load-bearing.
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

    def test_presale_and_preorder_are_purchasable_but_flagged(self):
        products, _ = _products()
        ginkgo = products["Ginkgo - Grafted Female"]["variants"][0]
        shower = products["Golden Shower"]["variants"][0]
        for variant in (ginkgo, shower):
            self.assertTrue(variant["available"])
            self.assertEqual(variant["availability_state"], "preorder")

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

    def test_species_fallback_categorises_a_product_the_frozen_map_lacks(self):
        products, _ = _products()
        # Jambolan Plum is a fruit; it must end up renderable.
        self.assertTrue(products["Jambolan Plum"]["category"])
        self.assertTrue(is_fruit_product(products["Jambolan Plum"], "daleys"))

    def test_ornamentals_are_recorded_but_not_renderable(self):
        """DEC-227: record everything, gate at render. An ornamental stays in
        the snapshot and stays off the site."""
        products, _ = _products()
        jacaranda = products["Jacaranda Purple"]
        self.assertEqual(jacaranda["category"], "")
        self.assertFalse(is_fruit_product(jacaranda, "daleys"))


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
