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
        # Fruit records carry no explicit category and default to "fruit";
        # the bush_tucker records (DAL-195 / P2.1) set it explicitly. Every
        # category present must be a known one.
        cats = set()
        for r in taxonomy.load_species():
            self.assertIn("category", r)  # default applied when the key is absent
            self.assertIn(r["category"], taxonomy.KNOWN_CATEGORIES)
            cats.add(r["category"])
        self.assertIn("fruit", cats)  # the fruit records still default to fruit

    def test_missing_file_returns_empty(self):
        self.assertEqual(taxonomy.load_species(SCRAPERS / "nope.json"), [])


class CategoryTest(unittest.TestCase):
    def test_categories_today(self):
        # P2.1 (DAL-195) added bush_tucker records: the category is present in
        # the taxonomy. It is not yet enabled (that is DAL-197 / P2.3).
        self.assertEqual(taxonomy.categories(), {"fruit", "bush_tucker"})

    def test_enabled_categories_switch(self):
        # DAL-197 (P2.3) enabled the bush tucker pilot.
        self.assertEqual(taxonomy.ENABLED_CATEGORIES, ("fruit", "bush_tucker"))

    def test_category_of_known_species(self):
        self.assertEqual(taxonomy.category_of("Mango"), "fruit")
        self.assertEqual(taxonomy.category_of("mango"), "fruit")  # case-insensitive

    def test_category_of_unknown(self):
        self.assertIsNone(taxonomy.category_of("Eucalyptus"))

    def test_enabled_species_today(self):
        # DAL-197 enabled bush_tucker, so enabled_species now spans both the
        # fruit and bush_tucker records (every category present is enabled).
        enabled = taxonomy.enabled_species()
        self.assertTrue(all(r["category"] in ("fruit", "bush_tucker")
                            for r in enabled))
        cats = {r["category"] for r in enabled}
        self.assertEqual(cats, {"fruit", "bush_tucker"})
        # nothing disabled remains, so the enabled set is every record
        self.assertEqual(len(enabled), len(taxonomy.load_species()))

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

    def test_live_file_bush_tucker_landing(self):
        # DAL-195 (P2.1) authored 20 bush_tucker records and tagged 8 adjacent
        # fruits. landing_species cross-lists by category OR tag regardless of
        # enablement, so the /bush-tucker/ page has content ready before the
        # DAL-197 enable. Every returned record must qualify one of those ways.
        land = taxonomy.landing_species("bush_tucker")
        self.assertTrue(land)
        for r in land:
            self.assertTrue(
                r.get("category") == "bush_tucker"
                or "bush_tucker" in r.get("tags", []),
                f"{r.get('common_name')} on the bush_tucker landing without "
                "the category or tag",
            )
        # the 8 cross-listed fruits keep category fruit (their URLs never move)
        tagged = [r for r in land if r.get("category") == "fruit"]
        self.assertEqual(len(tagged), 8)


if __name__ == "__main__":
    unittest.main()
