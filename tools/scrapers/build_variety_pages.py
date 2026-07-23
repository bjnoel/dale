#!/usr/bin/env python3
"""
Build cultivar/variety-level pages for treestock.com.au.

Each page answers: "Where can I buy [Cultivar Name] in Australia?"
Targets high-intent searches like "buy Hass avocado tree australia",
"Grimal jaboticaba for sale", "R2E2 mango tree price australia".

Generates /variety/[slug].html for all cultivar-level products
(products with "Species - Variety" or "Species – Variety" format).

Also generates /variety/index.html listing all cultivar pages.

Usage:
    python3 build_variety_pages.py <data_dir> <output_dir>
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

from shipping import SHIPPING_MAP, NURSERY_NAMES, restriction_warning, delivery_label
from stocklib.snapshots import iter_nursery_snapshots
from stocklib.structured_data import product_offer_jsonld
from stocklib.templates import render as render_template
from stocklib.variety_descriptions import has_description, render_blurb
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer, render_treesmith_promo, SITE_URL

NURSERY_URLS = {
    "daleys": "https://www.daleysfruit.com.au",
    "ross-creek": "https://www.rosscreektropicals.com.au",
    "ladybird": "https://ladybird.com.au",
    "fruitopia": "https://fruitopia.com.au",
    "primal-fruits": "https://primalfruits.com.au",
    "guildford": "https://guildfordgardencentre.com.au",
    "fruit-salad-trees": "https://www.fruitsaladtrees.com.au",
    "diggers": "https://www.diggers.com.au",
    "all-season-plants-wa": "https://allseasonplantswa.com.au",
    "ausnurseries": "https://www.ausnurseries.com",
    "fruit-tree-cottage": "https://www.fruittreecottage.com.au",
}

from stocklib.classify import NON_PLANT_KEYWORDS, is_real_product


from cultivar_parsing import (  # noqa: E402
    slugify, parse_cultivar, extract_type_label, canonical_cultivar,
    group_by_cultivar, GRANDFATHERED_VARIETY_SLUGS,
)
from stocklib.taxonomy import load_species
from stocklib.category_ui import category_badges_html, is_bush_tucker, CATEGORY_FILTER_CSS
from stocklib.utm import outbound

# Canonical species name -> the /species/ page slug from the taxonomy record
# (slugify("Davidson's Plum") gives davidson-s-plum; the record says
# davidsons-plum, which is the file build_species_pages actually writes).
_SPECIES_PAGE_SLUG = {r["common_name"]: r["slug"] for r in load_species()}

# Canonical species name -> full taxonomy record (for the category badge/filter).
_SPECIES_BY_NAME = {r["common_name"]: r for r in load_species()}


def species_page_slug(name: str) -> str:
    return _SPECIES_PAGE_SLUG.get(name) or slugify(name)


def visible_type_label(type_label: str, variety: str) -> str:
    """Drop pill parts whose text already appears in the variety name, so the
    banana 'Dwarf Cavendish' page shows no redundant Dwarf pill (DEC-177)."""
    if not type_label:
        return ""
    vlow = variety.lower()
    parts = [
        p for p in (s.strip() for s in type_label.split(","))
        if p and p.lower() not in vlow
    ]
    return ", ".join(parts)


def load_all_products(data_dir: Path) -> list[dict]:
    """Load all products from today's or latest snapshot."""
    products = []
    for nursery_key, data in iter_nursery_snapshots(data_dir):
        nursery_name = NURSERY_NAMES.get(nursery_key, nursery_key)
        restrict = "" if delivery_label(nursery_key) else restriction_warning(nursery_key)

        raw_products = data.get("products", [])
        for p in raw_products:
            title = p.get("title", "").strip()
            title_lower = title.lower()
            # Skip non-plant items and seed packets
            if not is_real_product(title):
                continue
            products.append({
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "title": title,
                "type_label": extract_type_label(title),
                "url": p.get("url", ""),
                "price": p.get("min_price") or 0,
                "available": p.get("any_available", False),
                "restrict": restrict,
                "ships_states": SHIPPING_MAP.get(nursery_key, []),
            })
    return products


