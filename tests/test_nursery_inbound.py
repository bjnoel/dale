"""
Tests for the Resend inbound webhook that logs nursery touches (DAL-273).

The signature tests matter most. This endpoint is deliberately NOT behind
Cloudflare Access, because Resend has to reach it unauthenticated, so the Svix
HMAC is the only thing standing between the nursery register and anyone who
guesses the URL. DEC-265 is the reason this route exists at all, and its lesson
was that a boundary asserted is not a boundary tested.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import base64
import hashlib
import hmac
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import nursery_inbound as ni

SECRET = "whsec_" + base64.b64encode(b"a-test-signing-key-32-bytes-long").decode()

REGISTER = {"nurseries": [
    {"key": "daleys", "name": "Daleys", "domain": "daleysfruit.com.au",
     "status": "warm"},
    {"key": "ross-creek", "name": "Ross Creek", "domain": "rosscreektropicals.com.au",
     "status": "contacted"},
    {"key": "nodomain", "name": "No Domain", "status": "not_contacted"},
]}


def sign(body, svix_id="msg_1", ts=None, secret=SECRET):
    ts = str(int(time.time()) if ts is None else ts)
    if isinstance(body, str):
        body = body.encode()
    key = base64.b64decode(secret.split("_", 1)[1])
    signed = svix_id.encode() + b"." + ts.encode() + b"." + body
    sig = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {"svix-id": svix_id, "svix-timestamp": ts, "svix-signature": f"v1,{sig}"}


def payload(from_="benedict@bjnoel.com", to=("orders@daleysfruit.com.au",),
            received_for=("nursery@veliamsal.resend.app",), subject="Scion wood",
            email_id="e_123", created_at="2026-08-06T01:00:00.000Z", cc=()):
    return {"type": "email.received", "created_at": created_at, "data": {
        "email_id": email_id, "created_at": created_at, "from": from_,
        "to": list(to), "cc": list(cc), "bcc": [],
        "received_for": list(received_for),
        "message_id": "<abc@mail>", "subject": subject, "attachments": []}}


class TestSignature(unittest.TestCase):
    def test_valid_signature_passes(self):
        body = json.dumps(payload())
        h = sign(body)
        self.assertTrue(ni.verify_signature(
            SECRET, h["svix-id"], h["svix-timestamp"], body, h["svix-signature"]))

    def test_tampered_body_fails(self):
        body = json.dumps(payload())
        h = sign(body)
        with self.assertRaises(ni.InboundError):
            ni.verify_signature(SECRET, h["svix-id"], h["svix-timestamp"],
                                body + " ", h["svix-signature"])

    def test_wrong_secret_fails(self):
        body = json.dumps(payload())
        h = sign(body, secret="whsec_" + base64.b64encode(b"different-key-here").decode())
        with self.assertRaises(ni.InboundError):
            ni.verify_signature(SECRET, h["svix-id"], h["svix-timestamp"],
                                body, h["svix-signature"])

    def test_replayed_old_timestamp_fails(self):
        """Svix's replay guard: a captured request must not work forever."""
        body = json.dumps(payload())
        old = int(time.time()) - (ni.TIMESTAMP_TOLERANCE_S + 60)
        h = sign(body, ts=old)
        with self.assertRaises(ni.InboundError) as cm:
            ni.verify_signature(SECRET, h["svix-id"], h["svix-timestamp"],
                                body, h["svix-signature"])
        self.assertIn("tolerance", str(cm.exception))

    def test_future_timestamp_fails(self):
        body = json.dumps(payload())
        h = sign(body, ts=int(time.time()) + ni.TIMESTAMP_TOLERANCE_S + 60)
        with self.assertRaises(ni.InboundError):
            ni.verify_signature(SECRET, h["svix-id"], h["svix-timestamp"],
                                body, h["svix-signature"])

    def test_signature_is_bound_to_the_svix_id(self):
        """The id is part of the signed string, so swapping it must fail."""
        body = json.dumps(payload())
        h = sign(body, svix_id="msg_1")
        with self.assertRaises(ni.InboundError):
            ni.verify_signature(SECRET, "msg_2", h["svix-timestamp"],
                                body, h["svix-signature"])

    def test_multiple_versions_one_valid_passes(self):
        """Svix sends several signatures during a secret rotation."""
        body = json.dumps(payload())
        h = sign(body)
        header = f"v1,ZmFrZQ== {h['svix-signature']}"
        self.assertTrue(ni.verify_signature(
            SECRET, h["svix-id"], h["svix-timestamp"], body, header))

    def test_non_v1_versions_are_ignored(self):
        body = json.dumps(payload())
        h = sign(body)
        good = h["svix-signature"].split(",", 1)[1]
        with self.assertRaises(ni.InboundError):
            ni.verify_signature(SECRET, h["svix-id"], h["svix-timestamp"],
                                body, f"v2,{good}")

    def test_missing_headers_fail(self):
        with self.assertRaises(ni.InboundError):
            ni.verify_signature(SECRET, None, None, b"{}", None)

    def test_no_secret_configured_fails_closed(self):
        """An unconfigured secret must reject, never accept."""
        body = json.dumps(payload())
        h = sign(body)
        with self.assertRaises(ni.InboundError):
            ni.verify_signature(None, h["svix-id"], h["svix-timestamp"],
                                body, h["svix-signature"])

    def test_bytes_and_str_bodies_agree(self):
        body = json.dumps(payload())
        h = sign(body)
        self.assertTrue(ni.verify_signature(
            SECRET, h["svix-id"], h["svix-timestamp"], body.encode(),
            h["svix-signature"]))


