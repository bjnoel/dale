#!/usr/bin/env python3
"""
Magento Beekeeping Supply Scraper

Scrapes product data from Magento-based beekeeping retailers by fetching
the sitemap and parsing each product page for structured data (Magento's
productPage event + JSON-LD Product). Designed for beewise.com.au (Perth),
which has no public JSON API like Shopify retailers do.

Usage:
    python3 magento_bee_scraper.py                    # Scrape all Magento retailers
    python3 magento_bee_scraper.py beewise            # Scrape one retailer
    python3 magento_bee_scraper.py --list             # List Magento retailers
"""

import concurrent.futures
import html as html_mod
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

from bee_retailers import RETAILERS

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent.parent / "data")) / "bee-stock"
USER_AGENT = "BeestockBot/1.0 (+https://beestock.com.au; price-monitoring)"
CONCURRENCY = 6
REQUEST_TIMEOUT = 30
SITEMAP_TIMEOUT = 30

PRODUCT_PAGE_EVENT_RE = re.compile(
    r'"event":"productPage","product":(\{(?:[^{}]|\{[^{}]*\})*\})'
)
JSON_LD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)
STOCK_AVAILABLE_RE = re.compile(r'class="[^"]*\bstock available\b', re.IGNORECASE)
STOCK_UNAVAILABLE_RE = re.compile(r'class="[^"]*\bstock unavailable\b', re.IGNORECASE)


def fetch(url, timeout=REQUEST_TIMEOUT):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_sitemap_urls(domain):
    """Return all <loc> URLs from the Magento sitemap at /sitemap.xml."""
    url = f"https://{domain}/sitemap.xml"
    body = fetch(url, timeout=SITEMAP_TIMEOUT)
    return re.findall(r"<loc>([^<]+)</loc>", body)


def parse_availability(raw_html, json_ld_blocks):
    """Return True if the page indicates in stock, False if out of stock, None if unknown."""
    for block in json_ld_blocks:
        if isinstance(block, dict) and block.get("@type") == "Product":
            offers = block.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            avail = (offers.get("availability") or "").lower()
            if "instock" in avail:
                return True
            if "outofstock" in avail or "soldout" in avail:
                return False
    if STOCK_UNAVAILABLE_RE.search(raw_html):
        return False
    if STOCK_AVAILABLE_RE.search(raw_html):
        return True
    return None


def extract_product(page_url, raw_html):
    """Extract a product dict from a Magento product page. Returns None if not a product."""
    ev = PRODUCT_PAGE_EVENT_RE.search(raw_html)
    if not ev:
        return None
    try:
        event = json.loads(ev.group(1))
    except json.JSONDecodeError:
        return None

    name = html_mod.unescape(event.get("name") or "").strip()
    if not name:
        return None

    # Parse JSON-LD blocks (lenient — Magento sometimes embeds raw newlines)
    ld_blocks = []
    for m in JSON_LD_RE.finditer(raw_html):
        try:
            ld_blocks.append(json.loads(m.group(1).strip(), strict=False))
        except json.JSONDecodeError:
            continue

    available = parse_availability(raw_html, ld_blocks)
    if available is None:
        available = True  # default-optimistic if the page has no clear marker

    price = event.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    sku = event.get("sku") or ""
    product_id = event.get("id")
    try:
        product_id = int(product_id) if product_id is not None else None
    except (TypeError, ValueError):
        product_id = None

    return {
        "page_url": page_url,
        "id": product_id,
        "sku": str(sku),
        "name": name,
        "price": price,
        "product_type": event.get("product_type") or "simple",
        "available": available,
    }


def fetch_and_parse(url):
    try:
        body = fetch(url)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return ("error", url, str(e))
    except Exception as e:
        return ("error", url, f"unexpected: {e}")
    product = extract_product(url, body)
    if product is None:
        return ("skip", url, None)
    return ("ok", url, product)


def scrape_magento(retailer_key, config):
    domain = config["domain"]
    print(f"Scraping {config['name']} ({domain})...")
    print("  Fetching sitemap...", end=" ", flush=True)
    try:
        urls = fetch_sitemap_urls(domain)
    except Exception as e:
        print(f"failed ({e})")
        return []
    print(f"{len(urls)} URLs")

    products = []
    errors = 0
    skipped = 0
    start = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        for i, result in enumerate(pool.map(fetch_and_parse, urls), 1):
            status, url, payload = result
            if status == "ok":
                products.append(payload)
            elif status == "error":
                errors += 1
                if errors <= 5:
                    print(f"  error on {url}: {payload}")
            else:
                skipped += 1
            if i % 100 == 0:
                print(f"  {i}/{len(urls)} ({len(products)} products, {skipped} non-products, {errors} errors)")

    elapsed = time.time() - start
    print(f"  Done in {elapsed:.1f}s: {len(products)} products, {skipped} non-products, {errors} errors")
    return products


def normalize_product(raw, retailer_key, config):
    """Convert a Magento product dict to the schema the beestock builders expect."""
    price = raw.get("price")
    available = bool(raw.get("available"))
    variant = {
        "id": raw.get("id"),
        "title": "Default",
        "price": f"{price:.2f}" if price is not None else None,
        "compare_at_price": None,
        "available": available,
        "sku": raw.get("sku"),
    }
    return {
        "retailer": retailer_key,
        "retailer_name": config["name"],
        "magento_id": raw.get("id"),
        "title": raw.get("name", "").strip(),
        "sku": raw.get("sku"),
        "url": raw["page_url"],
        "product_type": raw.get("product_type") or "simple",
        "tags": [],
        "created_at": None,
        "updated_at": None,
        "vendor": config["name"],
        "variants": [variant],
        "min_price": price,
        "max_price": price,
        "any_available": available,
        "on_sale": False,
    }


def save_snapshot(retailer_key, products, config):
    today = date.today().isoformat()
    retailer_dir = DATA_DIR / retailer_key
    retailer_dir.mkdir(parents=True, exist_ok=True)

    normalized = [normalize_product(p, retailer_key, config) for p in products]

    payload = {
        "retailer": retailer_key,
        "retailer_name": config["name"],
        "scraped_at": datetime.now().isoformat(),
        "product_count": len(normalized),
        "in_stock_count": sum(1 for p in normalized if p["any_available"]),
        "out_of_stock_count": sum(1 for p in normalized if not p["any_available"]),
        "products": normalized,
    }

    snapshot_file = retailer_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(payload, f, indent=2)

    latest_file = retailer_dir / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"  Saved: {snapshot_file}")
    print(f"  In stock: {payload['in_stock_count']} / {payload['product_count']}")
    return normalized


def main():
    magento_retailers = {k: v for k, v in RETAILERS.items() if v.get("platform") == "magento"}

    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            print("Configured Magento bee retailers:")
            for key, cfg in magento_retailers.items():
                print(f"  {key}: {cfg['name']} ({cfg.get('location', '')})")
            return

        key = sys.argv[1]
        if key not in magento_retailers:
            print(f"Unknown Magento retailer: {key}")
            print(f"Available: {', '.join(magento_retailers.keys()) or '(none)'}")
            sys.exit(1)
        targets = {key: magento_retailers[key]}
    else:
        targets = magento_retailers

    if not targets:
        print("No Magento retailers configured.")
        return

    for key, config in targets.items():
        products = scrape_magento(key, config)
        if products:
            save_snapshot(key, products, config)
        print()


if __name__ == "__main__":
    main()
