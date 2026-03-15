#!/usr/bin/env python3
"""
Build static species pages for SEO.

Generates one HTML page per fruit species showing:
- Current stock across all nurseries
- Price range
- Which nurseries carry it + shipping states
- Variety breakdown

Target keywords: "buy [species] tree online Australia", "[species] tree price Australia"

Usage:
    python3 build_species_pages.py /path/to/nursery-stock /path/to/output/
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

from shipping import SHIPPING_MAP

SPECIES_FILE = Path(__file__).parent / "fruit_species.json"

# Hardcoded non-plant keywords to skip (same as build-dashboard.py)
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


def load_species() -> list[dict]:
    if not SPECIES_FILE.exists():
        print(f"ERROR: {SPECIES_FILE} not found", file=sys.stderr)
        sys.exit(1)
    with open(SPECIES_FILE) as f:
        return json.load(f)


def build_species_lookup(species_list: list[dict]) -> dict:
    """Build a lowercase name → species entry lookup."""
    lookup = {}
    for s in species_list:
        key = s["common_name"].lower()
        lookup[key] = s
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = s
    return lookup


def match_title(title: str, lookup: dict) -> dict | None:
    """Match a product title against the species lookup."""
    title_lower = title.lower()
    # Try progressively shorter prefixes
    words = re.split(r'[\s\-–—]+', title_lower)
    for n in range(min(len(words), 5), 0, -1):
        candidate = " ".join(words[:n])
        if candidate in lookup:
            return lookup[candidate]
    return None


def load_nursery_products(data_dir: Path) -> list[dict]:
    """Load all products from latest.json files."""
    products = []
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        latest = nursery_dir / "latest.json"
        if not latest.exists():
            continue
        with open(latest) as f:
            data = json.load(f)
        nursery_key = nursery_dir.name
        nursery_name = data.get("nursery_name", nursery_key)
        for p in data.get("products", []):
            title = p.get("title", "")
            title_lower = title.lower()
            if any(kw in title_lower for kw in NON_PLANT_KEYWORDS):
                continue
            if title_lower in {"gift card", "gift voucher", "gift certificate"}:
                continue
            # Get best price
            variants = p.get("variants", [])
            min_price = p.get("min_price")
            if min_price is None and variants:
                avail_prices = [float(v["price"]) for v in variants if v.get("price") and v.get("available", True)]
                all_prices = [float(v["price"]) for v in variants if v.get("price")]
                min_price = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)
            elif min_price is None:
                min_price = p.get("price")

            available = p.get("any_available", p.get("available", False))
            products.append({
                "title": title,
                "url": p.get("url", ""),
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "price": round(float(min_price), 2) if min_price else None,
                "available": bool(available),
            })
    return products


def group_by_species(products: list[dict], lookup: dict) -> dict:
    """Group products by matched species slug."""
    by_species = {}
    for p in products:
        species = match_title(p["title"], lookup)
        if not species:
            continue
        slug = species["slug"]
        if slug not in by_species:
            by_species[slug] = {"species": species, "products": []}
        by_species[slug]["products"].append(p)
    return by_species


def build_species_page(species: dict, products: list[dict]) -> str:
    """Generate HTML for a single species page."""
    name = species["common_name"]
    latin = species["latin_name"]
    slug = species["slug"]
    region = species.get("region", "")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    in_stock = [p for p in products if p["available"]]
    out_of_stock = [p for p in products if not p["available"]]

    # Price stats (in-stock only)
    prices = [p["price"] for p in in_stock if p["price"]]
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None
    price_range = ""
    if min_price and max_price:
        if min_price == max_price:
            price_range = f"${min_price:.2f}"
        else:
            price_range = f"${min_price:.2f} – ${max_price:.2f}"

    # Which nurseries stock it
    nurseries_seen = {}
    for p in products:
        nk = p["nursery_key"]
        if nk not in nurseries_seen:
            nurseries_seen[nk] = {
                "name": p["nursery_name"],
                "in_stock": 0,
                "total": 0,
                "ships_to": SHIPPING_MAP.get(nk, []),
            }
        nurseries_seen[nk]["total"] += 1
        if p["available"]:
            nurseries_seen[nk]["in_stock"] += 1

    nursery_rows = ""
    for nk, n in sorted(nurseries_seen.items(), key=lambda x: -x[1]["in_stock"]):
        ships = ", ".join(n["ships_to"]) if n["ships_to"] else "Local only"
        in_s = n["in_stock"]
        total = n["total"]
        avail_text = f"{in_s} in stock" if in_s > 0 else "out of stock"
        avail_color = "text-green-700 font-semibold" if in_s > 0 else "text-gray-400"
        nursery_rows += f"""
      <tr class="border-b border-gray-100">
        <td class="py-2 pr-4 font-medium text-sm">{n['name']}</td>
        <td class="py-2 pr-4 text-sm {avail_color}">{avail_text} ({total} varieties)</td>
        <td class="py-2 text-xs text-gray-500">{ships}</td>
      </tr>"""

    # Product listing (in-stock first)
    product_rows = ""
    for p in sorted(products, key=lambda x: (not x["available"], x["price"] or 9999)):
        price_str = f"${p['price']:.2f}" if p["price"] else "—"
        avail_badge = (
            '<span class="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full">In stock</span>'
            if p["available"] else
            '<span class="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full">Out of stock</span>'
        )
        utm_url = p["url"] + ("&" if "?" in p["url"] else "?") + "utm_source=treestock&utm_medium=referral" if p["url"] else ""
        link = f'<a href="{utm_url}" target="_blank" rel="noopener" class="hover:text-green-700 hover:underline">{p["title"]}</a>' if p["url"] else p["title"]
        product_rows += f"""
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-2 pr-3 text-sm">{link}</td>
        <td class="py-2 pr-3 text-xs text-gray-500">{p['nursery_name']}</td>
        <td class="py-2 pr-3 text-sm font-medium">{price_str}</td>
        <td class="py-2">{avail_badge}</td>
      </tr>"""

    in_stock_count = len(in_stock)
    total_count = len(products)
    nursery_count = len(nurseries_seen)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Buy {name} Tree Online Australia — treestock.com.au</title>
<meta name="description" content="Find {name} ({latin}) trees for sale across {nursery_count} Australian nurseries. {in_stock_count} varieties in stock. Price from {price_range}. Compare prices and availability.">
<meta property="og:title" content="{name} Trees for Sale in Australia">
<meta property="og:description" content="{in_stock_count} {name} varieties in stock across {nursery_count} nurseries. From {price_range}.">
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
<script defer data-domain="treestock.com.au" src="https://data.bjnoel.com/js/script.outbound-links.js"></script>
<style>body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}</style>
</head>
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="max-w-3xl mx-auto px-4 py-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-green-800">
          <a href="/" class="hover:underline">treestock.com.au</a>
        </h1>
        <p class="text-sm text-gray-500">Australian Nursery Stock Tracker</p>
      </div>
      <div class="flex gap-2 text-sm">
        <a href="/" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 no-underline">Dashboard</a>
      </div>
    </div>
  </div>
</header>

<main class="max-w-3xl mx-auto px-4 py-6">

  <!-- Hero -->
  <div class="mb-6">
    <nav class="text-xs text-gray-400 mb-3">
      <a href="/" class="hover:underline">Home</a> ›
      <a href="/species/" class="hover:underline">Species</a> ›
      {name}
    </nav>
    <h2 class="text-3xl font-bold text-green-900 mb-1">{name} Trees</h2>
    <p class="text-gray-500 italic mb-3">{latin}{f' — {region}' if region else ''}</p>
    <div class="flex flex-wrap gap-3 text-sm">
      <span class="px-3 py-1 bg-green-50 text-green-800 rounded-full font-medium">{in_stock_count} varieties in stock</span>
      {f'<span class="px-3 py-1 bg-gray-50 text-gray-600 rounded-full">{price_range} AUD</span>' if price_range else ''}
      <span class="px-3 py-1 bg-gray-50 text-gray-600 rounded-full">{nursery_count} nurseries</span>
    </div>
  </div>

  <!-- Where to Buy -->
  <section class="mb-8">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Where to buy {name} trees in Australia</h3>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
            <th class="pb-2 pr-4">Nursery</th>
            <th class="pb-2 pr-4">Availability</th>
            <th class="pb-2">Ships to</th>
          </tr>
        </thead>
        <tbody>{nursery_rows}
        </tbody>
      </table>
    </div>
  </section>

  <!-- All Varieties -->
  <section class="mb-8">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">All {name} varieties ({total_count} listed)</h3>
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

  <!-- Notify Me / CTA -->
  {'<div class="p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm mb-6">' if in_stock_count == 0 else '<div class="p-4 bg-green-50 rounded-lg text-sm mb-6">'}
    {'<p class="font-semibold text-amber-800 mb-1">⚠️ ' + name + ' trees are currently out of stock</p><p class="text-gray-600 mb-3">Enter your email and we\'ll alert you when any ' + name + ' variety comes back in stock across our 8 monitored nurseries. <a href="/sample-digest.html" class="text-green-700 underline">See what you\'ll receive &rarr;</a></p>' if in_stock_count == 0 else '<p class="font-medium text-green-800 mb-1">Get restock alerts for ' + name + '</p><p class="text-gray-600 mb-3">We\'ll email you when new ' + name + ' varieties appear or prices drop at any of the 8 nurseries we monitor. <a href="/sample-digest.html" class="text-green-700 underline">See sample &rarr;</a></p>'}
    <form id="watchForm" class="flex flex-col sm:flex-row gap-2">
      <input type="email" id="watchEmail" placeholder="your@email.com" required
        class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 flex-1 max-w-xs">
      <button type="submit"
        class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium whitespace-nowrap">
        Notify me
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
        ? 'You\'re already set up for {name} alerts.'
        : '✓ Done! We\'ll email you when {name} trees come back in stock.';
      msg.className = 'mt-2 text-sm text-green-700';
      document.getElementById('watchForm').style.display = 'none';
    }})
    .catch(function() {{
      msg.textContent = 'Something went wrong — please try again.';
      msg.className = 'mt-2 text-sm text-red-600';
    }});
  }});
  </script>

</main>

<footer class="border-t border-gray-200 mt-8 py-6 text-center text-xs text-gray-400">
  <p>Data scraped daily from public nursery websites. Prices and availability may change. Updated {now}.</p>
  <p class="mt-1"><a href="/" class="underline">treestock.com.au</a> — Australian Nursery Stock Tracker</p>
</footer>

</body>
</html>"""


