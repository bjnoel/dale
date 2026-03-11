#!/usr/bin/env python3
"""
Ecwid Nursery Stock Scraper

Scrapes product data from Ecwid-based nurseries by:
1. Fetching the main page to discover all product URLs
2. Fetching each product page to extract JSON-LD structured data

Usage:
  python3 ecwid_scraper.py                    # Scrape all configured nurseries
  python3 ecwid_scraper.py primal-fruits      # Scrape one nursery
  python3 ecwid_scraper.py --list             # List configured nurseries
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

NURSERIES = {
    "primal-fruits": {
        "name": "Primal Fruits Perth",
        "domain": "primalfruits.com.au",
        "location": "Parkwood, WA",
        "ships_to_wa": True,
        "store_id": "102345518",
    },
}

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "nursery-stock"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"
REQUEST_DELAY = 1.5  # seconds between requests — be polite


def fetch_page(url, timeout=20):
    """Fetch a page and return the HTML body."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} fetching {url}")
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def discover_product_urls(domain):
    """Fetch the main page and extract all product URLs."""
    url = f"https://{domain}"
    print(f"  Discovering products from {url}...")
    html = fetch_page(url)
    if not html:
        return []

    # Extract product URLs (full and relative)
    pattern = rf'href="((?:https://{re.escape(domain)})?/products/[^"?#]+)"'
    matches = re.findall(pattern, html)

    # Normalise to full URLs, deduplicate, exclude system pages
    system_pages = {"account", "cart", "search", "checkout"}
    urls = set()
    for m in matches:
        if m.startswith("/"):
            m = f"https://{domain}{m}"
        slug = m.rstrip("/").split("/products/")[-1].lower()
        # Skip system pages and category pages
        if slug in system_pages:
            continue
        urls.add(m)

    print(f"  Found {len(urls)} product URLs")
    return sorted(urls)


def extract_product_data(url, html):
    """Extract product data from JSON-LD on a product page."""
    # Find JSON-LD script
    match = re.search(
        r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not match:
        return None

    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None

    if data.get("@type") != "Product":
        return None

    offers = data.get("offers", {})
    availability = offers.get("availability", "")

    return {
        "title": data.get("name", ""),
        "url": url,
        "sku": data.get("sku", ""),
        "description": data.get("description", ""),
        "price": float(offers.get("price", 0)) if offers.get("price") else None,
        "currency": offers.get("priceCurrency", "AUD"),
        "available": "InStock" in availability,
        "availability_raw": availability,
    }


def scrape_ecwid(nursery_key, config):
    """Scrape all products from an Ecwid store."""
    domain = config["domain"]
    print(f"Scraping {config['name']} ({domain})...")

    product_urls = discover_product_urls(domain)
    if not product_urls:
        print("  No products found")
        return []

    products = []
    for i, url in enumerate(product_urls):
        slug = url.split("/products/")[-1][:40]
        print(f"  [{i+1}/{len(product_urls)}] {slug}...", end=" ", flush=True)

        html = fetch_page(url)
        if not html:
            print("failed")
            continue

        product = extract_product_data(url, html)
        if product:
            product["nursery"] = nursery_key
            product["nursery_name"] = config["name"]
            product["ships_to_wa"] = config.get("ships_to_wa", False)
            products.append(product)
            status = "IN STOCK" if product["available"] else "out of stock"
            print(f"${product['price']:.2f} ({status})" if product["price"] else "no price")
        else:
            print("no data")

        time.sleep(REQUEST_DELAY)

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
        "ships_to_wa": config.get("ships_to_wa", False),
        "scraped_at": datetime.now().isoformat(),
        "product_count": len(products),
        "in_stock_count": len(in_stock),
        "out_of_stock_count": len(out_of_stock),
        "products": products,
    }

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
        products = scrape_ecwid(key, config)
        if products:
            save_snapshot(key, products, config)
        print()


if __name__ == "__main__":
    main()
