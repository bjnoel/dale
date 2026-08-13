"""Tests for tools/autonomous/monthly_maintenance.py.

DAL-282 / DEC-290. The box ran kernel 6.8.0-90 for 161 days with 6.8.0-124
installed and unbooted. The cadence that fixes it is only as good as its date
arithmetic, and that arithmetic crosses a timezone AND a day boundary:
02:30 AWST Monday is 18:30 UTC the preceding *Sunday*. Getting that wrong by a
day means the reboot silently never fires, which is indistinguishable from the
bug we are fixing.

Run from repo root with:
    .venv/bin/python -m unittest discover tests/
"""
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"
PERTH = ZoneInfo("Australia/Perth")


def load_maintenance():
    # notify is imported at module top; stub it so the test needs no Resend creds.
    sys.modules.setdefault("notify", mock.MagicMock())
    spec = importlib.util.spec_from_file_location(
        "monthly_maintenance", AUTONOMOUS / "monthly_maintenance.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def perth(y, m, d, hh=2, mm=30):
    return datetime(y, m, d, hh, mm, tzinfo=PERTH)


class FirstMondayTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_maintenance()

    def test_known_first_mondays_2026(self):
        for y, m, d in [(2026, 8, 3), (2026, 9, 7), (2026, 10, 5),
                        (2026, 11, 2), (2026, 12, 7)]:
            self.assertTrue(self.mod.is_first_monday(perth(y, m, d)),
                            f"{y}-{m}-{d} is the first Monday")

    def test_second_monday_is_not_the_first(self):
        self.assertFalse(self.mod.is_first_monday(perth(2026, 9, 14)))

    def test_monday_the_seventh_still_counts(self):
        """September 2026's first Monday is the 7th, the latest a first Monday
        can fall. An off-by-one on `day <= 7` would skip that whole month."""
        self.assertTrue(self.mod.is_first_monday(perth(2026, 9, 7)))

    def test_early_non_monday_does_not_count(self):
        # 2026-09-01 is a Tuesday and lands inside day <= 7.
        self.assertFalse(self.mod.is_first_monday(perth(2026, 9, 1)))


class WindowTimezoneTests(unittest.TestCase):
    """02:30 AWST Monday must be 18:30 UTC the preceding Sunday. Perth has no
    DST, so this holds year-round; the test pins it anyway because the cron
    lines are written in UTC and nothing else checks the conversion."""

    def setUp(self):
        self.mod = load_maintenance()

    def test_window_maps_to_previous_day_in_utc(self):
        window = perth(2026, 9, 7)
        utc = window.astimezone(timezone.utc)
        self.assertEqual((utc.month, utc.day, utc.hour, utc.minute), (9, 6, 18, 30))
        self.assertEqual(utc.weekday(), 6)  # Sunday

    def test_format_window_names_both_zones(self):
        text = self.mod.format_window(perth(2026, 9, 7))
        self.assertIn("Mon 07 Sep 2026 02:30 AWST", text)
        self.assertIn("Sun 06 Sep 18:30 UTC", text)

    def test_next_window_from_mid_month(self):
        self.assertEqual(self.mod.next_window(perth(2026, 8, 20, 9, 0)),
                         perth(2026, 9, 7))

    def test_next_window_includes_today_before_the_window(self):
        self.assertEqual(self.mod.next_window(perth(2026, 9, 7, 1, 0)),
                         perth(2026, 9, 7))

    def test_next_window_skips_today_once_the_window_has_passed(self):
        self.assertEqual(self.mod.next_window(perth(2026, 9, 7, 3, 0)),
                         perth(2026, 10, 5))


class AnnounceScheduleTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_maintenance()

    def test_announces_on_the_saturday_before_a_window(self):
        # Saturday 2026-09-05, two days before Monday the 7th.
        self.assertTrue(self.mod.should_announce(perth(2026, 9, 5, 9, 0)))

    def test_silent_on_every_other_saturday(self):
        for d in (12, 19, 26):
            self.assertFalse(self.mod.should_announce(perth(2026, 9, d, 9, 0)))

    def test_announcement_crosses_the_month_boundary(self):
        """October 2026's first Monday is the 5th, so its announcement falls on
        Saturday 3 October. November's falls on Saturday 31 October, in the
        previous month entirely."""
        self.assertTrue(self.mod.should_announce(perth(2026, 10, 3, 9, 0)))
        self.assertTrue(self.mod.should_announce(perth(2026, 10, 31, 9, 0)))


class HasWorkTests(unittest.TestCase):
    """A window with nothing to install must not reboot the box. Otherwise the
    cadence becomes twelve pointless outages a year and gets switched off."""

    def setUp(self):
        self.mod = load_maintenance()

    def test_nothing_pending_is_a_no_op(self):
        self.assertFalse(self.mod.has_work(None, 0))

    def test_reboot_pending_is_work(self):
        self.assertTrue(self.mod.has_work(datetime(2026, 6, 11, tzinfo=timezone.utc), 0))

    def test_packages_pending_is_work(self):
        self.assertTrue(self.mod.has_work(None, 55))


class VetoTests(unittest.TestCase):
    """The veto is one-shot on purpose. A sticky veto left in place would
    recreate exactly the nine-week gap DAL-282 is about."""

    def setUp(self):
        self.mod = load_maintenance()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.veto = Path(self.tmpdir.name) / "no-reboot"
        self.patch = mock.patch.object(self.mod, "VETO_FILE", str(self.veto))
        self.patch.start()
        self.mod.send_email.reset_mock()
        self.mod.send_email.side_effect = None

    def tearDown(self):
        self.patch.stop()
        self.tmpdir.cleanup()

    def test_veto_skips_the_window_and_clears_itself(self):
        self.veto.write_text("")
        with mock.patch.object(self.mod, "run") as ran:
            rc = self.mod.do_run(perth(2026, 9, 7))
        self.assertEqual(rc, 0)
        self.assertFalse(self.veto.exists(), "veto must not survive its own window")
        ran.assert_not_called()
        self.mod.send_email.assert_called_once()

    def test_veto_is_cleared_even_when_the_email_fails(self):
        """Otherwise a Resend outage turns a one-month skip into a permanent one."""
        self.veto.write_text("")
        self.mod.send_email.side_effect = RuntimeError("resend down")
        rc = self.mod.do_run(perth(2026, 9, 7))
        self.assertEqual(rc, 0)
        self.assertFalse(self.veto.exists())


class RunGuardTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_maintenance()
        self.mod.send_email.reset_mock()
        self.mod.send_email.side_effect = None

    def test_wrong_day_does_nothing(self):
        with mock.patch.object(self.mod, "run") as ran, \
             mock.patch.object(self.mod.os.path, "exists", return_value=False):
            rc = self.mod.do_run(perth(2026, 9, 14))
        self.assertEqual(rc, 0)
        ran.assert_not_called()

    def test_force_overrides_the_day_guard(self):
        """The attended first run happens on a Thursday in daylight, not at the
        scheduled window."""
        with mock.patch.object(self.mod.os.path, "exists", return_value=False), \
             mock.patch.object(self.mod, "pending_upgrades", return_value=(55, [])), \
             mock.patch.object(self.mod, "reboot_required_since",
                               return_value=datetime(2026, 6, 11, tzinfo=timezone.utc)):
            rc = self.mod.do_run(perth(2026, 8, 13, 14, 0), dry_run=True, force=True)
        self.assertEqual(rc, 0)

    def test_nothing_to_do_skips_the_reboot(self):
        with mock.patch.object(self.mod.os.path, "exists", return_value=False), \
             mock.patch.object(self.mod, "pending_upgrades", return_value=(0, [])), \
             mock.patch.object(self.mod, "reboot_required_since", return_value=None), \
             mock.patch.object(self.mod, "run") as ran:
            rc = self.mod.do_run(perth(2026, 9, 7))
        self.assertEqual(rc, 0)
        ran.assert_not_called()

    def test_a_failed_apt_stage_does_not_reboot(self):
        """Rebooting on top of a half-applied full-upgrade is how a two-minute
        outage becomes an unbootable box."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if "full-upgrade" in cmd:
                return 100, "E: dpkg was interrupted"
            return 0, ""

        with mock.patch.object(self.mod.os.path, "exists", return_value=False), \
             mock.patch.object(self.mod, "pending_upgrades", return_value=(55, [])), \
             mock.patch.object(self.mod, "reboot_required_since",
                               return_value=datetime(2026, 6, 11, tzinfo=timezone.utc)), \
             mock.patch.object(self.mod, "wait_for_session", return_value=True), \
             mock.patch.object(self.mod, "run", side_effect=fake_run):
            rc = self.mod.do_run(perth(2026, 9, 7))

        self.assertEqual(rc, 1)
        self.assertFalse(any("shutdown" in c for c in calls),
                         "must not reboot after a failed upgrade")
        self.mod.send_email.assert_called_once()


class SessionLockTests(unittest.TestCase):
    """An autonomous session started at 18:00 UTC can still hold the lock at the
    18:30 window."""

    def setUp(self):
        self.mod = load_maintenance()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.lock = Path(self.tmpdir.name) / "session.lock"
        self.patch = mock.patch.object(self.mod, "SESSION_LOCK", str(self.lock))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmpdir.cleanup()

    def test_no_lock_file_is_clear(self):
        self.assertFalse(self.mod.session_is_live())

    def test_dead_pid_is_not_live(self):
        # PID 0 is never a real userland process to signal here.
        self.lock.write_text("999999")
        self.assertFalse(self.mod.session_is_live())

    def test_our_own_pid_counts_as_live(self):
        import os
        self.lock.write_text(str(os.getpid()))
        self.assertTrue(self.mod.session_is_live())

    def test_garbage_lock_is_not_live(self):
        self.lock.write_text("not-a-pid")
        self.assertFalse(self.mod.session_is_live())

    def test_wait_gives_up_and_proceeds(self):
        """Waiting forever would mean the reboot never happens, which is the
        original bug wearing a different hat."""
        import os
        self.lock.write_text(str(os.getpid()))
        slept = []
        cleared = self.mod.wait_for_session(max_seconds=45, sleep=slept.append)
        self.assertFalse(cleared)
        self.assertEqual(len(slept), 3)  # 45s / 15s poll


if __name__ == "__main__":
    unittest.main()
