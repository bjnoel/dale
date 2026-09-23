"""
Regression tests: stocklib.retry covers the transient failures that actually
happen in front of shared hosting and CDNs, not only 429/503/509 and timeouts.

Before 2026-09-23 a 502 from a Cloudflare-fronted store, or a connection reset
mid-response, was fatal on the first attempt. Combined with the WooCommerce and
Squarespace paginators (which used to `break` on a failed page and publish what
they had), one reset connection could truncate a nursery's catalogue for a day.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import email.message
import http.client
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib import retry  # noqa: E402

URL = "https://example.test/products.json?page=1"


def _http_error(code):
    return urllib.error.HTTPError(URL, code, "error", email.message.Message(), None)


class _Resp:
    def __init__(self, body=b"ok", exc=None):
        self._body, self._exc = body, exc

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        if self._exc:
            raise self._exc
        return self._body


class _Opener:
    """Raises (or returns a response that raises on read) for each queued item."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        o = self.outcomes.pop(0)
        if isinstance(o, _Resp):
            return o
        raise o


class _Health:
    def __init__(self):
        self.http, self.errors = [], []

    def note_http_error(self, code, url=""):
        self.http.append(code)

    def note_error(self, msg):
        self.errors.append(msg)


def _req():
    return urllib.request.Request(URL)


class TransientClassesAreRetried(unittest.TestCase):
    def _assert_retried(self, first_failure):
        opener = _Opener(first_failure, _Resp(b"body"))
        sleeps = []
        out = retry.request_with_retry(_req(), _opener=opener, _sleep=sleeps.append)
        self.assertEqual(out, b"body")
        self.assertEqual(opener.calls, 2)
        self.assertEqual(len(sleeps), 1)

    def test_gateway_errors_are_retried(self):
        for code in (500, 502, 504, 520, 521, 522, 523, 524):
            with self.subTest(code=code):
                self._assert_retried(_http_error(code))

    def test_connection_reset_is_retried(self):
        self._assert_retried(ConnectionResetError(104, "Connection reset by peer"))

    def test_remote_disconnected_is_retried(self):
        self._assert_retried(http.client.RemoteDisconnected("closed"))

    def test_incomplete_read_during_body_is_retried(self):
        self._assert_retried(_Resp(exc=http.client.IncompleteRead(b"partial")))

    def test_dns_or_refused_urlerror_is_retried(self):
        self._assert_retried(urllib.error.URLError(ConnectionRefusedError(111, "refused")))


class FatalClassesAreNot(unittest.TestCase):
    def test_client_errors_fail_fast(self):
        for code in (401, 403, 404, 410):
            with self.subTest(code=code):
                opener = _Opener(_http_error(code))
                health = _Health()
                out = retry.request_with_retry(_req(), health=health,
                                               _opener=opener, _sleep=lambda s: None)
                self.assertIsNone(out)
                self.assertEqual(opener.calls, 1)
                self.assertEqual(health.http, [code])

    def test_non_network_bug_is_not_retried(self):
        opener = _Opener(ValueError("bad request object"))
        health = _Health()
        out = retry.request_with_retry(_req(), health=health,
                                       _opener=opener, _sleep=lambda s: None)
        self.assertIsNone(out)
        self.assertEqual(opener.calls, 1)
        self.assertEqual(len(health.errors), 1)

    def test_exhausted_transient_records_health_once(self):
        opener = _Opener(*[ConnectionResetError("reset")] * (retry.MAX_RETRIES + 1))
        health = _Health()
        out = retry.request_with_retry(_req(), health=health,
                                       _opener=opener, _sleep=lambda s: None)
        self.assertIsNone(out)
        self.assertEqual(opener.calls, retry.MAX_RETRIES + 1)
        self.assertEqual(len(health.errors), 1)


if __name__ == "__main__":
    unittest.main()
