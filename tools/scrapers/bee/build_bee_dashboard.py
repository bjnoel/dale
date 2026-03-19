#!/usr/bin/env python3
"""
Build a static HTML dashboard for beestock.com.au from bee-stock JSON data.
Generates a single self-contained index.html with embedded data.

Usage:
    python3 build_bee_dashboard.py /path/to/data/bee-stock /path/to/output/
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from bee_retailers import SHIPPING_MAP, RETAILER_NAMES
from bee_categories import categorise_product, CATEGORIES, CATEGORY_NAMES
from beestock_layout import render_head, render_header, render_footer, SITE_NAME, LOGO_SVG


def _variant_key(product_url: str, variant: dict) -> str:
    """Generate a unique key for a specific variant within a product."""
    base = product_url or ""
    sku = variant.get("sku")
    if sku:
        return f"{base}|sku:{sku}"
    vid = variant.get("id")
    if vid:
        return f"{base}|id:{vid}"
    vtitle = variant.get("title", "Default")
    return f"{base}|v:{vtitle}"


def load_previous_snapshot(retailer_dir: Path) -> dict:
    """Load the second-most-recent snapshot for variant-level price comparison."""
    snapshots = sorted(
        [f for f in retailer_dir.glob("*.json") if re.match(r"\d{4}-\d{2}-\d{2}\.json$", f.name)],
        reverse=True,
    )
    if len(snapshots) < 2:
        return {}
    with open(snapshots[1]) as f:
        data = json.load(f)
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


def load_retailer_data(data_dir: Path) -> tuple[list[dict], list[dict], dict]:
    """Load latest.json from each retailer subdirectory and normalize products.

    Returns (products, retailers_loaded, category_counts).
    """
    products = []
    retailers_loaded = []
    category_counts: dict[str, int] = {}

    for retailer_dir in sorted(data_dir.iterdir()):
        if not retailer_dir.is_dir():
            continue

        latest = retailer_dir / "latest.json"
        if not latest.exists():
            continue

        with open(latest) as f:
            data = json.load(f)

        prev_products = load_previous_snapshot(retailer_dir)
        products_before = len(products)

        retailer_name = retailer_dir.name
        scraped_at = data.get("scraped_at", "unknown")

        for p in data.get("products", []):
            title = p.get("title", "")
            tags = p.get("tags", [])
            product_type = p.get("product_type", "")

            # Skip gift cards
            if title.lower() in ("gift card", "gift voucher", "gift certificate"):
                continue

            # Categorise
            cat = categorise_product(title, tags, product_type)
            category_counts[cat] = category_counts.get(cat, 0) + 1

            # Normalize pricing
            variants = p.get("variants", [])
            min_price = p.get("min_price")
            if min_price is None and variants:
                avail_prices = [float(v.get("price", 0)) for v in variants if v.get("price") and v.get("available", True)]
                all_prices = [float(v.get("price", 0)) for v in variants if v.get("price")]
                min_price = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)
            elif min_price is None:
                min_price = p.get("price")

            available = p.get("any_available", p.get("available", False))

            on_sale = p.get("on_sale", False)
            if not on_sale and variants:
                on_sale = any(
                    v.get("compare_at_price") and v.get("price")
                    and float(v["compare_at_price"]) > float(v["price"])
                    for v in variants
                    if v.get("compare_at_price") and v.get("price")
                )

            product_data = {
                "t": title,
                "n": p.get("retailer_name", retailer_name),
                "nk": p.get("retailer", retailer_name),
                "p": round(min_price, 2) if min_price else None,
                "a": bool(available),
                "u": p.get("url", ""),
                "sale": bool(on_sale),
                "cat": cat,
            }

            # Vendor (brand) if available
            vendor = p.get("vendor", "")
            if vendor:
                product_data["brand"] = vendor

            # Price/stock change detection vs previous snapshot (variant-level)
            if prev_products:
                product_url = p.get("url", "")
                variants_list = p.get("variants", [])
                if variants_list:
                    any_prev_found = False
                    best_change = None
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
                            if vprice and prev_vprice and abs(vprice - prev_vprice) > 0.01:
                                diff = vprice - prev_vprice
                                pct = abs(diff) / prev_vprice
                                ch = "up" if diff > 0 else "down"
                                if best_change is None or pct > best_change[2]:
                                    best_change = (ch, prev_vprice, pct, vprice)
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
                        product_data["p"] = round(best_change[3], 2)
                else:
                    prev = prev_products.get(p.get("url", "")) or prev_products.get(title)
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

        retailer_added = products[products_before:]
        retailers_loaded.append({
            "key": retailer_name,
            "name": data.get("retailer_name", retailer_name),
            "count": len(retailer_added),
            "in_stock": sum(1 for p in retailer_added if p.get("a")),
            "scraped_at": scraped_at,
            "st": SHIPPING_MAP.get(retailer_name, []),
        })

    return products, retailers_loaded, category_counts


def build_html(products: list[dict], retailers: list[dict], category_counts: dict) -> str:
    """Generate the dashboard HTML with embedded data."""
    products_json = json.dumps(products, separators=(",", ":"))
    retailers_json = json.dumps(retailers, separators=(",", ":"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build category filter options (sorted by count, descending)
    cat_options = []
    for slug, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        name = CATEGORY_NAMES.get(slug, slug)
        cat_options.append(f'<option value="{slug}">{name} ({count})</option>')
    cat_options_html = "\n".join(cat_options)

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
  .retailer-tag { font-size: 0.65rem; padding: 1px 5px; border-radius: 4px; background: #fef3c7; color: #92400e; }
  .cat-tag { font-size: 0.65rem; padding: 1px 5px; border-radius: 4px; background: #e0e7ff; color: #3730a3; }"""

    head = render_head(
        title="beestock.com.au - Australian Beekeeping Supply Price Tracker",
        description="Track beekeeping supply prices across Australian retailers. Daily price drops, restocks, and availability. Compare extractors, hives, protective gear, and treatments.",
        canonical_url="https://beestock.com.au/",
        og_title="beestock.com.au - Australian Beekeeping Supply Price Tracker",
        og_description="Track beekeeping supply prices across Australian retailers. Daily price drops, restocks, and availability.",
        og_type="website",
        extra_style=extra_style,
    )

    return f"""{head}
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="max-w-5xl mx-auto px-4 py-2">
    <div class="flex items-center justify-between gap-3">
      <a href="/" class="flex items-center gap-2 no-underline flex-shrink-0">
        {LOGO_SVG}
        <span class="text-lg font-bold text-yellow-800">{SITE_NAME}</span>
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
    <input type="text" id="search" placeholder="Search beekeeping supplies... (e.g. extractor, flow hive, varroa)"
      class="w-full px-4 py-3 border border-gray-300 rounded-lg text-lg focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
      autofocus>
    <div class="flex flex-wrap gap-2 items-center text-sm">
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" id="inStockOnly" checked class="rounded"> In stock only
      </label>
      <select id="categoryFilter" class="border border-gray-300 rounded px-2 py-1 text-sm">
        <option value="">All categories</option>
        {cat_options_html}
      </select>
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" id="changesOnly" class="rounded"> Changes only
      </label>
      <select id="retailerFilter" class="border border-gray-300 rounded px-2 py-1 text-sm">
        <option value="">All retailers</option>
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
    <button onclick="showMore()" class="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700">
      Show more results
    </button>
  </div>

  <!-- About section (below results) -->
  <div class="mt-6 mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-900">
    <p class="font-semibold mb-1">About beestock.com.au</p>
    <p>We track prices and availability across Australian beekeeping supply retailers every day. Find the best prices on extractors, hives, protective gear, varroa treatments, and more.</p>
    <p class="mt-2 text-yellow-700">Built by a beekeeper, for beekeepers. <a href="/digest.html" class="underline font-medium">See today's changes &rarr;</a></p>
  </div>
</main>

{render_footer(max_width="max-w-5xl")}

<script>
const P = {products_json};
const R = {retailers_json};

const CATEGORY_NAMES = {json.dumps(CATEGORY_NAMES, separators=(",", ":"))};

let displayCount = 50;
let currentResults = [];

// Populate retailer filter
const retailerSelect = document.getElementById('retailerFilter');
R.sort((a, b) => a.name.localeCompare(b.name)).forEach(r => {{
  const opt = document.createElement('option');
  opt.value = r.key;
  opt.textContent = `${{r.name}} (${{r.in_stock}} in stock)`;
  retailerSelect.appendChild(opt);
}});

const totalProducts = P.length;
const totalInStock = P.filter(p => p.a).length;
const statsText = `${{totalInStock.toLocaleString()}} in stock across ${{R.length}} retailers (${{totalProducts.toLocaleString()}} total)`;
document.getElementById('stats').textContent = statsText;
const sm = document.getElementById('statsSmall');
if (sm) sm.textContent = statsText;

// Search & filter
const searchInput = document.getElementById('search');
const inStockOnly = document.getElementById('inStockOnly');
const categoryFilter = document.getElementById('categoryFilter');
const changesOnly = document.getElementById('changesOnly');
const sortBy = document.getElementById('sortBy');

function search() {{
  displayCount = 50;
  const q = searchInput.value.toLowerCase().trim();
  const retailer = retailerSelect.value;
  const category = categoryFilter.value;
  const stockOnly = inStockOnly.checked;
  const sort = sortBy.value;

  let results = P;

  if (stockOnly) results = results.filter(p => p.a);
  if (category) results = results.filter(p => p.cat === category);
  if (changesOnly.checked) results = results.filter(p => p.ch);
  if (retailer) results = results.filter(p => p.nk === retailer);

  if (q) {{
    const terms = q.split(/\\s+/);
    results = results.filter(p => {{
      const text = (p.t + ' ' + (p.brand || '') + ' ' + (CATEGORY_NAMES[p.cat] || '')).toLowerCase();
      return terms.every(t => text.includes(t));
    }});
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
    container.innerHTML = '<div class="text-center py-12 text-gray-400">No products found matching your search.</div>';
    loadMoreEl.classList.add('hidden');
    return;
  }}

  container.innerHTML = showing.map(p => {{
    const price = p.p ? ('$' + p.p.toFixed(2)) : '';
    const stockBadge = p.a
      ? '<span class="stock-badge in-stock">In stock</span>'
      : '<span class="stock-badge out-stock">Out of stock</span>';
    const saleBadge = p.sale ? '<span class="stock-badge sale-badge">Sale</span>' : '';
    const catName = CATEGORY_NAMES[p.cat] || '';
    const catBadge = catName ? `<span class="cat-tag">${{catName}}</span>` : '';

    let changeBadge = '';
    if (p.ch === 'new') changeBadge = '<span class="stock-badge new-badge">New</span>';
    else if (p.ch === 'back') changeBadge = '<span class="stock-badge back-badge">Back in stock!</span>';
    else if (p.ch === 'gone') changeBadge = '<span class="stock-badge out-stock">Just sold out</span>';

    let priceInfo = price;
    if (p.ch === 'down' && p.pp) priceInfo = `<span class="price-down">${{price}}</span> <span class="text-xs text-gray-400 line-through">${{('$' + p.pp.toFixed(2))}}</span>`;
    else if (p.ch === 'up' && p.pp) priceInfo = `<span class="price-up">${{price}}</span> <span class="text-xs text-gray-400">was ${{('$' + p.pp.toFixed(2))}}</span>`;

    const utm = p.u ? (p.u.includes('?') ? '&' : '?') + 'utm_source=beestock&utm_medium=referral' : '';
    return `<a href="${{p.u}}${{utm}}" target="_blank" rel="noopener" class="product-row flex items-center gap-3 py-3 px-2 block">
      <div class="flex-1 min-w-0">
        <div class="font-medium text-sm">${{p.t}}</div>
        <div class="flex items-center gap-1.5 mt-0.5 flex-wrap">
          <span class="retailer-tag">${{p.n}}</span>
          ${{catBadge}} ${{stockBadge}} ${{saleBadge}} ${{changeBadge}}
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
categoryFilter.addEventListener('change', search);
changesOnly.addEventListener('change', search);
retailerSelect.addEventListener('change', search);
sortBy.addEventListener('change', search);

// Initial render
search();
</script>

</body>
</html>"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build beestock.com.au dashboard")
    parser.add_argument("data_dir", help="Path to bee-stock/ directory")
    parser.add_argument("output_dir", nargs="?", default="bee-dashboard-output", help="Where to write index.html")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist")
        sys.exit(1)

    print(f"Loading retailer data from {data_dir}...")
    products, retailers, category_counts = load_retailer_data(data_dir)
    print(f"Loaded {len(products)} products from {len(retailers)} retailers")

    for r in retailers:
        print(f"  {r['name']}: {r['count']} products ({r['in_stock']} in stock)")

    print("Category breakdown:")
    for slug, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {CATEGORY_NAMES.get(slug, slug)}: {count}")

    output_dir.mkdir(parents=True, exist_ok=True)
    html = build_html(products, retailers, category_counts)

    out_file = output_dir / "index.html"
    tmp_file = output_dir / "index.html.tmp"
    tmp_file.write_text(html)
    tmp_file.rename(out_file)
    print(f"Dashboard written to {out_file} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
