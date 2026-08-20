"""Guards for the "Search rank (ASO)" section of the TreeSmith weekly digest.

Two failure modes, both of which this business has already shipped once.

1. A metrics dict without the "rank" key must still render. The revenue tests
   hand-build one, and a direct `metrics["rank"]` would KeyError all of them --
   which is how a new section takes the whole digest down.

2. A stopped capture must read as "no capture", never as "no movement". That is
   the digest-liveness failure: a renamed app event reported 0 as fact, and the
   number was believed because nothing said the input had gone quiet. A rank
   section is exactly where a silent zero would reverse a conclusion, because
   "nothing moved" is what a successful week looks like too.
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "tools" / "autonomous" / "treesmith_analytics.py"
)
spec = importlib.util.spec_from_file_location("treesmith_analytics", MODULE_PATH)
ta = importlib.util.module_from_spec(spec)
sys.modules["treesmith_analytics"] = ta
spec.loader.exec_module(ta)

RH_PATH = MODULE_PATH.parent / "rank_history.py"
rh_spec = importlib.util.spec_from_file_location("rank_history", RH_PATH)
rh = importlib.util.module_from_spec(rh_spec)
sys.modules["rank_history"] = rh
rh_spec.loader.exec_module(rh)


def base_metrics(**overrides):
    """A metrics dict with every key render() indexes directly, and no more."""
    metrics = {
        "installs": {"ok": True,
                     "data": {"this_week": 0, "prev_week": 0, "delta": None}},
        "active": {"ok": True, "data": {"wau": 0, "mau": 0}},
        "identity": {"ok": True,
                     "data": {"ids": 0, "persons": 0, "phantom": 0,
                              "inflation_pct": 0}},
        "plants": {"ok": True,
                   "data": {"owners": 0, "plants": 0, "observed_adds": 0,
                            "unobserved": 0, "unobserved_pct": None}},
        "activation": {"ok": True,
                       "data": {"installs": 0, "activated": 0, "rate": None}},
        "onboarding": {"ok": True,
                       "data": {"started": 0, "completed": 0, "rate": None}},
        "funnel": {"ok": True, "data": {"steps": [], "biggest_drop": None}},
        "paywall": {"ok": True, "data": {"shown": 0, "purchased": 0, "dismissed": 0}},
        "purchases": {"ok": True, "data": {"buckets": [], "production": []}},
        "revenuecat": {"ok": False, "error": "not under test"},
        "reconciliation": {"ok": True,
                           "data": {"via_paywall": 0, "via_purchase": 0,
                                    "agrees": True}},
        "retention": {"ok": True, "data": {"cohort": 0, "returned": 0, "rate": None}},
        "top_screens": {"ok": True, "data": {"rows": []}},
        "backup": {"ok": True, "data": {"completed": 0, "failed": []}},
    }
    metrics.update(overrides)
    return metrics


def store_block(age_days=1, **overrides):
    block = {
        "prev": "2026-08-13T02:01:00Z",
        "curr": "2026-08-20T02:01:00Z",
        "age_days": age_days,
        "moved": [],
        "entered": [],
        "dropped": [],
        "flat_n": 30,
        "still_absent_n": 6,
        "unmeasured_n": 0,
    }
    block.update(overrides)
    return block


def item(line, **overrides):
    it = {"country": "AU", "term": "graft tracker", "prev_rank": 1,
          "curr_rank": 11, "delta": 10, "line": line}
    it.update(overrides)
    return it


class TestSectionIsOptional(unittest.TestCase):
    def test_a_metrics_dict_without_the_key_still_renders(self):
        # The decisive one: metrics.get, not metrics[...].
        text, _ = ta.render(base_metrics())
        self.assertIn("TreeSmith Weekly", text)
        self.assertNotIn("Search rank", text)

    def test_a_failed_metric_renders_as_an_error_not_as_silence(self):
        text, _ = ta.render(base_metrics(
            rank={"ok": False, "error": "no rank series at /opt/data/x.csv"}))
        self.assertIn("Search rank", text)
        self.assertIn("ERROR", text)
        self.assertIn("no rank series", text)


class TestStaleness(unittest.TestCase):
    def test_a_stopped_capture_says_no_capture(self):
        text, _ = ta.render(base_metrics(rank={"ok": True, "data": {
            "path": "/x.csv", "stale": True, "age_days": 41,
            "stores": {"play": store_block(age_days=41)}}}))
        self.assertIn("NO CAPTURE", text)
        self.assertIn("41 days ago", text)

    def test_a_stopped_capture_does_not_say_nothing_moved(self):
        # The whole point. "no movement" and "no measurement" are different
        # facts and a quiet week looks identical to a dead cron job.
        text, _ = ta.render(base_metrics(rank={"ok": True, "data": {
            "path": "/x.csv", "stale": True, "age_days": 41,
            "stores": {"play": store_block(age_days=41)}}}))
        rank_text = text[text.index("Search rank"):text.index("Activation")]
        self.assertIn("NO CAPTURE", rank_text)
        self.assertIn("older news", rank_text)

    def test_a_fresh_capture_with_nothing_moving_says_so_plainly(self):
        text, _ = ta.render(base_metrics(rank={"ok": True, "data": {
            "path": "/x.csv", "stale": False, "age_days": 1,
            "stores": {"play": store_block()}}}))
        self.assertNotIn("NO CAPTURE", text)
        self.assertIn("no term moved beyond the noise band", text)

    def test_one_live_store_does_not_mask_a_dead_one(self):
        # m_rank aggregates the WORST store, so this exercises the flag it sets.
        data = {"path": "/x.csv", "stale": True, "age_days": 41, "stores": {
            "appstore": store_block(age_days=41),
            "play": store_block(age_days=1)}}
        text, _ = ta.render(base_metrics(rank={"ok": True, "data": data}))
        self.assertIn("NO CAPTURE", text)
        self.assertIn("41 days old", text)  # marked on the dead store's own line


class TestMovementRendering(unittest.TestCase):
    def _text(self, **block):
        text, html = ta.render(base_metrics(rank={"ok": True, "data": {
            "path": "/x.csv", "stale": False, "age_days": 1,
            "stores": {"appstore": store_block(**block)}}}))
        return text[text.index("Search rank"):text.index("Activation")], html

    def test_movement_lines_are_carried_verbatim(self):
        text, _ = self._text(moved=[item(
            "AU graft tracker: 1 -> 11 (down 10)  vacated, nobody took the slot")])
        self.assertIn("vacated, nobody took the slot", text)

    def test_long_buckets_are_truncated_and_say_how_many_were_dropped(self):
        # A silent top-5 reads as "that was everything".
        many = [item(f"AU term {i}", term=f"term {i}") for i in range(9)]
        text, _ = self._text(moved=many)
        self.assertIn("...and 4 more moved", text)

    def test_unmeasured_terms_are_flagged_not_folded_into_the_counts(self):
        # DEC-249: these did not move, they were never read.
        text, _ = self._text(unmeasured_n=3)
        self.assertIn("3 NOT MEASURED", text)

    def test_a_store_with_one_capture_is_not_reported_as_flat(self):
        text, _ = self._text(prev=None)
        self.assertIn("nothing to compare yet", text)
        self.assertNotIn("no term moved", text)

    def test_competitor_names_are_escaped_in_the_html(self):
        # "Case Tracker for USCIS & NVC" is a real neighbour of ours on the US
        # store, and these are the only strings in the digest we did not write.
        _, html = self._text(dropped=[item(
            "US graft tracker: 1 -> absent  displaced by Case Tracker for USCIS & NVC",
            curr_rank=None)])
        self.assertIn("USCIS &amp; NVC", html)
        self.assertNotIn("USCIS & NVC", html)


class TestMetricAgainstTheRealSeries(unittest.TestCase):
    def test_a_missing_series_is_an_error_not_an_empty_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, rh.series_path = rh.series_path, lambda: os.path.join(tmp, "gone.csv")
            sys.modules["rank_history"] = rh
            try:
                result = ta.run_metric(ta.m_rank)
            finally:
                rh.series_path = original
        self.assertFalse(result["ok"])
        self.assertIn("no rank series", result["error"])

    def test_the_backfilled_series_produces_a_play_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "series.csv")
            rh.backfill(path, write=True)
            original, rh.series_path = rh.series_path, lambda: path
            sys.modules["rank_history"] = rh
            try:
                result = ta.run_metric(ta.m_rank)
            finally:
                rh.series_path = original
        self.assertTrue(result["ok"], result.get("error"))
        play = result["data"]["stores"]["play"]
        self.assertEqual(play["prev"], "2026-08-13T01:56:00Z")
        self.assertEqual(play["curr"], "2026-08-13T02:55:00Z")
        # Apple has one capture, so it must not be compared against Play's.
        self.assertIsNone(result["data"]["stores"]["appstore"]["prev"])
        # And every listed movement carries its rendered line.
        for bucket in ("moved", "entered", "dropped"):
            for it in play[bucket]:
                self.assertIn("line", it)


if __name__ == "__main__":
    unittest.main()
