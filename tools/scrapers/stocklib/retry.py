"""Shared retry/backoff for scraper HTTP fetches.

Extracted from ecwid_scraper (Primal Fruits 429/timeout fix, 2026-06-18) after
the 2026-07-19 Shopify-wide 503 blip took out 10 nursery snapshots in one run:
every Shopify store 503'd once at the same moment and the scrapers had no
retry, so a transient platform hiccup became a missing snapshot day.

Retries HTTP 429/503 and read/connect timeouts with exponential backoff,
honouring a seconds-form Retry-After header. Import from here; do not copy
these into a scraper (tests/test_no_forking.py guards the constants).
"""
import socket
import time
import urllib.error
import urllib.request

RETRYABLE_HTTP = {429, 503}
MAX_RETRIES = 3        # extra attempts after the first try
BACKOFF_BASE = 2.0     # seconds; doubles each retry
BACKOFF_CAP = 30.0     # never wait longer than this between retries


def retry_after_seconds(headers):
    """Parse a Retry-After header in seconds form. Returns float or None.

    The HTTP-date form is ignored (we fall back to exponential backoff)."""
    if not headers:
        return None
    val = headers.get("Retry-After")
    if not val:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def backoff_delay(attempt, retry_after=None):
    """Seconds to wait before retry ``attempt`` (1-based).

    Exponential (BACKOFF_BASE * 2^(attempt-1)), but never shorter than a
    server-supplied Retry-After and never longer than BACKOFF_CAP."""
    base = BACKOFF_BASE * (2 ** (attempt - 1))
    if retry_after is not None:
        base = max(base, retry_after)
    return min(base, BACKOFF_CAP)


def is_timeout(exc):
    """True if ``exc`` is (or wraps) a socket/read timeout."""
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, urllib.error.URLError) and isinstance(
            exc.reason, (TimeoutError, socket.timeout)):
        return True
    return False


def request_with_retry(req, timeout=20, health=None, *, _opener=None, _sleep=time.sleep):
    """Send a urllib Request, retrying transient failures, and return the raw
    response bytes (or None once retries are exhausted / on a fatal error).

    Retries HTTP 429/503 and timeouts up to MAX_RETRIES times with exponential
    backoff (honouring Retry-After). ``_opener``/``_sleep`` are injection seams
    for tests."""
    opener = _opener or urllib.request.urlopen
    url = req.full_url
    for attempt in range(MAX_RETRIES + 1):
        try:
            with opener(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_HTTP and attempt < MAX_RETRIES:
                delay = backoff_delay(attempt + 1, retry_after_seconds(e.headers))
                print(f"  HTTP {e.code} on {url}; retry {attempt + 1}/{MAX_RETRIES} in {delay:.0f}s")
                _sleep(delay)
                continue
            print(f"  HTTP {e.code} fetching {url}")
            if health:
                health.note_http_error(e.code, url)
            return None
        except Exception as e:
            if is_timeout(e) and attempt < MAX_RETRIES:
                delay = backoff_delay(attempt + 1)
                print(f"  timeout on {url}; retry {attempt + 1}/{MAX_RETRIES} in {delay:.0f}s")
                _sleep(delay)
                continue
            print(f"  Error fetching {url}: {e}")
            if health:
                health.note_error(str(e))
            return None
    return None
