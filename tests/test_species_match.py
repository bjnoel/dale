"""
Tests for stocklib.species_match — the shared title->species matcher
(extracted from build-dashboard.py; build_nursery_pages.py now uses it too).

Regression: build_nursery_pages previously had its own fork that matched the
genus name ANYWHERE in the title, so "Peach Florida Prince (Prunus persica)"
counted as Plum (first Prunus species in dict order). The nursery page's
species table then disagreed with the dashboard its In Stock counts link to
(All Rare Herbs showed Plum 4-in-stock/5-total vs the dashboard's 1/2).
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib.species_match import load_species_lookup, match_species


class SpeciesMatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lookup = load_species_lookup()

    def match(self, title):
        m = match_species(title, self.lookup)
        return m["cn"] if m else None

    def test_latin_genus_in_title_does_not_hijack_species(self):
        # The old nursery-page fork matched genus "Prunus" anywhere -> Plum.
        self.assertEqual(
            self.match("Peach Florida Prince (Prunus persica), fruit tree"),
            "Peach")
        self.assertEqual(
            self.match("Peach Tropic Snow (Prunus persica), fruit tree"),
            "Peach")

    def test_leading_word_match(self):
        self.assertEqual(self.match("Apple 'Granny Smith'"), "Apple")

    def test_longest_match_wins_over_prefix(self):
        # "finger lime" must not match plain "lime"
        self.assertEqual(self.match("Finger Lime Red Champagne"), "Finger Lime")

    def test_variety_first_fallback(self):
        # "Variety Species (size)" titles (Heritage Fruit Trees format)
        self.assertEqual(self.match("Akane Apple (medium)"), "Apple")

    def test_no_match_returns_none(self):
        self.assertIsNone(self.match("Gift Card $50"))

    def test_nursery_page_agrees_with_dashboard_matcher(self):
        # Both builders must import THIS matcher (no forked copies), so the
        # nursery-page species table always agrees with the dashboard view its
        # In Stock counts link to.
        import build_nursery_pages
        self.assertIs(build_nursery_pages.match_species, match_species)
        self.assertIs(build_nursery_pages.load_species_lookup, load_species_lookup)


if __name__ == "__main__":
    unittest.main()
