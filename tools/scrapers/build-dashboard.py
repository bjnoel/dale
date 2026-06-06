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
from shipping import SHIPPING_MAP, NURSERY_NAMES, LOCAL_DELIVERY
from treestock_layout import render_head, render_footer, SITE_NAME, LOGO_SVG, NAV_ITEMS
from cultivar_parsing import product_variety_slug
from stocklib.taxonomy import load_species
# Reuse the variety builder's non-plant denylist so we never emit a variety
# slug (vs) for a product it would refuse to build a /variety/ page for
# (e.g. "Yates Apple": "yates" is a chemical brand in that list). Keeping a
# single source avoids the two lists drifting and producing broken links.
from build_variety_pages import NON_PLANT_KEYWORDS as _VARIETY_PAGE_DENY


# Confirmed via nursery websites/policies:
# - Daleys: ships to WA seasonally (special quarantine window, extra $25+ fee)
# - Primal Fruits: WA-based, ships within WA
# - Ross Creek: ships QLD/NSW/ACT/VIC only, NOT WA (quarantine restrictions noted)
# - Ladybird: ships QLD/NSW/VIC/ACT only, NOT WA
# - Fruitopia: unclear from policy, likely does NOT ship to WA (QLD-based, no WA mention)
SPECIES_FILE = Path(__file__).parent / "fruit_species.json"
RARITY_SCORES_FILE = Path("/opt/dale/data/rarity_scores.json")

# Featured nurseries (paying partners). Products are visually highlighted and sorted first.
# To activate a featured listing, add the nursery key here.
FEATURED_NURSERIES: set[str] = set()  # e.g. {'primal-fruits'} when live


def load_species_lookup() -> dict:
    """Load fruit species data and build a title-matching lookup."""
    species = load_species()

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
            <span class="text-gray-500"> ({r['nursery']})</span>
          </span>
          <span class="text-sm font-semibold text-gray-700 flex-shrink-0">{price_str}</span>
        </li>"""

    drop_rows = ""
    for d in top_drops:
        drop_rows += f"""<li class="flex items-baseline gap-1.5 py-1 border-b border-blue-100 last:border-0">
          <span class="text-blue-600 font-bold text-sm">&darr;</span>
          <span class="text-sm flex-1 min-w-0">
            <span class="font-medium">{d['title']}</span>
            <span class="text-gray-500"> ({d['nursery']})</span>
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
            _vs = product_variety_slug(title)
            if _vs and not any(kw in title_lower for kw in _VARIETY_PAGE_DENY):
                product_data["vs"] = _vs
                product_data["vt"] = title
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
            "lo": LOCAL_DELIVERY.get(nursery_name, {}).get("area", ""),
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

    # Full in-stock species list, ranked by current in-stock count (desc). The homepage
    # strip server-renders all of these as crawlable <a> links; JS collapses the view to a
    # default tier plus a progressive "Other" reveal for humans (see updatePillCounts).
    ranked_species = [
        s for s in sorted(species_summary.values(), key=lambda x: -x["in_stock"])
        if s["in_stock"] > 0
    ]

    return products, nurseries_loaded, ranked_species


