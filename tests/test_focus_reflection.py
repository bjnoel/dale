"""
Tests for the strategic reflection in tools/autonomous/session-prompt.py.

Regression coverage for one bug (2026-07-30):
  When a channel went stale, compute_reflection offered EVERY other parent
  in focus-tracker.json as a pivot target, including discontinued ones.
  After beestock was discontinued (DEC-230) and walkthrough paused
  (DEC-104), a stale treestock streak would tell autonomous Dale to
  consider "beestock.com.au growth" instead. focus-tracker.json now has an
  `archived_parents` list that compute_reflection filters out.

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

spec = importlib.util.spec_from_file_location(
    "session_prompt", AUTONOMOUS / "session-prompt.py"
)
session_prompt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session_prompt)

CONFIG = {
    "reflection": {
        "category_streak_threshold": 3,
        "parent_streak_threshold": 4,
        "revenue_alarm_days_threshold": 14,
        "lookback_sessions": 5,
    }
}


def _tracker(archived=None):
    """5 session-days of flat treestock:seo work -- a stale parent."""
    tracker = {
        "categories": {
            "treestock:seo": {
                "parent": "treestock",
                "metrics": ["weekly_organic_visitors"],
            },
            "beestock:growth": {
                "parent": "beestock",
                "metrics": ["weekly_visitors"],
            },
        },
        "parents": {
            "treestock": "treestock.com.au growth",
            "beestock": "beestock.com.au (discontinued 2026-07-23, frozen static)",
            "treesmith": "Track A (Treesmith) revenue",
            "walkthrough": "Track A (Walkthrough, paused) revenue",
            "revenue": "Direct monetisation",
        },
        "session_log": [
            {
                "session": 80 + i,
                "date": f"2026-07-0{i + 1}",
                "categories_worked": ["treestock:seo"],
                "metric_snapshot": {"weekly_organic_visitors": 100},
            }
            for i in range(5)
        ],
    }
    if archived is not None:
        tracker["archived_parents"] = archived
    return tracker


class ArchivedParentTests(unittest.TestCase):
    def test_stale_parent_is_detected(self):
        result = session_prompt.compute_reflection(_tracker([]), CONFIG)
        self.assertEqual(
            ["treestock"], [sp["parent"] for sp in result["stale_parents"]]
        )

    def test_archived_parents_excluded_from_alternatives(self):
        result = session_prompt.compute_reflection(
            _tracker(["beestock", "walkthrough"]), CONFIG
        )
        alts = result["stale_parents"][0]["alternatives"]
        joined = " ".join(alts).lower()
        self.assertNotIn("beestock", joined)
        self.assertNotIn("walkthrough", joined)
        # Live channels are still offered
        self.assertIn("Track A (Treesmith) revenue", alts)
        self.assertIn("Direct monetisation", alts)

    def test_the_bug_without_the_filter(self):
        # No archived_parents key = old behaviour, discontinued channel offered.
        # Guards against the filter silently becoming a no-op.
        result = session_prompt.compute_reflection(_tracker(), CONFIG)
        joined = " ".join(result["stale_parents"][0]["alternatives"]).lower()
        self.assertIn("beestock", joined)

    def test_reflection_block_never_names_an_archived_channel(self):
        result = session_prompt.compute_reflection(
            _tracker(["beestock", "walkthrough"]), CONFIG
        )
        block = session_prompt.build_reflection_block(result)
        self.assertNotIn("beestock", block.lower())
        self.assertNotIn("walkthrough", block.lower())


class LiveTrackerTests(unittest.TestCase):
    """The committed focus-tracker.json must keep the archive list honest."""

    def test_committed_tracker_archives_beestock_and_walkthrough(self):
        import json

        with open(REPO_ROOT / "state" / "focus-tracker.json") as f:
            tracker = json.load(f)
        archived = tracker.get("archived_parents", [])
        self.assertIn("beestock", archived)
        self.assertIn("walkthrough", archived)
        # Every archived name must be a real parent, or the filter does nothing
        for name in archived:
            self.assertIn(name, tracker.get("parents", {}))


if __name__ == "__main__":
    unittest.main()
