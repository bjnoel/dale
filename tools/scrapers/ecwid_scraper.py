#!/usr/bin/env python3
"""
Ecwid Nursery Stock Scraper (storefront API)

Reads products from the Ecwid storefront API (the same JSON the storefront SPA
fetches), not from product-page HTML.

Background: Ecwid stores used to server-render JSON-LD into every product page,
and this scraper parsed that. Around 2026-06-16 Primal Fruits' store stopped
server-rendering JSON-LD: every product page is now a bare JS SPA shell with zero
JSON-LD, so the old HTML scrape parsed 0 products (DEC-208 / DAL-205). The SPA
loads its catalogue from a regional storefront API:

    POST https://<region>-storefront-api.ecwid.com/storefront/api/v1/<storeId>/catalog
    body: {"categoryViewMode":"COLLAPSED","parentCategoryId":0,
           "pagination":{"offset":...,"limit":...}, "urlParams":{...}}

Requesting parentCategoryId 0 in COLLAPSED mode returns the whole catalogue flat
(products from every subcategory), paginated at max 200 per page;
``totalProductsCount`` is the reliable total (``hasMoreProducts`` is not). The
endpoint needs no auth, but the region host and a public token can rotate, so we
discover them at runtime from the store bootstrap script
(app.ecwid.com/script.js?<storeId>) rather than hardcoding them. The token is
passed through (it works with or without, verified 2026-06-18), so if Ecwid ever
starts enforcing it the scraper keeps working.

Usage:
  python3 ecwid_scraper.py                    # Scrape all configured nurseries
  python3 ecwid_scraper.py primal-fruits      # Scrape one nursery
  python3 ecwid_scraper.py --list             # List configured nurseries
"""

import html as _html
import json
import os
import re
import socket
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

from stocklib.model import validate_and_warn
from stocklib.scrape_health import ScrapeHealth

NURSERIES = {
    "primal-fruits": {
        "name": "Primal Fruits Perth",
        "domain": "primalfruits.com.au",
        "location": "Parkwood, WA",
        "store_id": "102345518",
        # API path: only a couple of POSTs per scrape, but the store has
        # rate-limited us before (DEC-208), so keep a polite inter-page delay.
        "delay": 1.0,
    },
}

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "nursery-stock"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"
REQUEST_DELAY = 1.5   # seconds between API pages — be polite
PAGE_SIZE = 200       # Ecwid caps a catalog page at 200 products
MAX_PAGES = 25        # safety cap on pagination (25 * 200 = 5000 products)

# Bootstrap script that the storefront embeds; carries the regional API host and
# the public token for this store.
BOOTSTRAP_URL = "https://app.ecwid.com/script.js?{store_id}"
_HOST_RE = re.compile(r"[a-z0-9-]+storefront-api\.ecwid\.com")
_TOKEN_RE = re.compile(r"pub[a-f0-9]{20,}")

# Retry policy for transient failures. 429 (rate limited) and 503 (overloaded)
# and read/connect timeouts get retried with exponential backoff so that a busy
# store doesn't silently drop products from the snapshot.
RETRYABLE_HTTP = {429, 503}
MAX_RETRIES = 3        # extra attempts after the first try
BACKOFF_BASE = 2.0     # seconds; doubles each retry
BACKOFF_CAP = 30.0     # never wait longer than this between retries


def _as_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _retry_after_seconds(headers):
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


def _backoff_delay(attempt, retry_after=None):
    """Seconds to wait before retry ``attempt`` (1-based).

    Exponential (BACKOFF_BASE * 2^(attempt-1)), but never shorter than a
    server-supplied Retry-After and never longer than BACKOFF_CAP."""
    base = BACKOFF_BASE * (2 ** (attempt - 1))
    if retry_after is not None:
        base = max(base, retry_after)
    return min(base, BACKOFF_CAP)


def _is_timeout(exc):
    """True if ``exc`` is (or wraps) a socket/read timeout."""
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, urllib.error.URLError) and isinstance(
            exc.reason, (TimeoutError, socket.timeout)):
        return True
    return False