def build_species_index(species_data: list[dict]) -> str:
    """Build an index page listing all species with data."""
    rows = ""
    for entry in sorted(species_data, key=lambda x: x["in_stock_count"], reverse=True):
        s = entry["species"]
        in_s = entry["in_stock_count"]
        total = entry["total_count"]
        nurseries = entry["nursery_count"]
        price_range = entry["price_range"]
        rows += f"""
    <tr class="border-b border-gray-100 hover:bg-gray-50">
      <td class="py-3 pr-4">
        <a href="/species/{s['slug']}.html" class="font-medium text-green-700 hover:underline">{s['common_name']}</a>
        <div class="text-xs text-gray-400 italic">{s['latin_name']}</div>
      </td>
      <td class="py-3 pr-4 text-sm {'text-green-700 font-medium' if in_s > 0 else 'text-gray-400'}">{in_s} in stock</td>
      <td class="py-3 pr-4 text-sm text-gray-500">{total} varieties</td>
      <td class="py-3 pr-4 text-sm text-gray-500">{nurseries} nurseries</td>
      <td class="py-3 text-sm text-gray-600">{price_range}</td>
    </tr>"""

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Buy Fruit Trees Online Australia — treestock.com.au</title>
<meta name="description" content="Find fruit trees for sale across Australian nurseries. Track prices, availability, and shipping for 50+ species including mango, avocado, fig, lychee and more.">
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
<script defer data-domain="treestock.com.au" src="https://data.bjnoel.com/js/script.outbound-links.js"></script>
<style>body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}</style>
</head>
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="max-w-3xl mx-auto px-4 py-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-green-800"><a href="/">treestock.com.au</a></h1>
        <p class="text-sm text-gray-500">Australian Nursery Stock Tracker</p>
      </div>
      <a href="/" class="text-sm px-3 py-1 rounded border border-gray-300 hover:bg-gray-50">Dashboard</a>
    </div>
  </div>
