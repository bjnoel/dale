#!/usr/bin/env python3
"""
Build retailer profile pages for beestock.com.au.
Generates /retailer/<key>.html and /retailer/index.html.

Usage:
    python3 build_bee_retailer_pages.py /path/to/data/bee-stock /path/to/bee-dashboard/
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from bee_categories import CATEGORY_NAMES, categorise_product
from bee_retailers import RETAILERS, RETAILER_NAMES, SHIPPING_MAP, restriction_warning
from beestock_layout import (
    render_head, render_header, render_breadcrumb, render_footer,
    SITE_URL,
)

# Per-retailer descriptions and tags
RETAILER_META = {
    "ecrotek": {
        "tags": ["full range", "extractors", "hives", "treatments"],
        "description": (
            "Ecrotek is a leading Australian beekeeping supplier based in Melbourne, VIC. "
            "They carry a full range of equipment including hives, extractors, protective gear, "
            "frames, foundation, and health treatments. Nationwide shipping."
        ),
    },
    "the-bee-store": {
        "tags": ["full range", "hives", "frames", "beginner kits"],
        "description": (
            "The Bee Store is an Australian beekeeping retailer offering hives, frames, "
            "foundation, protective gear, and beginner starter kits. They carry a wide selection "
            "of Langstroth equipment and accessories."
        ),
    },
    "buzzbee": {
        "tags": ["hives", "frames", "tools", "protective gear"],
        "description": (
            "Buzzbee is an Australian beekeeping supplier offering hive components, frames, "
            "foundation, tools, and protective clothing at competitive prices."
        ),
    },
    "flow-hive": {
        "tags": ["Flow Hive", "innovative", "beginner-friendly"],
        "description": (
            "Flow Hive, based in Byron Bay NSW, invented the patented Flow Frame technology "
            "that lets you harvest honey without opening the hive. They sell complete Flow Hive "
            "systems, accessories, and protective gear."
        ),
    },
}


def load_retailer_data(data_dir: Path) -> dict:
    """Load latest.json for all retailers. Returns dict keyed by retailer_key."""
    retailers = {}
    for retailer_dir in sorted(data_dir.iterdir()):
        if not retailer_dir.is_dir():
            continue
        latest = retailer_dir / "latest.json"
        if not latest.exists():
            continue
        with open(latest) as f:
            data = json.load(f)
        retailers[retailer_dir.name] = data
    return retailers


def build_category_breakdown(products: list) -> list:
    """Return list of {slug, name, in_stock, total} sorted by in_stock desc."""
    counts: dict[str, dict] = {}
    for p in products:
        title = p.get("title", "")
        tags = p.get("tags", [])
        product_type = p.get("product_type", "")
        cat = categorise_product(title, tags, product_type)
        name = CATEGORY_NAMES.get(cat, "Other")
        if name == "Other":
            continue
        if cat not in counts:
            counts[cat] = {"slug": cat, "name": name, "in_stock": 0, "total": 0}
        counts[cat]["total"] += 1
        if p.get("any_available", p.get("available", False)):
            counts[cat]["in_stock"] += 1
    return sorted(counts.values(), key=lambda x: (-x["in_stock"], -x["total"]))


def build_retailer_page(retailer_key: str, data: dict) -> str:
    meta = RETAILER_META.get(retailer_key, {})
    retailer_info = RETAILERS.get(retailer_key, {})
    name = RETAILER_NAMES.get(retailer_key, retailer_key.replace("-", " ").title())
    location = retailer_info.get("location", "Australia")
    url = f"https://{retailer_info['domain']}" if retailer_info.get("domain") else ""
    tags = meta.get("tags", [])
    description = meta.get("description", "")
    ships = sorted(SHIPPING_MAP.get(retailer_key, []))

    products = data.get("products", [])
    # Filter gift cards
    products = [p for p in products if p.get("title", "").lower() not in
                ("gift card", "gift voucher", "gift certificate")]

    in_stock_count = sum(1 for p in products if p.get("any_available", p.get("available", False)))
    total_count = len(products)

    category_breakdown = build_category_breakdown(products)
    cat_count = len(category_breakdown)

    restrict = restriction_warning(retailer_key)
    restrict_badge = (
        f'<span class="text-xs px-2 py-0.5 bg-red-100 text-red-800 rounded-full font-semibold ml-2">{restrict}</span>'
        if restrict else ""
    )
    tag_badges = "".join(
        f'<span class="text-xs px-2 py-0.5 bg-gray-100 text-gray-700 border border-gray-200 rounded mr-1 mb-1">{t}</span>'
        for t in tags
    )
    ship_badges = "".join(
        f'<span class="text-xs px-2 py-0.5 bg-gray-600 text-white rounded mr-1">{s}</span>'
        for s in ships
    )

    # Category breakdown rows
    cat_rows = ""
    for c in category_breakdown:
        in_s = c["in_stock"]
        stock_cell = (
            f'<span class="text-green-700 font-bold">{in_s}</span>'
            if in_s > 0 else f'<span class="text-gray-400">{in_s}</span>'
        )
        cat_rows += f"""
        <tr class="border-b border-gray-100 hover:bg-gray-50">
          <td class="py-1.5 pr-3 text-sm"><a href="/category/{c['slug']}.html" class="text-yellow-700 hover:underline">{c['name']}</a></td>
          <td class="py-1.5 pr-3 text-center text-sm">{stock_cell}</td>
          <td class="py-1.5 text-center text-sm text-gray-400">{c['total']}</td>
        </tr>"""

    # Top in-stock products
    in_stock_products = [p for p in products if p.get("any_available", p.get("available", False))]
    in_stock_products.sort(key=lambda p: p.get("min_price") or 9999)
    in_stock_products = in_stock_products[:20]

    product_rows = ""
    for p in in_stock_products:
        price = f"${p['min_price']:.2f}" if p.get("min_price") else "POA"
        title = p.get("title", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        p_url = p.get("url", "#")
        product_rows += f"""
        <tr class="border-b border-gray-100 hover:bg-gray-50">
          <td class="py-1.5 pr-3 text-sm"><a href="{p_url}" target="_blank" rel="noopener" class="text-yellow-700 hover:underline">{title}</a></td>
          <td class="py-1.5 text-right text-sm font-medium">{price}</td>
        </tr>"""

    url_display = url.replace("https://", "").replace("http://", "")
    url_link = (
        f'<a href="{url}" target="_blank" rel="noopener" class="text-yellow-700 hover:underline">{url_display}</a>'
        if url else ""
    )

    scraped_at = data.get("scraped_at", "")
    if scraped_at:
        try:
            dt = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
            scraped_at_fmt = dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            scraped_at_fmt = scraped_at
    else:
        scraped_at_fmt = "recently"

    extra_style = """\
  .stat-card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; padding: 1.2rem; text-align: center; }
  .stat-card .number { font-size: 2rem; font-weight: 700; color: #d97706; }
  .stat-card .label { font-size: 0.85rem; color: #6b7280; }
  .scrollable-table { max-height: 420px; overflow-y: auto; }
  .scrollable-table thead { position: sticky; top: 0; background: #f9fafb; }"""

    head = render_head(
        title=f"{name} - Beekeeping Supply Prices & Stock | beestock.com.au",
        description=f"Browse {name}'s current beekeeping supply stock. {total_count} products tracked, {in_stock_count} in stock. Compare prices on hives, extractors, frames, and more.",
        canonical_url=f"{SITE_URL}/retailer/{retailer_key}.html",
        og_title=f"{name} - Beekeeping Supply Prices & Stock",
        og_description=f"Browse {name}'s beekeeping supplies. {total_count} products tracked, {in_stock_count} in stock.",
        og_type="website",
        extra_style=extra_style,
    )
    header_html = render_header(active_path="/retailer/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Retailers", "/retailer/"), (name, "")])
    footer = render_footer()

    return f"""{head}
{header_html}

<main class="max-w-3xl mx-auto px-4 py-6">
  {breadcrumb}

  <div class="mb-6">
    <h2 class="text-2xl font-bold text-gray-900 mb-1">{name} {restrict_badge}</h2>
    <p class="text-gray-500 text-sm mb-2">📍 {location}{(' · ' + url_link) if url_link else ''}</p>
    <div class="mb-2">{tag_badges}</div>
    <div>Ships to: {ship_badges}</div>
  </div>

  <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
    <div class="stat-card"><div class="number">{in_stock_count}</div><div class="label">In Stock</div></div>
    <div class="stat-card"><div class="number">{total_count}</div><div class="label">Products Tracked</div></div>
    <div class="stat-card"><div class="number">{cat_count}</div><div class="label">Categories</div></div>
    <div class="stat-card"><div class="number">{len(ships)}</div><div class="label">States</div></div>
  </div>

  {f'<div class="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-6 text-sm text-gray-700">{description}</div>' if description else ''}

  <div class="grid md:grid-cols-2 gap-6">
    <div class="border border-gray-200 rounded-lg">
      <div class="flex justify-between items-center px-4 py-3 border-b border-gray-200 bg-gray-50 rounded-t-lg">
        <span class="font-semibold text-sm">Categories Carried</span>
        <span class="text-xs text-gray-500">{cat_count} categories</span>
      </div>
      <div class="scrollable-table">
        <table class="w-full text-left">
          <thead>
            <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
              <th class="py-2 px-3">Category</th>
              <th class="py-2 px-3 text-center">In Stock</th>
              <th class="py-2 px-3 text-center">Total</th>
            </tr>
          </thead>
          <tbody class="px-3">
            {cat_rows}
          </tbody>
        </table>
      </div>
    </div>

    <div class="border border-gray-200 rounded-lg">
      <div class="flex justify-between items-center px-4 py-3 border-b border-gray-200 bg-gray-50 rounded-t-lg">
        <span class="font-semibold text-sm">In Stock Now</span>
        <a href="/?retailer={retailer_key}" class="text-xs px-2 py-1 border border-yellow-600 text-yellow-700 rounded hover:bg-yellow-50">View all on dashboard →</a>
      </div>
      <div class="scrollable-table">
        <table class="w-full text-left">
          <thead>
            <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
              <th class="py-2 px-3">Product</th>
              <th class="py-2 px-3 text-right">Price</th>
            </tr>
          </thead>
          <tbody class="px-3">
            {product_rows}
          </tbody>
        </table>
      </div>
      <div class="px-4 py-2 border-t border-gray-200 text-xs text-gray-500">Showing top 20 in-stock products. <a href="/?retailer={retailer_key}" class="text-yellow-700 hover:underline">See all →</a></div>
    </div>
  </div>

  <p class="text-xs text-gray-400 mt-4">Data updated daily. Last checked: {scraped_at_fmt}.</p>
</main>

{footer}

</body>
</html>"""


def build_index_page(retailers_data: dict, today: str) -> str:
    count = len(retailers_data)
    cards = ""
    for key in sorted(retailers_data.keys()):
        data = retailers_data[key]
        meta = RETAILER_META.get(key, {})
        retailer_info = RETAILERS.get(key, {})
        name = RETAILER_NAMES.get(key, key.replace("-", " ").title())
        tags = meta.get("tags", [])
        ships = sorted(SHIPPING_MAP.get(key, []))
        location = retailer_info.get("location", "Australia")

        products = data.get("products", [])
        products = [p for p in products if p.get("title", "").lower() not in
                    ("gift card", "gift voucher", "gift certificate")]
        in_stock = sum(1 for p in products if p.get("any_available", p.get("available", False)))
        total = len(products)

        restrict = restriction_warning(key)
        restrict_badge = (
            f'<span class="text-xs px-2 py-0.5 bg-red-100 text-red-800 rounded-full font-semibold">{restrict}</span>'
            if restrict else ""
        )
        tag_badges = " ".join(
            f'<span class="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-700 border border-gray-200 rounded">{t}</span>'
            for t in tags[:3]
        )
        ship_str = ", ".join(ships)

        cards += f"""
    <div class="border border-gray-200 rounded-lg hover:shadow-md transition-shadow">
      <div class="p-4">
        <div class="flex justify-between items-start mb-1">
          <h3 class="font-semibold text-sm">
            <a href="/retailer/{key}.html" class="text-gray-900 hover:text-yellow-700 no-underline">{name}</a>
          </h3>
          {restrict_badge}
        </div>
        <p class="text-xs text-gray-500 mb-2">📍 {location}</p>
        <div class="mb-2 flex flex-wrap gap-1">{tag_badges}</div>
        <p class="text-xs text-gray-500 mb-1"><strong>{in_stock}</strong> in stock · {total} tracked</p>
        <p class="text-xs text-gray-500 mb-0">Ships to: {ship_str}</p>
      </div>
      <div class="px-4 pb-4">
        <a href="/retailer/{key}.html" class="block text-center text-sm px-3 py-1.5 border border-yellow-600 text-yellow-700 rounded hover:bg-yellow-50 no-underline">View Retailer →</a>
      </div>
    </div>"""

    head = render_head(
        title="Australian Beekeeping Supply Retailers | beestock.com.au",
        description=f"Browse all {count} Australian beekeeping retailers tracked by beestock.com.au. Compare stock, prices, and product ranges.",
        canonical_url=f"{SITE_URL}/retailer/",
        og_title="Australian Beekeeping Supply Retailers - beestock.com.au",
    )
    header_html = render_header(active_path="/retailer/")
    footer = render_footer()

    return f"""{head}
{header_html}

<main class="max-w-3xl mx-auto px-4 py-6">
  <h2 class="text-2xl font-bold text-gray-900 mb-1">Australian Beekeeping Retailers</h2>
  <p class="text-gray-500 text-sm mb-6">Daily stock tracking across {count} retailers. Updated {today}.</p>

  <div class="grid md:grid-cols-2 gap-4">
    {cards}
  </div>
</main>

{footer}

</body>
</html>"""


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <data_dir> <output_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    retailer_dir = output_dir / "retailer"
    retailer_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    retailers_data = load_retailer_data(data_dir)

    if not retailers_data:
        print("No retailer data found.")
        sys.exit(1)

    for key, data in retailers_data.items():
        name = RETAILER_NAMES.get(key, key.replace("-", " ").title())
        page = build_retailer_page(key, data)
        out = retailer_dir / f"{key}.html"
        out.write_text(page)
        products = data.get("products", [])
        products = [p for p in products if p.get("title", "").lower() not in
                    ("gift card", "gift voucher", "gift certificate")]
        in_stock = sum(1 for p in products if p.get("any_available", p.get("available", False)))
        total = len(products)
        print(f"  {name}: {in_stock} in stock / {total} total -> {out}")

    index = build_index_page(retailers_data, today)
    index_path = retailer_dir / "index.html"
    index_path.write_text(index)
    print(f"  Index -> {index_path} ({len(retailers_data)} retailers)")


if __name__ == "__main__":
    main()
