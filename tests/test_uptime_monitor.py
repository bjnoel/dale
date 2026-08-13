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


if __name__ == "__main__":
    unittest.main()
