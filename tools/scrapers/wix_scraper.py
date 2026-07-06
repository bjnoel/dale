#!/usr/bin/env python3
"""
Wix Nursery Stock Scraper

Scrapes product data from Wix-based nurseries by:
1. Fetching the store products sitemap (store-products-sitemap.xml) to
   discover every /product-page/<slug> URL
2. Fetching each product page and parsing the Wix "warmupData" JSON blob
   (<script type="application/json" id="wix-warmup-data">) that the
   storefront embeds for hydration

Why not JSON-LD: Wix product pages DO carry a JSON-LD Product block, but its
offers object is empty ({} -- no price, sku or availability), so it is useless
for stock tracking (DAL-206). The warmupData blob carries the full catalog
product node: name, price, discountedPrice, isInStock, inventory, options and
per-variant productItems.

Price semantics (verified against Heaven On Earth 2026-07-06): `price` is the
undiscounted base price and `discountedPrice` is what the buyer actually pays
(the store runs a storewide percent discount; 89 -> 62.30). Per-variant
productItems carry the same pair as price/comparePrice with hasDiscount.

Usage:
  python3 wix_scraper.py                    # Scrape all configured nurseries
  python3 wix_scraper.py heaven-on-earth    # Scrape one nursery
  python3 wix_scraper.py --list             # List configured nurseries
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
    "heaven-on-earth": {
        # Far North QLD rare-tropical specialist (abiu, mamey sapote, soursop,
        # miracle fruit, durian). Ships AU-wide except WA/TAS; citrus QLD-only
        # (per-product rule, flagged in product names as "QLD POSTAGE ONLY").
        "name": "Heaven On Earth Fruit Trees",
        "domain": "www.heavenonearthfruittrees.com.au",
        "location": "Far North QLD",
        "delay": 1.5,
    },
}

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "nursery-stock"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"
REQUEST_DELAY = 1.5   # seconds between product-page fetches -- be polite

# Retry policy for transient failures, same as ecwid_scraper: 429/503 and
# timeouts get retried with exponential backoff so a busy store doesn't
# silently drop products from the snapshot.
RETRYABLE_HTTP = {429, 503}
MAX_RETRIES = 3        # extra attempts after the first try
BACKOFF_BASE = 2.0     # seconds; doubles each retry
BACKOFF_CAP = 30.0     # never wait longer than this between retries

# If more than this fraction of product pages fail (after retries), abort the
# scrape without writing a snapshot. A partial snapshot looks like a mass
# delisting downstream and can fire false surge alerts; keeping the last good
# snapshot surfaces the breakage via scrape-health instead.
MAX_FAILURE_RATIO = 0.2

_WARMUP_RE = re.compile(
    r'<script type="application/json" id="wix-warmup-data">(.*?)</script>',
    re.DOTALL,
)
_LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")
_TAG_RE = re.compile(r"<[^>]+>")


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


def fetch_page(url, timeout=20, health=None, *, _opener=None, _sleep=time.sleep):
    """Fetch a URL and return the decoded body (str), retrying transient
    failures (429/503/timeouts) with exponential backoff. Returns None once
    retries are exhausted or on a fatal error. ``_opener``/``_sleep`` are
    injection seams for tests."""
    opener = _opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml,*/*",
    })
    for attempt in range(MAX_RETRIES + 1):
        try:
            with opener(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
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


def _strip_html(text):
    """Reduce an HTML description to clean plain text (warmupData carries the
    full HTML product body; downstream wants plain text)."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = _html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_sitemap(xml_text):
    """Pull the product-page URLs out of a store-products sitemap.

    Keeps only /product-page/ URLs (the store sitemap should contain nothing
    else, but category or policy pages would silently pollute the scrape).
    Returns a sorted, deduplicated list."""
    urls = set()
    for loc in _LOC_RE.findall(xml_text or ""):
        loc = _html.unescape(loc.strip())
        if "/product-page/" in loc:
            urls.add(loc)
    return sorted(urls)


