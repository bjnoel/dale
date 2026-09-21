"""
Tests for send_alert() in tools/autonomous/notify.py.

Regression coverage for the false halt alarm (2026-09-21):

  send_alert() had one template and eleven callers. The template said
  "[ALERT] Dale autonomous run halted" and "To resume: remove the issue or
  delete the STOP file", which was true of two callers: the 3-failure circuit
  breaker and the strike gate, both in dale-runner.sh.

  The other nine are cron jobs reporting their own trouble while the hourly
  runner carries on. On 2026-09-21 the 04:20 snapshot-server-config run
  recorded an entirely expected crontab change (the daily App Store pull added
  by DEC-334 on 2026-09-17) and mailed it as a halt. There was no STOP file,
  /opt/dale/autonomous/STOP did not exist, and the runner had polled Linear on
  the hour every hour through 04:00 and kept going after.

  The tell that this was already known: smoke_test.py calls send_email
  directly instead of send_alert, because the halt wording did not fit.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"
sys.path.insert(0, str(AUTONOMOUS))

spec = importlib.util.spec_from_file_location("notify", AUTONOMOUS / "notify.py")
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)

# The message the 2026-09-21 snapshot actually sent, trimmed.
DRIFT_REASON = (
    "The server's configuration changed this week and has been committed to "
    "infrastructure/.\n\n infrastructure/crontab.txt | 13 +++++---\n\n"
    "If you expected this, nothing to do."
)


class SendAlertWording(unittest.TestCase):
    def _capture(self, *args, **kwargs):
        with mock.patch.object(notify, "send_email") as send_email:
            notify.send_alert(*args, **kwargs)
        self.assertEqual(send_email.call_count, 1)
        subject, html = send_email.call_args[0][0], send_email.call_args[0][1]
        return subject, html

    def test_default_alert_does_not_claim_a_halt(self):
        """The config-drift mail must not say Dale stopped, because it did not.

        Checked on the headline and the subject, which is all Benedict sees on
        his phone before deciding whether to open it. The body may say "has NOT
        halted", which is the opposite claim.
        """
        subject, html = self._capture(DRIFT_REASON)
        self.assertNotIn("halted", subject.lower())
        headline = html.split("</h2>", 1)[0]
        self.assertNotIn("halted", headline.lower())

    def test_default_alert_does_not_send_benedict_after_a_stop_file(self):
        """There is no STOP file when a cron job fails. Do not send him looking."""
        _, html = self._capture(DRIFT_REASON)
        self.assertNotIn("STOP", html)

    def test_default_alert_says_the_runner_is_fine(self):
        _, html = self._capture(DRIFT_REASON)
        self.assertIn("NOT halted", html)

    def test_default_alert_still_carries_the_reason(self):
        subject, html = self._capture(DRIFT_REASON)
        self.assertIn("infrastructure/", html)
        self.assertTrue(subject.startswith("[ALERT] Dale needs a look"))

    def test_halted_alert_says_halted(self):
        subject, html = self._capture("3 consecutive failures", halted=True)
        self.assertIn("halted", subject.lower())
        self.assertIn("Dale autonomous run halted", html)

    def test_halted_alert_keeps_the_stop_file_recovery(self):
        _, html = self._capture("3 consecutive failures", halted=True)
        self.assertIn("/opt/dale/autonomous/STOP", html)

    def test_halted_subject_prefix_is_unchanged(self):
        """Benedict filters on this. Changing it silently retires his filter."""
        subject, _ = self._capture("3 consecutive failures", halted=True)
        self.assertTrue(subject.startswith("[ALERT] Dale halted"))

    def test_the_two_shapes_are_distinguishable_by_subject(self):
        quiet, _ = self._capture(DRIFT_REASON)
        loud, _ = self._capture(DRIFT_REASON, halted=True)
        self.assertNotEqual(quiet, loud)


class AlertCli(unittest.TestCase):
    def _run(self, args):
        """Drive the CLI with send_email stubbed out, and read back what it built."""
        script = (
            "import importlib.util, sys, json\n"
            f"spec = importlib.util.spec_from_file_location('notify', {str(AUTONOMOUS / 'notify.py')!r})\n"
            "notify = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(notify)\n"
            "notify.send_email = lambda subject, html, *a, **k: print(json.dumps([subject, html]))\n"
            f"sys.argv = ['notify.py'] + {args!r}\n"
            "cmd = sys.argv[1]\n"
            "rest = sys.argv[2:]\n"
            "halted = '--halted' in rest\n"
            "rest = [a for a in rest if a != '--halted']\n"
            "notify.send_alert(rest[0] if rest else 'Unknown error', halted=halted)\n"
        )
        out = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, check=True
        )
        import json

        return json.loads(out.stdout)

    def test_flag_is_not_swallowed_as_the_reason(self):
        subject, html = self._run(["alert", "--halted", "boom"])
        self.assertIn("boom", html)
        self.assertNotIn("--halted", html)
        self.assertTrue(subject.startswith("[ALERT] Dale halted"))

    def test_flag_may_follow_the_reason(self):
        subject, _ = self._run(["alert", "boom", "--halted"])
        self.assertTrue(subject.startswith("[ALERT] Dale halted"))

    def test_bare_alert_is_quiet(self):
        subject, _ = self._run(["alert", "boom"])
        self.assertTrue(subject.startswith("[ALERT] Dale needs a look"))


class OnlyTheRunnerMayCryHalt(unittest.TestCase):
    """A new cron job must not inherit the halt headline by default.

    This is the test that would have caught 2026-09-21: every caller outside
    dale-runner.sh is a job whose failure leaves autonomous Dale running.
    """

    CALL = re.compile(r'notify\.py"?\s+alert(?P<tail>[^\n]*)')

    def _callers(self):
        for path in sorted((REPO_ROOT / "tools").rglob("*")):
            if not path.is_file() or path.suffix not in (".sh", ".py"):
                continue
            if path.name == "notify.py":
                continue
            text = path.read_text(errors="ignore")
            for m in self.CALL.finditer(text):
                line = text[: m.start()].count("\n") + 1
                yield path.relative_to(REPO_ROOT), line, m.group("tail")

    def test_every_alert_caller_is_accounted_for(self):
        callers = list(self._callers())
        self.assertGreaterEqual(len(callers), 10, "alert callers vanished, check the regex")

    def test_halted_is_only_used_by_dale_runner(self):
        offenders = [
            f"{rel}:{line}"
            for rel, line, tail in self._callers()
            if "--halted" in tail and rel.name != "dale-runner.sh"
        ]
        self.assertEqual(
            offenders,
            [],
            "only the 3-failure breaker and the strike gate stop autonomous Dale; "
            "a failing cron job must not mail Benedict a halt",
        )

    def test_the_breaker_and_the_strike_still_say_halted(self):
        runner = (AUTONOMOUS / "dale-runner.sh").read_text()
        halted = [
            m.group("tail")
            for m in self.CALL.finditer(runner)
            if "--halted" in m.group("tail")
        ]
        self.assertEqual(len(halted), 2, "expected the breaker and the strike gate")
        self.assertTrue(any("consecutive failures" in t for t in halted))
        self.assertTrue(any("on strike" in t for t in halted))

    def test_snapshot_drift_does_not_cry_halt(self):
        """The 2026-09-21 mail itself."""
        snapshot = (AUTONOMOUS / "snapshot-server-config.sh").read_text()
        self.assertNotIn("--halted", snapshot)


if __name__ == "__main__":
    unittest.main()
