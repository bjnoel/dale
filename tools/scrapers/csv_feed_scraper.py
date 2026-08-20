#!/usr/bin/env python3
"""Supplier CSV feed scraper.

Some nurseries will hand us a product feed rather than make us parse their
storefront. Daleys is the first (Correy, 2026-08-20). This reader is generic on
purpose: a second nursery offering a feed should be a FEEDS entry plus a test
fixture, not a second script.

Why a feed beats the HTML scrape it replaces, measured 2026-08-20 against the
Plant-List.php snapshot of the same morning:

  - Plant-List.php only lists what is in stock, so 47% of the catalogue was
    structurally invisible (1,998 product groups in the feed vs 646 scraped).
    The invisible part is almost entirely out-of-stock named cultivars, which
    is exactly what collectors set watches on.
  - `available = stock_count > 0` read Daleys' nursery-floor inventory, not
    what a customer can buy. 57 SKUs were listed in stock that the feed reports
    as unbuyable, and 198 pre-order variants were reported as in stock.
  - Prices agreed on 793/793 shared SKUs, so the feed costs us no price
    accuracy.

Availability is four-state, and both of the naive mappings are wrong. Calling a
pre-order "in stock" is the bug we are fixing; calling it "out of stock" is a
new one, because you can genuinely buy the thing today, you just wait for it.
So `available` stays True for pre-orders and the nuance rides in
`availability_state`.

Feed URLs are semi-private (obscured path, x-robots-tag: noindex). They come
from the environment and are never committed.

Usage:
    DALEYS_FEED_URL=https://... python3 csv_feed_scraper.py [nursery ...]
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

from stocklib.model import validate_and_warn
from stocklib.retry import request_with_retry
from stocklib.scrape_health import ScrapeHealth
from stocklib.species_match import load_species_lookup, match_title
from stocklib.taxonomy import enabled_species

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "nursery-stock"
USER_AGENT = "treestock.com.au feed reader (+https://treestock.com.au; ben@treestock.com.au)"

# Availability vocabulary. Daleys' feed mixes schema.org CamelCase with
# Meta/Google Shopping lowercase; 2,900 rows say "out of stock" and exactly one
# says "OutOfStock" (sku 1045), so both spellings are mapped rather than
# assumed away. Raised with Correy 2026-08-20.
#
# Deliberately NOT derived from `qty`: sku 1045 is the sole row in 3,650 where
# qty (40) contradicts availability, so availability is the authority and qty
# is advisory.
DALEYS_AVAILABILITY = {
    "instock": "instock",
    "presale": "preorder",
    "preorder": "preorder",
    "out of stock": "outofstock",
    "outofstock": "outofstock",
}

FEEDS = {
    "daleys": {
        "name": "Daleys Fruit Tree Nursery",
        "url_env": "DALEYS_FEED_URL",
        "availability": DALEYS_AVAILABILITY,
        # Variant deep links carry the SKU as a path-segment prefix in two
        # different shapes: /sku1085-buy/<slug>.htm and /sku229-Rainforest/...
        # Correy's stated rule (strip "/skuNN-buy/") only covers the first and
        # leaves 454 of 1,998 groups disagreeing on their own group URL.
        # Stripping the prefix wherever it appears leaves 0.
        "group_url_re": r"/sku\d+-",
        # Frozen url -> category, captured from the last HTML snapshot. The feed
        # has no category column and stocklib.fruit_filters gates daleys on
        # category prefixes, so with no category every Daleys product silently
        # fails is_fruit_product and vanishes from the site with no alarm.
        "category_map": "daleys_category_map.json",
        # A feed truncated mid-file still parses as valid CSV. The old scraper
        # would overwrite latest.json from a single product, and every guard in
        # the system only catches a catalogue shrinking relative to its own
        # history, which a truncation on day one would not trip.
        "min_groups": 1500,
    },
}


def fetch_feed(url: str, health: ScrapeHealth) -> str | None:
    """Fetch the feed and return its decoded text."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    raw = request_with_retry(req, timeout=120, health=health)
    if raw is None:
        return None
    return raw.decode("utf-8-sig", errors="replace")


def parse_feed(text: str) -> list[dict]:
    """Parse the CSV into raw row dicts."""
    return list(csv.DictReader(io.StringIO(text)))


