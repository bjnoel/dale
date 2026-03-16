#!/usr/bin/env python3
"""
Build state-based location pages for fruit tree availability.

Generates /buy-fruit-trees-[state].html for WA, QLD, NSW, VIC.
Shows nurseries that ship to each state, with in-stock product lists.

Products are filtered to fruit/edible species only using fruit_species.json.
Non-plant items (supplies, ornamentals) are excluded.

Usage:
    python3 build_location_pages.py /path/to/nursery-stock /path/to/output/
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from shipping import SHIPPING_MAP, NURSERY_NAMES

SPECIES_FILE = Path(__file__).parent / "fruit_species.json"

# Non-plant keywords to exclude regardless of species match
NON_PLANT_KEYWORDS = [
    "fertilizer", "fertiliser", "potting mix", "soil mix", "seaweed solution",
    "fish emulsion", "worm castings", "secateurs", "pruning", "garden gloves",
    "plant label", "grafting tape", "grafting knife", "budding tape",
    "grow bag", "saucer", "pest spray", "insecticide", "fungicide",
    "neem oil", "insect killer", "insect control", "white oil", "weed killer",
    "herbicide", "concentrate spray", "shipping", "postage", "freight",
    "delivery charge", "gift card", "gift voucher", "gift certificate",
    "irrigation", "connector", "tree guard", "rubber hook", "biochar",
    "banana bunch cover", "bonsai bag", "tree tube", "tree stake",
    "orchard kit", "gropod", "searles", "ecofend", "sharp shooter",
    # Ornamental/non-fruit species Daleys sells
    "eucalyptus", "melaleuca", "callistemon", "banksia", "sheoak",
    "cordyline", "brachychiton", "lomandra", "allocasuarina",
    "acacia", "wattle", "bottlebrush", "kurrajong", "red bean",
    "white beech", "white cedar", "ivory curl", "flame tree",
    "swamp turpentine", "forest mat rush", "brown tamarind",
    "swamp paperbark", "river red gum", "lemon scented gum",
    "narrow-leaved ironbark", "flooded gum", "blackbutt",
    "resource book", "catalogue",
]

# States to generate pages for
STATES = ["WA", "QLD", "NSW", "VIC"]

# State display names
STATE_NAMES = {
    "WA": "Western Australia",
    "QLD": "Queensland",
    "NSW": "New South Wales",
    "VIC": "Victoria",
}

# State-specific intro text
STATE_INTROS = {
    "WA": (
        "Finding fruit trees online that ship to WA is surprisingly hard "
        "most nurseries are east coast only. These are the ones that do."
    ),
    "QLD": (
        "Queensland's warm climate suits a wide range of fruit trees. "
        "These nurseries ship to QLD, including tropical and subtropical varieties."
    ),
    "NSW": (
        "NSW has a huge range of climates, from subtropical to cool highlands. "
        "These nurseries ship to New South Wales."
    ),
    "VIC": (
        "Victoria's cool climate is ideal for stone fruit, apples, and pears. "
        "These nurseries ship to Victoria."
    ),
}

# State-specific info box (None = no box)
STATE_INFO_BOX = {
    "WA": (
        "WA has strict quarantine rules — only a handful of nurseries can legally "
        "ship fruit trees here. We track them all so you don't have to."
    ),
    "QLD": None,
    "NSW": None,
    "VIC": None,
}

# Per-state, per-nursery special notes
STATE_NURSERY_NOTES = {
    "WA": {
        "daleys": "seasonal window + extra fee",
        "heritage-fruit-trees": "VIC, ships to WA in winter (May-Sep)",
        "guildford": "Perth metro only",
        "fruit-salad-trees": "ships 1st Tuesday/month",
        "diggers": "ships nationwide",
        "primal-fruits": "WA-based",
        "all-season-plants-wa": "pickup only, Ellenbrook",
    },
    "QLD": {
        "diggers": "ships nationwide",
        "fruit-salad-trees": "ships nationwide",
        "daleys": "ships nationwide",
        "ross-creek": "QLD-based",
        "ladybird": "QLD-based",
        "fruitopia": "QLD-based",
    },
    "NSW": {
        "diggers": "ships nationwide",
        "fruit-salad-trees": "ships nationwide",
        "daleys": "NSW-based",
        "ausnurseries": "NSW-based",
        "fruit-tree-cottage": "QLD-based",
    },
    "VIC": {
        "diggers": "VIC-based, ships nationwide",
        "fruit-salad-trees": "ships nationwide",
        "daleys": "ships nationwide",
        "heritage-fruit-trees": "VIC-based",
        "fruit-tree-cottage": "ships nationwide",
    },
}

# Cross-state links per state
CROSS_LINKS = {
    "WA": [("QLD", "Buy in QLD"), ("NSW", "Buy in NSW"), ("VIC", "Buy in VIC")],
    "QLD": [("WA", "Buy in WA"), ("NSW", "Buy in NSW"), ("VIC", "Buy in VIC")],
    "NSW": [("WA", "Buy in WA"), ("QLD", "Buy in QLD"), ("VIC", "Buy in VIC")],
    "VIC": [("WA", "Buy in WA"), ("QLD", "Buy in QLD"), ("NSW", "Buy in NSW")],
}

# Manual entries for local pickup nurseries not in the scraper
# Shown as an additional section on state pages
LOCAL_NURSERIES = {
    "WA": [
        {
            "name": "Leeming Fruit Trees",
            "address": "4a Westmorland Drive, Leeming, WA 6149",
            "hours": "Call 0413 062 856 to confirm hours",
            "phone": "0413 062 856",
            "facebook": "https://www.facebook.com/Leeming.Fruit.Trees/",
            "specialty": "Rare tropical fruit trees: lychee, rambutan, mangosteen, durian, abiu, wampee, custard apple, and more.",
            "note": "Pickup only, no online shop",
        },
    ],
}


def load_species() -> set[str]:
    """Load all known fruit species names and synonyms."""
    with open(SPECIES_FILE) as f:
        species_list = json.load(f)
    names = set()
    for s in species_list:
        names.add(s["common_name"].lower())
        for syn in s.get("synonyms", []):
            if syn:
                names.add(syn.lower())
    return names


def build_species_lookup(species_list: list[dict]) -> dict:
    """Map species names/synonyms to species dicts."""
    lookup = {}
    for s in species_list:
        lookup[s["common_name"].lower()] = s
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = s
    return lookup


def match_title_to_species(title: str, lookup: dict) -> dict | None:
    """Try to match a product title to a known fruit species."""
    t = title.lower()
    words = re.split(r"[\s\-\u2013\u2014]+", t)
    for n in range(min(len(words), 5), 0, -1):
        candidate = " ".join(words[:n])
        if candidate in lookup:
            return lookup[candidate]
    return None


def is_non_plant(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in NON_PLANT_KEYWORDS)


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
        in_stock_count = sum(1 for p in data.get("products", []) if p.get("any_available"))
        total_count = len(data.get("products", []))
        for p in data.get("products", []):
            title = p.get("title", "")
            min_price = p.get("min_price")
            if min_price is None:
                variants = p.get("variants", [])
                prices = [float(v["price"]) for v in variants if v.get("price")]
                min_price = min(prices) if prices else None
            available = bool(p.get("any_available", False))
            url = p.get("url", "")
            products.append({
                "title": title,
                "url": url,
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "nursery_in_stock": in_stock_count,
                "nursery_total": total_count,
                "price": round(float(min_price), 2) if min_price else None,
                "available": available,
            })
    return products


def get_nursery_stats(products: list[dict], state: str) -> list[dict]:
    """Get per-nursery stats for nurseries that ship to this state."""
    nursery_products = defaultdict(list)
    for p in products:
        nursery_products[p["nursery_key"]].append(p)

    stats = []
    for key, ships_to in SHIPPING_MAP.items():
        if state not in ships_to:
            continue
        prods = nursery_products.get(key, [])
        in_stock = sum(1 for p in prods if p.get("available"))
        total = len(prods)
        if total == 0:
            continue
        note = STATE_NURSERY_NOTES.get(state, {}).get(key, "")
        stats.append({
            "key": key,
            "name": NURSERY_NAMES.get(key, key),
            "in_stock": in_stock,
            "total": total,
            "note": note,
        })

    # Sort by in-stock count descending
    stats.sort(key=lambda x: x["in_stock"], reverse=True)
    return stats


def build_page(state: str, products: list[dict], species_lookup: dict, today_str: str) -> str:
    state_name = STATE_NAMES[state]
    state_abbr = state
    intro = STATE_INTROS[state]
    info_box = STATE_INFO_BOX.get(state)

    # Nurseries that ship to this state
    nursery_stats = get_nursery_stats(products, state)
    total_in_stock = sum(n["in_stock"] for n in nursery_stats)
    nursery_count = len(nursery_stats)

    # Products for this state: nurseries that ship here, fruit/edible only, no non-plants
    state_nurseries = {n["key"] for n in nursery_stats}
    state_products = []
    for p in products:
        if p["nursery_key"] not in state_nurseries:
            continue
        if not p["available"]:
            continue
        if is_non_plant(p["title"]):
            continue
        # Must match a known fruit species
        if not match_title_to_species(p["title"], species_lookup):
            continue
        state_products.append(p)

    # Sort by price descending (interesting/rare plants tend to cost more)
    state_products.sort(key=lambda x: x["price"] or 0, reverse=True)

    shown = state_products[:60]
    shown_count = len(shown)

    # Cross-state links
    cross_links = CROSS_LINKS[state]
    cross_html = " &middot; ".join(
        f'<a href="/buy-fruit-trees-{s.lower()}.html" class="text-green-700 hover:underline">{label}</a>'
        for s, label in cross_links
    )

    # Nursery rows
    nursery_rows = ""
    for n in nursery_stats:
        note_html = (
            f'<span class="text-xs text-amber-600 ml-1">({n["note"]})</span>'
            if n["note"] else ""
        )
        nursery_rows += f"""        <tr class="border-b border-gray-100">
          <td class="py-2 pr-4 font-medium text-sm"><a href="/nursery/{n['key']}.html" class="text-green-700 hover:underline">{n['name']}</a></td>
          <td class="py-2 pr-4 text-sm text-green-700 font-semibold">{n['in_stock']} in stock</td>
          <td class="py-2 text-sm text-gray-500">{n['total']} varieties tracked{note_html}</td>
        </tr>\n"""

    # Product rows
    product_rows = ""
    for p in shown:
        price_str = f"${p['price']:.2f}" if p["price"] else "N/A"
        product_rows += f"""        <tr class="border-b border-gray-100">
          <td class="py-2 pr-4 text-sm"><a href="{p['url']}" class="hover:text-green-700" target="_blank" rel="noopener">{p['title']}</a></td>
          <td class="py-2 pr-4 text-sm font-semibold text-green-700">{price_str}</td>
          <td class="py-2 text-sm text-gray-500">{p['nursery_name']}</td>
        </tr>\n"""

    info_box_html = ""
    if info_box:
        info_box_html = f"""  <div class="bg-green-50 border-green-200 text-green-900 border rounded-lg p-4 mb-8">
    <p class="text-sm">{info_box}</p>
  </div>\n\n"""

    # Local pickup nurseries section (manual, non-scraped)
    local_nurseries = LOCAL_NURSERIES.get(state, [])
    local_section_html = ""
    if local_nurseries:
        local_rows = ""
        for n in local_nurseries:
            contact_parts = []
            if n.get("phone"):
                contact_parts.append(f'<a href="tel:{n["phone"]}" class="hover:text-green-700">{n["phone"]}</a>')
            if n.get("facebook"):
                contact_parts.append(f'<a href="{n["facebook"]}" class="text-green-700 hover:underline" target="_blank" rel="noopener">Facebook</a>')
            contact_html = " &middot; ".join(contact_parts) if contact_parts else ""
            local_rows += f"""        <tr class="border-b border-gray-100">
          <td class="py-2 pr-4 text-sm">
            <div class="font-medium">{n['name']}</div>
            <div class="text-xs text-gray-500">{n['address']}</div>
            <div class="text-xs text-gray-500">{n['hours']}</div>
          </td>
          <td class="py-2 pr-4 text-xs text-gray-600">{n['specialty']}</td>
          <td class="py-2 text-xs">{contact_html}</td>
        </tr>\n"""
        local_section_html = f"""
  <!-- Local pickup nurseries -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold mb-1">Local nurseries ({state_abbr} pickup only)</h2>
    <p class="text-sm text-gray-500 mb-3">These nurseries don't ship online but are worth visiting in person.</p>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase tracking-wide">
            <th class="pb-2 pr-4">Nursery</th>
            <th class="pb-2 pr-4">Speciality</th>
            <th class="pb-2">Contact</th>
          </tr>
        </thead>
        <tbody>
{local_rows}        </tbody>
      </table>
    </div>
  </section>
