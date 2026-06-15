"""
Tests for the category filter + badges on the /variety/ index
(build_variety_pages.build_variety_index).

The variety index is grouped into per-species sections; the category filter shows
or hides whole sections and composes with the existing search + state filter.
Guards:
  - each species section carries data-category (and data-bushtucker for tagged ones)
  - a cross-listed species (finger-lime: category fruit, tags ["bush_tucker"]) shows
    BOTH a Fruit and a Bush Tucker badge and is data-bushtucker="1"
  - the three category pills, the badge CSS, and the activeCat filter logic are present

Categories are resolved from the real fruit_species.json via the builder, so the test
uses real species names.

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

import build_variety_pages as bvp  # noqa: E402


def _entry(species, variety, slug, in_stock=4, states=("WA",)):
    return {
        "species": species,
        "variety": variety,
        "slug": slug,
        "nursery_count": 1,
        "in_stock": in_stock,
        "min_price": 19.95,
        "states": list(states),
    }


ENTRIES = [
    _entry("Mango", "Bowen", "mango-bowen"),                 # pure fruit
    _entry("Lemon Myrtle", "Standard", "lemon-myrtle-standard"),  # pure bush tucker
    _entry("Finger Lime", "Pink Ice", "finger-lime-pink-ice"),    # fruit cross-tagged bush tucker
]
VALID = {"mango", "lemon-myrtle", "finger-lime"}


def _section_for(html, slug):
    """Return the <section ...>...</section> block for a species slug (id=slug)."""
    for sec in re.findall(r"<section\b.*?</section>", html, re.S):
        if f'id="{slug}"' in sec:
            return sec
    return None


class VarietyIndexFilterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = bvp.build_variety_index(ENTRIES, VALID)

    def test_each_section_has_category(self):
        for slug in ("mango", "lemon-myrtle", "finger-lime"):
            sec = _section_for(self.html, slug)
            self.assertIsNotNone(sec, f"no section for {slug}")
            self.assertIn("data-category=", sec)

    def test_pure_fruit_section(self):
        sec = _section_for(self.html, "mango")
        self.assertIn('data-category="fruit"', sec)
        self.assertNotIn("data-bushtucker", sec)
        self.assertIn("cat-badge-fruit", sec)
        self.assertNotIn("cat-badge-bush", sec)

    def test_pure_bush_tucker_section(self):
        sec = _section_for(self.html, "lemon-myrtle")
        self.assertIn('data-category="bush_tucker"', sec)
        self.assertIn('data-bushtucker="1"', sec)
        self.assertIn("cat-badge-bush", sec)

    def test_cross_tagged_section_shows_both_badges(self):
        sec = _section_for(self.html, "finger-lime")
        self.assertIn('data-category="fruit"', sec)
        self.assertIn('data-bushtucker="1"', sec)
        self.assertIn("cat-badge-fruit", sec)
        self.assertIn("cat-badge-bush", sec)
        self.assertLess(sec.index("cat-badge-fruit"), sec.index("cat-badge-bush"))

    def test_filter_controls_present(self):
        for cat in ("all", "fruit", "bush_tucker"):
            self.assertIn(f'data-cat="{cat}"', self.html)
        self.assertIn("activeCat", self.html)
        self.assertIn(".cat-badge-bush", self.html)  # badge CSS injected via extra_style


if __name__ == "__main__":
    unittest.main()
