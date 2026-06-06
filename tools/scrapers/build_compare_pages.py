#!/usr/bin/env python3
"""
Build price comparison pages for top fruit species.

Each page answers: "Which nursery has the cheapest [species] tree in Australia?"
Target keywords: "[species] tree price australia", "cheapest [species] tree",
                 "compare [species] tree prices", "where to buy [species] tree"

Generates /compare/[species]-prices.html for top species with multi-nursery coverage.

Usage:
    python3 build_compare_pages.py /path/to/nursery-stock /path/to/output/
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

from shipping import SHIPPING_MAP, NURSERY_NAMES, LOCAL_DELIVERY, delivery_label
from stocklib.snapshots import iter_nursery_snapshots, variant_min_price
from stocklib.structured_data import product_offer_jsonld
from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer, SITE_URL

SPECIES_FILE = Path(__file__).parent / "fruit_species.json"

from stocklib.classify import NON_PLANT_KEYWORDS

# Minimum nurseries for a compare page to be useful
MIN_NURSERIES = 3


def load_species() -> list[dict]:
    with open(SPECIES_FILE) as f:
        return json.load(f)


def build_species_lookup(species_list: list[dict]) -> dict:
    lookup = {}
    for s in species_list:
        lookup[s["common_name"].lower()] = s
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = s
    return lookup


def match_title(title: str, lookup: dict) -> dict | None:
    title_lower = title.lower()
    # Strip common size/form prefixes
    for prefix in ["dwarf ", "semi-dwarf ", "miniature ", "standard ", "grafted ", "advanced "]:
        if title_lower.startswith(prefix):
            title_lower = title_lower[len(prefix):]
            break
    # Try from start first (most nurseries use "Species - Variety" format)
    words = re.split(r'[\s\-–—]+', title_lower)
    for n in range(min(len(words), 5), 0, -1):
        candidate = " ".join(words[:n])
        if candidate in lookup:
            return lookup[candidate]
    # Fallback: match any N-word sequence in title (handles "Variety Species (size)" format)
    words = re.split(r'[\s\-–—(]+', title_lower)
    words = [w.rstrip(").,") for w in words if w]
    for start in range(1, len(words)):
        for n in range(min(len(words) - start, 3), 0, -1):
            candidate = " ".join(words[start:start + n])
            if candidate in lookup:
                return lookup[candidate]
    return None


def load_all_products(data_dir: Path) -> list[dict]:
    """Load all products from today's snapshot (or latest.json fallback)."""
    products = []
    for nursery_key, data in iter_nursery_snapshots(data_dir):
        nursery_name = data.get("nursery_name") or NURSERY_NAMES.get(nursery_key, nursery_key)
        for p in data.get("products", []):
            title = p.get("title", "")
            title_lower = title.lower()
            if any(kw in title_lower for kw in NON_PLANT_KEYWORDS):
                continue
            if re.search(r'\bseeds?\b', title_lower) and 'seedling' not in title_lower and 'seedless' not in title_lower:
                continue
            min_price = p.get("min_price")
            if min_price is None:
                min_price = variant_min_price(p, prefer_available=True)
            available = p.get("any_available", p.get("available", False))
            url = p.get("url", "")
            products.append({
                "title": title,
                "url": url,
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "price": round(float(min_price), 2) if min_price else None,
                "available": bool(available),
            })
    return products


def group_by_species(products: list[dict], lookup: dict) -> dict:
    by_species = defaultdict(list)
    for p in products:
        sp = match_title(p["title"], lookup)
        if sp:
            by_species[sp["slug"]].append((sp, p))
    # Return dict of slug -> (species_meta, [products])
    result = {}
    for slug, items in by_species.items():
        sp_meta = items[0][0]
        prods = [i[1] for i in items]
        result[slug] = {"species": sp_meta, "products": prods}
    return result


