"""
Tests for the ticket outcome loop: trailer parsing, verdict classification,
due-date selection, and the store round-trip.

The trailer strings here are copied verbatim from real DAL tickets on
2026-08-06, including the prose ones that name no readable metric. That mix is
the point: the loop has to grade `treesmith_downloads` and decline to grade
`protects every other metric`, and never confuse the two.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"
sys.path.insert(0, str(AUTONOMOUS))

import ticket_outcomes as to


class TestParseTrailer(unittest.TestCase):
    def test_real_ticket_trailers(self):
        cases = [
            ("...\n\n`L0 · treesmith_downloads`", "L0", "treesmith_downloads"),
            ("...\n\n`L2 · treestock_organic_visitors`", "L2", "treestock_organic_visitors"),
            ("...\n\n`L3 · revenue_monthly`", "L3", "revenue_monthly"),
            ("...\n\n`L1 · treestock_subscriber_engagement`", "L1",
             "treestock_subscriber_engagement"),
            ("...\n\n`L0 · unblocks DEC-248 step 3`", "L0", "unblocks DEC-248 step 3"),
            ("...\n\n`L0 · protects every other metric`", "L0",
             "protects every other metric"),
        ]
        for body, level, metric in cases:
            with self.subTest(body=body):
                self.assertEqual(to.parse_trailer(body), (level, metric))

    def test_no_trailer(self):
        self.assertEqual(to.parse_trailer(""), (None, None))
        self.assertEqual(to.parse_trailer(None), (None, None))
        self.assertEqual(to.parse_trailer("A ticket with no trailer at all"),
                         (None, None))

    def test_takes_the_last_trailer(self):
        """A description that quotes the format in passing must not shadow the
        real trailer at the bottom."""
        body = ("Use the format `L2 · treesmith_downloads` when writing.\n\n"
                "**Why now:** ...\n\n`L1 · treestock_subscribers`")
        self.assertEqual(to.parse_trailer(body), ("L1", "treestock_subscribers"))

    def test_tolerates_alternative_separators(self):
        for sep in ("·", "-", "|", ":"):
            with self.subTest(sep=sep):
                level, metric = to.parse_trailer(f"x\n\n`L2 {sep} revenue_monthly`")
                self.assertEqual((level, metric), ("L2", "revenue_monthly"))

    def test_whitespace_is_normalised(self):
        level, metric = to.parse_trailer("x\n\n`L2 ·   revenue_monthly  `")
        self.assertEqual(metric, "revenue_monthly")


class TestNormaliseMetric(unittest.TestCase):
    def test_known_metrics_resolve(self):
        for name in to.METRIC_READERS:
            with self.subTest(name=name):
                self.assertEqual(to.normalise_metric(name), name)

    def test_prose_trailers_are_not_metrics(self):
        """Unmeasurable trailers must return None, not be coerced to a reader.
        These are all real: forcing them into a number would invent data."""
        for prose in ("unblocks DEC-248 step 3", "protects every other metric",
                      "reporting integrity", "nursery relationships"):
            with self.subTest(prose=prose):
                self.assertIsNone(to.normalise_metric(prose))

    def test_case_and_spacing_insensitive(self):
        self.assertEqual(to.normalise_metric("Treesmith Downloads"),
                         "treesmith_downloads")

    def test_empty(self):
        self.assertIsNone(to.normalise_metric(""))
        self.assertIsNone(to.normalise_metric(None))


class TestClassify(unittest.TestCase):
    def test_moved_up(self):
        self.assertEqual(to.classify(49, 61), ("moved", 24.5))

    def test_declined(self):
        call, pct = to.classify(100, 80)
        self.assertEqual(call, "declined")
        self.assertEqual(pct, -20.0)

    def test_inside_the_flat_band_is_flat(self):
        """Treestock swings this much on season alone, so it is not evidence."""
        self.assertEqual(to.classify(100, 103)[0], "flat")
        self.assertEqual(to.classify(100, 97)[0], "flat")

    def test_small_numbers_get_no_percentage(self):
        """1 -> 2 subscribers is +100% and means nothing."""
        call, pct = to.classify(1, 2)
        self.assertEqual(call, "too-small")
        self.assertIsNone(pct)

    def test_zero_baseline_with_real_movement(self):
        call, _ = to.classify(0, 50)
        self.assertEqual(call, "moved")

    def test_unmeasured_when_a_side_is_missing(self):
        """A failed read must never be graded as a decline to zero."""
        self.assertEqual(to.classify(None, 40), ("unmeasured", None))
        self.assertEqual(to.classify(40, None), ("unmeasured", None))

    def test_every_call_has_a_label(self):
        for call in ("moved", "declined", "flat", "too-small", "unmeasured"):
            self.assertIn(call, to.CALL_LABEL)


class TestDueRecords(unittest.TestCase):
    def _store(self, records):
        return {"version": 1, "records": records}

    def test_due_when_date_has_passed(self):
        store = self._store([
            {"ticket": "DAL-1", "verdict_due": "2026-08-01",
             "baseline": {"value": 10}, "verdict": None},
        ])
        due = to.due_records(store, date(2026, 8, 6))
        self.assertEqual([r["ticket"] for r in due], ["DAL-1"])

    def test_not_due_yet(self):
        store = self._store([
            {"ticket": "DAL-2", "verdict_due": "2026-09-01",
             "baseline": {"value": 10}, "verdict": None},
        ])
        self.assertEqual(to.due_records(store, date(2026, 8, 6)), [])

    def test_already_settled_is_skipped(self):
        store = self._store([
            {"ticket": "DAL-3", "verdict_due": "2026-08-01",
             "baseline": {"value": 10}, "verdict": {"call": "moved"}},
        ])
        self.assertEqual(to.due_records(store, date(2026, 8, 6)), [])

    def test_no_baseline_is_never_due(self):
        """Without a baseline there is nothing to compare against, so grading it
        would be inventing a before-value."""
        store = self._store([
            {"ticket": "DAL-4", "verdict_due": "2026-08-01",
             "baseline": None, "verdict": None},
        ])
        self.assertEqual(to.due_records(store, date(2026, 8, 6)), [])

    def test_malformed_due_date_is_skipped_not_crashed(self):
        store = self._store([
            {"ticket": "DAL-5", "verdict_due": "not-a-date",
             "baseline": {"value": 10}, "verdict": None},
        ])
        self.assertEqual(to.due_records(store, date(2026, 8, 6)), [])


class TestStore(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "ticket-outcomes.json")
            store = {"version": 1, "records": [{"ticket": "DAL-9"}]}
            to.save_store(store, path)
            self.assertEqual(to.load_store(path), store)

    def test_missing_file_gives_empty_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = to.load_store(str(Path(tmp) / "nope.json"))
            self.assertEqual(store["records"], [])

    def test_corrupt_file_gives_empty_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ticket-outcomes.json"
            path.write_text("{not json")
            self.assertEqual(to.load_store(str(path))["records"], [])

    def test_find_record(self):
        store = {"records": [{"ticket": "DAL-1"}, {"ticket": "DAL-2"}]}
        self.assertEqual(to.find_record(store, "DAL-2")["ticket"], "DAL-2")
        self.assertIsNone(to.find_record(store, "DAL-3"))


class TestSummaries(unittest.TestCase):
    STORE = {"records": [
        {"ticket": "DAL-1", "baseline": {"value": 1}, "verdict_due": "2026-09-01",
         "verdict": None},
        {"ticket": "DAL-2", "baseline": {"value": 1}, "verdict_due": "2026-08-20",
         "verdict": None},
        # Shipped naming a prose metric: counted as ungraded, not as awaiting.
        {"ticket": "DAL-3", "baseline": None, "verdict_due": "2026-08-20",
         "verdict": None},
        {"ticket": "DAL-4", "baseline": {"value": 1}, "verdict_due": "2026-08-01",
         "verdict": {"call": "moved", "settled_at": "2026-08-06T01:00:00+00:00"}},
    ]}

    def test_pending_summary(self):
        s = to.pending_summary(self.STORE)
        self.assertEqual(s["awaiting"], 2)
        self.assertEqual(s["ungraded"], 1)
        self.assertEqual(s["next_due"], "2026-08-20")

    def test_recent_verdicts(self):
        recent = to.recent_verdicts(self.STORE, days=1, today=date(2026, 8, 6))
        self.assertEqual([r["ticket"] for r in recent], ["DAL-4"])

    def test_recent_verdicts_excludes_old(self):
        recent = to.recent_verdicts(self.STORE, days=1, today=date(2026, 9, 1))
        self.assertEqual(recent, [])


class TestVerdictComment(unittest.TestCase):
    RECORD = {
        "ticket": "DAL-219", "metric": "treesmith_downloads",
        "baseline": {"value": 49, "unit": "installs/28d", "read_at": "2026-07-30"},
    }
    VERDICT = {"value": 61, "pct": 24.5, "call": "moved",
               "settled_at": "2026-08-27T00:00:00+00:00"}

    def test_contains_both_readings_and_the_call(self):
        body = to.build_verdict_comment(self.RECORD, self.VERDICT)
        self.assertIn("49", body)
        self.assertIn("61", body)
        self.assertIn("+24.5%", body)
        self.assertIn("moved", body)

    def test_disclaims_causation(self):
        """The verdict is a correlation over a window. Every comment has to say
        so, or a flat month gets read as proof the work was useless."""
        body = to.build_verdict_comment(self.RECORD, self.VERDICT)
        self.assertIn("not attribution", body)

    def test_handles_a_verdict_with_no_percentage(self):
        verdict = dict(self.VERDICT, pct=None, call="too-small")
        body = to.build_verdict_comment(self.RECORD, verdict)
        self.assertIn("too small to call", body)
        self.assertNotIn("None%", body)


class TestWindow(unittest.TestCase):
    def test_window_ends_yesterday(self):
        """Today is a partial day everywhere (Plausible, PostHog, the ledger),
        so including it would compare 28 full days against 27 and a bit."""
        start, end = to._window(date(2026, 8, 6), days=28)
        self.assertEqual(end, "2026-08-05")
        self.assertEqual(start, "2026-07-09")

    def test_window_length(self):
        start, end = to._window(date(2026, 8, 6), days=28)
        self.assertEqual((date.fromisoformat(end) - date.fromisoformat(start)).days,
                         27)


if __name__ == "__main__":
    unittest.main()
