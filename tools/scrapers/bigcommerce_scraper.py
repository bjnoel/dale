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

from stocklib.model import validate_and_warn
from stocklib.scrape_health import ScrapeHealth

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent / "data")) / "nursery-stock"
NURSERY_KEY = "heritage-fruit-trees"
NURSERY_NAME = "Heritage Fruit Trees"
BASE_URL = "https://www.heritagefruittrees.com.au"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"

# Product discovery is driven by the store's products sitemap (the complete
# catalogue), NOT by walking a few top-level category listings. The old approach
# walked CATEGORIES = [fruit-trees, nut-trees, berries-and-vine-fruit] and relied
# on them rolling up their subcategories. They do not: /nut-trees/ lists only
# almonds+hazelnuts (walnuts/chestnuts are separate subcats), /berries-and-vine-
# fruit/ misses blueberries/kiwi-fruit/all-grape-varieties/currants/raspberries,
# and /fruit-trees/ misses ~50 apples in deeper apple subcategories. That
# silently dropped ~150 real fruit (all blueberries, walnuts, chestnuts, kiwi,
# grapes, medlar, loquat, plus a chunk of apples/pears/cherries). DEC-208,
# follow-up to the WooCommerce leaf-category gap (DEC-207).
PRODUCTS_SITEMAP = BASE_URL + "/xmlsitemap.php?type=products&page={page}"

# Whether a product is in scope is decided from its breadcrumb (the store's own
# authoritative categorisation), not from guessed title keywords.
FRUIT_TOP_CATEGORIES = {"fruit trees", "nut trees", "berries and vine fruit"}
EXCLUDE_TOP_CATEGORIES = {
    "ornamental plants", "non plant products", "workshops", "rootstocks",
}

# Known non-product / out-of-scope URL slugs to skip (navigation, pages, etc.)
SKIP_SLUGS = {
    "fruit-trees", "nut-trees", "berries-and-vine-fruit", "blueberries",
    "kiwi-fruit", "all-grape-varieties", "ornamental-plants", "rootstocks",
    "gift-vouchers", "faqs", "about-us", "contact-us", "blog", "cart",
    "search", "account", "login", "sitemap", "ordering-information",
    "shipping-information", "privacy-policy", "returns-policy",
}

# Title keywords that indicate non-plant items to skip
from stocklib.classify import NON_PLANT_KEYWORDS
from stocklib.taxonomy import load_species, ENABLED_CATEGORIES


def _enabled_fruit_names():
    """Common names + aliases of every enabled (fruit/nut/berry/bush-tucker)
    species, lowercased. Used only as a fallback to classify products whose
    primary breadcrumb is a cross-cut category like "Specials"."""
    names = set()
    for r in load_species():
        cat = r.get("category", "fruit")
        tags = r.get("tags", [])
        if cat in ENABLED_CATEGORIES or any(t in ENABLED_CATEGORIES for t in tags):
            for n in [r.get("common_name", "")] + (r.get("aliases", []) or []):
                n = n.strip().lower()
                if n:
                    names.add(n)
    return names


FRUIT_NAMES = _enabled_fruit_names()
# Ornamental look-alikes a bare fruit-name match must NOT rescue (a crab/
# flowering form is ornamental, not edible stock).
_ORNAMENTAL_GUARD = ("crabapple", "crab apple", "flowering", "ornamental")

REQUEST_DELAY = 1.5  # seconds between requests (be polite)


def extract_breadcrumbs(page_html):
    """Category breadcrumb names for a BigCommerce product page (schema.org
    BreadcrumbList microdata), excluding Home/Shop and the product title.
    Returns [] if not found."""
    if not page_html:
        return []
    m = re.search(r"BreadcrumbList.*?</(?:ul|nav|ol)>", page_html, re.S)
    block = m.group(0) if m else ""
    names = re.findall(r'itemprop=["\']name["\'][^>]*>\s*([^<]+?)\s*<', block)
    crumbs = [html_module.unescape(n.strip()) for n in names if n.strip()]
    return [c for c in crumbs if c.lower() not in ("home", "shop")]


def in_scope(title, crumbs):
    """True if a product belongs in the fruit/nut/berry dataset.

    Decided from the breadcrumb category (authoritative), with a taxonomy
    fallback for products whose *primary* breadcrumb is a cross-cut like
    "Specials" / "Almost Sold Out" (those carry no fruit category, yet most are
    real fruit on clearance):

      - breadcrumb names a fruit/nut/berry top category   -> in scope
      - breadcrumb names ornamental/non-plant/workshop/rootstock -> out
      - otherwise: in scope only if the title matches a known fruit/nut/berry
        species and is not an ornamental look-alike (e.g. crabapple).
    """
    lower = [c.lower() for c in crumbs]
    if any(c in FRUIT_TOP_CATEGORIES for c in lower):
        return True
    if any(c in EXCLUDE_TOP_CATEGORIES for c in lower):
        return False
    tl = title.lower()
    if any(g in tl for g in _ORNAMENTAL_GUARD):
        return False
    return any(re.search(r"\b%s\b" % re.escape(n), tl) for n in FRUIT_NAMES)