class TestMatchNursery(unittest.TestCase):
    def test_exact_domain(self):
        self.assertEqual(ni.match_nursery("orders@daleysfruit.com.au", REGISTER),
                         "daleys")

    def test_subdomain_matches(self):
        self.assertEqual(
            ni.match_nursery("no-reply@mail.daleysfruit.com.au", REGISTER),
            "daleys")

    def test_unrelated_domain_does_not_match(self):
        self.assertIsNone(ni.match_nursery("someone@gmail.com", REGISTER))

    def test_suffix_confusion_does_not_match(self):
        """notdaleysfruit.com.au must not match daleysfruit.com.au."""
        self.assertIsNone(
            ni.match_nursery("a@notdaleysfruit.com.au", REGISTER))

    def test_nursery_without_a_domain_is_skipped(self):
        self.assertIsNone(ni.match_nursery("a@nodomain.com", REGISTER))

    def test_case_insensitive(self):
        self.assertEqual(ni.match_nursery("Orders@DaleysFruit.COM.AU", REGISTER),
                         "daleys")


class TestBuildRecord(unittest.TestCase):
    def test_outbound_to_a_nursery(self):
        rec = ni.build_record(payload(), REGISTER)
        self.assertEqual(rec["nursery"], "daleys")
        self.assertEqual(rec["direction"], "out")
        self.assertEqual(rec["by"], "benedict")
        self.assertEqual(rec["date"], "2026-08-06")
        self.assertEqual(rec["summary"], "Scion wood")
        self.assertEqual(rec["evidence"], "resend:e_123")

    def test_inbound_from_a_nursery(self):
        """A forwarded reply is direction 'in', read from the sender, not from
        the fact that Benedict was the one who BCC'd it."""
        rec = ni.build_record(
            payload(from_="correy@daleysfruit.com.au", to=("benedict@bjnoel.com",)),
            REGISTER)
        self.assertEqual(rec["direction"], "in")
        self.assertEqual(rec["by"], "daleys")

    def test_cc_counts_as_a_recipient(self):
        rec = ni.build_record(
            payload(to=("someone@example.com",),
                    cc=("sales@rosscreektropicals.com.au",)), REGISTER)
        self.assertEqual(rec["nursery"], "ross-creek")

    def test_display_name_form_is_parsed(self):
        rec = ni.build_record(
            payload(to=('"Daleys Orders" <orders@daleysfruit.com.au>',)), REGISTER)
        self.assertEqual(rec["nursery"], "daleys")

    def test_not_delivered_to_us_is_rejected(self):
        """Guards against anyone crafting a payload we would otherwise log."""
        with self.assertRaises(ni.InboundError) as cm:
            ni.build_record(payload(received_for=("someone@elsewhere.com",)),
                            REGISTER)
        self.assertIn("not delivered", str(cm.exception))

    def test_no_nursery_match_is_rejected(self):
        with self.assertRaises(ni.InboundError) as cm:
            ni.build_record(payload(to=("someone@gmail.com",)), REGISTER)
        self.assertIn("no nursery matched", str(cm.exception))

    def test_missing_subject_does_not_crash(self):
        rec = ni.build_record(payload(subject=None), REGISTER)
        self.assertEqual(rec["summary"], "(no subject)")

    def test_bad_created_at_falls_back_to_today(self):
        from datetime import datetime, timezone
        rec = ni.build_record(payload(created_at="not-a-date"), REGISTER)
        self.assertEqual(rec["date"],
                         datetime.now(timezone.utc).date().isoformat())

    def test_long_subject_is_truncated(self):
        rec = ni.build_record(payload(subject="x" * 500), REGISTER)
        self.assertLessEqual(len(rec["summary"]), 200)


