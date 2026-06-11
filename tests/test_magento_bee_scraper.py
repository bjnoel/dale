"""
Tests for tools/scrapers/bee/magento_bee_scraper.py -- product extraction
from Magento product pages (beewise.com.au).

Run from repo root with:
    python3 -m unittest discover tests/

Regression (2026-06-11): the Magento dataLayer productPage event on beewise
carries the ex-GST price (e.g. 232.73), while the JSON-LD Product offer
carries the inc-GST price the site displays (256.00). The scraper was
reading the event price, so every beewise listing showed ~9% under the
real price. extract_product must prefer the JSON-LD offer price.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BEE_SCRAPERS = REPO_ROOT / "tools" / "scrapers" / "bee"


def _load(path: Path):
    sys.path.insert(0, str(BEE_SCRAPERS))
    try:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(BEE_SCRAPERS))


scraper = _load(BEE_SCRAPERS / "magento_bee_scraper.py")

PAGE_URL = "https://www.beewise.com.au/honey-tank-konigin-25l.html"

# Trimmed from the real beewise product page: dataLayer event price is
# ex-GST, JSON-LD offer price is the displayed inc-GST price.
EVENT_SNIPPET = (
    '<script>dataLayer.push({"event":"productPage","product":'
    '{"id":"1765","sku":"KA-25","parent_sku":"KA-25","product_type":"simple",'
    '"name":"Honey Tank SS with Honey Gate & Handles - 25L",'
    '"price":232.73,"category":"Beewise Products"}});</script>'
)

JSON_LD_SNIPPET = (
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org/","@type":"Product",'
    '"name":"Honey Tank SS with Honey Gate &amp; Handles - 25L","sku":"KA-25",'
    '"offers":{"@type":"Offer","priceCurrency":"AUD",'
    '"availability":"https://schema.org/InStock","price":"256.00"}}'
    "</script>"
)

BREADCRUMB_SNIPPET = (
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[]}'
    "</script>"
)


class ExtractProductPrice(unittest.TestCase):
    def test_prefers_json_ld_inc_gst_price_over_event_price(self):
        html = EVENT_SNIPPET + BREADCRUMB_SNIPPET + JSON_LD_SNIPPET
        product = scraper.extract_product(PAGE_URL, html)
        self.assertIsNotNone(product)
        self.assertEqual(product["price"], 256.00)

    def test_falls_back_to_event_price_without_json_ld(self):
        product = scraper.extract_product(PAGE_URL, EVENT_SNIPPET)
        self.assertIsNotNone(product)
        self.assertEqual(product["price"], 232.73)

    def test_falls_back_when_json_ld_price_is_malformed(self):
        bad_ld = JSON_LD_SNIPPET.replace('"price":"256.00"', '"price":"POA"')
        product = scraper.extract_product(PAGE_URL, EVENT_SNIPPET + bad_ld)
        self.assertIsNotNone(product)
        self.assertEqual(product["price"], 232.73)

    def test_availability_still_read_from_json_ld(self):
        html = EVENT_SNIPPET + JSON_LD_SNIPPET
        product = scraper.extract_product(PAGE_URL, html)
        self.assertTrue(product["available"])


class ParseJsonLdPrice(unittest.TestCase):
    def test_offer_dict(self):
        blocks = [{"@type": "Product", "offers": {"price": "256.00"}}]
        self.assertEqual(scraper.parse_json_ld_price(blocks), 256.00)

    def test_offer_list_takes_first(self):
        blocks = [{"@type": "Product", "offers": [{"price": "10.50"}, {"price": "12.00"}]}]
        self.assertEqual(scraper.parse_json_ld_price(blocks), 10.50)

    def test_aggregate_offer_low_price(self):
        blocks = [{"@type": "Product",
                   "offers": {"@type": "AggregateOffer", "lowPrice": "99.00", "highPrice": "120.00"}}]
        self.assertEqual(scraper.parse_json_ld_price(blocks), 99.00)

    def test_non_product_blocks_ignored(self):
        blocks = [{"@type": "BreadcrumbList", "itemListElement": []}]
        self.assertIsNone(scraper.parse_json_ld_price(blocks))

    def test_empty(self):
        self.assertIsNone(scraper.parse_json_ld_price([]))
