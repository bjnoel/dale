#!/usr/bin/env python3
"""
Build static category landing pages for beestock.com.au SEO.

Generates one HTML page per product category at /category/{slug}.html
Target queries: "buy langstroth hive Australia", "honey extractor Australia", etc.

Usage:
    python3 build_bee_category_pages.py /path/to/bee-stock /path/to/bee-dashboard/
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

from bee_categories import CATEGORIES, CATEGORY_NAMES, categorise_product
from bee_retailers import RETAILER_NAMES
from beestock_layout import (
    render_head, render_header, render_footer,
    SITE_NAME, SITE_URL,
)

# ------------------------------------------------------------------ #
# SEO metadata per category
# ------------------------------------------------------------------ #

CATEGORY_SEO = {
    "hives-boxes": {
        "title": "Buy Beehives & Boxes in Australia",
        "description": (
            "Compare prices on beehives, Langstroth boxes, nucleus hives, and Flow Hives "
            "from 6 Australian beekeeping retailers. Updated daily."
        ),
        "intro": (
            "Looking to buy a beehive or hive box in Australia? beestock.com.au tracks live "
            "stock and prices from 6 Australian retailers every day, so you can compare "
            "Langstroth boxes, nucleus hives, brood boxes, and complete hive setups without "
            "checking each store separately. Whether you are setting up your first colony or "
            "expanding an existing apiary, use the list below to find the best available price. "
            "Prices updated daily. In-stock items shown first."
        ),
        "keywords": "buy beehive Australia, Langstroth hive Australia, beehive price comparison",
        "groups": ["Langstroth", "Flow Hive", "Nucleus", "Brood Box", "Super", "Lid", "Base"],
    },
    "frames-foundation": {
        "title": "Buy Beekeeping Frames & Foundation in Australia",
        "description": (
            "Compare prices on beekeeping frames and wax foundation from Australian retailers. "
            "Langstroth deep, medium, and ideal frames. Updated daily."
        ),
        "intro": (
            "Frames and foundation are the backbone of any hive. beestock.com.au compares "
            "current stock and prices across 6 Australian beekeeping retailers so you can "
            "find deep frames, medium frames, ideal frames, and wax or plastic foundation "
            "at the best available price. Results show in-stock items first. Updated daily."
        ),
        "keywords": "beekeeping frames Australia, langstroth frames, wax foundation Australia",
        "groups": ["Deep", "Medium", "Ideal", "Wired", "Unwired", "Wax", "Plastic"],
    },
    "extractors-processing": {
        "title": "Buy Honey Extractors & Processing Equipment in Australia",
        "description": (
            "Compare prices on honey extractors, uncapping knives, honey gates, strainers, "
            "and bottling tanks from 6 Australian retailers. Updated daily."
        ),
        "intro": (
            "Comparing honey extractor prices in Australia can save hundreds of dollars. "
            "beestock.com.au tracks prices across 6 Australian beekeeping stores every day "
            "and shows you who has the best deal right now. We cover manual and electric "
            "extractors from 2-frame to 9-frame, plus uncapping forks, honey gates, "
            "settling tanks, and other processing equipment. In-stock items shown first."
        ),
        "keywords": "honey extractor Australia, buy honey extractor, honey extractor price comparison",
        "groups": ["2 Frame", "4 Frame", "6 Frame", "9 Frame", "Electric", "Manual", "Uncapping"],
    },
    "protective-gear": {
        "title": "Buy Beekeeping Suits, Jackets & Protective Gear in Australia",
        "description": (
            "Compare prices on bee suits, jackets, veils, and gloves from Australian "
            "beekeeping retailers. Updated daily."
        ),
        "intro": (
            "Protective gear is essential for safe beekeeping. beestock.com.au tracks "
            "current stock and prices on bee suits, beekeeping jackets, veils, gloves, "
            "and hats across 6 Australian retailers. Compare full suits, ventilated "
            "mesh suits, cotton jackets, and round veils. Updated daily with in-stock "
            "items shown first."
        ),
        "keywords": "bee suit Australia, beekeeping jacket Australia, beekeeper protective gear",
        "groups": ["Full Suit", "Jacket", "Veil", "Gloves", "Hat", "Ventilated", "Cotton"],
    },
    "smokers-tools": {
        "title": "Buy Bee Smokers & Beekeeping Tools in Australia",
        "description": (
            "Compare prices on bee smokers, hive tools, queen catchers, and beekeeping "
            "accessories from Australian retailers. Updated daily."
        ),
        "intro": (
            "beestock.com.au compares bee smoker and beekeeping tool prices from 6 "
            "Australian retailers every day. Find the best price on smokers, hive tools, "
            "J-hook tools, bee brushes, queen marking pens, and frame lifters. "
            "In-stock items shown first. Updated daily."
        ),
        "keywords": "bee smoker Australia, hive tool Australia, beekeeping tools",
        "groups": ["Smoker", "Hive Tool", "J Hook", "Queen", "Frame Lifter", "Brush"],
    },
    "treatments": {
        "title": "Buy Varroa Mite Treatments & Beehive Health Products in Australia",
        "description": (
            "Compare prices on varroa mite treatments, Apistan, Apivar, oxalic acid, "
            "and hive health products from Australian beekeeping retailers. Updated daily."
        ),
        "intro": (
            "With varroa mite now established in Australia, treatment products are "
            "in high demand. beestock.com.au tracks current stock and prices on Apistan, "
            "Apivar, oxalic acid vaporisers, formic acid treatments, and small hive beetle "
            "traps across 6 Australian retailers. In-stock items shown first. Updated daily."
        ),
        "keywords": "varroa mite treatment Australia, Apistan Australia, Apivar Australia, oxalic acid beekeeping",
        "groups": ["Apistan", "Apivar", "Oxalic", "Formic", "Beetle Trap", "Thymol"],
    },
    "feeders": {
        "title": "Buy Bee Feeders & Supplement Feed in Australia",
        "description": (
            "Compare prices on bee feeders, pollen substitutes, and syrup feeders "
            "from Australian beekeeping retailers. Updated daily."
        ),
        "intro": (
            "beestock.com.au tracks current bee feeder prices across Australian "
            "beekeeping retailers. Find frame feeders, entrance feeders, top feeders, "
            "pollen patties, and pollen substitutes at the best available price. "
            "Updated daily with in-stock items shown first."
        ),
        "keywords": "bee feeder Australia, pollen substitute Australia, beekeeping feeder",
        "groups": ["Frame Feeder", "Entrance Feeder", "Top Feeder", "Pollen", "Boardman"],
    },
    "honey-containers": {
        "title": "Buy Honey Jars, Bottles & Labels in Australia",
        "description": (
            "Compare prices on honey jars, bottles, containers, and labels from "
            "Australian beekeeping retailers. Updated daily."
        ),
        "intro": (
            "beestock.com.au compares honey jar and container prices from Australian "
            "beekeeping supply stores. Find hex jars, round jars, squeeze bottles, "
            "bulk packs, and honey labels at the best price available right now. "
            "In-stock items shown first. Updated daily."
        ),
        "keywords": "honey jars Australia, honey bottles Australia, honey containers buy",
        "groups": ["Hex Jar", "Round Jar", "Squeeze", "Label", "Lid", "Bulk"],
    },
    "books-education": {
        "title": "Buy Beekeeping Books & Courses in Australia",
        "description": (
            "Compare prices on beekeeping books, guides, and educational resources "
            "from Australian retailers. Updated daily."
        ),
        "intro": (
            "beestock.com.au lists current beekeeping books and educational resources "
            "available from Australian suppliers. Find beginner guides, advanced "
            "management books, and reference manuals at the best available price. "
            "Updated daily with in-stock items shown first."
        ),
        "keywords": "beekeeping books Australia, beekeeping guide buy, learn beekeeping Australia",
        "groups": ["Beginner", "Advanced", "Manual", "Guide"],
    },
}


# ------------------------------------------------------------------ #
# Product loading (mirrors build_bee_dashboard.py logic)
# ------------------------------------------------------------------ #

def load_products(data_dir: Path) -> list[dict]:
    """Load all products from bee-stock data directory."""
    products = []
    for retailer_dir in sorted(data_dir.iterdir()):
        if not retailer_dir.is_dir():
            continue
        latest = retailer_dir / "latest.json"
        if not latest.exists():
            continue
        with open(latest) as f:
            data = json.load(f)
        retailer_key = retailer_dir.name
        for p in data.get("products", []):
            title = p.get("title", "")
            if title.lower() in ("gift card", "gift voucher", "gift certificate"):
                continue
            tags = p.get("tags", [])
            product_type = p.get("product_type", "")
            cat = categorise_product(title, tags, product_type)

            variants = p.get("variants", [])
            # min price (prefer available variants)
            avail_prices = [float(v["price"]) for v in variants
                            if v.get("price") and v.get("available", True)]
            all_prices = [float(v["price"]) for v in variants if v.get("price")]
            min_price = min(avail_prices) if avail_prices else (
                min(all_prices) if all_prices else p.get("min_price") or p.get("price")
            )
            max_price = max(avail_prices) if avail_prices else (
                max(all_prices) if all_prices else None
            )
            if max_price and min_price and max_price <= min_price + 0.01:
                max_price = None

            available = p.get("any_available", p.get("available", False))
            if not available and avail_prices:
                available = True

            retailer_display = (
                p.get("retailer_name")
                or RETAILER_NAMES.get(retailer_key, retailer_key.replace("-", " ").title())
            )

            products.append({
                "title": title,
                "cat": cat,
                "retailer": retailer_display,
                "retailer_key": retailer_key,
                "url": p.get("url", ""),
                "min_price": round(float(min_price), 2) if min_price else None,
                "max_price": round(float(max_price), 2) if max_price else None,
                "available": bool(available),
            })

    return products


# ------------------------------------------------------------------ #
# Grouping logic
# ------------------------------------------------------------------ #

def group_products(products: list[dict], group_terms: list[str]) -> dict[str, list[dict]]:
    """
    Group products by keywords found in their titles.
    Products matching no group term go into 'Other'.
    Returns ordered dict: group_name -> [products].
    """
    groups: dict[str, list[dict]] = {}
    for term in group_terms:
        groups[term] = []
    groups["Other"] = []

    for p in products:
        title_lower = p["title"].lower()
        matched = False
        for term in group_terms:
            if term.lower() in title_lower:
                groups[term].append(p)
                matched = True
                break
        if not matched:
            groups["Other"].append(p)

    # Remove empty groups (except Other if there are items in it)
    return {k: v for k, v in groups.items() if v}


# ------------------------------------------------------------------ #
# HTML generation
# ------------------------------------------------------------------ #

def product_row(p: dict) -> str:
    """Render a single product row."""
    title = p["title"]
    url = p["url"]
    retailer = p["retailer"]
    available = p["available"]
    min_price = p["min_price"]
    max_price = p["max_price"]

    # Price display
    if min_price:
        if max_price:
            price_str = f"${min_price:.2f} – ${max_price:.2f}"
        else:
            price_str = f"${min_price:.2f}"
    else:
        price_str = "—"

    # Availability badge
    avail_cls = "bg-green-100 text-green-800" if available else "bg-gray-100 text-gray-500"
    avail_label = "In Stock" if available else "Out of Stock"

    link = f'<a href="{url}" target="_blank" rel="noopener" class="text-amber-800 hover:underline font-medium">{title}</a>' if url else title

    return f"""
      <tr class="{'bg-white' if available else 'bg-gray-50'}">
        <td class="py-2 px-3 text-sm">{link}</td>
        <td class="py-2 px-3 text-sm text-gray-600 whitespace-nowrap">{retailer}</td>
        <td class="py-2 px-3 text-sm font-semibold text-right whitespace-nowrap">{price_str}</td>
        <td class="py-2 px-3 text-right">
          <span class="text-xs px-2 py-0.5 rounded-full font-medium {avail_cls}">{avail_label}</span>
        </td>
      </tr>"""


def render_product_table(products: list[dict], group_terms: list[str]) -> str:
    """Render the product table, optionally with group headings."""
    if not products:
        return '<p class="text-gray-500 text-sm">No products found in this category.</p>'

    table_header = """
    <table class="w-full text-left border-collapse">
      <thead>
        <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
          <th class="py-2 px-3 font-semibold">Product</th>
          <th class="py-2 px-3 font-semibold">Retailer</th>
          <th class="py-2 px-3 font-semibold text-right">Price</th>
          <th class="py-2 px-3 font-semibold text-right">Status</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100">"""

    # Sort: in-stock first, then by price
    products_sorted = sorted(
        products,
        key=lambda p: (not p["available"], p["min_price"] or 9999)
    )

    grouped = group_products(products_sorted, group_terms)
    tbody = ""

    if len(grouped) == 1:
        # Only one group (likely "Other") — no group headings
        for p in list(grouped.values())[0]:
            tbody += product_row(p)
    else:
        for group_name, group_products_list in grouped.items():
            if group_products_list:
                count = len(group_products_list)
                in_stock = sum(1 for p in group_products_list if p["available"])
                tbody += f"""
      <tr>
        <td colspan="4" class="py-2 px-3 bg-amber-50 text-xs font-semibold text-amber-900 uppercase tracking-wide">
          {group_name} <span class="font-normal text-gray-500">({in_stock} in stock of {count})</span>
        </td>
      </tr>"""
                for p in group_products_list:
                    tbody += product_row(p)

    return table_header + tbody + "\n      </tbody>\n    </table>"


