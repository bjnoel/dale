"""
Tests for stocklib.structured_data.product_offer_jsonld (Product + AggregateOffer).

Offers are per nursery listing (the price the page actually shows), not per
pot-size variant, so the markup never claims a price the page does not display.
lowPrice/highPrice/offerCount derive from those per-nursery prices.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib import structured_data as sd


def parse(script: str) -> dict:
    m = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', script, re.S)
    assert m, f"no ld+json found in {script!r}"
    return json.loads(m.group(1))


PRODUCTS = [
    {"title": "Avocado - Hass", "url": "https://daleys.test/hass", "nursery_name": "Daleys", "price": 34.95, "available": True},
    {"title": "Avocado - Hass", "url": "https://primal.test/hass", "nursery_name": "Primal Fruits", "price": 42.0, "available": True},
    {"title": "Avocado - Hass", "url": "https://oos.test/hass", "nursery_name": "OOS Nursery", "price": 39.0, "available": False},
]


class ProductOfferTest(unittest.TestCase):
    def test_aggregate_offer_shape(self):
        data = parse(sd.product_offer_jsonld(
            "Avocado - Hass", "https://treestock.com.au/variety/avocado-hass.html",
            PRODUCTS, description="desc"))
        self.assertEqual(data["@type"], "Product")
        self.assertEqual(data["name"], "Avocado - Hass")
        self.assertEqual(data["description"], "desc")
        agg = data["offers"]
        self.assertEqual(agg["@type"], "AggregateOffer")
        self.assertEqual(agg["priceCurrency"], "AUD")
        self.assertEqual(agg["lowPrice"], "34.95")
        self.assertEqual(agg["highPrice"], "42.00")
        self.assertEqual(agg["offerCount"], 3)
        self.assertEqual(len(agg["offers"]), 3)

    def test_availability_per_offer(self):
        agg = parse(sd.product_offer_jsonld("X", "u", PRODUCTS))["offers"]
        avail = {o["seller"]["name"]: o["availability"] for o in agg["offers"]}
        self.assertEqual(avail["Daleys"], "https://schema.org/InStock")
        self.assertEqual(avail["OOS Nursery"], "https://schema.org/OutOfStock")

    def test_dedup_by_url(self):
        dup = PRODUCTS + [dict(PRODUCTS[0])]  # same url again
        agg = parse(sd.product_offer_jsonld("X", "u", dup))["offers"]
        self.assertEqual(agg["offerCount"], 3)  # not 4

    def test_empty_when_no_priced_products(self):
        none_priced = [{"title": "x", "url": "u", "nursery_name": "N", "price": 0, "available": True}]
        self.assertEqual(sd.product_offer_jsonld("X", "u", none_priced), "")
        self.assertEqual(sd.product_offer_jsonld("X", "u", []), "")

    def test_single_offer_low_equals_high(self):
        agg = parse(sd.product_offer_jsonld("X", "u", [PRODUCTS[0]]))["offers"]
        self.assertEqual(agg["lowPrice"], "34.95")
        self.assertEqual(agg["highPrice"], "34.95")
        self.assertEqual(agg["offerCount"], 1)

    def test_offer_fields(self):
        o = parse(sd.product_offer_jsonld("X", "u", [PRODUCTS[0]]))["offers"]["offers"][0]
        self.assertEqual(o["@type"], "Offer")
        self.assertEqual(o["price"], "34.95")
        self.assertEqual(o["priceCurrency"], "AUD")
        self.assertEqual(o["url"], "https://daleys.test/hass")
        self.assertEqual(o["seller"]["name"], "Daleys")

    def test_summary_only_omits_offers_array(self):
        # Aggregation pages (species/compare) emit the summary without the
        # potentially-hundreds-long individual Offer list.
        agg = parse(sd.product_offer_jsonld("X", "u", PRODUCTS, include_offers=False))["offers"]
        self.assertEqual(agg["@type"], "AggregateOffer")
        self.assertEqual(agg["offerCount"], 3)
        self.assertEqual(agg["lowPrice"], "34.95")
        self.assertEqual(agg["highPrice"], "42.00")
        self.assertNotIn("offers", agg)


if __name__ == "__main__":
    unittest.main()
