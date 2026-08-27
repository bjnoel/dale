"""Dormant nurseries: backing off a scraper aimed at a closed store.

Heritage Fruit Trees shut online sales for 2026 on 2026-08-24 and now serves
HTTP 503 on every URL including its sitemap. bigcommerce_scraper.py has no
retry and no backoff, so it walked its whole known catalogue into that wall
nightly and would have kept doing so until the 2027 season.

These pin the two properties that make the backoff safe to leave running
unattended: it never triggers on an outage short enough to recover from, and it
un-triggers by itself the moment a probe succeeds.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib.scrape_health import (consecutive_failures, is_dormant,
                                    last_success_day, should_probe,
                                    untrusted_nurseries)
from stocklib.snapshots import is_stale, snapshot_age_days

MONDAY = "2026-08-31"
TUESDAY = "2026-09-01"


class DormancyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.health = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, day, ok, nursery="heritage-fruit-trees", products=0,
               in_stock=None, priced=None):
        rec = {"nursery": nursery, "ok": ok, "products": products,
               "ts": f"{day}T00:30:00"}
        if in_stock is not None:
            rec["in_stock"] = in_stock
        if priced is not None:
            rec["priced"] = priced
        with open(self.health / f"{day}.jsonl", "a") as fh:
            fh.write(json.dumps(rec) + "\n")

    def shut_but_answering(self, *days):
        """The 2026-08-26 shape: HTTP 200, whole catalogue, nothing to sell."""
        for d in days:
            self.record(d, True, products=378, in_stock=0, priced=1)

    def fail_run(self, *days):
        for d in days:
            self.record(d, False)

    def test_no_history_is_not_dormant(self):
        self.assertFalse(is_dormant("heritage-fruit-trees", MONDAY, self.health))
        self.assertTrue(should_probe("heritage-fruit-trees", MONDAY, self.health))

    def test_the_real_three_day_blip_stays_awake(self):
        """08-12 to 08-14 2026 was three straight 503s and recovered on the
        15th. A threshold that would have slept through that recovery is set
        too low, so this is the case the constant is chosen against."""
        self.fail_run("2026-08-12", "2026-08-13", "2026-08-14")
        self.assertEqual(consecutive_failures("heritage-fruit-trees", "2026-08-14", self.health), 3)
        self.assertFalse(is_dormant("heritage-fruit-trees", "2026-08-14", self.health))
        self.assertTrue(should_probe("heritage-fruit-trees", "2026-08-14", self.health))

    def test_five_failures_go_dormant(self):
        self.fail_run("2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28")
        self.assertTrue(is_dormant("heritage-fruit-trees", "2026-08-28", self.health))

    def test_dormant_probes_only_on_monday(self):
        self.fail_run("2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28")
        self.assertTrue(should_probe("heritage-fruit-trees", MONDAY, self.health))
        self.assertFalse(should_probe("heritage-fruit-trees", TUESDAY, self.health))

    def test_streak_survives_the_skipped_days_it_causes(self):
        """The trap in the design: once dormant, six days a week write no
        record at all. If those counted as successes the streak would decay and
        the nursery would bounce back to nightly scraping on its own."""
        self.fail_run("2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28")
        # 08-29 and 08-30 are skipped: no records written.
        self.assertEqual(consecutive_failures("heritage-fruit-trees", "2026-08-30", self.health), 5)
        self.assertTrue(is_dormant("heritage-fruit-trees", "2026-08-30", self.health))

    def test_one_good_probe_resumes_nightly_scraping(self):
        self.fail_run("2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28")
        self.record(MONDAY, True, products=300)
        self.assertEqual(consecutive_failures("heritage-fruit-trees", MONDAY, self.health), 0)
        self.assertFalse(is_dormant("heritage-fruit-trees", MONDAY, self.health))
        self.assertTrue(should_probe("heritage-fruit-trees", TUESDAY, self.health))

    def test_dormancy_is_per_nursery(self):
        self.fail_run("2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28")
        for d in ("2026-08-24", "2026-08-28"):
            self.record(d, True, nursery="ladybird", products=7000)
        self.assertTrue(is_dormant("heritage-fruit-trees", "2026-08-28", self.health))
        self.assertFalse(is_dormant("ladybird", "2026-08-28", self.health))

    def test_last_success_day(self):
        self.record("2026-08-23", True, products=128)
        self.fail_run("2026-08-24", "2026-08-25")
        self.assertEqual(
            last_success_day("heritage-fruit-trees", "2026-08-25", self.health), "2026-08-23")
        self.assertIsNone(last_success_day("ladybird", "2026-08-25", self.health))


class ShutButAnsweringTest(unittest.TestCase):
    """A closed store does not have to 503 at you.

    On 2026-08-26 Heritage started answering HTTP 200 again with all 378
    products present, every one OutOfStock and unpriced. That is `ok=true`, so
    the failure streak reset and nightly scraping resumed against a store that
    had not reopened -- and the runs got LONGER (432s, then 1235s and 1245s),
    because a 503 fails fast and a 200 does not. Verified against the live site
    before these were written: it really does serve 200 with
    schema.org/OutOfStock and no price.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.health = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    record = DormancyTest.record
    fail_run = DormancyTest.fail_run
    shut_but_answering = DormancyTest.shut_but_answering

    def test_the_real_event_would_have_scraped_forever(self):
        """The exact production sequence. Before this rule the streak read 0 on
        08-27 and Heritage was scraped nightly until the 2027 season."""
        self.record("2026-08-23", True, products=128, in_stock=128, priced=128)
        self.fail_run("2026-08-24", "2026-08-25")
        self.shut_but_answering("2026-08-26", "2026-08-27")
        self.assertEqual(
            consecutive_failures("heritage-fruit-trees", "2026-08-27", self.health), 4)
        # Four, not five: one more unproductive night is required. The threshold
        # is not bent to make the case in front of us fire today.
        self.assertFalse(is_dormant("heritage-fruit-trees", "2026-08-27", self.health))
        self.shut_but_answering("2026-08-28")
        self.assertTrue(is_dormant("heritage-fruit-trees", "2026-08-28", self.health))

    def test_last_good_day_is_not_last_night(self):
        """The skip message must not claim a good scrape it is skipping over."""
        self.record("2026-08-23", True, products=128, in_stock=128, priced=128)
        self.fail_run("2026-08-24", "2026-08-25")
        self.shut_but_answering("2026-08-26", "2026-08-27")
        self.assertEqual(
            last_success_day("heritage-fruit-trees", "2026-08-27", self.health),
            "2026-08-23")

    def test_sold_out_but_still_trading_stays_nightly(self):
        """The load-bearing distinction. A nursery can sell out completely and
        still be open, and it keeps its prices on the page. Backing off there
        would cost us the restock alert that is the reason to scrape daily."""
        for d in ("2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"):
            self.record(d, True, products=378, in_stock=0, priced=370)
        self.assertEqual(
            consecutive_failures("heritage-fruit-trees", "2026-08-28", self.health), 0)
        self.assertFalse(is_dormant("heritage-fruit-trees", "2026-08-28", self.health))

    def test_reopening_resumes_nightly_by_itself(self):
        self.fail_run("2026-08-24", "2026-08-25")
        self.shut_but_answering("2026-08-26", "2026-08-27", "2026-08-28")
        self.assertTrue(is_dormant("heritage-fruit-trees", "2026-08-28", self.health))
        self.record(MONDAY, True, products=380, in_stock=210, priced=375)
        self.assertEqual(
            consecutive_failures("heritage-fruit-trees", MONDAY, self.health), 0)
        self.assertTrue(should_probe("heritage-fruit-trees", TUESDAY, self.health))

    def test_records_without_a_priced_field_are_never_judged(self):
        """`priced` postdates most of the health log. Absent evidence must not
        retroactively rewrite six months of history into dormancy."""
        for d in ("2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28"):
            self.record(d, True, products=378, in_stock=0)
        self.assertEqual(
            consecutive_failures("heritage-fruit-trees", "2026-08-28", self.health), 0)

    def test_an_unproductive_run_is_still_trusted_data(self):
        """Heritage really is out of stock, so its zero is true and must keep
        reaching the site. Dormancy answers 'scrape it tonight?', not
        'believe it?'. Conflating them would delist a real catalogue."""
        self.shut_but_answering("2026-08-27")
        self.assertNotIn("heritage-fruit-trees",
                         untrusted_nurseries("2026-08-27", self.health))


class SnapshotStalenessTest(unittest.TestCase):
    """What the nursery page reads. Deliberately a different question from
    dormancy above: the page cares how old the data it is rendering is, not
    how many runs failed to produce newer data."""

    def test_fresh_snapshot_is_not_stale(self):
        self.assertEqual(snapshot_age_days("2026-08-23T00:26:29", "2026-08-24"), 1)
        self.assertFalse(is_stale("2026-08-23T00:26:29", "2026-08-24"))

    def test_week_old_snapshot_is_stale(self):
        self.assertTrue(is_stale("2026-08-23T00:26:29", "2026-08-30"))

    def test_unreadable_timestamp_reads_as_fresh(self):
        """A page that hid its stock because it could not parse a timestamp
        would be worse than one that showed it."""
        for bad in (None, "", "not-a-date"):
            self.assertIsNone(snapshot_age_days(bad, "2026-08-30"))
            self.assertFalse(is_stale(bad, "2026-08-30"))


if __name__ == "__main__":
    unittest.main()
