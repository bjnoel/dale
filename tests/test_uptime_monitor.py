"""
Tests for tools/autonomous/uptime_monitor.py.

Regression coverage for a bug (2026-05-18):
  uptime_state.json was truncated to 0 bytes on 2026-03-19. load_state()
  called json.load() unconditionally and crashed with JSONDecodeError,
  so the monitor logged ~34k tracebacks and ran zero checks for two
  months. load_state() now treats empty/corrupt state as a fresh start.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"


def load_uptime_monitor():
    # notify is imported at module top; stub it so the test doesn't need Resend creds.
    sys.modules.setdefault("notify", mock.MagicMock())
    spec = importlib.util.spec_from_file_location(
        "uptime_monitor", AUTONOMOUS / "uptime_monitor.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LoadStateTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_uptime_monitor()
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        self.path_patch = mock.patch.object(self.mod, "STATE_PATH", self.tmp.name)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_missing_file_returns_empty(self):
        Path(self.tmp.name).unlink()
        self.assertEqual(self.mod.load_state(), {})

    def test_empty_file_returns_empty(self):
        # Regression: the file existed but was 0 bytes; json.load() raised.
        Path(self.tmp.name).write_text("")
        self.assertEqual(self.mod.load_state(), {})

    def test_corrupt_file_returns_empty(self):
        Path(self.tmp.name).write_text("{not valid json")
        self.assertEqual(self.mod.load_state(), {})

    def test_valid_file_returns_parsed(self):
        Path(self.tmp.name).write_text('{"treestock": {"status": "up"}}')
        self.assertEqual(self.mod.load_state(), {"treestock": {"status": "up"}})


class DiskMonitorTests(unittest.TestCase):
    """Disk alert added 2026-07-04 after the root FS sat at 100% for ~10 days
    undetected (HTTP checks can't see a full disk), corrupting scraper snapshots."""

    def setUp(self):
        self.mod = load_uptime_monitor()

    def test_disk_level_thresholds(self):
        self.assertEqual(self.mod.disk_level(10), "ok")
        self.assertEqual(self.mod.disk_level(84.9), "ok")
        self.assertEqual(self.mod.disk_level(85), "warning")
        self.assertEqual(self.mod.disk_level(92.9), "warning")
        self.assertEqual(self.mod.disk_level(93), "critical")
        self.assertEqual(self.mod.disk_level(100), "critical")

    def test_escalation_sends_one_alert_per_step_up(self):
        self.assertEqual(self.mod.disk_alert_decision("ok", 88), ("warning", "alert"))
        self.assertEqual(self.mod.disk_alert_decision("ok", 95), ("critical", "alert"))
        self.assertEqual(self.mod.disk_alert_decision("warning", 95), ("critical", "alert"))

    def test_no_repeat_while_steady(self):
        self.assertEqual(self.mod.disk_alert_decision("warning", 88), ("warning", "none"))
        self.assertEqual(self.mod.disk_alert_decision("critical", 96), ("critical", "none"))

    def test_hysteresis_holds_between_recover_and_warn(self):
        # 80-85% band while already alerting: keep the level, don't flap.
        self.assertEqual(self.mod.disk_alert_decision("warning", 82), ("warning", "none"))
        self.assertEqual(self.mod.disk_alert_decision("critical", 82), ("critical", "none"))

    def test_recovery_below_threshold(self):
        self.assertEqual(self.mod.disk_alert_decision("warning", 50), ("ok", "recovered"))
        self.assertEqual(self.mod.disk_alert_decision("critical", 79), ("ok", "recovered"))

    def test_de_escalation_is_silent(self):
        # critical -> warning band: update the level but don't email.
        self.assertEqual(self.mod.disk_alert_decision("critical", 90), ("warning", "none"))

    def test_stays_ok(self):
        self.assertEqual(self.mod.disk_alert_decision("ok", 40), ("ok", "none"))

    def test_check_disk_emails_on_first_warning(self):
        # Force usage into the warning band and assert one alert email is sent.
        self.mod.send_email.reset_mock()
        fake = type("U", (), {"total": 100 * 10**9, "free": 10 * 10**9})()  # 90% used
        with mock.patch.object(self.mod.shutil, "disk_usage", return_value=fake):
            state = {}
            self.mod.check_disk(state, "2026-07-04T00:00:00Z")
        self.assertEqual(state["disk"]["level"], "warning")
        self.mod.send_email.assert_called_once()

    def test_check_disk_silent_when_healthy(self):
        self.mod.send_email.reset_mock()
        fake = type("U", (), {"total": 100 * 10**9, "free": 70 * 10**9})()  # 30% used
        with mock.patch.object(self.mod.shutil, "disk_usage", return_value=fake):
            state = {}
            self.mod.check_disk(state, "2026-07-04T00:00:00Z")
        self.assertEqual(state["disk"]["level"], "ok")
        self.mod.send_email.assert_not_called()


class GitDivergenceTests(unittest.TestCase):
    """The 2026-08-13 incident: a stranded commit sat unpushed for 50 minutes and
    was found by accident. Three failed sessions would have halted Dale."""

    def setUp(self):
        self.mod = load_uptime_monitor()

    def test_in_sync_is_silent(self):
        self.assertEqual(self.mod.git_divergence_decision(False, 0, 0), (False, "none"))

    def test_recently_ahead_is_silent(self):
        # Every session and inbound merge commits before it pushes. A repo ahead
        # for a few minutes is the normal path, not a fault.
        self.assertEqual(self.mod.git_divergence_decision(False, 1, 0.2), (False, "none"))

    def test_ahead_past_the_threshold_alerts(self):
        self.assertEqual(self.mod.git_divergence_decision(False, 2, 1.5), (True, "alert"))

    def test_does_not_re_alert_every_five_minutes(self):
        self.assertEqual(self.mod.git_divergence_decision(True, 2, 4.0), (True, "none"))

    def test_recovery_clears_and_notifies_once(self):
        self.assertEqual(self.mod.git_divergence_decision(True, 0, 0), (False, "recovered"))
        self.assertEqual(self.mod.git_divergence_decision(False, 0, 0), (False, "none"))

    def test_check_git_divergence_emails_on_a_stranded_commit(self):
        self.mod.send_email.reset_mock()
        stale = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())

        def fake_git(*args):
            if args[0] == "fetch":
                return ""
            return f"{stale}\tchore: log nursery touches from BCC'd inbound mail"

        with mock.patch.object(self.mod.os.path, "isdir", return_value=True), \
             mock.patch.object(self.mod, "_git", side_effect=fake_git):
            state = {}
            self.mod.check_git_divergence(state, "2026-08-13T03:00:00Z")

        self.assertTrue(state["git"]["alerted"])
        self.assertEqual(state["git"]["ahead"], 1)
        self.mod.send_email.assert_called_once()

    def test_check_git_divergence_silent_when_in_sync(self):
        self.mod.send_email.reset_mock()

        def fake_git(*args):
            return ""

        with mock.patch.object(self.mod.os.path, "isdir", return_value=True), \
             mock.patch.object(self.mod, "_git", side_effect=fake_git):
            state = {}
            self.mod.check_git_divergence(state, "2026-08-13T03:00:00Z")

        self.assertEqual(state["git"]["ahead"], 0)
        self.mod.send_email.assert_not_called()

    def test_fetch_failure_does_not_alert(self):
        """A network blip must not look like a divergence."""
        self.mod.send_email.reset_mock()
        with mock.patch.object(self.mod.os.path, "isdir", return_value=True), \
             mock.patch.object(self.mod, "_git", return_value=None):
            state = {}
            handled = self.mod.check_git_divergence(state, "2026-08-13T03:00:00Z")
        self.assertFalse(handled)
        self.assertNotIn("git", state)
        self.mod.send_email.assert_not_called()


