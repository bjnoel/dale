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

from shipping import SHIPPING_MAP, NURSERY_NAMES

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
    "ausnurseries": "https://www.ausnurseries.com.au",
    "fruit-tree-cottage": "https://www.fruittreecottage.com.au",
}

NON_PLANT_KEYWORDS = [
    "fertilizer", "fertiliser", "potting mix", "soil mix", "seaweed",
    "fish emulsion", "worm castings", "secateurs", "pruning", "gloves",
    "plant label", "grafting tape", "grafting knife", "grow bag",
    "pest spray", "insecticide", "fungicide", "neem oil", "white oil",
    "weed killer", "herbicide", "gift card", "gift voucher", "shipping",
    "postage", "freight", "delivery", "sharp shooter", "searles",
    "richgro", "poss-off", "eco-oil", "eco oil", "seasol", "powerfeed",
    "yates", "osmocote", "dynamic lifter",
]


def slugify(title: str) -> str:
    """Convert 'Avocado - Hass' to 'avocado-hass'."""
    s = title.lower()
    s = re.sub(r'[®™()]', '', s)
    s = re.sub(r'\s*[-–—]\s*', '-', s)
    s = re.sub(r'[^a-z0-9-]', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-')


def parse_cultivar(title: str) -> tuple[str, str] | None:
    """
    Parse 'Species - Variety' into (species, variety).
    Returns None if not a cultivar-named product.
    """
    # Must contain a separator
    m = re.match(r'^(.+?)\s*[-–—]\s*(.+)$', title.strip())
    if not m:
        return None
    species = m.group(1).strip()
    variety = m.group(2).strip()
    # Skip if variety is a size/pot indicator
    size_words = ['small', 'medium', 'large', 'xl', 'xxl', '75mm', '90mm',
                  '140mm', '200mm', '250mm', '300mm', 'tube', 'pot', 'bag',
                  'seedling', 'grafted', 'cutting', 'standard', 'dwarf',
                  'bare root', 'bareroot', 'advanced', 'budget',
                  'self-fertile', 'self fertile']
    if variety.lower() in size_words:
        return None
    # Skip if variety is just a letter (e.g. "Avocado - A" for pollination type)
    if re.match(r'^[A-Za-z]\s*$', variety):
        return None
    # Skip if species starts with a digit (e.g. "1L Richgro 'Poss")
    if re.match(r'^\d', species):
        return None
    return (species, variety)


def load_all_products(data_dir: Path) -> list[dict]:
    """Load all products from today's or latest snapshot."""
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
        nursery_name = NURSERY_NAMES.get(nursery_key, nursery_key)
        ships_wa = "WA" in SHIPPING_MAP.get(nursery_key, [])

        raw_products = data.get("products", [])
        for p in raw_products:
            title = p.get("title", "").strip()
            # Skip non-plant items
            if any(kw in title.lower() for kw in NON_PLANT_KEYWORDS):
                continue
            products.append({
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "title": title,
                "url": p.get("url", ""),
                "price": p.get("min_price") or 0,
                "available": p.get("any_available", False),
                "ships_wa": ships_wa,
                "ships_states": SHIPPING_MAP.get(nursery_key, []),
            })
    return products


def group_by_cultivar(products: list[dict]) -> dict:
    """
    Group products by normalized cultivar name.
    Key: (species_slug, variety_slug) → normalized title and list of products.
    """
    groups = defaultdict(lambda: {"title": "", "species": "", "variety": "", "products": []})

    for p in products:
        parsed = parse_cultivar(p["title"])
        if not parsed:
            continue
        species, variety = parsed
        # Normalize key
        key = slugify(f"{species}-{variety}")
        if not groups[key]["title"]:
            groups[key]["title"] = p["title"]
            groups[key]["species"] = species
            groups[key]["variety"] = variety
        groups[key]["products"].append(p)

    return groups


def build_variety_page(slug: str, data: dict) -> str:
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

    wa_options = [p for p in in_stock if p["ships_wa"]]
    cheapest = in_stock[0] if in_stock else None
    cheapest_wa = wa_options[0] if wa_options else None

    # Build product rows
    rows = ""
    for p in in_stock + out_stock:
        price_str = f"${p['price']:.2f}" if p["price"] else "—"
        avail_badge = (
            '<span class="text-green-700 font-medium text-sm">✓ In stock</span>'
            if p["available"]
            else '<span class="text-red-400 text-sm">Out of stock</span>'
        )
        wa_badge = (
            '<span class="text-blue-600 text-xs">Ships to WA</span>'
            if p["ships_wa"]
            else '<span class="text-gray-400 text-xs">No WA shipping</span>'
        )
        states = ", ".join(p["ships_states"]) if p["ships_states"] else "—"
        nursery_url = NURSERY_URLS.get(p["nursery_key"], "#")
        product_link = p["url"] or nursery_url
        rows += f"""
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-3 pr-4">
          <a href="{product_link}" target="_blank" rel="nofollow noopener"
             class="font-medium text-green-800 hover:underline">{p["nursery_name"]}</a>
          <div class="text-xs text-gray-400">{wa_badge}</div>
        </td>
        <td class="py-3 pr-4 font-semibold text-gray-900">{price_str}</td>
        <td class="py-3 pr-4">{avail_badge}</td>
        <td class="py-3 text-xs text-gray-400">{states}</td>
      </tr>"""

    # Summary callouts
    summary_parts = []
    if cheapest:
        summary_parts.append(
            f'<span class="font-medium">Cheapest:</span> '
            f'{cheapest["nursery_name"]} at ${cheapest["price"]:.2f}'
        )
    if cheapest_wa and cheapest_wa != cheapest:
        summary_parts.append(
            f'<span class="font-medium">Best WA option:</span> '
            f'{cheapest_wa["nursery_name"]} at ${cheapest_wa["price"]:.2f}'
        )
    elif cheapest_wa:
        summary_parts.append(
            f'<span class="font-medium">Ships to WA:</span> Yes — '
            f'{cheapest_wa["nursery_name"]}'
        )
    else:
        summary_parts.append(
            '<span class="font-medium text-amber-700">WA shipping:</span> '
            'None of the nurseries currently ship this variety to WA'
        )

    summary_html = " &nbsp;·&nbsp; ".join(summary_parts) if summary_parts else ""

    in_stock_count = len(in_stock)
    nursery_count = len(set(p["nursery_key"] for p in products))
    species_slug = slugify(species)

    meta_desc = (
        f"Find {title} trees for sale in Australia. "
        f"Compare prices across {nursery_count} nurseries. "
        f"{in_stock_count} nurseries currently in stock. Updated daily."
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Buy {title} Trees in Australia — Prices & Availability — treestock.com.au</title>
<meta name="description" content="{meta_desc}">
<link rel="canonical" href="https://treestock.com.au/variety/{slug}.html">
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
        <a href="/" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50">Dashboard</a>
        <a href="/species/{species_slug}.html" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50">All {species}</a>
      </div>
    </div>
  </div>
</header>

<main class="max-w-3xl mx-auto px-4 py-6">
  <nav class="text-xs text-gray-400 mb-4">
    <a href="/" class="hover:underline">Home</a> ›
    <a href="/variety/" class="hover:underline">Varieties</a> ›
    <a href="/species/{species_slug}.html" class="hover:underline">{species}</a> ›
    {variety}
  </nav>

  <h2 class="text-3xl font-bold text-green-900 mb-1">Buy {title} Trees in Australia</h2>
  <p class="text-gray-500 text-sm mb-4">Updated {today} · {nursery_count} nurseries tracked · {in_stock_count} in stock</p>

  {"<div class='bg-green-50 border border-green-200 rounded-lg px-4 py-3 mb-6 text-sm text-green-900'>" + summary_html + "</div>" if summary_html else ""}

  <div class="overflow-x-auto mb-8">
    <table class="w-full text-left">
      <thead>
        <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
          <th class="pb-2 pr-4">Nursery</th>
          <th class="pb-2 pr-4">Price</th>
          <th class="pb-2 pr-4">Status</th>
          <th class="pb-2">Ships to</th>
        </tr>
      </thead>
      <tbody>{rows}
      </tbody>
    </table>
  </div>

  <!-- Email signup -->
  <div class="bg-gray-50 border border-gray-200 rounded-lg p-5 mb-8">
    <h3 class="font-semibold text-gray-900 mb-1">Get daily stock updates</h3>
    <p class="text-sm text-gray-600 mb-3">
      Subscibe to the treestock.com.au daily digest — stock changes, price drops,
      and new arrivals across all nurseries.
    </p>
    <form id="subscribeForm" class="flex gap-2 flex-wrap">
      <input type="email" id="subEmail" placeholder="your@email.com" required
        class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 flex-1 max-w-xs">
      <button type="submit"
        class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium whitespace-nowrap">
        Subscribe free
      </button>
    </form>
    <div id="subMsg" class="mt-2 text-sm hidden"></div>
  </div>

  <!-- SEO text -->
  <section class="text-sm text-gray-500 border-t border-gray-100 pt-6">
    <h3 class="font-medium text-gray-700 mb-2">About {title}</h3>
    <p>
      This page tracks <strong>{title}</strong> tree availability and prices across {nursery_count} Australian
      online nurseries, updated daily. Data is scraped directly from nursery websites so you can compare
      without visiting each one individually.
    </p>
    <p class="mt-2">
      Looking for other {species} varieties?
      <a href="/species/{species_slug}.html" class="underline text-green-700">See all {species} options →</a>
    </p>
    <p class="mt-2 text-xs text-gray-400">
      Prices shown are the lowest available variant at time of last scrape. Always verify current pricing
      and shipping costs on the nursery's website before ordering.
    </p>
  </section>

</main>

<footer class="border-t border-gray-200 mt-8 py-6 text-center text-xs text-gray-400">
  <p>Data scraped daily from public nursery websites. Prices and availability may change. Updated {now}.</p>
  <p class="mt-1"><a href="/" class="underline">treestock.com.au</a> — Australian Nursery Stock Tracker</p>
</footer>

<script>
document.getElementById('subscribeForm').addEventListener('submit', function(e) {{
  e.preventDefault();
  var email = document.getElementById('subEmail').value.trim();
  var msg = document.getElementById('subMsg');
  fetch('/api/subscribe', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{email: email, action: 'subscribe'}})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(d) {{
    msg.textContent = d.message === 'Already subscribed'
      ? 'You\\'re already subscribed!'
      : '✓ Subscribed! You\\'ll get daily stock updates.';
    msg.className = 'mt-2 text-sm text-green-700';
    msg.style.display = 'block';
    document.getElementById('subscribeForm').style.display = 'none';
  }})
  .catch(function() {{
    msg.textContent = 'Something went wrong — please try again.';
    msg.className = 'mt-2 text-sm text-red-600';
    msg.style.display = 'block';
  }});
}});
</script>