def build_compare_page(species: dict, products: list[dict]) -> str:
    name = species["common_name"]
    latin = species["latin_name"]
    slug = species["slug"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    in_stock = [p for p in products if p["available"] and p["price"]]
    all_priced = [p for p in products if p["price"]]

    # Per-nursery best price
    nursery_best = {}
    for p in products:
        nk = p["nursery_key"]
        if nk not in nursery_best:
            nursery_best[nk] = {
                "name": p["nursery_name"],
                "best_price": None,
                "best_title": None,
                "best_url": None,
                "in_stock_count": 0,
                "total": 0,
                "ships_to": SHIPPING_MAP.get(nk, []),
            }
        nursery_best[nk]["total"] += 1
        if p["available"]:
            nursery_best[nk]["in_stock_count"] += 1
        if p["available"] and p["price"]:
            if nursery_best[nk]["best_price"] is None or p["price"] < nursery_best[nk]["best_price"]:
                nursery_best[nk]["best_price"] = p["price"]
                nursery_best[nk]["best_title"] = p["title"]
                nursery_best[nk]["best_url"] = p["url"]

    # Sort nurseries by best price (in-stock first, then by price)
    sorted_nurseries = sorted(
        nursery_best.items(),
        key=lambda x: (
            x[1]["best_price"] is None or x[1]["in_stock_count"] == 0,
            x[1]["best_price"] or 9999
        )
    )

    # Price stats
    in_stock_prices = [p["price"] for p in in_stock]
    min_price = min(in_stock_prices) if in_stock_prices else None
    max_price = max(in_stock_prices) if in_stock_prices else None

    price_range_str = ""
    if min_price:
        if min_price == max_price:
            price_range_str = f"${min_price:.2f}"
        else:
            price_range_str = f"${min_price:.2f} – ${max_price:.2f}"

    nursery_count = len([nk for nk, n in nursery_best.items() if n["in_stock_count"] > 0])
    total_nurseries = len(nursery_best)

    # Per-nursery comparison rows as view-data. The template autoescapes the
    # scraped title and the utm URL (which carries the & that f-strings left raw).
    nursery_view = []
    for nk, n in sorted_nurseries:
        in_stock_row = bool(n["best_price"] and n["in_stock_count"] > 0)
        if in_stock_row and n["best_url"]:
            utm_url = n["best_url"] + ("&" if "?" in n["best_url"] else "?") + "utm_source=treestock&utm_medium=compare"
        else:
            utm_url = ""
        local_lbl = delivery_label(nk)
        ships = local_lbl if local_lbl else (", ".join(n["ships_to"]) if n["ships_to"] else "Local only")
        nursery_view.append({
            "name": n["name"],
            "in_stock_row": in_stock_row,
            "best_price": n["best_price"],
            "best_title": n["best_title"],
            "utm_url": utm_url,
            "in_stock_count": n["in_stock_count"],
            "ships": ships,
        })

    # Full product listing (in-stock first, then price-sorted) as view-data.
    sorted_products = sorted(products, key=lambda x: (not x["available"], x["price"] or 9999, x["title"]))
    product_view = []
    for p in sorted_products:
        if p["url"]:
            utm_url = p["url"] + ("&" if "?" in p["url"] else "?") + "utm_source=treestock&utm_medium=compare"
        else:
            utm_url = ""
        product_view.append({
            "url": p["url"],
            "utm_url": utm_url,
            "title": p["title"],
            "nursery_name": p["nursery_name"],
            "price": p["price"],
            "available": p["available"],
        })

    cheapest = None
    if sorted_nurseries and sorted_nurseries[0][1]["best_price"] and sorted_nurseries[0][1]["in_stock_count"] > 0:
        cheapest_n = sorted_nurseries[0][1]
        cheapest = {"name": cheapest_n["name"], "best_price": cheapest_n["best_price"]}

    seo_nurseries = [n["name"] for _, n in sorted_nurseries]

    head = render_head(
        title=f"{name} Tree Price Comparison Australia — treestock.com.au",
        description=f"Compare {name} ({latin}) tree prices across {total_nurseries} Australian nurseries. {len(in_stock)} varieties in stock. {'Prices from ' + price_range_str + ' AUD.' if price_range_str else ''} Updated daily.",
        canonical_url=f"{SITE_URL}/compare/{slug}-prices.html",
        og_title=f"{name} Tree Prices — Compare {total_nurseries} Australian Nurseries",
        og_description=f"{'From ' + price_range_str if price_range_str else str(len(in_stock)) + ' varieties in stock'} across {nursery_count} nurseries. Compare prices and availability at treestock.com.au",
        jsonld=product_offer_jsonld(
            name=f"{name} Tree",
            url=f"{SITE_URL}/compare/{slug}-prices.html",
            products=products,
            description=f"Compare {name} ({latin}) tree prices across {total_nurseries} Australian nurseries.",
        ),
    )
    header = render_header(active_path="/compare/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Compare Prices", "/compare/"), (name, "")])
    footer = render_footer()

    return render_template(
        "compare_page.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        name=name, latin=latin, slug=slug, now=now,
        total_nurseries=total_nurseries, in_stock_count=len(in_stock),
        price_range_str=price_range_str, cheapest=cheapest,
        nursery_view=nursery_view, product_view=product_view,
        seo_nurseries=seo_nurseries,
    )


