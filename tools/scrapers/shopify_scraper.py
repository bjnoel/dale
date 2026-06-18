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

from stocklib.model import validate_and_warn
from stocklib.scrape_health import ScrapeHealth

# Nursery configurations
NURSERIES = {
    "ross-creek": {
        "name": "Ross Creek Tropicals",
        "domain": "www.rosscreektropicals.com.au",
        "location": "Gympie, QLD",
    },
    "ladybird": {
        "name": "Ladybird Nursery",
        "domain": "www.ladybirdnursery.com.au",
        "location": "Kallangur, QLD",
    },
    "fruitopia": {
        "name": "Fruitopia Nursery",
        "domain": "fruitopianursery.com.au",
        "location": "Brisbane/Gold Coast, QLD",
    },
    "fruit-salad-trees": {
        "name": "Fruit Salad Trees",
        "domain": "www.fruitsaladtrees.com",
        "location": "Emmaville, NSW",
    },
    "diggers": {
        "name": "The Diggers Club",
        "domain": "www.diggers.com.au",
        "location": "Dromana, VIC",
        "fruit_tags": ["all fruit & nuts", "all fruit &amp; nuts", "all berries", "fruit trees", "nuts"],
        # Curated rescue (DEC-209): Diggers tags its fruit inconsistently. ~30
        # real fruit/nut/berry live plants carry no "all fruit & nuts"/"all
        # berries" tag (some are essentially untagged, e.g. Loquat). No tag rule
        # separates them from the herbs/veg/tea that share IsEd/FruitMonth, and
        # ornamentals named after fruit (Dahlia 'Raspberry Cheesecake', Russian
        # Olive) carry IsOrn=False, so a name match would drag them in. These
        # handles are a hand-verified allow-list of the dropped fruit; review on
        # re-audit (well-tagged new fruit are still caught by fruit_tags).
        "fruit_handles": [
            "blueberry-brightwell", "blueberry-brigitta", "boysenberry",
            "bunya-pine", "chokeberry-black", "cinnamon-myrtle", "cranberry",
            "goji-berry-wolfberry", "jaboticaba", "jostaberry", "lemon-lisbon",
            "lemon-myrtle", "loquat", "native-currant", "olive-verdale",
            "orange-navelina-trifoliata", "persimmon-ichikikei-jiro",
            "pig-face-pink-native-pigface", "raspberry-bogong",
            "raspberry-chilcotin", "raspberry-heritage", "raspberry-purple",
            "raspberry-willamette", "strawberry-melba-potted", "strawberry-musk",
            "strawberry-reine-des-vallees", "strawberry-tioga",
            "tasmanian-pepperberry-female",
            "tasmanian-pepperberry-male-tasmannia-lanceolata",
            "thornless-blackberry-chester", "thornless-loganberry",
            "walnut-black", "wild-plum-syn-kaffir-plum", "youngberry",
        ],
    },
    "all-season-plants-wa": {
        "name": "All Season Plants WA",
        "domain": "allseasonplantswa.com.au",
        "location": "Perth, WA",
    },
    "ausnurseries": {
        "name": "Aus Nurseries",
        "domain": "ausnurseries.com",
        "location": "Australia",
    },
    "fruit-tree-cottage": {
        "name": "Fruit Tree Cottage",
        "domain": "www.fruittreecottage.com.au",
        "location": "Forest Glen, QLD",
    },
    "perth-mobile-nursery": {
        "name": "Perth Mobile Nursery",
        "domain": "perthmobilenursery.com.au",
        "location": "Perth, WA",
    },
    "forever-seeds": {
        "name": "Forever Seeds",
        "domain": "forever-seeds.myshopify.com",
        "location": "NSW",
        "fruit_tags": ["Fruit", "edible", "citrus"],
    },
    "garden-world": {
        # Full-service garden centre with 3,400+ SKUs (bulbs, pots, hardware,
        # ornamentals). Every fruit/nut/berry/olive product carries the
        # product_type "FOOD PLANTS", which is the clean fruit filter here: the
        # "*Online" tags are inconsistently applied (some fruit trees have no
        # tags at all), so tag filtering would miss ~60 trees.
        # Melbourne-metro delivery only (in-house vans) + in-store pickup.
        #
        # The store also files some edible stock under product_type "NATIVE"
        # (bush-tucker) rather than "FOOD PLANTS", but tags it "Fruit Online":
        # this rescues Finger Lime (Rainforest Pearl / D'Emerald, incl. dwarf)
        # and Blackberry 'Chester Thornless', which the type filter alone drops
        # (DEC-209). Pure bush-tucker natives (Davidson's Plum, Dorrigo
        # pepperberry, midyim, lemon/cinnamon myrtle) carry only "Edible
        # Australian Natives" and are deliberately NOT rescued here -- that tag
        # also covers native culinary herbs (mints, basil) we don't track.
        "name": "Garden World",
        "domain": "gardenworld.au",
        "location": "Braeside, VIC",
        "product_types": ["FOOD PLANTS"],
        "fruit_tags": ["fruit online"],
    },
}

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "nursery-stock"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"
REQUEST_DELAY = 2  # seconds between paginated requests