def build_html(products: list[dict], nurseries: list[dict], ranked_species: list[dict], highlights_html: str = "") -> str:
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

    # Build hard-to-find slug set from computed rarity scores
    hard_to_find_slugs: set[str] = set()
    if RARITY_SCORES_FILE.exists():
        try:
            with open(RARITY_SCORES_FILE) as f:
                rarity_data = json.load(f)
            hard_to_find_slugs = {slug for slug, r in rarity_data.items() if r.get("hard_to_find")}
        except Exception:
            pass
    hard_to_find_json = json.dumps(list(hard_to_find_slugs), separators=(",", ":"))
    # Single JSON blob for the externalized dashboard.js (read via the
    # <script type="application/json"> island).
    dashboard_data_json = json.dumps({
        "products": products, "nurseries": nurseries,
        "species_slugs": species_slugs, "hard_to_find": list(hard_to_find_slugs),
    }, separators=(",", ":"))
    cache_v = datetime.now(timezone.utc).strftime("%Y%m%d")

    # Server-render the FULL in-stock species strip for SEO: every species page is linked
    # from the homepage as a crawlable <a>. data-q drives the JS filter; href is the
    # crawler / no-JS fallback. On load, JS (updatePillCounts) rebuilds this strip into a
    # default tier plus a progressive "Other" pill, so humans see a compact strip. The
    # static markup is served identically to everyone (no cloaking / no UA sniffing).
    species_strip_html = "\n".join(
        f'<a href="/species/{s["sl"]}.html" class="species-pill" data-q="{s["cn"]}" data-sl="{s["sl"]}">{s["cn"]} <span class="count">{s["in_stock"]}</span></a>'
        for s in ranked_species
    )

    extra_style = """\
  .stock-badge { font-size: 0.7rem; padding: 2px 6px; border-radius: 9999px; }
  .restrict-badge { background: #fee2e2; color: #991b1b; font-size: 0.65rem; }
  .local-badge { background: #fef3c7; color: #92400e; font-size: 0.65rem; }
  .sale-badge { background: #fee2e2; color: #991b1b; }
  .new-badge { background: #dbeafe; color: #1e40af; }
  .back-badge { background: #d1fae5; color: #065f46; font-weight: 600; }
  .price-down { color: #059669; font-weight: 600; }
  .price-up { color: #dc2626; }
  .in-stock { background: #d1fae5; color: #065f46; }
  .out-stock { background: #f3f4f6; color: #6b7280; }
  #results { min-height: 200px; }
  .product-row-wrap { border-bottom: 1px solid #f3f4f6; }
  .notify-link { display: inline-block; margin: 0 0 8px 0.5rem; padding: 2px 10px; font-size: 0.75rem; color: #15803d; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 9999px; text-decoration: none; }
  .notify-link:hover { background: #dcfce7; }
  .product-row:hover { background: #f9fafb; }
  .product-row.featured-row { border-left: 3px solid #f59e0b; background: #fffdf5; }
  .product-row.featured-row:hover { background: #fef9e7; }
  .nursery-tag { font-size: 0.65rem; padding: 1px 5px; border-radius: 4px; background: #e0e7ff; color: #3730a3; cursor: pointer; }
  .nursery-tag:hover { background: #c7d2fe; }
  .nursery-tag.featured-tag { background: #fef3c7; color: #92400e; font-weight: 600; }
  .featured-badge { font-size: 0.6rem; padding: 1px 5px; border-radius: 4px; background: #f59e0b; color: white; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }
  .rare-badge { font-size: 0.6rem; padding: 1px 5px; border-radius: 4px; background: #fef3c7; color: #92400e; font-weight: 700; cursor: pointer; }
  .rare-badge:hover { background: #fde68a; }
  .species-strip { display: flex; gap: 0.5rem; flex-wrap: wrap; max-height: 34px; overflow: hidden; padding-bottom: 4px; transition: max-height 0.2s ease; }
  .species-strip.expanded { max-height: 500px; }
  .toggle-pills-btn { background: none; border: none; color: #059669; font-size: 0.75rem; cursor: pointer; padding: 4px 0 0; }
  .toggle-pills-btn:hover { text-decoration: underline; }
  .species-pill { flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px; border: 1px solid #e5e7eb; border-radius: 9999px; font-size: 0.8125rem; color: #374151; white-space: nowrap; text-decoration: none; transition: border-color 0.15s, background 0.15s; cursor: pointer; }
  .species-pill:hover { border-color: #22c55e; background: #f0fdf4; color: #065f46; }
  .species-pill.active { border-color: #16a34a; background: #dcfce7; color: #166534; font-weight: 600; }
  .species-pill .count { color: #059669; font-weight: 600; font-size: 0.7rem; }
  .species-pill.active .count { color: #15803d; }
  .species-pill.dimmed { opacity: 0.4; }
  .species-pill.dimmed .count { color: #9ca3af; }
  .other-pill { cursor: pointer; color: #6b7280; border-color: #e5e7eb; border-style: dashed; }
  .other-pill:hover { background: #f9fafb; border-color: #9ca3af; color: #374151; }
  .other-pill .count { color: #6b7280; }
  .filter-chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
  .filter-chip button { background: none; border: none; color: #166534; font-size: 0.85rem; cursor: pointer; padding: 0; line-height: 1; }
  .filter-chip button:hover { color: #dc2626; }"""

    # Twitter Card + og:title/description/image/type are emitted by render_head;
    # only the og:image dimensions (which render_head does not model) are added here.
    extra_head_tags = """<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">"""

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
    <div id="speciesWrap">
      <div class="species-strip">{species_strip_html}</div>
      <button id="toggleSpecies" class="toggle-pills-btn" style="display:none">Show all &#9662;</button>
    </div>
    <div id="activeFilters" class="flex flex-wrap gap-1.5" style="display:none"></div>
    <div class="flex flex-wrap gap-2 items-center text-sm">
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" id="inStockOnly" class="rounded"> In stock only
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
      <p id="subCTA" class="text-sm text-green-800 flex-1"><strong>Get the free WA Rare Fruit Guide + restock alerts.</strong> Free daily email, unsubscribe any time. <a href="/wa-rare-fruit-guide.html" class="text-green-700 underline whitespace-nowrap">Preview the guide &rarr;</a></p>
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
        <button id="subBtn" type="submit" class="px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium">
          Subscribe free
        </button>
      </form>
    </div>
    <div id="subMessage" class="mt-2 text-sm hidden"></div>
  </div>

{highlights_html}


</main>

{render_footer(max_width="max-w-5xl", extra_text='<a href="/advertise.html" class="underline">Nursery partnerships</a>')}

<script type="application/json" id="dashboard-data">{dashboard_data_json}</script>
<script src="/dashboard.js?v={cache_v}" defer></script>

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
    products, nurseries, ranked_species = load_nursery_data(data_dir)
    print(f"Loaded {len(products)} products from {len(nurseries)} nurseries")

    for n in nurseries:
        print(f"  {n['name']}: {n['count']} products ({n['in_stock']} in stock)")
    print(f"  Top species for grid: {', '.join(s['cn'] for s in ranked_species[:5])} ({len(ranked_species)} species linked)")

    print("Building recent highlights...")
    highlights_html = build_recent_highlights(data_dir)
    print(f"  Highlights section: {'generated' if highlights_html else 'empty (insufficient data)'}")

    output_dir.mkdir(parents=True, exist_ok=True)
    html = build_html(products, nurseries, ranked_species, highlights_html)

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
