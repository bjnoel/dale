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


class SchemaTest(unittest.TestCase):
    """Authoring rules for species records (DEC-200 P1.1). A bad record fails
    here at commit time, not as a silent classification leak in production."""

    def setUp(self):
        self.records = taxonomy.load_species()

    def test_every_category_is_known(self):
        for r in self.records:
            self.assertIn(
                r["category"], taxonomy.KNOWN_CATEGORIES,
                f"{r.get('common_name')}: unknown category {r['category']!r}",
            )

    def test_every_tag_is_known(self):
        for r in self.records:
            for tag in r["tags"]:
                self.assertIn(
                    tag, taxonomy.KNOWN_CATEGORIES,
                    f"{r.get('common_name')}: unknown tag {tag!r}",
                )

    def test_slugs_are_unique(self):
        slugs = [r["slug"] for r in self.records]
        dupes = {s for s in slugs if slugs.count(s) > 1}
        self.assertFalse(dupes, f"duplicate slugs: {dupes}")

    def test_no_bare_ornamental_word_names(self):
        # "Lemon Myrtle" is a fine name; "Myrtle" alone would unlock crepe
        # myrtles through the vocabulary-scoped variety gate (design doc 3.4).
        import cultivar_parsing
        for r in self.records:
            names = [r.get("common_name", "")] + list(r.get("synonyms", []))
            for name in names:
                self.assertNotIn(
                    name.strip().lower(), cultivar_parsing._ORNAMENTAL_WORDS,
                    f"{r.get('common_name')}: bare ornamental word name {name!r}",
                )


class LandingSpeciesTest(unittest.TestCase):
    def _write(self, records):
        import json as _json
        import tempfile
        f = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, dir="/tmp")
        _json.dump(records, f)
        f.close()
        self.addCleanup(Path(f.name).unlink)
        return Path(f.name)

    def test_matches_category_or_tag(self):
        path = self._write([
            {"common_name": "Lemon Myrtle", "slug": "lemon-myrtle",
             "category": "bush_tucker"},
            {"common_name": "Finger Lime", "slug": "finger-lime",
             "category": "fruit", "tags": ["bush_tucker"]},
            {"common_name": "Mango", "slug": "mango"},
        ])
        names = [r["common_name"] for r in taxonomy.landing_species("bush_tucker", path)]
        self.assertEqual(names, ["Lemon Myrtle", "Finger Lime"])

    def test_no_matches_is_empty(self):
        path = self._write([{"common_name": "Mango", "slug": "mango"}])
        self.assertEqual(taxonomy.landing_species("native", path), [])

    def test_live_file_bush_tucker_is_empty_today(self):
        # No records are tagged yet; P2.1 authors them. This flips at P2.1.
        self.assertEqual(taxonomy.landing_species("bush_tucker"), [])


if __name__ == "__main__":
    unittest.main()
