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

from stocklib.availability import PURCHASABLE_STATES, roll_up
from stocklib.model import validate_and_warn
from stocklib.retry import request_with_retry
from stocklib.scrape_health import count_priced, ScrapeHealth
from stocklib.species_match import load_species_lookup, match_title
from stocklib.taxonomy import enabled_species

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", Path(__file__).parent.parent.parent / "data")) / "nursery-stock"
USER_AGENT = "treestock.com.au feed reader (+https://treestock.com.au; ben@treestock.com.au)"

# Availability vocabulary. The feed used to mix schema.org CamelCase with
# Meta/Google Shopping lowercase: 2,900 rows said "out of stock" and exactly
# one said "OutOfStock" (sku 1045). We flagged the odd row out; Correy went the
# other way and normalised all 2,942 to schema.org "OutOfStock" on 2026-08-27,
# which is the right call and would have broken a parser that had matched only
# the lowercase spelling. Both stay mapped: snapshots written before that date
# are still read back by stocklib.changes, and the mapping is what makes the
# change a non-event rather than a silent 2,942-row restock.
#
# PreSale and PreOrder are separate states, not synonyms (Correy, 2026-08-27):
# PreSale is a 1-2 month seasonal catalogue, PreOrder is a 1-6 month wait on a
# graft or cutting that has struck. See stocklib.availability for the copy.
#
# Deliberately NOT derived from `qty`: 2 rows of 3,650 have a healthy qty and
# say OutOfStock (sku 1045 Jaboticaba qty 40, sku 3939 Blueberry qty 36), so
# availability is the authority and qty is advisory. It was 1 row on 2026-08-20
# and 2 on 2026-08-27, so it is a recurring state at Daleys' end, not a typo.
DALEYS_AVAILABILITY = {
    "instock": "instock",
    "presale": "presale",
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
        # The feed grew a `category` column in the 2026-08-25 refresh, which
        # Correy confirmed on 2026-08-27 ("I have made this update with category
        # as the last one in the list"). It covers 1,998 of 1,998 groups. Note
        # the two dates: the resolver already preferred the feed's own column,
        # so the change took effect the night it appeared and nothing announced
        # it. A silent improvement is still a silent change of behaviour. The frozen url -> category map below is
        # demoted to a fallback rather than deleted: fruit_filters gates daleys
        # on category prefixes, so a feed that silently stops emitting the
        # column would drop every Daleys product off the site with no alarm.
        # `min_feed_category_share` is the alarm for exactly that.
        "category_map": "daleys_category_map.json",
        "min_feed_category_share": 0.90,
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
    """Resolve a product category.

    Order matters. The feed's own column wins (Daleys added one 2026-08-27),
    then the frozen map of what the HTML scraper last saw, then our own species
    taxonomy. Anything unresolved gets no category, which is how ornamentals
    and natives stay recorded in the snapshot but off the site (DEC-227): the
    gate is is_fruit_product at render time, not this scraper.

    `counts` records which rung each product came off, because the fallbacks
    are the ones that go quietly wrong. The species rung in particular is a
    guess: before the feed carried categories it filed 30 scion-wood cuttings
    and 26 rainforest ornamentals as "Fruit and Nut Trees", which put $9.75
    sticks on /species/apple next to real trees.
    """

    def __init__(self, config: dict):
        self.frozen = {}
        self.counts = {"feed": 0, "frozen": 0, "species": 0, "none": 0}
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
            self.counts["feed"] += 1
            return feed_category.strip()
        mapped = self.frozen.get(url)
        if mapped:
            self.counts["frozen"] += 1
            return mapped
        match = match_title(title, self._lookup)
        if match and match.get("cn", "").lower() in self._enabled:
            self.counts["species"] += 1
            return "Fruit and Nut Trees"
        self.counts["none"] += 1
        return ""

    @property
    def feed_share(self) -> float:
        """Share of products categorised by the feed's own column."""
        total = sum(self.counts.values())
        return self.counts["feed"] / total if total else 0.0


def extract_products(rows: list[dict], config: dict,
                     resolver: "CategoryResolver | None" = None) -> tuple[list[dict], dict]:
    """Group feed rows into products. Returns (products, catalogue).

    `catalogue` holds the per-product static fields (description, images) that
    never change day to day. They are 2.6MB of a 3.4MB feed and keeping them in
    the dated snapshot would cost ~1GB a year to store the same text 365 times.
    """
    availability = config["availability"]
    group_re = re.compile(config["group_url_re"])
    # Passed in by scrape() so it can read `resolver.counts` afterwards without
    # widening this function's return tuple.
    resolver = resolver or CategoryResolver(config)

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
        purchasable = state in PURCHASABLE_STATES

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
        # `wait_state` names WHICH wait ("presale" 1-2 months vs "preorder"
        # 1-6); `preorder` stays a plain bool because build-dashboard, the
        # digest and send_variety_alerts have all read it as one since
        # 2026-08-20 and snapshots on disk carry it that way.
        product["wait_state"] = roll_up(v["availability_state"]
                                        for v in product["variants"])
        product["preorder"] = product["wait_state"] is not None
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
        "presale_count": sum(1 for p in products if p["wait_state"] == "presale"),
        "graft_preorder_count": sum(1 for p in products
                                    if p["wait_state"] == "preorder"),
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
    health = ScrapeHealth(nursery_key, source="feed")

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
    resolver = CategoryResolver(config)
    products, catalogue = extract_products(rows, config, resolver)

    # The feed's category column is what keeps Daleys on the site at all: with
    # no category, fruit_filters' prefix gate drops every product and nothing
    # else in the pipeline notices, because a nursery going to zero on ONE day
    # trips no history-relative guard. Warn rather than fail, so a partial
    # regression still publishes the catalogue with the frozen map behind it.
    floor_share = config.get("min_feed_category_share")
    if floor_share is not None and resolver.feed_share < floor_share:
        message = (f"only {resolver.feed_share:.0%} of products carry a feed "
                   f"category (floor {floor_share:.0%}); falling back to "
                   f"{resolver.counts['frozen']} frozen and "
                   f"{resolver.counts['species']} species-matched, "
                   f"{resolver.counts['none']} uncategorised")
        print(f"  WARNING: {message}", file=sys.stderr)
        health.note_error(message)
    else:
        print(f"  Categories: {resolver.counts['feed']} from the feed, "
              f"{resolver.counts['frozen']} frozen, "
              f"{resolver.counts['species']} species-matched, "
              f"{resolver.counts['none']} none")

    floor = config.get("min_groups", 0)
    if len(products) < floor:
        message = (f"only {len(products)} products, below the floor of {floor}; "
                   "refusing to overwrite the snapshot")
        print(f"  ERROR: {message}")
        health.note_error(message)
        health.finish(products=len(products), ok=False)
        return False

    in_stock = sum(1 for p in products if p["any_available"])
    presale = sum(1 for p in products if p["wait_state"] == "presale")
    graft = sum(1 for p in products if p["wait_state"] == "preorder")
    print(f"  {len(products)} products, {in_stock} buyable "
          f"({presale} pre-sale 1-2mo, {graft} pre-order 1-6mo)")
    save_snapshot(nursery_key, config, products, catalogue)
    health.finish(products=len(products), in_stock=in_stock,
                  priced=count_priced(products))
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
