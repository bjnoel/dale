#!/usr/bin/env python3
"""
Shopify Nursery Stock Scraper

Scrapes product data from Shopify-based nurseries using their public JSON API.
Respects rate limits and stores historical data for trend tracking.

Usage:
  python3 shopify_scraper.py                    # Scrape all configured nurseries
  python3 shopify_scraper.py ross-creek         # Scrape one nursery
  python3 shopify_scraper.py --list             # List configured nurseries
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

# Nursery configurations
NURSERIES = {
    "ross-creek": {
        "name": "Ross Creek Tropicals",
        "domain": "www.rosscreektropicals.com.au",
        "location": "Gympie, QLD",
        "ships_to_wa": False,
    },
    "ladybird": {
        "name": "Ladybird Nursery",
        "domain": "www.ladybirdnursery.com.au",
        "location": "Kallangur, QLD",
        "ships_to_wa": False,
    },
    "fruitopia": {
        "name": "Fruitopia Nursery",
        "domain": "fruitopianursery.com.au",
        "location": "Brisbane/Gold Coast, QLD",
        "ships_to_wa": False,
    },
    "fruit-salad-trees": {
        "name": "Fruit Salad Trees",
        "domain": "www.fruitsaladtrees.com",
        "location": "Emmaville, NSW",
        "ships_to_wa": True,
        "ships_to_wa_note": "1st Tuesday of month",
    },
    "diggers": {
        "name": "The Diggers Club",
        "domain": "www.diggers.com.au",
        "location": "Dromana, VIC",
        "ships_to_wa": True,
        "ships_to_wa_note": "Weekly",
        "fruit_tags": ["all fruit & nuts", "all fruit &amp; nuts", "all berries", "fruit trees", "nuts"],
    },
}

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "nursery-stock"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"
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


def scrape_shopify(nursery_key, config):
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

    # Filter by fruit tags if configured
    fruit_tags = config.get("fruit_tags")
    if fruit_tags:
        filtered = []
        for p in all_products:
            tags = p.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip().lower() for t in tags.split(",")]
            else:
                tags = [t.lower() for t in tags]
            if any(ft.lower() in tags for ft in fruit_tags):
                filtered.append(p)
        print(f"  Total: {len(all_products)} products, {len(filtered)} fruit/nut (filtered)")
        return filtered

    print(f"  Total: {len(all_products)} products")
    return all_products


def normalize_product(raw, nursery_key, config):
    """Extract the fields we care about from Shopify's product JSON."""
    variants = raw.get("variants", [])

    product = {
        "nursery": nursery_key,
        "nursery_name": config["name"],
        "shopify_id": raw.get("id"),
        "title": raw.get("title", "").strip(),
        "handle": raw.get("handle"),
        "url": f"https://{config['domain']}/products/{raw.get('handle')}",
        "product_type": raw.get("product_type", ""),
        "tags": raw.get("tags", []) if isinstance(raw.get("tags"), list) else [t.strip() for t in raw.get("tags", "").split(",") if t.strip()],
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "ships_to_wa": config.get("ships_to_wa", False),
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

    # Summary fields — prefer prices from available variants
    avail_prices = [float(v["price"]) for v in product["variants"] if v["price"] and v["available"]]
    all_prices = [float(v["price"]) for v in product["variants"] if v["price"]]
    product["min_price"] = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)
    product["max_price"] = max(avail_prices) if avail_prices else (max(all_prices) if all_prices else None)
    product["any_available"] = any(v["available"] for v in product["variants"])
    product["on_sale"] = any(v["compare_at_price"] and float(v["compare_at_price"]) > float(v["price"]) for v in product["variants"] if v["price"] and v["compare_at_price"])

    return product


def save_snapshot(nursery_key, products, config):
    """Save a dated snapshot of the scrape results."""
    today = date.today().isoformat()
    nursery_dir = DATA_DIR / nursery_key
    nursery_dir.mkdir(parents=True, exist_ok=True)

    # Normalize products
    normalized = [normalize_product(p, nursery_key, config) for p in products]

    # Save full snapshot
    snapshot_file = nursery_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump({
            "nursery": nursery_key,
            "nursery_name": config["name"],
            "scraped_at": datetime.now().isoformat(),
            "product_count": len(normalized),
            "in_stock_count": sum(1 for p in normalized if p["any_available"]),
            "out_of_stock_count": sum(1 for p in normalized if not p["any_available"]),
            "products": normalized,
        }, f, indent=2)

    print(f"  Saved: {snapshot_file}")
    print(f"  In stock: {sum(1 for p in normalized if p['any_available'])}")
    print(f"  Out of stock: {sum(1 for p in normalized if not p['any_available'])}")

    # Save latest symlink / copy for easy access
    latest_file = nursery_dir / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(json.load(open(snapshot_file)), f, indent=2)

    return normalized


def print_summary(nursery_key, products):
    """Print a quick summary of what we found."""
    fruit_keywords = [
        "jaboticaba", "rollinia", "sapodilla", "sapote", "grumichama",
        "miracle fruit", "ice cream bean", "inga", "eugenia", "syzygium",
        "annona", "cherimoya", "soursop", "custard apple", "dragon fruit",
        "pitaya", "mangosteen", "rambutan", "longan", "lychee",
        "jackfruit", "durian", "cacao", "coffee", "vanilla",
        "fig", "mulberry", "pomegranate", "guava", "feijoa",
        "passionfruit", "tamarind", "carambola", "starfruit",
    ]

    print(f"\n  Rare/sought-after varieties in stock:")
    for p in products:
        if not p["any_available"]:
            continue
        title_lower = p["title"].lower()
        for keyword in fruit_keywords:
            if keyword in title_lower:
                price_str = f"${p['min_price']:.2f}" if p["min_price"] else "?"
                print(f"    {p['title']} — {price_str}")
                break


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            print("Configured nurseries:")
            for key, cfg in NURSERIES.items():
                print(f"  {key}: {cfg['name']} ({cfg['location']})")
            return

        # Scrape specific nursery
        key = sys.argv[1]
        if key not in NURSERIES:
            print(f"Unknown nursery: {key}")
            print(f"Available: {', '.join(NURSERIES.keys())}")
            sys.exit(1)
        targets = {key: NURSERIES[key]}
    else:
        targets = NURSERIES

    for key, config in targets.items():
        products = scrape_shopify(key, config)
        if products:
            normalized = save_snapshot(key, products, config)
            print_summary(key, normalized)
        print()


if __name__ == "__main__":
    main()
