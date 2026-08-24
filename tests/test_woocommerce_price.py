"""
Regression tests for woocommerce_scraper.parse_store_price.

The bug (found 2026-08-24 from the Dwarf Moorpark Apricot row on the homepage):
the WooCommerce Store API returns prices as STRINGS in minor units, so a store
that publishes no price returns "0" -- which is truthy in Python. The old guard
was `float(price_raw) / 100 if price_raw else None`, so "0" sailed through and
became the real price $0.00.

That 0.0 then degraded twice more: build-dashboard.py wrote `null` for it
(0.0 is falsy) and dashboard.js rendered an empty string, so the row showed no
price at all. Meanwhile the row still offered "Alert me if the price drops",
which send_variety_alerts.qualifying_drop() refuses to fire on old_price <= 0.

PlantNet is the live case: it is the retail arm of a wholesale breeder and 79 of
its 110 fruit-tree SKUs are "find a stockist", so it reports price "0" with
is_in_stock true. Rayners Orchard has the same shape on 38 of 399.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from woocommerce_scraper import normalize_product, parse_store_price  # noqa: E402


class TestParseStorePrice(unittest.TestCase):
    def test_string_zero_is_unpublished_not_free(self):
        # The actual defect. "0" is truthy, so the old guard missed it.
        self.assertIsNone(parse_store_price("0"))

    def test_numeric_zero_is_unpublished(self):
        self.assertIsNone(parse_store_price(0))

    def test_none_and_empty_are_unpublished(self):
        self.assertIsNone(parse_store_price(None))
        self.assertIsNone(parse_store_price(""))

    def test_garbage_is_unpublished_rather_than_raising(self):
        self.assertIsNone(parse_store_price("POA"))

    def test_real_price_converts_from_minor_units(self):
        self.assertEqual(parse_store_price("4800"), 48.00)
        self.assertEqual(parse_store_price("5995"), 59.95)

    def test_minor_unit_is_honoured(self):
        self.assertEqual(parse_store_price("4800", 2), 48.00)
        self.assertEqual(parse_store_price("48", 0), 48.00)

    def test_sub_dollar_price_survives(self):
        # Guard against a naive `price > 1` style fix.
        self.assertEqual(parse_store_price("50"), 0.50)


class TestNormalizeProductPrice(unittest.TestCase):
    """The PlantNet product from the live API, verbatim, end to end."""

    CONFIG = {"name": "PlantNet"}

    def _raw(self, price):
        return {
            "name": "Dwarf Moorpark Apricot",
            "permalink": "https://plantnet.com.au/shop/fruit-trees/apricots/dwarf-moorpark-apricot/",
            "prices": {
                "price": price,
                "regular_price": price,
                "currency_code": "AUD",
                "currency_minor_unit": 2,
            },
            "is_in_stock": True,
            "categories": [{"name": "Apricot trees"}],
            "tags": [],
        }

    def test_unpriced_plantnet_product_has_no_price(self):
        p = normalize_product(self._raw("0"), "plantnet", self.CONFIG)
        self.assertIsNone(p["min_price"])
        self.assertIsNone(p["max_price"])
        self.assertIsNone(p["variants"][0]["price"])

    def test_unpriced_product_is_still_in_stock(self):
        # Losing the price must not lose the availability -- the item IS buyable,
        # just not priced online, so it still belongs in the dataset.
        p = normalize_product(self._raw("0"), "plantnet", self.CONFIG)
        self.assertTrue(p["any_available"])
        self.assertTrue(p["variants"][0]["available"])

    def test_priced_product_is_unaffected(self):
        p = normalize_product(self._raw("4800"), "plantnet", self.CONFIG)
        self.assertEqual(p["min_price"], 48.00)
        self.assertEqual(p["variants"][0]["price"], 48.00)


if __name__ == "__main__":
    unittest.main()
