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

from shipping import SHIPPING_MAP, NURSERY_NAMES
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer

SPECIES_FILE = Path(__file__).parent / "fruit_species.json"

NON_PLANT_KEYWORDS = [
    "fertilizer", "fertiliser", "potting mix", "soil mix", "seaweed solution",
    "fish emulsion", "worm castings", "secateurs", "pruning", "garden gloves",
    "plant label", "grafting tape", "grafting knife", "budding tape",
    "grow bag", "terracotta", "saucer", "pest spray", "insecticide", "fungicide",
    "neem oil", "insect killer", "insect control", "white oil", "weed killer",
    "herbicide", "concentrate spray", "shipping", "postage", "freight",
    "delivery charge", "gift card", "gift voucher", "gift certificate",
    "sharp shooter", "searles liquid", "ecofend",
]

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
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    products = []
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        snap = nursery_dir / f"{today}.json"
        fallback = nursery_dir / "latest.json"
        f = snap if snap.exists() else fallback
        if not f.exists():
            continue
        with open(f) as fp:
            data = json.load(fp)
        nursery_key = nursery_dir.name
        nursery_name = data.get("nursery_name") or NURSERY_NAMES.get(nursery_key, nursery_key)
        for p in data.get("products", []):
            title = p.get("title", "")
            if any(kw in title.lower() for kw in NON_PLANT_KEYWORDS):
                continue
            min_price = p.get("min_price")
            variants = p.get("variants", [])
            if min_price is None and variants:
                avail_prices = [float(v["price"]) for v in variants if v.get("price") and v.get("available", True)]
                all_prices = [float(v["price"]) for v in variants if v.get("price")]
                min_price = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)
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

    # Build nursery comparison table rows
    nursery_rows = ""
    for i, (nk, n) in enumerate(sorted_nurseries):
        if n["best_price"] and n["in_stock_count"] > 0:
            cheapest_badge = ' <span class="text-xs px-1.5 py-0.5 bg-green-100 text-green-800 rounded font-semibold">Cheapest</span>' if i == 0 else ""
            price_cell = f'${n["best_price"]:.2f}{cheapest_badge}'
            utm_url = n["best_url"] + ("&" if "?" in n["best_url"] else "?") + "utm_source=treestock&utm_medium=compare" if n["best_url"] else ""
            title_link = f'<a href="{utm_url}" target="_blank" rel="noopener" class="text-green-700 hover:underline text-xs">{n["best_title"]}</a>' if n["best_url"] else f'<span class="text-xs">{n["best_title"]}</span>'
            avail_text = f'<span class="text-green-700">{n["in_stock_count"]} in stock</span>'
        else:
            price_cell = '<span class="text-gray-400">—</span>'
            title_link = '<span class="text-gray-400 text-xs">Out of stock</span>'
            avail_text = '<span class="text-gray-400">out of stock</span>'

        ships = ", ".join(n["ships_to"]) if n["ships_to"] else "Local only"
        nursery_rows += f"""
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-3 pr-3 font-medium text-sm">{n['name']}</td>
        <td class="py-3 pr-3 text-sm font-semibold">{price_cell}</td>
        <td class="py-3 pr-3 text-sm">{title_link}</td>
        <td class="py-3 pr-3 text-sm">{avail_text}</td>
        <td class="py-3 text-xs text-gray-400">{ships}</td>
      </tr>"""

    # Build full product listing (in-stock, price-sorted)
    sorted_products = sorted(products, key=lambda x: (not x["available"], x["price"] or 9999, x["title"]))
    product_rows = ""
    for p in sorted_products:
        price_str = f"${p['price']:.2f}" if p["price"] else "—"
        avail_badge = (
            '<span class="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full">In stock</span>'
            if p["available"] else
            '<span class="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full">Out of stock</span>'
        )
        utm_url = p["url"] + ("&" if "?" in p["url"] else "?") + "utm_source=treestock&utm_medium=compare" if p["url"] else ""
        link = f'<a href="{utm_url}" target="_blank" rel="noopener" class="hover:text-green-700 hover:underline">{p["title"]}</a>' if p["url"] else p["title"]
        product_rows += f"""
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-2 pr-3 text-sm">{link}</td>
        <td class="py-2 pr-3 text-xs text-gray-500">{p['nursery_name']}</td>
        <td class="py-2 pr-3 text-sm font-medium">{price_str}</td>
        <td class="py-2">{avail_badge}</td>
      </tr>"""

    cheapest_summary = ""
    if sorted_nurseries and sorted_nurseries[0][1]["best_price"] and sorted_nurseries[0][1]["in_stock_count"] > 0:
        cheapest_nk, cheapest_n = sorted_nurseries[0]
        cheapest_summary = f'<p class="text-sm text-gray-600 mt-2">Cheapest in stock: <strong>{cheapest_n["name"]}</strong> from <strong>${cheapest_n["best_price"]:.2f}</strong>.</p>'

    head = render_head(
        title=f"{name} Tree Price Comparison Australia — treestock.com.au",
        description=f"Compare {name} ({latin}) tree prices across {total_nurseries} Australian nurseries. {len(in_stock)} varieties in stock. {'Prices from ' + price_range_str + ' AUD.' if price_range_str else ''} Updated daily.",
        og_title=f"{name} Tree Prices — Compare {total_nurseries} Australian Nurseries",
        og_description=f"{'From ' + price_range_str if price_range_str else str(len(in_stock)) + ' varieties in stock'} across {nursery_count} nurseries. Compare prices and availability at treestock.com.au",
    )
    header = render_header(subtitle="Australian Nursery Stock Tracker", active_path="/compare/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Compare Prices", "/compare/"), (name, "")])
    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-6">

  {breadcrumb}

  <!-- Hero -->
  <div class="mb-6">
    <h2 class="text-3xl font-bold text-green-900 mb-1">{name} Tree Prices</h2>
    <p class="text-gray-500 italic mb-1">{latin}</p>
    <p class="text-gray-600 text-sm mb-3">
      Comparing {name} tree prices across {total_nurseries} Australian online nurseries.
      Updated {now}.
    </p>
    <div class="flex flex-wrap gap-3 text-sm">
      {f'<span class="px-3 py-1 bg-green-50 text-green-800 rounded-full font-medium">{len(in_stock)} in stock</span>' if in_stock else '<span class="px-3 py-1 bg-amber-50 text-amber-700 rounded-full font-medium">Currently out of stock</span>'}
      {f'<span class="px-3 py-1 bg-gray-50 text-gray-600 rounded-full">{price_range_str} AUD</span>' if price_range_str else ''}
      <span class="px-3 py-1 bg-gray-50 text-gray-600 rounded-full">{total_nurseries} nurseries tracked</span>
    </div>
    {cheapest_summary}
  </div>

  <!-- Price Comparison Table -->
  <section class="mb-8">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Price comparison by nursery</h3>
    <p class="text-sm text-gray-500 mb-3">Showing lowest available price per nursery. <a href="/species/{slug}.html" class="text-green-700 underline">View full {name} species page →</a></p>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
            <th class="pb-2 pr-3">Nursery</th>
            <th class="pb-2 pr-3">Best price</th>
            <th class="pb-2 pr-3">Cheapest variety</th>
            <th class="pb-2 pr-3">Stock</th>
            <th class="pb-2">Ships to</th>
          </tr>
        </thead>
        <tbody>{nursery_rows}
        </tbody>
      </table>
    </div>
  </section>

  <!-- All Varieties (price sorted) -->
  <section class="mb-8">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">All {name} varieties — sorted by price</h3>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
            <th class="pb-2 pr-3">Variety</th>
            <th class="pb-2 pr-3">Nursery</th>
            <th class="pb-2 pr-3">Price</th>
            <th class="pb-2">Status</th>
          </tr>
        </thead>
        <tbody>{product_rows}
        </tbody>
      </table>
    </div>
  </section>

  <!-- Email alert CTA -->
  <div class="p-4 bg-green-50 rounded-lg text-sm mb-6">
    <p class="font-medium text-green-800 mb-1">Get price drop alerts for {name}</p>
    <p class="text-gray-600 mb-3">We monitor {total_nurseries} nurseries daily. Get emailed when {name} prices drop or new varieties appear. <a href="/sample-digest.html" class="text-green-700 underline">See sample &rarr;</a></p>
    <form id="watchForm" class="flex flex-col sm:flex-row gap-2">
      <input type="email" id="watchEmail" placeholder="your@email.com" required
        class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 flex-1 max-w-xs">
      <button type="submit"
        class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium whitespace-nowrap">
        Alert me
      </button>
    </form>
    <div id="watchMessage" class="mt-2 text-sm hidden"></div>
  </div>

  <script>
  document.getElementById('watchForm').addEventListener('submit', function(e) {{
    e.preventDefault();
    var email = document.getElementById('watchEmail').value.trim();
    var msg = document.getElementById('watchMessage');
    fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email: email, action: 'watch', species: '{slug}'}})
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{
      msg.textContent = d.message === 'Already watching'
        ? 'You\'re already set up for {name} price alerts.'
        : '✓ Done! We\'ll email you when {name} prices change.';
      msg.className = 'mt-2 text-sm text-green-700';
      msg.style.display = 'block';
      document.getElementById('watchForm').style.display = 'none';
    }})
    .catch(function() {{
      msg.textContent = 'Something went wrong — please try again.';
      msg.className = 'mt-2 text-sm text-red-600';
      msg.style.display = 'block';
    }});
  }});
  </script>

  <!-- SEO text -->
  <section class="mt-8 text-sm text-gray-500 border-t border-gray-100 pt-6">
    <h3 class="font-medium text-gray-700 mb-2">About this comparison</h3>
    <p>This page compares {name} tree prices across {total_nurseries} Australian online nurseries, updated daily by treestock.com.au. We track stock levels, prices, and availability so you can find the best deal without visiting each nursery website individually.</p>
    <p class="mt-2">Nurseries monitored: {", ".join(n["name"] for _, n in sorted_nurseries)}.</p>
    <p class="mt-2">Note: Prices shown are the lowest available variant per nursery at time of last scrape. Always verify current price and shipping costs on the nursery's website before ordering.</p>
  </section>

