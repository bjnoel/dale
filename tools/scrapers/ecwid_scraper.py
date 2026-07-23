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
    "wild-garden-organics": {
        # QLD rare-tropical grafted-fruit nursery on an Ecwid "starter site".
        # store_id discovered from app.ecwid.com/script.js?95573253 (2026-06-20).
        "name": "Wild Garden Organics",
        "domain": "wildgardenorganics.com.au",
        "location": "QLD",
        "store_id": "95573253",
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

# Retry policy for transient failures (429/503/timeouts) lives in
# stocklib.retry, shared with the other scrapers. Old private names kept as
# aliases for existing callers/tests.
from stocklib.retry import (  # noqa: E402
    RETRYABLE_HTTP, MAX_RETRIES, BACKOFF_BASE, BACKOFF_CAP,
    retry_after_seconds as _retry_after_seconds,
    backoff_delay as _backoff_delay,
    is_timeout as _is_timeout,
    request_with_retry as _request,
)


def _as_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
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
    price = _as_float(prices.get("basePrice"))

    # Emit BOTH dialects' availability/price fields. Ecwid is the "flat" dialect
    # (top-level available/price, no variants), but most builders read the
    # variant dialect's precomputed any_available/min_price/max_price and treat a
    # missing field as out-of-stock / price-on-application. Carrying both keeps
    # every consumer correct (the Primal Fruits "0 in stock, all POA" bug) without
    # adding a `variants` list, so changes.py still keys these products by URL.
    return {
        "title": name,
        "url": page_url,
        "sku": sku,
        "description": _strip_html(raw.get("description") or ""),
        "price": price,
        "min_price": price,
        "max_price": price,
        "currency": "AUD",
        "available": available,
        "any_available": available,
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
