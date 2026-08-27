"""
Tests for squarespace_scraper -- the platform scraper added for Perry's Fruit &
Nut Nursery (our first South Australian nursery, 2026-08-27).

The fixtures below are trimmed from a real capture of
perrysfruitnursery.com.au/shop?format=json, so the three gotchas they pin are
the store's real behaviour and not invented edge cases:

1. Product-level `priceCents` is 0 on every multi-variant product, while the
   variants carry the real prices. Reading the product level would have put
   "$0.00" on a $220 tree -- the same class of bug as DEC-314's POA "0".
2. `offset` past the end of the collection re-serves the LAST product forever
   instead of returning an empty page, so a loop-until-empty pager never
   terminates.
3. `unlimited: true` means the store does not track stock for that variant, and
   `qtyInStock` reads 0 on those. Treating that 0 as out-of-stock marks most of
   the catalogue dead.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

import squarespace_scraper as sq


def _variant(vid, price, *, qty=0, unlimited=False, sku="SQ1", attrs=None,
             sale_price=None, on_sale=False):
    return {
        "id": vid,
        "sku": sku,
        "price": price,
        "salePrice": sale_price if sale_price is not None else price,
        "onSale": on_sale,
        "qtyInStock": qty,
        "unlimited": unlimited,
        "attributes": attrs or {},
    }


def _item(iid, title, variants, *, cats=None, price_cents=0, body=""):
    return {
        "id": iid,
        "title": title,
        "fullUrl": f"/shop/p/{title.lower().replace(' ', '-')}",
        "body": body,
        "categoryIds": cats or [],
        "priceCents": price_cents,
        "onSale": False,
        "variants": variants,
    }


CATEGORIES = {
    "nestedCategories": {
        "categories": [
            {"id": "cat-citrus", "displayName": "Citrus"},
            {"id": "cat-nuts", "displayName": "Nuts"},
        ]
    }
}


class VariantExtractionTest(unittest.TestCase):
    def test_price_is_cents_and_becomes_dollars(self):
        v = sq.extract_variant(_variant("v1", 7200))
        self.assertEqual(v["price"], 72.00)

    def test_unlimited_means_available_with_no_count(self):
        """The store does not track stock for this variant, so qtyInStock is a
        meaningless 0. It must not read as sold out, and stock_count must be
        None rather than 0 so downstream can tell 'none left' from 'never
        counted'."""
        v = sq.extract_variant(_variant("v1", 7200, qty=0, unlimited=True))
        self.assertTrue(v["available"])
        self.assertIsNone(v["stock_count"])

    def test_tracked_zero_is_out_of_stock(self):
        v = sq.extract_variant(_variant("v1", 13000, qty=0, unlimited=False))
        self.assertFalse(v["available"])
        self.assertEqual(v["stock_count"], 0)

    def test_tracked_positive_is_in_stock(self):
        v = sq.extract_variant(_variant("v1", 13000, qty=3))
        self.assertTrue(v["available"])
        self.assertEqual(v["stock_count"], 3)

    def test_sale_price_only_wins_when_it_is_actually_lower(self):
        """Squarespace sets salePrice == price when a variant is not on sale,
        and a store could use it in the strike-through 'was' sense. Only a
        genuine markdown may move the price."""
        cheaper = sq.extract_variant(
            _variant("v1", 10000, sale_price=8000, on_sale=True))
        self.assertEqual(cheaper["price"], 80.00)

        higher = sq.extract_variant(
            _variant("v2", 10000, sale_price=12000, on_sale=True))
        self.assertEqual(higher["price"], 100.00)

    def test_variant_title_joins_option_values_not_labels(self):
        """Perry's alone uses 'Container', 'container', 'type', 'rootstock',
        'variety' and 'Packet' as option labels across six products. Building
        the title from values only keeps the variant key stable when an owner
        renames a label."""
        v = sq.extract_variant(_variant("v1", 22000, attrs={"Container": "40cm pot"}))
        self.assertEqual(v["title"], "40cm pot")

    def test_variant_with_no_options_is_default(self):
        self.assertEqual(sq.extract_variant(_variant("v1", 3900))["title"], "Default")


class ProductExtractionTest(unittest.TestCase):
    def test_price_range_comes_from_variants_not_the_product(self):
        """The regression this file exists for: Perry's 'Lemon' carries
        priceCents 0 while its three pot sizes are $72/$110/$220."""
        item = _item("i1", "Lemon", [
            _variant("v1", 7200, unlimited=True, attrs={"Container": "4 litre nursery bag"}),
            _variant("v2", 11000, qty=0, attrs={"Container": "25cm pot"}),
            _variant("v3", 22000, qty=0, attrs={"Container": "40cm pot"}),
        ], cats=["cat-citrus"], price_cents=0)

        p = sq.extract_product(item, "https://example.com/shop/p/lemon",
                               sq.category_names(CATEGORIES))
        self.assertEqual(p["min_price"], 72.00)
        self.assertEqual(p["max_price"], 220.00)
        self.assertNotEqual(p["min_price"], 0)

    def test_product_is_available_if_any_variant_is(self):
        item = _item("i1", "Almond", [
            _variant("v1", 9500, unlimited=True),
            _variant("v2", 7500, qty=0),
        ])
        p = sq.extract_product(item, "u")
        self.assertTrue(p["available"])
        self.assertTrue(p["any_available"])
        self.assertEqual(p["availability_raw"], "InStock")

    def test_product_is_out_of_stock_when_every_variant_is(self):
        item = _item("i1", "Walnut", [_variant("v1", 13000, qty=0)])
        p = sq.extract_product(item, "u")
        self.assertFalse(p["available"])
        self.assertEqual(p["availability_raw"], "OutOfStock")

    def test_category_maps_from_id_and_tolerates_an_unmapped_one(self):
        """Seven of Perry's 98 products sit in a category that is in no active
        nav entry, so the id resolves to nothing. That must yield an empty
        category, never a raw Squarespace id leaking onto a page."""
        cats = sq.category_names(CATEGORIES)
        mapped = sq.extract_product(_item("i1", "Yuzu", [_variant("v1", 8200)],
                                          cats=["cat-citrus"]), "u", cats)
        self.assertEqual(mapped["category"], "Citrus")

        orphan = sq.extract_product(_item("i2", "White Sapote", [_variant("v1", 9500)],
                                          cats=["cat-not-in-nav"]), "u", cats)
        self.assertEqual(orphan["category"], "")