def fetch_json(url, health=None):
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
        if health:
            health.note_http_error(e.code, url)
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        if health:
            health.note_error(str(e))
        return None


def product_tags(raw):
    """Normalise a Shopify product's tags to a lowercased list (the API returns
    either a list or a comma-joined string)."""
    tags = raw.get("tags", [])
    if isinstance(tags, str):
        return [t.strip().lower() for t in tags.split(",") if t.strip()]
    return [str(t).lower() for t in tags]


def product_in_scope(raw, config):
    """True if a product should be kept for this nursery. An include-filter:
    keep when ANY configured signal matches (logical OR), so a nursery can list
    its fruit under a product_type AND rescue items the store files elsewhere by
    tag or by an explicit handle allow-list. A nursery with no filter keeps
    everything.

    - product_types: exact match on the product's product_type (lowercased).
    - fruit_tags:    membership in the product's tag list (lowercased).
    - fruit_handles: exact match on the product handle. A curated rescue list for
      stores whose fruit is too inconsistently tagged to catch by type/tag
      without dragging in herbs/veg/ornamentals (e.g. Diggers).

    Mirrors woocommerce_scraper.category_matches: an empty filter means keep all.
    """
    types = config.get("product_types")
    fruit_tags = config.get("fruit_tags")
    fruit_handles = config.get("fruit_handles")
    if not (types or fruit_tags or fruit_handles):
        return True
    if types and (raw.get("product_type") or "").lower() in {t.lower() for t in types}:
        return True
    if fruit_tags:
        tags = product_tags(raw)
        if any(ft.lower() in tags for ft in fruit_tags):
            return True
    if fruit_handles and (raw.get("handle") or "") in fruit_handles:
        return True
    return False


def scrape_shopify(nursery_key, config, health=None):
    """Scrape all products from a Shopify store's JSON API."""
    domain = config["domain"]
    all_products = []
    page = 1

    print(f"Scraping {config['name']} ({domain})...")

    while True:
        url = f"https://{domain}/products.json?limit=250&page={page}"
        print(f"  Page {page}...", end=" ", flush=True)

        data = fetch_json(url, health)
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

    # Apply the include-filter (product_types / fruit_tags / fruit_handles).
    # An unfiltered nursery keeps everything; product_in_scope returns True.
    has_filter = any(config.get(k) for k in ("product_types", "fruit_tags", "fruit_handles"))
    if has_filter:
        before = len(all_products)
        all_products = [p for p in all_products if product_in_scope(p, config)]
        print(f"  Filtered (in scope): {before} -> {len(all_products)}")
    else:
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
    snapshot = {
        "nursery": nursery_key,
        "nursery_name": config["name"],
        "scraped_at": datetime.now().isoformat(),
        "product_count": len(normalized),
        "in_stock_count": sum(1 for p in normalized if p["any_available"]),
        "out_of_stock_count": sum(1 for p in normalized if not p["any_available"]),
        "products": normalized,
    }
    validate_and_warn(snapshot, nursery_key)

    snapshot_file = nursery_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)

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
        health = ScrapeHealth(key)
        try:
            products = scrape_shopify(key, config, health)
            normalized = []
            if products:
                normalized = save_snapshot(key, products, config)
                print_summary(key, normalized)
        except Exception as e:
            health.note_error(repr(e))
            health.finish(ok=False)
            raise
        health.finish(products=len(normalized),
                      in_stock=sum(1 for p in normalized if p["any_available"]))
        print()


if __name__ == "__main__":
    main()
