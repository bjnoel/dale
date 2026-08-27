#!/usr/bin/env python3
"""
Squarespace Nursery Stock Scraper

Squarespace exposes any collection as JSON by appending `?format=json` to its
URL, so a store catalogue needs no HTML parsing at all: one request returns
every product with its variants, prices (in cents), SKUs and stock counts.

  https://<domain>/<shop path>?format=json&offset=<n>

Shape of a store item (verified against Perry's Fruit & Nut Nursery
2026-08-27): title, fullUrl, id, categoryIds, and a `variants` list where each
variant carries `price` (cents), `salePrice`, `sku`, `qtyInStock` and
`unlimited`.

Three gotchas, each of which cost a debugging round:

1. **Product-level price is a lie on multi-variant products.** `priceCents` is
   0 for anything with options -- Perry's "Lemon" reads 0 while its three pot
   sizes are $72/$110/$220. Price is read at the VARIANT level only, which is
   also the treestock house rule for comparing prices between snapshots.

2. **Pagination clamps instead of ending.** `offset` is a plain item index, but
   past the end of the collection it does not return an empty page: Perry's
   returns the single oldest product for offset=98, 99 and 100 alike. A
   loop-until-empty pager never terminates here. We instead dedupe on item id
   and stop as soon as a page contributes nothing new.

3. **`unlimited` means "stock not tracked", not "in stock forever".** Where a
   store leaves inventory untracked (63 of Perry's 107 variants) Squarespace
   reports no quantity at all. We treat unlimited as available, because that is
   what the storefront shows the buyer -- but it means the restock signal for
   those products is permanently on, and `untracked_variant_count` is recorded
   in the snapshot so downstream can see how much of a store that covers.

Usage:
  python3 squarespace_scraper.py                # Scrape all configured nurseries
  python3 squarespace_scraper.py perrys         # Scrape one nursery
  python3 squarespace_scraper.py --list         # List configured nurseries
"""

import html as _html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, date
from pathlib import Path

from stocklib.classify import is_real_product
from stocklib.model import validate_and_warn
from stocklib.scrape_health import count_priced, ScrapeHealth

# `exclude_pattern` is a per-store title filter for items that are real
# products but not nursery stock, and which the shared NON_PLANT_KEYWORDS
# filter cannot catch without risking other nurseries. Perry's sells its own
# jujube crop alongside the trees ("FRESH Jujube fruit", 5kg box; "Dried Jujube
# Fruit", 350g-2kg packets); both pass is_real_product because a jujube is a
# real fruit. Kept local rather than pushed into stocklib.classify: "dried" and
# "fresh" are too broad to apply to all 26 nurseries sight unseen.
NURSERIES = {
    "perrys": {
        "name": "Perry's Fruit & Nut Nursery",
        "domain": "perrysfruitnursery.com.au",
        "shop_path": "/shop",
        "location": "McLaren Flat, SA",
        "exclude_pattern": r"^(fresh|dried)\b.*\bfruit\b",
    },
}

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "nursery-stock"
USER_AGENT = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"
REQUEST_DELAY = 1.5   # seconds between collection pages -- be polite
PAGE_LIMIT = 40       # safety net; 40 pages of any page size is far past any nursery

from stocklib.retry import request_with_retry as _request  # noqa: E402

# If a store's catalogue comes back empty or unparseable we write nothing and
# keep the last good snapshot, rather than publishing what looks downstream
# like the whole nursery delisting overnight.
_TAG_RE = re.compile(r"<[^>]+>")


def _as_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip_html(text):
    """Reduce an HTML product body to clean plain text."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", _html.unescape(text)).strip()


def fetch_json(url, timeout=20, health=None, *, _opener=None, _sleep=time.sleep):
    """Fetch a Squarespace `?format=json` URL and return the parsed dict.

    Returns None on a fatal error, exhausted retries, or a body that is not
    JSON. Squarespace serves an HTML "Please Stand By" interstitial when it
    rate-limits or rejects a request, so a non-JSON body is a real failure
    rather than something to parse around."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/javascript,*/*",
    })
    raw = _request(req, timeout=timeout, health=health, _opener=_opener, _sleep=_sleep)
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        if health:
            health.note_error(f"non-JSON body from {url} (rate-limit interstitial?)")
        return None


