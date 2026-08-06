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
import sys
import unittest
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