"""

    # Build canonical date string
    try:
        dt = datetime.strptime(today_str, "%Y-%m-%d")
        date_display = dt.strftime("%-d %B %Y")
    except Exception:
        date_display = today_str

    slug = state.lower()
    other_states = [s for s in STATES if s != state]
    other_slugs_html = " &middot; ".join(
        f'<a href="/buy-fruit-trees-{s.lower()}.html" class="hover:text-green-700">'
        f'Buy in {STATE_NAMES[s]}</a>'
        for s in other_states
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Buy Fruit Trees Online — {state_name} | treestock.com.au</title>
<meta name="description" content="Find fruit trees for sale online that ship to {state_name}. {total_in_stock} varieties in stock across {nursery_count} nurseries, updated daily. Compare prices and check availability.">
<meta property="og:title" content="Fruit Trees for Sale Online in {state_name}">
<meta property="og:description" content="Find fruit trees for sale online that ship to {state_name}. {total_in_stock} varieties in stock across {nursery_count} nurseries, updated daily.">
<meta property="og:url" content="https://treestock.com.au/buy-fruit-trees-{slug}.html">
<meta name="robots" content="index, follow">
<link rel="canonical" href="https://treestock.com.au/buy-fruit-trees-{slug}.html">
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
<script defer data-domain="treestock.com.au" src="https://data.bjnoel.com/js/script.outbound-links.js"></script>
<style>body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}</style>
</head>
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="max-w-3xl mx-auto px-4 py-4">
    <div class="flex items-center justify-between">
      <a href="/" class="text-lg font-bold text-green-700">treestock.com.au</a>
      <nav class="text-sm text-gray-600 space-x-4 hidden sm:block">
        <a href="/species/" class="hover:text-green-700">Browse species</a>
        <a href="/nursery/" class="hover:text-green-700">Nurseries</a>
        <a href="/digest.html" class="hover:text-green-700">Daily digest</a>
      </nav>
    </div>
  </div>
</header>

<main class="max-w-3xl mx-auto px-4 py-8">

  <nav class="text-xs text-gray-500 mb-6">
    <a href="/" class="hover:text-green-700">Home</a>
    <span class="mx-2">&rsaquo;</span>
    <span>Fruit trees for sale &mdash; {state_name}</span>
  </nav>

  <h1 class="text-2xl font-bold mb-2">Buy Fruit Trees Online in {state_name}</h1>
  <p class="text-gray-600 mb-1">Updated {date_display} &middot; {total_in_stock} varieties in stock across {nursery_count} nurseries</p>
  <p class="text-gray-600 text-sm mb-6">{intro}</p>

{info_box_html}  <!-- Nursery summary -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold mb-3">Nurseries that ship to {state_name}</h2>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase tracking-wide">
            <th class="pb-2 pr-4">Nursery</th>
            <th class="pb-2 pr-4">In stock</th>
            <th class="pb-2">Notes</th>
          </tr>
        </thead>
        <tbody>
{nursery_rows}        </tbody>
      </table>
    </div>
    <p class="text-xs text-gray-500 mt-2">
      Stock counts update daily after our morning scrape. <a href="/" class="text-green-700 underline">Filter by nursery on the dashboard</a>
    </p>
  </section>

  <!-- In-stock products -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold mb-3">In stock now, ships to {state_abbr} (top {shown_count} by price)</h2>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase tracking-wide">
            <th class="pb-2 pr-4">Variety</th>
            <th class="pb-2 pr-4">Price</th>
            <th class="pb-2">Nursery</th>
          </tr>
        </thead>
        <tbody>
{product_rows}        </tbody>
      </table>
    </div>
    <p class="text-xs text-gray-500 mt-2">Showing {shown_count} of {total_in_stock} in-stock varieties.
      <a href="/" class="text-green-700 underline">See all {total_in_stock} on the dashboard</a>
    </p>
  </section>

{local_section_html}  <!-- Subscribe CTA -->
  <section class="bg-green-50 border border-green-200 rounded-lg p-6 mb-8">
    <h2 class="text-lg font-semibold text-green-900 mb-2">Get daily stock alerts for {state_name}</h2>
    <p class="text-sm text-green-800 mb-4">Free daily email when rare varieties come back in stock or prices change. Unsubscribe anytime.</p>
    <form action="https://treestock.com.au/api/subscribe" method="post" class="flex flex-col sm:flex-row gap-2">
      <input type="email" name="email" placeholder="your@email.com" required
        class="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-green-500">
      <input type="hidden" name="state" value="{state_abbr}">
      <button type="submit"
        class="bg-green-700 text-white px-4 py-2 rounded text-sm font-medium hover:bg-green-800">
        Get alerts
      </button>
    </form>
  </section>

  <!-- Cross-state links -->
  <section class="mb-8">
    <p class="text-sm text-gray-600">Also available: {cross_html}</p>
  </section>

</main>

<footer class="border-t border-gray-200 mt-8 py-6">
  <div class="max-w-3xl mx-auto px-4">
    <p class="text-xs text-gray-500">
      <a href="/" class="hover:text-green-700">treestock.com.au</a> &middot;
      Australian fruit tree stock tracker &middot;
      Data updated daily &middot;
      <a href="/nursery/" class="hover:text-green-700">All nurseries</a> &middot;
      <a href="/species/" class="hover:text-green-700">Browse by species</a>
    </p>
  </div>
</footer>

</body>
</html>
"""


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} /path/to/nursery-stock /path/to/output/")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print("Loading species...")
    with open(SPECIES_FILE) as f:
        species_list = json.load(f)
    species_lookup = build_species_lookup(species_list)
    print(f"  {len(species_lookup)} species/synonyms loaded")

    print("Loading products...")
    products = load_all_products(data_dir)
    print(f"  {len(products)} products loaded")

    for state in STATES:
        print(f"\nBuilding {state} page...")
        html = build_page(state, products, species_lookup, today)
        out_file = output_dir / f"buy-fruit-trees-{state.lower()}.html"
        out_file.write_text(html)

        # Count for summary
        state_nurseries = {
            k for k, v in SHIPPING_MAP.items() if state in v
        }
        in_stock = sum(
            1 for p in products
            if p["nursery_key"] in state_nurseries
            and p["available"]
            and not is_non_plant(p["title"])
            and match_title_to_species(p["title"], species_lookup)
        )
        print(f"  Written: {out_file} ({in_stock} matched in-stock products)")

    print("\nDone.")


if __name__ == "__main__":
    main()
