"""
A closed nursery's stock is withdrawn at the snapshot layer, for every builder.

On 2026-09-23, three days into Aus Nurseries' holiday closure (every URL a
Shopify password page, HTTP 401), 490 rows on 173 variety, species, buy and
compare pages still said "In stock" for it. DEC-350 had fixed search and the
nursery page only; the other builders read the frozen latest.json as live.

These tests pin: the snapshot walk withdraws a dormant nursery's stock; the
closure note shortens the threshold from 3 days to 1; the input is not
mutated; and the page lifecycle holds a page carried only by a dormant
nursery instead of tombstoning it (a holiday is not a delisting).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "scrapers"))

from stocklib import registry  # noqa: E402
from stocklib.page_ledger import LIVE, TOMBSTONE, FAMILY_SPECIES_STATE, PageLedger, decide_night  # noqa: E402
from stocklib.snapshots import (  # noqa: E402
    dormant_nurseries, iter_nursery_snapshots, load_current_snapshot, withdraw_if_dormant,
)

NOTED = "ausnurseries"       # carries a dormant_note in the registry
UNNOTED = "fruit-tree-cottage"  # does not


def snapshot(key, scraped_at):
    return {
        "nursery": key, "nursery_name": key, "scraped_at": scraped_at,
        "product_count": 2, "in_stock_count": 1, "out_of_stock_count": 1,
        "products": [
            {"title": "Apple Jonathon", "url": f"https://{key}/apple",
             "any_available": True, "preorder": True, "total_stock": 4,
             "min_price": 40.0,
             "variants": [{"title": "Default", "price": "40.00", "available": True,
                           "stock_count": 4}]},
            {"title": "Fig Brown Turkey", "url": f"https://{key}/fig",
             "any_available": False, "min_price": 30.0,
             "variants": [{"title": "Default", "price": "30.00", "available": False}]},
        ],
    }


def write(data_dir, key, snap):
    d = Path(data_dir) / key
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest.json").write_text(json.dumps(snap))


class RegistryCarriesTheNote(unittest.TestCase):
    def test_noted_nursery_has_note_and_unnoted_does_not(self):
        self.assertIn("20 October 2026", registry.dormant_note(NOTED))
        self.assertEqual(registry.dormant_note(UNNOTED), "")
        self.assertEqual(registry.dormant_note("no-such-nursery"), "")


class SnapshotWalkWithdrawsDormantStock(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def walk(self, today):
        return dict(iter_nursery_snapshots(self.dir, today))

    def test_noted_nursery_is_withdrawn_one_day_after_its_last_scrape(self):
        write(self.dir, NOTED, snapshot(NOTED, "2026-09-19T00:02:40"))
        snap = self.walk("2026-09-20")[NOTED]
        self.assertTrue(snap["dormant"])
        self.assertEqual(snap["in_stock_count"], 0)
        apple = snap["products"][0]
        self.assertFalse(apple["any_available"])
        self.assertFalse(apple["variants"][0]["available"])
        for claim in ("preorder", "total_stock"):
            self.assertNotIn(claim, apple)
        self.assertNotIn("stock_count", apple["variants"][0])
        # The rows stay: they are the record, and what keeps pages alive.
        self.assertEqual(len(snap["products"]), 2)
        self.assertEqual(apple["min_price"], 40.0)

    def test_same_day_scrape_is_never_withdrawn_even_with_a_note(self):
        write(self.dir, NOTED, snapshot(NOTED, "2026-09-20T00:02:40"))
        snap = self.walk("2026-09-20")[NOTED]
        self.assertNotIn("dormant", snap)
        self.assertTrue(snap["products"][0]["any_available"])

    def test_unnoted_nursery_waits_three_days(self):
        write(self.dir, UNNOTED, snapshot(UNNOTED, "2026-09-19T00:02:40"))
        for today, dormant in (("2026-09-20", False), ("2026-09-21", False),
                               ("2026-09-22", True)):
            with self.subTest(today=today):
                snap = self.walk(today)[UNNOTED]
                self.assertEqual(snap.get("dormant", False), dormant)
                self.assertEqual(snap["products"][0]["any_available"], not dormant)

    def test_opt_out_returns_the_record_as_recorded(self):
        write(self.dir, NOTED, snapshot(NOTED, "2026-09-19T00:02:40"))
        snap = dict(iter_nursery_snapshots(self.dir, "2026-09-23",
                                           withdraw_dormant=False))[NOTED]
        self.assertTrue(snap["products"][0]["any_available"])

    def test_withdrawal_does_not_mutate_its_input(self):
        snap = snapshot(NOTED, "2026-09-19T00:02:40")
        before = copy.deepcopy(snap)
        out = withdraw_if_dormant(NOTED, snap, "2026-09-23")
        self.assertEqual(snap, before)
        self.assertIsNot(out, snap)

    def test_single_nursery_loader_applies_the_same_rule(self):
        write(self.dir, NOTED, snapshot(NOTED, "2026-09-19T00:02:40"))
        snap = load_current_snapshot(self.dir / NOTED, "2026-09-23")
        self.assertFalse(snap["products"][0]["any_available"])
        self.assertIsNone(load_current_snapshot(self.dir / "missing", "2026-09-23"))

    def test_dormant_nurseries_lists_only_the_closed_ones(self):
        write(self.dir, NOTED, snapshot(NOTED, "2026-09-19T00:02:40"))
        write(self.dir, "daleys", snapshot("daleys", "2026-09-23T00:05:37"))
        self.assertEqual(dormant_nurseries(self.dir, "2026-09-23"), {NOTED})


class LifecycleHoldsPagesOfDormantNurseries(unittest.TestCase):
    """buy-rambutan-trees-{nsw,qld,vic} were carried only by Aus Nurseries on
    2026-09-23. Withdrawn stock drops them from tonight's generated set, and
    without the dormant set in `untrusted` they would tombstone two nights later
    and stay tombstoned for the rest of a one-month holiday."""

    PAD = [f"pad-{i:03d}" for i in range(30)]
    SLUG = "buy-rambutan-trees-queensland"

    def setUp(self):
        self.led = PageLedger(FAMILY_SPECIES_STATE)
        rows = [{"nursery_key": NOTED, "nursery_name": "Aus Nurseries",
                 "title": "Rambutan", "price": 60.0, "available": True,
                 "url": "https://ausnurseries/rambutan"}]
        for slug in self.PAD + [self.SLUG]:
            e = self.led.seed(slug, today="2026-09-19", first_seen="2026-06-01",
                              last_seen="2026-09-19", live_days=100,
                              in_stock_days=100, last_in_stock="2026-09-19",
                              state=LIVE, rows=rows)
            e["seeded"] = True

    def nights(self, untrusted):
        plan = None
        for day in ("2026-09-20", "2026-09-21", "2026-09-22"):
            plan = decide_night(self.led, self.PAD, today=day,
                                untrusted=untrusted, allow_delete=True)
        return plan

    def test_without_the_dormant_set_the_page_tombstones(self):
        self.nights(untrusted=set())
        self.assertEqual(self.led.pages[self.SLUG]["state"], TOMBSTONE)

    def test_with_the_dormant_set_the_page_is_held_live(self):
        tmp = Path(tempfile.mkdtemp())
        write(tmp, NOTED, snapshot(NOTED, "2026-09-19T00:02:40"))
        plan = self.nights(untrusted=dormant_nurseries(tmp, "2026-09-22"))
        self.assertEqual(self.led.pages[self.SLUG]["state"], LIVE)
        self.assertEqual(plan.held[self.SLUG], "untrusted nurseries")


if __name__ == "__main__":
    unittest.main()
