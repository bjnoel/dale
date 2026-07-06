"""Regression tests for the Wix warmupData scraper (DAL-206, 2026-07-06).

Wix product pages carry a JSON-LD Product block whose offers object is EMPTY
(no price/sku/availability), so the scraper parses the wix-warmup-data JSON
blob instead. These tests pin:

  - extract_warmup_data + find_product_node + extract_product against two real
    captured product pages from Heaven On Earth Fruit Trees, pruned to the
    warmup blob (tests/fixtures/wix_product_*.html): one in stock, one sold
    out, both carrying the storewide percent discount. A field move in the
    blob (price/discountedPrice/isInStock) is caught rather than silently
    yielding junk.
  - the Wix price semantics: `price` is the undiscounted base and
    `discountedPrice`/`comparePrice` is what the buyer pays. The scraper must
    record the discounted price, and never trust a "discount" that raises it.
  - the conservative stock fallback: a node with no recognisable stock flag is
    OUT of stock (breakage surfaces as a surge alert, not false restock
    emails) -- same rule as the Ecwid scraper.
  - per-variant productItems widening min/max into a real price range.
  - parse_sitemap keeps only /product-page/ URLs, deduped.
  - scrape_wix aborts (returns [], writes nothing) on an empty sitemap or when
    too many product pages fail, rather than emitting a partial snapshot.

No test hits the network. Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import wix_scraper as ws  # noqa: E402

from stocklib.model import validate_snapshot  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture_product(name, url="https://example.com/product-page/x"):
    html = (FIXTURES / name).read_text()
    node = ws.find_product_node(ws.extract_warmup_data(html))
    assert node is not None, f"no product node in fixture {name}"
    return ws.extract_product(node, url)


class ExtractWarmupDataTest(unittest.TestCase):
    def test_missing_tag_returns_none(self):
        # The DAL-205 failure mode: page renders but the blob is gone.
        self.assertIsNone(ws.extract_warmup_data("<html><body>no blob</body></html>"))
        self.assertIsNone(ws.extract_warmup_data(""))
        self.assertIsNone(ws.extract_warmup_data(None))

    def test_malformed_json_returns_none(self):
        html = '<script type="application/json" id="wix-warmup-data">{not json</script>'
        self.assertIsNone(ws.extract_warmup_data(html))

    def test_parses_fixture(self):
        html = (FIXTURES / "wix_product_sapodilla.html").read_text()
        data = ws.extract_warmup_data(html)
        self.assertIn("appsWarmupData", data)


class FindProductNodeTest(unittest.TestCase):
    def test_none_and_empty(self):
        self.assertIsNone(ws.find_product_node(None))
        self.assertIsNone(ws.find_product_node({}))
        self.assertIsNone(ws.find_product_node({"appsWarmupData": {}}))

    def test_skips_non_product_app_entries(self):
        warmup = {"appsWarmupData": {
            "some-app": {"initialData": {"foo": 1}},
            "stores-app": {"productPage_AUD_slug": {"catalog": {"product": {"name": "X"}}}},
        }}
        self.assertEqual(ws.find_product_node(warmup), {"name": "X"})


class ExtractProductFixtureTest(unittest.TestCase):
    """Real captured pages from Heaven On Earth (2026-07-06 capture)."""

    def test_in_stock_discounted_product(self):
        p = _fixture_product("wix_product_sapodilla.html",
                             "https://www.heavenonearthfruittrees.com.au/product-page/sapodilla")
        self.assertEqual(p["title"], "Sapodilla Tree (2 years old)")
        # Base price $89, storewide 30% discount: the buyer pays $62.30 and
        # that is what we must record (not the undiscounted base).
        self.assertEqual(p["price"], 62.3)
        self.assertEqual(p["min_price"], 62.3)
        self.assertEqual(p["max_price"], 62.3)
        self.assertEqual(p["currency"], "AUD")
        self.assertTrue(p["available"])
        self.assertTrue(p["any_available"])
        self.assertEqual(p["availability_raw"], "InStock")
        self.assertEqual(p["url"], "https://www.heavenonearthfruittrees.com.au/product-page/sapodilla")
        # Description is stripped to plain text.
        self.assertIn("Sapodilla fruit is round to egg-shape", p["description"])
        self.assertNotIn("<", p["description"])

    def test_sold_out_product(self):
        p = _fixture_product("wix_product_abiu.html")
        self.assertEqual(p["title"], "Abiu Z4 Fruit Tree (Already Fruiting)")
        self.assertFalse(p["available"])
        self.assertFalse(p["any_available"])
        self.assertEqual(p["availability_raw"], "OutOfStock")
        self.assertEqual(p["price"], 104.3)  # discounted from $149

    def test_fixture_products_validate_as_snapshot(self):
        products = [_fixture_product("wix_product_sapodilla.html"),
                    _fixture_product("wix_product_abiu.html")]
        for prod in products:
            prod["nursery"] = "heaven-on-earth"
            prod["nursery_name"] = "Heaven On Earth Fruit Trees"
        snapshot = {"nursery": "heaven-on-earth", "products": products}
        self.assertEqual(validate_snapshot(snapshot), [])


class ExtractProductSemanticsTest(unittest.TestCase):
    def test_unknown_stock_state_is_out_of_stock(self):
        # No isInStock: conservative default (Ecwid rule).
        p = ws.extract_product({"name": "Mystery Tree", "price": 50}, "u")
        self.assertFalse(p["available"])
        self.assertEqual(p["availability_raw"], "OutOfStock")

    def test_inventory_status_is_not_trusted(self):
        # inventory.status says "in_stock" even on sold-out products (verified
        # against 66 rendered-sold-out pages, 2026-07-06), so it must never be
        # used as a stock signal. Only isInStock counts.
        node = {"name": "T", "price": 50, "isInStock": False,
                "inventory": {"status": "in_stock", "quantity": 0}}
        self.assertFalse(ws.extract_product(node, "u")["available"])
        node = {"name": "T", "price": 50, "inventory": {"status": "in_stock"}}
        self.assertFalse(ws.extract_product(node, "u")["available"])

    def test_discount_never_raises_price(self):
        # A "discountedPrice" above base is not a discount; keep the base.
        node = {"name": "T", "price": 50, "discountedPrice": 60, "isInStock": True}
        self.assertEqual(ws.extract_product(node, "u")["price"], 50)

    def test_no_discount_uses_base_price(self):
        node = {"name": "T", "price": 50, "discountedPrice": None, "isInStock": True}
        self.assertEqual(ws.extract_product(node, "u")["price"], 50)

    def test_price_range_from_product_items(self):
        # Size options: per-variant productItems at different prices must
        # widen min/max (price = the "from" price). None seen live on Heaven
        # On Earth at capture time, so this pins the synthetic-variant path.
        node = {
            "name": "Mango (choose size)", "price": 45, "isInStock": True,
            "productItems": [
                {"price": 45, "isVisible": True},
                {"price": 95, "isVisible": True},
                {"price": 200, "isVisible": False},  # hidden variants excluded
            ],
        }
        p = ws.extract_product(node, "u")
        self.assertEqual(p["price"], 45)
        self.assertEqual(p["min_price"], 45)
        self.assertEqual(p["max_price"], 95)

    def test_effective_item_price_discount_semantics(self):
        # Wix names are backwards: comparePrice is the discounted price.
        self.assertEqual(
            ws._effective_item_price({"price": 89, "comparePrice": 62.3, "hasDiscount": True}),
            62.3)
        # Without hasDiscount, comparePrice is ignored.
        self.assertEqual(
            ws._effective_item_price({"price": 89, "comparePrice": 62.3}), 89)
        # A comparePrice ABOVE price (strike-through "was" sense) is ignored.
        self.assertEqual(
            ws._effective_item_price({"price": 89, "comparePrice": 120, "hasDiscount": True}),
            89)
        self.assertEqual(ws._effective_item_price({"comparePrice": 62.3}), 62.3)
        self.assertIsNone(ws._effective_item_price({}))


class ParseSitemapTest(unittest.TestCase):
    def test_keeps_only_product_pages_deduped(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset>
          <url><loc>https://www.example.com/product-page/sapodilla</loc></url>
          <url><loc>https://www.example.com/product-page/sapodilla</loc></url>
          <url><loc> https://www.example.com/product-page/abiu-tree </loc></url>
          <url><loc>https://www.example.com/shipping-policy</loc></url>
        </urlset>"""
        self.assertEqual(ws.parse_sitemap(xml), [
            "https://www.example.com/product-page/abiu-tree",
            "https://www.example.com/product-page/sapodilla",
        ])

    def test_empty(self):
        self.assertEqual(ws.parse_sitemap(""), [])
        self.assertEqual(ws.parse_sitemap(None), [])