</body>
</html>"""


def build_variety_index(entries: list[dict]) -> str:
    """Build /variety/index.html listing all cultivar pages."""
    # Group by species for easier browsing
    by_species = defaultdict(list)
    for e in entries:
        by_species[e["species"]].append(e)

    species_sections = ""
    for sp in sorted(by_species.keys()):
        varieties = sorted(by_species[sp], key=lambda x: x["variety"])
        sp_slug = slugify(sp)
        rows = ""
        for v in varieties:
            in_s = v["in_stock"]
            n_count = v["nursery_count"]
            price = f'${v["min_price"]:.2f}' if v["min_price"] else "—"
            wa_note = " 🚛 WA" if v["wa_available"] else ""
            rows += f"""
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-2 pr-4">
          <a href="/variety/{v['slug']}.html" class="text-green-800 hover:underline">{v['variety']}</a>
          {wa_note}
        </td>
        <td class="py-2 pr-4 text-sm text-gray-600">{n_count} nurseries</td>
        <td class="py-2 pr-4 text-sm">{in_s} in stock</td>
        <td class="py-2 text-sm font-medium">{price}</td>
      </tr>"""

        in_stock_count = sum(v["in_stock"] for v in varieties)
        species_sections += f"""
  <section class="mb-8" id="{sp_slug}">
    <h3 class="text-lg font-semibold text-green-900 mb-1">
      <a href="/species/{sp_slug}.html" class="hover:underline">{sp}</a>
      <span class="text-sm font-normal text-gray-500 ml-2">{len(varieties)} varieties · {in_stock_count} in stock</span>
    </h3>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-400 uppercase">
            <th class="pb-1 pr-4">Variety</th>
            <th class="pb-1 pr-4">Coverage</th>
            <th class="pb-1 pr-4">Stock</th>
            <th class="pb-1">From</th>
          </tr>
        </thead>
        <tbody>{rows}
        </tbody>
      </table>
    </div>
  </section>"""

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_varieties = len(entries)
    total_in_stock = sum(e["in_stock"] for e in entries)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fruit Tree Varieties for Sale in Australia — treestock.com.au</title>
<meta name="description" content="Browse {total_varieties} named fruit tree varieties available from Australian nurseries. Find Hass avocado, R2E2 mango, Grimal jaboticaba, Brown Turkey fig and more. Compare prices and check WA shipping. Updated daily.">
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
        <a href="/" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50">Dashboard</a>
      </div>
    </div>
  </div>
</header>

<main class="max-w-3xl mx-auto px-4 py-6">
  <nav class="text-xs text-gray-400 mb-4">
    <a href="/" class="hover:underline">Home</a> › Varieties
  </nav>

  <h2 class="text-3xl font-bold text-green-900 mb-2">Fruit Tree Varieties for Sale in Australia</h2>
  <p class="text-gray-600 mb-6">
    Browse {total_varieties} named cultivars tracked across {len(by_species)} species.
    {total_in_stock} currently in stock across all Australian nurseries. Updated daily.
  </p>

  {species_sections}

</main>

<footer class="border-t border-gray-200 mt-8 py-6 text-center text-xs text-gray-400">
  <p>Data scraped daily from public nursery websites. Updated {now}.</p>
  <p class="mt-1"><a href="/" class="underline">treestock.com.au</a> — Australian Nursery Stock Tracker</p>
</footer>

</body>
</html>"""


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <data_dir> <output_dir>", file=sys.stderr)
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    variety_dir = output_dir / "variety"
    variety_dir.mkdir(parents=True, exist_ok=True)

    products = load_all_products(data_dir)
    print(f"Loaded {len(products)} products")

    groups = group_by_cultivar(products)
    print(f"Found {len(groups)} distinct cultivar names")

    index_entries = []
    pages_written = 0

    for slug, data in groups.items():
        prods = data["products"]
        in_stock = [p for p in prods if p["available"] and p["price"]]
        all_nurseries = set(p["nursery_key"] for p in prods)
        wa_available = any(p["ships_wa"] for p in in_stock)
        min_price = min((p["price"] for p in in_stock), default=None)

        html = build_variety_page(slug, data)
        out_path = variety_dir / f"{slug}.html"
        with open(out_path, "w") as f:
            f.write(html)

        index_entries.append({
            "slug": slug,
            "title": data["title"],
            "species": data["species"],
            "variety": data["variety"],
            "nursery_count": len(all_nurseries),
            "in_stock": len(in_stock),
            "min_price": min_price,
            "wa_available": wa_available,
        })
        pages_written += 1

    # Write index
    index_html = build_variety_index(index_entries)
    with open(variety_dir / "index.html", "w") as f:
        f.write(index_html)

    print(f"Written {pages_written} variety pages + index to {variety_dir}/")

    # Print summary stats
    multi = sum(1 for e in index_entries if e["nursery_count"] > 1)
    in_stock_count = sum(1 for e in index_entries if e["in_stock"] > 0)
    wa_count = sum(1 for e in index_entries if e["wa_available"])
    print(f"  Multi-nursery: {multi}, In-stock varieties: {in_stock_count}, WA-shippable: {wa_count}")


if __name__ == "__main__":
    main()
