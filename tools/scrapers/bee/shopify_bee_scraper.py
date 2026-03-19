#!/usr/bin/env python3
"""
Shopify Beekeeping Supply Scraper

Scrapes product data from Shopify-based beekeeping retailers using their
public JSON API. Same pattern as the nursery shopify_scraper.py.

Usage:
    python3 shopify_bee_scraper.py                    # Scrape all configured retailers
    python3 shopify_bee_scraper.py ecrotek             # Scrape one retailer
    python3 shopify_bee_scraper.py --list              # List configured retailers
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

from bee_retailers import RETAILERS

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent.parent / "data")) / "bee-stock"
USER_AGENT = "BeestockBot/1.0 (+https://beestock.com.au; price-monitoring)"
REQUEST_DELAY = 2  # seconds between paginated requests


def fetch_json(url):
    """Fetch JSON from URL with proper headers."""
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


def scrape_shopify(retailer_key, config):
    """Scrape all products from a Shopify store's JSON API."""
    domain = config["domain"]
    all_products = []
    page = 1

    print(f"Scraping {config['name']} ({domain})...")

    while True:
        url = f"https://{domain}/products.json?limit=250&page={page}"
        print(f"  Page {page}...", end=" ", flush=True)

        data = fetch_json(url)
        if data is None:
            print("failed")
            break

        products = data.get("products", [])
        if not products:
            print("empty (done)")
            break

        print(f"{len(products)} products")
        all_products.extend(products)
        page += 1
        time.sleep(REQUEST_DELAY)

    print(f"  Total: {len(all_products)} products")
    return all_products


def normalize_product(raw, retailer_key, config):
    """Extract the fields we care about from Shopify's product JSON."""
    variants = raw.get("variants", [])

    product = {
        "retailer": retailer_key,
        "retailer_name": config["name"],
        "shopify_id": raw.get("id"),
        "title": raw.get("title", "").strip(),
        "handle": raw.get("handle"),
        "url": f"https://{config['domain']}/products/{raw.get('handle')}",
        "product_type": raw.get("product_type", ""),
        "tags": raw.get("tags", []) if isinstance(raw.get("tags"), list) else [t.strip() for t in raw.get("tags", "").split(",") if t.strip()],
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "vendor": raw.get("vendor", ""),
        "variants": [],
    }

    for v in variants:
        product["variants"].append({
            "id": v.get("id"),
            "title": v.get("title", "Default"),
            "price": v.get("price"),
            "compare_at_price": v.get("compare_at_price"),
            "available": v.get("available", False),
            "sku": v.get("sku"),
        })

    # Summary fields
    avail_prices = [float(v["price"]) for v in product["variants"] if v["price"] and v["available"]]
    all_prices = [float(v["price"]) for v in product["variants"] if v["price"]]
    product["min_price"] = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)
    product["max_price"] = max(avail_prices) if avail_prices else (max(all_prices) if all_prices else None)
    product["any_available"] = any(v["available"] for v in product["variants"])
    product["on_sale"] = any(
        v["compare_at_price"] and float(v["compare_at_price"]) > float(v["price"])
        for v in product["variants"]
        if v["price"] and v["compare_at_price"]
    )

    return product


def save_snapshot(retailer_key, products, config):
    """Save a dated snapshot of the scrape results."""
    today = date.today().isoformat()
    retailer_dir = DATA_DIR / retailer_key
    retailer_dir.mkdir(parents=True, exist_ok=True)

    normalized = [normalize_product(p, retailer_key, config) for p in products]

    snapshot_file = retailer_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump({
            "retailer": retailer_key,
            "retailer_name": config["name"],
            "scraped_at": datetime.now().isoformat(),
            "product_count": len(normalized),
            "in_stock_count": sum(1 for p in normalized if p["any_available"]),
            "out_of_stock_count": sum(1 for p in normalized if not p["any_available"]),
            "products": normalized,
        }, f, indent=2)

    print(f"  Saved: {snapshot_file}")
    print(f"  In stock: {sum(1 for p in normalized if p['any_available'])}")
    print(f"  Out of stock: {sum(1 for p in normalized if not p['any_available'])}")

    # Save latest copy for easy access
    latest_file = retailer_dir / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(json.load(open(snapshot_file)), f, indent=2)

    return normalized


def main():
    # Filter to Shopify retailers only
    shopify_retailers = {k: v for k, v in RETAILERS.items() if v.get("platform") == "shopify"}

    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            print("Configured Shopify bee retailers:")
            for key, cfg in shopify_retailers.items():
                print(f"  {key}: {cfg['name']} ({cfg['location']})")
            return

        key = sys.argv[1]
        if key not in shopify_retailers:
            print(f"Unknown retailer: {key}")
            print(f"Available: {', '.join(shopify_retailers.keys())}")
            sys.exit(1)
        targets = {key: shopify_retailers[key]}
    else:
        targets = shopify_retailers

    for key, config in targets.items():
        products = scrape_shopify(key, config)
        if products:
            save_snapshot(key, products, config)
        print()


if __name__ == "__main__":
    main()
