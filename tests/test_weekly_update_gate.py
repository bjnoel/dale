"""
Tests for tools/autonomous/check-weekly-update.py -- the strike gate that
decides whether autonomous Dale runs on a given day.

Regression target: on 2026-04-22 (Wed of W17), Dale struck even though
Benedict had published a W16 weekly update three days earlier. The old
gate only accepted the current ISO week's file. Fix: accept any update
within GRACE_WEEKS ISO weeks.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_PATH = REPO_ROOT / "tools" / "autonomous" / "check-weekly-update.py"

# Hyphenated filename means we can't `import check-weekly-update` directly.
spec = importlib.util.spec_from_file_location("check_weekly_update", GATE_PATH)
gate = importlib.util.module_from_spec(spec)
sys.modules["check_weekly_update"] = gate
spec.loader.exec_module(gate)


class WeeksBetween(unittest.TestCase):
    def test_same_week(self):
        self.assertEqual(gate.weeks_between((2026, 17), (2026, 17)), 0)

    def test_one_week_forward(self):
        self.assertEqual(gate.weeks_between((2026, 16), (2026, 17)), 1)

    def test_one_week_backward(self):
        self.assertEqual(gate.weeks_between((2026, 17), (2026, 16)), -1)

    def test_year_boundary(self):
        # 2025-W52 Monday = 2025-12-22; 2026-W01 Monday = 2025-12-29.
        self.assertEqual(gate.weeks_between((2025, 52), (2026, 1)), 1)

    def test_53_week_year(self):
        # 2020 was a 53-week ISO year. W53 Monday = 2020-12-28.
        self.assertEqual(gate.weeks_between((2020, 52), (2020, 53)), 1)
        self.assertEqual(gate.weeks_between((2020, 53), (2021, 1)), 1)


class GateDecision(unittest.TestCase):
    """The core regression surface. Pure function, no I/O."""

    def test_current_week_present_passes(self):
        ok, msg = gate.gate_decision(
            current_week=(2026, 17), weekday=3,
            latest_week=(2026, 17), grace_weeks=2,
        )
        self.assertTrue(ok, msg)

    def test_one_week_old_update_passes_on_wednesday(self):
        # The exact bug we're fixing: Wed of W17, latest is W16.
        ok, msg = gate.gate_decision(
            current_week=(2026, 17), weekday=3,
            latest_week=(2026, 16), grace_weeks=2,
        )
        self.assertTrue(ok, msg)
        self.assertIn("Grace", msg)

    def test_two_week_old_update_passes_at_grace_boundary(self):
        ok, msg = gate.gate_decision(
            current_week=(2026, 18), weekday=5,
            latest_week=(2026, 16), grace_weeks=2,
        )
        self.assertTrue(ok, msg)

    def test_three_week_old_update_strikes(self):
        ok, msg = gate.gate_decision(
            current_week=(2026, 19), weekday=3,
            latest_week=(2026, 16), grace_weeks=2,
        )
        self.assertFalse(ok)
        self.assertIn("STRIKE", msg)

    def test_no_update_ever_early_week_passes(self):
        # Monday, no history. Strike gate only fires Wed+.
        ok, msg = gate.gate_decision(
            current_week=(2026, 17), weekday=1,
            latest_week=None, grace_weeks=2,
        )
        self.assertTrue(ok, msg)

    def test_no_update_ever_wednesday_strikes(self):
        ok, msg = gate.gate_decision(
            current_week=(2026, 17), weekday=3,
            latest_week=None, grace_weeks=2,
        )
        self.assertFalse(ok)
        self.assertIn("STRIKE", msg)

    def test_grace_across_year_boundary(self):
        # W01 2026, latest is W52 2025 (one ISO week ago).
        ok, msg = gate.gate_decision(
            current_week=(2026, 1), weekday=3,
            latest_week=(2025, 52), grace_weeks=2,
        )
        self.assertTrue(ok, msg)

    def test_grace_weeks_zero_reproduces_old_behaviour(self):
        # grace_weeks=0 means only current-week file counts.
        ok, _ = gate.gate_decision(
            current_week=(2026, 17), weekday=3,
            latest_week=(2026, 16), grace_weeks=0,
        )
        self.assertFalse(ok)


class LatestUpdateWeek(unittest.TestCase):
    """Scans the weekly-updates directories. Uses a tmp data dir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        (self.data_dir / "weekly-updates").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, body="real content with enough characters to pass the length check"):
        (self.data_dir / "weekly-updates" / name).write_text(body)

    def _scan(self):
        # Pass explicit search_dirs so the repo's real weekly-updates/ doesn't leak in.
        return gate.latest_update_week(
            str(self.data_dir),
            search_dirs=[str(self.data_dir / "weekly-updates")],
        )

    def test_picks_most_recent(self):
        self._write("2026-W12.md")
        self._write("2026-W14.md")
        self._write("2026-W13.md")
        self.assertEqual(self._scan(), (2026, 14))

    def test_skips_malformed_names(self):
        self._write("2026-W14.md")
        self._write("2026-W15.draft")  # wrong extension
        self._write("notes.md")
        self.assertEqual(self._scan(), (2026, 14))

    def test_skips_empty_files(self):
        self._write("2026-W14.md")
        self._write("2026-W15.md", body="# only a header\n\n")
        self.assertEqual(self._scan(), (2026, 14))

    def test_returns_none_when_no_files(self):
        self.assertIsNone(self._scan())

    def test_year_boundary_picks_newer_year(self):
        self._write("2025-W52.md")
        self._write("2026-W01.md")
        self.assertEqual(self._scan(), (2026, 1))


if __name__ == "__main__":
    unittest.main()
