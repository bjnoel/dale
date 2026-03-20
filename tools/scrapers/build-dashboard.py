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
from treestock_layout import render_head, render_footer, SITE_NAME, LOGO_SVG, NAV_ITEMS


# Confirmed via nursery websites/policies:
# - Daleys: ships to WA seasonally (special quarantine window, extra $25+ fee)
# - Primal Fruits: WA-based, ships within WA
# - Ross Creek: ships QLD/NSW/ACT/VIC only, NOT WA (quarantine restrictions noted)
# - Ladybird: ships QLD/NSW/VIC/ACT only, NOT WA
# - Fruitopia: unclear from policy, likely does NOT ship to WA (QLD-based, no WA mention)
SPECIES_FILE = Path(__file__).parent / "fruit_species.json"

# Featured nurseries (paying partners). Products are visually highlighted and sorted first.
# To activate a featured listing, add the nursery key here.
FEATURED_NURSERIES: set[str] = set()  # e.g. {'primal-fruits'} when live


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

    # Try matching on both original and cleaned title (prefix-first approach)
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

    # Fallback: try matching any N-word sequence starting at each position.
    # Handles "Variety Species (size)" format (e.g. Heritage Fruit Trees titles
    # like "Akane Apple (medium)" where "apple" is not at position 0).
    # Only try starting positions > 0 (already tried position 0 above).
    for t_lower, t_orig in [(title_lower, title), (clean_title, clean_title_original)]:
        words = re.split(r'[\s\-–—(]+', t_lower)
        words = [w.rstrip(").,") for w in words if w]
        for start in range(1, len(words)):
            for n in range(min(len(words) - start, 3), 0, -1):
                candidate = " ".join(words[start:start + n])
                if candidate in lookup:
                    result = dict(lookup[candidate])
                    # Cultivar is the part BEFORE the species name
                    matched = lookup[candidate]["cn"]
                    match_idx = t_orig.lower().find(matched.lower())
                    if match_idx > 0:
                        cv = t_orig[:match_idx].strip(" -–—'\"()")
                        # Remove trailing size info like (dwarf), (medium), (semi-dwarf)
                        cv = re.sub(r'\s*\(?(dwarf|semi-dwarf|standard|medium|large|small|miniature)\)?$', '', cv, flags=re.I).strip()
                        if cv and not re.match(r'\d+mm|\d+cm|\d+ltr|pot|pack', cv.lower()):
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
    "forever-seeds": {
        # Only include products that are grown plants/trees, not seed packets or herbs
        "mode": "title_include",
        "include_keywords": ["fruit tree", "fruit plant", "vine plant", "fruiting"],
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

        # Use date-based glob to get last 7 days (handles month/year rollover)
        from datetime import date, timedelta
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        snapshots = sorted([f for f in nursery_dir.glob("2???-??-??.json") if f.stem >= cutoff])
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

            _highlight_skip = ["ornamental", "asparagus", "fertiliz", "fertilis",
                               "potting mix", "insecticide", "fungicide", "herbicide"]
            for p in curr_data.get("products", []):
                title = p.get("title", "")
                url = p.get("url", "")
                variants = p.get("variants", [])
                # Skip non-fruit products in highlights
                _tl = title.lower()
                if any(kw in _tl for kw in _highlight_skip):
                    continue
                if re.search(r'\bseeds?\b', _tl) and 'seedling' not in _tl and 'seedless' not in _tl:
                    continue

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

    if filt.get("mode") == "title_include":
        title_lower = product.get("title", "").lower()
        include_keywords = filt.get("include_keywords", [])
        return any(kw in title_lower for kw in include_keywords)

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
                "ornamental",  # ornamental trees/shrubs are not fruit trees
                "asparagus",   # vegetable, not a fruit tree
            ]
            if any(kw in title_lower for kw in non_plant_keywords):
                continue

            # Skip seed packets (not nursery-grown trees/plants)
            # Match standalone "seed" or "seeds" but not "seedling" or "seedless"
            if re.search(r'\bseeds?\b', title_lower) and 'seedling' not in title_lower and 'seedless' not in title_lower:
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
            if nursery_name in FEATURED_NURSERIES:
                product_data["ft"] = True

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
            "ft": nursery_name in FEATURED_NURSERIES,
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

    # Build species slug lookup for dynamic CTA (common names + synonyms -> slug + display name)
    species_slugs: dict[str, dict] = {}
    if SPECIES_FILE.exists():
        with open(SPECIES_FILE) as f:
            species_data = json.load(f)
        for s in species_data:
            entry = {"slug": s["slug"], "name": s["common_name"]}
            species_slugs[s["common_name"].lower()] = entry
            for syn in s.get("synonyms", []):
                if syn:
                    species_slugs[syn.lower()] = entry
    species_slugs_json = json.dumps(species_slugs, separators=(",", ":"))

    # Server-render species strip for SEO (crawlable <a> tags)
    # data-q attribute drives JS filter; href preserved for crawlers/fallback
    species_strip_html = "\n".join(
        f'<a href="/species/{s["sl"]}.html" class="species-pill" data-q="{s["cn"]}">{s["cn"]} <span class="count">{s["in_stock"]}</span></a>'
        for s in top_species
    )

    extra_style = """\
  .stock-badge { font-size: 0.7rem; padding: 2px 6px; border-radius: 9999px; }
  .restrict-badge { background: #fee2e2; color: #991b1b; font-size: 0.65rem; }
  .sale-badge { background: #fee2e2; color: #991b1b; }
  .new-badge { background: #dbeafe; color: #1e40af; }
  .back-badge { background: #d1fae5; color: #065f46; font-weight: 600; }
  .price-down { color: #059669; font-weight: 600; }
  .price-up { color: #dc2626; }
  .in-stock { background: #d1fae5; color: #065f46; }
  .out-stock { background: #f3f4f6; color: #6b7280; }
  #results { min-height: 200px; }
  .product-row { border-bottom: 1px solid #f3f4f6; }
  .product-row:hover { background: #f9fafb; }
  .product-row.featured-row { border-left: 3px solid #f59e0b; background: #fffdf5; }
  .product-row.featured-row:hover { background: #fef9e7; }
  .nursery-tag { font-size: 0.65rem; padding: 1px 5px; border-radius: 4px; background: #e0e7ff; color: #3730a3; }
  .nursery-tag.featured-tag { background: #fef3c7; color: #92400e; font-weight: 600; }
  .featured-badge { font-size: 0.6rem; padding: 1px 5px; border-radius: 4px; background: #f59e0b; color: white; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
  .species-strip { display: flex; gap: 0.5rem; overflow-x: auto; padding-bottom: 4px; -webkit-overflow-scrolling: touch; scrollbar-width: thin; }
  .species-strip::-webkit-scrollbar { height: 3px; }
  .species-strip::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 3px; }
  .species-pill { flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px; border: 1px solid #e5e7eb; border-radius: 9999px; font-size: 0.8125rem; color: #374151; white-space: nowrap; text-decoration: none; transition: border-color 0.15s, background 0.15s; cursor: pointer; }
  .species-pill:hover { border-color: #22c55e; background: #f0fdf4; color: #065f46; }
  .species-pill.active { border-color: #16a34a; background: #dcfce7; color: #166534; font-weight: 600; }
  .species-pill .count { color: #059669; font-weight: 600; font-size: 0.7rem; }
  .species-pill.active .count { color: #15803d; }"""

    extra_head_tags = """<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="treestock.com.au - Australian Nursery Stock Tracker">
<meta name="twitter:description" content="Track fruit tree stock across Australian nurseries. Daily price drops, restocks, and availability. Filter by state. Free.">
<meta name="twitter:image" content="https://treestock.com.au/og-image.png">"""

    head = render_head(
        title="treestock.com.au - Australian Nursery Stock Tracker",
        description="Track rare fruit and plant stock across Australian nurseries. Search availability, compare prices, find what's in stock.",
        canonical_url="https://treestock.com.au/",
        og_title="treestock.com.au - Australian Nursery Stock Tracker",
        og_description="Track fruit tree stock across Australian nurseries. Daily price drops, restocks, and availability. Filter by state. Free.",
        og_image="https://treestock.com.au/og-image.png",
        og_type="website",
        extra_head=extra_head_tags,
        extra_style=extra_style,
    )

    return f"""{head}
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="max-w-5xl mx-auto px-4 py-2">
    <div class="flex items-center justify-between gap-3">
      <a href="/" class="flex items-center gap-2 no-underline flex-shrink-0">
        {LOGO_SVG}
        <span class="text-lg font-bold text-green-800">{SITE_NAME}</span>
      </a>
      <div class="text-right text-xs text-gray-400">
        <div id="stats" class="hidden sm:block"></div>
        <div id="statsSmall" class="sm:hidden"></div>
        <div class="hidden sm:block">Updated {now}</div>
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

  <!-- Browse by Species -->
  <div id="speciesWrap" class="mb-3">
    <div class="species-strip">{species_strip_html}</div>
  </div>

  <!-- Results -->
  <div id="results"></div>
  <div id="loadMore" class="text-center py-4 hidden">
    <button onclick="showMore()" class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700">
      Show more results
    </button>
  </div>

  <!-- Email Alerts Signup (below results) -->
  <div class="mt-6 mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
    <div class="flex flex-col sm:flex-row sm:items-center gap-2">
      <p id="subCTA" class="text-sm text-green-800 flex-1"><strong>Get tomorrow's changes in your inbox</strong> — free daily email, unsubscribe any time. <a href="/sample-digest.html" class="text-green-700 underline whitespace-nowrap">See example &rarr;</a></p>
      <form id="subscribeForm" class="flex gap-2 flex-shrink-0 flex-wrap">
        <input type="email" id="subEmail" placeholder="your@email.com" required
          class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 w-44">
        <select id="subState" class="px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
          <option value="ALL">All states</option>
          <option value="NSW">NSW</option><option value="VIC">VIC</option>
          <option value="QLD">QLD</option><option value="WA">WA</option>
          <option value="SA">SA</option><option value="TAS">TAS</option>
          <option value="NT">NT</option><option value="ACT">ACT</option>
        </select>
        <button type="submit" class="px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium">
          Subscribe free
        </button>
      </form>
    </div>
    <div id="subMessage" class="mt-2 text-sm hidden"></div>
  </div>

{highlights_html}


</main>

{render_footer(max_width="max-w-5xl", extra_text='<a href="/advertise.html" class="underline">Nursery partnerships</a>')}

<script>
const P = {products_json};
const N = {nurseries_json};
const SPECIES_SLUGS = {species_slugs_json};

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

// Populate nursery filter (featured nurseries first, then alphabetical)
const nurserySelect = document.getElementById('nurseryFilter');
const sortedN = [...N].sort((a, b) => (b.ft ? 1 : 0) - (a.ft ? 1 : 0) || a.name.localeCompare(b.name));
sortedN.forEach(n => {{
  const opt = document.createElement('option');
  opt.value = n.key;
  opt.textContent = n.ft
    ? `* ${{n.name}} (${{n.in_stock}} in stock)`
    : `${{n.name}} (${{n.in_stock}} in stock)`;
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

  // Featured nurseries bubble to top within current sort (only on default/name sort, not price sort)
  if (!sort || sort === 'name') {{
    results.sort((a, b) => (b.ft ? 1 : 0) - (a.ft ? 1 : 0));
  }}

  currentResults = results;
  render();
  updateSubCTA(q);
}}

function updateSubCTA(q) {{
  const ctaEl = document.getElementById('subCTA');
  if (!ctaEl) return;
  const floatInput = document.getElementById('floatEmail');

  if (!q) {{
    ctaEl.innerHTML = `<strong>Get tomorrow's changes in your inbox</strong> \u2014 free daily email, unsubscribe any time. <a href="/sample-digest.html" class="text-green-700 underline whitespace-nowrap">See example &rarr;</a>`;
    if (floatInput) floatInput.placeholder = 'Get daily alerts (free)';
    return;
  }}

  // Check if query matches a known species (try longest match first)
  const words = q.split(/\s+/);
  let matched = null;
  for (let n = words.length; n >= 1; n--) {{
    const candidate = words.slice(0, n).join(' ');
    if (SPECIES_SLUGS[candidate]) {{
      matched = SPECIES_SLUGS[candidate];
      break;
    }}
  }}

  if (matched) {{
    const name = matched.name;
    const slug = matched.slug;
    ctaEl.innerHTML = `<strong>Get alerted when ${{name}} prices change or come back in stock</strong> — free daily email. <a href="/species/${{slug}}.html" class="text-green-700 underline whitespace-nowrap">See all ${{name}} &rarr;</a>`;
    if (floatInput) floatInput.placeholder = `${{name}} price alerts (free)`;
  }} else {{
    const displayQ = q.length > 20 ? q.slice(0, 20) + '...' : q;
    ctaEl.innerHTML = `<strong>Get alerted when "${{displayQ}}" prices change</strong> — free daily email, unsubscribe any time. <a href="/sample-digest.html" class="text-green-700 underline whitespace-nowrap">See example &rarr;</a>`;
    if (floatInput) floatInput.placeholder = `"${{displayQ}}" price alerts (free)`;
  }}
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
    const featuredClass = p.ft ? ' featured-row' : '';
    const nurseryTagClass = p.ft ? 'nursery-tag featured-tag' : 'nursery-tag';
    const featuredBadge = p.ft ? '<span class="featured-badge">Featured</span>' : '';
    return `<a href="${{p.u}}${{utm}}" target="_blank" rel="noopener" class="product-row${{featuredClass}} flex items-center gap-3 py-3 px-2 block">
      <div class="flex-1 min-w-0">
        <div class="font-medium text-sm">${{p.t}}${{latinName}}</div>
        <div class="flex items-center gap-1.5 mt-0.5 flex-wrap">
          <span class="${{nurseryTagClass}}">${{p.n}}</span>
          ${{featuredBadge}} ${{stockBadge}} ${{shipsBadge}} ${{saleBadge}} ${{changeBadge}}
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
searchInput.addEventListener('input', function() {{
  // Clear active pill when user types manually
  document.querySelectorAll('.species-pill.active').forEach(p => p.classList.remove('active'));
  search();
}});
inStockOnly.addEventListener('change', search);
stateFilter.addEventListener('change', function() {{
  search();
  // Sync subscribe state dropdown with search filter
  const subState = document.getElementById('subState');
  if (subState && stateFilter.value) subState.value = stateFilter.value;
}});
changesOnly.addEventListener('change', search);
nurserySelect.addEventListener('change', search);
sortBy.addEventListener('change', search);

// Species strip pill click: filter homepage results (preserving all other filters)
document.querySelectorAll('.species-pill[data-q]').forEach(function(pill) {{
  pill.addEventListener('click', function(e) {{
    e.preventDefault();
    const q = this.getAttribute('data-q');
    const isActive = this.classList.contains('active');
    // Clear all active pills
    document.querySelectorAll('.species-pill.active').forEach(p => p.classList.remove('active'));
    if (isActive) {{
      // Clicking an active pill clears the species filter
      searchInput.value = '';
    }} else {{
      // Set species search and mark this pill active
      searchInput.value = q;
      this.classList.add('active');
    }}
    search();
    // Scroll to results
    const results = document.getElementById('results');
    if (results) results.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }});
}});

// Initial render
search();

// Subscribe form
document.getElementById('subscribeForm').addEventListener('submit', async (e) => {{
  e.preventDefault();
  const email = document.getElementById('subEmail').value;
  const state = document.getElementById('subState').value;
  const msg = document.getElementById('subMessage');
  const btn = e.target.querySelector('button');
  btn.disabled = true;
  btn.textContent = 'Subscribing...';
  try {{
    const resp = await fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email, state}}),
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

// Floating subscribe bar (mobile only — shows after scroll or timer)
(function() {{
  if (localStorage.getItem('ts_subscribed')) return;
  // 3-day dismiss cooldown (not per-session, so returning visitors still see it)
  const dismissedUntil = localStorage.getItem('ts_bar_dismissed_until');
  if (dismissedUntil && Date.now() < parseInt(dismissedUntil, 10)) return;

  const bar = document.getElementById('floatBar');
  if (!bar) return;

  // Sync placeholder text with main CTA if it has been updated
  const subCTA = document.getElementById('subCTA');
  const floatInput = document.getElementById('floatEmail');
  if (subCTA && floatInput) {{
    const ctaText = subCTA.innerText || '';
    if (ctaText.includes('Get alerted when') && ctaText.length < 80) {{
      floatInput.placeholder = ctaText.replace('Get alerted when', 'Alert me when').replace(' — free daily email', '').trim().slice(0, 50) || 'Get daily alerts (free)';
    }}
  }}

  let shown = false;
  function showBar() {{
    if (shown) return;
    shown = true;
    bar.classList.remove('translate-y-full');
    bar.classList.add('translate-y-0');
  }}

  // Show after 150px scroll (was 300px — show sooner)
  window.addEventListener('scroll', function() {{
    if (!shown && window.scrollY > 150) showBar();
  }}, {{ passive: true }});

  // Also show after 40 seconds even without scrolling (time-based fallback)
  setTimeout(showBar, 40000);

  document.getElementById('floatDismiss').addEventListener('click', function() {{
    // 3-day cooldown — won't pester same-day, but will show to return visitors
    localStorage.setItem('ts_bar_dismissed_until', Date.now() + 3 * 24 * 60 * 60 * 1000);
    bar.classList.add('translate-y-full');
  }});

  document.getElementById('floatForm').addEventListener('submit', async function(e) {{
    e.preventDefault();
    const email = document.getElementById('floatEmail').value;
    const state = document.getElementById('subState') ? document.getElementById('subState').value : 'ALL';
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = '...';
    try {{
      const resp = await fetch('/api/subscribe', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{email, state}}),
      }});
      const data = await resp.json();
      if (resp.status === 201 || resp.status === 200) {{
        localStorage.setItem('ts_subscribed', '1');
        bar.innerHTML = `<div class="flex items-center justify-center gap-2 py-3 px-4 text-sm text-green-800 font-medium">Subscribed! You'll get tomorrow's changes in your inbox.</div>`;
        setTimeout(function() {{ bar.classList.add('translate-y-full'); }}, 3000);
      }} else {{
        btn.disabled = false;
        btn.textContent = 'Subscribe';
        document.getElementById('floatMsg').textContent = data.message || 'Try again';
        document.getElementById('floatMsg').classList.remove('hidden');
      }}
    }} catch(err) {{
      btn.disabled = false;
      btn.textContent = 'Subscribe';
    }}
  }});
}})();

</script>

<!-- Floating subscribe bar (mobile only) -->
<div id="floatBar" class="md:hidden fixed bottom-0 left-0 right-0 bg-green-700 text-white shadow-lg transform translate-y-full transition-transform duration-300 z-50">
  <div class="flex items-center gap-2 px-3 py-2.5">
    <form id="floatForm" class="flex items-center gap-2 flex-1 min-w-0">
      <input type="email" id="floatEmail" placeholder="Get daily alerts (free)" required
        class="flex-1 min-w-0 px-2.5 py-1.5 rounded-lg text-sm text-gray-900 border-0 focus:outline-none focus:ring-2 focus:ring-white">
      <button type="submit" class="flex-shrink-0 px-3 py-1.5 bg-white text-green-700 rounded-lg text-sm font-semibold">
        Subscribe
      </button>
    </form>
    <button id="floatDismiss" aria-label="Dismiss" class="flex-shrink-0 text-green-200 hover:text-white pl-1 text-lg leading-none">&times;</button>
  </div>
  <div id="floatMsg" class="hidden text-xs text-green-200 px-3 pb-2"></div>
</div>

</body>
</html>"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build treestock.com.au dashboard")
    parser.add_argument("data_dir", help="Path to nursery-stock/ directory")
    parser.add_argument("output_dir", nargs="?", default="dashboard-output", help="Where to write index.html (default: ./dashboard-output/)")
    parser.add_argument("--featured", metavar="NURSERY_KEY", help="Nursery key to feature (e.g. primal-fruits). Overrides FEATURED_NURSERIES constant. Use for demo/preview builds only.")
    parser.add_argument("--output-name", default="index.html", metavar="FILENAME", help="Output filename (default: index.html). Use e.g. featured-demo.html for demo builds.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist")
        sys.exit(1)

    # --featured flag overrides the FEATURED_NURSERIES constant without modifying source
    global FEATURED_NURSERIES
    if args.featured:
        FEATURED_NURSERIES = {args.featured}
        print(f"Featured nursery override: {args.featured}")

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

    # Atomic write: write to temp file then rename to avoid serving partial HTML
    out_file = output_dir / args.output_name
    tmp_file = output_dir / (args.output_name + ".tmp")
    tmp_file.write_text(html)
    tmp_file.rename(out_file)
    print(f"Dashboard written to {out_file} ({len(html):,} bytes)")

    # Post-build verification
    actual_size = out_file.stat().st_size
    if actual_size < 500_000:
        print(f"WARNING: Output file is suspiciously small ({actual_size:,} bytes). Expected >500KB.", file=sys.stderr)
        sys.exit(2)
    if len(products) < 1000:
        print(f"WARNING: Only {len(products)} products loaded. Expected >1000. Check scrapers.", file=sys.stderr)
        sys.exit(2)
    print(f"Verification passed: {actual_size:,} bytes, {len(products)} products")


if __name__ == "__main__":
    main()
