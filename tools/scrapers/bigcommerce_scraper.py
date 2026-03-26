#!/usr/bin/env python3
"""
Heritage Fruit Trees BigCommerce Scraper

Scrapes Heritage Fruit Trees (heritagefruittrees.com.au) - a BigCommerce store
specialising in heritage/heirloom apple, pear, plum, cherry, stone fruit and other
temperate trees. Does not ship to WA, TAS, or NT (accreditation discontinued Mar 2026).

Product format: In BigCommerce, each size/rootstock variant is a *separate product URL*
(e.g. /akane-apple-medium/ and /akane-apple-dwarf/ are two products). We treat each
as a separate product with a single "Default Title" variant.

Usage:
    python3 bigcommerce_scraper.py             # Scrape Heritage Fruit Trees
    python3 bigcommerce_scraper.py --dry-run   # Parse URLs only, don't fetch product pages
"""

import html as html_module
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent / "data")) / "nursery-stock"
NURSERY_KEY = "heritage-fruit-trees"
NURSERY_NAME = "Heritage Fruit Trees"
BASE_URL = "https://www.heritagefruittrees.com.au"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"

# Category slugs to scrape (fruit/nut/berry only — excludes ornamentals)
CATEGORIES = [
    "fruit-trees",
    "nut-trees",
    "berries-and-vine-fruit",
]

# Known non-product URL slugs to skip (navigation, pages, etc.)
SKIP_SLUGS = {
    "fruit-trees", "nut-trees", "berries-and-vine-fruit", "blueberries",
    "kiwi-fruit", "all-grape-varieties", "ornamental-plants", "rootstocks",
    "gift-vouchers", "faqs", "about-us", "contact-us", "blog", "cart",
    "search", "account", "login", "sitemap", "ordering-information",
    "shipping-information", "privacy-policy", "returns-policy",
}

# Title keywords that indicate non-plant items to skip
NON_PLANT_KEYWORDS = [
    "label", "labels", "workshop", "class", "ticket",
    "fertilizer", "fertiliser", "secateur", "pruning",
    "shipping", "postage", "freight", "delivery",
    "gift card", "gift voucher", "gift certificate",
    "orchard kit", "grafting tape", "budding tape",
]

REQUEST_DELAY = 1.5  # seconds between requests (be polite)


def fetch_html(url, delay=True):
    """Fetch HTML from URL with proper headers."""
    if delay:
        time.sleep(REQUEST_DELAY)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  HTTP {e.code} fetching {url}")
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def get_product_urls_from_category(category_slug):
    """Paginate through a BigCommerce category and collect product URLs."""
    urls = []
    page = 1

    while True:
        url = f"{BASE_URL}/{category_slug}/?page={page}"
        html = fetch_html(url, delay=(page > 1))
        if not html:
            print(f"    page {page}: failed")
            break

        # BigCommerce uses absolute URLs in listing pages
        base_escaped = re.escape(BASE_URL)

        # Find product links via "Choose Options" / "Add to Cart" buttons — one per product
        choose_options = re.findall(
            rf'href="({base_escaped}/[a-z0-9][a-z0-9\-]+/)"[^>]*>\s*(?:Choose Options|Add to Cart)',
            html
        )

        if not choose_options:
            # Fallback: links in h4/h2 tags (product title links)
            choose_options = re.findall(
                rf'<h[24][^>]*>\s*<a\s+href="({base_escaped}/[a-z0-9][a-z0-9\-]+/)"',
                html
            )

        if not choose_options:
            # Fallback: any absolute product URL in the listing
            choose_options = re.findall(
                rf'href="({base_escaped}/[a-z0-9][a-z0-9\-]{{3,}}/)"',
                html
            )

        # Extract just the path component and filter known non-product slugs
        new_urls = []
        for u in choose_options:
            path = u.replace(BASE_URL, "")
            if path.strip("/") not in SKIP_SLUGS:
                new_urls.append(path)
        new_urls = list(dict.fromkeys(new_urls))  # deduplicate

        print(f"    page {page}: {len(new_urls)} products", end="")
        urls.extend(new_urls)

        # Check if next page exists
        if f"page={page + 1}" in html:
            page += 1
            print()
        else:
            print(" (last page)")
            break

    return list(dict.fromkeys(urls))  # deduplicate across pages


