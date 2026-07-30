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


class CommitTrailerTests(unittest.TestCase):
    """Regression coverage for the mislabelled commit trailer (2026-07-30).

    The 03:00 session ran on claude-opus-5 and signed its commit
    "Co-Authored-By: Claude Opus 4.6". A model cannot reliably know its own
    id, so the runner now derives the exact trailer from config.json and
    hands it over verbatim.
    """

    def test_model_names(self):
        cases = {
            "claude-opus-5": "Claude Opus 5",
            "claude-sonnet-4-6": "Claude Sonnet 4.6",
            "claude-fable-5": "Claude Fable 5",
            # trailing date stamps are not version numbers
            "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
            # context-window variants
            "claude-opus-5[1m]": "Claude Opus 5 (1M context)",
        }
        for model_id, expected in cases.items():
            with self.subTest(model_id=model_id):
                self.assertEqual(session_prompt.model_display_name(model_id), expected)

    def test_unpinned_model_does_not_invent_a_version(self):
        # With the CLI default in play we do not know what ran. Saying
        # "Claude" is honest; naming a version would be the original bug.
        self.assertEqual(session_prompt.model_display_name(""), "Claude")
        self.assertEqual(
            session_prompt.commit_trailer({}),
            "Co-Authored-By: Claude <noreply@anthropic.com>",
        )

    def test_trailer_includes_model_and_effort(self):
        self.assertEqual(
            session_prompt.commit_trailer(
                {"claude": {"model": "claude-opus-5", "effort": "medium"}}
            ),
            "Co-Authored-By: Claude Opus 5 (effort: medium) <noreply@anthropic.com>",
        )

    def test_trailer_omits_effort_when_unset(self):
        self.assertEqual(
            session_prompt.commit_trailer({"claude": {"model": "claude-opus-5"}}),
            "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>",
        )

    def test_committed_config_produces_a_versioned_trailer(self):
        import json

        with open(REPO_ROOT / "tools" / "autonomous" / "config.json") as f:
            config = json.load(f)
        trailer = session_prompt.commit_trailer(config)
        self.assertTrue(trailer.startswith("Co-Authored-By: Claude "))
        self.assertNotEqual(
            trailer,
            "Co-Authored-By: Claude <noreply@anthropic.com>",
            "config.json should pin a model, so the trailer must name one",
        )

    def test_rendered_prompt_carries_the_trailer(self):
        # The value is interpolated into a large f-string. If that breaks, the
        # rule silently ships as a literal placeholder and sessions guess again.
        prompt = session_prompt.build_prompt()
        expected = session_prompt.commit_trailer(session_prompt.load_config())
        self.assertIn(expected, prompt)
        self.assertNotIn("{commit_trailer_line}", prompt)


if __name__ == "__main__":
    unittest.main()
