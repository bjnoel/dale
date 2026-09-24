"""
Regression tests for the Heritage Fruit Trees Storefront GraphQL path.

Two live defects this pins (2026-09-23):

1. 53 Heritage products were shown in stock that could not be bought. BCData
   and GraphQL both separate "in stock" from "purchasable"; with online sales
   closed for 2026 those 53 were isInStock=true, availabilityV2 "Unavailable",
   BCData purchasable:false. The scraper read only `instock`.
2. The synthetic variant id was hash(url), which Python randomises per process:
   0 of 378 ids matched between two consecutive nights.

And the rewrite itself: ~620 sequential HTML fetches (1,240s nightly) replaced
by ~13 GraphQL requests, falling back to the HTML path when GraphQL cannot be
trusted.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import bigcommerce_scraper as bc  # noqa: E402

TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJFUzI1NiJ9.eyJjaWQiOlsxXX0.c2lnbmF0dXJl"


def _crumbs(*paths):
    return {"edges": [
        {"node": {"breadcrumbs": {"edges": [{"node": {"name": n}} for n in ("Shop",) + p]}}}
        for p in paths
    ]}


def _node(entity_id, name, path, *, price=30.0, base=None, in_stock=True,
          status="Available", cats=(("Fruit Trees", "Apple Trees"),)):
    return {
        "entityId": entity_id, "name": name, "path": path, "sku": str(entity_id),
        "prices": {"price": {"value": price} if price is not None else None,
                   "basePrice": {"value": base if base is not None else price} if price is not None else None,
                   "salePrice": {"value": price} if price is not None else None},
        "inventory": {"isInStock": in_stock},
        "availabilityV2": {"status": status},
        "categories": _crumbs(*cats),
    }


BUYABLE = _node(101, "Akane Apple (medium)", "/akane-apple-medium/", price=35.95)
# The live bug: in stock, not purchasable (store closed for the season).
IN_STOCK_NOT_BUYABLE = _node(102, "Josephine de Malines Pear (semi-dwarf)",
                             "/josephine-de-malines-pear-semi-dwarf/",
                             price=37.95, status="Unavailable",
                             cats=(("Fruit Trees", "Pear Trees"),))
ON_SALE = _node(103, "Black Genoa Fig", "/black-genoa-fig/", price=25.5, base=31.95,
                cats=(("Fruit Trees", "Fig Trees"),))
ORNAMENTAL = _node(104, "Acoma Crepe Myrtle", "/acoma-crepe-myrtle/",
                   cats=(("Ornamental Plants", "Flowering Trees and Shrubs"),))
# Primary category is a cross-cut; the title is what makes it fruit.
SPECIALS_FRUIT = _node(105, "Stella Cherry (dwarf)", "/stella-cherry-dwarf/",
                       cats=(("Specials",),))
# Dual-listed flowering crab: Fruit Trees AND Ornamental. The page breadcrumb
# was the ornamental one, so it has never been in the dataset.
DUAL_CRAB = _node(106, "Golden Hornet Crabapple (Malus 'Golden Hornet')",
                  "/golden-hornet-crabapple/",
                  cats=(("Fruit Trees", "Crabapples"),
                        ("Ornamental Plants", "Flowering Trees and Shrubs")))
SONNING_CRAB = _node(110, "Sonning Crab (Malus x purpurea 'Sonningensis')",
                     "/sonning-crab-malus-purpurea-sonningensis/",
                     cats=(("Fruit Trees", "Crabapples"),
                           ("Ornamental Plants", "Flowering Trees and Shrubs")))
# A fruiting crab apple filed only under Fruit Trees has always been kept.
FRUIT_CRAB = _node(107, "Huonville Crab Apple (dwarf)", "/huonville-crab-apple-dwarf/",
                   cats=(("Fruit Trees", "Crabapples"),))
UNPRICED_OOS = _node(108, "Rival Apricot", "/rival-apricot/", price=None,
                     in_stock=False, status="Unavailable",
                     cats=(("Fruit Trees", "Apricot Trees"),))
JUNK = _node(109, "Budding Tape 14mm", "/budding-tape-14mm/",
             cats=(("Non-Plant Products", "Grafting Equipment"),))


class _Resp:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


class _Opener:
    """Answers GET homepage / sitemap and POST /graphql from canned pages."""

    def __init__(self, pages, *, home=None, fail_graphql_page=None):
        self.pages = pages
        self.home = home if home is not None else f'<script>var t="{TOKEN}";</script>'
        self.fail_graphql_page = fail_graphql_page
        self.graphql_calls = 0
        self.auth = []

    def __call__(self, req, timeout=None):
        if req.full_url == bc.GRAPHQL_URL:
            self.graphql_calls += 1
            self.auth.append(req.get_header("Authorization"))
            if self.graphql_calls == self.fail_graphql_page:
                return _Resp(json.dumps({"errors": [{"message": "boom"}]}))
            idx = self.graphql_calls - 1
            nodes = self.pages[idx]
            more = idx + 1 < len(self.pages)
            return _Resp(json.dumps({"data": {"site": {"products": {
                "pageInfo": {"hasNextPage": more, "endCursor": f"c{idx}" if more else None},
                "edges": [{"node": n} for n in nodes],
            }}}}))
        return _Resp(self.home)


class _Health:
    def __init__(self):
        self.errors = []
        self.http = []

    def note_error(self, m):
        self.errors.append(m)

    def note_http_error(self, code, url=""):
        self.http.append(code)


class TokenExtraction(unittest.TestCase):
    def test_finds_three_part_jwt(self):
        html = f'<script>window.stencilBootstrap("x", "{{\\"token\\":\\"{TOKEN}\\"}}")</script>'
        self.assertEqual(bc.extract_storefront_token(html), TOKEN)

    def test_none_when_absent(self):
        self.assertIsNone(bc.extract_storefront_token("<html>no token</html>"))
        self.assertIsNone(bc.extract_storefront_token(None))


class ParseNode(unittest.TestCase):
    def test_buyable_product_shape_matches_snapshot_contract(self):
        p = bc.parse_graphql_node(BUYABLE)
        self.assertEqual(p["handle"], "akane-apple-medium")
        self.assertEqual(p["url"], "https://www.heritagefruittrees.com.au/akane-apple-medium/")
        v = p["variants"][0]
        # History keys on url|sku:<slug>; the sku must stay the slug.
        self.assertEqual(v["sku"], "akane-apple-medium")
        self.assertEqual(v["price"], "35.95")
        self.assertEqual(v["id"], 101)
        self.assertEqual(p["min_price"], 35.95)
        self.assertTrue(p["any_available"])
        self.assertFalse(p["on_sale"])
        self.assertIsNone(v["compare_at_price"])

    def test_in_stock_but_not_purchasable_is_not_available(self):
        p = bc.parse_graphql_node(IN_STOCK_NOT_BUYABLE)
        self.assertFalse(p["any_available"])
        self.assertFalse(p["variants"][0]["available"])

    def test_sale_price_records_compare_at(self):
        p = bc.parse_graphql_node(ON_SALE)
        self.assertEqual(p["variants"][0]["price"], "25.50")
        self.assertEqual(p["variants"][0]["compare_at_price"], "31.95")
        self.assertTrue(p["on_sale"])

    def test_scope(self):
        self.assertIsNone(bc.parse_graphql_node(ORNAMENTAL))
        self.assertIsNone(bc.parse_graphql_node(JUNK))
        self.assertIsNone(bc.parse_graphql_node(DUAL_CRAB))
        self.assertIsNone(bc.parse_graphql_node(SONNING_CRAB))
        self.assertIsNotNone(bc.parse_graphql_node(SPECIALS_FRUIT))
        self.assertIsNotNone(bc.parse_graphql_node(FRUIT_CRAB))

    def test_unpriced_out_of_stock(self):
        p = bc.parse_graphql_node(UNPRICED_OOS)
        self.assertIsNone(p["min_price"])
        self.assertIsNone(p["variants"][0]["price"])
        self.assertFalse(p["any_available"])


class Pagination(unittest.TestCase):
    def test_walks_every_page_with_the_token(self):
        opener = _Opener([[BUYABLE, ORNAMENTAL], [ON_SALE], [SPECIALS_FRUIT]])
        sleeps = []
        products = bc.scrape_graphql(4, _opener=opener, _sleep=sleeps.append)
        self.assertEqual(opener.graphql_calls, 3)
        self.assertEqual(set(opener.auth), {f"Bearer {TOKEN}"})
        self.assertEqual([p["handle"] for p in products],
                         ["akane-apple-medium", "black-genoa-fig", "stella-cherry-dwarf"])
        self.assertEqual(len(sleeps), 2)  # between pages, not after the last

    def test_a_failed_page_fails_the_whole_catalogue(self):
        opener = _Opener([[BUYABLE], [ON_SALE], [SPECIALS_FRUIT]], fail_graphql_page=2)
        health = _Health()
        self.assertIsNone(bc.scrape_graphql(3, health, _opener=opener, _sleep=lambda s: None))
        self.assertTrue(any("fallback" in e for e in health.errors))


class FallbackTriggers(unittest.TestCase):
    def test_no_token_falls_back(self):
        opener = _Opener([[BUYABLE]], home="<html>theme changed</html>")
        health = _Health()
        self.assertIsNone(bc.scrape_graphql(1, health, _opener=opener, _sleep=lambda s: None))
        self.assertEqual(opener.graphql_calls, 0)
        self.assertTrue(health.errors)

    def test_short_catalogue_falls_back(self):
        # 2 products against a 10-product sitemap is under GRAPHQL_MIN_SHARE.
        opener = _Opener([[BUYABLE, ON_SALE]])
        health = _Health()
        self.assertIsNone(bc.scrape_graphql(10, health, _opener=opener, _sleep=lambda s: None))
        self.assertTrue(any("short" in e for e in health.errors))

    def test_scrape_uses_html_when_graphql_declines(self):
        calls = []
        orig_g, orig_h, orig_u = bc.scrape_graphql, bc.scrape_html, bc.get_all_product_urls
        try:
            bc.get_all_product_urls = lambda health=None: ["/a/", "/b/"]
            bc.scrape_graphql = lambda n, health=None: calls.append(("g", n)) or None
            bc.scrape_html = lambda paths, health=None: calls.append(("h", len(paths))) or []
            bc.scrape(health=None)
        finally:
            bc.scrape_graphql, bc.scrape_html, bc.get_all_product_urls = orig_g, orig_h, orig_u
        self.assertEqual(calls, [("g", 2), ("h", 2)])


class HtmlPath(unittest.TestCase):
    PAGE = ('<h1 class="productView-title">Josephine de Malines Pear</h1>'
            '<script type="application/ld+json">{"@type":"Product","offers":{"price":"37.95"}}</script>'
            '<script>var BCData = {"product_attributes":{"instock":true,"purchasable":%s}};</script>')

    def test_purchasable_false_means_not_available(self):
        d = bc.parse_product_page("/josephine/", self.PAGE % "false")
        self.assertFalse(d["in_stock"])

    def test_purchasable_true_keeps_instock(self):
        d = bc.parse_product_page("/josephine/", self.PAGE % "true")
        self.assertTrue(d["in_stock"])

    def test_404_is_not_a_health_event(self):
        import email.message
        import urllib.error

        def opener(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 404, "nf", email.message.Message(), None)
        health = _Health()
        self.assertIsNone(bc.fetch_html("https://x/y/", delay=False, health=health,
                                        _opener=opener, _sleep=lambda s: None))
        self.assertEqual(health.http, [])


class DeterministicId(unittest.TestCase):
    def test_same_across_processes(self):
        code = ("import sys; sys.path.insert(0, %r); import bigcommerce_scraper as b; "
                "print(b.variant_id_for('https://www.heritagefruittrees.com.au/akane-apple-medium/'))"
                % str(SCRAPERS))
        outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                               env={"PYTHONHASHSEED": str(seed), "PATH": "/usr/bin:/bin"},
                               cwd=str(SCRAPERS)).stdout.strip()
                for seed in (1, 2, 3)}
        self.assertEqual(len(outs), 1, outs)
        self.assertTrue(outs.pop().isdigit())


if __name__ == "__main__":
    unittest.main()