def build_category_page(
    cat_slug: str,
    products: list[dict],
    total_in_stock: int,
    today: str,
) -> str:
    """Build the full HTML for one category page."""
    seo = CATEGORY_SEO.get(cat_slug, {
        "title": f"Buy {CATEGORY_NAMES.get(cat_slug, cat_slug.title())} in Australia",
        "description": f"Compare prices on {CATEGORY_NAMES.get(cat_slug, cat_slug)} from Australian beekeeping retailers.",
        "intro": f"Compare current prices on {CATEGORY_NAMES.get(cat_slug, cat_slug)} from Australian beekeeping retailers.",
        "keywords": f"beekeeping {cat_slug} Australia",
        "groups": [],
    })

    canonical = f"{SITE_URL}/category/{cat_slug}.html"
    cat_name = CATEGORY_NAMES.get(cat_slug, cat_slug.title())
    in_stock = sum(1 for p in products if p["available"])
    total = len(products)

    head = render_head(
        title=f"{seo['title']} | beestock.com.au",
        description=seo["description"],
        canonical_url=canonical,
        og_title=seo["title"],
        og_description=seo["description"],
        og_type="website",
    )
    header = render_header(active_path=f"/category/{cat_slug}.html")

    product_table = render_product_table(products, seo.get("groups", []))

    # All category links for breadcrumb/navigation
    cat_links = " &middot; ".join(
        f'<a href="/category/{c["slug"]}.html" class="hover:text-amber-700">{c["name"]}</a>'
        for c in CATEGORIES
    )

    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-5xl mx-auto px-4 py-6">

  <!-- Breadcrumb -->
  <nav class="text-xs text-gray-400 mb-4">
    <a href="/" class="hover:text-amber-700">beestock.com.au</a>
    &rsaquo;
    <span class="text-gray-600">{cat_name}</span>
  </nav>

  <!-- Page header -->
  <div class="mb-6">
    <h1 class="text-2xl font-bold text-gray-900 mb-2">{seo["title"]}</h1>
    <p class="text-gray-600 text-sm leading-relaxed max-w-2xl">{seo["intro"]}</p>
    <p class="text-xs text-gray-400 mt-2">
      {in_stock} in stock of {total} products tracked &middot; Updated {today}
    </p>
  </div>

  <!-- Back to search -->
  <div class="mb-4">
    <a href="/?cat={cat_slug}" class="inline-block text-sm bg-amber-100 text-amber-900 px-3 py-1.5 rounded hover:bg-amber-200 transition-colors">
      Search &amp; filter within {cat_name} &rarr;
    </a>
  </div>

  <!-- Product table -->
  <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-8">
    {product_table}
  </div>

  <!-- All categories -->
  <div class="text-sm text-gray-500 mb-8">
    <span class="font-medium text-gray-700">Browse by category:</span><br>
    <div class="mt-1 leading-loose">{cat_links}</div>
  </div>

  <!-- Subscribe CTA -->
  <div class="bg-amber-50 border border-amber-200 rounded-lg p-5 mb-6">
    <h2 class="font-semibold text-amber-900 mb-1">Get daily price alerts</h2>
    <p class="text-sm text-amber-800 mb-3">
      Subscribe for a daily digest showing price changes and restocks across all {total_in_stock:,} products we track.
    </p>
    <form id="subscribeForm" class="flex gap-2 max-w-md">
      <input id="subEmail" type="email" placeholder="your@email.com" required
        class="flex-1 border border-amber-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400">
      <button type="submit"
        class="bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium px-4 py-1.5 rounded transition-colors">
        Subscribe
      </button>
    </form>
    <p id="subMsg" class="hidden text-sm mt-2"></p>
  </div>

