"""
Tests for the category filter + badge on the /species/ index
(build_species_pages.build_species_index).

Guards the subtle bits that the golden file does not pin on its own:
  - every species renders a row (all rows server-rendered, so crawlable
    regardless of the active filter)
  - a fruit cross-tagged bush_tucker (the finger-lime case) carries BOTH
    data-category="fruit" and data-bushtucker="1", and its badge reads "Fruit"
    (its primary category), not "Bush Tucker"
  - the three filter pills, the filterSpecies() script, and the hidden-row CSS
    are present

Run from repo root with:
    python3 -m unittest discover tests/
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guide_helpers import bsp  # noqa: E402


def _entry(slug, common, latin, category=None, tags=None, in_stock=5):
    species = {"slug": slug, "common_name": common, "latin_name": latin}
    if category is not None:
        species["category"] = category
    if tags is not None:
        species["tags"] = tags
    return {
        "species": species,
        "in_stock_count": in_stock,
        "rarity": {},
        "total_count": 3,
        "nursery_count": 2,
        "price_range": "$10 to $40",
    }


SPECIES_DATA = [
    _entry("mango", "Mango", "Mangifera indica", in_stock=12),                       # pure fruit (no category field -> default fruit)
    _entry("lemon-myrtle", "Lemon Myrtle", "Backhousia citriodora",
           category="bush_tucker", in_stock=4),                                      # pure bush tucker
    _entry("finger-lime", "Finger Lime", "Microcitrus australasica",
           tags=["bush_tucker"], in_stock=8),                                        # fruit cross-tagged bush tucker
]


def _row_for(html, slug):
    """Return the <tr>...</tr> block whose link points at /species/<slug>.html."""
    body = html.split("<tbody>", 1)[-1]
    for row in re.findall(r"<tr\b.*?</tr>", body, re.S):
        if f'href="/species/{slug}.html"' in row:
            return row
    return None


class SpeciesIndexFilterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = bsp.build_species_index(SPECIES_DATA)

    def test_every_species_renders_a_row(self):
        for slug in ("mango", "lemon-myrtle", "finger-lime"):
            self.assertIsNotNone(_row_for(self.html, slug), f"no row for {slug}")

    def test_pure_fruit_row(self):
        row = _row_for(self.html, "mango")
        self.assertIn('data-category="fruit"', row)
        self.assertNotIn("data-bushtucker", row)
        self.assertIn("cat-badge-fruit", row)
        self.assertIn(">Fruit</span>", row)

    def test_pure_bush_tucker_row(self):
        row = _row_for(self.html, "lemon-myrtle")
        self.assertIn('data-category="bush_tucker"', row)
        self.assertIn('data-bushtucker="1"', row)
        self.assertIn("cat-badge-bush", row)
        self.assertIn(">Bush Tucker</span>", row)

    def test_cross_tagged_fruit_shows_under_both_but_labelled_fruit(self):
        row = _row_for(self.html, "finger-lime")
        # appears under the Bush Tucker pill (tag match) ...
        self.assertIn('data-bushtucker="1"', row)
        # ... but its primary category and badge are Fruit, not Bush Tucker
        self.assertIn('data-category="fruit"', row)
        self.assertIn("cat-badge-fruit", row)
        self.assertIn(">Fruit</span>", row)

    def test_filter_controls_present(self):
        for arg in ("'all'", "'fruit'", "'bush_tucker'"):
            self.assertIn(f"filterSpecies({arg}, this)", self.html)
        self.assertIn("function filterSpecies(cat, btn)", self.html)
        self.assertIn("tr.hidden-row { display: none; }", self.html)


if __name__ == "__main__":
    unittest.main()
