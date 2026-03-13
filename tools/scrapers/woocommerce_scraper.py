#!/usr/bin/env python3
"""
WooCommerce Nursery Stock Scraper

Scrapes product data from WooCommerce-based nurseries using the public
Store API (wc/store/v1/products). No API key required.

Usage:
  python3 woocommerce_scraper.py                    # Scrape all configured nurseries
  python3 woocommerce_scraper.py guildford          # Scrape one nursery
  python3 woocommerce_scraper.py --list             # List configured nurseries
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from html import unescape
from pathlib import Path

NURSERIES = {
    "guildford": {
        "name": "Guildford Garden Centre",
        "domain": "guildfordgardencentre.com.au",
        "location": "Guildford, WA",
        "fruit_categories": ["fruits-nuts", "edibles"],
    },
}

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "nursery-stock"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"
REQUEST_DELAY = 1.5


def fetch_json(url):
    """Fetch JSON from URL."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} fetching {url}")
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def scrape_woocommerce(nursery_key, config):
    """Scrape all products from a WooCommerce store."""
    domain = config["domain"]
    fruit_cats = config.get("fruit_categories", [])
    all_products = []
    page = 1
    per_page = 100

    print(f"Scraping {config['name']} ({domain})...")

    while True:
        url = f"https://{domain}/wp-json/wc/store/v1/products?per_page={per_page}&page={page}"
        print(f"  Page {page}...", end=" ", flush=True)

        data = fetch_json(url)
        if data is None:
            print("failed")
            break

        if not data:
            print("empty (done)")
            break

        # Filter to fruit/edible categories only
        for product in data:
            cats = [c["slug"] for c in product.get("categories", [])]
            if fruit_cats:
                if not any(fc in cats or any(fc in c for c in cats) for fc in fruit_cats):
                    continue
            all_products.append(product)

        print(f"{len(data)} products ({len(all_products)} fruit/edible)")

        if len(data) < per_page:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    print(f"  Total fruit/edible: {len(all_products)} products")
    return all_products


def normalize_product(raw, nursery_key, config):
    """Normalize a WooCommerce product."""
    # Price is in cents (minor units)
    prices = raw.get("prices", {})
    price_raw = prices.get("price")
    minor_unit = prices.get("currency_minor_unit", 2)
    price = float(price_raw) / (10 ** minor_unit) if price_raw else None

    regular_raw = prices.get("regular_price")
    regular_price = float(regular_raw) / (10 ** minor_unit) if regular_raw else None

    on_sale = raw.get("on_sale", False)
    available = raw.get("is_in_stock", False)

    # Clean HTML entities from name
    title = unescape(raw.get("name", ""))

    return {
        "nursery": nursery_key,
        "nursery_name": config["name"],
        "title": title,
        "url": raw.get("permalink", ""),
        "product_type": ", ".join(c["name"] for c in raw.get("categories", [])),
        "tags": [t["name"] for t in raw.get("tags", [])],
        "variants": [{
            "title": "Default",
            "price": price,
            "available": available,
        }],
        "min_price": price,
        "max_price": price,
        "any_available": available,
        "on_sale": on_sale,
    }


def save_snapshot(nursery_key, products, config):
    """Save a dated snapshot."""
    today = date.today().isoformat()
    nursery_dir = DATA_DIR / nursery_key
    nursery_dir.mkdir(parents=True, exist_ok=True)

    normalized = [normalize_product(p, nursery_key, config) for p in products]
    in_stock = sum(1 for p in normalized if p["any_available"])

    snapshot = {
        "nursery": nursery_key,
        "nursery_name": config["name"],
        "location": config.get("location", ""),
        "scraped_at": datetime.now().isoformat(),
        "product_count": len(normalized),
        "in_stock_count": in_stock,
        "out_of_stock_count": len(normalized) - in_stock,
        "products": normalized,
    }

    snapshot_file = nursery_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    latest_file = nursery_dir / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"  Saved: {snapshot_file}")
    print(f"  In stock: {in_stock} / Out of stock: {len(normalized) - in_stock}")


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            print("Configured WooCommerce nurseries:")
            for key, cfg in NURSERIES.items():
                print(f"  {key}: {cfg['name']} ({cfg['location']})")
            return

        key = sys.argv[1]
        if key not in NURSERIES:
            print(f"Unknown nursery: {key}")
            sys.exit(1)
        targets = {key: NURSERIES[key]}
    else:
        targets = NURSERIES

    for key, config in targets.items():
        products = scrape_woocommerce(key, config)
        if products:
            save_snapshot(key, products, config)
        print()


if __name__ == "__main__":
    main()
