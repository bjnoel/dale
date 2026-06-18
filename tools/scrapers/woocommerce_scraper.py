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

from stocklib.model import validate_and_warn
from stocklib.scrape_health import ScrapeHealth

NURSERIES = {
    "guildford": {
        "name": "Guildford Garden Centre",
        "domain": "guildfordgardencentre.com.au",
        "location": "Guildford, WA",
        # Guildford tags many fruit trees with only their leaf category and omits
        # the "fruits-nuts"/"edibles" parent (e.g. Fig - Peter Good carries only
        # exotic-tropical-fruit-trees + fig-tree). Parent-only filtering silently
        # dropped ~225 real fruit/nut trees. Listing the leaf categories too fixes
        # it. Matching is substring-based, so "stone-fruit" also catches
        # "stone-fruit-trees-bare-root-stock", "dwarf-fruit" catches the dwarf
        # bare-root group, etc.
        "fruit_categories": [
            "fruits-nuts", "edibles",
            "stone-fruit", "citrus", "fig-tree", "nut-trees",
            "dwarf-fruit", "exotic-tropical-fruit", "berries-vines",
            "berries-and-vines", "self-fertile-fruit", "grape", "blueberry",
            "raspberry", "passion-fruit", "guava-feijoa", "mango", "avocado",
            "banana", "mulberry", "soft-skin", "currant",
        ],
    },
    "yalca-fruit-trees": {
        "name": "Yalca Fruit Trees",
        "domain": "yalcafruittrees.com.au",
        "location": "Yalca, VIC",
        "fruit_categories": [
            "apple-trees", "dwarf-apple-trees", "apricot-trees", "cherry-trees",
            "fig-trees", "mulberry-trees", "nectarine-trees", "peach-trees",
            "pear-trees", "perry-pear-trees", "persimmon-trees",
            "plum-trees", "plum-trees-european", "quince-trees",
            "almond-trees", "pistachio-trees", "raspberry-plants",
            "dwarf-fruit-trees", "sub-tropical-and-low-chill-fruits",
            "fruit-tree-hybrid", "specials-discounts",
            # Nuts/fruit Yalca tags with their own leaf category only (not the
            # listed ones above): walnuts, hazelnuts, pomegranate, tayberry.
            # Ornamentals (maple/ash/elm) stay excluded -- they carry only
            # "ornamental-trees".
            "walnut-trees", "hazel-nuts", "pomegranate-trees", "blackberry-plants",
        ],
    },
    "garden-express": {
        # Australia's largest online nursery (6,200+ products total, mostly non-fruit).
        # Use category_api mode to fetch only the fruit/nut categories — avoids paginating 60+ pages.
        # Ships nationwide incl. WA/NT/TAS (quarantine surcharge applies).
        # Mostly bare-root seasonal (June-Sep); only citrus in stock March.
        "name": "Garden Express",
        "domain": "www.gardenexpress.com.au",
        "location": "VIC",
        "category_api": True,
        "fruit_categories": [
            "fruit-nut-trees",
            "trees-stone-fruit",
            "trees-apples-pears",
            "trees-avocados",
            "fruiting-vines",
            "fruit-trees-2025",
        ],
    },
    "plantnet": {
        # PlantNet (retail arm of Balhannah Nurseries, est. 1887, SA).
        # Ships to WA via their Olea Nurseries partner in Manjimup WA.
        # Temperate fruit specialist: apples, pears, stone fruit, berries, citrus.
        # ~110 products in fruit-trees category.
        "name": "PlantNet",
        "domain": "plantnet.com.au",
        "location": "Balhannah, SA",
        "category_api": True,
        "fruit_categories": ["fruit-trees"],
    },
    "fruit-tree-lane": {
        # Fruit Tree Lane, Helidon QLD. Specialises in fruit trees, finger limes,
        # figs, olives, blueberries, and subtropical varieties.
        # Does NOT ship to WA, NT, or TAS (quarantine restrictions).
        "name": "Fruit Tree Lane",
        "domain": "fruittreelane.com.au",
        "location": "Helidon, QLD",
        "fruit_categories": [
            "apple", "avocado", "blackberry", "blueberry", "citrus",
            "dragon-fruit-plants", "feijoa-fruit-trees", "figs-ficus-carica",
            "finger-limes", "fruit-trees", "guava", "kiwiberry-plants",
            "longan", "loquats", "macadamia", "mango", "mulberry",
            "olives", "passionfruit", "pear", "pomegranate", "raspberry",
            "tamarillo", "vanilla-fruit-trees-2",
        ],
    },
    "engalls": {
        # Engall's Nursery, Dural NSW. Citrus specialist — 70+ products including
        # specialty/rare varieties: Yuzu, Buddha's Hand, Calamansi, Sudachi, Etrog,
        # Bergamot, Rangpur Lime, Indonesian Lime, Chinotto, and more.
        # Does NOT ship to WA, NT, TAS, or parts of SA (quarantine restrictions).
        "name": "Engall's Nursery",
        "domain": "www.engalls.com.au",
        "location": "Dural, NSW",
        # Engall's tags oranges/mandarins/limes/lemons/etc. with only their
        # fruit-type leaf category (e.g. "dwarf-orange", "lime", "mandarin"),
        # which lack the "citrus" substring, and also stocks olives.
        # "citrus"/"dwarf-citrus" alone dropped ~15 real trees. Base slugs catch
        # their "dwarf-" variants via substring (e.g. "orange" -> "dwarf-orange").
        "fruit_categories": [
            "citrus", "dwarf-citrus", "speciality", "mandarin", "orange",
            "lime", "lemon", "grapefruit", "cumquat", "olives",
        ],
    },
    "rayners": {
        # Rayners Orchard, Yarra Valley VIC. Deep range of dwarf/multi-graft stone
        # fruit, pears, citrus, dozens of finger-lime cultivars, feijoas. ~290 trees.
        # Delivers within Victoria only (interstate for bulk 50+ orders).
        # Products are mostly UNcategorized (some tagged grow-your-own), so we do
        # NOT include-filter by category; instead we exclude the non-tree categories
        # (wines, preserves, gifts, tours, classes) and the one uncategorised
        # "Preserved Cherries" jar. Title-keyword junk filters can't be used here:
        # "wine" hits the Winesap apple, "honey" hits the Honey Murcott mandarin.
        "name": "Rayners Orchard",
        "domain": "www.raynersorchard.com.au",
        "location": "Yarra Valley, VIC",
        "exclude_categories": [
            "local-wines", "preserves-sauces-jams-honeys", "preserved-fruit",
            "preserving-goods", "gifts", "tour-operators", "classes",
        ],
        "exclude_title_keywords": ["preserved"],
    },
    "diacos": {
        # Diaco's Garden Nursery, Melbourne (Heatherton + other VIC stores).
        # Large general garden centre (~900 SKUs: ornamentals, hardware,
        # chemicals, pots). Fruit/edibles sit in one category, so we use
        # category_api mode to fetch only it rather than paginating the lot.
        # Melbourne-metro delivery + in-store pickup; no interstate (no WA/NT/TAS).
        "name": "Diaco's Garden Nursery",
        "domain": "diacos.com.au",
        "location": "Heatherton, VIC",
        "category_api": True,
        "fruit_categories": ["fruit-trees-and-edibles"],
    },
}

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "nursery-stock"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"
REQUEST_DELAY = 1.5