</main>

{footer}

</body>
</html>"""


def build_compare_index(entries: list[dict]) -> str:
    """Build /compare/index.html listing all compare pages."""
    rows = ""
    for e in sorted(entries, key=lambda x: -x["nursery_count"]):
        sp = e["species"]
        in_s = e["in_stock"]
        nurseries = e["nursery_count"]
        price = f'${e["min_price"]:.2f}' if e["min_price"] else "—"
        rows += f"""
    <tr class="border-b border-gray-100 hover:bg-gray-50">
      <td class="py-3 pr-4">
        <a href="/compare/{sp['slug']}-prices.html" class="font-medium text-green-800 hover:underline">{sp['common_name']}</a>
        <div class="text-xs text-gray-400 italic">{sp['latin_name']}</div>
      </td>
      <td class="py-3 pr-4 text-sm">{nurseries} nurseries</td>
      <td class="py-3 pr-4 text-sm">{in_s} in stock</td>
      <td class="py-3 text-sm font-medium">{price}</td>
    </tr>"""

    head = render_head(
        title="Fruit Tree Price Comparisons — Australian Nurseries — treestock.com.au",
        description=f"Compare fruit tree prices across Australian online nurseries. Find the cheapest mango, fig, avocado, lemon and more. Updated daily from {len(entries)} species.",
    )
    header = render_header(subtitle="Australian Nursery Stock Tracker", active_path="/compare/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Compare Prices", "")])
    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-6">
  {breadcrumb}

  <h2 class="text-3xl font-bold text-green-900 mb-2">Fruit Tree Price Comparisons</h2>
  <p class="text-gray-600 mb-6">
    Compare fruit tree prices across {len(entries)} species and multiple Australian nurseries.
    Find the cheapest price, check which nurseries ship to your state, and get alerts when prices drop.
    Updated daily.
  </p>

  <div class="overflow-x-auto">
    <table class="w-full text-left">
      <thead>
        <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
          <th class="pb-2 pr-4">Species</th>
          <th class="pb-2 pr-4">Coverage</th>
          <th class="pb-2 pr-4">In stock</th>
          <th class="pb-2">From</th>
        </tr>
      </thead>
      <tbody>{rows}
      </tbody>
    </table>
  </div>
</main>

{footer}

</body>
</html>"""


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
