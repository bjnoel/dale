"""
Tests for the Treesmith intro drip email (DAL-173).

Benedict's brief was specific: the email goes to new subscribers about a week
after they subscribe, and never again. Three things can go wrong and all three
are expensive:

  1. Sending twice to the same person.
  2. Sending to the 13 existing subscribers, who are the subject of a separate
     one-time broadcast Benedict wants to approve on its own.
  3. Sending before he has approved the copy, which is what the enabled flag
     exists to prevent.

Plus the copy itself has to survive the two errors this repo has already made
in Treesmith copy: calling Pro a subscription (corrected 2026-07-27) and the
wrong App Store id / "Android beta" in the original DAL-173 draft.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import send_treesmith_intro as intro

# Comfortably after DRIP_START_DATE so the fixtures below can be up to 40 days
# old without tripping the start-date gate, which has its own test.
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def sub(email, days_ago, state="ALL"):
    return {
        "email": email,
        "subscribed_at": (NOW - timedelta(days=days_ago)).isoformat(),
        "state": state,
    }


class EligibilityTest(unittest.TestCase):
    def due(self, subscribers, sends_log=None):
        return [s["email"] for s in intro.eligible_subscribers(
            subscribers, sends_log or {}, NOW)]

    def test_waits_the_delay_before_sending(self):
        subscribers = [sub("new@example.com", 2), sub("ready@example.com", 8)]
        self.assertEqual(self.due(subscribers), ["ready@example.com"])

    def test_boundary_at_exactly_the_delay_is_due(self):
        self.assertEqual(
            self.due([sub("edge@example.com", intro.DRIP_DELAY_DAYS)]),
            ["edge@example.com"],
        )

    def test_never_sends_twice(self):
        subscribers = [sub("done@example.com", 30)]
        log = {"done@example.com": "2026-08-01T00:00:00+00:00"}
        self.assertEqual(self.due(subscribers, log), [])

    def test_sends_log_match_is_case_insensitive(self):
        subscribers = [sub("Mixed@Example.com", 30)]
        log = {"mixed@example.com": "2026-08-01T00:00:00+00:00"}
        self.assertEqual(self.due(subscribers, log), [])

    def test_excludes_subscribers_from_before_the_drip_existed(self):
        # The real subscribers.json entries all predate DRIP_START_DATE. They
        # belong to the separate one-time broadcast, not to this drip.
        old = {
            "email": "original@example.com",
            "subscribed_at": "2026-03-13T14:32:43.292437",
            "state": "WA",
        }
        self.assertEqual(self.due([old]), [])

    def test_drip_start_date_is_not_in_the_future(self):
        # A future start date would silently make the drip a permanent no-op.
        start = intro._parse_subscribed_at(intro.DRIP_START_DATE)
        self.assertLessEqual(start, datetime.now(timezone.utc))

    def test_unparseable_subscribe_date_is_skipped_not_crashed(self):
        bad = {"email": "bad@example.com", "subscribed_at": "sometime", "state": "ALL"}
        self.assertEqual(self.due([bad, sub("ok@example.com", 10)]), ["ok@example.com"])

    def test_oldest_subscriber_first(self):
        subscribers = [sub("b@example.com", 10), sub("a@example.com", 40),
                       sub("c@example.com", 8)]
        self.assertEqual(self.due(subscribers),
                         ["a@example.com", "b@example.com", "c@example.com"])


class DripGuardTest(unittest.TestCase):
    """The drip must send nothing until Benedict has approved the copy, and must
    never send more than MAX_PER_RUN in one go."""

    def setUp(self):
        self.calls = []
        self.saved = []
        self._orig = (intro.load_subscribers, intro.load_sends_log,
                      intro.save_sends_log, intro.send_email,
                      intro.get_resend_api_key, intro.get_unsubscribe_secret,
                      intro.ENABLED_FLAG)
        intro.load_sends_log = lambda path: {}
        intro.save_sends_log = lambda path, log: self.saved.append(dict(log))
        intro.get_resend_api_key = lambda: "key"
        intro.get_unsubscribe_secret = lambda: "s" * 64
        intro.send_email = lambda key, to, subj, html, text=None: (
            self.calls.append(to) or True)

    def tearDown(self):
        (intro.load_subscribers, intro.load_sends_log, intro.save_sends_log,
         intro.send_email, intro.get_resend_api_key,
         intro.get_unsubscribe_secret, intro.ENABLED_FLAG) = self._orig

    def test_sends_nothing_when_not_enabled(self):
        intro.load_subscribers = lambda: [sub("waiting@example.com", 30)]
        intro.ENABLED_FLAG = Path("/nonexistent/treesmith-intro-enabled")
        intro.run_drip(now=NOW)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.saved, [])

    def test_dry_run_sends_nothing_even_when_enabled(self):
        intro.load_subscribers = lambda: [sub("waiting@example.com", 30)]
        intro.ENABLED_FLAG = REPO_ROOT / "tests" / "test_treesmith_intro.py"
        intro.run_drip(dry_run=True, now=NOW)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.saved, [])

    def test_enabled_run_sends_and_records_each_send(self):
        intro.load_subscribers = lambda: [sub("a@example.com", 30),
                                          sub("b@example.com", 20)]
        intro.ENABLED_FLAG = REPO_ROOT / "tests" / "test_treesmith_intro.py"
        intro.run_drip(now=NOW)
        self.assertEqual(self.calls, ["a@example.com", "b@example.com"])
        # Logged after each send, not once at the end: a crash mid-run must not
        # re-send to whoever already got it.
        self.assertEqual(len(self.saved), 2)
        self.assertEqual(set(self.saved[-1]), {"a@example.com", "b@example.com"})

    def test_run_is_capped(self):
        intro.load_subscribers = lambda: [
            sub(f"s{i}@example.com", 30) for i in range(intro.MAX_PER_RUN + 5)]
        intro.ENABLED_FLAG = REPO_ROOT / "tests" / "test_treesmith_intro.py"
        intro.run_drip(now=NOW)
        self.assertEqual(len(self.calls), intro.MAX_PER_RUN)

    def test_test_mode_records_nothing(self):
        intro.load_subscribers = lambda: []
        intro.run_test("b@bjnoel.com")
        self.assertEqual(self.calls, ["b@bjnoel.com"])
        self.assertEqual(self.saved, [])


class CopyTest(unittest.TestCase):
    def setUp(self):
        self.html = intro.build_html()
        self.text = intro.build_text()

    def test_pro_is_never_called_a_subscription(self):
        for body in (self.html, self.text):
            # Collapsed whitespace: the plain-text version wraps mid-phrase.
            lowered = " ".join(body.lower().split())
            self.assertIn("one-time purchase, not a subscription", lowered)
            self.assertNotIn("pro subscription", lowered)
            self.assertNotIn("subscribe to pro", lowered)

    def test_cloud_backup_is_not_listed_as_a_pro_feature(self):
        # Cloud backup is a separate yearly subscription. The safest copy simply
        # does not mention it; if it is ever added it must not sit inside the
        # sentence describing what Pro unlocks.
        for body in (self.html, self.text):
            self.assertNotIn("cloud backup", body.lower())

    def test_correct_app_store_listing_and_au_storefront(self):
        # The original DAL-173 draft carried id6743767587, which is not our app.
        for body in (self.html, self.text):
            self.assertIn("id6761506742", body)
            self.assertNotIn("id6743767587", body)
            self.assertIn("apps.apple.com/au/", body)
            self.assertNotIn("apps.apple.com/us/", body)

    def test_android_is_not_described_as_beta(self):
        for body in (self.html, self.text):
            self.assertIn("play.google.com/store/apps/details?id=app.treesmith", body)
            self.assertNotIn("beta", body.lower())

    def test_landing_link_is_attributable(self):
        # DEC-239: every Treesmith surface carries a distinct utm_content so the
        # funnel audit can tell them apart.
        for body in (self.html, self.text):
            self.assertIn("utm_content=intro_email", body)
            self.assertIn("utm_campaign=treesmith_intro", body)

    def test_no_em_dashes(self):
        for body in (self.html, self.text, intro.SUBJECT):
            self.assertNotIn("\u2014", body)
            self.assertNotIn("\u2013", body)

    def test_no_unverifiable_usage_claims(self):
        # 0 ratings on both stores (DAL-225). We cannot claim users.
        for body in (self.html, self.text):
            lowered = body.lower()
            for claim in ("used by", "thousands of", "loved by", "join "):
                self.assertNotIn(claim, lowered)

    def test_free_tier_limit_matches_the_app(self):
        for body in (self.html, self.text):
            self.assertIn(f"up to {intro.FREE_PLANT_LIMIT} plants", body)

    def test_compliance_footer_is_injected(self):
        html = intro.inject_footer(self.html, "a@example.com", "tok", "WA",
                                   intro.SITE_URL)
        text = intro.inject_text_footer(self.text, "a@example.com", "tok", "WA",
                                        intro.SITE_URL)
        for body in (html, text):
            self.assertIn("unsubscribe.html?email=a%40example.com&token=tok", body)
            self.assertIn("/api/preferences?email=a%40example.com&token=tok", body)


if __name__ == "__main__":
    unittest.main()
