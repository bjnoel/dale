"""
The state-page showcase must not hand the table to one nursery.

build_location_pages used to sort the 60-row "in stock now" table by price
descending, with the comment "interesting/rare plants tend to cost more". They
do not reliably, and price turned out to be a proxy for "which nursery prices
highest" rather than for interest. Measured on live data 2026-08-24:

    WA    Perth Mobile Nursery  53 of 60 rows   $349 - $1,400
    QLD   Ladybird Nursery      37 of 60 rows   $199.95 - $530
    NSW   Ladybird Nursery      37 of 60 rows   identical to QLD in all 60 rows
    VIC   Ladybird Nursery      37 of 60 rows   57 of 60 shared with QLD

Nothing under $199.95 appeared on any of the three eastern pages, and the QLD
and NSW pages were the same page.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from build_location_pages import (  # noqa: E402
    MAX_PER_NURSERY, MAX_PER_SPECIES, pick_showcase, showcase_scores,
)
from stocklib.species_match import build_species_lookup  # noqa: E402
from stocklib.taxonomy import enabled_species  # noqa: E402

LOOKUP = build_species_lookup(enabled_species())


def prod(title, nursery, price, **kw):
    d = {"title": title, "nursery_key": nursery, "nursery_name": nursery,
         "price": price, "available": True, "url": f"https://x/{title}"}
    d.update(kw)
    return d


class ScoringTests(unittest.TestCase):
    def test_a_cultivar_only_one_nursery_has_outscores_a_common_one(self):
        products = [
            prod("Apple Gravenstein", "a", 40),
            prod("Apple Gravenstein", "b", 45),
            prod("Apple Gravenstein", "c", 50),
            prod("Apple Sundowner", "a", 40),
        ]
        scores = showcase_scores(products, LOOKUP, {})
        self.assertGreater(scores[3], scores[0],
                           "the cultivar one nursery stocks is the find")

    def test_price_does_not_decide_the_order(self):
        """The whole defect in one assertion."""
        cheap_and_rare = prod("Apple Sundowner", "a", 15)
        dear_and_common = prod("Apple Gravenstein", "a", 900)
        products = [cheap_and_rare, dear_and_common,
                    prod("Apple Gravenstein", "b", 40),
                    prod("Apple Gravenstein", "c", 45)]
        scores = showcase_scores(products, LOOKUP, {})
        self.assertGreater(scores[0], scores[1])

    def test_a_hard_to_find_species_gets_a_bonus(self):
        products = [prod("Jujube Chico", "a", 40), prod("Apple Sundowner", "a", 40)]
        rarity = {"jujube": {"hard_to_find": True}, "apple": {"hard_to_find": False}}
        scores = showcase_scores(products, LOOKUP, rarity)
        self.assertGreater(scores[0], scores[1])

    def test_missing_rarity_scores_are_survivable(self):
        """These pages must build on a box that never ran the species builder."""
        products = [prod("Apple Sundowner", "a", 40)]
        self.assertEqual(len(showcase_scores(products, LOOKUP, {})), 1)

    def test_pot_sizes_of_one_cultivar_are_not_three_separate_finds(self):
        """Scarcity keys on the variety slug, so one nursery listing the same
        cultivar in three sizes still counts as one nursery holding it."""
        products = [
            prod("Apple Gravenstein", "a", 40),
            prod("Apple Gravenstein (Bare rooted)", "a", 45),
            prod("Apple Sundowner", "b", 40),
        ]
        scores = showcase_scores(products, LOOKUP, {})
        self.assertAlmostEqual(scores[0], scores[2])


class DiversityCapTests(unittest.TestCase):
    """The caps stop one catalogue crowding OUT the others.

    They are proportional, not absolute: where there are no others to protect
    they lift to what the material supports, so a thin state page fills rather
    than showing 30 rows with 60 good products unshown. On the real data they
    never bind -- WA has 9 nurseries and ~106 species in stock.
    """

    SPECIES = ["Apple", "Fig", "Plum", "Pear", "Peach", "Cherry", "Mango",
               "Olive", "Lemon", "Lime", "Orange", "Apricot", "Banana",
               "Grape", "Guava", "Persimmon", "Pomegranate", "Mulberry",
               "Avocado", "Feijoa", "Jujube", "Loquat"]

    def _realistic(self, nurseries=9):
        """A catalogue shaped like a real state page: many species, many
        nurseries, comfortably more than 60 rows of material."""
        return [prod(f"{sp} Cultivar{j}", f"n{j}", 30 + i)
                for i, sp in enumerate(self.SPECIES)
                for j in range(nurseries)]

    def test_no_nursery_owns_the_table_when_others_have_stock(self):
        """The WA defect: Perth Mobile Nursery held 53 of 60 rows."""
        products = self._realistic() + [
            prod(f"Apple Hoard{i}", "greedy", 1000 - i) for i in range(200)
        ]
        shown = pick_showcase(products, LOOKUP, {})
        counts = Counter(p["nursery_key"] for p in shown)
        self.assertLessEqual(counts["greedy"], MAX_PER_NURSERY)
        self.assertGreater(len(counts), 5, "the other nurseries must still appear")

    def test_no_species_owns_the_table_when_others_have_stock(self):
        """Without this the prototype put five Daleys lilly pillies in the top
        ten: a different monopoly with the same effect on the reader."""
        products = self._realistic() + [
            prod(f"Apple Hoard{i}", f"n{i % 9}", 1000 - i) for i in range(200)
        ]
        shown = pick_showcase(products, LOOKUP, {})
        apples = sum(1 for p in shown if p["title"].startswith("Apple"))
        self.assertLessEqual(apples, MAX_PER_SPECIES)

    def test_a_realistic_catalogue_fills_the_page(self):
        self.assertEqual(len(pick_showcase(products=self._realistic(),
                                           species_lookup=LOOKUP,
                                           rarity_scores={})), 60)

    def test_a_thin_state_still_fills_rather_than_capping_itself_short(self):
        """Three nurseries at a hard cap of 10 would give 30 rows. The caps
        exist to protect nurseries that are not there."""
        shown = pick_showcase(self._realistic(nurseries=3), LOOKUP, {})
        self.assertEqual(len(shown), 60)

    def test_a_small_catalogue_is_returned_whole(self):
        products = [prod("Apple Sundowner", "a", 40), prod("Fig Black Genoa", "b", 20)]
        self.assertEqual(len(pick_showcase(products, LOOKUP, {})), 2)

    def test_the_result_is_deterministic(self):
        """Ties break on title, so two builds of the same data agree. Without a
        tiebreak the golden test would flap on dict ordering."""
        products = [prod(f"Apple Cultivar{i}", f"n{i % 4}", 40) for i in range(30)]
        self.assertEqual([p["title"] for p in pick_showcase(products, LOOKUP, {})],
                         [p["title"] for p in pick_showcase(products, LOOKUP, {})])

    def test_the_wa_pathology_cannot_come_back(self):
        """End to end on the shape of the live failure: one nursery whose whole
        catalogue is priced above everyone else's. Under the old price-desc
        sort it took every row."""
        products = self._realistic() + [
            prod(f"{sp} Premium{i}", "expensive", 900 + i)
            for i, sp in enumerate(self.SPECIES)
        ]
        shown = pick_showcase(products, LOOKUP, {})
        counts = Counter(p["nursery_key"] for p in shown)
        self.assertLessEqual(counts["expensive"], MAX_PER_NURSERY)
        self.assertLess(counts["expensive"], len(shown) / 2)


if __name__ == "__main__":
    unittest.main()
