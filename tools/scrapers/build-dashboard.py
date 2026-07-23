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
from treestock_layout import render_head, render_header, render_footer, CONTENT_MAX_WIDTH, organization_jsonld, website_jsonld
from cultivar_parsing import product_variety_slug
from stocklib.classify import CATEGORY_KEYWORDS, TRUE_JUNK, is_seed_packet
from stocklib.taxonomy import enabled_species, load_species
from stocklib.species_match import load_species_lookup, match_species
from stocklib.category_ui import category_keys, CATEGORY_BADGE_CSS
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
RARITY_SCORES_FILE = Path("/opt/dale/data/rarity_scores.json")

# Dashboard junk filter (DEC-200 P1.5): the shared true-junk list plus the
# ornamental and vegetable plant keywords. Native keywords are deliberately
# EXCLUDED: the dashboard has always shown the handful of live melaleuca /
# wattle rows and they must stay visible (as unclassified search results)
# rather than vanish at the de-fork. The variety/species/compare surfaces
# keep using the stricter NON_PLANT_KEYWORDS.
DASHBOARD_JUNK_KEYWORDS = TRUE_JUNK | {
    kw for kw, cat in CATEGORY_KEYWORDS.items() if cat in ("ornamental", "vegetable")
}

# Featured nurseries (paying partners). Products are visually highlighted and sorted first.
# To activate a featured listing, add the nursery key here.
FEATURED_NURSERIES: set[str] = set()  # e.g. {'primal-fruits'} when live


def _all_records_category_matcher():
    """Rung 1 of the categorize ladder (DEC-200): the existing match_species
    flow over ALL species records, enabled or not ("category known but
    disabled" is needs-review information, not junk), returning the matched
    record's category."""
    lookup: dict[str, dict] = {}
    for s in load_species():
        entry = {"cn": s["common_name"], "category": s.get("category", "fruit")}
        lookup[s["common_name"].lower()] = entry
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = entry

    def matcher(title: str):
        m = match_species(title, lookup)
        return m["category"] if m else None
    return matcher


