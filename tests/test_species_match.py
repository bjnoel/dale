"""
Tests for stocklib.species_match — the shared title->species matcher
(extracted from build-dashboard.py; build_nursery_pages.py now uses it too).

Regression: build_nursery_pages previously had its own fork that matched the
genus name ANYWHERE in the title, so "Peach Florida Prince (Prunus persica)"
counted as Plum (first Prunus species in dict order). The nursery page's
species table then disagreed with the dashboard its In Stock counts link to
(All Rare Herbs showed Plum 4-in-stock/5-total vs the dashboard's 1/2).
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib.species_match import (
    build_species_lookup,
    load_species_lookup,
    match_species,
    match_title,
)


class SapoteDisambiguationTest(unittest.TestCase):
    """White Sapote carried the bare synonym "Sapote", which _fallback_candidate
    matches at any position. That swept four unrelated species into the white
    sapote bucket: 12 of the 15 products on /buy-white-sapote-trees-*.html were
    canistel (Pouteria campechiana) or mamey sapote (Pouteria sapota), neither of
    which is even in the same family as Casimiroa edulis. Canistel was also the
    biggest untracked species we stocked, 11 products across 5 nurseries, and the
    titles that did NOT contain "sapote" ("Canistel - Lyndall", "Canistel Aurea")
    matched nothing at all and were invisible site-wide.

    Fixed by deleting the bare synonym and giving canistel and mamey sapote their
    own species records. Black Sapote was never affected: it matches on the full
    two-word name, which outranks a one-word candidate at the same position.
    """

    @classmethod
    def setUpClass(cls):
        cls.lookup = build_species_lookup()

    def _slug(self, title):
        m = match_title(title, self.lookup)
        return m["slug"] if m else None

    def test_canistel_titles_never_land_on_white_sapote(self):
        # Every canistel title seen in live nursery data, in its original spelling.
        for title in ("Canistel",
                      "Canistel  - Ross Sapote",
                      "Canistel - Lyndall",
                      "Canistel - Grey",
                      "Canistel - Kona",
                      "Canistel Aurea",
                      "Canistel (Yellow Sapote)",
                      "Cannistel Yellow Sapote (2 years old)",
                      "Egg Fruit Tree / Yellow Sapote / Canistel",
                      "CANISTEL or YELLOW SAPOTE (  Pouteria Campechiana ) Organic Seedling Plant"):
            self.assertEqual(self._slug(title), "canistel", title)

    def test_mamey_sapote_is_its_own_species(self):
        self.assertEqual(self._slug("Mamey Sapote"), "mamey-sapote")

    def test_white_sapote_still_matches_its_own_products(self):
        for title in ("White Sapote",
                      "White Sapote - MYSTERY Grafted (Seconds)",
                      "Aztec White Sapote Fruit Tree"):
            self.assertEqual(self._slug(title), "white-sapote", title)

    def test_black_sapote_unaffected(self):
        for title in ("Black Sapote Tahiti",
                      "Dwarf Black Sapote 'Maher'",
                      "Black Tahiti, Chocolate Black Sapote",
                      "BLACK SAPOTE / CHOCOLATE PUDDING FRUIT  ( Diospyros digyna ) Seed"):
            self.assertEqual(self._slug(title), "black-sapote", title)

    def test_unidentified_sapotes_match_nothing_rather_than_the_wrong_thing(self):
        # Green sapote (Pouteria viridis) and Bruno sapote are not tracked species.
        # Showing nothing beats filing them under a species they are not.
        for title in ("Green Sapote", "Bruno Sapote"):
            self.assertIsNone(self._slug(title), title)

    def test_pineapple_guava_is_feijoa_not_guava(self):
        # Acca sellowiana, genuinely sold under both names. This one is correct
        # and is pinned here so a future synonym cull does not "fix" it.
        self.assertEqual(self._slug("Pineapple Guava"), "feijoa")
        self.assertEqual(self._slug("Strawberry Guava"), "guava")

    def test_no_single_word_synonym_is_the_tail_of_another_species_name(self):
        """The bug class, not just the bug. A one-word synonym that ends another
        species' common name will swallow that species through the any-position
        fallback, exactly as "Sapote" swallowed Mamey/Green/Yellow Sapote."""
        species = json.loads(
            (REPO_ROOT / "tools" / "scrapers" / "fruit_species.json").read_text())
        names = {s["common_name"].lower() for s in species}
        offenders = []
        for s in species:
            for syn in s.get("synonyms", []):
                syn = syn.lower()
                if " " in syn:
                    continue
                for other in names:
                    if other != s["common_name"].lower() and other.endswith(" " + syn):
                        offenders.append(f"{s['common_name']} synonym {syn!r} swallows {other!r}")
        self.assertEqual(offenders, [], "; ".join(offenders))

    def test_no_dashes_in_species_descriptions(self):
        """Descriptions render into species and combo pages, so the treestock
        no-em-dash copy rule applies to them. Olive carried one for months on the
        highest-traffic page we have."""
        species = json.loads(
            (REPO_ROOT / "tools" / "scrapers" / "fruit_species.json").read_text())
        for s in species:
            for field in ("common_name", "description"):
                self.assertNotIn("—", s.get(field, ""), f"{s['slug']}.{field}")
                self.assertNotIn("–", s.get(field, ""), f"{s['slug']}.{field}")


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


class MatchTitleTest(unittest.TestCase):
    """match_title: the same matching algorithm on full species records.

    Regression: five builders (compare, species, state, trends pages and
    species alerts) each carried their own match_title. Most lacked prefix
    stripping and the variety-first fallback, so "Dwarf Apple Pink Lady" or
    "Akane Apple (medium)" counted on compare pages and the dashboard but
    silently vanished from species pages, state pages, trends and alerts.
    """
    @classmethod
    def setUpClass(cls):
        cls.lookup = build_species_lookup()

    def match(self, title):
        m = match_title(title, self.lookup)
        return m["common_name"] if m else None

    def test_returns_full_species_record(self):
        m = match_title("Apple 'Granny Smith'", self.lookup)
        self.assertEqual(m["common_name"], "Apple")
        self.assertIn("slug", m)

    def test_prefix_stripping(self):
        # The forks without prefix stripping dropped these entirely.
        self.assertEqual(self.match("Dwarf Apple Pink Lady"), "Apple")
        self.assertEqual(self.match("Grafted Avocado Hass"), "Avocado")
        self.assertEqual(self.match("Bare Root Peach Tropic Snow"), "Peach")

    def test_variety_first_fallback(self):
        # Heritage Fruit Trees' "Variety Species (size)" format.
        self.assertEqual(self.match("Akane Apple (medium)"), "Apple")

    def test_longest_match_wins(self):
        self.assertEqual(self.match("Finger Lime Red Champagne"), "Finger Lime")

    def test_no_match_returns_none(self):
        self.assertIsNone(self.match("Grafting Tape 25mm"))

    def test_all_species_surfaces_share_one_matcher(self):
        # Every builder that groups products by species must import THE
        # matcher, so no two pages can disagree about what a product is.
        import build_compare_pages
        import build_location_pages
        import build_nursery_compare
        import build_species_pages
        import build_species_state_pages
        import build_species_trends
        import send_species_alerts
        for mod in (build_compare_pages, build_location_pages,
                    build_nursery_compare, build_species_pages,
                    build_species_state_pages, send_species_alerts):
            self.assertIs(mod.match_title, match_title, mod.__name__)
            self.assertIs(mod.build_species_lookup, build_species_lookup,
                          mod.__name__)
        self.assertIs(build_species_trends.match_title, match_title)
        self.assertIs(build_species_trends.build_lookup, build_species_lookup)


if __name__ == "__main__":
    unittest.main()
