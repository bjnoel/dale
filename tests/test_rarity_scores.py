"""
`hard_to_find` is a PUBLIC CLAIM, so it gets tested like one.

The flag written by `compute_rarity_scores` renders as a "Hard to find" badge on
/rare.html, on the homepage stock table and on the state buy pages. Until
DEC-341 / DAL-293 its availability half averaged over LISTINGS, so a nursery
carrying twenty named varieties of one species outvoted four nurseries carrying
one each, and a species could read as scarce purely because whoever stocks it
keeps thin SKUs. On 2026-09-17 that badged 45 species, 37 of which were in stock
somewhere in Australia on essentially every measured day.

These tests pin the four things that make the badge honest:

1. Nursery-day rollup, not listing-day. `test_thin_skus_do_not_make_a_species_rare`
   is built to FAIL under the old rule: it is the exact shape (one nursery, many
   dead SKUs, one live one) that produced the false badges.
2. Outage days are excluded rather than counted as "nobody had any" (DEC-324).
3. A species we have barely observed is never badged. An unbadged rare plant is a
   missed badge; a badged common plant is a false statement to a visitor.
4. The badge and the CC BY dataset at /shipping-reachability.json are computed
   from the same rollup AND divide by the same denominator, which is what
   DAL-293 was for. The denominator is every measured day, not every day the
   species happened to be listed; those differ, and publishing both is the
   defect.

Real nursery keys and the real species matcher are used throughout, so these
exercise the same registry filter and title matching production does. Only the
availability history is synthetic, which is the part being tested.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"


def _load(name):
    sys.path.insert(0, str(SCRAPERS))
    spec = importlib.util.spec_from_file_location(name, SCRAPERS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bsp = _load("build_species_pages")
bsr = _load("build_shipping_reachability")

from stocklib.species_match import build_species_lookup  # noqa: E402
from stocklib.taxonomy import enabled_species  # noqa: E402

LOOKUP = build_species_lookup(enabled_species())
NURSERIES = sorted(bsr.SHIPPING_MAP)

#: Comfortably above MIN_OBSERVED_DAYS so the observability guard is not what is
#: being tested, except in the test that tests it.
N_DAYS = 60
DAYS = [f"2026-{3 + d // 28:02d}-{d % 28 + 1:02d}" for d in range(N_DAYS)]


def _write_history(root: Path, nursery: str, products: list[dict]):
    """products: [{"title": str, "in_stock_days": [...], "listed_days": [...]}]"""
    d = root / nursery
    d.mkdir(parents=True, exist_ok=True)
    (d / "availability.json").write_text(json.dumps({
        "nursery": nursery,
        "products": {
            p["title"]: {
                "title": p["title"],
                "days": {
                    day: {"a": day in p["in_stock_days"]}
                    for day in p.get("listed_days", DAYS)
                },
            }
            for p in products
        },
    }))


def _by_species(slug: str, nurseries: list[str]):
    """The current-snapshot shape compute_rarity_scores takes, minimal."""
    return {slug: {"products": [
        {"nursery_key": n, "available": True} for n in nurseries
    ]}}


class NurseryDayRollup(unittest.TestCase):
    def test_thin_skus_do_not_make_a_species_rare(self):
        """The exact shape that produced 37 false badges.

        One nursery lists twenty varieties of the species. Nineteen are never in
        stock, one always is. So a buyer could get one on every single day.

        Listing-day average: 1 of 20 listings in stock = 0.05 availability, which
        at two nurseries scores 93.6 and badges VERY RARE.
        Nursery-day rollup: in stock somewhere on 60 of 60 days, so not rare.
        """
        shops = NURSERIES[:2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            titles = [f"Jaboticaba '{chr(65 + i)}'" for i in range(20)]
            _write_history(root, shops[0], [
                {"title": titles[0], "in_stock_days": DAYS},
                *({"title": t, "in_stock_days": []} for t in titles[1:]),
            ])
            scores = bsp.compute_rarity_scores(root, _by_species("jaboticaba", shops), LOOKUP)

        got = scores["jaboticaba"]
        self.assertEqual(got["days_observed"], N_DAYS)
        self.assertEqual(got["days_in_stock"], N_DAYS)
        self.assertEqual(got["avg_availability"], 1.0)
        self.assertFalse(
            got["hard_to_find"],
            "a species buyable on every measured day must never be badged hard to find",
        )

    def test_a_species_unbuyable_on_most_days_is_still_badged(self):
        """The fix must not simply empty the page: real scarcity still scores."""
        shops = NURSERIES[:1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_history(root, shops[0], [
                {"title": "Kakadu Plum", "in_stock_days": DAYS[:3]},
            ])
            scores = bsp.compute_rarity_scores(root, _by_species("kakadu-plum", shops), LOOKUP)

        got = scores["kakadu-plum"]
        self.assertEqual(got["days_in_stock"], 3)
        self.assertTrue(got["hard_to_find"])
        self.assertGreaterEqual(got["score"], bsp.HARD_TO_FIND_SCORE)

    def test_two_nurseries_stocking_on_alternate_days_is_not_scarce(self):
        """Neither shop has it half the time; the country always does.

        This is the rollup doing what a per-nursery average cannot: the question
        is whether a buyer can get one, not whether a given shop has one.
        """
        shops = NURSERIES[:2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_history(root, shops[0], [{"title": "Abiu", "in_stock_days": DAYS[0::2]}])
            _write_history(root, shops[1], [{"title": "Abiu", "in_stock_days": DAYS[1::2]}])
            scores = bsp.compute_rarity_scores(root, _by_species("abiu", shops), LOOKUP)

        self.assertEqual(scores["abiu"]["avg_availability"], 1.0)
        self.assertFalse(scores["abiu"]["hard_to_find"])


class OutageDays(unittest.TestCase):
    def test_a_scraper_outage_day_does_not_count_as_nobody_had_any(self):
        """DEC-324: a failed cron is not a fact about Australian nurseries.

        Twenty nurseries report on every day but the last, where one reports and
        has nothing. Counting it would drop availability below 1.0; excluding it
        keeps the species honestly common.
        """
        shops = NURSERIES[:20]
        healthy, outage = DAYS[:-1], DAYS[-1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i, shop in enumerate(shops):
                _write_history(root, shop, [{
                    "title": "Feijoa",
                    "in_stock_days": healthy,
                    "listed_days": DAYS if i == 0 else healthy,
                }])
            scores = bsp.compute_rarity_scores(root, _by_species("feijoa", shops), LOOKUP)

        got = scores["feijoa"]
        self.assertEqual(got["days_observed"], len(healthy), f"{outage} should be excluded")
        self.assertEqual(got["avg_availability"], 1.0)


class ObservabilityGuard(unittest.TestCase):
    def test_a_barely_observed_species_is_never_badged(self):
        """A species added to the taxonomy last week has no scarcity record.

        The denominator is every measured day, so without the guard its first
        night in the data reads as "in stock on 0 of the 60 days we have been
        measuring" and it gets badged VERY RARE. The guard counts the days the
        species was actually LISTED somewhere, which is what we have watched.
        """
        short = DAYS[: bsp.MIN_OBSERVED_DAYS - 1]
        shops = NURSERIES[:2]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # A second nursery reports all 60 days so the panel is complete
            # throughout: the window is fully measured, the SPECIES is not.
            _write_history(root, shops[0], [
                {"title": "Kakadu Plum", "in_stock_days": [], "listed_days": short},
                {"title": "Feijoa", "in_stock_days": DAYS},
            ])
            _write_history(root, shops[1], [{"title": "Feijoa", "in_stock_days": DAYS}])
            scores = bsp.compute_rarity_scores(root, _by_species("kakadu-plum", shops), LOOKUP)

        got = scores["kakadu-plum"]
        self.assertEqual(got["days_listed"], len(short))
        self.assertEqual(got["days_observed"], N_DAYS, "the window is fully measured")
        self.assertFalse(
            got["hard_to_find"],
            "too little history to claim scarcity in public",
        )

    def test_the_guard_is_not_tuned_to_todays_data(self):
        """Every tracked species has 185+ days of history against a 189-day
        measurable window, so the guard is nowhere near any live species. A
        threshold set at the value that makes today come out right is not a
        threshold (DEC-323)."""
        self.assertLessEqual(bsp.MIN_OBSERVED_DAYS, 60)


class AgreesWithThePublishedDataset(unittest.TestCase):
    def test_badge_and_cc_by_dataset_read_the_same_rollup(self):
        """DAL-293's actual ask: the two published numbers must not disagree.

        Same fixture through both code paths. `days_in_stock` behind the badge
        must equal `days_in_stock_somewhere` in shipping-reachability.json.
        """
        shops = NURSERIES[:2]
        in_stock = DAYS[:17]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_history(root, shops[0], [{"title": "Riberry", "in_stock_days": in_stock}])
            _write_history(root, shops[1], [{"title": "Riberry", "in_stock_days": in_stock[:5]}])
            scores = bsp.compute_rarity_scores(root, _by_species("riberry", shops), LOOKUP)
            stock, days, reporting, _listed = bsr.load_stock_history(root, LOOKUP)
            published = bsr.compute(
                stock, days, reporting, [{"slug": "riberry", "common_name": "Riberry"}],
            )

        self.assertEqual(
            scores["riberry"]["days_in_stock"],
            published["species"]["riberry"]["days_in_stock_somewhere"],
        )
        self.assertEqual(
            scores["riberry"]["days_observed"],
            published["species"]["riberry"]["days_tracked"],
        )

    def test_they_agree_when_the_species_is_delisted_for_part_of_the_window(self):
        """The case that caught the first version of this fix.

        Riberry was listed on 186 of 189 measured days. Dividing by days-LISTED
        looks more careful and produced 186 here against 189 in the CC BY file:
        two published numbers for one fact, which is the defect DAL-293 exists
        to remove. A day on which nobody listed it is a day nobody could buy it.
        """
        shops = NURSERIES[:2]
        listed = DAYS[:-3]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_history(root, shops[0], [
                {"title": "Riberry", "in_stock_days": DAYS[:17], "listed_days": listed},
                {"title": "Feijoa", "in_stock_days": DAYS},
            ])
            _write_history(root, shops[1], [{"title": "Feijoa", "in_stock_days": DAYS}])
            scores = bsp.compute_rarity_scores(root, _by_species("riberry", shops), LOOKUP)
            stock, days, reporting, _listed = bsr.load_stock_history(root, LOOKUP)
            published = bsr.compute(
                stock, days, reporting, [{"slug": "riberry", "common_name": "Riberry"}],
            )

        got = scores["riberry"]
        self.assertEqual(got["days_listed"], len(listed))
        self.assertEqual(got["days_observed"], N_DAYS)
        self.assertEqual(got["days_observed"], published["species"]["riberry"]["days_tracked"])
        self.assertEqual(
            got["days_in_stock"], published["species"]["riberry"]["days_in_stock_somewhere"],
        )


class LoadStockHistoryReturnsListedDays(unittest.TestCase):
    def test_listed_but_never_in_stock_is_distinguishable_from_untracked(self):
        """DEC-339: an empty result is at least three facts, so say which."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_history(root, NURSERIES[0], [
                {"title": "Breadfruit", "in_stock_days": []},
            ])
            stock, days, reporting, listed = bsr.load_stock_history(root, LOOKUP)

        self.assertEqual(stock.get("breadfruit", {}), {})
        self.assertEqual(len(listed["breadfruit"]), N_DAYS)
        self.assertNotIn("kakadu-plum", listed)


if __name__ == "__main__":
    unittest.main()