class RebootRequiredTests(unittest.TestCase):
    """DAL-282: the box ran 6.8.0-90 for 161 days with 6.8.0-124 installed and
    reboot-required set since 11 June. 0 packages pending from the security
    pocket, so every existing signal read green."""

    def setUp(self):
        self.mod = load_uptime_monitor()

    def test_reboot_level_thresholds(self):
        self.assertEqual(self.mod.reboot_level(0), "ok")
        self.assertEqual(self.mod.reboot_level(39.9), "ok")
        self.assertEqual(self.mod.reboot_level(40), "warning")
        self.assertEqual(self.mod.reboot_level(74.9), "warning")
        self.assertEqual(self.mod.reboot_level(75), "critical")

    def test_a_normal_monthly_cycle_never_alerts(self):
        """The longest gap between first Mondays is 35 days. If the threshold
        fired inside a healthy cycle, the alert would be noise within two
        months and ignored by the third."""
        for age in (1, 20, 30, 35, 39):
            self.assertEqual(self.mod.reboot_alert_decision("ok", age), ("ok", "none"))

    def test_missed_window_alerts_once(self):
        self.assertEqual(self.mod.reboot_alert_decision("ok", 41), ("warning", "alert"))
        self.assertEqual(self.mod.reboot_alert_decision("warning", 41), ("warning", "none"))

    def test_second_missed_window_escalates_once(self):
        self.assertEqual(self.mod.reboot_alert_decision("warning", 80), ("critical", "alert"))
        self.assertEqual(self.mod.reboot_alert_decision("critical", 90), ("critical", "none"))

    def test_the_state_we_actually_found(self):
        # 2026-06-11 to 2026-08-13 is 63 days: warning, not yet critical.
        self.assertEqual(self.mod.reboot_alert_decision("ok", 63), ("warning", "alert"))

    def test_recovery_when_the_file_disappears(self):
        self.assertEqual(self.mod.reboot_alert_decision("warning", None), ("ok", "recovered"))
        self.assertEqual(self.mod.reboot_alert_decision("critical", None), ("ok", "recovered"))

    def test_no_pending_reboot_is_silent(self):
        self.assertEqual(self.mod.reboot_alert_decision("ok", None), ("ok", "none"))

    def test_check_reboot_required_emails_once_past_the_threshold(self):
        self.mod.send_email.reset_mock()
        with mock.patch.object(self.mod, "read_reboot_required",
                               return_value=(63.0, "2026-06-11 06:22 UTC",
                                             ["libc6", "linux-image-6.8.0-124-generic"])):
            state = {}
            self.mod.check_reboot_required(state, "2026-08-13T03:00:00Z")
            self.assertEqual(state["reboot"]["level"], "warning")
            self.mod.send_email.assert_called_once()

            # Five minutes later, still pending: no second email.
            self.mod.check_reboot_required(state, "2026-08-13T03:05:00Z")
            self.mod.send_email.assert_called_once()

    def test_check_reboot_required_silent_when_none_pending(self):
        self.mod.send_email.reset_mock()
        with mock.patch.object(self.mod, "read_reboot_required",
                               return_value=(None, None, [])):
            state = {}
            self.mod.check_reboot_required(state, "2026-08-13T03:00:00Z")
        self.assertEqual(state["reboot"]["level"], "ok")
        self.assertIsNone(state["reboot"]["age_days"])
        self.mod.send_email.assert_not_called()

    def test_failed_send_is_retried_next_run(self):
        """Same contract as check_disk: a Resend outage must not swallow the
        only warning we get."""
        self.mod.send_email.reset_mock()
        self.mod.send_email.side_effect = RuntimeError("resend down")
        with mock.patch.object(self.mod, "read_reboot_required",
                               return_value=(63.0, "2026-06-11 06:22 UTC", ["libc6"])):
            state = {}
            self.mod.check_reboot_required(state, "2026-08-13T03:00:00Z")
            self.assertEqual(state["reboot"]["level"], "ok")  # not committed
            self.mod.send_email.side_effect = None
            self.mod.check_reboot_required(state, "2026-08-13T03:05:00Z")
        self.assertEqual(state["reboot"]["level"], "warning")
        self.assertEqual(self.mod.send_email.call_count, 2)


