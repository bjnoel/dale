"""
Regression tests for shopify_scraper retry/backoff (2026-07-19 Shopify 503 blip).

On 2026-07-19 every Shopify store 503'd instantly in the same run (a
platform-side blip), and fetch_json had no retry, so 10 nurseries lost their
snapshot for the day. fetch_json now goes through stocklib.retry, shared with
ecwid_scraper (whose backoff maths test_ecwid_retry.py already pins). These
tests pin the Shopify wiring: transient 503s are retried, fatal codes are not,
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

import shopify_scraper as ss  # noqa: E402
from stocklib import retry  # noqa: E402

URL = "https://www.diggers.com.au/products.json?limit=250&page=1"


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


PAGE = json.dumps({"products": [{"id": 1, "title": "Loquat"}]})


class FetchJsonRetryTest(unittest.TestCase):
    def test_retries_503_then_succeeds(self):
        sleeps = []
        opener = _FakeOpener([_http_error(503), _http_error(503), PAGE])
        data = ss.fetch_json(URL, _opener=opener, _sleep=sleeps.append)
        self.assertEqual(data["products"][0]["title"], "Loquat")
        self.assertEqual(opener.calls, 3)
        self.assertEqual(len(sleeps), 2)

    def test_gives_up_after_max_retries_and_records_health(self):
        sleeps = []
        health = _FakeHealth()
        opener = _FakeOpener([_http_error(503)] * (retry.MAX_RETRIES + 1))
        data = ss.fetch_json(URL, health=health,
                             _opener=opener, _sleep=sleeps.append)
        self.assertIsNone(data)
        self.assertEqual(opener.calls, retry.MAX_RETRIES + 1)
        self.assertEqual(len(sleeps), retry.MAX_RETRIES)
        self.assertEqual(health.http_errors, [(503, URL)])

    def test_retries_timeout_then_succeeds(self):
        sleeps = []
        opener = _FakeOpener([TimeoutError("The read operation timed out"), PAGE])
        data = ss.fetch_json(URL, _opener=opener, _sleep=sleeps.append)
        self.assertEqual(len(data["products"]), 1)
        self.assertEqual(len(sleeps), 1)

    def test_does_not_retry_404(self):
        sleeps = []
        health = _FakeHealth()
        opener = _FakeOpener([_http_error(404), PAGE])
        data = ss.fetch_json(URL, health=health,
                             _opener=opener, _sleep=sleeps.append)
        self.assertIsNone(data)
        self.assertEqual(opener.calls, 1)
        self.assertEqual(sleeps, [])
        self.assertEqual(health.http_errors, [(404, URL)])

    def test_bad_json_records_health(self):
        health = _FakeHealth()
        opener = _FakeOpener(["not json"])
        data = ss.fetch_json(URL, health=health,
                             _opener=opener, _sleep=lambda s: None)
        self.assertIsNone(data)
        self.assertEqual(len(health.errors), 1)


class TruncatedSnapshotAbortTest(unittest.TestCase):
    """A page failing mid-pagination must kill the whole snapshot, not save a
    truncated one (fruitopia saved 250 of ~1100 products on 2026-07-19)."""

    def _run_with_pages(self, pages):
        orig = ss.fetch_json
        it = iter(pages)
        ss.fetch_json = lambda url, health=None: next(it)
        try:
            return ss.scrape_shopify(
                "fruitopia", {"name": "Fruitopia", "domain": "x.example"},
                health=self._health)
        finally:
            ss.fetch_json = orig

    def setUp(self):
        self._health = _FakeHealth()
        self._orig_delay = ss.REQUEST_DELAY
        ss.REQUEST_DELAY = 0

    def tearDown(self):
        ss.REQUEST_DELAY = self._orig_delay

    def test_mid_pagination_failure_returns_empty(self):
        page1 = {"products": [{"id": n} for n in range(250)]}
        products = self._run_with_pages([page1, None])
        self.assertEqual(products, [])
        self.assertEqual(len(self._health.errors), 1)
        self.assertIn("aborted", self._health.errors[0])

    def test_clean_end_of_pagination_keeps_products(self):
        page1 = {"products": [{"id": n} for n in range(3)]}
        products = self._run_with_pages([page1, {"products": []}])
        self.assertEqual(len(products), 3)
        self.assertEqual(self._health.errors, [])


if __name__ == "__main__":
    unittest.main()