def category_names(payload):
    """Map Squarespace category id -> display name from a collection payload.

    Only categories shown in the store's own nav appear here. Products can also
    carry an id that is in no active category (7 of Perry's 98, a mix of
    grapevines, a gift voucher and dried fruit), so callers must tolerate an
    unmapped id rather than assuming the lookup succeeds."""
    nested = payload.get("nestedCategories")
    if not isinstance(nested, dict):
        return {}
    return {
        c["id"]: c.get("displayName", "")
        for c in nested.get("categories", []) or []
        if isinstance(c, dict) and c.get("id")
    }


def extract_variant(raw):
    """Map one Squarespace variant to the snapshot's variant shape.

    Price is in cents. `salePrice` is what the buyer pays when the variant is
    on sale, and Squarespace sets it equal to `price` when it is not, so it is
    only trusted when it is actually lower."""
    price = _as_float(raw.get("price"))
    sale = _as_float(raw.get("salePrice"))
    effective = sale if (raw.get("onSale") and sale and price and sale < price) else price

    # `unlimited` = the store does not track stock for this variant, so the
    # storefront always offers it. `qtyInStock` is authoritative only when
    # stock IS tracked; it reads 0 on every untracked variant and treating that
    # as out-of-stock would mark most of the catalogue dead.
    unlimited = bool(raw.get("unlimited"))
    qty = raw.get("qtyInStock")
    available = unlimited or bool(qty and qty > 0)

    attrs = raw.get("attributes") or {}
    # Option names are the store owner's free text and are not normalised by
    # Squarespace: Perry's alone uses "Container", "container", "type",
    # "rootstock", "variety" and "Packet" across six products. Join the values
    # only, so the variant title is stable if the owner renames a label.
    title = " / ".join(str(v).strip() for v in attrs.values() if str(v).strip()) or "Default"

    return {
        "title": title,
        "price": effective / 100 if effective is not None else None,
        "sku": (raw.get("sku") or "").strip() or None,
        "id": raw.get("id"),
        "available": available,
        # None (not 0) where the store does not track stock, so downstream can
        # tell "none left" apart from "never counted".
        "stock_count": None if unlimited else qty,
    }


def extract_product(item, url, categories=None):
    """Map one Squarespace store item to the snapshot's product shape."""
    categories = categories or {}
    variants = [extract_variant(v) for v in (item.get("variants") or [])]

    prices = [v["price"] for v in variants if v["price"] is not None]
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None
    any_available = any(v["available"] for v in variants)

    cat = ""
    for cid in item.get("categoryIds") or []:
        if categories.get(cid):
            cat = categories[cid]
            break

    return {
        "title": (item.get("title") or "").strip(),
        "url": url,
        "id": item.get("id"),
        "description": _strip_html(item.get("body") or item.get("excerpt") or ""),
        "category": cat,
        # Both dialects' fields, as the other scrapers emit, so every builder
        # renders it without special-casing the platform.
        "price": min_price,
        "min_price": min_price,
        "max_price": max_price,
        "currency": "AUD",
        "available": any_available,
        "any_available": any_available,
        "availability_raw": "InStock" if any_available else "OutOfStock",
        "on_sale": bool(item.get("onSale")),
        "variants": variants,
    }


