"""
Tests for the daily digest's "Waiting on you" block.

The block exists because DAL-177 sat in Todo assigned to Benedict for 101 days
while the digest reported cheerfully on activity every morning. Detection has
two halves and both are load-bearing: assignment catches DAL-177, and the
Cost-line scan catches the many unassigned tickets that still end "Dale drafts,
Benedict sends".

Cost lines below are copied verbatim from real DAL tickets on 2026-08-06.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"
sys.path.insert(0, str(AUTONOMOUS))

# Module name has a hyphen, so it cannot be imported normally.
_spec = importlib.util.spec_from_file_location(
    "daily_digest", AUTONOMOUS / "daily-digest.py")
daily_digest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(daily_digest)

MATCH = daily_digest.BENEDICT_ACTION_RE.search


class TestBenedictActionDetection(unittest.TestCase):
    def test_real_cost_lines_that_need_benedict(self):
        for line in [
            "**Cost:** $0, ~5 min · Benedict must: open Play Console.",
            "**Cost:** $0 · Benedict: dashboard, project settings, API keys.",
            "**Cost:** $0 · Blocked on Benedict for an export or an API key.",
            "**Blocked on you, both cheap:** create the alias",
            "**Cost:** $0 · Dale drafts one page, Benedict sends.",
            "**Cost:** $0 · Dale specs, Benedict implements.",
            "**Cost:** $0 · Dale researches, Benedict approves the outreach list.",
            "**Cost:** $0 · Benedict picks which ones to join.",
            "**Cost:** $0 · Benedict verifies (import from GSC is fastest).",
            "**Cost:** $0 · Dale drafts, Benedict approves.",
            "**Cost:** $0 · Dale specs, ~30 min of Benedict's Flutter time.",
            "Draft the three replies so Benedict only pastes and sends.",
            "**Cost:** $0 · Dale drafts, Benedict submits.",
        ]:
            with self.subTest(line=line):
                self.assertTrue(MATCH(line), f"should have matched: {line}")

    def test_autonomous_tickets_do_not_match(self):
        for line in [
            "**Cost:** $0, ~2hr · Dale autonomous, read-only.",
            "**Cost:** $0 · Dale autonomous, one session maximum.",
            "**Cost:** $0, roughly 15 lines · Dale autonomous.",
            "**Cost:** $0, a few lines · Dale autonomous, carefully.",
        ]:
            with self.subTest(line=line):
                self.assertFalse(MATCH(line), f"should not have matched: {line}")

    def test_case_insensitive(self):
        self.assertTrue(MATCH("blocked on benedict for a key"))


class TestWaitingRender(unittest.TestCase):
    WAITING = [
        {"id": "DAL-177", "title": "Store description variant", "state": "Todo",
         "days": 101, "assigned": True},
        {"id": "DAL-274", "title": "Draft nursery replies", "state": "Backlog",
         "days": 3, "assigned": False},
    ]

    def test_text_flags_the_stale_one(self):
        out = daily_digest.build_digest_text(
            [], [], [], {"count": 0, "cost_usd": 0, "duration_min": 0,
                         "tokens_in": 0, "tokens_out": 0},
            "", "focus",
            {"total_subscribers": 0, "variety_watch_count": 0, "variety_watches": {}},
            "2026-08-06", waiting=self.WAITING)
        self.assertIn("101d (!)", out)
        self.assertIn("DAL-177", out)
        self.assertIn("1 over 30 days old", out)
        # A 3-day-old ticket is listed but not flagged.
        self.assertIn("DAL-274", out)
        self.assertNotIn("3d (!)", out)

    def test_empty_state_says_so(self):
        out = daily_digest.build_digest_text(
            [], [], [], {"count": 0, "cost_usd": 0, "duration_min": 0,
                         "tokens_in": 0, "tokens_out": 0},
            "", "focus",
            {"total_subscribers": 0, "variety_watch_count": 0, "variety_watches": {}},
            "2026-08-06", waiting=[])
        self.assertIn("Nothing is blocked on you", out)

    def test_html_marks_stale_rows_red(self):
        html = daily_digest._waiting_html(self.WAITING)
        self.assertIn("#b91c1c", html)   # stale colour, DAL-177
        self.assertIn("DAL-274", html)

    def test_missing_age_does_not_crash(self):
        """createdAt can fail to parse; the row should still render."""
        html = daily_digest._waiting_html(
            [{"id": "DAL-1", "title": "x", "state": "Todo", "days": None,
              "assigned": True}])
        self.assertIn("DAL-1", html)


REGISTER = {
    "nurseries": [
        {"key": "ftl", "name": "Fruit Tree Lane", "status": "not_contacted",
         "open_action": {"owner": "benedict", "since": "2026-03-28",
                         "what": "Touch 1 draft was prepared under DAL-77"}},
        {"key": "daleys", "name": "Daleys Fruit Trees", "status": "warm",
         "open_action": {"owner": "benedict", "since": "2026-04-25",
                         "what": "Touch 1.5 reply: thank Correy"}},
        # Dale's work, not Benedict's: must not appear on his list.
        {"key": "gw", "name": "Garden World", "status": "not_contacted",
         "open_action": {"owner": "dale", "since": "2026-07-30",
                         "what": "No email or contact page found"}},
        # No open action at all.
        {"key": "quiet", "name": "Quiet Nursery", "status": "not_contacted"},
        # Open action with an empty 'what' is not an action.
        {"key": "blank", "name": "Blank Action", "status": "warm",
         "open_action": {"owner": "benedict", "since": "2026-01-01", "what": ""}},
    ]
}


class TestNurseryActions(unittest.TestCase):
    """The oldest thing blocked on Benedict is not in Linear: Fruit Tree Lane has
    owed a reply since 2026-03-28. The waiting list has to be able to see it."""

    def _dir(self, register=REGISTER):
        tmp = tempfile.mkdtemp()
        (Path(tmp) / "nursery-contacts.json").write_text(json.dumps(register))
        return tmp

    def test_returns_only_benedict_owned_actions(self):
        rows = daily_digest.get_nursery_actions(self._dir(), today=date(2026, 8, 6))
        self.assertEqual([r["id"] for r in rows],
                         ["Fruit Tree Lane", "Daleys Fruit Trees"])

    def test_ages_from_since(self):
        rows = daily_digest.get_nursery_actions(self._dir(), today=date(2026, 8, 6))
        self.assertEqual(rows[0]["days"], 131)
        self.assertEqual(rows[1]["days"], 103)

    def test_tagged_as_nursery_source(self):
        rows = daily_digest.get_nursery_actions(self._dir(), today=date(2026, 8, 6))
        self.assertTrue(all(r["source"] == "nursery" for r in rows))
        self.assertTrue(all(r["assigned"] for r in rows))

    def test_long_action_text_is_trimmed(self):
        reg = {"nurseries": [{"name": "N", "status": "warm", "open_action": {
            "owner": "benedict", "since": "2026-01-01", "what": "x" * 400}}]}
        rows = daily_digest.get_nursery_actions(self._dir(reg), today=date(2026, 8, 6))
        self.assertLessEqual(len(rows[0]["title"]),
                             daily_digest.NURSERY_ACTION_MAXLEN + 3)
        self.assertTrue(rows[0]["title"].endswith("..."))

    def test_bad_since_date_does_not_crash(self):
        reg = {"nurseries": [{"name": "N", "status": "warm", "open_action": {
            "owner": "benedict", "since": "not-a-date", "what": "do it"}}]}
        rows = daily_digest.get_nursery_actions(self._dir(reg), today=date(2026, 8, 6))
        self.assertIsNone(rows[0]["days"])

    def test_missing_register_returns_empty(self):
        self.assertEqual(
            daily_digest.get_nursery_actions(tempfile.mkdtemp()), [])

    def test_corrupt_register_returns_empty(self):
        tmp = tempfile.mkdtemp()
        (Path(tmp) / "nursery-contacts.json").write_text("{not json")
        self.assertEqual(daily_digest.get_nursery_actions(tmp), [])


class TestMergedWaitingList(unittest.TestCase):
    """One blocked-on-me list. Linear tickets and nursery actions interleave
    strictly by age, whichever source they came from."""

    LINEAR = [
        {"id": "DAL-80", "title": "Goodwill outreach", "state": "Todo",
         "days": 133, "assigned": True, "source": "linear"},
        {"id": "DAL-177", "title": "Store description", "state": "Todo",
         "days": 101, "assigned": True, "source": "linear"},
    ]
    NURSERY = [
        {"id": "Fruit Tree Lane", "title": "reply owed", "state": "not_contacted",
         "days": 131, "assigned": True, "source": "nursery"},
    ]

    def test_interleaves_by_age(self):
        merged = daily_digest.sort_by_age(self.LINEAR + self.NURSERY)
        self.assertEqual([r["id"] for r in merged],
                         ["DAL-80", "Fruit Tree Lane", "DAL-177"])

    def test_undated_rows_sort_last(self):
        rows = self.LINEAR + [{"id": "X", "title": "t", "state": "s",
                               "days": None, "assigned": True, "source": "linear"}]
        self.assertEqual(daily_digest.sort_by_age(rows)[-1]["id"], "X")

    def test_text_render_tags_the_nursery_row(self):
        merged = daily_digest.sort_by_age(self.LINEAR + self.NURSERY)
        out = daily_digest.build_digest_text(
            [], [], [], {"count": 0, "cost_usd": 0, "duration_min": 0,
                         "tokens_in": 0, "tokens_out": 0},
            "", "focus",
            {"total_subscribers": 0, "variety_watch_count": 0, "variety_watches": {}},
            "2026-08-06", waiting=merged)
        self.assertIn("Fruit Tree Lane", out)
        self.assertIn("[nursery]", out)
        # Linear rows stay untagged.
        self.assertNotIn("DAL-80: Goodwill outreach [Todo] [nursery]", out)

    def test_html_render_tags_the_nursery_row(self):
        merged = daily_digest.sort_by_age(self.LINEAR + self.NURSERY)
        html = daily_digest._waiting_html(merged)
        self.assertIn("[nursery]", html)
        self.assertIn("Fruit Tree Lane", html)


class TestOutcomesRender(unittest.TestCase):
    RECENT = [{
        "ticket": "DAL-219", "metric": "treesmith_downloads",
        "baseline": {"value": 49, "unit": "installs/28d"},
        "verdict": {"value": 61, "pct": 24.5, "call": "moved"},
    }]
    SUMMARY = {"awaiting": 4, "ungraded": 2, "next_due": "2026-09-01"}

    def test_html_shows_before_after_and_call(self):
        html = daily_digest._outcomes_html(self.RECENT, self.SUMMARY)
        self.assertIn("49", html)
        self.assertIn("61", html)
        self.assertIn("+24.5%", html)
        self.assertIn("moved", html)
        self.assertIn("shipped without a readable metric", html)

    def test_no_verdicts_still_reports_pending(self):
        html = daily_digest._outcomes_html([], self.SUMMARY)
        self.assertIn("No verdicts came due today", html)
        self.assertIn("4 awaiting a verdict", html)

    def test_verdict_without_percentage_renders(self):
        recent = [dict(self.RECENT[0],
                       verdict={"value": 3, "pct": None, "call": "too-small"})]
        html = daily_digest._outcomes_html(recent, self.SUMMARY)
        self.assertIn("too small to call", html)
        self.assertNotIn("None", html)


if __name__ == "__main__":
    unittest.main()