</header>

<main class="max-w-3xl mx-auto px-4 py-6">
  <h2 class="text-2xl font-bold text-green-900 mb-2">Fruit Tree Species</h2>
  <p class="text-gray-500 text-sm mb-6">Browse by species to compare prices and availability across 8 Australian nurseries. Updated daily.</p>

  <div class="overflow-x-auto">
    <table class="w-full text-left">
      <thead>
        <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
          <th class="pb-2 pr-4">Species</th>
          <th class="pb-2 pr-4">In Stock</th>
          <th class="pb-2 pr-4">Varieties</th>
          <th class="pb-2 pr-4">Nurseries</th>
          <th class="pb-2">Price Range</th>
        </tr>
      </thead>
      <tbody>{rows}
      </tbody>
    </table>
  </div>
</main>

<footer class="border-t border-gray-200 mt-8 py-6 text-center text-xs text-gray-400">
  <p>Data scraped daily from public nursery websites. Updated {now}.</p>
  <p class="mt-1"><a href="/" class="underline">treestock.com.au</a></p>
</footer>
</body>
</html>"""


def main():
    if len(sys.argv) < 3:
        print("Usage: build_species_pages.py <data-dir> <output-dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    print("Loading species taxonomy...")
    species_list = load_species()
    lookup = build_species_lookup(species_list)
    print(f"  {len(species_list)} species, {len(lookup)} lookup entries")

    print("Loading nursery products...")
    products = load_nursery_products(data_dir)
    print(f"  {len(products)} products loaded")

    print("Grouping by species...")
    by_species = group_by_species(products, lookup)
    print(f"  {len(by_species)} species matched")

    species_dir = output_dir / "species"
    species_dir.mkdir(parents=True, exist_ok=True)

    index_data = []
    generated = 0
    for slug, entry in sorted(by_species.items()):
        species = entry["species"]
        prods = entry["products"]
        in_stock = [p for p in prods if p["available"]]
        prices = [p["price"] for p in in_stock if p["price"]]
        min_p = min(prices) if prices else None
        max_p = max(prices) if prices else None
        price_range = ""
        if min_p and max_p:
            price_range = f"${min_p:.2f}" if min_p == max_p else f"${min_p:.2f}–${max_p:.2f}"

        nurseries = {p["nursery_key"] for p in prods}
        index_data.append({
            "species": species,
            "in_stock_count": len(in_stock),
            "total_count": len(prods),
            "nursery_count": len(nurseries),
            "price_range": price_range,
        })

        html = build_species_page(species, prods)
        out_file = species_dir / f"{slug}.html"
        out_file.write_text(html)
        generated += 1
        if generated <= 5 or generated % 10 == 0:
            print(f"  {species['common_name']}: {len(in_stock)}/{len(prods)} in stock, {len(nurseries)} nurseries")

    # Build index
    index_html = build_species_index(index_data)
    index_file = species_dir / "index.html"
    index_file.write_text(index_html)

    print(f"\nGenerated {generated} species pages + index → {species_dir}")
    print(f"Index: {index_file}")


if __name__ == "__main__":
    main()
