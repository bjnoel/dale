"""
Tests for the category filter + badges on the /compare/ index
(build_compare_pages.build_compare_index). Flat species table, same shape as the
/species/ index. The shared badge logic lives in stocklib.category_ui (also covered
by test_species_index_filter / test_variety_index_filter); this guards the compare
wiring: per-row data-category/data-bushtucker, the badge, the pills, and the script.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import build_compare_pages as bcp  # noqa: E402


def _entry(record):
    return {"species": record, "nursery_count": 3, "in_stock": 5, "min_price": 19.95}


ENTRIES = [
    _entry({"slug": "mango", "common_name": "Mango", "latin_name": "Mangifera indica"}),
    _entry({"slug": "lemon-myrtle", "common_name": "Lemon Myrtle",
            "latin_name": "Backhousia citriodora", "category": "bush_tucker"}),
    _entry({"slug": "finger-lime", "common_name": "Finger Lime",
            "latin_name": "Microcitrus australasica", "tags": ["bush_tucker"]}),
]


def _row_for(html, slug):
    body = html.split("<tbody>", 1)[-1]
    for row in re.findall(r"<tr\b.*?</tr>", body, re.S):
        if f'href="/compare/{slug}-prices.html"' in row:
            return row
    return None


class CompareIndexFilterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = bcp.build_compare_index(ENTRIES)

    def test_pure_fruit_row(self):
        row = _row_for(self.html, "mango")
        self.assertIn('data-category="fruit"', row)
        self.assertNotIn("data-bushtucker", row)
        self.assertEqual(row.count("cat-badge-"), 1)

    def test_pure_bush_tucker_row(self):
        row = _row_for(self.html, "lemon-myrtle")
        self.assertIn('data-category="bush_tucker"', row)
        self.assertIn('data-bushtucker="1"', row)
        self.assertIn("cat-badge-bush", row)

    def test_cross_tagged_row_shows_both_badges(self):
        row = _row_for(self.html, "finger-lime")
        self.assertIn('data-category="fruit"', row)
        self.assertIn('data-bushtucker="1"', row)
        self.assertIn("cat-badge-fruit", row)
        self.assertIn("cat-badge-bush", row)

    def test_filter_controls_present(self):
        for arg in ("'all'", "'fruit'", "'bush_tucker'"):
            self.assertIn(f"filterSpecies({arg}, this)", self.html)
        self.assertIn("function filterSpecies(cat, btn)", self.html)
        self.assertIn("tr.hidden-row { display: none; }", self.html)


if __name__ == "__main__":
    unittest.main()