class PaginationTest(unittest.TestCase):
    """The clamp: past the end of the collection Squarespace re-serves the last
    product instead of an empty page. Verified live against Perry's, where
    offset 98, 99 and 100 all return 'White Sapote'."""

    def _store(self, pages):
        calls = []

        def fake_fetch(url):
            calls.append(url)
            idx = int(url.split("offset=")[1].split("&")[0])
            return pages(idx)

        return fake_fetch, calls

    def test_a_clamping_endpoint_terminates(self):
        all_items = [_item(f"i{n}", f"Tree {n}", [_variant(f"v{n}", 5000, qty=1)])
                     for n in range(5)]

        def pages(offset):
            window = all_items[offset:offset + 3]
            # The clamp: never empty, always at least the last item.
            return dict(CATEGORIES, items=window or [all_items[-1]])

        fetch, calls = self._store(pages)
        products = sq.scrape_squarespace("t", {"name": "T", "domain": "d", "delay": 0},
                                         _fetch=fetch)
        self.assertEqual(len(products), 5)
        self.assertLess(len(calls), sq.PAGE_LIMIT,
                        "pager did not terminate against a clamping endpoint")

    def test_products_are_not_duplicated_across_pages(self):
        item = _item("i1", "Fig", [_variant("v1", 5000, qty=1)])

        def pages(offset):
            return dict(CATEGORIES, items=[item])   # same item forever

        fetch, _ = self._store(pages)
        products = sq.scrape_squarespace("t", {"name": "T", "domain": "d", "delay": 0},
                                         _fetch=fetch)
        self.assertEqual(len(products), 1)

    def test_an_unfetchable_first_page_writes_nothing(self):
        """A store outage must keep the last good snapshot. Returning a partial
        or empty product list here looks downstream like the whole nursery
        delisting overnight and can fire false surge alerts (DEC-293)."""
        products = sq.scrape_squarespace("t", {"name": "T", "domain": "d", "delay": 0},
                                         _fetch=lambda u: None)
        self.assertEqual(products, [])


class NonStockFilterTest(unittest.TestCase):
    def _scrape(self, titles, exclude=None):
        items = [_item(f"i{n}", t, [_variant(f"v{n}", 5000, qty=1)])
                 for n, t in enumerate(titles)]
        served = {"done": False}

        def fetch(url):
            if served["done"]:
                return dict(CATEGORIES, items=items[-1:])
            served["done"] = True
            return dict(CATEGORIES, items=items)

        cfg = {"name": "T", "domain": "d", "delay": 0}
        if exclude:
            cfg["exclude_pattern"] = exclude
        return [p["title"] for p in sq.scrape_squarespace("t", cfg, _fetch=fetch)]

    def test_gift_vouchers_are_dropped_by_the_shared_filter(self):
        kept = self._scrape(["Quandong", "Gift Voucher"])
        self.assertEqual(kept, ["Quandong"])

    def test_the_stores_own_produce_is_dropped_but_the_tree_is_kept(self):
        """Perry's sells its jujube crop next to its jujube trees. Both pass
        is_real_product (a jujube IS a real fruit), so the produce needs the
        per-store title filter -- and it must not take 'Jujube Tree' with it."""
        kept = self._scrape(
            ["Jujube Tree", "FRESH Jujube fruit", "Dried Jujube Fruit"],
            exclude=sq.NURSERIES["perrys"]["exclude_pattern"])
        self.assertEqual(kept, ["Jujube Tree"])

    def test_the_filter_is_off_unless_a_store_configures_it(self):
        kept = self._scrape(["Dried Jujube Fruit"])
        self.assertEqual(kept, ["Dried Jujube Fruit"])


class PerrysConfigTest(unittest.TestCase):
    def test_perrys_is_configured_and_registered_together(self):
        """A scraper config without a registry record renders the nursery with
        no name, no location and no shipping states."""
        from stocklib import registry
        self.assertIn("perrys", sq.NURSERIES)
        self.assertIn("perrys", registry.NURSERY_NAMES)
        self.assertEqual(registry.SHIPPING_MAP["perrys"], ["SA"])

    def test_perrys_is_the_only_south_australian_nursery_we_track(self):
        """The reason it was added (DAL-255). If this ever fails because a
        second SA nursery arrived, that is good news -- update the test."""
        from stocklib import registry
        sa_only = [n.key for n in registry.NURSERIES if n.ships_to == ("SA",)]
        self.assertEqual(sa_only, ["perrys"])


if __name__ == "__main__":
    unittest.main()
