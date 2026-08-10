"""
Tests for stocklib.mailer — shared email plumbing (DEC-232 follow-up).

Regression: get_resend_api_key, get_unsubscribe_secret,
make_unsubscribe_token, load_subscribers, load/save_sends_log and send_email
existed as 4-7 hand-synced copies across the send_* scripts,
subscribe_server.py and the detect_* alerters. make_unsubscribe_token is the
critical one: a drifted copy means every unsubscribe/preferences link that
sender emits stops verifying against the subscribe server.
"""
import hashlib
import hmac
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib.mailer import make_unsubscribe_token


class MakeUnsubscribeTokenTest(unittest.TestCase):
    def test_token_format_pinned(self):
        # The exact token format every historical email link carries:
        # HMAC-SHA256(secret, lowercased email), hex, first 32 chars.
        # Changing this breaks every unsubscribe link already in inboxes.
        secret, email = "s3cret", "Person@Example.COM"
        expected = hmac.new(
            secret.encode(), email.lower().encode(), hashlib.sha256
        ).hexdigest()[:32]
        self.assertEqual(make_unsubscribe_token(email, secret), expected)
        self.assertEqual(len(expected), 32)

    def test_email_case_insensitive(self):
        self.assertEqual(make_unsubscribe_token("a@b.com", "k"),
                         make_unsubscribe_token("A@B.COM", "k"))

    def test_empty_secret_fails_closed(self):
        # Never mint a token from an empty key (the subscribe server's
        # fail-closed behaviour, now shared by every sender).
        self.assertEqual(make_unsubscribe_token("a@b.com", ""), "")

    def test_all_senders_share_the_token_function(self):
        import send_digest
        import send_species_alerts
        import send_variety_alerts
        import send_weekly_digest
        import send_welcome_email
        import subscribe_server
        for mod in (send_digest, send_species_alerts, send_variety_alerts,
                    send_weekly_digest, send_welcome_email, subscribe_server):
            self.assertIs(mod.make_unsubscribe_token, make_unsubscribe_token,
                          mod.__name__)


if __name__ == "__main__":
    unittest.main()


class ReplyToTest(unittest.TestCase):
    """Every subscriber-facing email must carry a working Reply-To (DAL-243).

    For the whole life of the list we sent From `alerts@mail.treestock.com.au`,
    a subdomain with no MX and no A record, and set no Reply-To at all. So every
    reply to every email ever sent hard-bounced, while the welcome email and the
    Treesmith intro both told people to "just reply to this email". Nothing
    caught it because nothing looked at the reply path. These tests are that
    look.
    """

    def test_reply_to_is_not_the_unroutable_send_domain(self):
        """The bug in one assertion: replying must not go back to the MX-less
        subdomain we send from."""
        from stocklib.mailer import FROM_EMAIL, REPLY_TO_EMAIL
        send_domain = FROM_EMAIL.split("@", 1)[1]
        reply_domain = REPLY_TO_EMAIL.split("@", 1)[1]
        self.assertNotEqual(reply_domain, send_domain)
        self.assertNotIn("mail.treestock.com.au", REPLY_TO_EMAIL)

    def test_reply_to_is_on_the_apex_which_has_mx(self):
        from stocklib.mailer import REPLY_TO_EMAIL
        self.assertTrue(REPLY_TO_EMAIL.endswith("@treestock.com.au"),
                        f"{REPLY_TO_EMAIL} is not on the apex domain")

    def test_send_email_payload_sets_reply_to(self):
        """Capture the payload stocklib's sender actually builds."""
        import json
        import urllib.request
        from unittest import mock
        from stocklib import mailer

        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"id": "fake"}'

        def fake_urlopen(req, timeout=None):
            captured["payload"] = json.loads(req.data.decode())
            return FakeResp()

        with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            mailer.send_email("key", "a@b.com", "subj", "<p>hi</p>")

        self.assertEqual(captured["payload"].get("reply_to"),
                         mailer.REPLY_TO_EMAIL)

    def test_every_treestock_sender_sets_reply_to(self):
        """The three send_*.py scripts build their own payloads rather than
        calling mailer.send_email, so each one has to set it. This is the test
        that would have caught the original bug across all four senders."""
        senders = ["send_confirmation_email.py", "send_manage_link_email.py",
                   "send_welcome_email.py"]
        scrapers = REPO_ROOT / "tools" / "scrapers"
        for name in senders:
            with self.subTest(sender=name):
                src = (scrapers / name).read_text()
                self.assertIn('"reply_to"', src,
                              f"{name} builds an email payload with no reply_to")

    def test_senders_import_the_identity_rather_than_redefining_it(self):
        """They each had their own FROM_EMAIL/FROM_NAME copy, which is why this
        fix had to be made in four places. test_no_forking guards it now too."""
        scrapers = REPO_ROOT / "tools" / "scrapers"
        for name in ["send_confirmation_email.py", "send_manage_link_email.py",
                     "send_welcome_email.py"]:
            with self.subTest(sender=name):
                src = (scrapers / name).read_text()
                self.assertNotIn('\nFROM_EMAIL = "', src)
                self.assertIn("REPLY_TO_EMAIL", src)