</main>

{footer}

<script>
const subForm = document.getElementById('subscribeForm');
const subMsg = document.getElementById('subMsg');
if (subForm) {{
  subForm.addEventListener('submit', function(e) {{
    e.preventDefault();
    const email = document.getElementById('subEmail').value.trim();
    if (!email) return;
    const btn = subForm.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Subscribing...';
    fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email}}),
    }})
    .then(r => r.json())
    .then(d => {{
      subMsg.classList.remove('hidden', 'text-red-700');
      subMsg.classList.add('text-green-700');
      subMsg.textContent = d.message === 'Already subscribed'
        ? "You're already subscribed."
        : "Subscribed! Check your inbox.";
      subForm.reset();
      btn.disabled = false;
      btn.textContent = 'Subscribe';
    }})
    .catch(() => {{
      subMsg.classList.remove('hidden', 'text-green-700');
      subMsg.classList.add('text-red-700');
      subMsg.textContent = 'Something went wrong. Please try again.';
      btn.disabled = false;
      btn.textContent = 'Subscribe';
    }});
  }});
}}
</script>

</body>
</html>"""


# ------------------------------------------------------------------ #
# Sitemap update
# ------------------------------------------------------------------ #

def update_sitemap(output_dir: Path, today: str) -> None:
    """Add category pages to sitemap.xml."""
    sitemap_path = output_dir / "sitemap.xml"
    if not sitemap_path.exists():
        return

    content = sitemap_path.read_text()

    # Remove existing category entries
    content = re.sub(
        r'\s*<url>\s*<loc>https://beestock\.com\.au/category/[^<]+</loc>.*?</url>',
        '',
        content,
        flags=re.DOTALL,
    )

    # Build new category entries
    cat_entries = ""
    for cat in CATEGORIES:
        cat_entries += f"""
  <url>
    <loc>https://beestock.com.au/category/{cat["slug"]}.html</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>"""

    # Insert before </urlset>
    content = content.replace("</urlset>", cat_entries + "\n</urlset>")
    sitemap_path.write_text(content)
    print(f"Sitemap updated: added {len(CATEGORIES)} category URLs")