def fetch_html(url, delay=True, health=None):
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
            return None  # expected for guessed product URLs; not a health event
        print(f"  HTTP {e.code} fetching {url}")
        if health:
            health.note_http_error(e.code, url)
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        if health:
            health.note_error(str(e))
        return None


def get_product_urls_from_category(category_slug, health=None):
    """Paginate through a BigCommerce category and collect product URLs."""
    urls = []
    page = 1

    while True:
        url = f"{BASE_URL}/{category_slug}/?page={page}"
        html = fetch_html(url, delay=(page > 1), health=health)
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


def get_all_product_urls(health=None):
    """Collect every product URL from the store's products sitemap (the complete
    catalogue). Replaces the old category-walk discovery, which silently missed
    fruit in subcategories the three top-level listings did not roll up
    (DEC-208). Products are single-path-segment slugs; nav/category/page slugs
    and known SKIP_SLUGS are filtered out (the breadcrumb scope filter and the
    title junk filter handle the rest downstream)."""
    paths = []
    seen = set()
    page = 1
    while True:
        url = PRODUCTS_SITEMAP.format(page=page)
        html = fetch_html(url, delay=(page > 1), health=health)
        if not html:
            break
        locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", html)
        if not locs:
            break
        new = 0
        for loc in locs:
            slug = loc.replace(BASE_URL, "").strip().strip("/")
            # products are single-segment slugs; skip categories/nav/junk
            if not slug or "/" in slug or slug in SKIP_SLUGS:
                continue
            if slug not in seen:
                seen.add(slug)
                paths.append("/" + slug + "/")
                new += 1
        print(f"  sitemap page {page}: {len(locs)} locs, {new} new product URLs")
        page += 1
    return paths


def scrape(dry_run=False, health=None):
    """Main scrape function. Returns list of normalized products."""
    print(f"\nScraping {NURSERY_NAME} ({BASE_URL})")
    print("=" * 60)

    # Step 1: Collect every product URL from the products sitemap.
    print("\nFetching products sitemap...")
    all_product_paths = get_all_product_urls(health)

    print(f"\nTotal product URLs from sitemap: {len(all_product_paths)}")

    if dry_run:
        print("\n[DRY RUN] Skipping individual product page fetches.")
        for p in all_product_paths[:10]:
            print(f"  {BASE_URL}{p}")
        return []

    # Step 2: Fetch each product page for price + stock data
    print(f"\nFetching {len(all_product_paths)} product pages...")
    products = []
    skipped = 0
    out_of_scope = 0

    for i, product_path in enumerate(all_product_paths):
        slug = product_path.strip("/")
        print(f"  [{i+1}/{len(all_product_paths)}] /{slug}/", end=" ", flush=True)

        # Pre-filter by slug
        if any(kw in slug for kw in ["label", "workshop", "class", "fertiliz", "secateur", "gift-card", "gift-voucher"]):
            print("skip (slug filter)")
            skipped += 1
            continue

        html = fetch_html(f"{BASE_URL}{product_path}", health=health)
        data = parse_product_page(product_path, html)

        if data is None:
            print("skip (non-plant or no data)")
            skipped += 1
            continue

        # Scope filter: keep fruit/nut/berry only, by the store's own breadcrumb
        # category (ornamentals/non-plant/workshops/rootstocks are excluded).
        crumbs = extract_breadcrumbs(html)
        if not in_scope(data["title"], crumbs):
            print(f"skip (out of scope: {crumbs[:2] or data['title'][:30]})")
            out_of_scope += 1
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
    print(f"Skipped (junk):   {skipped}")
    print(f"Out of scope:     {out_of_scope}")
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
    validate_and_warn(snapshot, NURSERY_KEY)

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
    health = ScrapeHealth(NURSERY_KEY) if not dry_run else None
    try:
        products = scrape(dry_run=dry_run, health=health)
        if products:
            save_snapshot(products)
    except Exception as e:
        if health:
            health.note_error(repr(e))
            health.finish(ok=False)
        raise
    if products:
        health.finish(products=len(products),
                      in_stock=sum(1 for p in products if p["any_available"]))
    elif not dry_run:
        health.finish(ok=False)
        print("\nNo products scraped. Check for blocking or site structure changes.")
        sys.exit(1)
