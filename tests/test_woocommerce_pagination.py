"""
Regression tests: a WooCommerce scrape never publishes a partial catalogue,
Guildford-style stores are fetched by resolved category, and "external"
(find-a-stockist) products are not in stock.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

import woocommerce_scraper as wc  # noqa: E402


def _prod(i, cats=("fig-tree",), **kw):
    p = {"id": i, "name": f"Fig {i}", "permalink": f"https://x.test/p/{i}/",
         "categories": [{"slug": c, "name": c} for c in cats],
         "prices": {"price": "2500", "currency_minor_unit": 2},
         "is_in_stock": True, "type": "simple", "tags": []}
    p.update(kw)
    return p


class _Store:
    """Routes Store API URLs to canned pages; None simulates a failed fetch."""

    def __init__(self, pages, cat_pages=None):
        self.pages, self.cat_pages, self.urls = pages, cat_pages, []

    def __call__(self, url, health=None):
        self.urls.append(url)
        page = int(url.rsplit("page=", 1)[1])
        src = self.cat_pages if "/categories" in url else self.pages
        if src is None:
            return None
        return src[page - 1] if page <= len(src) else []


CONFIG = {"name": "Test", "domain": "x.test", "fruit_categories": ["fig-tree"]}


def _run(store, config=CONFIG):
    with mock.patch.object(wc, "fetch_json", store), mock.patch.object(wc.time, "sleep"):
        return wc.scrape_woocommerce("test", config)


class NoPartialCatalogue(unittest.TestCase):
    def test_failed_middle_page_publishes_nothing(self):
        full = [_prod(i) for i in range(100)]
        store = _Store([full, None, [_prod(200)]], cat_pages=None)
        self.assertEqual(_run(store), [])

    def test_failed_category_page_in_category_mode_publishes_nothing(self):
        cfg = dict(CONFIG, category_api=True, fruit_categories=["a", "b"])
        calls = {"n": 0}

        def fetch(url, health=None):
            calls["n"] += 1
            return [_prod(1, cats=("a",))] if "category=a" in url else None

        with mock.patch.object(wc, "fetch_json", fetch), mock.patch.object(wc.time, "sleep"):
            self.assertEqual(wc.scrape_woocommerce("test", cfg), [])

    def test_clean_last_page_keeps_everything(self):
        store = _Store([[_prod(i) for i in range(100)], [_prod(100), _prod(101)]],
                       cat_pages=None)
        self.assertEqual(len(_run(store)), 102)


class ResolvedCategoryFetch(unittest.TestCase):
    CATS = [[{"id": 7, "slug": "fig-tree"}, {"id": 8, "slug": "roses"},
             {"id": 9, "slug": "fig-tree-dwarf"}]]

    def test_asks_only_for_matching_categories(self):
        store = _Store([[_prod(1), _prod(2, cats=("roses",))]], cat_pages=self.CATS)
        out = _run(store)
        product_urls = [u for u in store.urls if "/categories" not in u]
        self.assertTrue(all("category=7,9" in u for u in product_urls), product_urls)
        # The per-product filter still runs, so a stray rose is still dropped.
        self.assertEqual([p["id"] for p in out], [1])

    def test_unreadable_category_list_falls_back_to_whole_store(self):
        store = _Store([[_prod(1)]], cat_pages=None)
        out = _run(store)
        product_urls = [u for u in store.urls if "/categories" not in u]
        self.assertTrue(product_urls and all("category=" not in u for u in product_urls))
        self.assertEqual(len(out), 1)


class ExternalProducts(unittest.TestCase):
    def test_find_a_stockist_product_is_not_in_stock(self):
        raw = _prod(1, type="external", is_purchasable=False)
        n = wc.normalize_product(raw, "plantnet", {"name": "PlantNet"})
        self.assertFalse(n["any_available"])
        self.assertFalse(n["variants"][0]["available"])

    def test_simple_in_stock_product_still_in_stock(self):
        n = wc.normalize_product(_prod(1), "plantnet", {"name": "PlantNet"})
        self.assertTrue(n["any_available"])


if __name__ == "__main__":
    unittest.main()
