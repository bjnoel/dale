"""
The shipping-reachability page is the one page on treestock built to be cited by
somebody else, so its two arithmetic decisions are the ones worth pinning.

1. Nursery-day rollup. compute_rarity_scores in build_species_pages.py averages
   over LISTINGS, so a nursery carrying twenty named varieties of one species
   outvotes four nurseries carrying one each (DEC-246). Fine as an internal
   ranking signal, wrong in a published number. These tests assert a nursery
   counts once however many SKUs it lists.

2. Outage days are excluded, not averaged in. Six days in June and July recorded
   exactly one nursery because the scrapers failed. "Nothing was in stock
   anywhere in Australia" on those days is a fact about our cron, and averaging
   it in understated every state (it moved "in stock every single day" from 69
   species to 100). The threshold is measured, so a test that only checked the
   constant would be circular: these check the BEHAVIOUR at the observed values.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"


def _load():
    sys.path.insert(0, str(SCRAPERS))
    spec = importlib.util.spec_from_file_location(
        "build_shipping_reachability", SCRAPERS / "build_shipping_reachability.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load()


def _days(n, start=1):
    return [f"2026-03-{d:02d}" for d in range(start, start + n)]


class PanelCompleteness(unittest.TestCase):
    def test_total_outage_day_is_excluded(self):
        days = _days(4)
        reporting = {days[0]: 20, days[1]: 20, days[2]: 1, days[3]: 20}
        kept, dropped = mod.complete_days(days, reporting)
        self.assertEqual(dropped, [days[2]])
        self.assertEqual(kept, [days[0], days[1], days[3]])

    def test_partial_day_at_the_observed_worst_is_excluded(self):
        """0.60 of the panel is the worst partial day we have actually seen."""
        days = _days(2)
        kept, dropped = mod.complete_days(days, {days[0]: 25, days[1]: 15})
        self.assertEqual(dropped, [days[1]])
        self.assertEqual(kept, [days[0]])

    def test_worst_healthy_day_is_kept(self):
        """0.89 of the panel is the worst day with no outage. It must survive."""
        days = _days(2)
        kept, dropped = mod.complete_days(days, {days[0]: 19, days[1]: 17})
        self.assertEqual(dropped, [])
        self.assertEqual(kept, days)

    def test_a_growing_panel_does_not_retroactively_disqualify_march(self):
        """We tracked 8 nurseries in March and 25 in August. March is not an
        outage: completeness is judged against the running maximum up to that
        day, not against the final panel."""
        days = _days(3)
        kept, dropped = mod.complete_days(days, {days[0]: 8, days[1]: 16, days[2]: 25})
        self.assertEqual(dropped, [])
        self.assertEqual(kept, days)


class NurseryDayRollup(unittest.TestCase):
    """One nursery is one vote, whatever its SKU count."""

    SPECIES = [
        {"slug": "abiu", "common_name": "Abiu", "category": "fruit"},
        {"slug": "riberry", "common_name": "Riberry", "category": "fruit"},
    ]

    def _compute(self, stock, days, reporting=None):
        reporting = reporting or {d: 20 for d in days}
        return mod.compute(stock, days, reporting, self.SPECIES)

    def test_species_counts_once_per_day_however_many_nurseries(self):
        days = _days(2)
        stock = {"abiu": {days[0]: {"daleys", "ross-creek", "fruitopia"}, days[1]: {"daleys"}}}
        result = self._compute(stock, days)
        # 1 species in stock on each of 2 days, not 3 then 1.
        self.assertEqual(result["states"]["VIC"]["avg_species_in_stock_per_day"], 1.0)

    def test_a_state_only_counts_nurseries_that_ship_there(self):
        days = _days(1)
        # Guildford Garden Centre is WA-based and does not ship east.
        stock = {"abiu": {days[0]: {"guildford"}}}
        result = self._compute(stock, days)
        self.assertEqual(result["states"]["WA"]["species_ever_reachable"], 1)
        self.assertEqual(result["states"]["TAS"]["species_ever_reachable"], 0)
        self.assertIn("Abiu", result["states"]["TAS"]["species_never_reachable"])

    def test_national_scarcity_counts_days_in_stock_anywhere(self):
        days = _days(4)
        stock = {
            "abiu": {d: {"daleys"} for d in days},
            "riberry": {days[0]: {"daleys"}, days[1]: set(), days[2]: set(), days[3]: set()},
        }
        result = self._compute(stock, days)
        self.assertEqual(result["species"]["abiu"]["pct_of_days"], 100.0)
        self.assertEqual(result["species"]["riberry"]["days_in_stock_somewhere"], 1)
        self.assertEqual(result["species"]["riberry"]["pct_of_days"], 25.0)

    def test_an_outage_day_does_not_depress_the_scarcity_share(self):
        """The bug this whole exclusion exists for: a species in stock every day
        we actually measured must read 100%, not 75%."""
        days = _days(4)
        stock = {"abiu": {days[0]: {"daleys"}, days[1]: {"daleys"}, days[2]: set(), days[3]: {"daleys"}}}
        reporting = {days[0]: 20, days[1]: 20, days[2]: 1, days[3]: 20}
        result = self._compute(stock, days, reporting)
        self.assertEqual(result["window"]["days"], 3)
        self.assertEqual(result["window"]["days_excluded_incomplete"], 1)
        self.assertEqual(result["species"]["abiu"]["pct_of_days"], 100.0)


class PublishedPageContract(unittest.TestCase):
    """The page is published for citation, so the promises on it are testable."""

    def test_page_declares_its_licence_and_links_the_raw_data(self):
        days = _days(2)
        stock = {"abiu": {d: {"daleys"} for d in days}}
        result = mod.compute(stock, days, {d: 20 for d in days}, NurseryDayRollup.SPECIES)
        html = mod.build_page(result)
        self.assertIn("creativecommons.org/licenses/by/4.0", html)
        self.assertIn(f'href="/{mod.DATA_SLUG}"', html)
        self.assertIn('"@type": "Dataset"', html)
        # DEC-249: a page with no analytics tag reports 0 pageviews forever.
        self.assertIn("data.bjnoel.com/js/script", html)
        # treestock copy rule: no em dashes.
        self.assertNotIn("\u2014", html.split("<main")[1].split("</main>")[0])

    def test_the_page_is_in_the_sitemap(self):
        spec = importlib.util.spec_from_file_location(
            "build_sitemap", SCRAPERS / "build_sitemap.py"
        )
        sitemap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sitemap)
        self.assertIn(mod.PAGE_SLUG, [p for p, _, _ in sitemap.STATIC_PAGES])


if __name__ == "__main__":
    unittest.main()
