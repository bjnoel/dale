#!/usr/bin/env python3
"""
Build state-based location pages for beestock.com.au.

Generates /buy-beekeeping-supplies-[state].html for WA, QLD, NSW, VIC.
Shows all retailers (all ship nationwide), with in-stock product lists,
local retailers highlighted, varroa status, and subscribe CTAs.

Usage:
    python3 build_bee_location_pages.py /path/to/bee-stock /path/to/bee-dashboard/
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from bee_retailers import RETAILERS, RETAILER_NAMES, SHIPPING_MAP
from beestock_layout import render_head, render_header, render_breadcrumb, render_footer, SITE_URL

# States to generate pages for
STATES = ["WA", "QLD", "NSW", "VIC"]

STATE_NAMES = {
    "WA": "Western Australia",
    "QLD": "Queensland",
    "NSW": "New South Wales",
    "VIC": "Victoria",
}

STATE_SLUGS = {
    "WA": "wa",
    "QLD": "qld",
    "NSW": "nsw",
    "VIC": "vic",
}

# State-specific intro text
STATE_INTROS = {
    "WA": (
        "Western Australia remains varroa-free, making it one of the best places in "
        "Australia to keep bees. All major Australian retailers ship beekeeping supplies "
        "to WA. Beewise, based in Perth, is the only WA-local option for in-store pickup."
    ),
    "QLD": (
        "Queensland has a strong beekeeping tradition, with a warm climate that keeps "
        "colonies active year-round. Varroa mite has entered QLD, so treatment products "
        "are now essential. Beekeeping Supplies Australia is QLD-based for faster delivery."
    ),
    "NSW": (
        "New South Wales was ground zero for the 2022 varroa mite detection. Varroa is "
        "now established and beekeepers are managing rather than eradicating. Demand for "
        "treatment products has surged. Flow Hive, in Byron Bay, ships nationally from NSW."
    ),
    "VIC": (
        "Victoria has a diverse beekeeping landscape, from coastal to alpine regions. "
        "Varroa has spread to parts of VIC, and treatment protocols are becoming standard "
        "practice. Ecrotek and Bec's BeeHive are both VIC-based for faster local delivery."
    ),
}

# State-specific info box (varroa status)
STATE_INFO_BOXES = {
    "WA": {
        "style": "green",
        "title": "WA is varroa-free",
        "body": (
            "Western Australia has not had a varroa detection as of 2025. "
            "Strict biosecurity at the WA border has kept the state free. "
            "WA beekeepers still benefit from having varroa treatments on hand "
            "as a precaution, and the overall beekeeping conditions here are excellent."
        ),
    },
    "QLD": {
        "style": "amber",
        "title": "Varroa mite is present in QLD",
        "body": (
            "Varroa mite has entered Queensland. Beekeepers in QLD should ensure "
            "they have an approved treatment protocol in place. Oxalic acid, "
            "ApiVar, and ApiLifeVar are commonly used. Check with Queensland "
            "DAF for current management requirements."
        ),
    },
    "NSW": {
        "style": "amber",
        "title": "Varroa mite is established in NSW",
        "body": (
            "Varroa mite was first detected in Newcastle in June 2022. "
            "Eradication was abandoned and NSW moved to a management phase. "
            "All NSW beekeepers must now actively manage varroa. "
            "NSW DPI maintains a Varroa Response page with current requirements."
        ),
    },
    "VIC": {
        "style": "amber",
        "title": "Varroa mite has spread to parts of VIC",
        "body": (
            "Varroa mite has spread from NSW into Victoria. Treatment is now "
            "part of standard hive management for Victorian beekeepers. "
            "Agriculture Victoria provides guidance on approved treatments "
            "and hive registration requirements."
        ),
    },
}

# Which retailers are local/based in each state
STATE_LOCAL_RETAILERS = {
    "WA": ["beewise"],
    "QLD": ["beekeeping-supplies-australia"],
    "NSW": ["flow-hive"],
    "VIC": ["ecrotek", "becs-beehive"],
}

# Per-retailer, per-state notes
STATE_RETAILER_NOTES = {
    "WA": {
        "beewise": "Perth-based, in-store pickup available",
    },
    "QLD": {
        "beekeeping-supplies-australia": "QLD-based",
        "flow-hive": "NSW-based, ships nationwide",
        "ecrotek": "VIC-based, ships nationwide",
    },
    "NSW": {
        "flow-hive": "Byron Bay, NSW-based",
        "ecrotek": "VIC-based, ships nationwide",
    },
    "VIC": {
        "ecrotek": "Melbourne, VIC-based",
        "becs-beehive": "Gembrook, VIC-based",
        "flow-hive": "NSW-based, ships nationwide",
    },
}

# Cross-state links
CROSS_LINKS = {
    "WA":  [("QLD", "QLD"), ("NSW", "NSW"), ("VIC", "VIC")],
    "QLD": [("WA", "WA"),  ("NSW", "NSW"), ("VIC", "VIC")],
    "NSW": [("WA", "WA"),  ("QLD", "QLD"), ("VIC", "VIC")],
    "VIC": [("WA", "WA"),  ("QLD", "QLD"), ("NSW", "NSW")],
}

# Popular categories to link to from state pages
FEATURED_CATEGORIES = [
    ("hiveware", "Hiveware"),
    ("frames-foundation", "Frames & Foundation"),
    ("protective-gear", "Protective Gear"),
    ("extractors-processing", "Extractors & Processing"),
    ("treatments", "Treatments & Health"),
]


def load_all_products(data_dir: Path) -> dict[str, list[dict]]:
    """Load all products grouped by retailer key."""
    by_retailer: dict[str, list[dict]] = {}
    for retailer_dir in sorted(data_dir.iterdir()):
        if not retailer_dir.is_dir():
            continue
        if retailer_dir.name not in RETAILERS:
            continue
        latest = retailer_dir / "latest.json"
        if not latest.exists():
            continue
        with open(latest) as f:
            data = json.load(f)
        products = data.get("products", [])
        # Filter gift cards
        products = [
            p for p in products
            if p.get("title", "").lower() not in
            ("gift card", "gift voucher", "gift certificate")
            and len(p.get("title", "")) >= 3
        ]
        by_retailer[retailer_dir.name] = products
    return by_retailer


def get_retailer_stats(by_retailer: dict[str, list[dict]], state: str) -> list[dict]:
    """Build per-retailer stats for retailers that ship to this state."""
    stats = []
    for key, ships_to in SHIPPING_MAP.items():
        if state not in ships_to:
            continue
        products = by_retailer.get(key, [])
        in_stock = sum(1 for p in products if p.get("any_available", p.get("available", False)))
        total = len(products)
        if total == 0:
            continue
        is_local = key in STATE_LOCAL_RETAILERS.get(state, [])
        note = STATE_RETAILER_NOTES.get(state, {}).get(key, "")
        if is_local and not note:
            note = f"{STATE_NAMES[state]}-based"
        stats.append({
            "key": key,
            "name": RETAILER_NAMES.get(key, key),
            "in_stock": in_stock,
            "total": total,
            "is_local": is_local,
            "note": note,
        })
    # Local retailers first, then by in-stock count descending
    stats.sort(key=lambda x: (-int(x["is_local"]), -x["in_stock"]))
    return stats


def get_top_products(by_retailer: dict[str, list[dict]], state: str, limit: int = 40) -> list[dict]:
    """Get top in-stock products from retailers shipping to this state, sorted by price desc."""
    products = []
    for key, ships_to in SHIPPING_MAP.items():
        if state not in ships_to:
            continue
        for p in by_retailer.get(key, []):
            if not p.get("any_available", p.get("available", False)):
                continue
            min_price = p.get("min_price")
            if min_price is None:
                continue
            products.append({
                "title": p.get("title", ""),
                "url": p.get("url", "#"),
                "price": float(min_price),
                "retailer_name": RETAILER_NAMES.get(key, key),
                "retailer_key": key,
            })
    # Sort by price descending (premium items first, more interesting)
    products.sort(key=lambda x: -x["price"])
    return products[:limit]


def build_page(
    state: str,
    by_retailer: dict[str, list[dict]],
    today_str: str,
) -> str:
    state_name = STATE_NAMES[state]
    slug = STATE_SLUGS[state]
    intro = STATE_INTROS[state]
    info_box_data = STATE_INFO_BOXES.get(state)

    retailer_stats = get_retailer_stats(by_retailer, state)
    total_in_stock = sum(r["in_stock"] for r in retailer_stats)
    retailer_count = len(retailer_stats)

    top_products = get_top_products(by_retailer, state)

    try:
        dt = datetime.strptime(today_str, "%Y-%m-%d")
        date_display = dt.strftime("%-d %B %Y")
    except Exception:
        date_display = today_str

    # Info box HTML
    info_box_html = ""
    if info_box_data:
        if info_box_data["style"] == "green":
            box_classes = "bg-green-50 border-green-200 text-green-900"
            title_classes = "text-green-800"
        else:
            box_classes = "bg-amber-50 border-amber-200 text-amber-900"
            title_classes = "text-amber-800"
        info_box_html = f"""  <div class="{box_classes} border rounded-lg p-4 mb-8">
    <p class="font-semibold text-sm {title_classes} mb-1">{info_box_data['title']}</p>
    <p class="text-sm">{info_box_data['body']}</p>
  </div>

