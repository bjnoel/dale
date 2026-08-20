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



class OrnamentalRelativeTest(unittest.TestCase):
    """1.6a. match_title matches a species name mid-title, so the ornamental
    cousins of our fruit species were filed as the fruit itself. Measured on
    the live catalogue 2026-08-20: 60 titles across 14 species.

    /variety/ already kept them apart (parse_cultivar reads "Ornamental Pear -
    Bradford" as the species "Ornamental Pear", which the DEC-195 gate then
    rejects), so this aligns the two consumers rather than deciding anything
    new. Every title below was live.
    """

    def setUp(self):
        self.lookup = load_species_lookup()

    def _cn(self, title):
        m = match_title(title, self.lookup)
        return m.get("cn") if m else None

    def test_crabapple_both_forms(self):
        """The plan's starting case. The singular was ALREADY mis-filed as
        Apple; the plural escaped only because "apples" is not a lookup key,
        which is luck that 1.6b's plural work is about to take away. Both
        directions pinned, deliberately.
        """
        for title in ("Crab Apple Charlottae (Flowering tree)",
                      "Crab Apples Charlottae (Flowering tree)",
                      "Crab apple Ioensis Plena",
                      "Crab Apple 'Tom Matthews' (Malus spp.) 300mm pot PICK UP ONLY",
                      "Crab Apple Tree (Malus spp.) - Advanced PICK UP ONLY"):
            with self.subTest(title=title):
                self.assertIsNone(self._cn(title))

    def test_real_apples_unaffected(self):
        self.assertEqual(self._cn("Apple Pink Lady"), "Apple")
        self.assertEqual(self._cn("Apple - Granny Smith"), "Apple")

    def test_flowering_prunus_and_quince(self):
        for title in ("Flowering Cherry - Mt Fuji",
                      "Flowering Cherry Kanzan (Prunus serrulata)",
                      "Dwarf Flowering Cherry - Kojo No Mai",
                      "Yoshino Flowering Cherry yedoensis (Prunus x)",
                      "Flowering Peach - Alboplena",
                      "Super Dwarf Flowering Peach 'White' (Prunus Persica)",
                      "Pink Roseoplena flowering peach [Bare rooted]",
                      "Flowering Plum Blireana",
                      "Flowering Purple-Leafed Plum (Prunus cerasifera Nigra)",
                      "Flowering Apricot Bush Form Pink (Prunus mume)",
                      "Flowering Almond Double pink (Bare rooted)",
                      "Super Dwarf Flowering Nectarine 'Pink'",
                      "Flowering Quince Nivalis (Chaenomeles speciosa)"):
            with self.subTest(title=title):
                self.assertIsNone(self._cn(title))

    def test_flowering_after_the_species_is_not_ornamental(self):
        """The single live counter-example, and the reason "flowering" is
        positional while "ornamental" is not. A red-flowering strawberry is
        still a strawberry.
        """
        self.assertEqual(self._cn("Strawberry - Red Flowering"), "Strawberry")

    def test_ornamental_in_any_position(self):
        """Verified against all 14,751 live titles: no title carrying
        "ornamental" is a fruiting variety, including the five where the word
        trails the species name.
        """
        for title in ("Ornamental Pear - Bradford",
                      "Ornamental Pear 'Capital' (Pyrus calleryana)",
                      "Ornamental Grape Vine",
                      "Ornamental Plum - Nigra",
                      "Grape - Ornamental",
                      "Pomegranate - Ornamental",
                      "Pineapple - Mini Ornamental",
                      "Olive | Bambalina Dwarf Ornamental",
                      "Weeping Mulberry - Ornamental - Chaparral"):
            with self.subTest(title=title):
                self.assertIsNone(self._cn(title))

    def test_weeping_is_deliberately_not_a_qualifier(self):
        """"weeping" is genuinely mixed on live data and no positional or
        vocabulary rule separates it, so adding it would cost real fruit.
        These three are fruiting trees and must keep matching.
        """
        self.assertEqual(self._cn("Star apple Weeping Grafted"), "Star Apple")
        self.assertEqual(self._cn("Mulberry - Weeping"), "Mulberry")
        self.assertEqual(self._cn("Weeping Mulberry 'White' (PICKUP ONLY)"), "Mulberry")

    def test_guard_applies_to_match_species_too(self):
        """Two functions, two copies of the leading/fallback cascade. Guarding
        only match_title would leave the dashboard and nursery pages, which
        call match_species, still bucketing ornamentals as fruit.
        """
        self.assertIsNone(match_species("Ornamental Pear - Bradford", self.lookup))
        self.assertIsNone(match_species("Flowering Cherry - Mt Fuji", self.lookup))
        self.assertIsNone(match_species("Crab apple Ioensis Plena", self.lookup))
        real = match_species("Apple Pink Lady", self.lookup)
        self.assertEqual(real["cn"], "Apple")
        self.assertEqual(real["cv"], "Pink Lady")