class AptFreshnessTests(unittest.TestCase):
    """Found while fixing DAL-282: an apt-get update started by apt.systemd.daily
    on 24 June was still running 48 days later, holding /var/lib/apt/lists/lock.
    unattended-upgrades installed nothing after 24 June, and the '0 pending from
    -security' that made the box look current was read off a frozen index. On a
    fresh index it was 142 upgradable, 83 of them security."""

    def setUp(self):
        self.mod = load_uptime_monitor()

    def test_daily_refresh_is_ok(self):
        self.assertEqual(self.mod.apt_stale_level(0.5), "ok")
        self.assertEqual(self.mod.apt_stale_level(2.9), "ok")

    def test_thresholds(self):
        self.assertEqual(self.mod.apt_stale_level(3), "warning")
        self.assertEqual(self.mod.apt_stale_level(9.9), "warning")
        self.assertEqual(self.mod.apt_stale_level(10), "critical")

    def test_the_48_day_hang_would_have_been_critical(self):
        self.assertEqual(self.mod.apt_stale_decision("ok", 48), ("critical", "alert"))

    def test_missing_stamp_is_critical_not_ok(self):
        """'No evidence apt ever succeeded' must not read as healthy. Assuming
        the friendlier interpretation is what let this sit for seven weeks."""
        self.assertEqual(self.mod.apt_stale_level(None), "critical")
        self.assertEqual(self.mod.apt_stale_decision("ok", None), ("critical", "alert"))

    def test_no_repeat_while_steady(self):
        self.assertEqual(self.mod.apt_stale_decision("warning", 5), ("warning", "none"))
        self.assertEqual(self.mod.apt_stale_decision("critical", 60), ("critical", "none"))

    def test_recovery_once_it_refreshes(self):
        self.assertEqual(self.mod.apt_stale_decision("critical", 0.1), ("ok", "recovered"))

    def test_check_apt_freshness_emails_once(self):
        self.mod.send_email.reset_mock()
        self.mod.send_email.side_effect = None
        with mock.patch.object(self.mod, "apt_index_age_days", return_value=48.0):
            state = {}
            self.mod.check_apt_freshness(state, "2026-08-13T04:00:00Z")
            self.mod.check_apt_freshness(state, "2026-08-13T04:05:00Z")
        self.assertEqual(state["apt"]["level"], "critical")
        self.mod.send_email.assert_called_once()

    def test_check_apt_freshness_silent_when_fresh(self):
        self.mod.send_email.reset_mock()
        self.mod.send_email.side_effect = None
        with mock.patch.object(self.mod, "apt_index_age_days", return_value=0.2):
            state = {}
            self.mod.check_apt_freshness(state, "2026-08-13T04:00:00Z")
        self.assertEqual(state["apt"]["level"], "ok")
        self.mod.send_email.assert_not_called()


if __name__ == "__main__":
    unittest.main()
