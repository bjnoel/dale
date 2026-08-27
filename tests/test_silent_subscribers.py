"""
DAL-262: a subscriber can stop receiving digests and nothing says so.

The rule under test is deliberately NOT "no digest in 14 days", which is what
the ticket proposed. Measured against the real send log, a calendar rule
false-fires on three healthy subscribers across 2026-03-31 to 2026-04-20,
because the digest was not running at all in that window. So a gap is counted in
opportunities (send-log entries that reached somebody), and total list silence is
reported separately as a sender outage.

These tests exist to hold that distinction, because a calendar threshold is the
obvious thing to "simplify" this back into.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

import detect_silent_subscribers as dss  # noqa: E402

TODAY = date(2026, 8, 27)


def sub(email, freq="daily", joined="2026-01-01"):
    rec = {"email": email, "subscribed_at": f"{joined}T00:00:00", "state": "ALL"}
    if freq is not None:
        rec["frequency"] = freq
    return rec


def daily_log(days, recipients):
    """Every day in `days` mailed `recipients`, unless a per-day list is given."""
    if isinstance(recipients, dict):
        return dict(recipients)
    return {d: list(recipients) for d in days}


DAYS = [f"2026-08-{n:02d}" for n in range(1, 28)]


class OpportunityCountingTests(unittest.TestCase):
    def test_a_day_that_mailed_nobody_is_not_an_opportunity(self):
        """A run that sent zero emails is not a send anyone can be said to miss."""
        log = {"2026-08-01": ["a@x"], "2026-08-02": [], "2026-08-03": []}
        self.assertEqual(dss.opportunity_keys(log), ["2026-08-01"])

    def test_weekly_keys_parse_to_their_end_date(self):
        self.assertEqual(dss.key_to_date("week-2026-08-23"), date(2026, 8, 23))
        self.assertEqual(dss.key_to_date("2026-08-23"), date(2026, 8, 23))


class StoppedSubscriberTests(unittest.TestCase):
    def test_missing_the_last_three_daily_sends_is_reported(self):
        log = daily_log(DAYS, {d: (["a@x", "b@x"] if d <= "2026-08-23" else ["b@x"])
                               for d in DAYS})
        findings, outages = dss.detect([sub("a@x"), sub("b@x")], log, {}, TODAY)
        self.assertEqual(outages, [])
        self.assertEqual([f["email"] for f in findings], ["a@x"])
        self.assertEqual(findings[0]["type"], "stopped")
        self.assertEqual(findings[0]["missed"], 4)

    def test_missing_two_is_still_within_the_observed_noise_floor(self):
        """Healthy subscribers have missed 2 consecutive sends in real history."""
        log = daily_log(DAYS, {d: (["a@x", "b@x"] if d <= "2026-08-25" else ["b@x"])
                               for d in DAYS})
        findings, _ = dss.detect([sub("a@x"), sub("b@x")], log, {}, TODAY)
        self.assertEqual(findings, [])

    def test_frequency_off_is_never_reported(self):
        log = daily_log(DAYS, ["b@x"])
        findings, _ = dss.detect([sub("a@x", freq="off"), sub("b@x")], log, {}, TODAY)
        self.assertEqual(findings, [])


class NeverReceivedTests(unittest.TestCase):
    """The DAL-260 case: signed up, never received one, invisible for 23 days."""

    def test_a_subscriber_who_has_never_received_one_is_reported(self):
        log = daily_log(DAYS, ["b@x"])
        findings, _ = dss.detect(
            [sub("a@x", joined="2026-08-01"), sub("b@x")], log, {}, TODAY)
        self.assertEqual([f["type"] for f in findings], ["never"])
        self.assertIn("never received", findings[0]["detail"])

    def test_a_subscriber_who_joined_today_is_not_an_alert(self):
        log = daily_log(DAYS, ["b@x"])
        findings, _ = dss.detect(
            [sub("a@x", joined="2026-08-27"), sub("b@x")], log, {}, TODAY)
        self.assertEqual(findings, [])

    def test_a_weekly_subscriber_gets_two_weeks_before_being_called_broken(self):
        weekly = {"week-2026-08-16": ["b@x"], "week-2026-08-23": ["b@x"]}
        one_week = {"week-2026-08-23": ["b@x"]}
        s = [sub("a@x", freq="weekly", joined="2026-08-10"),
             sub("b@x", freq="weekly", joined="2026-08-10")]
        self.assertEqual(dss.detect(s, {}, one_week, TODAY)[0], [])
        self.assertEqual([f["email"] for f in dss.detect(s, {}, weekly, TODAY)[0]], ["a@x"])


class SenderOutageTests(unittest.TestCase):
    """The regression the calendar rule would have caused."""

    def test_total_silence_is_the_senders_fault_not_the_subscribers(self):
        log = {"2026-08-01": ["a@x", "b@x"]}
        findings, outages = dss.detect([sub("a@x"), sub("b@x")], log, {}, TODAY)
        self.assertEqual(findings, [], "nobody is broken when the sender is down")
        self.assertEqual(len(outages), 1)
        self.assertEqual(outages[0]["frequency"], "daily")
        self.assertEqual(outages[0]["days"], 26)

    def test_a_stalled_channel_does_not_mask_the_other_one(self):
        """Daily down, weekly fine: the weekly subscriber is still judged."""
        weekly = {f"week-2026-08-{n}": ["b@x"] for n in ("09", "16", "23")}
        subs = [sub("a@x"), sub("b@x", freq="weekly"), sub("c@x", freq="weekly")]
        findings, outages = dss.detect(subs, {"2026-08-01": ["a@x"]}, weekly, TODAY)
        self.assertEqual([o["frequency"] for o in outages], ["daily"])
        self.assertEqual([f["email"] for f in findings], ["c@x"])

    def test_a_four_day_pause_is_not_an_outage(self):
        """2026-07-01 to 07-04 was a real pause and did not need an email."""
        log = {"2026-08-23": ["a@x"]}
        _, outages = dss.detect([sub("a@x")], log, {}, TODAY)
        self.assertEqual(outages, [])


class ReportTests(unittest.TestCase):
    def test_the_email_names_the_subscriber_and_the_condition(self):
        findings = [{"email": "a@x", "frequency": "daily", "type": "never",
                     "missed": 9, "detail": "has never received a daily digest"}]
        subject, html, text = dss.build_email(findings, [], "2026-08-27", 12)
        self.assertIn("a@x", html)
        self.assertIn("a@x", text)
        self.assertIn("1 not receiving", subject)

    def test_the_email_says_a_skip_can_be_legitimate(self):
        """A digest is skipped when nothing matches the filters. Saying so is the
        difference between an alarm that gets read and one that gets muted."""
        _, html, _ = dss.build_email(
            [{"email": "a@x", "frequency": "daily", "type": "stopped",
              "missed": 3, "detail": "x"}], [], "2026-08-27", 12)
        self.assertIn("legitimately skipped", html)
        self.assertIn("Nothing has been repaired", html)


if __name__ == "__main__":
    unittest.main()