def build_compare_index(entries: list[dict]) -> str:
    """Build /compare/index.html listing all compare pages."""
    entries_view = []
    for e in sorted(entries, key=lambda x: -x["nursery_count"]):
        sp = e["species"]
        entries_view.append({
            "slug": sp["slug"],
            "common_name": sp["common_name"],
            "latin_name": sp["latin_name"],
            "nursery_count": e["nursery_count"],
            "in_stock": e["in_stock"],
            "min_price": e["min_price"],
        })

    head = render_head(
        title="Fruit Tree Price Comparisons — Australian Nurseries — treestock.com.au",
        description=f"Compare fruit tree prices across Australian online nurseries. Find the cheapest mango, fig, avocado, lemon and more. Updated daily from {len(entries)} species.",
        canonical_url=f"{SITE_URL}/compare/",
    )
    header = render_header(active_path="/compare/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Compare Prices", "")])
    footer = render_footer()

    return render_template(
        "compare_index.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        entry_count=len(entries), entries_view=entries_view,
    )


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <data_dir> <output_dir>", file=sys.stderr)
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    compare_dir = output_dir / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)

    species_list = load_species()
    lookup = build_species_lookup(species_list)
    products = load_all_products(data_dir)

    print(f"Loaded {len(products)} products across all nurseries")

    by_species = group_by_species(products, lookup)

    index_entries = []
    pages_written = 0

    for slug, data in by_species.items():
        sp = data["species"]
        prods = data["products"]

        # Count how many unique nurseries have in-stock items
        in_stock_nurseries = set(p["nursery_key"] for p in prods if p["available"])
        all_nurseries = set(p["nursery_key"] for p in prods)

        if len(all_nurseries) < MIN_NURSERIES:
            continue

        in_stock_prods = [p for p in prods if p["available"] and p["price"]]
        min_price = min((p["price"] for p in in_stock_prods), default=None)

        html = build_compare_page(sp, prods)
        out_path = compare_dir / f"{slug}-prices.html"
        with open(out_path, "w") as f:
            f.write(html)

        index_entries.append({
            "species": sp,
            "nursery_count": len(all_nurseries),
            "in_stock": len(in_stock_prods),
            "min_price": min_price,
        })
        pages_written += 1

    # Write index
    index_html = build_compare_index(index_entries)
    with open(compare_dir / "index.html", "w") as f:
        f.write(index_html)

    print(f"Written {pages_written} compare pages + index to {compare_dir}/")


if __name__ == "__main__":
    main()