def build_variety_page(slug: str, data: dict, valid_species_slugs: set[str]) -> str:
    """Build HTML for a single cultivar page."""
    title = data["title"]
    species = data["species"]
    variety = data["variety"]
    products = data["products"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Sort: in-stock first, then by price
    in_stock = [p for p in products if p["available"] and p["price"]]
    out_stock = [p for p in products if not p["available"] or not p["price"]]
    in_stock.sort(key=lambda p: p["price"])

    cheapest = in_stock[0] if in_stock else None

    # Build product rows
    # Row view-data. The template autoescapes the scraped nursery name, the
    # product URL and the ships-to states; restrict_div is a prebuilt fragment
    # over the curated restriction warning (|safe).
    product_view = []
    for p in in_stock + out_stock:
        local_lbl = delivery_label(p["nursery_key"])
        states = local_lbl if local_lbl else (", ".join(p["ships_states"]) if p["ships_states"] else "—")
        nursery_url = NURSERY_URLS.get(p["nursery_key"], "#")
        restrict_div = (
            f'<div class="text-xs"><span class="text-xs text-red-600">{p["restrict"]}</span></div>'
            if p["restrict"] else ""
        )
        product_view.append({
            "product_link": outbound(p["url"] or (nursery_url if nursery_url != "#" else ""), "variety-page") or "#",
            "nursery_name": p["nursery_name"],
            "type_label": visible_type_label(p["type_label"], variety),
            "restrict_div": restrict_div,
            "price_str": f"${p['price']:.2f}" if p["price"] else "—",
            "available": p["available"],
            "states": states,
        })

    # Summary callouts
    summary_parts = []
    if cheapest:
        summary_parts.append(
            f'<span class="font-medium">Cheapest:</span> '
            f'{cheapest["nursery_name"]} at ${cheapest["price"]:.2f}'
        )

    summary_html = " &nbsp;·&nbsp; ".join(summary_parts) if summary_parts else ""
    summary_callout = (
        "<div class='bg-green-50 border border-green-200 rounded-lg px-4 py-3 mb-6 text-sm text-green-900'>"
        + summary_html + "</div>"
    ) if summary_html else ""

    in_stock_count = len(in_stock)
    nursery_count = len(set(p["nursery_key"] for p in products))
    species_slug = species_page_slug(species)
    # Optional verified "what's unique about this variety" blurb, rendered under the
    # meta line and above the price table. Empty string for un-enriched varieties.
    blurb_html = render_blurb(slug, species_slug) if has_description(slug, species_slug) else ""
    variety_title = f"{species} - {variety}"
    # Escape single quotes for safe embedding in JS string literals
    variety_title_js = variety_title.replace("'", "\\'")
    slug_js = slug.replace("'", "\\'")
    species_slug_js = species_slug.replace("'", "\\'")

    meta_desc = (
        f"Find {title} trees for sale in Australia. "
        f"Compare prices across {nursery_count} nurseries. "
        f"{in_stock_count} nurseries currently in stock. Updated daily."
    )

    head = render_head(
        title=f"Buy {title} Trees in Australia, Prices & Availability | treestock.com.au",
        description=meta_desc,
        canonical_url=f"https://treestock.com.au/variety/{slug}.html",
        og_title=f"Buy {title} Trees in Australia",
        og_description=meta_desc,
        og_type="product",
        jsonld=product_offer_jsonld(
            name=title,
            url=f"https://treestock.com.au/variety/{slug}.html",
            products=products,
            description=meta_desc,
        ),
    )
    header = render_header(active_path="/variety/")
    species_href = f"/species/{species_slug}.html" if species_slug in valid_species_slugs else ""
    breadcrumb = render_breadcrumb([
        ("Home", "/"), ("Varieties", "/variety/"),
        (species, species_href), (variety, ""),
    ])
    footer = render_footer()

    other_varieties_html = (f'''<p class="mt-2">
      Looking for other {species} varieties?
      <a href="/species/{species_slug}.html" class="underline text-green-700">See all {species} options &rarr;</a>
    </p>''' if species_slug in valid_species_slugs else "")

    return render_template(
        "variety_page.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        treesmith_promo=render_treesmith_promo("variety"),
        title=title, today=today, nursery_count=nursery_count, in_stock_count=in_stock_count,
        blurb_html=blurb_html,
        summary_callout=summary_callout, product_view=product_view,
        watch_heading=(f"Notify me next time {variety} {species} comes back" if in_stock
                       else f"Get notified when {variety} {species} comes back in stock"),
        watch_body=(f"{variety} {species} is currently in stock. You can still set an alert for next time."
                    if in_stock else
                    f"{variety} {species} is currently out of stock. Enter your email to get an alert the moment it's available again."),
        other_varieties_html=other_varieties_html,
        slug_js=slug_js, species_slug_js=species_slug_js, variety_title_js=variety_title_js,
    )


def build_variety_index(entries: list[dict], valid_species_slugs: set[str]) -> str:
    """Build /variety/index.html listing all cultivar pages.

    valid_species_slugs is the set of species slugs that have a real
    /species/<slug>.html page; anything else renders as plain text rather
    than a broken link (e.g. "Sapodilla Grafted" — parse_cultivar can't
    distinguish a propagation-method prefix from the canonical species name).
    """
    # Group by species for easier browsing
    by_species = defaultdict(list)
    for e in entries:
        by_species[e["species"]].append(e)

    # Per-species section view-data. The template autoescapes the scraped
    # variety and species names in both the visible links and the data-var /
    # data-sp filter attributes (the manual &quot; escaping is gone -- autoescape
    # now covers ", & and < in those attributes).
    species_view = []
    for sp in sorted(by_species.keys()):
        varieties = sorted(by_species[sp], key=lambda x: x["variety"])
        sp_slug = species_page_slug(sp)
        row_view = [
            {
                "var_lower": v["variety"].lower(),
                "slug": v["slug"],
                "variety": v["variety"],
                "n_count": v["nursery_count"],
                "in_s": v["in_stock"],
                "price": f'${v["min_price"]:.2f}' if v["min_price"] else "—",
                "states": " ".join(v.get("states", [])),
            }
            for v in varieties
        ]
        sp_heading = (
            f'<a href="/species/{sp_slug}.html" class="hover:underline">{sp}</a>'
            if sp_slug in valid_species_slugs else sp
        )
        record = _SPECIES_BY_NAME.get(sp, {})
        species_view.append({
            "sp_heading": sp_heading,
            "sp_slug": sp_slug,
            "sp_lower": sp.lower(),
            "variety_count": len(varieties),
            "in_stock_count": sum(v["in_stock"] for v in varieties),
            "rows": row_view,
            "category": record.get("category", "fruit"),
            "is_bush_tucker": is_bush_tucker(record),
            "badges_html": category_badges_html(record),
        })

    total_varieties = len(entries)
    total_in_stock = sum(e["in_stock"] for e in entries)

    head = render_head(
        title="Fruit Tree and Bush Tucker Varieties for Sale in Australia | treestock.com.au",
        description=f"Browse {total_varieties} named fruit tree and Australian bush tucker varieties from nurseries. Find Hass avocado, R2E2 mango, Grimal jaboticaba, Brown Turkey fig and more. Compare prices and check availability. Updated daily.",
        canonical_url=f"{SITE_URL}/variety/",
        extra_style=CATEGORY_FILTER_CSS,
    )
    header = render_header(active_path="/variety/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Varieties", "")])
    footer = render_footer()

    return render_template(
        "variety_index.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        total_varieties=total_varieties, total_in_stock=total_in_stock,
        species_count=len(by_species), species_view=species_view,
    )


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <data_dir> <output_dir>", file=sys.stderr)
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    variety_dir = output_dir / "variety"
    variety_dir.mkdir(parents=True, exist_ok=True)

    # Species pages are built before variety pages by run-all-scrapers.sh.
    # Use the resulting filenames as the source of truth for which species
    # slugs are linkable (parse_cultivar's species portion can include
    # propagation prefixes like "Sapodilla Grafted" that have no species page).
    species_dir = output_dir / "species"
    valid_species_slugs = (
        {p.stem for p in species_dir.glob("*.html") if p.stem != "index"}
        if species_dir.exists() else set()
    )
    print(f"Loaded {len(valid_species_slugs)} valid species slugs from {species_dir}")

    products = load_all_products(data_dir)
    print(f"Loaded {len(products)} products")

    groups = group_by_cultivar(products)
    print(f"Found {len(groups)} distinct cultivar names")

    index_entries = []
    pages_written = 0
    written_slugs = set()

    for slug, data in groups.items():
        prods = data["products"]
        in_stock = [p for p in prods if p["available"] and p["price"]]
        all_nurseries = set(p["nursery_key"] for p in prods)
        min_price = min((p["price"] for p in in_stock), default=None)

        html = build_variety_page(slug, data, valid_species_slugs)
        out_path = variety_dir / f"{slug}.html"
        with open(out_path, "w") as f:
            f.write(html)
        written_slugs.add(slug)
        pages_written += 1

        # Grandfathered non-fruit pages exist only to keep their subscribers'
        # restock alerts alive (DEC-195); they stay out of the browsable index.
        if slug in GRANDFATHERED_VARIETY_SLUGS:
            continue

        index_entries.append({
            "slug": slug,
            "title": data["title"],
            "species": data["species"],
            "variety": data["variety"],
            "nursery_count": len(all_nurseries),
            "in_stock": len(in_stock),
            "min_price": min_price,
            "states": sorted({st for p in prods for st in p["ships_states"]}),
        })

    # Delete orphan variety pages from previous runs (e.g. when parse_cultivar
    # tightens up and a slug stops being generated). Don't touch index.html.
    current_slugs = written_slugs
    orphans = [
        p for p in variety_dir.glob("*.html")
        if p.stem != "index" and p.stem not in current_slugs
    ]
    for p in orphans:
        p.unlink()
    if orphans:
        print(f"Removed {len(orphans)} orphan variety page(s)")

    # Write index
    index_html = build_variety_index(index_entries, valid_species_slugs)
    with open(variety_dir / "index.html", "w") as f:
        f.write(index_html)

    print(f"Written {pages_written} variety pages + index to {variety_dir}/")

    # Print summary stats
    multi = sum(1 for e in index_entries if e["nursery_count"] > 1)
    in_stock_count = sum(1 for e in index_entries if e["in_stock"] > 0)
    print(f"  Multi-nursery: {multi}, In-stock varieties: {in_stock_count}")


if __name__ == "__main__":
    main()