# ------------------------------------------------------------------ #
# Dashboard footer patch — add category links
# ------------------------------------------------------------------ #

def patch_dashboard_footer(output_dir: Path) -> None:
    """
    Add category page links to the beestock dashboard footer if not already present.
    """
    index_path = output_dir / "index.html"
    if not index_path.exists():
        return
    content = index_path.read_text()
    if "Browse by category" in content:
        print("Dashboard already has category links — skipping patch")
        return

    cat_links_html = "\n".join(
        f'<a href="/category/{cat["slug"]}.html" class="hover:text-gray-600">{cat["name"]}</a>'
        for cat in CATEGORIES
    )

    # Inject before the closing </footer> tag
    section = f"""
  <div class="mt-3">
    <p class="text-xs text-gray-500 mb-1 font-medium">Browse by category:</p>
    <div class="flex flex-wrap justify-center gap-x-3 gap-y-1 text-xs text-gray-400">
{cat_links_html}
    </div>
  </div>
"""
    content = content.replace("</footer>", section + "</footer>", 1)
    tmp = output_dir / "index.html.tmp"
    tmp.write_text(content)
    tmp.rename(index_path)
    print("Dashboard footer patched with category links")


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build beestock category pages")
    parser.add_argument("data_dir", help="Path to bee-stock/ data directory")
    parser.add_argument("output_dir", nargs="?", default="/opt/dale/bee-dashboard",
                        help="Output directory (bee-dashboard)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    if not data_dir.exists():
        print(f"Error: data_dir {data_dir} does not exist")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    category_dir = output_dir / "category"
    category_dir.mkdir(exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"Loading products from {data_dir}...")
    all_products = load_products(data_dir)
    print(f"Loaded {len(all_products)} products")

    total_in_stock = sum(1 for p in all_products if p["available"])

    # Group products by category
    by_cat: dict[str, list[dict]] = {}
    for p in all_products:
        by_cat.setdefault(p["cat"], []).append(p)

    # Build one page per category (skip 'other')
    pages_written = 0
    for cat in CATEGORIES:
        slug = cat["slug"]
        products = by_cat.get(slug, [])
        if not products:
            print(f"  {cat['name']}: no products, skipping")
            continue

        html = build_category_page(slug, products, total_in_stock, today)
        out_path = category_dir / f"{slug}.html"
        tmp_path = category_dir / f"{slug}.html.tmp"
        tmp_path.write_text(html)
        tmp_path.rename(out_path)
        in_stock = sum(1 for p in products if p["available"])
        print(f"  {cat['name']}: {len(products)} products ({in_stock} in stock) -> {out_path}")
        pages_written += 1

    print(f"\nWrote {pages_written} category pages to {category_dir}")

    # Update sitemap
    update_sitemap(output_dir, today)

    # Patch dashboard footer
    patch_dashboard_footer(output_dir)

    print("Done.")


if __name__ == "__main__":
    main()
