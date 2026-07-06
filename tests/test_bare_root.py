"""
Tests for tools/scrapers/build_bare_root_page.py -- the season-aware bare-root
landing page for treestock.com.au (DAL-185).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"

sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


br = _load(SCRAPERS / "build_bare_root_page.py")

EM_DASH = "—"
EN_DASH = "–"

# Synthetic snapshot data. Nursery keys must be real registry keys so
# NURSERY_NAMES / restriction_warning resolve.
PRODUCTS_DALEYS = [
    {"title": "Apple Pink Lady (Bare Rooted)", "url": "https://example.com/pink-lady",
     "min_price": 45.0, "any_available": True, "tags": []},
    {"title": "Plum Satsuma Bare-Rooted Tree", "url": "https://example.com/satsuma",
     "min_price": 39.0, "any_available": True, "tags": []},
    {"title": "Pear Beurre Bosc", "url": "https://example.com/bosc",
     "min_price": 52.5, "any_available": True, "tags": ["Bare Rooted Trees"]},
    {"title": "Cherry Stella bear rooted", "url": "https://example.com/stella",
     "min_price": 60.0, "any_available": True, "tags": []},
    {"title": "Fig Brown Turkey (Bare root)", "url": "https://example.com/fig",
     "min_price": 30.0, "any_available": True, "tags": []},
    {"title": "Nectarine Goldmine (Bare rooted)", "url": "https://example.com/goldmine",
     "min_price": 25.0, "any_available": False, "tags": []},
    {"title": "Mango Kensington Pride", "url": "https://example.com/kp",
     "min_price": 89.0, "any_available": True, "tags": []},
    {"title": "Gift Card", "url": "https://example.com/gift",
     "min_price": 50.0, "any_available": True, "tags": ["Bare Rooted Trees"]},
]

PRODUCTS_DIGGERS = [
    {"title": "Mulberry Black English (Bare Rooted)", "url": "https://example.com/mulberry",
     "min_price": 42.0, "any_available": False, "tags": []},
]


def _write_data_dir(tmp: Path):
    for key, products in (("daleys", PRODUCTS_DALEYS), ("diggers", PRODUCTS_DIGGERS)):
        d = tmp / key
        d.mkdir(parents=True)
        (d / "latest.json").write_text(json.dumps({"nursery_name": key, "products": products}))


def _build(today: str, products=None) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        if products is None:
            _write_data_dir(data)
        else:
            d = data / "daleys"
            d.mkdir(parents=True)
            (d / "latest.json").write_text(json.dumps({"nursery_name": "daleys", "products": products}))
        return br.build_page(str(data), date.fromisoformat(today))


HTML_OPEN = _build("2026-07-15")
HTML_CLOSED = _build("2026-11-15")
HTML_SPARSE = _build("2026-07-15", products=[
    {"title": "Apple Fuji (Bare Rooted)", "url": "https://example.com/fuji",
     "min_price": 45.0, "any_available": True, "tags": []},
    {"title": "Plum Mariposa (Bare Rooted)", "url": "https://example.com/mariposa",
     "min_price": 40.0, "any_available": False, "tags": []},
])


class SeasonStateTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(br.season_state(date(2026, 5, 31), 100), "closed")
        self.assertEqual(br.season_state(date(2026, 6, 1), 100), "open")
        self.assertEqual(br.season_state(date(2026, 9, 30), 100), "open")
        self.assertEqual(br.season_state(date(2026, 10, 1), 100), "closed")

    def test_sparse_threshold(self):
        self.assertEqual(br.season_state(date(2026, 7, 15), br.SPARSE_MIN - 1), "sparse")
        self.assertEqual(br.season_state(date(2026, 7, 15), br.SPARSE_MIN), "open")
        # Out of season the count is irrelevant.
        self.assertEqual(br.season_state(date(2026, 12, 1), 0), "closed")

    def test_season_year(self):
        self.assertEqual(br.season_year(date(2026, 7, 5)), 2026)
        self.assertEqual(br.season_year(date(2026, 2, 1)), 2026)
        self.assertEqual(br.season_year(date(2026, 11, 15)), 2027)


class MatchingTests(unittest.TestCase):
    def test_title_and_tag_and_typo_matching(self):
        self.assertTrue(br._is_bare_root({"title": "Apple (Bare Rooted)", "tags": []}))
        self.assertTrue(br._is_bare_root({"title": "Pear Bosc", "tags": ["Bare Rooted Trees"]}))
        self.assertTrue(br._is_bare_root({"title": "Cherry bear rooted", "tags": []}))
        self.assertFalse(br._is_bare_root({"title": "Mango Kensington Pride", "tags": ["trees"]}))

    def test_junk_products_excluded(self):
        # "Gift Card" carries a bare-root tag but is not a real plant product.
        self.assertNotIn("Gift Card", HTML_OPEN)

    def test_non_bare_root_excluded(self):
        self.assertNotIn("Kensington Pride", HTML_OPEN)


class OpenStateTests(unittest.TestCase):
    def test_open_status_box(self):
        self.assertIn("Bare-root season is on", HTML_OPEN)
        # 5 in-stock bare-root items in the daleys fixture (nectarine is out of stock).
        self.assertIn("5 trees in stock", HTML_OPEN)

    def test_table_sorted_cheapest_first(self):
        fig = HTML_OPEN.index("Fig Brown Turkey")
        plum = HTML_OPEN.index("Plum Satsuma")
        apple = HTML_OPEN.index("Apple Pink Lady")
        self.assertLess(fig, plum)
        self.assertLess(plum, apple)

    def test_out_of_stock_not_in_table(self):
        self.assertNotIn("Nectarine Goldmine", HTML_OPEN)

    def test_price_formatting(self):
        self.assertIn("$45", HTML_OPEN)
        self.assertIn("$52.50", HTML_OPEN)
        self.assertNotIn("$45.00", HTML_OPEN)

    def test_nursery_section_lists_both_nurseries(self):
        self.assertIn('href="/nursery/daleys.html"', HTML_OPEN)
        self.assertIn('href="/nursery/diggers.html"', HTML_OPEN)


class SparseAndClosedStateTests(unittest.TestCase):
    def test_sparse_shows_counts_not_table(self):
        self.assertIn("Very little bare-root stock", HTML_SPARSE)
        self.assertIn("bare-root listings", HTML_SPARSE)
        self.assertNotIn("<th>Price</th>", HTML_SPARSE)

    def test_closed_status_and_no_table(self):
        self.assertIn("Season closed", HTML_CLOSED)
        self.assertIn("The bare-root season is over for this year", HTML_CLOSED)
        self.assertNotIn("<th>Price</th>", HTML_CLOSED)

    def test_closed_points_at_next_season_year(self):
        # Built at 2026-11-15, the next season is 2027.
        self.assertIn("2027", HTML_CLOSED)

    def test_curated_sections_survive_closed_state(self):
        for anchor in ('id="what-is-bare-root"', 'id="species"', 'id="faq"',
                       'id="references"', 'id="alerts"'):
            self.assertIn(anchor, HTML_CLOSED, f"missing section {anchor} in closed state")


class PageChromeTests(unittest.TestCase):
    def test_canonical_and_og(self):
        self.assertIn('<link rel="canonical" href="https://treestock.com.au/bare-root.html">', HTML_OPEN)
        self.assertIn('<meta property="og:type" content="article">', HTML_OPEN)

    def test_season_year_in_title(self):
        self.assertIn("Bare Root Fruit Trees Australia 2026", HTML_OPEN)
        self.assertIn("Bare Root Fruit Trees Australia 2027", HTML_CLOSED)

    def test_species_links_resolve(self):
        valid = {s["slug"] for s in br.enabled_species() if s.get("slug")}
        for slug in re.findall(r'href="/species/([a-z0-9-]+)\.html"', HTML_OPEN):
            self.assertIn(slug, valid, f"species link {slug} would 404")

    def test_faq_jsonld_valid(self):
        m = re.search(r'<script type="application/ld\+json">\n(.*?)\n</script>', HTML_OPEN, re.S)
        self.assertIsNotNone(m)
        data = json.loads(m.group(1))
        self.assertEqual(data["@type"], "FAQPage")
        self.assertEqual(len(data["mainEntity"]), len(br.FAQS))

    def test_no_em_or_en_dashes(self):
        for html in (HTML_OPEN, HTML_CLOSED, HTML_SPARSE):
            self.assertNotIn(EM_DASH, html)
            self.assertNotIn(EN_DASH, html)

    def test_external_links_use_noopener(self):
        for tag in re.findall(r"<a [^>]*target=\"_blank\"[^>]*>", HTML_OPEN):
            self.assertIn("noopener", tag, f"target=_blank without noopener: {tag}")

    def test_restriction_warnings_not_ships_to_badges(self):
        self.assertNotIn("Ships to WA", HTML_OPEN)


class ShippingCellTests(unittest.TestCase):
    """A WA nursery's stock must not read like an interstate restriction: local
    delivery is neutral, an interstate quarantine gap is an amber caution."""

    def test_local_nursery_is_neutral_not_amber(self):
        cell = br._shipping_cell("guildford")  # WA, Perth metro local delivery
        self.assertIn("Perth metro only", cell)
        self.assertIn("text-gray-500", cell)
        self.assertNotIn("text-amber-700", cell)

    def test_restricted_nursery_is_amber(self):
        cell = br._shipping_cell("ausnurseries")  # no WA/NT/TAS
        self.assertIn("No WA/NT/TAS", cell)
        self.assertIn("text-amber-700", cell)

    def test_nationwide_nursery_reads_all_states(self):
        cell = br._shipping_cell("diggers")  # ships everywhere
        self.assertIn("All states", cell)
        self.assertNotIn("text-amber-700", cell)


class MainTests(unittest.TestCase):
    def test_main_writes_named_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            _write_data_dir(data)
            out = Path(tmp) / "out"
            sys.argv = ["build_bare_root_page.py", str(data), str(out), "--today", "2026-07-15"]
            br.main()
            f = out / "bare-root.html"
            self.assertTrue(f.exists())
            self.assertGreater(f.stat().st_size, 5000)


if __name__ == "__main__":
    unittest.main()