class DerivedLookupKeyTest(unittest.TestCase):
    """1.6b. match_title only matched a registry name spelled exactly as the
    registry spells it, so two ordinary title forms missed: the plural and the
    closed-up compound. Fixed with explicit derived keys, never a stemmer.
    68 live titles recovered on 2026-08-20.
    """

    def setUp(self):
        self.lookup = load_species_lookup()

    def _cn(self, title):
        m = match_title(title, self.lookup)
        return m.get("cn") if m else None

    def test_plurals(self):
        for title, want in (
                ("Biloxi Blueberries - 50mm pots", "Blueberry"),
                ("Autumn Bliss raspberries (pack of five)", "Raspberry"),
                ("Pears Beurre Bosc ( pome fruit)", "Pear"),
                ("Nectarines Fantasia (Bare rooted)", "Nectarine"),
                ("Imperial Mandarins (citrus)", "Mandarin"),
                ("Washington Navel Oranges (citrus)", "Orange"),
                ("Villa Franca Lemons (citrus)", "Lemon"),
                ("White Mulberries", "Mulberry"),
                ("Strawberries", "Strawberry"),
                ("White currants", "Currant"),
                ("Figs Tree Peter Good", "Fig"),
                ("Earli rich peaches", "Peach")):
            with self.subTest(title=title):
                self.assertEqual(self._cn(title), want)

    def test_singular_still_matches(self):
        for title, want in (("Biloxi Blueberry", "Blueberry"),
                            ("Apple Pink Lady", "Apple"),
                            ("Pear Beurre Bosc", "Pear")):
            with self.subTest(title=title):
                self.assertEqual(self._cn(title), want)

    def test_one_word_compounds(self):
        for title in ("Fingerlime - Small Seedling", "Red Fingerlime",
                      "Wauchope Grafted Fingerlime", "Yellow Fingerlime"):
            with self.subTest(title=title):
                self.assertEqual(self._cn(title), "Finger Lime")
        self.assertEqual(self._cn("Finger Lime Alstonville"), "Finger Lime")

    def test_derived_keys_never_shadow_a_canonical_name(self):
        """Derived keys are added in a SECOND pass with setdefault, so every
        name the registry actually writes still resolves to exactly what it
        resolved to before. Measured on the live registry: 339 names produce
        537 derived keys and zero collisions.

        Asserted against a canonical-only lookup rather than against each
        record, because two registry names genuinely collide already and that
        predates this work: "Native Raspberry" and "Atherton Raspberry" are
        listed as synonyms of Raspberry AND "Native Raspberry" is a species
        record in its own right, which wins. That is a registry data question,
        not a matcher one, and this test must not silently adopt it.
        """
        from stocklib.taxonomy import enabled_species
        canonical_only = {}
        for sp in enabled_species():
            canonical_only[sp["common_name"].lower()] = sp["common_name"]
            for syn in sp.get("synonyms", []):
                if syn:
                    canonical_only[syn.lower()] = sp["common_name"]
        for key in canonical_only:
            with self.subTest(key=key):
                self.assertIn(key, self.lookup)

    def test_derived_pass_is_additive_only(self):
        """The stronger version of the above: canonical keys resolve to the
        same record with and without the derived pass."""
        from stocklib.species_match import _add_derived
        from stocklib.taxonomy import enabled_species
        plain = {}
        derived_pairs = []
        for sp in enabled_species():
            entry = {"cn": sp["common_name"]}
            plain[sp["common_name"].lower()] = entry
            derived_pairs.append((sp["common_name"], entry))
            for syn in sp.get("synonyms", []):
                if syn:
                    plain[syn.lower()] = entry
                    derived_pairs.append((syn, entry))
        before = {k: v["cn"] for k, v in plain.items()}
        _add_derived(plain, derived_pairs)
        after = {k: plain[k]["cn"] for k in before}
        self.assertEqual(before, after)
        self.assertGreater(len(plain), len(before))

    def test_plurals_do_not_resurrect_the_crabapple(self):
        """THE reason 1.6a ran first. "Crab Apples Charlottae" used to escape
        only because "apples" was not a lookup key. 1.6b makes it one, so
        without 1.6a's guard this commit would have started mis-filing the
        ornamental crabapple that the audit found escaping by luck.
        """
        for title in ("Crab Apples Charlottae (Flowering tree)",
                      "Crab Apple Charlottae (Flowering tree)",
                      "Ornamental Pears Bradford",
                      "Flowering Cherries Mt Fuji"):
            with self.subTest(title=title):
                self.assertIsNone(self._cn(title))

    def test_no_stemmer(self):
        """The vocabulary is a closed, readable set. A stemmer would match
        arbitrary inflections; these are not registry-derived spellings.
        """
        for title in ("Appling", "Blueberrying Season", "Peached"):
            with self.subTest(title=title):
                self.assertIsNone(self._cn(title))

    def test_quoted_fallback_landmine_still_holds(self):
        """The chilli range is rejected ONLY by the quote characters in
        fallback position, and 1.6b must not have loosened that. Pinned in
        both directions, because most of it passes by accident.
        """
        for title in ("Chilli 'Lemon Drop'", "Chilli 'Aji Pineapple'",
                      "Chilli 'Red Hot Cherry'", "Berzelia 'Strawberry Jelly'"):
            with self.subTest(title=title):
                self.assertIsNone(self._cn(title))
        self.assertEqual(self._cn("Blueberry 'Biloxi'"), "Blueberry")