def scrape_squarespace(nursery_key, config, health=None, *, _fetch=None):
    """Scrape every product from a Squarespace store collection."""
    fetch = _fetch or (lambda u: fetch_json(u, health=health))
    domain = config["domain"]
    shop_path = config.get("shop_path", "/shop")
    base = f"https://{domain}{shop_path}"
    print(f"Scraping {config['name']} ({domain}) via Squarespace collection JSON...")

    exclude = config.get("exclude_pattern")
    exclude_re = re.compile(exclude, re.I) if exclude else None

    seen_ids = set()
    raw_items = []
    categories = {}
    offset = 0
    for page in range(PAGE_LIMIT):
        url = f"{base}?{urllib.parse.urlencode({'format': 'json', 'offset': offset})}"
        payload = fetch(url)
        if payload is None:
            if page == 0:
                print("  Could not fetch the store collection; aborting (keeping last snapshot)")
                if health:
                    health.note_error("store collection unfetchable")
                return []
            print(f"  Page {page + 1} failed; stopping with {len(raw_items)} products")
            break

        if not categories:
            categories = category_names(payload)

        items = payload.get("items") or []
        # The clamp described in the module docstring: past the end of the
        # collection Squarespace re-serves the last product instead of an empty
        # page, so "nothing new on this page" is the real end-of-collection
        # signal. Never `while items:`.
        fresh = [i for i in items if i.get("id") not in seen_ids]
        if not fresh:
            break
        for i in fresh:
            seen_ids.add(i.get("id"))
        raw_items.extend(fresh)
        offset += len(items)

        if len(fresh) < len(items):
            break
        time.sleep(config.get("delay", REQUEST_DELAY))

    if not raw_items:
        print("  No products in store collection; aborting (keeping last snapshot)")
        if health:
            health.note_error("store collection empty")
        return []

    products = []
    skipped = 0
    for item in raw_items:
        title = (item.get("title") or "").strip()
        if not title:
            skipped += 1
            continue
        if not is_real_product(title):
            skipped += 1
            continue
        if exclude_re and exclude_re.search(title):
            skipped += 1
            continue
        full_url = item.get("fullUrl") or ""
        url = f"https://{domain}{full_url}" if full_url.startswith("/") else full_url
        product = extract_product(item, url, categories)
        product["nursery"] = nursery_key
        product["nursery_name"] = config["name"]
        products.append(product)

    if skipped:
        print(f"  {skipped} non-stock items skipped (vouchers, produce)")

    products.sort(key=lambda p: p.get("title", ""))
    print(f"  Total: {len(products)} products scraped")
    return products


def save_snapshot(nursery_key, products, config):
    """Save a dated snapshot plus latest.json."""
    today = date.today().isoformat()
    nursery_dir = DATA_DIR / nursery_key
    nursery_dir.mkdir(parents=True, exist_ok=True)

    in_stock = [p for p in products if p["available"]]
    out_of_stock = [p for p in products if not p["available"]]
    untracked = sum(1 for p in products for v in p["variants"] if v["stock_count"] is None)

    snapshot = {
        "nursery": nursery_key,
        "nursery_name": config["name"],
        "location": config.get("location", ""),
        "scraped_at": datetime.now().isoformat(),
        "source": "squarespace",
        "product_count": len(products),
        "in_stock_count": len(in_stock),
        "out_of_stock_count": len(out_of_stock),
        # How much of this store reports no stock quantity at all. Those
        # products read "in stock" every single day, so a restock alert can
        # never fire for them and their availability history is not evidence.
        "untracked_variant_count": untracked,
        "products": products,
    }
    validate_and_warn(snapshot, nursery_key)

    with open(nursery_dir / f"{today}.json", "w") as f:
        json.dump(snapshot, f, indent=2)
    with open(nursery_dir / "latest.json", "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"  Saved: {nursery_dir / (today + '.json')}")
    print(f"  In stock: {len(in_stock)} / Out of stock: {len(out_of_stock)}")
    print(f"  Variants with no tracked quantity: {untracked}")


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            print("Configured Squarespace nurseries:")
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
        health = ScrapeHealth(key, source="squarespace")
        products = []
        try:
            products = scrape_squarespace(key, config, health)
            if products:
                save_snapshot(key, products, config)
        except Exception as e:
            health.note_error(repr(e))
            health.finish(ok=False)
            raise
        health.finish(products=len(products),
                      in_stock=sum(1 for p in products if p["available"]),
                      priced=count_priced(products))
        print()


if __name__ == "__main__":
    main()
