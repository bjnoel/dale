"""
Tests for tools/autonomous/check-weekly-update.py -- the engagement gate
that decides whether autonomous Dale runs on a given day.

History of the gate:
- 2026-04-22 regression: Dale struck on Wed of W17 despite a W16 update
  three days earlier (gate only accepted the current week's file).
- 2026-07-23 redesign (engagement gate): the old weekly-writing gate had a
  loophole where Monday and Tuesday always passed no matter how stale the
  last update was, so a months-old update meant Dale worked Mon-Tue and
  struck Wed-Sun, every week, forever. The new gate strikes only after
  GRACE_DAYS with no engagement signal (Benedict weekly-update file OR the
  Linear engagement stamp), and applies on every weekday.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import date
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

    def test_recent_weekly_update_passes(self):
        # W30 Monday is 2026-07-20; three days later is fine.
        ok, msg = gate.gate_decision(
            today=date(2026, 7, 23),
            latest_week=(2026, 30), stamp_date=None, grace_days=28,
        )
        self.assertTrue(ok, msg)

    def test_recent_linear_stamp_passes_without_any_update_file(self):
        ok, msg = gate.gate_decision(
            today=date(2026, 7, 23),
            latest_week=None, stamp_date=date(2026, 7, 22), grace_days=28,
        )
        self.assertTrue(ok, msg)
        self.assertIn("Linear", msg)

    def test_newest_signal_wins(self):
        # Update file is months stale but Linear stamp is fresh: proceed.
        ok, msg = gate.gate_decision(
            today=date(2026, 7, 23),
            latest_week=(2026, 20), stamp_date=date(2026, 7, 20), grace_days=28,
        )
        self.assertTrue(ok, msg)

    def test_all_signals_stale_strikes(self):
        ok, msg = gate.gate_decision(
            today=date(2026, 7, 23),
            latest_week=(2026, 20), stamp_date=date(2026, 5, 20), grace_days=28,
        )
        self.assertFalse(ok)
        self.assertIn("STRIKE", msg)

    def test_no_monday_loophole(self):
        # The 2026-07 bug: old gate passed Mon/Tue regardless of staleness.
        # 2026-07-20 was a Monday; W20's update is months old. Must strike.
        ok, msg = gate.gate_decision(
            today=date(2026, 7, 20),
            latest_week=(2026, 20), stamp_date=None, grace_days=28,
        )
        self.assertFalse(ok)
        self.assertIn("STRIKE", msg)

    def test_no_signals_ever_strikes(self):
        ok, msg = gate.gate_decision(
            today=date(2026, 7, 23),
            latest_week=None, stamp_date=None, grace_days=28,
        )
        self.assertFalse(ok)
        self.assertIn("STRIKE", msg)

    def test_grace_boundary_inclusive(self):
        # Exactly 28 days ago still passes; 29 strikes.
        ok, _ = gate.gate_decision(
            today=date(2026, 7, 29),
            latest_week=None, stamp_date=date(2026, 7, 1), grace_days=28,
        )
        self.assertTrue(ok)
        ok, _ = gate.gate_decision(
            today=date(2026, 7, 30),
            latest_week=None, stamp_date=date(2026, 7, 1), grace_days=28,
        )
        self.assertFalse(ok)

    def test_weekly_update_dated_by_its_monday(self):
        # W25 Monday = 2026-06-15. 28 days later = 2026-07-13 passes,
        # 2026-07-14 strikes.
        ok, _ = gate.gate_decision(
            today=date(2026, 7, 13),
            latest_week=(2026, 25), stamp_date=None, grace_days=28,
        )
        self.assertTrue(ok)
        ok, _ = gate.gate_decision(
            today=date(2026, 7, 14),
            latest_week=(2026, 25), stamp_date=None, grace_days=28,
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

    def test_skips_unsigned_auto_drafts(self):
        self._write("2026-W14.md")
        self._write(
            "2026-W15.md",
            body="# Week 2026-W15\n\n<!-- auto-drafted by Dale: delete this "
                 "line to sign off -->\n\n- DAL-1 something shipped\n",
        )
        self.assertEqual(self._scan(), (2026, 14))

    def test_signed_off_draft_counts(self):
        # Benedict deleted the marker line: the draft now counts.
        self._write("2026-W14.md")
        self._write(
            "2026-W15.md",
            body="# Week 2026-W15\n\n- DAL-1 something shipped\nlooks good, B\n",
        )
        self.assertEqual(self._scan(), (2026, 15))

    def test_returns_none_when_no_files(self):
        self.assertIsNone(self._scan())

    def test_year_boundary_picks_newer_year(self):
        self._write("2025-W52.md")
        self._write("2026-W01.md")
        self.assertEqual(self._scan(), (2026, 1))


class EngagementStamp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _write_stamp(self, payload):
        with open(os.path.join(self.data_dir, "benedict-engagement.json"), "w") as f:
            if isinstance(payload, str):
                f.write(payload)
            else:
                json.dump(payload, f)

    def test_missing_stamp_returns_none(self):
        self.assertIsNone(gate.read_engagement_stamp(self.data_dir))

    def test_valid_stamp(self):
        self._write_stamp({"last_seen": "2026-07-22", "source": "linear"})
        self.assertEqual(gate.read_engagement_stamp(self.data_dir), date(2026, 7, 22))

    def test_datetime_last_seen_truncated_to_date(self):
        self._write_stamp({"last_seen": "2026-07-22T09:15:00Z", "source": "linear"})
        self.assertEqual(gate.read_engagement_stamp(self.data_dir), date(2026, 7, 22))

    def test_corrupt_stamp_returns_none(self):
        self._write_stamp("{not json")
        self.assertIsNone(gate.read_engagement_stamp(self.data_dir))

    def test_wrong_shape_returns_none(self):
        self._write_stamp({"seen": "2026-07-22"})
        self.assertIsNone(gate.read_engagement_stamp(self.data_dir))


if __name__ == "__main__":
    unittest.main()
