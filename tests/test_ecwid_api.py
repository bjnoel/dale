"""Regression tests for the Ecwid storefront-API scraper (DAL-205, 2026-06-18).

Primal Fruits' Ecwid store stopped server-rendering JSON-LD into product pages
(every page became a bare SPA shell), so the old HTML scraper parsed 0 products.
The rewrite reads the storefront API instead. These tests pin:

  - parse_catalog_page + extract_product against a real captured API response
    fixture (tests/fixtures/ecwid_catalog_primal_fruits.json), so a field move in
    the API (price/sku/url/stock) is caught rather than silently yielding junk.
  - the runtime host/token discovery regexes.
  - the pagination loop: dedups by product id, stops on an empty page, and aborts
    (writes nothing) on a failed page rather than emitting a partial snapshot.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import ecwid_scraper as es  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ecwid_catalog_primal_fruits.json"


def _load_fixture():
    with open(FIXTURE) as f:
        return json.load(f)


def _by_title(domain="primalfruits.com.au"):
    raw_products, total = es.parse_catalog_page(_load_fixture())
    products = {p["title"]: p for p in (es.extract_product(rp, domain) for rp in raw_products)}
    return products, total, raw_products


class ParseCatalogTest(unittest.TestCase):
    def test_pulls_products_and_total(self):
        raw_products, total = es.parse_catalog_page(_load_fixture())
        self.assertEqual(len(raw_products), 3)
        self.assertEqual(total, 288)  # the real store total at capture time

    def test_empty_and_malformed_responses(self):
        self.assertEqual(es.parse_catalog_page(None), ([], 0))
        self.assertEqual(es.parse_catalog_page({}), ([], 0))
        self.assertEqual(es.parse_catalog_page({"expandedCategories": []}), ([], 0))


class ExtractProductTest(unittest.TestCase):
    def test_in_stock_priced_product_with_sku(self):
        products, _, _ = _by_title()
        p = products["Eugenia zuccarinii"]
        self.assertEqual(p["price"], 50.0)
        self.assertEqual(p["sku"], "EugZaSS")
        self.assertTrue(p["available"])
        self.assertEqual(p["availability_raw"], "InStock")
        self.assertEqual(p["currency"], "AUD")
        # relative directPageUrl is made absolute, slug + product id preserved
        self.assertTrue(p["url"].startswith("https://primalfruits.com.au/products/"))
        self.assertIn("Eugenia-zuccarinii", p["url"])

    def test_sold_out_product_with_null_sku(self):
        products, _, _ = _by_title()
        p = products["Whitman Fibreless Soursop"]
        self.assertFalse(p["available"])
        self.assertEqual(p["availability_raw"], "OutOfStock")
        self.assertEqual(p["sku"], "")          # null variation SKU -> ""
        self.assertEqual(p["price"], 30.0)

    def test_third_product_maps(self):
        products, _, _ = _by_title()
        p = products["Japanese Maple tree"]
        self.assertEqual(p["sku"], "MapJSM")
        self.assertEqual(p["price"], 35.0)
        self.assertTrue(p["available"])

    def test_every_fixture_product_has_required_fields(self):
        # The whole point of the rewrite: no more 0-product snapshots, and every
        # product carries the fields the snapshot/validator needs.
        products, _, raw = _by_title()
        self.assertEqual(len(products), len(raw))
        for p in products.values():
            self.assertTrue(p["title"])
            self.assertTrue(p["url"])
            self.assertIn("available", p)
            self.assertTrue(p["price"] is None or p["price"] >= 0)

    def test_description_is_plain_text(self):
        products, _, _ = _by_title()
        desc = products["Eugenia zuccarinii"]["description"]
        self.assertTrue(desc)
        self.assertNotIn("<", desc)             # HTML tags stripped
        self.assertNotIn(">", desc)

    def test_absolute_url_passed_through(self):
        p = es.extract_product(
            {"name": "X", "urls": {"directPageUrl": "https://other/p/1"}}, "primalfruits.com.au")
        self.assertEqual(p["url"], "https://other/p/1")

    def test_missing_fields_do_not_crash(self):
        p = es.extract_product({}, "primalfruits.com.au")
        self.assertEqual(p["title"], "")
        self.assertEqual(p["price"], None)
        self.assertFalse(p["available"])        # no flag -> treated as sold out


class StripHtmlTest(unittest.TestCase):
    def test_strips_tags_and_unescapes(self):
        self.assertEqual(es._strip_html("<p>Botanical&nbsp;Name:&amp; A</p>"),
                         "Botanical Name:& A")

    def test_empty(self):
        self.assertEqual(es._strip_html(""), "")
        self.assertEqual(es._strip_html(None), "")


class DiscoverStorefrontTest(unittest.TestCase):
    BOOTSTRAP = (
        'var x={apiHost:"https://au-syd3-storefront-api.ecwid.com/storefront/api/v1"};'
        'window.ecwid_script_data={storeId:102345518,publicToken:'
        '"pubbe5c7ca7cd54f189f3b7446553dc4c1f"};'
    )

    def test_extracts_host_and_token(self):
        host, token = es.discover_storefront("102345518", _fetch=lambda *a, **k: self.BOOTSTRAP)
        self.assertEqual(host, "au-syd3-storefront-api.ecwid.com")
        self.assertEqual(token, "pubbe5c7ca7cd54f189f3b7446553dc4c1f")

    def test_bootstrap_unreachable_returns_none_host(self):
        host, token = es.discover_storefront("102345518", _fetch=lambda *a, **k: None)
        self.assertIsNone(host)
        self.assertIsNone(token)


class ScrapeOrchestrationTest(unittest.TestCase):
    """scrape_ecwid pagination/dedup/abort, with the network seams stubbed."""

    CONFIG = {"name": "Primal Fruits Perth", "domain": "primalfruits.com.au",
              "store_id": "102345518", "delay": 0}

    def setUp(self):
        self._orig_discover = es.discover_storefront
        self._orig_fetch = es.fetch_catalog_page
        self._orig_sleep = es.time.sleep
        es.discover_storefront = lambda *a, **k: ("host", "tok")
        es.time.sleep = lambda *a, **k: None

    def tearDown(self):
        es.discover_storefront = self._orig_discover
        es.fetch_catalog_page = self._orig_fetch
        es.time.sleep = self._orig_sleep

    @staticmethod
    def _page(ids, total):
        return {"expandedCategories": [{
            "products": [{"identifier": {"productId": i}, "name": f"P{i}",
                          "urls": {"directPageUrl": f"/products/p{i}"},
                          "defaultOptionsOverrides": {
                              "pricesOverrides": {"basePrice": 10},
                              "variationOverrides": {"sku": f"S{i}", "isSoldOut": False}},
                          "flags": {"isAllVariationsSoldOut": False}} for i in ids],
            "totalProductsCount": total}]}

    def test_paginates_and_dedups_across_pages(self):
        pages = [self._page([1, 2, 3], 5), self._page([3, 4, 5], 5), self._page([], 5)]
        calls = []

        def fake(host, sid, dom, offset, limit, token=None, health=None, **k):
            calls.append(offset)
            return pages[offset // limit] if offset // limit < len(pages) else self._page([], 5)
        es.fetch_catalog_page = fake

        products = es.scrape_ecwid("primal-fruits", self.CONFIG)
        titles = sorted(p["title"] for p in products)
        self.assertEqual(titles, ["P1", "P2", "P3", "P4", "P5"])  # id 3 deduped
        # stopped once total (5) reached -- did not keep paging
        self.assertEqual(calls, [0, 200])

    def test_aborts_without_partial_snapshot_on_failed_page(self):
        # page 0 ok (3 of 5), page 1 fails -> must return [] so save_snapshot is
        # skipped and the last good snapshot is preserved.
        def fake(host, sid, dom, offset, limit, token=None, health=None, **k):
            return self._page([1, 2, 3], 5) if offset == 0 else None
        es.fetch_catalog_page = fake
        self.assertEqual(es.scrape_ecwid("primal-fruits", self.CONFIG), [])

    def test_aborts_when_host_discovery_fails(self):
        es.discover_storefront = lambda *a, **k: (None, None)
        self.assertEqual(es.scrape_ecwid("primal-fruits", self.CONFIG), [])


if __name__ == "__main__":
    unittest.main()