class TestPersistence(unittest.TestCase):
    def _path(self):
        return str(Path(tempfile.mkdtemp()) / "nursery-inbound.jsonl")

    def test_append_then_duplicate_is_refused(self):
        """Resend retries until it gets a 2xx, so the same email arrives twice
        by design."""
        path = self._path()
        rec = ni.build_record(payload(), REGISTER)
        self.assertTrue(ni.append_record(rec, path))
        self.assertFalse(ni.append_record(rec, path))
        self.assertEqual(len(Path(path).read_text().strip().splitlines()), 1)

    def test_different_emails_both_land(self):
        path = self._path()
        ni.append_record(ni.build_record(payload(email_id="e_1"), REGISTER), path)
        ni.append_record(ni.build_record(payload(email_id="e_2"), REGISTER), path)
        self.assertEqual(len(Path(path).read_text().strip().splitlines()), 2)

    def test_corrupt_lines_do_not_break_dedup(self):
        path = self._path()
        Path(path).write_text("{not json\n")
        rec = ni.build_record(payload(), REGISTER)
        self.assertTrue(ni.append_record(rec, path))


class TestHandle(unittest.TestCase):
    """The full path, since that is what the HTTP route actually calls."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.register = self.tmp / "nursery-contacts.json"
        self.register.write_text(json.dumps(REGISTER))
        self.secret_file = self.tmp / "resend-inbound.env"
        self.secret_file.write_text(f"RESEND_INBOUND_SIGNING_SECRET={SECRET}\n")
        self.log = str(self.tmp / "inbound.jsonl")

    def _call(self, body, headers):
        return ni.handle(body, headers, str(self.register),
                         str(self.secret_file), self.log)

    def test_happy_path_logs_a_touch(self):
        body = json.dumps(payload())
        out = self._call(body, sign(body))
        self.assertIn("daleys", out)
        self.assertEqual(len(Path(self.log).read_text().strip().splitlines()), 1)

    def test_bad_signature_writes_nothing(self):
        body = json.dumps(payload())
        h = sign(body)
        h["svix-signature"] = "v1,AAAA"
        with self.assertRaises(ni.InboundError):
            self._call(body, h)
        self.assertFalse(Path(self.log).exists())

    def test_other_event_types_are_ignored(self):
        body = json.dumps({"type": "email.sent", "data": {}})
        out = self._call(body, sign(body))
        self.assertIn("ignored", out)

    def test_non_json_body_with_valid_signature_is_rejected(self):
        body = "not json at all"
        with self.assertRaises(ni.InboundError):
            self._call(body, sign(body))

    def test_missing_secret_file_fails_closed(self):
        body = json.dumps(payload())
        with self.assertRaises(ni.InboundError):
            ni.handle(body, sign(body), str(self.register),
                      str(self.tmp / "nope.env"), self.log)


if __name__ == "__main__":
    unittest.main()