def strip_size(name: str, pot: str, height: str) -> str:
    """Drop the trailing "<pot> <height>" from a variant name.

    The feed's `name` is the variant name ("Sapodilla - Krasuey 4L 60-70cm"),
    not the product name, and cultivar_parsing cannot strip a hyphenated range:
    it reads "60-70cm" as the cultivar token "60" and mints
    sapodilla-krasuey-60 as a distinct watchable variety. Feeding it raw names
    yields 1,598 slugs where 885 are correct.

    We do not need to fix that parser, because the feed hands us `pot` and
    `height` as their own columns. Removing them is exact on 3,648 of 3,650
    rows and leaves 0 of 1,998 groups disagreeing about their product title.
    """
    out = name.rstrip()
    for suffix in (height.strip(), pot.strip()):
        if suffix and out.endswith(suffix):
            out = out[: -len(suffix)].rstrip()
    return out


def variant_title(pot: str, height: str) -> str:
    """Human label for a variant, e.g. "4L 60-70cm"."""
    return " ".join(p for p in (pot.strip(), height.strip()) if p) or "Default"


def _price(raw: str) -> float | None:
    try:
        return float(str(raw).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


class CategoryResolver:
    """Resolve a product category, which the feed does not carry.

    Order matters. The feed's own column wins if it ever gains one (asked for
    2026-08-20), then the frozen map of what the HTML scraper last saw, then
    our own species taxonomy. Anything unresolved gets no category, which is
    how ornamentals and natives stay recorded in the snapshot but off the site
    (DEC-227): the gate is is_fruit_product at render time, not this scraper.
    """

    def __init__(self, config: dict):
        self.frozen = {}
        name = config.get("category_map")
        if name:
            path = Path(__file__).parent / name
            if path.exists():
                with open(path) as f:
                    self.frozen = json.load(f).get("categories", {})
        self._lookup = load_species_lookup()
        self._enabled = {r["common_name"].lower() for r in enabled_species()}

    def resolve(self, feed_category: str, url: str, title: str) -> str:
        if feed_category.strip():
            return feed_category.strip()
        mapped = self.frozen.get(url)
        if mapped:
            return mapped
        match = match_title(title, self._lookup)
        if match and match.get("cn", "").lower() in self._enabled:
            return "Fruit and Nut Trees"
        return ""


def extract_products(rows: list[dict], config: dict) -> tuple[list[dict], dict]:
    """Group feed rows into products. Returns (products, catalogue).

    `catalogue` holds the per-product static fields (description, images) that
    never change day to day. They are 2.6MB of a 3.4MB feed and keeping them in
    the dated snapshot would cost ~1GB a year to store the same text 365 times.
    """
    availability = config["availability"]
    group_re = re.compile(config["group_url_re"])
    resolver = CategoryResolver(config)

    groups: dict[str, dict] = {}
    catalogue: dict[str, dict] = {}

    for row in rows:
        group_id = row.get("item_group_id") or row.get("id") or ""
        if not group_id:
            continue
        link = row.get("link", "")
        url = group_re.sub("/", link)
        pot, height = row.get("pot", ""), row.get("height", "")
        title = strip_size(row.get("name", ""), pot, height)
        if not title:
            continue

        state = availability.get(row.get("availability", "").strip().lower(), "outofstock")
        # Pre-orders are purchasable, so `available` stays True and the wait is
        # carried by availability_state. Reporting them as unavailable would
        # replace one wrong answer with another.
        purchasable = state in ("instock", "preorder")

        variant = {
            "title": variant_title(pot, height),
            "price": _price(row.get("price")),
            "available": purchasable,
            "stock_count": int(row["qty"]) if str(row.get("qty", "")).strip().isdigit() else 0,
            # Numeric-as-string, matching the old scraper, so
            # stocklib.changes.variant_key keeps producing "{url}|sku:{n}" and
            # price/stock history survives the source switch.
            "sku": str(row.get("id", "")).strip(),
            "availability_state": state,
            "pot": pot.strip(),
            "height": height.strip(),
            "method": row.get("method", "").strip(),
        }
        sale = _price(row.get("sale_price"))
        if sale is not None:
            variant["sale_price"] = sale

        product = groups.get(group_id)
        if product is None:
            product = groups[group_id] = {
                "nursery": "",  # filled by save_snapshot
                "nursery_name": "",
                "title": title,
                "url": url,
                "category": resolver.resolve(row.get("category", ""), url, title),
                "botanical_name": row.get("botanical_name", "").strip(),
                "variants": [],
                "source": "feed",
            }
            catalogue[group_id] = {
                "title": title,
                "url": url,
                "description": row.get("description", ""),
                "image_link": row.get("image_link", ""),
                "additional_image_link": row.get("additional_image_link", ""),
            }
        product["variants"].append(variant)

    # Deliberately no is_real_product / category filtering here. Every gate is a
    # render-time decision (build_* scripts already apply is_real_product, and
    # is_fruit_product gates the category), because the feed is a live view with
    # no history: a row we decline to record today cannot be recovered later.
    products = []
    for product in groups.values():
        priced = [v["price"] for v in product["variants"] if v["price"] is not None]
        avail_priced = [v["price"] for v in product["variants"]
                        if v["price"] is not None and v["available"]]
        pool = avail_priced or priced
        product["min_price"] = min(pool) if pool else None
        product["max_price"] = max(pool) if pool else None
        product["any_available"] = any(v["available"] for v in product["variants"])
        product["total_stock"] = sum(v["stock_count"] for v in product["variants"])
        product["preorder"] = any(v["availability_state"] == "preorder"
                                  for v in product["variants"])
        products.append(product)

    products.sort(key=lambda p: p["title"])
    return products, catalogue


def save_snapshot(nursery_key: str, config: dict, products: list[dict],
                  catalogue: dict) -> Path:
    """Write the dated snapshot, latest.json, and the overwritten catalogue."""
    nursery_dir = DATA_DIR / nursery_key
    nursery_dir.mkdir(parents=True, exist_ok=True)

    for product in products:
        product["nursery"] = nursery_key
        product["nursery_name"] = config["name"]

    in_stock = [p for p in products if p["any_available"]]
    snapshot = {
        "nursery": nursery_key,
        "nursery_name": config["name"],
        "scraped_at": datetime.now().isoformat(),
        "source": "feed",
        "product_count": len(products),
        "in_stock_count": len(in_stock),
        "out_of_stock_count": len(products) - len(in_stock),
        "variant_count": sum(len(p["variants"]) for p in products),
        "preorder_count": sum(1 for p in products if p["preorder"]),
        "products": products,
    }
    validate_and_warn(snapshot, nursery_key)

    today = date.today().isoformat()
    snapshot_file = nursery_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)
    with open(nursery_dir / "latest.json", "w") as f:
        json.dump(snapshot, f, indent=2)

    # Overwritten, never date-versioned: descriptions and image URLs do not
    # change day to day and are most of the feed's bytes.
    with open(nursery_dir / "catalogue.json", "w") as f:
        json.dump({"nursery": nursery_key, "captured_at": snapshot["scraped_at"],
                   "products": catalogue}, f, indent=2)

    print(f"  Saved: {snapshot_file}")
    return snapshot_file


