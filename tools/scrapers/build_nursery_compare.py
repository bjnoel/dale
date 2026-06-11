#!/usr/bin/env python3
"""
Build nursery comparison table page for treestock.com.au.

Generates /compare/nurseries.html — a side-by-side comparison of all tracked nurseries.
Targets queries: "compare fruit tree nurseries Australia", "best online fruit tree nursery",
                 "fruit tree nurseries that ship to WA", "cheapest fruit tree nursery Australia"

Usage:
    python3 build_nursery_compare.py /path/to/data/nursery-stock /path/to/dashboard/
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from shipping import SHIPPING_MAP, NURSERY_NAMES, restriction_warning, LOCAL_DELIVERY, delivery_label
from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer

from stocklib.taxonomy import enabled_species


def load_species_lookup() -> dict:
    species = enabled_species()
    lookup = {}
    for s in species:
        common = s["common_name"].lower()
        entry = {"cn": s["common_name"], "sl": s["slug"]}
        lookup[common] = entry
        for alias in s.get("aliases", []):
            lookup[alias.lower()] = entry
    return lookup


def count_species(products: list, species_lookup: dict) -> int:
    """Count distinct species in a nursery's product list."""
    found = set()
    for p in products:
        title = p.get("title", "").lower()
        for term, entry in species_lookup.items():
            if term and term in title:
                found.add(entry["cn"])
                break
    return len(found)


def load_nursery_data(data_dir: Path) -> dict:
    nurseries = {}
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        latest = nursery_dir / "latest.json"
        if not latest.exists():
            continue
        with open(latest) as f:
            data = json.load(f)
        nurseries[nursery_dir.name] = data
    return nurseries


def build_compare_page(nurseries_data: dict, species_lookup: dict, today: str) -> str:
    """Build the nursery comparison table page."""

    # Compile row data for each nursery
    rows = []
    for key, data in nurseries_data.items():
        name = NURSERY_NAMES.get(key, data.get("nursery_name", key))
        ships = sorted(SHIPPING_MAP.get(key, []))
        wa = "WA" in ships
        in_stock = data.get("in_stock_count", 0)
        total = data.get("product_count", len(data.get("products", [])))
        products = data.get("products", [])
        species_count = count_species(products, species_lookup)
        restrict = restriction_warning(key)
        location = data.get("location", "Australia")
        pct = round(100 * in_stock / total) if total else 0

        rows.append({
            "key": key,
            "name": name,
            "in_stock": in_stock,
            "total": total,
            "pct": pct,
            "species": species_count,
            "wa": wa,
            "ships": ships,
            "restrict": restrict,
            "location": location,
        })

    # Sort by in-stock count descending
    rows.sort(key=lambda r: (-r["in_stock"], -r["total"]))

    total_nurseries = len(rows)

    # Row view-data. The template autoescapes the nursery name and location;
    # the wa/restriction/ship cells are built from our own curated state data.
    row_view = []
    for r in rows:
        local_lbl = delivery_label(r["key"])
        ship_str = local_lbl if local_lbl else (", ".join(r["ships"]) if r["ships"] else "Unknown")
        row_view.append({
            "key": r["key"],
            "name": r["name"],
            "location": r["location"],
            "in_stock": r["in_stock"],
            "total": r["total"],
            "pct": r["pct"],
            "species": r["species"],
            "wa": r["wa"],
            "local_lbl": local_lbl,
            "ship_str": ship_str,
            "restrict": r["restrict"],
        })

    # Summary stats
    wa_count = sum(1 for r in rows if r["wa"])
    total_in_stock = sum(r["in_stock"] for r in rows)
    total_products = sum(r["total"] for r in rows)

    extra_style = """\
  table { border-collapse: collapse; width: 100%; }
  .filter-btn { cursor: pointer; }
  .filter-btn.active { background-color: #065f46; color: white; }
  tr.hidden-row { display: none; }"""

    head = render_head(
        title="Compare Australian Fruit Tree Nurseries | treestock.com.au",
        description=f"Side-by-side comparison of {total_nurseries} Australian fruit tree nurseries. See stock levels, species range, prices, and shipping to WA and all states.",
        canonical_url="https://treestock.com.au/compare/nurseries.html",
        og_title="Compare Australian Fruit Tree Nurseries",
        og_description=f"Compare {total_nurseries} nurseries: stock levels, species range, and shipping to your state. Updated daily.",
        og_type="website",
        extra_style=extra_style,
    )
    header_html = render_header(active_path="/compare/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Compare", "/compare/"), ("Nurseries", "")])
    footer = render_footer()

    return render_template(
        "nursery_compare.html.j2",
        head=head, header_html=header_html, breadcrumb=breadcrumb, footer=footer,
        total_nurseries=total_nurseries,
        total_in_stock_fmt=f"{total_in_stock:,}",
        total_products_fmt=f"{total_products:,}",
        wa_count=wa_count, today=today, row_view=row_view,
    )


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <data_dir> <output_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    compare_dir = output_dir / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    species_lookup = load_species_lookup()
    nurseries_data = load_nursery_data(data_dir)

    if not nurseries_data:
        print("No nursery data found.")
        sys.exit(1)

    page = build_compare_page(nurseries_data, species_lookup, today)
    out = compare_dir / "nurseries.html"
    out.write_text(page)
    print(f"Built nursery comparison page: {out}")
    print(f"  {len(nurseries_data)} nurseries compared")


if __name__ == "__main__":
    main()
