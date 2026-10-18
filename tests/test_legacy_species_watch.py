"""Carried-over species watches (DEC-359) read as the species, not a cultivar.

/variety/cherry-nanking used to be "Cherry - Nanking". Since Nanking Cherry
got its own record the page covers every plain listing of the species, and
its copy said "Get notified when All Varieties Nanking Cherry comes back".
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import guide_helpers  # noqa: E402,F401  (puts tools/scrapers on sys.path)

import build_variety_pages as bvp  # noqa: E402
from cultivar_parsing import group_by_cultivar  # noqa: E402


class LegacySpeciesWatchCopyTest(unittest.TestCase):

    def _product(self, title, available=False):
        return {"title": title, "url": "https://nursery.example/x", "nursery": "daleys",
                "nursery_key": "daleys", "nursery_name": "Daleys Fruit Trees",
                "price": 39.0, "available": available, "ships_states": ["QLD", "NSW"],
                "restrict": "", "type_label": ""}

    def test_group_is_titled_by_the_species(self):
        groups = group_by_cultivar([self._product("Nanking Cherry"),
                                    self._product("Plum - Satsuma")])
        self.assertEqual(groups["cherry-nanking"]["title"], "Nanking Cherry")
        self.assertEqual(groups["plum-satsuma"]["title"], "Plum - Satsuma")

    def test_page_copy_names_the_species_alone(self):
        data = group_by_cultivar([self._product("Nanking Cherry")])["cherry-nanking"]
        html = bvp.build_variety_page("cherry-nanking", data, {"nanking-cherry"})
        self.assertIn("Buy Nanking Cherry Trees in Australia", html)
        self.assertIn("Get notified when Nanking Cherry comes back", html)
        self.assertIn("See the Nanking Cherry page", html)
        self.assertNotIn("All Varieties Nanking", html)
        self.assertNotIn("Nanking Cherry - All Varieties Trees", html)

    def test_cultivar_pages_keep_their_reading(self):
        self.assertEqual(bvp._reading_name("Satsuma", "Plum"), "Satsuma Plum")
        self.assertEqual(bvp._reading_name("All Varieties", "Jambolan"), "Jambolan")


if __name__ == "__main__":
    unittest.main()