def write_needs_review(products: list[dict], out_path: Path) -> None:
    """Run the categorize ladder over the dashboard's (already junk-filtered)
    products and write the per-nursery needs-review report for /admin."""
    from stocklib.categorize import Categorizer, build_needs_review
    categorizer = Categorizer(species_matcher=_all_records_category_matcher())
    report = build_needs_review(
        ((p["t"], p.get("nk", ""), p.get("cat", "")) for p in products),
        categorizer,
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    total_unclassified = sum(n["unclassified"] for n in report["nurseries"].values())
    print(f"Needs-review report written to {out_path} "
          f"({total_unclassified} unclassified products)")


# Per-nursery fruit-only filters: shared with daily_digest.py via stocklib
# (the two copies drifted; see stocklib/fruit_filters.py).
from stocklib.fruit_filters import FRUIT_FILTERS, is_fruit_product


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
                if is_seed_packet(_tl):
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
          <span class="text-sm flex-shrink-0"><span class="line-through text-gray-500">${d['old_price']:.0f}</span> <span class="font-semibold text-blue-700">${d['new_price']:.0f}</span> <span class="text-blue-600">&minus;{d['pct']}%</span></span>
        </li>"""

    total_restocks = len(restocks)
    total_drops = len(price_drops)

    return f"""  <!-- Recent Highlights — "what subscribers knew this week" -->
  <div class="mb-4 rounded-lg border border-gray-200 overflow-hidden">
    <div class="bg-gray-50 px-4 py-2.5 border-b border-gray-200 flex items-center justify-between">
      <span class="text-sm font-semibold text-gray-700">📬 What subscribers got alerted to this week</span>
      <span class="text-xs text-gray-600">{total_restocks} restocks · {total_drops} price drops detected</span>
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




# Category landing pages (DEC-200 IA / DAL-198). Each reuses the full dashboard
# search + filters + results, scoped to one category's stock. The homepage is
# NOT in here and is never touched (results above the fold, nothing above them).
# To add a category: enable it in stocklib.taxonomy, then add an entry here and
# a nav link in treestock_layout.NAV_ITEMS.
_BUSH_TUCKER_INTRO = """  <div class="mb-4">
    <h1 class="text-2xl font-bold text-green-900 mb-1">Australian Bush Tucker Plants</h1>
    <p class="text-sm text-gray-600">Native food plants in stock across Australian nurseries. Search lemon myrtle, finger lime, warrigal greens, mountain pepper, quandong and more, then compare prices and check which nurseries ship to your state. Updated daily.</p>
  </div>"""

LANDING_PAGES: dict[str, dict] = {
    "bush_tucker": {
        "title": "Australian Bush Tucker Plants for Sale, Compare Prices | treestock.com.au",
        "description": "Find Australian bush tucker and native food plants in stock across nurseries: lemon myrtle, finger lime, warrigal greens, mountain pepper, quandong and more. Compare prices, check availability and shipping.",
        "canonical_url": "https://treestock.com.au/bush-tucker/",
        "og_title": "Australian Bush Tucker Plants",
        "og_description": "Track bush tucker and native food plant stock across Australian nurseries. Lemon myrtle, finger lime, warrigal greens, quandong and more. Free.",
        "active_path": "/bush-tucker/",
        "search_placeholder": "Search bush tucker... (e.g. lemon myrtle, finger lime, warrigal greens)",
        "data_url": "/bush-tucker/data.js",
        "intro_html": _BUSH_TUCKER_INTRO,
    },
}


def filter_to_category(products: list[dict], nurseries: list[dict],
                       ranked_species: list[dict], category: str):
    """Scope the loaded dashboard data to one category landing page (DAL-198).

    A product belongs if it matched a species in the category's landing set
    (the species' own category OR a cross-listing tag, e.g. the bush-tucker-
    tagged fruits like Finger Lime), OR the categorize ladder routes it into the
    category via the nursery's category_raw mapping (e.g. a Daleys "Bush Food
    Plants" product with no species record). Returns scoped
    (products, nurseries, ranked_species)."""
    from stocklib.categorize import Categorizer
    from stocklib.taxonomy import landing_species

    landing_slugs = {s["slug"] for s in landing_species(category)}
    categorizer = Categorizer(species_matcher=_all_records_category_matcher())

    kept = []
    for p in products:
        sl = p.get("sl")
        if sl and sl in landing_slugs:
            kept.append(p)
            continue
        cat, _src = categorizer.categorize(
            p.get("t", ""), p.get("nk", ""), p.get("cat", ""))
        if cat == category:
            kept.append(p)

    kept_keys = {p.get("nk") for p in kept}
    kept_nurseries = []
    for n in nurseries:
        if n["key"] not in kept_keys:
            continue
        n = dict(n)
        n_products = [p for p in kept if p.get("nk") == n["key"]]
        n["count"] = len(n_products)
        n["in_stock"] = sum(1 for p in n_products if p.get("a"))
        kept_nurseries.append(n)

    kept_ranked = [s for s in ranked_species if s["sl"] in landing_slugs]
    return kept, kept_nurseries, kept_ranked


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

            # Skip items matching non-plant keywords in title (shared list;
            # natives deliberately exempt, see DASHBOARD_JUNK_KEYWORDS)
            if any(kw in title_lower for kw in DASHBOARD_JUNK_KEYWORDS):
                continue

            # Skip seed packets (not nursery-grown trees/plants)
            if is_seed_packet(title_lower):
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
    # Resolve common names from the species lookup by SLUG. The slug is unique
    # per record (enforced by the taxonomy schema test); the latin name is NOT
    # -- Riberry and Lilly Pilly both carry Syzygium luehmannii -- so keying cn
    # resolution on the latin name mislabelled one of them (surfaced at the
    # DAL-197 bush tucker enable).
    sl_to_cn: dict[str, str] = {}
    if species_lookup:
        for entry in species_lookup.values():
            sl_, cn = entry.get("sl", ""), entry.get("cn", "")
            if sl_ and cn:
                sl_to_cn.setdefault(sl_, cn)

    for sl, s in species_summary.items():
        if not s["cn"]:
            s["cn"] = sl_to_cn.get(sl, sl.replace("-", " ").title())
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


def build_html(products: list[dict], nurseries: list[dict], ranked_species: list[dict], highlights_html: str = "", landing: dict | None = None) -> str:
    # `landing` carries per-page overrides for a category landing page (e.g.
    # /bush-tucker/, DAL-198). When None every value below is the homepage
    # default, so the homepage output is byte-identical.
    L = landing or {}
    """Generate the dashboard HTML with embedded data."""
    products_json = json.dumps(products, separators=(",", ":"))
    nurseries_json = json.dumps(nurseries, separators=(",", ":"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build species slug lookup for dynamic CTA (common names + synonyms -> slug + display name)
    species_slugs: dict[str, dict] = {}
    for s in enabled_species():
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
    hard_to_find_json = json.dumps(sorted(hard_to_find_slugs), separators=(",", ":"))
    # Single JSON blob, written to an external data.js (window.__DATA) that loads
    # `defer` before dashboard.js. Keeping it out of the HTML shrinks the document
    # ~70x for a much faster FCP; JSON.parse of a string literal keeps the parse fast
    # so TBT stays flat. dashboard.js reads window.__DATA synchronously (defer order).
    # Per-species category list (primary category + cross-listing tags) so the
    # results JS can badge each row Fruit / Bush Tucker and filter by category.
    # A cross-listed species (finger-lime) maps to ["fruit", "bush_tucker"].
    species_cats = {s["slug"]: category_keys(s) for s in enabled_species()}

    dashboard_data_json = json.dumps({
        "products": products, "nurseries": nurseries,
        "species_slugs": species_slugs, "hard_to_find": sorted(hard_to_find_slugs),
        "species_cats": species_cats,
    }, separators=(",", ":"))
    data_js = "window.__DATA=JSON.parse(" + json.dumps(dashboard_data_json) + ");"
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
  .price-down { color: #047857; font-weight: 600; }
  .price-up { color: #b91c1c; }
  .in-stock { background: #d1fae5; color: #065f46; }
  .out-stock { background: #f3f4f6; color: #4b5563; }
  #results { min-height: 200px; }
  /* Reserve a screen of height while the results container is empty (pre-JS), so the
     rows dashboard.js injects on load fill reserved space instead of shoving the
     subscribe block / footer down. Kills the load-time layout shift (was CLS 0.945).
     :empty stops matching the instant JS sets innerHTML, so it never gaps a filled view. */
  #results:empty { min-height: 100vh; }
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
  .toggle-pills-btn { background: none; border: none; color: #047857; font-size: 0.75rem; cursor: pointer; padding: 8px 6px; margin-top: 2px; }
  .toggle-pills-btn:hover { text-decoration: underline; }
  .species-pill { flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px; border: 1px solid #e5e7eb; border-radius: 9999px; font-size: 0.8125rem; color: #374151; white-space: nowrap; text-decoration: none; transition: border-color 0.15s, background 0.15s; cursor: pointer; }
  .species-pill:hover { border-color: #22c55e; background: #f0fdf4; color: #065f46; }
  .species-pill.active { border-color: #16a34a; background: #dcfce7; color: #166534; font-weight: 600; }
  .species-pill .count { color: #047857; font-weight: 600; font-size: 0.7rem; }
  .species-pill.active .count { color: #15803d; }
  .species-pill.dimmed { opacity: 0.4; }
  .species-pill.dimmed .count { color: #9ca3af; }
  .other-pill { cursor: pointer; color: #6b7280; border-color: #e5e7eb; border-style: dashed; }
  .other-pill:hover { background: #f9fafb; border-color: #9ca3af; color: #374151; }
  .other-pill .count { color: #6b7280; }
  .filter-chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
  .filter-chip button { background: none; border: none; color: #166534; font-size: 0.85rem; cursor: pointer; padding: 0; line-height: 1; }
  .filter-chip button:hover { color: #dc2626; }
  .search-box { position: relative; }
  .search-suggest { position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 30; margin: 0; padding: 4px; list-style: none; background: #fff; border: 1px solid #d1d5db; border-radius: 0.5rem; box-shadow: 0 8px 24px rgba(0,0,0,0.12); max-height: 320px; overflow-y: auto; }
  .search-suggest[hidden] { display: none; }
  .search-suggest li { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 8px 12px; border-radius: 0.375rem; font-size: 0.95rem; color: #1f2937; cursor: pointer; }
  .search-suggest li.active, .search-suggest li:hover { background: #f0fdf4; color: #065f46; }
  .search-suggest .suggest-name { font-weight: 500; }
  .search-suggest .suggest-syn { font-weight: 400; color: #6b7280; font-size: 0.8rem; margin-left: 4px; }
  .search-suggest .suggest-count { flex-shrink: 0; color: #047857; font-size: 0.75rem; white-space: nowrap; }
""" + CATEGORY_BADGE_CSS

    # Optional intro block above the search (category landing pages only; the
    # homepage stays "search first" with nothing above results). Empty -> the
    # homepage markup is unchanged.
    intro_html = L.get("intro_html", "")
    intro_block = ("\n" + intro_html) if intro_html else ""
    data_url = L.get("data_url", "/data.js")

    # Category filter (Fruit / Bush Tucker) sits in the existing filter row on the
    # homepage only. Category landing pages (e.g. /bush-tucker/) are already scoped
    # to one category, so the control would be redundant there.
    category_filter_html = "" if landing is not None else (
        '<select id="categoryFilter" aria-label="Filter by plant category" '
        'class="border border-gray-300 rounded px-2 py-1 text-sm">'
        '<option value="">All plants</option>'
        '<option value="fruit">Fruit</option>'
        '<option value="bush_tucker">Bush Tucker</option>'
        '</select>'
    )

    # Twitter Card + og:title/description/image/type are emitted by render_head;
    # only the og:image dimensions (which render_head does not model) are added here.
    extra_head_tags = """<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">"""

    head = render_head(
        title=L.get("title", "treestock.com.au - Australian Nursery Stock Tracker"),
        description=L.get("description", "Track rare fruit and plant stock across Australian nurseries. Search availability, compare prices, find what's in stock."),
        canonical_url=L.get("canonical_url", "https://treestock.com.au/"),
        og_title=L.get("og_title", "treestock.com.au - Australian Nursery Stock Tracker"),
        og_description=L.get("og_description", "Track fruit tree stock across Australian nurseries. Daily price drops, restocks, and availability. Filter by state. Free."),
        og_image="https://treestock.com.au/og-image.png",
        og_type="website",
        jsonld=L.get("jsonld", [organization_jsonld(), website_jsonld()]),
        extra_head=extra_head_tags,
        extra_style=extra_style,
    )

    # Shared site header/nav (same chrome as every other page). The "Updated"
    # timestamp sits top-right on the logo row via extra_right (hidden on mobile,
    # where the hamburger takes that spot); the in-stock stat now lives in the
    # footer (see render_footer below).
    header = render_header(
        max_width=CONTENT_MAX_WIDTH,
        show_nav=True,
        active_path=L.get("active_path", "/"),
        extra_right=f'<span class="text-xs text-gray-500 hidden sm:block">Updated {now}</span>',
    )

    html = f"""{head}
{header}

<main class="{CONTENT_MAX_WIDTH} mx-auto px-4 py-4">{intro_block}
  <!-- Search & Filters -->
  <div class="mb-4 space-y-3">
    <div class="search-box relative">
      <input type="text" id="search" placeholder="{L.get("search_placeholder", "Search plants... (e.g. sapodilla, mango, fig)")}"
        class="w-full px-4 py-3 border border-gray-300 rounded-lg text-lg focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
        autofocus autocomplete="off" role="combobox" aria-expanded="false"
        aria-controls="searchSuggest" aria-autocomplete="list" aria-label="Search plants">
      <ul id="searchSuggest" role="listbox" aria-label="Species suggestions" class="search-suggest" hidden></ul>
    </div>
    <div id="speciesWrap">
      <div class="species-strip">{species_strip_html}</div>
      <button id="toggleSpecies" class="toggle-pills-btn" style="display:none">Show all &#9662;</button>
    </div>
    <div id="activeFilters" class="flex flex-wrap gap-1.5" style="display:none"></div>
    <div class="flex flex-wrap gap-2 items-center text-sm">
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" id="inStockOnly" class="rounded"> In stock only
      </label>
      <select id="stateFilter" aria-label="Filter by state" class="border border-gray-300 rounded px-2 py-1 text-sm">
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
      {category_filter_html}
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" id="changesOnly" class="rounded"> Changes only
      </label>
      <select id="nurseryFilter" aria-label="Filter by nursery" class="border border-gray-300 rounded px-2 py-1 text-sm">
        <option value="">All nurseries</option>
      </select>
      <select id="sortBy" aria-label="Sort results" class="border border-gray-300 rounded px-2 py-1 text-sm">
        <option value="relevance">Sort: Relevance</option>
        <option value="price-asc">Price: Low to High</option>
        <option value="price-desc">Price: High to Low</option>
        <option value="name">Name: A-Z</option>
      </select>
      <span id="resultCount" class="text-gray-500 ml-auto"></span>
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
        <select id="subState" aria-label="State for stock alerts" class="px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
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

{render_footer(max_width=CONTENT_MAX_WIDTH, extra_text='<span id="stats" class="block mb-1"></span>')}

<script src="{data_url}?v={cache_v}" defer></script>
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

    return html, data_js


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build treestock.com.au dashboard")
    parser.add_argument("data_dir", help="Path to nursery-stock/ directory")
    parser.add_argument("output_dir", nargs="?", default="dashboard-output", help="Where to write index.html (default: ./dashboard-output/)")
    parser.add_argument("--featured", metavar="NURSERY_KEY", help="Nursery key to feature (e.g. primal-fruits). Overrides FEATURED_NURSERIES constant. Use for demo/preview builds only.")
    parser.add_argument("--output-name", default="index.html", metavar="FILENAME", help="Output filename (default: index.html). Use e.g. featured-demo.html for demo builds.")
    parser.add_argument("--needs-review-out", metavar="PATH", help="Also run the categorize ladder (DEC-200) and write the per-nursery needs-review JSON to PATH. Off by default so golden builds never see it.")
    parser.add_argument("--category", metavar="CATEGORY", choices=sorted(LANDING_PAGES), help="Build a category landing page (e.g. bush_tucker) instead of the homepage: same components, scoped to that category's stock (DAL-198). Writes index.html + data.js into output_dir; reference the scoped data.js via the page's data_url.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    # Resolve rarity_scores.json relative to data_dir so test fixtures are used
    # in golden tests (fixture/rarity_scores.json) rather than the live server file.
    # On the live server data_dir is /opt/dale/data/nursery-stock/ so parent is unchanged.
    global RARITY_SCORES_FILE
    RARITY_SCORES_FILE = data_dir.parent / "rarity_scores.json"

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

    if args.needs_review_out:
        write_needs_review(products, Path(args.needs_review_out))

    landing = None
    if args.category:
        products, nurseries, ranked_species = filter_to_category(
            products, nurseries, ranked_species, args.category)
        landing = LANDING_PAGES[args.category]
        print(f"  Category landing '{args.category}': {len(products)} products, "
              f"{len(ranked_species)} species, {len(nurseries)} nurseries")

    output_dir.mkdir(parents=True, exist_ok=True)
    html, data_js = build_html(products, nurseries, ranked_species, highlights_html, landing=landing)

    # Atomic write: write to temp file then rename to avoid serving partial HTML
    out_file = output_dir / args.output_name
    tmp_file = output_dir / (args.output_name + ".tmp")
    tmp_file.write_text(html)
    tmp_file.rename(out_file)
    print(f"Dashboard written to {out_file} ({len(html):,} bytes)")

    # The dataset now lives in an external data.js (window.__DATA), loaded defer
    # before dashboard.js. This is where the bulk of the bytes are (was inline HTML).
    data_file = output_dir / "data.js"
    data_tmp = output_dir / "data.js.tmp"
    data_tmp.write_text(data_js)
    data_tmp.rename(data_file)
    print(f"Data written to {data_file} ({len(data_js):,} bytes)")

    # Post-build verification. data.js is now the big file; the HTML is small by
    # design, so guard each against its own floor (a corrupt build trips one of
    # them). These floors are calibrated for the full homepage; a category
    # landing page is legitimately a small fraction of the catalogue, so the
    # data.js / product-count floors do not apply to it.
    html_size = out_file.stat().st_size
    data_size = data_file.stat().st_size
    if html_size < 8_000:
        print(f"WARNING: index.html is suspiciously small ({html_size:,} bytes). Expected >8KB.", file=sys.stderr)
        sys.exit(2)
    if not args.category:
        if data_size < 500_000:
            print(f"WARNING: data.js is suspiciously small ({data_size:,} bytes). Expected >500KB.", file=sys.stderr)
            sys.exit(2)
        if len(products) < 1000:
            print(f"WARNING: Only {len(products)} products loaded. Expected >1000. Check scrapers.", file=sys.stderr)
            sys.exit(2)
    print(f"Verification passed: index.html {html_size:,} bytes, data.js {data_size:,} bytes, {len(products)} products")


if __name__ == "__main__":
    main()
