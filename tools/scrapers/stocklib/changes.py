"""
Shared stock-change engine for the treestock + beestock daily digests.

This is the comparison engine that bee_daily_digest.py had forked from
daily_digest.py -- the function bodies were identical bar comments. It diffs
yesterday's snapshot against today's at the variant level and categorises the
changes (back in stock, price drops, new products).

The two sites differ only in two parameters, not in logic:
  - product_filter(raw_product, key) -> bool: which products count. treestock
    passes its is_fruit_product; beestock passes None (keep everything).
  - keys: which directories under data_dir to scan. beestock passes its set of
    known RETAILERS; treestock passes None (scan all nursery dirs).

The site-specific FORMATTING (branding, copy, HTML/text rendering) stays in each
site's own digest module; only this engine is shared. Each site keeps its public
API (load_snapshot(dir, date), load_all_changes(data, date)) via thin wrappers
that bind its product_filter / keys.

Pure, stdlib-only; unit-tested in tests/test_changes.py.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

ProductFilter = Callable[[dict, str], bool]


def variant_key(product_url: str, variant: dict) -> str:
    """Generate a unique key for a specific variant within a product."""
    base = product_url or ""
    sku = variant.get("sku")                  # prefer SKU (Daleys, Ecwid) -- most stable
    if sku:
        return f"{base}|sku:{sku}"
    vid = variant.get("id")                   # then variant ID (Shopify)
    if vid:
        return f"{base}|id:{vid}"
    vtitle = variant.get("title", "Default")  # fallback: variant title
    return f"{base}|v:{vtitle}"


def variant_display_title(product_title: str, variant_title: str) -> str:
    """Build a display title for a variant, e.g. 'Acerola (Large)'."""
    if not variant_title or variant_title in ("Default", "Default Title"):
        return product_title
    return f"{product_title} ({variant_title})"


def load_snapshot(snap_dir: Path, target_date: str,
                  product_filter: Optional[ProductFilter] = None) -> dict:
    """Load a date's snapshot for one nursery/retailer dir as a {variant_key:
    product} lookup. Multi-variant products are flattened so each variant is
    tracked independently (prevents false price changes when one variant goes out
    of stock and min_price shifts to a different-priced variant).

    product_filter(raw_product, dir_name) -> bool decides which products count;
    None keeps all (beestock). treestock passes is_fruit_product.
    """
    snapshot = Path(snap_dir) / f"{target_date}.json"
    if not snapshot.exists():
        return {}
    with open(snapshot) as f:
        data = json.load(f)
    products = {}
    key_name = Path(snap_dir).name
    for p in data.get("products", []):
        if product_filter is not None and not product_filter(p, key_name):
            continue

        url = p.get("url", "")
        title = p.get("title", "")
        variants = p.get("variants", [])

        if not variants:
            # No variants at all (e.g. Ecwid flat products) -- key by URL
            key = url or title
            products[key] = p
        else:
            # Always flatten to variant level, even single-variant products, so
            # keys stay consistent when a product gains/loses variants.
            for v in variants:
                vkey = variant_key(url, v)
                vprice = v.get("price")
                if isinstance(vprice, str):
                    try:
                        vprice = float(vprice)
                    except (ValueError, TypeError):
                        vprice = None
                products[vkey] = {
                    "title": variant_display_title(title, v.get("title", "")),
                    "url": url,
                    "min_price": vprice,
                    "any_available": bool(v.get("available", False)),
                }
    return products


def compare_snapshots(prev: dict, curr: dict) -> dict:
    """Compare two snapshots and return categorised changes."""
    changes = {
        "price_drops": [],
        "back_in_stock": [],
        "new_products": [],
    }

    for key, product in curr.items():
        title = product.get("title", "")
        price = product.get("min_price")
        available = product.get("any_available", product.get("available", False))

        if key not in prev:
            if available:
                changes["new_products"].append({
                    "title": title,
                    "price": price,
                    "url": product.get("url", ""),
                })
            continue

        prev_product = prev[key]
        prev_price = prev_product.get("min_price")
        prev_available = prev_product.get("any_available", prev_product.get("available", False))

        # Stock changes first (affects how we report price changes)
        back_in_stock = available and not prev_available

        if back_in_stock:
            entry = {
                "title": title,
                "price": price,
                "url": product.get("url", ""),
            }
            # Include old price if it changed (so we can show "back at $X, was $Y")
            if price and prev_price and abs(price - prev_price) > 0.01:
                entry["old_price"] = prev_price
            changes["back_in_stock"].append(entry)

        # Price changes (only for items that stayed available -- back-in-stock
        # items already show their price change above)
        if price and prev_price and available and not back_in_stock:
            diff = price - prev_price
            if diff < -0.01:
                changes["price_drops"].append({
                    "title": title,
                    "old_price": prev_price,
                    "new_price": price,
                    "url": product.get("url", ""),
                })

    return changes


def load_all_changes(data_dir: Path, target_date: str,
                     keys: Optional[set] = None,
                     product_filter: Optional[ProductFilter] = None) -> tuple[dict, int]:
    """Load and compare snapshots for target_date vs the day before, across the
    nursery/retailer dirs under data_dir. keys (if given) restricts to those
    directory names (beestock passes its RETAILERS). Returns (all_changes, total).
    """
    prev_date = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    all_changes = {}
    total_changes = 0

    for d in sorted(Path(data_dir).iterdir()):
        if not d.is_dir():
            continue
        if keys is not None and d.name not in keys:
            continue
        prev = load_snapshot(d, prev_date, product_filter)
        curr = load_snapshot(d, target_date, product_filter)
        if not prev or not curr:
            continue
        changes = compare_snapshots(prev, curr)
        all_changes[d.name] = changes
        total_changes += sum(len(v) for v in changes.values())

    return all_changes, total_changes