def scrape(nursery_key: str, config: dict) -> bool:
    """Fetch, parse and save one nursery's feed. Returns True on success."""
    print(f"\n{config['name']} ({nursery_key})")
    health = ScrapeHealth(nursery_key)

    url = os.environ.get(config["url_env"], "").strip()
    if not url:
        message = f"{config['url_env']} is not set"
        print(f"  ERROR: {message}")
        health.note_error(message)
        health.finish(ok=False)
        return False

    text = fetch_feed(url, health)
    if text is None:
        health.finish(ok=False)
        return False

    rows = parse_feed(text)
    print(f"  Parsed {len(rows)} feed rows")
    products, catalogue = extract_products(rows, config)

    floor = config.get("min_groups", 0)
    if len(products) < floor:
        message = (f"only {len(products)} products, below the floor of {floor}; "
                   "refusing to overwrite the snapshot")
        print(f"  ERROR: {message}")
        health.note_error(message)
        health.finish(products=len(products), ok=False)
        return False

    in_stock = sum(1 for p in products if p["any_available"])
    preorder = sum(1 for p in products if p["preorder"])
    print(f"  {len(products)} products, {in_stock} buyable ({preorder} pre-order)")
    save_snapshot(nursery_key, config, products, catalogue)
    health.finish(products=len(products), in_stock=in_stock)
    return True


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        return 0

    keys = args or list(FEEDS)
    unknown = [k for k in keys if k not in FEEDS]
    if unknown:
        print(f"Unknown feed(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    failures = [k for k in keys if not scrape(k, FEEDS[k])]
    if failures:
        print(f"\nFAILED: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
