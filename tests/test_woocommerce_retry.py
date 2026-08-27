"""
Regression tests for woocommerce_scraper retry/backoff.

woocommerce_scraper.fetch_json was a private copy of the fetch with no retry
at all. It reproduced stocklib.retry's log lines and health calls exactly, so
the scrape log looked identical to a scraper that had tried and given up, and
the durations in data/scraper-health were the only tell:

    2026-08-21  plantnet  HTTP 503  1.62s     <- 503 IS retryable
    2026-08-26  engalls   HTTP 509  0.88s
    2026-08-27  rayners   HTTP 429  1.31s     <- 429 IS retryable

Three retries cannot happen in under 2s (BACKOFF_BASE alone is 2.0), so none
of those was retried. Each cost a nursery its snapshot for the day.

These tests pin the wiring: transient codes are retried, fatal ones are not,
and health records the failure once retries are exhausted.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import email.message
import json
import sys
import unittest
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import woocommerce_scraper as wc  # noqa: E402
from stocklib import retry  # noqa: E402

URL = "https://www.engalls.com.au/wp-json/wc/store/v1/products?per_page=100&page=1"


def _http_error(code, retry_after=None):
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError(URL, code, "error", hdrs, None)


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


PAGE = json.dumps([{"id": 1, "name": "Yuzu", "prices": {"price": "6500"}}])


class RetryableCodeTest(unittest.TestCase):
    """509 is why this branch exists: Engall's runs LiteSpeed, and 509
    (Bandwidth Limit Exceeded) is the shared-hosting bandwidth cap. It is not
    in any RFC, so it was never on the list."""

    def test_509_is_retryable(self):
        self.assertIn(509, retry.RETRYABLE_HTTP)

    def test_429_and_503_still_retryable(self):
        self.assertIn(429, retry.RETRYABLE_HTTP)
        self.assertIn(503, retry.RETRYABLE_HTTP)

    def test_client_errors_are_not_retryable(self):
        # 400 is Garden Express post-Shopify-migration: retrying it every night
        # would be three extra requests at a store that has moved.
        for code in (400, 403, 404, 410, 500):
            self.assertNotIn(code, retry.RETRYABLE_HTTP)


class FetchJsonRetryTest(unittest.TestCase):
    def test_retries_509_then_succeeds(self):
        """The engalls 2026-08-26 case. One 509, then the site is fine."""
        sleeps = []
        opener = _FakeOpener([_http_error(509), PAGE])
        data = wc.fetch_json(URL, _opener=opener, _sleep=sleeps.append)
        self.assertEqual(data[0]["name"], "Yuzu")
        self.assertEqual(opener.calls, 2)
        self.assertEqual(len(sleeps), 1)

    def test_retries_429_then_succeeds(self):
        """The rayners 2026-08-27 case."""
        sleeps = []
        opener = _FakeOpener([_http_error(429), _http_error(429), PAGE])
        data = wc.fetch_json(URL, _opener=opener, _sleep=sleeps.append)
        self.assertEqual(len(data), 1)
        self.assertEqual(opener.calls, 3)
        self.assertEqual(len(sleeps), 2)

    def test_retries_503_then_succeeds(self):
        """The plantnet 2026-08-21 case."""
        sleeps = []
        opener = _FakeOpener([_http_error(503), PAGE])
        data = wc.fetch_json(URL, _opener=opener, _sleep=sleeps.append)
        self.assertEqual(len(data), 1)
        self.assertEqual(opener.calls, 2)

    def test_honours_retry_after(self):
        sleeps = []
        opener = _FakeOpener([_http_error(509, retry_after=25), PAGE])
        wc.fetch_json(URL, _opener=opener, _sleep=sleeps.append)
        self.assertEqual(sleeps, [25.0])

    def test_gives_up_after_max_retries_and_records_health_once(self):
        sleeps = []
        health = _FakeHealth()
        opener = _FakeOpener([_http_error(509)] * (retry.MAX_RETRIES + 1))
        data = wc.fetch_json(URL, health=health,
                             _opener=opener, _sleep=sleeps.append)
        self.assertIsNone(data)
        self.assertEqual(opener.calls, retry.MAX_RETRIES + 1)
        self.assertEqual(len(sleeps), retry.MAX_RETRIES)
        self.assertEqual(health.http_errors, [(509, URL)])

    def test_retries_timeout_then_succeeds(self):
        sleeps = []
        opener = _FakeOpener([TimeoutError("The read operation timed out"), PAGE])
        data = wc.fetch_json(URL, _opener=opener, _sleep=sleeps.append)
        self.assertEqual(len(data), 1)
        self.assertEqual(len(sleeps), 1)

    def test_does_not_retry_400(self):
        """Garden Express 400s after moving to Shopify. Fatal, not transient."""
        sleeps = []
        health = _FakeHealth()
        opener = _FakeOpener([_http_error(400), PAGE])
        data = wc.fetch_json(URL, health=health,
                             _opener=opener, _sleep=sleeps.append)
        self.assertIsNone(data)
        self.assertEqual(opener.calls, 1)
        self.assertEqual(sleeps, [])
        self.assertEqual(health.http_errors, [(400, URL)])

    def test_bad_json_records_health(self):
        health = _FakeHealth()
        opener = _FakeOpener(["not json"])
        data = wc.fetch_json(URL, health=health,
                             _opener=opener, _sleep=lambda s: None)
        self.assertIsNone(data)
        self.assertEqual(len(health.errors), 1)


if __name__ == "__main__":
    unittest.main()