def extract_warmup_data(html_text):
    """Parse the wix-warmup-data JSON blob out of a product page.

    Returns the parsed dict, or None if the tag is missing or unparseable
    (e.g. Wix changes how it hydrates pages -- the DAL-205 failure mode)."""
    m = _WARMUP_RE.search(html_text or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def find_product_node(warmup):
    """Locate the catalog product node inside warmupData.

    The node lives at appsWarmupData.<stores-app-id>.productPage_<currency>_
    <slug>.catalog.product; the app id and key spelling are Wix internals, so
    scan every app for a productPage* entry rather than hardcoding them."""
    apps = (warmup or {}).get("appsWarmupData") or {}
    for app in apps.values():
        if not isinstance(app, dict):
            continue
        for key, val in app.items():
            if key.startswith("productPage") and isinstance(val, dict):
                node = (val.get("catalog") or {}).get("product")
                if node:
                    return node
    return None


def _effective_item_price(item):
    """The price a buyer pays for one productItem (variant).

    Wix names are backwards from Shopify: `price` is the undiscounted base and
    `comparePrice` is the discounted price when hasDiscount is set. Only trust
    comparePrice when it is actually lower, in case a store uses it in the
    strike-through "was" sense instead."""
    price = _as_float(item.get("price"))
    compare = _as_float(item.get("comparePrice"))
    if item.get("hasDiscount") and compare and price and compare < price:
        return compare
    return price if price is not None else compare


def extract_product(node, url):
    """Map one warmupData catalog product node to the flat snapshot shape."""
    name = (node.get("name") or "").strip()

    base = _as_float(node.get("price"))
    discounted = _as_float(node.get("discountedPrice"))
    # discountedPrice is what the buyer pays; only trust it when it is a real
    # discount (lower than base), never as a price increase.
    price = discounted if (discounted and (base is None or discounted <= base)) else base

    # Per-variant prices (size options etc.). A product without options still
    # carries one default productItem; with options each visible item is one
    # variant, so min/max across them is the real price range.
    items = [i for i in (node.get("productItems") or [])
             if isinstance(i, dict) and i.get("isVisible", True)]
    item_prices = [p for p in (_effective_item_price(i) for i in items) if p]
    min_price = min(item_prices) if item_prices else price
    max_price = max(item_prices) if item_prices else price

    # isInStock is the ONLY trustworthy stock signal. inventory.status looked
    # like a fallback but is a lie: on Heaven On Earth every sold-out product
    # (66 of 128 at capture time, "Out of Stock" rendered on page) still
    # carries inventory.status == "in_stock", so falling back to it would
    # mark the whole store in stock -- the non-conservative direction. If Wix
    # ever renames isInStock, everything goes out of stock instead, which
    # surfaces to Benedict as a stock-drop surge alert rather than spamming
    # subscribers with false restock/variety alerts (same rule as Ecwid).
    available = bool(node.get("isInStock"))

    # Emit BOTH dialects' availability/price fields (flat dialect + the
    # variant dialect's precomputed any_available/min_price/max_price) so all
    # builders render it correctly -- see ecwid_scraper.extract_product and
    # the DEC-210 "0 in stock / POA" bug.
    return {
        "title": name,
        "url": url,
        "sku": (node.get("sku") or "").strip(),
        "description": _strip_html(node.get("description") or ""),
        "price": min_price,
        "min_price": min_price,
        "max_price": max_price,
        "currency": node.get("currency") or "AUD",
        "available": available,
        "any_available": available,
        "availability_raw": "InStock" if available else "OutOfStock",
    }


def scrape_wix(nursery_key, config, health=None):
    """Scrape all products from a Wix store via its products sitemap."""
    domain = config["domain"]
    print(f"Scraping {config['name']} ({domain}) via Wix warmupData...")

    sitemap_url = f"https://{domain}/store-products-sitemap.xml"
    xml_text = fetch_page(sitemap_url, health=health)
    urls = parse_sitemap(xml_text)
    if not urls:
        print("  No product URLs in store sitemap; aborting (keeping last snapshot)")
        if health:
            health.note_error("store products sitemap empty or unfetchable")
        return []
    print(f"  {len(urls)} product URLs in sitemap")

    delay = config.get("delay", REQUEST_DELAY)
    products = []
    failures = 0
    for i, url in enumerate(urls):
        slug = url.rstrip("/").split("/product-page/")[-1][:45]
        print(f"  [{i+1}/{len(urls)}] {slug}...", end=" ", flush=True)

        html_text = fetch_page(url, health=health)
        node = find_product_node(extract_warmup_data(html_text)) if html_text else None
        if node is None:
            print("no product data")
            failures += 1
        elif node.get("isVisible") is False:
            print("hidden; skipped")
        else:
            product = extract_product(node, url)
            product["nursery"] = nursery_key
            product["nursery_name"] = config["name"]
            products.append(product)
            status = "IN STOCK" if product["available"] else "out of stock"
            price_str = f"${product['price']:.2f}" if product["price"] else "no price"
            print(f"{price_str} ({status})")

        if i + 1 < len(urls):
            time.sleep(delay)

    if failures > MAX_FAILURE_RATIO * len(urls):
        print(f"  {failures}/{len(urls)} pages failed; aborting (keeping last snapshot)")
        if health:
            health.note_error(f"{failures}/{len(urls)} product pages failed")
        return []
    if failures:
        print(f"  Warning: {failures}/{len(urls)} pages failed; snapshot is slightly short")

    products.sort(key=lambda p: p.get("title", ""))
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
            print("Configured Wix nurseries:")
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
            products = scrape_wix(key, config, health)
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
