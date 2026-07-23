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
