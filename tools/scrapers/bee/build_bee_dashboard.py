#!/usr/bin/env python3
"""
Build a static HTML dashboard for beestock.com.au from bee-stock JSON data.
Generates a single self-contained index.html with embedded data.

Usage:
    python3 build_bee_dashboard.py /path/to/data/bee-stock /path/to/output/
"""

import html as html_mod
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from bee_retailers import SHIPPING_MAP, RETAILER_NAMES
from bee_categories import categorise_product, CATEGORIES, CATEGORY_NAMES
from beestock_layout import render_head, render_header, render_footer, SITE_NAME, LOGO_SVG

# Matches "8 frame", "10 frame", "8-frame", "10-frame" etc. in product titles
_FRAME_SIZE_RE = re.compile(r'\b(8|10)\s*-?\s*frame\b', re.IGNORECASE)


def extract_frame_size(title: str) -> str | None:
    """Return '8' or '10' if the title specifies a frame size, else None."""
    m = _FRAME_SIZE_RE.search(title)
    if m:
        return m.group(1)  # '8' or '10'
    return None


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

            # Decode HTML entities (Magento scrapers may return &amp;amp;amp; etc.)
            prev_title = None
            while prev_title != title:
                prev_title = title
                title = html_mod.unescape(title)
            title = title.strip()

            # Skip garbage titles: empty, whitespace-only, or special-char-only (e.g. '*', '**')
            if len(re.sub(r'[^a-zA-Z0-9]', '', title)) < 3:
                continue

            # Skip gift cards
            title_lower = title.lower()
            if any(kw in title_lower for kw in ("gift card", "gift voucher", "gift certificate")):
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

            max_price = p.get("max_price")
            if max_price is None and variants:
                avail_prices = [float(v.get("price", 0)) for v in variants if v.get("price") and v.get("available", True)]
                all_prices = [float(v.get("price", 0)) for v in variants if v.get("price")]
                max_price = max(avail_prices) if avail_prices else (max(all_prices) if all_prices else None)

            frame_size = extract_frame_size(title)
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
            if frame_size:
                product_data["fs"] = frame_size

            if max_price and min_price and max_price > min_price + 0.01:
                product_data["mp"] = round(max_price, 2)

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

    # Build category pill strip (in-stock only, sorted by count)
    in_stock_by_cat: dict[str, int] = {}
    for p in products:
        if p.get("a"):
            cat = p.get("cat", "other")
            in_stock_by_cat[cat] = in_stock_by_cat.get(cat, 0) + 1

    cat_pills_html = ""
    for slug, count in sorted(in_stock_by_cat.items(), key=lambda x: -x[1]):
        if count < 3:
            continue
        name = CATEGORY_NAMES.get(slug, "Other")
        if name == "Other":
            continue
        cat_pills_html += f'<button class="cat-pill" data-cat="{slug}">{name} <span class="count">{count}</span></button>\n'

    extra_style = """\
  .stock-badge { font-size: 0.7rem; padding: 2px 6px; border-radius: 9999px; }
  .restrict-badge { background: #fee2e2; color: #991b1b; font-size: 0.65rem; }
  .sale-badge { background: #fee2e2; color: #991b1b; }
  .new-badge { background: #dbeafe; color: #1e40af; }
  .back-badge { background: #d1fae5; color: #065f46; font-weight: 600; }
  .frame-badge { background: #fef3c7; color: #78350f; font-size: 0.65rem; padding: 2px 6px; border-radius: 9999px; }
  .price-down { color: #059669; font-weight: 600; }
  .price-up { color: #dc2626; }
  .in-stock { background: #d1fae5; color: #065f46; }
  .out-stock { background: #f3f4f6; color: #6b7280; }
  #results { min-height: 200px; }
  .product-row { border-bottom: 1px solid #f3f4f6; }
  .product-row:hover { background: #f9fafb; }
  .retailer-tag { font-size: 0.65rem; padding: 1px 5px; border-radius: 4px; background: #fef3c7; color: #92400e; cursor: pointer; }
  .retailer-tag:hover { background: #fde68a; }
  .cat-tag { font-size: 0.65rem; padding: 1px 5px; border-radius: 4px; background: #e0e7ff; color: #3730a3; }
  .cat-pill { flex-shrink: 0; display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px; border: 1px solid #e5e7eb; border-radius: 9999px; font-size: 0.8125rem; color: #374151; white-space: nowrap; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
  .cat-pill:hover { border-color: #f59e0b; background: #fef3c7; color: #92400e; }
  .cat-pill.active { border-color: #d97706; background: #fef3c7; color: #92400e; font-weight: 600; }
  .cat-pill .count { color: #d97706; font-weight: 600; font-size: 0.7rem; }
  .cat-pill.active .count { color: #b45309; }
  #cat-pills { display: flex; gap: 8px; flex-wrap: wrap; max-height: 34px; overflow: hidden; padding-bottom: 4px; transition: max-height 0.2s ease; }
  #cat-pills.expanded { max-height: 500px; }
  .toggle-pills-btn { background: none; border: none; color: #d97706; font-size: 0.75rem; cursor: pointer; padding: 4px 0 0; }
  .toggle-pills-btn:hover { text-decoration: underline; }"""

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
    <!-- Category pills -->
    <div id="cat-pills">
      {cat_pills_html}
    </div>
    <button id="toggleCatPills" class="toggle-pills-btn" style="display:none">Show all &#9662;</button>
    <div class="flex flex-wrap gap-2 items-center text-sm">
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" id="inStockOnly" checked class="rounded"> In stock only
      </label>
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" id="changesOnly" class="rounded"> Changes only
      </label>
      <label class="flex items-center gap-1 cursor-pointer">
        <input type="checkbox" id="saleOnly" class="rounded"> Sale only
      </label>
      <select id="categoryFilter" class="border border-gray-300 rounded px-2 py-1 text-sm">
        <option value="">All categories</option>
        {cat_options_html}
      </select>
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

  <!-- Subscribe CTA (below results) -->
  <div class="mt-6 mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
    <p class="font-semibold text-yellow-900 mb-1">Get daily price alerts</p>
    <p class="text-sm text-yellow-800 mb-3">Be the first to know when prices drop or items restock. Free, daily email digest.</p>
    <form id="subscribeForm" class="flex gap-2 flex-wrap">
      <input type="email" id="subEmail" placeholder="your@email.com" required
        class="flex-1 min-w-0 px-3 py-2 border border-yellow-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-yellow-500">
      <button type="submit"
        class="px-4 py-2 bg-yellow-700 text-white rounded-lg text-sm font-medium hover:bg-yellow-800 whitespace-nowrap">
        Subscribe
      </button>
    </form>
    <p id="subMsg" class="text-sm mt-2 hidden"></p>
  </div>

  <!-- About section (below subscribe) -->
  <div class="mb-4 p-4 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-700">
    <p class="font-semibold text-gray-800 mb-1">About beestock.com.au</p>
    <p>Track prices and availability across Australian beekeeping supply retailers every day. Find the best prices on extractors, hives, protective gear, varroa treatments, and more.</p>
    <p class="mt-2"><a href="/digest.html" class="text-yellow-800 underline font-medium">See today's changes &rarr;</a></p>
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
const saleOnly = document.getElementById('saleOnly');
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
  if (saleOnly.checked) results = results.filter(p => p.sale);
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
    // Relevance sort (no query): in-stock first, then items with changes, then alphabetic
    const relevanceScore = p => {{
      if (!p.a) return 3;
      if (p.ch === 'new' || p.ch === 'back') return 0;
      if (p.ch === 'down') return 1;
      return 2;
    }};
    results.sort((a, b) => {{
      const diff = relevanceScore(a) - relevanceScore(b);
      if (diff !== 0) return diff;
      return a.t.localeCompare(b.t);
    }});
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
    let price = p.p ? ('$' + p.p.toFixed(2)) : '';
    if (p.mp && p.p && p.mp > p.p * 4) price = 'from $' + p.p.toFixed(2);
    else if (p.mp && p.p && p.mp > p.p + 0.01) price = '$' + p.p.toFixed(2) + ' - $' + p.mp.toFixed(2);
    const stockBadge = p.a
      ? '<span class="stock-badge in-stock">In stock</span>'
      : '<span class="stock-badge out-stock">Out of stock</span>';
    const saleBadge = p.sale ? '<span class="stock-badge sale-badge">Sale</span>' : '';
    const catName = CATEGORY_NAMES[p.cat] || '';
    const catBadge = catName ? `<span class="cat-tag">${{catName}}</span>` : '';
    const frameBadge = p.fs ? `<span class="frame-badge">${{p.fs}}-frame</span>` : '';

    let changeBadge = '';
    if (p.ch === 'new') changeBadge = '<span class="stock-badge new-badge">New</span>';
    else if (p.ch === 'back') changeBadge = '<span class="stock-badge back-badge">Back in stock!</span>';
    else if (p.ch === 'gone') changeBadge = '<span class="stock-badge out-stock">Just sold out</span>';

    const minPrice = p.p ? ('$' + p.p.toFixed(2)) : '';
    let priceInfo = price;
    if (p.ch === 'down' && p.pp) priceInfo = `<span class="price-down">${{minPrice}}</span> <span class="text-xs text-gray-400 line-through">${{('$' + p.pp.toFixed(2))}}</span>`;
    else if (p.ch === 'up' && p.pp) priceInfo = `<span class="price-up">${{minPrice}}</span> <span class="text-xs text-gray-400">was ${{('$' + p.pp.toFixed(2))}}</span>`;

    const utm = p.u ? (p.u.includes('?') ? '&' : '?') + 'utm_source=beestock&utm_medium=referral' : '';
    return `<a href="${{p.u}}${{utm}}" target="_blank" rel="noopener" class="product-row flex items-center gap-3 py-3 px-2 block">
      <div class="flex-1 min-w-0">
        <div class="font-medium text-sm">${{p.t}}</div>
        <div class="flex items-center gap-1.5 mt-0.5 flex-wrap">
          <span class="retailer-tag" data-nk="${{p.nk}}">${{p.n}}</span>
          ${{catBadge}} ${{frameBadge}} ${{stockBadge}} ${{saleBadge}} ${{changeBadge}}
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
  // Clear active pill when typing manually
  document.querySelectorAll('.cat-pill.active').forEach(p => p.classList.remove('active'));
  categoryFilter.value = '';
  search();
}});
inStockOnly.addEventListener('change', search);
categoryFilter.addEventListener('change', function() {{
  // Clear active pill when dropdown changes
  document.querySelectorAll('.cat-pill.active').forEach(p => p.classList.remove('active'));
  search();
}});
changesOnly.addEventListener('change', search);
saleOnly.addEventListener('change', search);
retailerSelect.addEventListener('change', search);
sortBy.addEventListener('change', search);

// Category pill clicks
document.querySelectorAll('.cat-pill[data-cat]').forEach(function(pill) {{
  pill.addEventListener('click', function(e) {{
    e.preventDefault();
    const cat = this.getAttribute('data-cat');
    const isActive = this.classList.contains('active');
    document.querySelectorAll('.cat-pill.active').forEach(p => p.classList.remove('active'));
    if (isActive) {{
      categoryFilter.value = '';
    }} else {{
      this.classList.add('active');
      categoryFilter.value = cat;
    }}
    search();
  }});
}});

// Show/hide category pill toggle button based on overflow
(function() {{
  const strip = document.getElementById('cat-pills');
  const btn = document.getElementById('toggleCatPills');
  if (strip && btn && strip.scrollHeight > strip.clientHeight) {{
    btn.style.display = 'inline';
    btn.addEventListener('click', function() {{
      strip.classList.toggle('expanded');
      this.innerHTML = strip.classList.contains('expanded') ? 'Show less &#9652;' : 'Show all &#9662;';
    }});
  }}
}})();

// Retailer tag click: filter by retailer
document.getElementById('results').addEventListener('click', function(e) {{
  const tag = e.target.closest('.retailer-tag[data-nk]');
  if (tag) {{
    e.preventDefault();
    e.stopPropagation();
    retailerSelect.value = tag.getAttribute('data-nk');
    search();
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }}
}});

// Initial render
search();

// Subscribe form
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
        : "Subscribed! Check your inbox for a confirmation.";
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
