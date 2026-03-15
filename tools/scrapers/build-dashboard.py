#!/usr/bin/env python3
"""
Build a static HTML dashboard from nursery stock JSON data.
Generates a single self-contained index.html with embedded data.

Usage:
    python3 build-dashboard.py /path/to/data/nursery-stock /path/to/output/
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from shipping import SHIPPING_MAP, NURSERY_NAMES


# Confirmed via nursery websites/policies:
# - Daleys: ships to WA seasonally (special quarantine window, extra $25+ fee)
# - Primal Fruits: WA-based, ships within WA
# - Ross Creek: ships QLD/NSW/ACT/VIC only, NOT WA (quarantine restrictions noted)
# - Ladybird: ships QLD/NSW/VIC/ACT only, NOT WA
# - Fruitopia: unclear from policy, likely does NOT ship to WA (QLD-based, no WA mention)
SPECIES_FILE = Path(__file__).parent / "fruit_species.json"


def load_species_lookup() -> dict:
    """Load fruit species data and build a title-matching lookup."""
    if not SPECIES_FILE.exists():
        return {}

    with open(SPECIES_FILE) as f:
        species = json.load(f)

    lookup = {}
    for s in species:
        common = s["common_name"].lower()
        entry = {
            "cn": s["common_name"],
            "ln": s["latin_name"],
            "sl": s["slug"],
            "r": s["region"],
        }
        # Parse genus/species from latin_name
        parts = s["latin_name"].split()
        if len(parts) >= 2:
            entry["g"] = parts[0]  # genus

        lookup[common] = entry
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = entry

    return lookup


def match_species(title: str, lookup: dict) -> dict | None:
    """Try to match a product title against the species lookup."""
    title_lower = title.lower()

    # Strip common prefixes that precede the actual species name
    prefixes = ["dwarf ", "semi-dwarf ", "semi dwarf ", "miniature ", "standard ",
                 "grafted ", "advanced ", "bare root ", "bare-root "]
    clean_title = title_lower
    clean_title_original = title
    for prefix in prefixes:
        if clean_title.startswith(prefix):
            clean_title = clean_title[len(prefix):]
            clean_title_original = title[len(prefix):]
            break

    # Try matching on both original and cleaned title
    for t_lower, t_orig in [(title_lower, title), (clean_title, clean_title_original)]:
        words = re.split(r'[\s\-–—]+', t_lower)
        for n in range(len(words), 0, -1):
            candidate = " ".join(words[:n])
            if candidate in lookup:
                result = dict(lookup[candidate])
                # Extract cultivar: everything after the matched common name
                matched = lookup[candidate]["cn"]
                # Find where the match ends in the original title
                match_idx = t_orig.lower().find(matched.lower())
                if match_idx >= 0:
                    remainder = t_orig[match_idx + len(matched):].strip(" -–—'\"")
                else:
                    remainder = ""
                if remainder and not remainder.startswith("("):
                    # Check for quoted cultivar name: "Apple 'Granny Smith'"
                    cv_match = re.match(r"['\"]([^'\"]+)['\"]", remainder)
                    if cv_match:
                        result["cv"] = cv_match.group(1)
                    else:
                        cv = remainder.split(" - ")[0].split(" (")[0].strip()
                        # Don't treat size/pot info as cultivar
                        if cv and not re.match(r'\d+mm|\d+cm|\d+ltr|pot|pack|pick\s*up', cv.lower()):
                            result["cv"] = cv
                return result

    return None


# Product type / tag filters for fruit-only tracking
# If a nursery has useful categorization, only include products matching these
FRUIT_FILTERS = {
    "ladybird": {
        "mode": "tags",
        "include_tags": ["Fruit Trees & Edibles"],  # products with this tag prefix
    },
    "ross-creek": {
        "mode": "all",  # all products are fruit/plant related
    },
    "fruitopia": {
        "mode": "all",
    },
    "daleys": {
        "mode": "categories",
        "include_prefixes": [
            "Fruit and Nut Trees", "Fruit Trees/",
            "Bush Food Plants",
            "Herbs, Spices & Perennial Vegetables",
        ],
    },
    "primal-fruits": {
        "mode": "all",
    },
    "guildford": {
        "mode": "all",  # already filtered at scrape time by WooCommerce categories
    },
    "fruit-salad-trees": {
        "mode": "all",  # all products are multi-graft fruit trees
    },
    "diggers": {
        "mode": "all",  # already filtered at scrape time by fruit/nut tags
    },
    "all-season-plants-wa": {
        "mode": "all",  # WA-based fruit tree nursery, all products are fruit
    },
    "ausnurseries": {
        "mode": "all",  # Dedicated fruit/nut tree nursery
    },
    "fruit-tree-cottage": {
        "mode": "all",  # Dedicated fruit tree nursery (Forest Glen, QLD)
    },
}


def build_recent_highlights(data_dir: Path) -> str:
    """Scan last 7 days of nursery data to find notable restocks and price drops.
    Returns an HTML snippet for the homepage 'Recent Highlights' section."""
    restocks = []
    price_drops = []

    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue

        snapshots = sorted([f for f in nursery_dir.glob("2026-03-*.json")])
        if len(snapshots) < 2:
            continue

        # Load shipping info from latest.json
        latest_path = nursery_dir / "latest.json"
        if not latest_path.exists():
            continue
        with open(latest_path) as f:
            latest_meta = json.load(f)
        # Use SHIPPING_MAP as source of truth for WA shipping
        nursery_key = nursery_dir.name
        ships_wa = "WA" in SHIPPING_MAP.get(nursery_key, [])
        nursery_name = NURSERY_NAMES.get(nursery_key, latest_meta.get("nursery_name", nursery_key))

        # Scan consecutive days
        for i in range(1, len(snapshots)):
            with open(snapshots[i - 1]) as f:
                prev_data = json.load(f)
            with open(snapshots[i]) as f:
                curr_data = json.load(f)

            snap_date = snapshots[i].stem  # e.g. "2026-03-14"

            prev_prods = {}
            for p in prev_data.get("products", []):
                key = p.get("url") or p.get("title", "")
                prev_prods[key] = p

            for p in curr_data.get("products", []):
                key = p.get("url") or p.get("title", "")
                title = p.get("title", "")
                url = p.get("url", "")

                curr_avail = p.get("available") or p.get("any_available", False)
                curr_price = p.get("price") or p.get("min_price") or 0

                if key in prev_prods:
                    prev = prev_prods[key]
                    prev_avail = prev.get("available") or prev.get("any_available", False)
                    prev_price = prev.get("price") or prev.get("min_price") or 0

                    # Restock: was out, now in stock
                    if curr_avail and not prev_avail and curr_price and curr_price < 500:
                        restocks.append({
                            "nursery": nursery_name,
                            "title": title,
                            "price": curr_price,
                            "date": snap_date,
                            "ships_wa": ships_wa,
                            "url": url,
                        })

                    # Price drop: meaningful drop (>=5%)
                    if (curr_avail and prev_price and curr_price
                            and curr_price < prev_price
                            and (prev_price - curr_price) / prev_price >= 0.05
                            and (prev_price - curr_price) >= 3):
                        price_drops.append({
                            "nursery": nursery_name,
                            "title": title,
                            "old_price": prev_price,
                            "new_price": curr_price,
                            "drop": prev_price - curr_price,
                            "pct": round((prev_price - curr_price) / prev_price * 100),
                            "date": snap_date,
                            "ships_wa": ships_wa,
                            "url": url,
                        })

    # Sort: WA-shipping first, then by date desc
    restocks.sort(key=lambda x: (not x["ships_wa"], x["date"]), reverse=True)
    price_drops.sort(key=lambda x: (not x["ships_wa"], x["drop"]), reverse=True)

    # Pick top items (prefer WA-shipping, deduplicate by nursery)
    top_restocks = []
    seen_nurseries_r = set()
    for r in restocks:
        if r["nursery"] not in seen_nurseries_r or r["ships_wa"]:
            top_restocks.append(r)
            seen_nurseries_r.add(r["nursery"])
        if len(top_restocks) >= 4:
            break

    top_drops = []
    seen_nurseries_d = set()
    for d in price_drops:
        if d["nursery"] not in seen_nurseries_d or d["ships_wa"]:
            top_drops.append(d)
            seen_nurseries_d.add(d["nursery"])
        if len(top_drops) >= 3:
            break

    if not top_restocks and not top_drops:
        return ""

    def wa_badge(ships_wa):
        if ships_wa:
            return '<span class="inline-block text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded ml-1">Ships to WA</span>'
        return ""

    restock_rows = ""
    for r in top_restocks:
        price_str = f"${r['price']:.0f}" if r['price'] else ""
        short_date = r["date"][5:]  # "03-14" -> show as MM/DD for brevity
        restock_rows += f"""<li class="flex items-baseline gap-1.5 py-1 border-b border-green-100 last:border-0">
          <span class="text-green-600 font-bold text-sm">✅</span>
          <span class="text-sm flex-1 min-w-0">
            <span class="font-medium">{r['title']}</span>
            <span class="text-gray-500"> — {r['nursery']}</span>
            {wa_badge(r['ships_wa'])}
          </span>
          <span class="text-sm font-semibold text-gray-700 flex-shrink-0">{price_str}</span>
        </li>"""

    drop_rows = ""
    for d in top_drops:
        drop_rows += f"""<li class="flex items-baseline gap-1.5 py-1 border-b border-blue-100 last:border-0">
          <span class="text-blue-600 font-bold text-sm">↓</span>
          <span class="text-sm flex-1 min-w-0">
            <span class="font-medium">{d['title']}</span>
            <span class="text-gray-500"> — {d['nursery']}</span>
            {wa_badge(d['ships_wa'])}
          </span>
          <span class="text-sm flex-shrink-0"><span class="line-through text-gray-400">${d['old_price']:.0f}</span> <span class="font-semibold text-blue-700">${d['new_price']:.0f}</span> <span class="text-blue-600">−{d['pct']}%</span></span>
        </li>"""

    total_restocks = len(restocks)
    total_drops = len(price_drops)

    return f"""  <!-- Recent Highlights — "what subscribers knew this week" -->
  <div class="mb-4 rounded-lg border border-gray-200 overflow-hidden">
    <div class="bg-gray-50 px-4 py-2.5 border-b border-gray-200 flex items-center justify-between">
      <span class="text-sm font-semibold text-gray-700">📬 What subscribers got alerted to this week</span>
      <span class="text-xs text-gray-400">{total_restocks} restocks · {total_drops} price drops detected</span>
    </div>
    <div class="grid sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-gray-100">
      <div class="px-4 py-3">
        <p class="text-xs font-semibold text-green-700 uppercase tracking-wide mb-2">Back in stock</p>
        <ul class="space-y-0.5">{restock_rows}</ul>
      </div>
      <div class="px-4 py-3">
        <p class="text-xs font-semibold text-blue-700 uppercase tracking-wide mb-2">Price drops</p>
        <ul class="space-y-0.5">{drop_rows}</ul>
      </div>
    </div>
  </div>"""


def is_fruit_product(product: dict, nursery_key: str) -> bool:
    """Check if a product should be included based on nursery-specific filters."""
    filt = FRUIT_FILTERS.get(nursery_key)
    if not filt or filt.get("mode") == "all":
        return True

    if filt.get("mode") == "tags":
        tags = product.get("tags", [])
        include_tags = filt.get("include_tags", [])
        for tag in tags:
            for inc in include_tags:
                if tag.startswith(inc):
                    return True
        return False

    if filt.get("mode") == "categories":
        cat = product.get("product_type", product.get("category", ""))
        include_prefixes = filt.get("include_prefixes", [])
        return any(cat.startswith(prefix) for prefix in include_prefixes)

    return True




def load_previous_snapshot(nursery_dir: Path) -> dict:
    """Load the second-most-recent snapshot for price comparison."""
    snapshots = sorted(
        [f for f in nursery_dir.glob("*.json") if f.name != "latest.json"],
        reverse=True,
    )
    if len(snapshots) < 2:
        return {}
    # snapshots[0] = today, snapshots[1] = previous day
    with open(snapshots[1]) as f:
        data = json.load(f)
    # Build lookup by URL with title fallback. Merge duplicates (Daleys
    # has plant-list + pre-purchase entries for the same URL) so min_price
    # reflects all variants, preventing false price-change detection.
    lookup = {}
    for p in data.get("products", []):
        key = p.get("url") or p.get("title", "")
        if key in lookup:
            # Merge variants into existing entry, recompute min_price
            existing = lookup[key]
            existing_skus = {v.get("sku") for v in existing.get("variants", [])}
            for v in p.get("variants", []):
                if v.get("sku") not in existing_skus:
                    existing.setdefault("variants", []).append(v)
            avail_prices = [v["price"] for v in existing.get("variants", [])
                            if v.get("price") is not None and v.get("available")]
            if avail_prices:
                existing["min_price"] = min(avail_prices)
        else:
            lookup[key] = p
    return lookup


def load_nursery_data(data_dir: Path) -> list[dict]:
    """Load latest.json from each nursery subdirectory and normalize products."""
    species_lookup = load_species_lookup()
    products = []
    nurseries_loaded = []
    matched_count = 0

    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue

        latest = nursery_dir / "latest.json"
        if not latest.exists():
            continue

        with open(latest) as f:
            data = json.load(f)

        # Load previous snapshot for change detection
        prev_products = load_previous_snapshot(nursery_dir)
        products_before = len(products)

        nursery_name = nursery_dir.name
        scraped_at = data.get("scraped_at", "unknown")

        # Deduplicate products by URL (Daleys has plant-list + pre-purchase
        # entries for the same URL with different variants)
        raw_products = []
        seen_urls = {}
        for p in data.get("products", []):
            url = p.get("url", "")
            if url and url in seen_urls:
                # Merge variants into first occurrence
                existing = seen_urls[url]
                existing_skus = {v.get("sku") for v in existing.get("variants", [])}
                for v in p.get("variants", []):
                    if v.get("sku") not in existing_skus:
                        existing.setdefault("variants", []).append(v)
                # Recompute min_price
                avail_prices = [v["price"] for v in existing.get("variants", [])
                                if v.get("price") is not None and v.get("available")]
                all_prices = [v["price"] for v in existing.get("variants", [])
                              if v.get("price") is not None]
                existing["min_price"] = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)
                existing["any_available"] = any(v.get("available") for v in existing.get("variants", []))
                existing["total_stock"] = sum(v.get("stock_count", 0) for v in existing.get("variants", []))
            else:
                raw_products.append(p)
                if url:
                    seen_urls[url] = p

        for p in raw_products:
            # Apply nursery-specific fruit/edible filter
            if not is_fruit_product(p, nursery_name):
                continue

            # Skip non-plant items
            title = p.get("title", "")
            title_lower = title.lower()
            product_type = p.get("product_type", p.get("category", "")).lower()

            # Exact title matches to skip
            skip_titles = {"gift card", "gift voucher", "gift certificate"}
            if title_lower in skip_titles:
                continue

            # Skip non-plant product types
            non_plant_types = {
                "accessories", "tools", "fertilizer", "fertiliser", "soil",
                "potting mix", "mulch", "pots", "planters", "garden supplies",
                "merchandise", "apparel", "clothing", "books", "gift cards",
            }
            if product_type in non_plant_types:
                continue

            # Skip items matching non-plant keywords in title
            non_plant_keywords = [
                "fertilizer", "fertiliser", "potting mix", "soil mix",
                "seaweed solution", "fish emulsion", "worm castings",
                "secateurs", "pruning", "garden gloves", "plant label",
                "grafting tape", "grafting knife", "budding tape",
                "grow bag", "terracotta", "saucer",
                "pest spray", "insecticide", "fungicide", "neem oil",
                "insect killer", "insect control", "white oil",
                "weed killer", "herbicide", "concentrate spray",
                "shipping", "postage", "freight", "delivery charge",
                "combo pack", "starter kit",
                "sharp shooter", "searles liquid",
                "irrigation", "tree sealant", "end stop terminator",
            ]
            if any(kw in title_lower for kw in non_plant_keywords):
                continue

            # Skip standalone pot/planter products (but not "potted" plants)
            # Matches "Pot 'Storm' Size 1", "Pot 'Rock' Size 2", etc.
            if re.match(r"^pot\s+['\"]", title_lower):
                continue

            # Skip garden chemical products
            if 'ecofend' in title_lower or 'searles' in title_lower:
                continue

            # Skip if title looks like a liquid/spray product (e.g., "Product 1L", "250ml Spray")
            if re.search(r'\b\d+\s*(ml|l|litre|liter)\b', title_lower):
                # But allow plant names that happen to contain these (e.g., "45Ltr Pot" in plant name is OK)
                # Only skip if it looks like a standalone liquid product (starts with number or contains spray/concentrate)
                if re.match(r'^\d+\s*(ml|l)', title_lower) or 'spray' in title_lower or 'concentrate' in title_lower:
                    continue

            # Normalize to common format — prefer prices from available variants
            variants = p.get("variants", [])
            min_price = p.get("min_price")
            if min_price is None and variants:
                avail_prices = [float(v.get("price", 0)) for v in variants if v.get("price") and v.get("available", True)]
                all_prices = [float(v.get("price", 0)) for v in variants if v.get("price")]
                min_price = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)
            elif min_price is None:
                min_price = p.get("price")

            available = p.get("any_available", p.get("available", False))
            stock_count = p.get("total_stock")
            if stock_count is None and variants:
                counts = [v.get("stock_count") for v in variants if v.get("stock_count") is not None]
                stock_count = sum(counts) if counts else None

            on_sale = p.get("on_sale", False)
            if not on_sale and variants:
                on_sale = any(
                    v.get("compare_at_price") and v.get("price")
                    and float(v["compare_at_price"]) > float(v["price"])
                    for v in variants
                    if v.get("compare_at_price") and v.get("price")
                )

            nursery_key = p.get("nursery", nursery_name)

            # Match against species taxonomy
            species = match_species(title, species_lookup)

            product_data = {
                "t": title,
                "n": p.get("nursery_name", nursery_name),
                "nk": p.get("nursery", nursery_name),
                "p": round(min_price, 2) if min_price else None,
                "a": bool(available),
                "s": stock_count,
                "u": p.get("url", ""),
                "sale": bool(on_sale),
                "cat": p.get("product_type", p.get("category", "")),
            }

            if species:
                matched_count += 1
                product_data["ln"] = species.get("ln", "")  # latin name
                product_data["sl"] = species.get("sl", "")  # slug (for species pages)
                if "g" in species:
                    product_data["g"] = species["g"]  # genus
                if "cv" in species:
                    product_data["cv"] = species["cv"]  # cultivar
                if "r" in species:
                    product_data["r"] = species["r"]  # region

            # Price/stock change detection vs previous snapshot
            if prev_products:
                product_url = p.get("url", "")
                prev = prev_products.get(product_url) or prev_products.get(title)
                if prev is None:
                    product_data["ch"] = "new"  # new product
                else:
                    prev_price = prev.get("min_price")
                    prev_avail = prev.get("any_available", prev.get("available", False))
                    if min_price and prev_price:
                        diff = min_price - prev_price
                        if abs(diff) > 0.01:
                            product_data["pp"] = round(prev_price, 2)  # previous price
                            product_data["ch"] = "up" if diff > 0 else "down"
                    if available and not prev_avail:
                        product_data["ch"] = "back"  # back in stock
                    elif not available and prev_avail:
                        product_data["ch"] = "gone"  # went out of stock

            products.append(product_data)

        nursery_added = products[products_before:]
        nurseries_loaded.append({
            "key": nursery_name,
            "name": data.get("nursery_name", nursery_name),
            "count": len(nursery_added),
            "in_stock": sum(1 for p in nursery_added if p.get("a")),
            "scraped_at": scraped_at,
            "st": SHIPPING_MAP.get(nursery_name, []),
        })

    print(f"  Species matched: {matched_count}/{len(products)} ({100*matched_count//len(products) if products else 0}%)")

    # Build species summary for the browse-by-species section
    species_summary: dict[str, dict] = {}
    for p in products:
        sl = p.get("sl")
        if not sl:
            continue
        if sl not in species_summary:
            species_summary[sl] = {
                "cn": "",  # filled below
                "sl": sl,
                "in_stock": 0,
                "prices": [],
            }
        if p.get("a"):
            species_summary[sl]["in_stock"] += 1
        if p.get("p"):
            species_summary[sl]["prices"].append(p["p"])
        if not species_summary[sl]["cn"] and p.get("ln"):
            species_summary[sl]["_ln"] = p["ln"]

    # Resolve common names from species lookup
    ln_to_cn: dict[str, str] = {}
    if species_lookup:
        for entry in species_lookup.values():
            ln = entry.get("ln", "")
            cn = entry.get("cn", "")
            if ln and cn and ln not in ln_to_cn:
                ln_to_cn[ln] = cn

    for sl, s in species_summary.items():
        if not s["cn"]:
            ln = s.get("_ln", "")
            s["cn"] = ln_to_cn.get(ln, sl.replace("-", " ").title())
        s.pop("_ln", None)
        prices = s.pop("prices", [])
        if prices:
            s["min_p"] = round(min(prices), 2)
            s["max_p"] = round(max(prices), 2)

    top_species = sorted(species_summary.values(), key=lambda x: -x["in_stock"])[:16]

    return products, nurseries_loaded, top_species


def build_html(products: list[dict], nurseries: list[dict], top_species: list[dict], highlights_html: str = "") -> str:
    """Generate the dashboard HTML with embedded data."""
    products_json = json.dumps(products, separators=(",", ":"))
    nurseries_json = json.dumps(nurseries, separators=(",", ":"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Server-render species strip for SEO (crawlable <a> tags)
    species_strip_html = "\n".join(
        f'<a href="/species/{s["sl"]}.html" class="species-pill">{s["cn"]} <span class="count">{s["in_stock"]}</span></a>'
        for s in top_species
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>treestock.com.au - Australian Nursery Stock Tracker</title>
<meta name="description" content="Track rare fruit and plant stock across Australian nurseries. Search availability, compare prices, find what's in stock.">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta property="og:type" content="website">
<meta property="og:url" content="https://treestock.com.au/">
<meta property="og:title" content="treestock.com.au - Australian Nursery Stock Tracker">
<meta property="og:description" content="Track fruit tree stock across 9 Australian nurseries. Daily price drops, restocks, and availability. Filter by state. Free.">
<meta property="og:image" content="https://treestock.com.au/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="treestock.com.au - Australian Nursery Stock Tracker">
<meta name="twitter:description" content="Track fruit tree stock across 9 Australian nurseries. Daily price drops, restocks, and availability. Filter by state. Free.">
<meta name="twitter:image" content="https://treestock.com.au/og-image.png">
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
<script defer data-domain="treestock.com.au" src="https://data.bjnoel.com/js/script.outbound-links.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
  .stock-badge {{ font-size: 0.7rem; padding: 2px 6px; border-radius: 9999px; }}
  .wa-badge {{ background: #fef3c7; color: #92400e; }}
  .sale-badge {{ background: #fee2e2; color: #991b1b; }}
  .new-badge {{ background: #dbeafe; color: #1e40af; }}
  .back-badge {{ background: #d1fae5; color: #065f46; font-weight: 600; }}
  .price-down {{ color: #059669; font-weight: 600; }}
  .price-up {{ color: #dc2626; }}
  .in-stock {{ background: #d1fae5; color: #065f46; }}
  .out-stock {{ background: #f3f4f6; color: #6b7280; }}
  #results {{ min-height: 200px; }}
  .product-row {{ border-bottom: 1px solid #f3f4f6; }}
  .product-row:hover {{ background: #f9fafb; }}
  .nursery-tag {{ font-size: 0.65rem; padding: 1px 5px; border-radius: 4px; background: #e0e7ff; color: #3730a3; }}
  .species-strip {{ display: flex; gap: 0.5rem; overflow-x: auto; padding-bottom: 4px; -webkit-overflow-scrolling: touch; scrollbar-width: thin; }}
  .species-strip::-webkit-scrollbar {{ height: 3px; }}
  .species-strip::-webkit-scrollbar-thumb {{ background: #d1d5db; border-radius: 3px; }}
  .species-pill {{ flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px; border: 1px solid #e5e7eb; border-radius: 9999px; font-size: 0.8125rem; color: #374151; white-space: nowrap; text-decoration: none; transition: border-color 0.15s, background 0.15s; }}
  .species-pill:hover {{ border-color: #22c55e; background: #f0fdf4; color: #065f46; }}
  .species-pill .count {{ color: #059669; font-weight: 600; font-size: 0.7rem; }}
</style>
</head>
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="max-w-5xl mx-auto px-4 py-3">
    <div class="flex items-start justify-between gap-2">
      <div class="flex items-center gap-2">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" class="w-8 h-8 flex-shrink-0">
          <rect width="64" height="64" rx="12" fill="#065f46"/>
          <path d="M32,12 C18,16 12,28 14,42 C16,38 20,34 26,32 C22,38 20,44 20,50 C28,44 38,34 40,20 C38,14 34,12 32,12Z" fill="#22c55e" opacity="0.9"/>
          <path d="M32,14 C28,24 24,34 20,48" fill="none" stroke="#065f46" stroke-width="1.5" opacity="0.4"/>
          <circle cx="44" cy="44" r="8" fill="#f59e0b"/>
          <text x="44" y="48" text-anchor="middle" font-family="sans-serif" font-size="12" font-weight="bold" fill="#065f46">$</text>
        </svg>
        <div>
          <h1 class="text-xl font-bold text-green-800">treestock.com.au</h1>
          <p class="text-xs text-gray-400 sm:hidden" id="statsSmall"></p>
          <p class="text-xs text-gray-400 hidden sm:block">Australian Nursery Stock Tracker</p>
        </div>
      </div>
      <div class="hidden sm:block text-right text-xs text-gray-400">
        <div id="stats"></div>
        <div>Updated {now}</div>
      </div>
    </div>
  </div>
</header>

<main class="max-w-5xl mx-auto px-4 py-4">
  <!-- Search & Filters -->
  <div class="mb-4 space-y-3">
    <input type="text" id="search" placeholder="Search plants... (e.g. sapodilla, mango, fig)"
      class="w-full px-4 py-3 border border-gray-300 rounded-lg text-lg focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
      autofocus>
    <div class="flex flex-wrap gap-2 items-center text-sm">
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" id="inStockOnly" checked class="rounded"> In stock only
      </label>
      <select id="stateFilter" class="border border-gray-300 rounded px-2 py-1 text-sm">
        <option value="">All states</option>
        <option value="NSW">NSW</option>
        <option value="VIC">VIC</option>
        <option value="QLD">QLD</option>
        <option value="SA">SA</option>
        <option value="WA">WA</option>
        <option value="TAS">TAS</option>
        <option value="NT">NT</option>
        <option value="ACT">ACT</option>
      </select>
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" id="changesOnly" class="rounded"> Changes only
      </label>
      <select id="nurseryFilter" class="border border-gray-300 rounded px-2 py-1 text-sm">
        <option value="">All nurseries</option>
      </select>
      <select id="sortBy" class="border border-gray-300 rounded px-2 py-1 text-sm">
        <option value="relevance">Sort: Relevance</option>
        <option value="price-asc">Price: Low to High</option>
        <option value="price-desc">Price: High to Low</option>
        <option value="name">Name: A-Z</option>
      </select>
      <span id="resultCount" class="text-gray-400 ml-auto"></span>
    </div>
  </div>

  <!-- Nursery Summary (hidden when searching) -->
  <div id="nurserySummaryWrap" class="mb-4">
    <button id="nurseryToggle" class="sm:hidden flex items-center gap-1 text-sm text-gray-500 mb-2" onclick="toggleNurserySummary()">
      <span id="nurseryToggleIcon">&#9654;</span> Nurseries
    </button>
    <div id="nurserySummary" class="hidden sm:grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 text-sm"></div>
  </div>

  <!-- Rare Finds teaser -->
  <div class="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between gap-3">
    <div>
      <span class="text-sm font-semibold text-amber-900">🌿 Rare &amp; Exotic Finds</span>
      <span class="text-sm text-amber-800 ml-2">Jaboticaba, Rambutan, Sapodilla, Rollinia &amp; more in stock now.</span>
    </div>
    <a href="/rare.html" class="text-sm font-semibold text-amber-700 hover:text-amber-900 whitespace-nowrap">View all &rarr;</a>
  </div>

  <!-- Browse by Species — horizontal scroll strip, server-rendered for SEO -->
  <div id="speciesWrap" class="mb-4">
    <div class="flex items-center gap-2 mb-2">
      <h2 class="text-sm font-semibold text-gray-600">Browse by Species</h2>
      <a href="/species/" class="text-xs text-green-600 hover:underline ml-auto">All species &rarr;</a>
    </div>
    <div class="species-strip">{species_strip_html}</div>
  </div>

{highlights_html}

  <!-- Email Alerts Signup (above results) -->
  <div class="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
    <div class="flex flex-col sm:flex-row sm:items-center gap-2">
      <p class="text-sm text-green-800 flex-1"><strong>Get tomorrow's changes in your inbox</strong> — free daily email, unsubscribe any time. <a href="/sample-digest.html" class="text-green-700 underline whitespace-nowrap">See example &rarr;</a></p>
      <form id="subscribeForm" class="flex gap-2 flex-shrink-0">
        <input type="email" id="subEmail" placeholder="your@email.com" required
          class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 w-44">
        <button type="submit" class="px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium">
          Subscribe free
        </button>
      </form>
    </div>
    <div id="subMessage" class="mt-2 text-sm hidden"></div>
  </div>

  <!-- Results -->
  <div id="results"></div>
  <div id="loadMore" class="text-center py-4 hidden">
    <button onclick="showMore()" class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700">
      Show more results
    </button>
  </div>
</main>

<footer class="border-t border-gray-200 mt-8 py-6 text-center text-xs text-gray-400">
  <div class="flex justify-center gap-4 mb-3 text-sm">
    <a href="/digest.html" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 text-gray-600">Today's Digest</a>
    <a href="/species/" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 text-gray-600">Browse by Species</a>
    <a href="/variety/" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 text-gray-600">Variety Finder</a>
    <a href="/compare/" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 text-gray-600">Compare Prices</a>
    <a href="/rare.html" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 text-gray-600">Rare Finds</a>
    <a href="/history.html" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 text-gray-600">Price History</a>
  </div>
  <p>Data scraped daily from public nursery websites. Prices and availability may change.</p>
  <p class="mt-1">A project by <a href="https://bjnoel.com" class="underline">Benedict Noel</a>, Perth WA</p>
</footer>

<script>
const P = {products_json};
const N = {nurseries_json};

const NURSERY_URLS = {{
  'ross-creek': 'rosscreektropicals.com.au',
  'ladybird': 'ladybirdnursery.com.au',
  'fruitopia': 'fruitopia.com.au',
  'daleys': 'daleysfruit.com.au',
  'primal-fruits': 'primalfruits.com.au',
}};

let displayCount = 50;
let currentResults = [];
let nurseryExpanded = false;

function toggleNurserySummary() {{
  nurseryExpanded = !nurseryExpanded;
  const el = document.getElementById('nurserySummary');
  const icon = document.getElementById('nurseryToggleIcon');
  if (nurseryExpanded) {{
    el.classList.remove('hidden');
    el.classList.add('grid');
    icon.innerHTML = '&#9660;';
  }} else {{
    el.classList.add('hidden');
    el.classList.remove('grid');
    icon.innerHTML = '&#9654;';
  }}
}}

// Build state→nursery shipping lookup
const SHIPS_TO = {{}};
N.forEach(n => {{ SHIPS_TO[n.key] = n.st || []; }});

// Populate nursery filter & summary
const nurserySelect = document.getElementById('nurseryFilter');
const nurserySummary = document.getElementById('nurserySummary');
N.forEach(n => {{
  const opt = document.createElement('option');
  opt.value = n.key;
  opt.textContent = `${{n.name}} (${{n.in_stock}} in stock)`;
  nurserySelect.appendChild(opt);

  nurserySummary.innerHTML += `
    <div class="border border-gray-200 rounded p-2">
      <div class="font-medium text-xs">${{n.name}}</div>
      <div class="text-green-700 font-bold">${{n.in_stock}}</div>
      <div class="text-gray-400 text-xs">of ${{n.count}} in stock</div>
    </div>`;
}});

const totalProducts = P.length;
const totalInStock = P.filter(p => p.a).length;
const statsText = `${{totalInStock.toLocaleString()}} in stock across ${{N.length}} nurseries (${{totalProducts.toLocaleString()}} total)`;
document.getElementById('stats').textContent = statsText;
const sm = document.getElementById('statsSmall');
if (sm) sm.textContent = statsText;

// Search & filter
const searchInput = document.getElementById('search');
const inStockOnly = document.getElementById('inStockOnly');
const stateFilter = document.getElementById('stateFilter');
const changesOnly = document.getElementById('changesOnly');
const sortBy = document.getElementById('sortBy');

function search() {{
  displayCount = 50;
  const q = searchInput.value.toLowerCase().trim();
  const nursery = nurserySelect.value;
  const stockOnly = inStockOnly.checked;
  const st = stateFilter.value;
  const sort = sortBy.value;

  // Hide nursery summary and species grid when actively searching/filtering
  const hasFilters = q || nursery || changesOnly.checked;
  const wrap = document.getElementById('nurserySummaryWrap');
  wrap.style.display = hasFilters ? 'none' : '';
  const speciesWrap = document.getElementById('speciesWrap');
  speciesWrap.style.display = hasFilters ? 'none' : '';

  let results = P;

  if (stockOnly) results = results.filter(p => p.a);
  if (st) results = results.filter(p => (SHIPS_TO[p.nk] || []).includes(st));
  if (changesOnly.checked) results = results.filter(p => p.ch);
  if (nursery) results = results.filter(p => p.nk === nursery);

  if (q) {{
    const terms = q.split(/\\s+/);
    results = results.filter(p => {{
      const text = (p.t + ' ' + p.cat + ' ' + (p.ln || '') + ' ' + (p.cv || '')).toLowerCase();
      return terms.every(t => text.includes(t));
    }});
    // Score by how early the match appears
    results = results.map(p => {{
      const idx = p.t.toLowerCase().indexOf(terms[0]);
      return {{ ...p, _score: idx === -1 ? 999 : idx }};
    }});
  }}

  // Sort
  if (sort === 'price-asc') {{
    results.sort((a, b) => (a.p || 9999) - (b.p || 9999));
  }} else if (sort === 'price-desc') {{
    results.sort((a, b) => (b.p || 0) - (a.p || 0));
  }} else if (sort === 'name') {{
    results.sort((a, b) => a.t.localeCompare(b.t));
  }} else if (q) {{
    results.sort((a, b) => (a._score || 0) - (b._score || 0));
  }} else {{
    results.sort((a, b) => a.t.localeCompare(b.t));
  }}

  currentResults = results;
  render();
}}

function render() {{
  const results = currentResults;
  const showing = results.slice(0, displayCount);
  const container = document.getElementById('results');
  const countEl = document.getElementById('resultCount');
  const loadMoreEl = document.getElementById('loadMore');

  countEl.textContent = `${{results.length}} result${{results.length !== 1 ? 's' : ''}}`;

  if (showing.length === 0) {{
    container.innerHTML = '<div class="text-center py-12 text-gray-400">No plants found matching your search.</div>';
    loadMoreEl.classList.add('hidden');
    return;
  }}

  container.innerHTML = showing.map(p => {{
    const price = p.p ? ('$' + p.p.toFixed(2)) : '';
    const stockBadge = p.a
      ? `<span class="stock-badge in-stock">${{p.s ? p.s + ' left' : 'In stock'}}</span>`
      : '<span class="stock-badge out-stock">Out of stock</span>';
    const _st = stateFilter.value;
    const shipsBadge = (_st && (SHIPS_TO[p.nk] || []).includes(_st))
      ? `<span class="stock-badge wa-badge">Ships to ${{_st}}</span>` : '';
    const saleBadge = p.sale ? '<span class="stock-badge sale-badge">Sale</span>' : '';
    const latinName = p.ln ? `<span class="text-xs text-gray-400 italic ml-1">${{p.ln}}</span>` : '';
    const cultivar = p.cv ? ` '${{p.cv}}'` : '';

    // Change indicators
    let changeBadge = '';
    if (p.ch === 'new') changeBadge = '<span class="stock-badge new-badge">New</span>';
    else if (p.ch === 'back') changeBadge = '<span class="stock-badge back-badge">Back in stock!</span>';
    else if (p.ch === 'gone') changeBadge = '<span class="stock-badge out-stock">Just sold out</span>';

    let priceInfo = price;
    if (p.ch === 'down' && p.pp) priceInfo = `<span class="price-down">${{price}}</span> <span class="text-xs text-gray-400 line-through">${{('$' + p.pp.toFixed(2))}}</span>`;
    else if (p.ch === 'up' && p.pp) priceInfo = `<span class="price-up">${{price}}</span> <span class="text-xs text-gray-400">was ${{('$' + p.pp.toFixed(2))}}</span>`;

    const utm = p.u ? (p.u.includes('?') ? '&' : '?') + 'utm_source=treestock&utm_medium=referral' : '';
    return `<a href="${{p.u}}${{utm}}" target="_blank" rel="noopener" class="product-row flex items-center gap-3 py-3 px-2 block">
      <div class="flex-1 min-w-0">
        <div class="font-medium text-sm">${{p.t}}${{latinName}}</div>
        <div class="flex items-center gap-1.5 mt-0.5 flex-wrap">
          <span class="nursery-tag">${{p.n}}</span>
          ${{stockBadge}} ${{shipsBadge}} ${{saleBadge}} ${{changeBadge}}
        </div>
      </div>
      <div class="text-right flex-shrink-0">
        <div class="font-bold text-sm">${{priceInfo}}</div>
      </div>
    </a>`;
  }}).join('');

  if (results.length > displayCount) {{
    loadMoreEl.classList.remove('hidden');
  }} else {{
    loadMoreEl.classList.add('hidden');
  }}
}}

function showMore() {{
  displayCount += 50;
  render();
}}

// Event listeners
searchInput.addEventListener('input', search);
inStockOnly.addEventListener('change', search);
stateFilter.addEventListener('change', search);
changesOnly.addEventListener('change', search);
nurserySelect.addEventListener('change', search);
sortBy.addEventListener('change', search);

// Initial render
search();

// Subscribe form
document.getElementById('subscribeForm').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const email = document.getElementById('subEmail').value;
  const msg = document.getElementById('subMessage');
  const btn = e.target.querySelector('button');
  btn.disabled = true;
  btn.textContent = 'Subscribing...';
  try {{
    const resp = await fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email}}),
    }});
    const data = await resp.json();
    msg.textContent = data.message || 'Subscribed!';
    msg.className = 'mt-2 text-sm text-green-600';
    msg.classList.remove('hidden');
    if (resp.status === 201) {{
      document.getElementById('subEmail').value = '';
    }}
  }} catch (err) {{
    msg.textContent = 'Something went wrong. Try again later.';
    msg.className = 'mt-2 text-sm text-red-600';
    msg.classList.remove('hidden');
  }}
  btn.disabled = false;
  btn.textContent = 'Subscribe';
}});

</script>
</body>
</html>"""


def main():
    if len(sys.argv) < 2:
        print("Usage: build-dashboard.py <data-dir> [output-dir]")
        print("  data-dir: path to nursery-stock/ directory with nursery subdirectories")
        print("  output-dir: where to write index.html (default: ./dashboard-output/)")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("dashboard-output")

    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist")
        sys.exit(1)

    print(f"Loading nursery data from {data_dir}...")
    products, nurseries, top_species = load_nursery_data(data_dir)
    print(f"Loaded {len(products)} products from {len(nurseries)} nurseries")

    for n in nurseries:
        print(f"  {n['name']}: {n['count']} products ({n['in_stock']} in stock)")
    print(f"  Top species for grid: {', '.join(s['cn'] for s in top_species[:5])}")

    print("Building recent highlights...")
    highlights_html = build_recent_highlights(data_dir)
    print(f"  Highlights section: {'generated' if highlights_html else 'empty (insufficient data)'}")

    output_dir.mkdir(parents=True, exist_ok=True)
    html = build_html(products, nurseries, top_species, highlights_html)
    out_file = output_dir / "index.html"
    out_file.write_text(html)
    print(f"Dashboard written to {out_file} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
