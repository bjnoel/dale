"""Guards on the daily digest's "new queries" and "position movers" blocks.

DAL-268 / DEC-327. DAL-261 fixed the truncation that made these blocks read 200
of 1,703 GSC rows. Reading the true set then showed the blocks were still wrong,
for a second and separate reason: the mover rule was "moved 5+ spots" with no
impression floor at all, and the list was sorted by size of move.

Backtested over 8 consecutive 7-day treestock windows (2026-06-30..2026-08-24),
scoring every candidate rule on whether the move was still there a week later:

  * old rule: ~316 rows/week, 45% of them queries that vanished entirely the
    next week, only 31% holding the new position;
  * 98% of the rows it actually PRINTED had <= 2 impressions in both weeks,
    because sorting by size of move selects the extreme tail, and at 1-2
    impressions the median week-over-week swing is 4.0 spots with 45% of all
    queries clearing 5. The threshold sat below the noise floor of the
    population that dominated the list.

So the dial that was broken was the impression floor, which did not exist, not
the spot count. These tests pin both, and pin the sort order, because sorting by
change is what converted a merely noisy rule into a maximally noisy one.
"""

import unittest
from pathlib import Path
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

AUTONOMOUS = Path(__file__).resolve().parent.parent / "tools" / "autonomous"


def load(name, filename):
    loader = SourceFileLoader(name, str(AUTONOMOUS / filename))
    spec = spec_from_loader(name, loader)
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


SITE = "sc-domain:example.test"


class _FakeService:
    """Serves canned query rows for period A and period B by date range."""

    def __init__(self, a_rows, b_rows):
        self._periods = [a_rows, b_rows]  # collect_gsc_stats asks for A, then B
        self._body = None

    # sites().list().execute()
    def sites(self):
        return self

    def list(self):
        return self

    # searchanalytics().query(...).execute()
    def searchanalytics(self):
        return self

    def query(self, siteUrl, body):
        self._body = body
        return self

    def execute(self):
        if self._body is None:
            return {"siteEntry": [{"siteUrl": SITE, "permissionLevel": "siteFullUser"}]}
        body, self._body = self._body, None
        if body["dimensions"] == ["date"]:
            return {"rows": [{"keys": ["2026-08-20"], "clicks": 10,
                              "impressions": 100, "position": 12.0}]}
        assert self._periods, "more query-dimension calls than periods supplied"
        return {"rows": self._periods.pop(0)}


def row(query, impressions, position, clicks=0):
    return {"keys": [query], "clicks": clicks, "impressions": impressions,
            "position": position}


class QueryMovementThresholdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tr = load("traffic_report", "traffic_report.py")

    def collect(self, a_rows, b_rows):
        svc = _FakeService(a_rows, b_rows)
        self.tr.get_gsc_service = lambda: svc
        return self.tr.collect_gsc_stats([SITE])[0]

    # --- the rule must REJECT what it used to print -------------------------

    def test_thin_query_swinging_wildly_is_not_a_mover(self):
        """The exact shape of 98% of the rows the old block printed.

        One impression each week and a 77-position "improvement". Under the old
        rule this was the headline row; it is a single search result page whose
        averaged position means almost nothing.
        """
        stat = self.collect([row("davidson plum tree", 1, 3.0)],
                            [row("davidson plum tree", 1, 80.0)])
        self.assertEqual(stat["position_movers"], [])

    def test_the_floor_is_what_rejects_it_not_the_spot_count(self):
        """Same query, same 77-spot move, enough impressions: now it reports.

        This is the paired control. If this test passed only because the spot
        threshold went up, the previous test would be proving the wrong thing.
        """
        n = self.tr.MOVER_MIN_IMPRESSIONS
        stat = self.collect([row("davidson plum tree", n, 3.0)],
                            [row("davidson plum tree", n, 80.0)])
        self.assertEqual([m["query"] for m in stat["position_movers"]],
                         ["davidson plum tree"])

    def test_impression_floor_applies_to_both_weeks_not_just_the_new_one(self):
        """A query that was thin LAST week is just as unmeasured as one thin now."""
        n = self.tr.MOVER_MIN_IMPRESSIONS
        stat = self.collect([row("guava tree perth", n * 10, 4.0)],
                            [row("guava tree perth", 1, 60.0)])
        self.assertEqual(stat["position_movers"], [])

    def test_move_smaller_than_the_measured_drift_is_not_a_mover(self):
        n = self.tr.MOVER_MIN_IMPRESSIONS
        below = self.tr.MOVER_MIN_SPOTS - 1
        stat = self.collect([row("olive trees for sale", n * 20, 10.0)],
                            [row("olive trees for sale", n * 20, 10.0 + below)])
        self.assertEqual(stat["position_movers"], [])

    # --- the rule must still CATCH a real move ------------------------------

    def test_a_real_drop_on_a_page_with_traffic_still_reports(self):
        """Direction matters: a fall must surface, not just a rise."""
        stat = self.collect([row("olive trees perth", 400, 26.0, clicks=22)],
                            [row("olive trees perth", 380, 12.0, clicks=43)])
        self.assertEqual(len(stat["position_movers"]), 1)
        self.assertLess(stat["position_movers"][0]["change"], 0)

    # --- ordering ------------------------------------------------------------

    def test_movers_are_ranked_by_impressions_not_by_size_of_move(self):
        """Sorting by change is what made a noisy rule maximally noisy.

        Both rows below clear the thresholds, so this is purely about which one
        Benedict reads first. The 500-impression query matters more than the
        barely-qualifying one with a flashier number beside it.
        """
        n = self.tr.MOVER_MIN_IMPRESSIONS
        stat = self.collect(
            [row("big term", 500, 8.0), row("tiny term", n, 2.0)],
            [row("big term", 500, 20.0), row("tiny term", n, 70.0)],
        )
        self.assertEqual([m["query"] for m in stat["position_movers"]],
                         ["big term", "tiny term"])

    # --- new queries ---------------------------------------------------------

    def test_new_query_below_the_impression_floor_is_not_reported(self):
        """At >= 3 impressions, 52% of "new" queries were gone again a week
        later and 96% never earned a click. The floor is 5."""
        stat = self.collect([row("brand new term", self.tr.NEW_QUERY_MIN_IMPRESSIONS - 1, 40.0)],
                            [row("unrelated", 50, 10.0)])
        self.assertEqual(stat["new_queries"], [])

    def test_new_query_at_the_floor_is_reported(self):
        stat = self.collect([row("brand new term", self.tr.NEW_QUERY_MIN_IMPRESSIONS, 40.0)],
                            [row("unrelated", 50, 10.0)])
        self.assertEqual([q["query"] for q in stat["new_queries"]], ["brand new term"])

    # --- the constants themselves -------------------------------------------

    def test_thresholds_sit_clear_of_the_measured_noise_floor(self):
        """DEC-323: a threshold is a guess until it is replayed over history.

        Measured p90 week-over-week drift in the 10-29 impression band is 8.7
        spots; in the 3-9 band it is 12.9. A spot threshold at or below 8 is
        inside the noise, and a round 5 with no floor is what we had.
        """
        self.assertGreaterEqual(self.tr.MOVER_MIN_SPOTS, 9)
        self.assertGreaterEqual(self.tr.MOVER_MIN_IMPRESSIONS, 5)
        self.assertGreaterEqual(self.tr.NEW_QUERY_MIN_IMPRESSIONS, 5)


if __name__ == "__main__":
    unittest.main()