class RegistryBatchTest(unittest.TestCase):
    """1.5, first batch: 12 species records for fruit that had live stock and
    no registry entry. Berries first, then rare tropicals, per the plan.
    Counts are live titles on 2026-08-20.
    """

    def setUp(self):
        self.lookup = load_species_lookup()

    def _cn(self, title):
        m = match_title(title, self.lookup)
        return m.get("cn") if m else None

    def test_rubus_hybrid_berries(self):
        for title, want in (("Tayberry", "Tayberry"),
                            ("Tayberry 2L", "Tayberry"),
                            ("Berry - Boysenberry", "Boysenberry"),
                            ("Boysenberry Fresh Potted", "Boysenberry"),
                            ("Youngberry Rubus Spp Bare Root", "Youngberry"),
                            ("Berry - Loganberry Thornless", "Loganberry"),
                            ("Lawtonberry - Cane", "Lawtonberry")):
            with self.subTest(title=title):
                self.assertEqual(self._cn(title), want)

    def test_rare_tropicals(self):
        for title, want in (("Achacha", "Achacha"),
                            ("Achacha Grafted", "Achacha"),
                            ("Kwai Muk - Richmond", "Kwai Muk"),
                            ("Bignay (Antidesma bunius)", "Bignay"),
                            ("Nam Nam Tree  ( Cynometra Cauliflora )", "Nam Nam"),
                            ("Giant Lau Lau (syzygium megacarpa) - Medium", "Lau Lau")):
            with self.subTest(title=title):
                self.assertEqual(self._cn(title), want)

    def test_achacha_synonyms(self):
        """primal-fruits and ladybird both sell it under the Bolivian name."""
        self.assertEqual(self._cn("Achacha -Garcinia humilis"), "Achacha")
        self.assertEqual(self._cn("Achachairu"), "Achacha")
        self.assertEqual(self._cn("\u200bAchachair\u00fa (Garcinia humilis)"), "Achacha")

    def test_both_breadfruits_added_together_on_purpose(self):
        """"African Breadfruit" is Treculia africana, a different genus from
        Artocarpus altilis. Adding only "Breadfruit" would have swept the
        African one into it through the any-position fallback. Adding both
        lets the longest LEADING match win, which is the matcher's own rule.
        """
        self.assertEqual(self._cn("Breadfruit"), "Breadfruit")
        self.assertEqual(self._cn("African Breadfruit"), "African Breadfruit")

    def test_garcinia_is_deliberately_not_a_species_record(self):
        """The plan listed "Garcinia" as a batch member. It is a GENUS: 17 live
        titles span at least nine species (humilis/achacha, madruno,
        macrophylla, paniculata, gardneriana, cambogia, dulcis, warrenii,
        hombroniana) plus two mangosteens. One record would collapse all of
        them into one bucket, which is the mis-filing 1.6a exists to stop.
        Achacha is added by its own name instead; the rest stay unclassified
        until someone adds them individually.
        """
        for title in ("Garcinia Madruno", "Garcinia Macrophylla",
                      "Garcinia Gardneriana", "Garcinia paniculata (tropical fruit)",
                      'Garcinia cambogia "Red"', "Garcinia warrenii"):
            with self.subTest(title=title):
                self.assertIsNone(self._cn(title))

    def test_grumichama_was_already_registered(self):
        """Also on the plan's list, but it has had a record (and a growing
        guide) for some time. Pinned so the stale entry is not re-added.
        """
        self.assertEqual(self._cn("Grumichama - Black"), "Grumichama")

    def test_new_records_carry_the_required_fields(self):
        import json as _json
        from pathlib import Path as _Path
        recs = _json.loads((_Path(__file__).resolve().parent.parent
                            / "tools" / "scrapers" / "fruit_species.json").read_text())
        by_name = {r["common_name"]: r for r in recs}
        for name in ("Tayberry", "Boysenberry", "Youngberry", "Loganberry",
                     "Lawtonberry", "Achacha", "Kwai Muk", "Bignay", "Nam Nam",
                     "Lau Lau", "Breadfruit", "African Breadfruit"):
            with self.subTest(name=name):
                r = by_name[name]
                for field in ("common_name", "latin_name", "slug", "region",
                              "synonyms"):
                    self.assertIn(field, r)
                self.assertTrue(r["slug"] and " " not in r["slug"])
        # slugs stay unique across the whole registry
        slugs = [r["slug"] for r in recs]
        self.assertEqual(len(slugs), len(set(slugs)))


if __name__ == "__main__":
    unittest.main()