class ScrapeAbortTest(unittest.TestCase):
    """scrape_wix must return [] (write nothing) rather than a partial
    snapshot when discovery or too many pages fail."""

    CONFIG = {"name": "Test Nursery", "domain": "example.com", "delay": 0}

    def test_empty_sitemap_aborts(self):
        with mock.patch.object(ws, "fetch_page", return_value=None):
            self.assertEqual(ws.scrape_wix("test", self.CONFIG), [])

    def test_too_many_page_failures_aborts(self):
        sitemap = "".join(
            f"<loc>https://example.com/product-page/p{i}</loc>" for i in range(10))
        good = (FIXTURES / "wix_product_sapodilla.html").read_text()

        def fake_fetch(url, timeout=20, health=None, **kw):
            if "sitemap" in url:
                return sitemap
            # 3 of 10 product pages come back broken (>20% threshold)
            if url.endswith(("p0", "p1", "p2")):
                return "<html>outage page, no warmup blob</html>"
            return good

        with mock.patch.object(ws, "fetch_page", side_effect=fake_fetch):
            self.assertEqual(ws.scrape_wix("test", self.CONFIG), [])

    def test_few_failures_keeps_snapshot(self):
        sitemap = "".join(
            f"<loc>https://example.com/product-page/p{i}</loc>" for i in range(10))
        good = (FIXTURES / "wix_product_sapodilla.html").read_text()

        def fake_fetch(url, timeout=20, health=None, **kw):
            if "sitemap" in url:
                return sitemap
            if url.endswith("p0"):
                return None
            return good

        with mock.patch.object(ws, "fetch_page", side_effect=fake_fetch):
            products = ws.scrape_wix("test", self.CONFIG)
        self.assertEqual(len(products), 9)
        self.assertTrue(all(p["nursery"] == "test" for p in products))


if __name__ == "__main__":
    unittest.main()
