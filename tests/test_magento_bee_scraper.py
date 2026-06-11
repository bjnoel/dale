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
import json
import os
import sys
import tempfile
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


RAW_PRODUCT = {
    "page_url": PAGE_URL,
    "id": 1765,
    "sku": "KA-25",
    "name": "Honey Tank SS - 25L",
    "price": 256.00,
    "product_type": "simple",
    "available": True,
}


class SaveSnapshot(unittest.TestCase):
    """Regression (2026-06-11): beewise's latest.json was a symlink to the
    2026-04-19 dated snapshot, so every scrape rewrote that dated file."""

    def test_latest_json_symlink_replaced_not_written_through(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["DALE_DATA_DIR"] = td
            try:
                mod = _load(BEE_SCRAPERS / "magento_bee_scraper.py")
            finally:
                del os.environ["DALE_DATA_DIR"]
            retailer_dir = Path(td) / "bee-stock" / "beewise"
            retailer_dir.mkdir(parents=True)
            dated_old = retailer_dir / "2026-04-19.json"
            dated_old.write_text('{"old": true}')
            (retailer_dir / "latest.json").symlink_to(dated_old)

            mod.save_snapshot("beewise", [RAW_PRODUCT], {"name": "Beewise"})

            latest = retailer_dir / "latest.json"
            self.assertFalse(latest.is_symlink())
            self.assertEqual(json.loads(latest.read_text())["product_count"], 1)
            self.assertEqual(dated_old.read_text(), '{"old": true}')


class ScrapeErrorRateGuard(unittest.TestCase):
    """Regression (2026-06-11): beewise started rate-limiting (429) mid-run;
    a partial snapshot must not be saved over a complete one."""

    def _scrape_with_error_rate(self, n_errors, n_total=10):
        mod = _load(BEE_SCRAPERS / "magento_bee_scraper.py")
        mod.fetch_sitemap_urls = lambda domain: [f"u{i}" for i in range(n_total)]
        mod.fetch_and_parse = lambda u: (
            ("error", u, "HTTP Error 429: Too Many Requests")
            if int(u[1:]) < n_errors
            else ("ok", u, dict(RAW_PRODUCT))
        )
        return mod.scrape_magento("beewise", {"name": "Beewise", "domain": "example.com"})

    def test_aborts_on_high_error_rate(self):
        self.assertEqual(self._scrape_with_error_rate(n_errors=5), [])

    def test_keeps_results_on_low_error_rate(self):
        self.assertEqual(len(self._scrape_with_error_rate(n_errors=1)), 9)
