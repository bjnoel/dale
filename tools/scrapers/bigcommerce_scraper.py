#!/usr/bin/env python3
"""
Heritage Fruit Trees BigCommerce Scraper

Scrapes Heritage Fruit Trees (heritagefruittrees.com.au) - a BigCommerce store
specialising in heritage/heirloom apple, pear, plum, cherry, stone fruit and other
temperate trees. Does not ship to WA, TAS, or NT (accreditation discontinued Mar 2026).

Product format: In BigCommerce, each size/rootstock variant is a *separate product URL*
(e.g. /akane-apple-medium/ and /akane-apple-dwarf/ are two products). We treat each
as a separate product with a single "Default Title" variant.

Two ways in, fastest first:

1. Storefront GraphQL (primary, since 2026-09-23). Every Stencil page embeds a
   short-lived storefront token; with it, /graphql returns the whole catalogue
   (price, stock, purchasability, every category breadcrumb) in ~13 requests of
   50. The HTML path below took ~620 sequential page fetches and 1,240s a night,
   64% of the entire scrape run, for the same data.
2. Products sitemap + one HTML page per product (fallback). Used when the token
   is missing or GraphQL fails or comes back short, so a theme change degrades
   us to slow rather than to nothing.

Usage:
    python3 bigcommerce_scraper.py             # Scrape Heritage Fruit Trees
    python3 bigcommerce_scraper.py --dry-run   # List product URLs only, fetch no pages
    python3 bigcommerce_scraper.py --html      # Force the sitemap+HTML fallback path
"""

import html as html_module
import json
import os
import re
import sys
import time
import urllib.request
import zlib
from datetime import datetime, date
from pathlib import Path

from stocklib.jsonio import atomic_write_json
from stocklib.model import validate_and_warn
from stocklib.retry import request_with_retry
from stocklib.scrape_health import (ScrapeHealth, consecutive_failures,
                                    count_priced, last_success_day, should_probe)

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent / "data")) / "nursery-stock"
NURSERY_KEY = "heritage-fruit-trees"
NURSERY_NAME = "Heritage Fruit Trees"
BASE_URL = "https://www.heritagefruittrees.com.au"
GRAPHQL_URL = BASE_URL + "/graphql"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"

# Product discovery is driven by the store's products sitemap (the complete
# catalogue), NOT by walking a few top-level category listings. The old approach
# walked CATEGORIES = [fruit-trees, nut-trees, berries-and-vine-fruit] and relied
# on them rolling up their subcategories. They do not: /nut-trees/ lists only
# almonds+hazelnuts (walnuts/chestnuts are separate subcats), /berries-and-vine-
# fruit/ misses blueberries/kiwi-fruit/all-grape-varieties/currants/raspberries,
# and /fruit-trees/ misses ~50 apples in deeper apple subcategories. That
# silently dropped ~150 real fruit (all blueberries, walnuts, chestnuts, kiwi,
# grapes, medlar, loquat, plus a chunk of apples/pears/cherries). DEC-209,
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
# Slug fragments that are never trees (labels, workshops, tools, vouchers).
SKIP_SLUG_FRAGMENTS = ("label", "workshop", "class", "fertiliz", "secateur",
                       "gift-card", "gift-voucher")

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

REQUEST_DELAY = 1.5   # seconds between HTML page fetches (be polite)
GRAPHQL_DELAY = 1.0   # seconds between GraphQL pages
GRAPHQL_PAGE_SIZE = 50  # the Storefront API maximum
# GraphQL must return at least this share of the sitemap's product count, or
# we distrust it and take the slow path. A short answer is the dangerous one:
# it would publish as a successful scrape and read as mass delistings.
GRAPHQL_MIN_SHARE = 0.5