"""

    # Retailer table rows
    retailer_rows = ""
    for r in retailer_stats:
        local_badge = (
            '<span class="text-xs px-1.5 py-0.5 bg-yellow-100 text-yellow-800 border border-yellow-200 rounded ml-1">Local</span>'
            if r["is_local"] else ""
        )
        note_html = (
            f'<span class="text-xs text-amber-600 ml-1">({r["note"]})</span>'
            if r["note"] else ""
        )
        retailer_rows += f"""        <tr class="border-b border-gray-100">
          <td class="py-2 pr-4 font-medium text-sm">
            <a href="/retailer/{r['key']}.html" class="text-yellow-700 hover:underline">{r['name']}</a>{local_badge}
          </td>
          <td class="py-2 pr-4 text-sm text-yellow-700 font-semibold">{r['in_stock']} in stock</td>
          <td class="py-2 text-sm text-gray-500">{r['total']} tracked{note_html}</td>
        </tr>\n"""

    # Product rows
    product_rows = ""
    for p in top_products:
        title = p["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        product_rows += f"""        <tr class="border-b border-gray-100">
          <td class="py-2 pr-4 text-sm">
            <a href="{p['url']}" class="hover:text-yellow-700" target="_blank" rel="noopener">{title}</a>
          </td>
          <td class="py-2 pr-4 text-sm font-semibold text-yellow-700">${p['price']:.2f}</td>
          <td class="py-2 text-sm text-gray-500">{p['retailer_name']}</td>
        </tr>\n"""

    shown_count = len(top_products)

    # Category links
    cat_links_html = " &middot; ".join(
        f'<a href="/category/{cat_slug}.html" class="text-yellow-700 hover:underline">{cat_name}</a>'
        for cat_slug, cat_name in FEATURED_CATEGORIES
    )

    # Cross-state links
    cross_html = " &middot; ".join(
        f'<a href="/buy-beekeeping-supplies-{s.lower()}.html" class="text-yellow-700 hover:underline">'
        f'Beekeeping supplies {label}</a>'
        for s, label in CROSS_LINKS[state]
    )

    head = render_head(
        title=f"Buy Beekeeping Supplies Online in {state_name} | beestock.com.au",
        description=(
            f"Find beekeeping supplies that ship to {state_name}. "
            f"{total_in_stock} products in stock across {retailer_count} retailers, "
            f"updated daily. Compare hives, frames, extractors, and protective gear."
        ),
        canonical_url=f"{SITE_URL}/buy-beekeeping-supplies-{slug}.html",
        og_title=f"Beekeeping Supplies in {state_name} | beestock.com.au",
        og_description=(
            f"Compare beekeeping supplies that ship to {state_name}. "
            f"{total_in_stock} products in stock, prices updated daily."
        ),
        extra_head='<meta name="robots" content="index, follow">',
    )
    header = render_header()
    breadcrumb = render_breadcrumb([
        ("Home", "/"),
        (f"Beekeeping supplies in {state_name}", ""),
    ])
    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-8">

  {breadcrumb}

  <h1 class="text-2xl font-bold mb-2">Buy Beekeeping Supplies Online in {state_name}</h1>
  <p class="text-gray-600 mb-1">Updated {date_display} &middot; {total_in_stock} products in stock across {retailer_count} retailers</p>
  <p class="text-gray-600 text-sm mb-6">{intro}</p>

{info_box_html}  <!-- Retailer summary -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold mb-3">Retailers shipping to {state_name}</h2>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase tracking-wide">
            <th class="pb-2 pr-4">Retailer</th>
            <th class="pb-2 pr-4">In stock</th>
            <th class="pb-2">Notes</th>
          </tr>
        </thead>
        <tbody>
{retailer_rows}        </tbody>
      </table>
    </div>
    <p class="text-xs text-gray-500 mt-2">
      Stock counts update daily. <a href="/" class="text-yellow-700 underline">Browse all products on the dashboard</a>
    </p>
  </section>

  <!-- In-stock products -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold mb-3">In stock now, ships to {state} (top {shown_count} by price)</h2>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase tracking-wide">
            <th class="pb-2 pr-4">Product</th>
            <th class="pb-2 pr-4">Price</th>
            <th class="pb-2">Retailer</th>
          </tr>
        </thead>
        <tbody>
{product_rows}        </tbody>
      </table>
    </div>
    <p class="text-xs text-gray-500 mt-2">
      Showing top {shown_count} in-stock products.
      <a href="/" class="text-yellow-700 underline">See all {total_in_stock} on the dashboard</a>
    </p>
  </section>

  <!-- Category links -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold mb-3">Shop by category</h2>
    <p class="text-sm text-gray-600">{cat_links_html}</p>
  </section>

  <!-- Subscribe CTA -->
  <section class="bg-yellow-50 border border-yellow-200 rounded-lg p-6 mb-8">
    <h2 class="text-lg font-semibold text-yellow-900 mb-2">Get price drop alerts for {state_name}</h2>
    <p class="text-sm text-yellow-800 mb-4">Free email alerts when beekeeping supply prices drop or go back in stock. Unsubscribe anytime.</p>
    <a href="/" class="inline-block bg-yellow-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-yellow-700">Browse deals on the dashboard</a>
  </section>

  <!-- Cross-state links -->
  <section class="mb-8">
    <p class="text-sm text-gray-600">Also: {cross_html}</p>
  </section>

</main>

{footer}

</body>
</html>
"""