def _request(req, timeout=20, health=None, *, _opener=None, _sleep=time.sleep):
    """Send a urllib Request, retrying transient failures, and return the raw
    response bytes (or None once retries are exhausted / on a fatal error).

    Shared by fetch_page (GET) and fetch_json (POST). Retries HTTP 429/503 and
    timeouts up to MAX_RETRIES times with exponential backoff (honouring
    Retry-After). ``_opener``/``_sleep`` are injection seams for tests."""
    opener = _opener or urllib.request.urlopen
    url = req.full_url
    for attempt in range(MAX_RETRIES + 1):
        try:
            with opener(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_HTTP and attempt < MAX_RETRIES:
                delay = _backoff_delay(attempt + 1, _retry_after_seconds(e.headers))
                print(f"  HTTP {e.code} on {url}; retry {attempt + 1}/{MAX_RETRIES} in {delay:.0f}s")
                _sleep(delay)
                continue
            print(f"  HTTP {e.code} fetching {url}")
            if health:
                health.note_http_error(e.code, url)
            return None
        except Exception as e:
            if _is_timeout(e) and attempt < MAX_RETRIES:
                delay = _backoff_delay(attempt + 1)
                print(f"  timeout on {url}; retry {attempt + 1}/{MAX_RETRIES} in {delay:.0f}s")
                _sleep(delay)
                continue
            print(f"  Error fetching {url}: {e}")
            if health:
                health.note_error(str(e))
            return None
    return None


def fetch_page(url, timeout=20, health=None, *, _opener=None, _sleep=time.sleep):
    """Fetch a URL and return the decoded body (str), retrying transient
    failures. Returns None once retries are exhausted or on a fatal error."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*",
    })
    raw = _request(req, timeout=timeout, health=health, _opener=_opener, _sleep=_sleep)
    return raw.decode("utf-8", errors="replace") if raw is not None else None


def fetch_json(url, payload, timeout=20, health=None, *, _opener=None, _sleep=time.sleep):
    """POST ``payload`` as JSON and return the parsed response (dict), retrying
    transient failures. Returns None on failure or undecodable JSON."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    raw = _request(req, timeout=timeout, health=health, _opener=_opener, _sleep=_sleep)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        print(f"  JSON decode error from {url}: {e}")
        if health:
            health.note_error(f"json decode: {e}")
        return None


def discover_storefront(store_id, health=None, *, _fetch=fetch_page):
    """Discover the regional storefront API host and public token for a store by
    reading its bootstrap script. Returns (host, token); host is None if the
    bootstrap could not be read or no host was found (caller should abort)."""
    js = _fetch(BOOTSTRAP_URL.format(store_id=store_id), health=health)
    if not js:
        return None, None
    host_m = _HOST_RE.search(js)
    token_m = _TOKEN_RE.search(js)
    return (host_m.group(0) if host_m else None,
            token_m.group(0) if token_m else None)


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text):
    """Reduce an HTML description to clean plain text (the storefront API returns
    the full HTML product body; downstream wants plain text like the old
    JSON-LD description)."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = _html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_catalog_page(data):
    """Pull (raw_products, total_count) out of one catalog API response.

    The response nests the catalogue under expandedCategories[0] (the root
    category, requested with parentCategoryId 0). Returns ([], 0) for an empty
    or malformed response."""
    cats = (data or {}).get("expandedCategories") or []
    if not cats:
        return [], 0
    root = cats[0] or {}
    return (root.get("products") or [], root.get("totalProductsCount") or 0)


def extract_product(raw, domain):
    """Map one Ecwid catalog product object to the flat snapshot product shape."""
    name = (raw.get("name") or "").strip()

    urls = raw.get("urls") or {}
    page_url = urls.get("directPageUrl") or urls.get("proxyLinkUrl") or ""
    if page_url and not page_url.startswith("http"):
        page_url = f"https://{domain}{page_url}"

    overrides = raw.get("defaultOptionsOverrides") or {}
    prices = overrides.get("pricesOverrides") or {}
    variation = overrides.get("variationOverrides") or {}

    # Sold-out products often carry a null variation SKU; that's fine, flat Ecwid
    # products are keyed by URL downstream, not SKU.
    sku = (variation.get("sku") or "").strip()

    flags = raw.get("flags") or {}
    sold_out = flags.get("isAllVariationsSoldOut")
    if sold_out is None:
        sold_out = variation.get("isSoldOut")
    if sold_out is None:
        # Unknown stock state (e.g. the API renamed the flag): treat as out of
        # stock. The conservative default surfaces breakage to Benedict as a
        # stock-drop surge alert rather than spamming subscribers with false
        # restock/variety alerts.
        sold_out = True
    available = not bool(sold_out)

    return {
        "title": name,
        "url": page_url,
        "sku": sku,
        "description": _strip_html(raw.get("description") or ""),
        "price": _as_float(prices.get("basePrice")),
        "currency": "AUD",
        "available": available,
        "availability_raw": "OutOfStock" if sold_out else "InStock",
    }


def fetch_catalog_page(host, store_id, domain, offset, limit, token=None,
                       health=None, *, _opener=None, _sleep=time.sleep):
    """Fetch one page of the catalogue from the storefront API."""
    url = f"https://{host}/storefront/api/v1/{store_id}/catalog"
    if token:
        url += f"?token={token}"
    payload = {
        "categoryViewMode": "COLLAPSED",
        "lang": "en",
        "parentCategoryId": 0,
        "pagination": {"offset": offset, "limit": limit},
        "urlParams": {
            "urlType": "CLEAN_URL",
            "baseUrl": "/products",
            "canonicalBaseUrl": f"https://{domain}/products",
            "isCleanUrls": True,
            "isCanonicalUrlsEnabled": True,
            "isSlugsWithoutIds": True,
        },
    }
    return fetch_json(url, payload, health=health, _opener=_opener, _sleep=_sleep)


def scrape_ecwid(nursery_key, config, health=None):
    """Scrape all products from an Ecwid store via its storefront API."""
    store_id = config["store_id"]
    domain = config["domain"]
    print(f"Scraping {config['name']} (store {store_id}) via Ecwid storefront API...")

    host, token = discover_storefront(store_id, health)
    if not host:
        print("  Could not discover storefront API host; aborting (keeping last snapshot)")
        if health:
            health.note_error("storefront API host discovery failed")
        return []
    print(f"  API host: {host}" + (" (token found)" if token else " (no token)"))

    delay = config.get("delay", REQUEST_DELAY)
    limit = config.get("page_size", PAGE_SIZE)

    by_key = {}
    total = 0
    for page in range(MAX_PAGES):
        offset = page * limit
        data = fetch_catalog_page(host, store_id, domain, offset, limit, token, health=health)
        if data is None:
            # A page failed after retries. Abort rather than write a partial
            # snapshot (which would look like a big drop and could fire false
            # out-of-stock / surge alerts). Last good snapshot is preserved.
            print(f"  page at offset {offset} failed after retries; aborting")
            if health:
                health.note_error(f"catalog page offset {offset} failed")
            return []
        raw_products, total = parse_catalog_page(data)
        if not raw_products:
            break
        for rp in raw_products:
            product = extract_product(rp, domain)
            ident = rp.get("identifier") or {}
            key = ident.get("productId")
            if key is None:
                key = product["url"] or product["title"]
            if key in by_key:
                continue
            product["nursery"] = nursery_key
            product["nursery_name"] = config["name"]
            by_key[key] = product
        print(f"  offset {offset}: +{len(raw_products)} products ({len(by_key)}/{total})")
        if total and len(by_key) >= total:
            break
        time.sleep(delay)

    products = sorted(by_key.values(), key=lambda p: p.get("title", ""))
    print(f"  Total: {len(products)} products scraped")
    return products


def save_snapshot(nursery_key, products, config):
    """Save a dated snapshot."""
    today = date.today().isoformat()
    nursery_dir = DATA_DIR / nursery_key
    nursery_dir.mkdir(parents=True, exist_ok=True)

    in_stock = [p for p in products if p["available"]]
    out_of_stock = [p for p in products if not p["available"]]

    snapshot = {
        "nursery": nursery_key,
        "nursery_name": config["name"],
        "location": config.get("location", ""),
        "scraped_at": datetime.now().isoformat(),
        "product_count": len(products),
        "in_stock_count": len(in_stock),
        "out_of_stock_count": len(out_of_stock),
        "products": products,
    }
    validate_and_warn(snapshot, nursery_key)

    snapshot_file = nursery_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    latest_file = nursery_dir / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"  Saved: {snapshot_file}")
    print(f"  In stock: {len(in_stock)} / Out of stock: {len(out_of_stock)}")

    # Print high-value items
    expensive = sorted(
        [p for p in products if p["price"] and p["price"] >= 50],
        key=lambda p: p["price"], reverse=True
    )
    if expensive:
        print(f"\n  High-value items (>=$50):")
        for p in expensive[:15]:
            status = "IN STOCK" if p["available"] else "out of stock"
            print(f"    ${p['price']:.2f} — {p['title']} ({status})")


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            print("Configured Ecwid nurseries:")
            for key, cfg in NURSERIES.items():
                print(f"  {key}: {cfg['name']} ({cfg['location']})")
            return

        key = sys.argv[1]
        if key not in NURSERIES:
            print(f"Unknown nursery: {key}")
            print(f"Available: {', '.join(NURSERIES.keys())}")
            sys.exit(1)
        targets = {key: NURSERIES[key]}
    else:
        targets = NURSERIES

    for key, config in targets.items():
        health = ScrapeHealth(key)
        try:
            products = scrape_ecwid(key, config, health)
            if products:
                save_snapshot(key, products, config)
        except Exception as e:
            health.note_error(repr(e))
            health.finish(ok=False)
            raise
        health.finish(products=len(products),
                      in_stock=sum(1 for p in products if p["available"]))
        print()


if __name__ == "__main__":
    main()