# A Stencil storefront token is an ES256 JWT embedded in every page.
_TOKEN_RE = re.compile(r"eyJ0eXAiOiJKV1Qi[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

GRAPHQL_QUERY = """query Catalogue($after: String) {
  site {
    products(first: %d, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node {
        entityId name path sku
        prices(includeTax: true) {
          price { value } basePrice { value } salePrice { value }
        }
        inventory { isInStock }
        availabilityV2 { status }
        categories { edges { node {
          breadcrumbs(depth: 5) { edges { node { name } } }
        } } }
      } }
    }
  }
}""" % GRAPHQL_PAGE_SIZE


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


def in_scope_all_categories(title, crumbs):
    """in_scope() for a product whose crumbs come from EVERY category it is in.

    A product page shows one breadcrumb; GraphQL lists all of them. The 20
    flowering crabapples are filed under both Fruit Trees > Crabapples and
    Ornamental Plants > Flowering Trees, and their page breadcrumb was the
    ornamental one, so the HTML path always left them out. With every category
    visible, Fruit Trees would win. An ornamental-looking title that is ALSO
    filed as ornamental stays out; a fruiting crab apple filed only under Fruit
    Trees (Huonville Crab Apple) stays in, exactly as before.
    """
    lower = {c.lower() for c in crumbs}
    tl = title.lower()
    # "crab" not just "crabapple": Sonning Crab (Malus x purpurea) is one of
    # the dual-listed flowering forms and its title never says crabapple.
    if lower & EXCLUDE_TOP_CATEGORIES and any(g in tl for g in _ORNAMENTAL_GUARD + ("crab",)):
        return False
    return in_scope(title, crumbs)


def is_junk(slug, title):
    """Labels, workshops, tools, vouchers: never trees, whatever their category."""
    if any(kw in slug for kw in SKIP_SLUG_FRAGMENTS):
        return True
    return any(kw in title.lower() for kw in NON_PLANT_KEYWORDS)


def variant_id_for(url):
    """Deterministic synthetic id for an HTML-path product.

    This used to be hash(url) & 0x7FFFFFFF. Python randomises str hashes per
    process (PYTHONHASHSEED), so on 2026-09-22 vs 09-23 0 of 378 ids matched.
    Nothing broke only because every consumer keys on the sku first."""
    return zlib.crc32(url.encode("utf-8")) & 0x7FFFFFFF


def build_product(slug, title, price_float, in_stock, variant_id, compare_at=None):
    """One snapshot product in the shape every other scraper writes.

    The variant sku is the URL slug, and it must stay that way: the
    availability history keys on url|sku:<slug>, so changing it would fork every
    Heritage product's history into a new one."""
    price = f"{price_float:.2f}" if price_float is not None else None
    on_sale = bool(compare_at and price_float is not None and compare_at > price_float)
    return {
        "nursery": NURSERY_KEY,
        "nursery_name": NURSERY_NAME,
        "title": title,
        "handle": slug,
        "url": f"{BASE_URL}/{slug}/",
        "product_type": "",
        "tags": [],
        "created_at": None,
        "updated_at": None,
        "variants": [{
            "id": variant_id,
            "title": "Default Title",
            "price": price,
            "compare_at_price": f"{compare_at:.2f}" if on_sale else None,
            "available": in_stock,
            "sku": slug,
        }],
        "min_price": price_float,
        "max_price": price_float,
        "any_available": in_stock,
        "on_sale": on_sale,
    }


# --------------------------------------------------------------------------
# Path 1: Storefront GraphQL
# --------------------------------------------------------------------------

def extract_storefront_token(page_html):
    """The storefront JWT embedded in a Stencil page, or None."""
    if not page_html:
        return None
    m = _TOKEN_RE.search(page_html)
    return m.group(0) if m else None


def _graphql_page(token, after, health=None, *, _opener=None, _sleep=time.sleep):
    """One page of the catalogue query. Returns the `products` connection dict,
    or None on transport failure or a GraphQL error payload."""
    body = json.dumps({"query": GRAPHQL_QUERY, "variables": {"after": after}}).encode()
    req = urllib.request.Request(GRAPHQL_URL, data=body, method="POST", headers={
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    raw = request_with_retry(req, timeout=30, health=health, _opener=_opener, _sleep=_sleep)
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except ValueError as e:
        print(f"  GraphQL returned non-JSON: {e}")
        return None
    if payload.get("errors"):
        print(f"  GraphQL errors: {str(payload['errors'])[:200]}")
        return None
    try:
        return payload["data"]["site"]["products"]
    except (KeyError, TypeError):
        print("  GraphQL response missing data.site.products")
        return None


def fetch_graphql_catalog(token, health=None, *, _opener=None, _sleep=time.sleep):
    """Every product node in the store, or None if any page failed.

    All-or-nothing on purpose: a catalogue missing its last few pages would be
    published as a successful scrape and read downstream as delistings."""
    nodes, after, page = [], None, 0
    while True:
        page += 1
        conn = _graphql_page(token, after, health, _opener=_opener, _sleep=_sleep)
        if conn is None:
            print(f"  GraphQL page {page} failed")
            return None
        edges = conn.get("edges") or []
        nodes.extend(e["node"] for e in edges if e.get("node"))
        info = conn.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            break
        after = info.get("endCursor")
        if not after:
            print(f"  GraphQL page {page} says hasNextPage but gave no cursor")
            return None
        _sleep(GRAPHQL_DELAY)
    print(f"  GraphQL: {len(nodes)} products in {page} requests")
    return nodes


def node_crumbs(node):
    """Every category breadcrumb name on a GraphQL product node, deduplicated
    in order, without Home/Shop."""
    crumbs = []
    for cat in (node.get("categories") or {}).get("edges") or []:
        bc = ((cat.get("node") or {}).get("breadcrumbs") or {}).get("edges") or []
        for b in bc:
            name = html_module.unescape(((b.get("node") or {}).get("name") or "").strip())
            if name and name.lower() not in ("home", "shop") and name not in crumbs:
                crumbs.append(name)
    return crumbs


def _money(obj):
    try:
        v = (obj or {}).get("value")
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_graphql_node(node):
    """Normalise one GraphQL product node, or None if it is junk/out of scope.

    Availability is stock AND purchasable. BigCommerce keeps them apart: on
    2026-09-23 Heritage had 53 products with isInStock=true and
    availabilityV2.status="Unavailable" (online sales closed for 2026; the site
    says to register for 2027 stock alerts). The HTML path read only BCData
    `instock`, so treestock showed those 53 as buyable."""
    slug = (node.get("path") or "").strip("/")
    if not slug or "/" in slug or slug in SKIP_SLUGS:
        return None
    title = html_module.unescape((node.get("name") or "").strip()) or slug.replace("-", " ").title()
    if is_junk(slug, title):
        return None
    if not in_scope_all_categories(title, node_crumbs(node)):
        return None

    prices = node.get("prices") or {}
    price = _money(prices.get("price"))
    base = _money(prices.get("basePrice"))
    in_stock = bool((node.get("inventory") or {}).get("isInStock"))
    purchasable = ((node.get("availabilityV2") or {}).get("status") == "Available")
    return build_product(slug, title, price, in_stock and purchasable,
                         node.get("entityId") or variant_id_for(f"{BASE_URL}/{slug}/"),
                         compare_at=base)


def scrape_graphql(expected_count, health=None, *, _opener=None, _sleep=time.sleep):
    """Products via GraphQL, or None if the caller should fall back to HTML."""
    home = fetch_html(BASE_URL + "/", delay=False, health=health, _opener=_opener, _sleep=_sleep)
    token = extract_storefront_token(home)
    if not token:
        print("  No storefront token on the homepage; falling back to HTML pages")
        if health:
            health.note_error("storefront token not found; used HTML fallback")
        return None
    nodes = fetch_graphql_catalog(token, health, _opener=_opener, _sleep=_sleep)
    if nodes is None:
        if health:
            health.note_error("GraphQL catalogue failed; used HTML fallback")
        return None
    if expected_count and len(nodes) < GRAPHQL_MIN_SHARE * expected_count:
        print(f"  GraphQL returned {len(nodes)} products against {expected_count} "
              f"in the sitemap; distrusting it, falling back to HTML pages")
        if health:
            health.note_error(f"GraphQL short ({len(nodes)}/{expected_count}); used HTML fallback")
        return None
    products = [p for p in (parse_graphql_node(n) for n in nodes) if p]
    print(f"  In scope: {len(products)} of {len(nodes)}")
    return products


# --------------------------------------------------------------------------
# Path 2: products sitemap + one HTML page per product (fallback)
# --------------------------------------------------------------------------

class _NotFoundIsNotAnError:
    """Health proxy: a 404 on a sitemap-listed product URL is a delisting, not
    a scrape fault, so it must not count toward the 403/429 block alarms."""

    def __init__(self, health):
        self._health = health

    def note_http_error(self, code, url=""):
        if code != 404 and self._health:
            self._health.note_http_error(code, url)

    def note_error(self, message):
        if self._health:
            self._health.note_error(message)


def fetch_html(url, delay=True, health=None, *, _opener=None, _sleep=time.sleep):
    """Fetch HTML with retry on transient failures. None on failure or 404."""
    if delay:
        _sleep(REQUEST_DELAY)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
    })
    raw = request_with_retry(req, timeout=30, health=_NotFoundIsNotAnError(health),
                             _opener=_opener, _sleep=_sleep)
    return raw.decode("utf-8", errors="replace") if raw is not None else None


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

    # In stock is not the same as buyable. BCData carries both, and with
    # online sales closed Heritage had 53 lines at instock:true,
    # purchasable:false (see parse_graphql_node).
    m = re.search(r'"purchasable"\s*:\s*(true|false)', html)
    if m and m.group(1) == "false":
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


def get_all_product_urls(health=None, *, _opener=None, _sleep=time.sleep):
    """Collect every product URL from the store's products sitemap (the complete
    catalogue). Products are single-path-segment slugs; nav/category/page slugs
    and known SKIP_SLUGS are filtered out (the breadcrumb scope filter and the
    title junk filter handle the rest downstream)."""
    paths = []
    seen = set()
    page = 1
    while True:
        url = PRODUCTS_SITEMAP.format(page=page)
        html = fetch_html(url, delay=(page > 1), health=health, _opener=_opener, _sleep=_sleep)
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


def scrape_html(all_product_paths, health=None):
    """Products via one HTML page fetch each (slow: ~2s a product)."""
    print(f"\nFetching {len(all_product_paths)} product pages...")
    products = []
    skipped = 0
    out_of_scope = 0

    for i, product_path in enumerate(all_product_paths):
        slug = product_path.strip("/")
        print(f"  [{i+1}/{len(all_product_paths)}] /{slug}/", end=" ", flush=True)

        if any(kw in slug for kw in SKIP_SLUG_FRAGMENTS):
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

        url = f"{BASE_URL}{product_path}"
        product = build_product(slug, data["title"], data["price_float"],
                                data["in_stock"], variant_id_for(url))
        status = "✓" if data["in_stock"] else "✗"
        price_str = f"${data['price_float']:.2f}" if data["price_float"] else "?"
        print(f"{status} {data['title'][:45]:<45} {price_str}")
        products.append(product)

    print(f"Skipped (junk):   {skipped}")
    print(f"Out of scope:     {out_of_scope}")
    return products


def scrape(dry_run=False, health=None, force_html=False):
    """Main scrape function. Returns list of normalized products."""
    print(f"\nScraping {NURSERY_NAME} ({BASE_URL})")
    print("=" * 60)

    # The sitemap is one request, and it is both the HTML path's work list and
    # the yardstick that tells us whether GraphQL answered in full.
    print("\nFetching products sitemap...")
    all_product_paths = get_all_product_urls(health)
    print(f"\nTotal product URLs from sitemap: {len(all_product_paths)}")

    if dry_run:
        print("\n[DRY RUN] Skipping product fetches.")
        for p in all_product_paths[:10]:
            print(f"  {BASE_URL}{p}")
        return []

    products = None
    if not force_html:
        print("\nFetching catalogue via Storefront GraphQL...")
        products = scrape_graphql(len(all_product_paths), health)
    if products is None:
        products = scrape_html(all_product_paths, health)

    print(f"\n{'='*60}")
    print(f"Products scraped: {len(products)}")
    print(f"In stock:         {sum(1 for p in products if p['any_available'])}")
    print(f"Out of stock:     {sum(1 for p in products if not p['any_available'])}")
    return products


def save_snapshot(products):
    """Save dated snapshot in standard nursery-stock format."""
    today = date.today().isoformat()
    nursery_dir = DATA_DIR / NURSERY_KEY

    snapshot = {
        "nursery": NURSERY_KEY,
        "nursery_name": NURSERY_NAME,
        "scraped_at": datetime.now().isoformat(),
        "source": "bigcommerce",
        "product_count": len(products),
        "in_stock_count": sum(1 for p in products if p["any_available"]),
        "out_of_stock_count": sum(1 for p in products if not p["any_available"]),
        "products": products,
    }
    validate_and_warn(snapshot, NURSERY_KEY)

    snapshot_file = atomic_write_json(nursery_dir / f"{today}.json", snapshot)
    print(f"\nSaved: {snapshot_file}")
    latest_file = atomic_write_json(nursery_dir / "latest.json", snapshot)
    print(f"Saved: {latest_file}")

    return snapshot


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    force_html = "--html" in sys.argv
    today = date.today().isoformat()

    # A closed store is not a broken scraper. Heritage shut online sales for
    # 2026 on 2026-08-24 and every URL, sitemap included, served HTTP 503 for
    # days. A nightly run walked the whole known catalogue into that wall: the
    # 08-24 run spent 357s doing exactly that. Left alone until the 2027 season
    # that is tens of thousands of pointless requests at a nursery Benedict has
    # a relationship with, and scraping has cost us goodwill before (Beewise,
    # DEC-198).
    #
    # Skipping writes no health record, which untrusted_nurseries() already
    # reads as "do not believe this nursery's absences today", so the ledger
    # and the alerts stay protected. Exit 0, not 1: this is a decision, not a
    # failure, and it must not count against run-all-scrapers.sh's failure floor.
    if not dry_run and not force and not should_probe(NURSERY_KEY, today):
        streak = consecutive_failures(NURSERY_KEY, today)
        last_ok = last_success_day(NURSERY_KEY, today) or "never"
        print(f"{NURSERY_NAME} looks dormant: {streak} failed runs in a row, "
              f"last good scrape {last_ok}. Probing weekly (Mondays); "
              f"skipping today. Use --force to override.")
        sys.exit(0)

    health = ScrapeHealth(NURSERY_KEY, source="bigcommerce") if not dry_run else None
    try:
        products = scrape(dry_run=dry_run, health=health, force_html=force_html)
        if products:
            save_snapshot(products)
    except Exception as e:
        if health:
            health.note_error(repr(e))
            health.finish(ok=False)
        raise
    if products:
        health.finish(products=len(products),
                      in_stock=sum(1 for p in products if p["any_available"]),
                      priced=count_priced(products))
    elif not dry_run:
        health.finish(ok=False)
        print("\nNo products scraped. Check for blocking or site structure changes.")
        sys.exit(1)
