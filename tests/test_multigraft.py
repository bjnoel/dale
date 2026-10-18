"""Multi-graft trees on every named species' page (2026-10-18).

A product files under one species, the first named, so "Peach + Nectarine +
Plum + Peachcot" never showed on the plum page. Benedict: list multi-grafts
on the other species' pages in a separate, lower section; leave hybrids
alone. Titles below are live ones from 2026-10-18.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guide_helpers import bsp  # noqa: E402

from stocklib.species_match import (  # noqa: E402
    build_species_lookup,
    load_species_lookup,
    multigraft_species,
)


class MultigraftSpeciesTest(unittest.TestCase):

    def setUp(self):
        self.lookup = load_species_lookup()

    def test_multigrafts_name_every_species_in_title_order(self):
        for title, want in (
                ("Peach + Nectarine + Plum + Peachcot", ["peach", "nectarine", "plum"]),
                ("Lemon & Lime Tree (QLD Only)", ["lemon", "lime"]),
                ("Imperial Mandarin and Cara Cara Orange Tree", ["mandarin", "orange"]),
                ("Peach/Nectarine Multi Graft – SweetSensation/RubySensation", ["peach", "nectarine"]),
                ("Double Grafted Lemon / Lime", ["lemon", "lime"]),
                ("Lime + Lemonade", ["lime", "lemon"])):
            with self.subTest(title=title):
                self.assertEqual(multigraft_species(title, self.lookup), want)

    def test_hybrids_are_one_fruit_not_a_multigraft(self):
        for title in ("Nectarine x Plum – Spicezee",
                      "Peach x Nectarine – Peacharine",
                      "Plumscrumptious Plum x Apricot (Bare-Rooted)",
                      "Sugar ' spice Nectarine and plum Hybrid (stone fruit)"):
            with self.subTest(title=title):
                self.assertEqual(multigraft_species(title, self.lookup), [])

    def test_cultivar_names_are_never_read_as_species(self):
        # Quoted, or after a spaced dash: "Satsuma" is a mandarin synonym and
        # "Strawberry" a species, but here they name a plum and a guava.
        for title in ("Plum Combo - 'Santa Rosa' & 'Satsuma'",
                      "Plum Multi Graft – Satsuma/Santa Rosa",
                      "Guava 'Red Cherry/Strawberry' - Large",
                      "Apple Pollinating Duo - 'Fuji' and 'Jonathan'"):
            with self.subTest(title=title):
                self.assertEqual(multigraft_species(title, self.lookup), [])

    def test_a_slash_writing_a_second_name_is_one_tree(self):
        self.assertEqual(multigraft_species("Amla / Indian Gooseberry", self.lookup), [])
        # The binomial vetoes the second name's fall-through to Plum.
        self.assertEqual(multigraft_species(
            "DAVIDSON PLUM / MULLUMBIMBI PLUM (Davidsonia Jerseyana) Seedling Plant Fruit Tree",
            self.lookup), [])

    def test_works_on_the_full_record_lookup_too(self):
        self.assertEqual(multigraft_species("Pomelo + Orange", build_species_lookup()),
                         ["pomelo", "orange"])


class SpeciesPageMultigraftSectionTest(unittest.TestCase):

    SPECIES = {"common_name": "Plum", "latin_name": "Prunus salicina / domestica",
               "slug": "plum", "region": "East Asia/Europe", "description": "A plum blurb."}

    def _product(self, title, price, available=True):
        return {"title": title, "url": "https://nursery.example/x",
                "nursery_key": "fruit-salad-trees", "nursery_name": "Fruit Salad Trees",
                "price": price, "available": available}

    def test_grouped_under_the_other_species_only(self):
        products = [self._product("Peach + Nectarine + Plum + Peachcot", 89.0),
                    self._product("Plum - Satsuma", 40.0),
                    self._product("Nectarine x Plum – Spicezee", 45.0)]
        groups = bsp.group_multigrafts(products, build_species_lookup())
        self.assertEqual([p["title"] for p in groups["plum"]],
                         ["Peach + Nectarine + Plum + Peachcot"])
        self.assertIn("nectarine", groups)
        self.assertNotIn("peach", groups)  # its own page already lists it

    def test_separate_section_not_counted_in_the_page_figures(self):
        own = [self._product("Plum - Satsuma", 40.0)]
        graft = [self._product("Peach + Nectarine + Plum + Peachcot", 89.0)]
        html = bsp.build_species_page(self.SPECIES, own, multigraft_products=graft)
        self.assertIn('id="multigraft"', html)
        self.assertIn("Also on multi-graft trees (1)", html)
        self.assertIn("All Plum listings (1)", html)
        self.assertLess(html.index('id="listings"'), html.index('id="multigraft"'))
        self.assertNotIn("$89.00 to", html)  # price range is own listings only

    def test_no_section_without_multigrafts(self):
        html = bsp.build_species_page(self.SPECIES, [self._product("Plum - Satsuma", 40.0)])
        self.assertNotIn('id="multigraft"', html)


if __name__ == "__main__":
    unittest.main()
