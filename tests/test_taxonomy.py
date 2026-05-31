"""
Tests for stocklib.taxonomy -- the category-aware species loader (the "all trees"
enabler). Today every record is fruit and ENABLED_CATEGORIES == ("fruit",), so
this pins the current behaviour and the category-default machinery.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib import taxonomy


class LoadSpeciesTest(unittest.TestCase):
    def test_loads_records(self):
        species = taxonomy.load_species()
        self.assertTrue(species, "expected species records")
        # matches the count in fruit_species.json
        raw = json.loads((SCRAPERS / "fruit_species.json").read_text())
        self.assertEqual(len(species), len(raw))

    def test_every_record_gets_a_category(self):
        for r in taxonomy.load_species():
            self.assertIn("category", r)
            self.assertEqual(r["category"], "fruit")  # default applied

    def test_missing_file_returns_empty(self):
        self.assertEqual(taxonomy.load_species(SCRAPERS / "nope.json"), [])


class CategoryTest(unittest.TestCase):
    def test_categories_is_fruit_only_today(self):
        self.assertEqual(taxonomy.categories(), {"fruit"})

    def test_enabled_categories_switch(self):
        self.assertEqual(taxonomy.ENABLED_CATEGORIES, ("fruit",))

    def test_category_of_known_species(self):
        self.assertEqual(taxonomy.category_of("Mango"), "fruit")
        self.assertEqual(taxonomy.category_of("mango"), "fruit")  # case-insensitive

    def test_category_of_unknown(self):
        self.assertIsNone(taxonomy.category_of("Eucalyptus"))

    def test_enabled_species_is_all_today(self):
        self.assertEqual(len(taxonomy.enabled_species()), len(taxonomy.load_species()))

    def test_is_enabled(self):
        self.assertTrue(taxonomy.is_enabled("Mango"))
        self.assertFalse(taxonomy.is_enabled("Eucalyptus"))


if __name__ == "__main__":
    unittest.main()
