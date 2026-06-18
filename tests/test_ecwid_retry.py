"""
Regression tests for ecwid_scraper retry/backoff (Primal Fruits 429 + timeout
fix, 2026-06-18).

Primal Fruits' Ecwid store rate-limits us with HTTP 429 and stalls connections
("read operation timed out"). Before this fix fetch_page had no retry, so every
429'd or timed-out product silently dropped out of the snapshot. These tests pin
the backoff maths and the retry loop so that regression can't come back.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import email.message
import sys
import unittest
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import ecwid_scraper as es  # noqa: E402


def _http_error(code, retry_after=None):
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://primalfruits.com.au/products/x",
                                  code, "error", hdrs, None)


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body.encode("utf-8")


class _FakeOpener:
    """Replays a list of actions: an Exception is raised, a str is returned."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return _FakeResp(action)


class _FakeHealth:
    def __init__(self):
        self.http_errors = []
        self.errors = []

    def note_http_error(self, code, url):
        self.http_errors.append((code, url))

    def note_error(self, msg):
        self.errors.append(msg)


class BackoffMathTest(unittest.TestCase):
    def test_exponential_growth(self):
        # BACKOFF_BASE * 2^(attempt-1): 2, 4, 8 ...
        self.assertEqual(es._backoff_delay(1), 2.0)
        self.assertEqual(es._backoff_delay(2), 4.0)
        self.assertEqual(es._backoff_delay(3), 8.0)

    def test_capped(self):
        self.assertEqual(es._backoff_delay(10), es.BACKOFF_CAP)

    def test_honours_retry_after_when_larger(self):
        self.assertEqual(es._backoff_delay(1, retry_after=5), 5.0)

    def test_ignores_retry_after_when_smaller(self):
        self.assertEqual(es._backoff_delay(3, retry_after=1), 8.0)


class RetryAfterParseTest(unittest.TestCase):
    def test_seconds_form(self):
        h = email.message.Message()
        h["Retry-After"] = "12"
        self.assertEqual(es._retry_after_seconds(h), 12.0)

    def test_missing(self):
        self.assertIsNone(es._retry_after_seconds(email.message.Message()))
        self.assertIsNone(es._retry_after_seconds(None))

    def test_http_date_form_ignored(self):
        h = email.message.Message()
        h["Retry-After"] = "Wed, 21 Oct 2026 07:28:00 GMT"
        self.assertIsNone(es._retry_after_seconds(h))


class FetchRetryTest(unittest.TestCase):
    def test_retries_429_then_succeeds(self):
        sleeps = []
        opener = _FakeOpener([_http_error(429), _http_error(429), "<html>ok</html>"])
        body = es.fetch_page("https://primalfruits.com.au/products/x",
                             _opener=opener, _sleep=sleeps.append)
        self.assertEqual(body, "<html>ok</html>")
        self.assertEqual(opener.calls, 3)
        self.assertEqual(len(sleeps), 2)

    def test_gives_up_after_max_retries_and_records_health(self):
        sleeps = []
        health = _FakeHealth()
        opener = _FakeOpener([_http_error(429)] * (es.MAX_RETRIES + 1))
        body = es.fetch_page("https://primalfruits.com.au/products/x",
                             health=health, _opener=opener, _sleep=sleeps.append)
        self.assertIsNone(body)
        self.assertEqual(opener.calls, es.MAX_RETRIES + 1)
        self.assertEqual(len(sleeps), es.MAX_RETRIES)
        self.assertEqual(health.http_errors, [(429, "https://primalfruits.com.au/products/x")])

    def test_retry_after_header_sets_sleep(self):
        sleeps = []
        opener = _FakeOpener([_http_error(429, retry_after=7), "<html>ok</html>"])
        es.fetch_page("https://primalfruits.com.au/products/x",
                      _opener=opener, _sleep=sleeps.append)
        self.assertEqual(sleeps, [7.0])

    def test_retries_timeout_then_succeeds(self):
        sleeps = []
        opener = _FakeOpener([TimeoutError("The read operation timed out"),
                              "<html>ok</html>"])
        body = es.fetch_page("https://primalfruits.com.au/products/x",
                             _opener=opener, _sleep=sleeps.append)
        self.assertEqual(body, "<html>ok</html>")
        self.assertEqual(len(sleeps), 1)

    def test_does_not_retry_404(self):
        sleeps = []
        health = _FakeHealth()
        opener = _FakeOpener([_http_error(404), "<html>never</html>"])
        body = es.fetch_page("https://primalfruits.com.au/products/x",
                             health=health, _opener=opener, _sleep=sleeps.append)
        self.assertIsNone(body)
        self.assertEqual(opener.calls, 1)
        self.assertEqual(sleeps, [])
        self.assertEqual(health.http_errors, [(404, "https://primalfruits.com.au/products/x")])


if __name__ == "__main__":
    unittest.main()
