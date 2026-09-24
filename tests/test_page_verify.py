"""
stocklib.page_verify + its WooCommerce wiring: a product the store API calls
in stock, whose page says "we are unable to supply this product", is not stock.

The real case (2026-09-24): Guildford's "Apricot Multi Graft - Moorpark/
Trevatt" showed on treestock as In stock, $134.99, "Back in stock!", while its
page carried the waf-product-unavailable block and no price or cart button.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib import page_verify as pv  # noqa: E402
import woocommerce_scraper as wc  # noqa: E402

MARKER = "waf-product-unavailable"
UNAVAILABLE = f'<div class="{MARKER}"><p>unable to supply</p></div>'
BUYABLE = '<form class="cart"><button class="single_add_to_cart_button">Add</button></form>'
APRICOT = "https://g.test/product/apricot-multi-graft-moorpark-trevatt-2/"
LONGAN = "https://g.test/product/longan-chompoo/"


def _p(url, available=True):
    return {"url": url, "title": url.rstrip("/").rsplit("/", 1)[-1],
            "any_available": available,
            "variants": [{"title": "Default", "price": 134.99, "available": available}]}


def _write_latest(d, products):
    (Path(d) / "latest.json").write_text(json.dumps({"products": products}))


class _Pages:
    def __init__(self, pages):
        self.pages, self.fetched = pages, []

    def __call__(self, url):
        self.fetched.append(url)
        return self.pages.get(url)


class Selection(unittest.TestCase):
    def test_newly_in_stock_is_a_must_check(self):
        must, roll = pv.select_urls([_p(APRICOT)], prev_in_stock=set(),
                                    checks={APRICOT: {"checked": "2026-09-01"}})
        self.assertEqual(must, [APRICOT])

    def test_never_checked_is_a_must_check(self):
        must, _ = pv.select_urls([_p(LONGAN)], prev_in_stock={LONGAN}, checks={})
        self.assertEqual(must, [LONGAN])

    def test_rolling_takes_the_longest_unchecked_first(self):
        urls = [f"https://g.test/p/{i}/" for i in range(4)]
        checks = {u: {"checked": f"2026-09-0{9 - i}"} for i, u in enumerate(urls)}
        must, roll = pv.select_urls([_p(u) for u in urls], set(urls), checks, rolling=2)
        self.assertEqual(must, [])
        self.assertEqual(roll, [urls[3], urls[2]])

    def test_out_of_stock_products_are_never_loaded(self):
        must, roll = pv.select_urls([_p(APRICOT, available=False)], set(), {})
        self.assertEqual((must, roll), ([], []))

    def test_must_checks_are_capped(self):
        prods = [_p(f"https://g.test/p/{i}/") for i in range(10)]
        must, _ = pv.select_urls(prods, set(), {}, must_cap=3)
        self.assertEqual(len(must), 3)


class Verify(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_the_apricot_is_withdrawn_and_the_longan_is_not(self):
        prods = [_p(APRICOT), _p(LONGAN)]
        stats = pv.verify(prods, self.dir, MARKER,
                          _Pages({APRICOT: UNAVAILABLE, LONGAN: BUYABLE}), "2026-09-25")
        self.assertFalse(prods[0]["any_available"])
        self.assertFalse(prods[0]["variants"][0]["available"])
        self.assertTrue(prods[0]["page_unavailable"])
        self.assertTrue(prods[1]["any_available"])
        self.assertEqual(len(stats["withdrawn"]), 1)
        saved = json.loads((self.dir / pv.CHECKS_FILE).read_text())["checks"]
        self.assertEqual(saved[APRICOT], {"checked": "2026-09-25", "unavailable": True})

    def test_a_failed_page_load_keeps_the_previous_verdict(self):
        (self.dir / pv.CHECKS_FILE).write_text(json.dumps(
            {"checks": {APRICOT: {"checked": "2026-09-24", "unavailable": True}}}))
        _write_latest(self.dir, [])          # so tonight it is a must-check
        prods = [_p(APRICOT)]
        stats = pv.verify(prods, self.dir, MARKER, _Pages({}), "2026-09-25")
        self.assertEqual(stats["failed"], 1)
        self.assertFalse(prods[0]["any_available"])

    def test_a_product_the_store_restores_comes_back(self):
        (self.dir / pv.CHECKS_FILE).write_text(json.dumps(
            {"checks": {APRICOT: {"checked": "2026-09-24", "unavailable": True}}}))
        _write_latest(self.dir, [_p(APRICOT, available=False)])  # withdrawn last night
        prods = [_p(APRICOT)]
        pv.verify(prods, self.dir, MARKER, _Pages({APRICOT: BUYABLE}), "2026-09-25")
        self.assertTrue(prods[0]["any_available"])

    def test_verdicts_for_delisted_products_are_pruned(self):
        (self.dir / pv.CHECKS_FILE).write_text(json.dumps(
            {"checks": {"https://g.test/gone/": {"checked": "2026-09-01", "unavailable": False}}}))
        pv.verify([_p(LONGAN)], self.dir, MARKER, _Pages({LONGAN: BUYABLE}), "2026-09-25")
        saved = json.loads((self.dir / pv.CHECKS_FILE).read_text())["checks"]
        self.assertEqual(set(saved), {LONGAN})


class WooWiring(unittest.TestCase):
    """End to end through save_snapshot, as the nightly run calls it."""

    def _raw(self, slug):
        return {"id": 1, "name": "Apricot Multi Graft", "type": "variable",
                "permalink": f"https://g.test/product/{slug}/",
                "prices": {"price": "13499", "currency_minor_unit": 2},
                "is_in_stock": True, "is_purchasable": True, "categories": [], "tags": []}

    def test_back_in_stock_in_the_api_but_unsuppliable_on_the_page(self):
        data = Path(tempfile.mkdtemp())
        cfg = dict(wc.NURSERIES["guildford"])
        (data / "guildford").mkdir()
        _write_latest(data / "guildford", [])  # yesterday: not in stock
        pages = _Pages({APRICOT: UNAVAILABLE})
        with mock.patch.object(wc, "DATA_DIR", data):
            snap = wc.save_snapshot("guildford", [self._raw("apricot-multi-graft-moorpark-trevatt-2")],
                                    cfg, _fetch_page=pages)
        self.assertEqual(pages.fetched, [APRICOT])
        self.assertEqual(snap["in_stock_count"], 0)
        latest = json.loads((data / "guildford" / "latest.json").read_text())
        self.assertFalse(latest["products"][0]["any_available"])

    def test_stores_without_a_marker_load_no_pages(self):
        data = Path(tempfile.mkdtemp())
        cfg = {"name": "PlantNet", "domain": "p.test"}
        pages = _Pages({})
        with mock.patch.object(wc, "DATA_DIR", data):
            snap = wc.save_snapshot("plantnet", [self._raw("x")], cfg, _fetch_page=pages)
        self.assertEqual(pages.fetched, [])
        self.assertEqual(snap["in_stock_count"], 1)


if __name__ == "__main__":
    unittest.main()
