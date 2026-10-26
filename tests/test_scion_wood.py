"""
Scion wood and cuttings: off every tree surface, listed on /scion-wood.html.

Daleys' "Scion Wood Apple - Red Delicious $9.75" was the second row of the
cheapest table on /species/apple.html, and Primal's "(1 x Cutting)" figs read
as the cheapest fig trees. Benedict (2026-10-26): a separate scion wood
section, all species on one page. Titles are verbatim from live snapshots.
"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib.classify import is_propagation_material
from stocklib.fruit_filters import in_scope
import build_scion_wood_page as sw


class PropagationMaterialTest(unittest.TestCase):
    def test_scion_wood_and_bundles_of_cuttings(self):
        for t in ("Scion Wood Apple - Gala", "Scion Wood  Mulberry - White Shahtoot",
                  "White Shahtoot Mulberry -Scion", "Adam's Pride Fig (1 x Cutting)",
                  "White Shahtoot Mulberry (3xCuttings)", "Fig Cuttings"):
            with self.subTest(t=t):
                self.assertTrue(is_propagation_material(t))

    def test_rooted_plants_grown_from_cuttings_are_trees(self):
        # Every bare singular "Cutting" seen live is a potted plant, as are
        # "Cutting Grown" and "Rooted Cutting".
        for t in ("Finger lime Chartreuse Cutting 90mm (Qld only)",
                  "Alstonville Finger Lime Trees -50mm Pots (Cutting Grown)",
                  "Tahitian Lime Organic (Rooted Cutting already fruits)",
                  "Babaco Cutting", "Apple - Pink Lady"):
            with self.subTest(t=t):
                self.assertFalse(is_propagation_material(t))

    def test_off_tree_surfaces_even_at_an_open_nursery(self):
        # Primal is mode "all": its category never filtered these.
        self.assertFalse(in_scope({"title": "White Shahtoot Mulberry -Scion"}, "primal-fruits"))
        self.assertFalse(in_scope({"title": "Adam's Pride Fig (1 x Cutting)"}, "primal-fruits"))
        self.assertTrue(in_scope({"title": "Fig Brown Turkey"}, "primal-fruits"))


def _snapshot(root: Path, key: str, products: list[dict]):
    d = root / key
    d.mkdir(parents=True)
    (d / "latest.json").write_text(json.dumps({"nursery": key, "nursery_name": key, "products": products}))


class ScionWoodPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        data = Path(cls.tmp.name)
        _snapshot(data, "daleys", [
            # Filed under a non-fruit category: the page must not care.
            {"title": "Scion Wood Apple - Gala", "url": "https://x/gala", "min_price": 9.75,
             "any_available": False, "category": "Gardening Tools - Accessories/Scion Wood"},
            {"title": "Scion Wood Apple - Pink Lady", "url": "https://x/pl", "min_price": 9.75,
             "any_available": True, "category": "Gardening Tools - Accessories/Scion Wood"},
            {"title": "Apple - Pink Lady", "url": "https://x/tree", "min_price": 45.0,
             "any_available": True, "category": "Fruit Trees/Apples"},
        ])
        _snapshot(data, "primal-fruits", [
            {"title": "Adam's Pride Fig (1 x Cutting)", "url": "https://x/fig", "min_price": 10.0,
             "any_available": True},
        ])
        cls.rows = sw.collect_scion_wood(data)
        cls.html = sw.build_page(data, date(2026, 10, 26))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_lists_only_propagation_material(self):
        self.assertEqual(sorted(r["title"] for r in self.rows),
                         ["Adam's Pride Fig (1 x Cutting)", "Scion Wood Apple - Gala",
                          "Scion Wood Apple - Pink Lady"])

    def test_grouped_by_species_with_anchors_in_stock_first(self):
        self.assertIn('id="apple"', self.html)
        self.assertIn('id="fig"', self.html)
        start = self.html.index('id="apple"')
        apple = self.html[start:self.html.index("</section>", start)]
        self.assertLess(apple.index("Pink Lady"), apple.index("Gala"))
        self.assertIn("Sold out", apple)

    def test_species_page_link(self):
        counts = sw.counts_by_species(self.rows)
        self.assertEqual(counts["apple"], {"total": 2, "in_stock": 1})
        link = sw.species_link_html("apple", counts, "Apple")
        self.assertIn('href="/scion-wood.html#apple"', link)
        self.assertIn("2 listed, 1 in stock", link)
        self.assertEqual(sw.species_link_html("mango", counts, "Mango"), "")

    def test_no_em_dashes_in_copy(self):
        self.assertNotIn("—", self.html)


if __name__ == "__main__":
    unittest.main()