def fetch_json(url, health=None):
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
        if health:
            health.note_http_error(e.code, url)
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        if health:
            health.note_error(str(e))
        return None


def category_matches(cats, fruit_cats):
    """True if a product (with category slugs `cats`) belongs to one of the
    configured `fruit_cats`. A configured slug matches when it equals a product
    slug OR is a substring of one (so "stone-fruit" catches
    "stone-fruit-trees-bare-root-stock"). An empty `fruit_cats` means "keep all".

    Substring matching is why a nursery that tags products only with a leaf
    category (e.g. Guildford's "fig-tree", with no "fruits-nuts" parent) needs
    those leaf slugs listed explicitly, not just the parent.
    """
    if not fruit_cats:
        return True
    return any(fc in cats or any(fc in c for c in cats) for fc in fruit_cats)


def scrape_woocommerce(nursery_key, config, health=None):
    """Scrape all products from a WooCommerce store."""
    domain = config["domain"]
    fruit_cats = config.get("fruit_categories", [])
    excl_cats = set(config.get("exclude_categories", []))
    excl_kw = [k.lower() for k in config.get("exclude_title_keywords", [])]
    use_category_api = config.get("category_api", False)

    print(f"Scraping {config['name']} ({domain})...")

    if use_category_api:
        return _scrape_by_category(nursery_key, config, domain, fruit_cats, health)

    all_products = []
    page = 1
    per_page = 100

    while True:
        url = f"https://{domain}/wp-json/wc/store/v1/products?per_page={per_page}&page={page}"
        print(f"  Page {page}...", end=" ", flush=True)

        data = fetch_json(url, health)
        if data is None:
            print("failed")
            break

        if not data:
            print("empty (done)")
            break

        # Filter to fruit/edible categories only
        for product in data:
            cats = [c["slug"] for c in product.get("categories", [])]
            if not category_matches(cats, fruit_cats):
                continue
            # Exclude non-tree categories / titles (for stores without an
            # include-filter, e.g. Rayners: drop wines, preserves, gifts, tours).
            if excl_cats and any(c in excl_cats for c in cats):
                continue
            if excl_kw and any(k in product.get("name", "").lower() for k in excl_kw):
                continue
            all_products.append(product)

        print(f"{len(data)} products ({len(all_products)} fruit/edible)")

        if len(data) < per_page:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    print(f"  Total fruit/edible: {len(all_products)} products")
    return all_products


def _scrape_by_category(nursery_key, config, domain, fruit_cats, health=None):
    """Fetch products by iterating specific category slugs (for large stores)."""
    seen_ids = set()
    all_products = []
    per_page = 100

    for cat_slug in fruit_cats:
        page = 1
        cat_new = 0
        while True:
            url = (f"https://{domain}/wp-json/wc/store/v1/products"
                   f"?per_page={per_page}&page={page}&category={cat_slug}")
            data = fetch_json(url, health)
            if not data:
                break
            for product in data:
                pid = product.get("id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_products.append(product)
                    cat_new += 1
            if len(data) < per_page:
                break
            page += 1
            time.sleep(REQUEST_DELAY)
        print(f"  Category '{cat_slug}'... {cat_new} ({cat_new} new, {len(all_products)} total)")

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
    validate_and_warn(snapshot, nursery_key)

    snapshot_file = nursery_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    latest_file = nursery_dir / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"  Saved: {snapshot_file}")
    print(f"  In stock: {in_stock} / Out of stock: {len(normalized) - in_stock}")
    return snapshot


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
        health = ScrapeHealth(key)
        try:
            products = scrape_woocommerce(key, config, health)
            snapshot = save_snapshot(key, products, config) if products else None
        except Exception as e:
            health.note_error(repr(e))
            health.finish(ok=False)
            raise
        if snapshot:
            health.finish(products=snapshot["product_count"],
                          in_stock=snapshot["in_stock_count"])
        else:
            health.finish()
        print()


if __name__ == "__main__":
    main()
