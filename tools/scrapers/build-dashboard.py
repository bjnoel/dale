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

from daily_digest import _variant_key
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

        # Scan consecutive days using variant-level comparison
        for i in range(1, len(snapshots)):
            with open(snapshots[i - 1]) as f:
                prev_data = json.load(f)
            with open(snapshots[i]) as f:
                curr_data = json.load(f)

            snap_date = snapshots[i].stem  # e.g. "2026-03-14"

            # Build variant-level lookup for previous day
            prev_variants = {}
            for p in prev_data.get("products", []):
                url = p.get("url", "")
                variants = p.get("variants", [])
                if not variants:
                    key = url or p.get("title", "")
                    prev_variants[key] = {
                        "price": p.get("price") or p.get("min_price"),
                        "available": p.get("available") or p.get("any_available", False),
                    }
                else:
                    for v in variants:
                        vkey = _variant_key(url, v)
                        vp = v.get("price")
                        try:
                            vp = float(vp) if vp is not None else None
                        except (ValueError, TypeError):
                            vp = None
                        prev_variants[vkey] = {
                            "price": vp,
                            "available": bool(v.get("available", False)),
                        }

            for p in curr_data.get("products", []):
                title = p.get("title", "")
                url = p.get("url", "")
                variants = p.get("variants", [])

                if not variants:
                    # No variants — product-level comparison
                    key = url or title
                    curr_avail = p.get("available") or p.get("any_available", False)
                    curr_price = p.get("price") or p.get("min_price") or 0
                    prev_v = prev_variants.get(key)
                    if prev_v:
                        prev_avail = prev_v["available"]
                        prev_price = prev_v["price"] or 0
                        if curr_avail and not prev_avail and curr_price and curr_price < 500:
                            restocks.append({"nursery": nursery_name, "title": title, "price": curr_price, "date": snap_date, "ships_wa": ships_wa, "url": url})
                        if (curr_avail and prev_price and curr_price and curr_price < prev_price
                                and (prev_price - curr_price) / prev_price >= 0.05 and (prev_price - curr_price) >= 3):
                            price_drops.append({"nursery": nursery_name, "title": title, "old_price": prev_price, "new_price": curr_price,
                                                "drop": prev_price - curr_price, "pct": round((prev_price - curr_price) / prev_price * 100),
                                                "date": snap_date, "ships_wa": ships_wa, "url": url})
                else:
                    # Variant-level comparison
                    for v in variants:
                        vkey = _variant_key(url, v)
                        prev_v = prev_variants.get(vkey)
                        if not prev_v:
                            continue
                        try:
                            vprice = float(v.get("price") or 0)
                        except (ValueError, TypeError):
                            vprice = 0
                        v_avail = bool(v.get("available", False))
                        try:
                            prev_price = float(prev_v["price"] or 0)
                        except (ValueError, TypeError):
                            prev_price = 0
                        prev_avail = prev_v["available"]
                        vtitle = v.get("title", "")
                        display = f"{title} ({vtitle})" if vtitle and vtitle not in ("Default", "Default Title") else title

                        if v_avail and not prev_avail and vprice and vprice < 500:
                            restocks.append({"nursery": nursery_name, "title": display, "price": vprice, "date": snap_date, "ships_wa": ships_wa, "url": url})
                        if (v_avail and prev_price and vprice and vprice < prev_price
                                and (prev_price - vprice) / prev_price >= 0.05 and (prev_price - vprice) >= 3):
                            price_drops.append({"nursery": nursery_name, "title": display, "old_price": prev_price, "new_price": vprice,
                                                "drop": prev_price - vprice, "pct": round((prev_price - vprice) / prev_price * 100),
                                                "date": snap_date, "ships_wa": ships_wa, "url": url})

    # Sort: by date desc, then by impact
    restocks.sort(key=lambda x: x["date"], reverse=True)
    price_drops.sort(key=lambda x: x["drop"], reverse=True)

    # Pick top items (deduplicate by nursery)
    top_restocks = []
    seen_nurseries_r = set()
    for r in restocks:
        if r["nursery"] not in seen_nurseries_r:
            top_restocks.append(r)
            seen_nurseries_r.add(r["nursery"])
        if len(top_restocks) >= 4:
            break

    top_drops = []
    seen_nurseries_d = set()
    for d in price_drops:
        if d["nursery"] not in seen_nurseries_d:
            top_drops.append(d)
            seen_nurseries_d.add(d["nursery"])
        if len(top_drops) >= 3:
            break

    if not top_restocks and not top_drops:
        return ""

    restock_rows = ""
    for r in top_restocks:
        price_str = f"${r['price']:.0f}" if r['price'] else ""
        restock_rows += f"""<li class="flex items-baseline gap-1.5 py-1 border-b border-green-100 last:border-0">
          <span class="text-green-600 font-bold text-sm">&#10003;</span>
          <span class="text-sm flex-1 min-w-0">
            <span class="font-medium">{r['title']}</span>
            <span class="text-gray-500"> &mdash; {r['nursery']}</span>
          </span>
          <span class="text-sm font-semibold text-gray-700 flex-shrink-0">{price_str}</span>
        </li>"""

    drop_rows = ""
    for d in top_drops:
        drop_rows += f"""<li class="flex items-baseline gap-1.5 py-1 border-b border-blue-100 last:border-0">
          <span class="text-blue-600 font-bold text-sm">&darr;</span>
          <span class="text-sm flex-1 min-w-0">
            <span class="font-medium">{d['title']}</span>
            <span class="text-gray-500"> &mdash; {d['nursery']}</span>
          </span>
          <span class="text-sm flex-shrink-0"><span class="line-through text-gray-400">${d['old_price']:.0f}</span> <span class="font-semibold text-blue-700">${d['new_price']:.0f}</span> <span class="text-blue-600">&minus;{d['pct']}%</span></span>
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
    """Load the second-most-recent snapshot for variant-level price comparison.

    Returns a dict keyed by variant key (url|sku:X, url|id:X, or url|v:Title)
    with {min_price, any_available} per variant. This prevents false price changes
    when a different-sized variant goes in/out of stock.
    """
    snapshots = sorted(
        [f for f in nursery_dir.glob("*.json") if re.match(r"\d{4}-\d{2}-\d{2}\.json$", f.name)],
        reverse=True,
    )
    if len(snapshots) < 2:
        return {}
    # snapshots[0] = today, snapshots[1] = previous day
    with open(snapshots[1]) as f:
        data = json.load(f)
    # Build variant-level lookup (same approach as daily_digest.load_snapshot)
    lookup = {}
    for p in data.get("products", []):
        url = p.get("url", "")
        variants = p.get("variants", [])
        if not variants:
            key = url or p.get("title", "")
            lookup[key] = p
        else:
            for v in variants:
                vkey = _variant_key(url, v)
                vprice = v.get("price")
                if isinstance(vprice, str):
                    try:
                        vprice = float(vprice)
                    except (ValueError, TypeError):
                        vprice = None
                lookup[vkey] = {
                    "min_price": vprice,
                    "any_available": bool(v.get("available", False)),
                }
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

            # Price/stock change detection vs previous snapshot (variant-level)
            if prev_products:
                product_url = p.get("url", "")
                variants_list = p.get("variants", [])
                if variants_list:
                    # Compare each variant individually to detect real price changes
                    any_prev_found = False
                    best_change = None  # track the most significant change to display
                    for v in variants_list:
                        vkey = _variant_key(product_url, v)
                        prev_v = prev_products.get(vkey)
                        if prev_v is not None:
                            any_prev_found = True
                            vprice = v.get("price")
                            if isinstance(vprice, str):
                                try:
                                    vprice = float(vprice)
                                except (ValueError, TypeError):
                                    vprice = None
                            prev_vprice = prev_v.get("min_price")
                            v_avail = bool(v.get("available", False))
                            prev_v_avail = prev_v.get("any_available", False)
                            # Price change on this variant
                            if vprice and prev_vprice and abs(vprice - prev_vprice) > 0.01:
                                diff = vprice - prev_vprice
                                pct = abs(diff) / prev_vprice
                                ch = "up" if diff > 0 else "down"
                                if best_change is None or pct > best_change[2]:
                                    best_change = (ch, prev_vprice, pct, vprice)
                            # Back in stock
                            if v_avail and not prev_v_avail:
                                if best_change is None:
                                    product_data["ch"] = "back"
                            elif not v_avail and prev_v_avail:
                                if best_change is None and not product_data.get("ch"):
                                    product_data["ch"] = "gone"
                    if not any_prev_found:
                        product_data["ch"] = "new"
                    elif best_change:
                        product_data["ch"] = best_change[0]
                        product_data["pp"] = round(best_change[1], 2)
                        # Override displayed price with the variant that actually changed
                        product_data["p"] = round(best_change[3], 2)
                else:
                    # No variants — fall back to product-level lookup
                    prev = prev_products.get(product_url) or prev_products.get(title)
                    if prev is None:
                        product_data["ch"] = "new"
                    else:
                        prev_price = prev.get("min_price")
                        prev_avail = prev.get("any_available", prev.get("available", False))
                        if min_price and prev_price:
                            diff = min_price - prev_price
                            if abs(diff) > 0.01:
                                product_data["pp"] = round(prev_price, 2)
                                product_data["ch"] = "up" if diff > 0 else "down"
                        if available and not prev_avail:
                            product_data["ch"] = "back"
                        elif not available and prev_avail:
                            product_data["ch"] = "gone"

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
  .restrict-badge {{ background: #fee2e2; color: #991b1b; font-size: 0.65rem; }}
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

  <!-- Results (keep above the fold) -->
  <div id="results"></div>
  <div id="loadMore" class="text-center py-4 hidden">
    <button onclick="showMore()" class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700">
      Show more results
    </button>
  </div>

  <!-- Email Alerts Signup (below results) -->
  <div class="mt-6 mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
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

{highlights_html}

  <!-- Browse by Species -->
  <div id="speciesWrap" class="mb-4">
    <div class="flex items-center gap-2 mb-2">
      <h2 class="text-sm font-semibold text-gray-600">Browse by Species</h2>
      <a href="/species/" class="text-xs text-green-600 hover:underline ml-auto">All species &rarr;</a>
    </div>
    <div class="species-strip">{species_strip_html}</div>
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

// Build state→nursery shipping lookup
const SHIPS_TO = {{}};
N.forEach(n => {{ SHIPS_TO[n.key] = n.st || []; }});

// Populate nursery filter
const nurserySelect = document.getElementById('nurseryFilter');
N.forEach(n => {{
  const opt = document.createElement('option');
  opt.value = n.key;
  opt.textContent = `${{n.name}} (${{n.in_stock}} in stock)`;
  nurserySelect.appendChild(opt);
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
    // Show shipping restriction warnings for WA/NT/TAS
    const nShips = SHIPS_TO[p.nk] || [];
    const restricted = ['WA','NT','TAS'].filter(s => !nShips.includes(s));
    const _st = stateFilter.value;
    const shipsBadge = (_st && !nShips.includes(_st))
      ? `<span class="stock-badge restrict-badge">No ${{_st}}</span>`
      : (restricted.length > 0 && restricted.length < 3 && !_st)
        ? `<span class="stock-badge restrict-badge">No ${{restricted.join('/')}}</span>`
        : '';
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