def parse_product_page(product_path, html):
    """Extract title, price, and stock status from a product page."""
    if not html:
        return None

    # Title: try h1.productView-title, then any h1
    title = None
    for pattern in [
        r'<h1[^>]*class="[^"]*productView-title[^"]*"[^>]*>\s*([^<]+)',
        r'class="productView-title"[^>]*>\s*<span[^>]*>\s*([^<]+)',
        r'<h1[^>]*>\s*([^<]{3,80})',
    ]:
        m = re.search(pattern, html)
        if m:
            title = m.group(1).strip()
            # Remove HTML entities
            title = html_module.unescape(title)
            if title and len(title) > 2:
                break

    if not title:
        # Last resort: use the URL slug
        title = product_path.strip("/").replace("-", " ").title()

    # Skip obvious non-plant items
    title_lower = title.lower()
    if any(kw in title_lower for kw in NON_PLANT_KEYWORDS):
        return None

    # Price: from schema.org JSON-LD (most reliable)
    price = None
    ld_matches = re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    for ld_text in ld_matches:
        try:
            ld = json.loads(ld_text.strip())
            if isinstance(ld, dict) and ld.get("@type") == "Product":
                offers = ld.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0]
                p = offers.get("price") or ld.get("price")
                if p:
                    price = str(p)
                    break
        except (json.JSONDecodeError, KeyError, IndexError):
            continue

    if not price:
        # Fallback: BCData price
        m = re.search(r'"price"\s*:\s*"([0-9]+\.[0-9]+)"', html)
        if m:
            price = m.group(1)

    # Stock status: from BCData.instock (most reliable for BigCommerce)
    in_stock = True  # default optimistic
    m = re.search(r'"instock"\s*:\s*(true|false)', html)
    if m:
        in_stock = m.group(1) == "true"
    else:
        # Fallback: schema.org availability
        m = re.search(r'"availability"\s*:\s*"https://schema\.org/([^"]+)"', html)
        if m:
            in_stock = m.group(1) == "InStock"
        else:
            # If "Out of Stock" text visible, mark as out of stock
            if "out of stock" in html.lower() or "notify me" in html.lower():
                in_stock = False

    price_float = None
    if price:
        try:
            price_float = float(price)
        except ValueError:
            price = None

    return {
        "title": title,
        "price": price,
        "price_float": price_float,
        "in_stock": in_stock,
    }


def scrape(dry_run=False):
    """Main scrape function. Returns list of normalized products."""
    print(f"\nScraping {NURSERY_NAME} ({BASE_URL})")
    print("=" * 60)

    # Step 1: Collect product URLs from all relevant categories
    all_product_paths = []
    seen = set()
    for category in CATEGORIES:
        print(f"\nCategory: /{category}/")
        paths = get_product_urls_from_category(category)
        for p in paths:
            if p not in seen:
                seen.add(p)
                all_product_paths.append(p)
        print(f"  Subtotal: {len(paths)} URLs ({len(all_product_paths)} unique total)")

    print(f"\nTotal unique product URLs: {len(all_product_paths)}")

    if dry_run:
        print("\n[DRY RUN] Skipping individual product page fetches.")
        for p in all_product_paths[:10]:
            print(f"  {BASE_URL}{p}")
        return []

    # Step 2: Fetch each product page for price + stock data
    print(f"\nFetching {len(all_product_paths)} product pages...")
    products = []
    skipped = 0

    for i, product_path in enumerate(all_product_paths):
        slug = product_path.strip("/")
        print(f"  [{i+1}/{len(all_product_paths)}] /{slug}/", end=" ", flush=True)

        # Pre-filter by slug
        if any(kw in slug for kw in ["label", "workshop", "class", "fertiliz", "secateur", "gift-card", "gift-voucher"]):
            print("skip (slug filter)")
            skipped += 1
            continue

        html = fetch_html(f"{BASE_URL}{product_path}")
        data = parse_product_page(product_path, html)

        if data is None:
            print("skip (non-plant or no data)")
            skipped += 1
            continue

        price = data["price"]
        price_float = data["price_float"]
        in_stock = data["in_stock"]
        title = data["title"]

        # Synthetic variant ID (stable hash of URL)
        variant_id = hash(f"{BASE_URL}{product_path}") & 0x7FFFFFFF

        product = {
            "nursery": NURSERY_KEY,
            "nursery_name": NURSERY_NAME,
            "title": title,
            "handle": slug,
            "url": f"{BASE_URL}{product_path}",
            "product_type": "",
            "tags": [],
            "created_at": None,
            "updated_at": None,
            "variants": [{
                "id": variant_id,
                "title": "Default Title",
                "price": price,
                "compare_at_price": None,
                "available": in_stock,
                "sku": slug,  # use slug as SKU for stable variant tracking
            }],
            "min_price": price_float,
            "max_price": price_float,
            "any_available": in_stock,
            "on_sale": False,
        }

        status = "✓" if in_stock else "✗"
        price_str = f"${price_float:.2f}" if price_float else "?"
        print(f"{status} {title[:45]:<45} {price_str}")
        products.append(product)

    print(f"\n{'='*60}")
    print(f"Products scraped: {len(products)}")
    print(f"Skipped:          {skipped}")
    print(f"In stock:         {sum(1 for p in products if p['any_available'])}")
    print(f"Out of stock:     {sum(1 for p in products if not p['any_available'])}")

    return products


def save_snapshot(products):
    """Save dated snapshot in standard nursery-stock format."""
    today = date.today().isoformat()
    nursery_dir = DATA_DIR / NURSERY_KEY
    nursery_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "nursery": NURSERY_KEY,
        "nursery_name": NURSERY_NAME,
        "scraped_at": datetime.now().isoformat(),
        "product_count": len(products),
        "in_stock_count": sum(1 for p in products if p["any_available"]),
        "out_of_stock_count": sum(1 for p in products if not p["any_available"]),
        "products": products,
    }

    snapshot_file = nursery_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"\nSaved: {snapshot_file}")

    latest_file = nursery_dir / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"Saved: {latest_file}")

    return snapshot


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    products = scrape(dry_run=dry_run)
    if products:
        save_snapshot(products)
    elif not dry_run:
        print("\nNo products scraped. Check for blocking or site structure changes.")
        sys.exit(1)