def update_sitemap(output_dir: Path, today: str) -> None:
    """Add/update location pages in sitemap.xml."""
    sitemap_path = output_dir / "sitemap.xml"
    if not sitemap_path.exists():
        return

    content = sitemap_path.read_text()

    # Remove existing location page entries
    content = re.sub(
        r'\s*<url>\s*<loc>https://beestock\.com\.au/buy-beekeeping-supplies-[^<]+</loc>.*?</url>',
        '',
        content,
        flags=re.DOTALL,
    )

    # Build new location entries
    loc_entries = ""
    for state in STATES:
        slug = STATE_SLUGS[state]
        loc_entries += f"""
  <url>
    <loc>https://beestock.com.au/buy-beekeeping-supplies-{slug}.html</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>"""

    content = content.replace("</urlset>", loc_entries + "\n</urlset>")
    sitemap_path.write_text(content)
    print(f"Sitemap updated: added {len(STATES)} location page URLs")


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} /path/to/bee-stock /path/to/bee-dashboard/")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print("Loading retailer data...")
    by_retailer = load_all_products(data_dir)
    total_products = sum(len(v) for v in by_retailer.values())
    print(f"  {len(by_retailer)} retailers, {total_products} products loaded")

    for state in STATES:
        print(f"\nBuilding {state} page...")
        html = build_page(state, by_retailer, today)
        slug = STATE_SLUGS[state]
        out_file = output_dir / f"buy-beekeeping-supplies-{slug}.html"
        out_file.write_text(html)

        stats = get_retailer_stats(by_retailer, state)
        in_stock = sum(r["in_stock"] for r in stats)
        print(f"  Written: {out_file} ({in_stock} in-stock products, {len(stats)} retailers)")

    print("\nUpdating sitemap...")
    update_sitemap(output_dir, today)

    print("\nDone.")


if __name__ == "__main__":
    main()
