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
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

from shipping import SHIPPING_MAP, LOCAL_DELIVERY, delivery_label
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer

SPECIES_FILE = Path(__file__).parent / "fruit_species.json"

# Match build_variety_pages.py so the slugs link to pages that actually exist.
_VARIETY_SIZE_WORDS = {
    'small', 'medium', 'large', 'xl', 'xxl', '75mm', '90mm',
    '140mm', '200mm', '250mm', '300mm', 'tube', 'pot', 'bag',
    'seedling', 'grafted', 'cutting', 'standard', 'dwarf',
    'bare root', 'bareroot', 'advanced', 'budget',
    'self-fertile', 'self fertile',
}


def _variety_slug(title: str) -> str | None:
    m = re.match(r'^(.+?)\s*[-–—]\s*(.+)$', title.strip())
    if not m:
        return None
    species, variety = m.group(1).strip(), m.group(2).strip()
    if variety.lower() in _VARIETY_SIZE_WORDS:
        return None
    if re.match(r'^[A-Za-z]\s*$', variety):
        return None
    if re.match(r'^\d', species):
        return None
    s = f"{species}-{variety}".lower()
    s = re.sub(r'[®™()]', '', s)
    s = re.sub(r'\s*[-–—]\s*', '-', s)
    s = re.sub(r'[^a-z0-9-]', '-', s)
    s = re.sub(r'-+', '-', s)
    return s.strip('-') or None

# Related species groups for cross-linking — people who buy one often compare others in the group.
# Ordered by popularity within each group (most popular first).
RELATED_GROUPS = {
    "tropical": ["mango", "lychee", "longan", "jackfruit", "banana", "dragon-fruit", "papaya", "rambutan", "starfruit"],
    "citrus": ["lemon", "lime", "orange", "mandarin", "grapefruit", "pomelo", "finger-lime"],
    "stone_fruit": ["peach", "nectarine", "apricot", "plum", "cherry"],
    "pome": ["apple", "pear"],
    "subtropical": ["avocado", "guava", "feijoa", "passionfruit", "loquat", "jaboticaba", "sapodilla", "custard-apple", "white-sapote", "black-sapote", "wax-jambu", "grumichama"],
    "exotic_tropical": ["jackfruit", "cacao", "rollinia", "rambutan", "wax-jambu", "miracle-fruit"],
    "berries": ["blueberry", "raspberry", "mulberry", "lilly-pilly", "grumichama", "jaboticaba"],
    "figs": ["fig", "mulberry"],
    "nuts": ["macadamia", "pecan"],
    "vines": ["grape", "passionfruit"],
    "mediterranean": ["olive", "fig", "pomegranate", "loquat", "grape"],
}

# Build reverse lookup: slug -> list of related slugs (from same group, excluding self)
def build_related_lookup() -> dict[str, list[str]]:
    related: dict[str, list[str]] = {}
    for group_members in RELATED_GROUPS.values():
        for slug in group_members:
            others = [s for s in group_members if s != slug]
            if slug not in related:
                related[slug] = []
            for other in others:
                if other not in related[slug]:
                    related[slug].append(other)
    return related

RELATED_LOOKUP = build_related_lookup()

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
    "ornamental",  # ornamental trees/shrubs are not fruit trees
    "asparagus",   # vegetable, not a fruit tree
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
            if re.search(r'\bseeds?\b', title_lower) and 'seedling' not in title_lower and 'seedless' not in title_lower:
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


def compute_rarity_scores(data_dir: Path, by_species: dict, lookup: dict) -> dict[str, dict]:
    """Compute rarity scores for each species using availability history.

    Score formula (0 = common, 100 = extremely rare):
      60% weight: nursery scarcity (fewer nurseries carry it = rarer)
      40% weight: availability scarcity (out-of-stock more often = rarer)

    Returns dict of {slug: {"score", "hard_to_find", "avg_availability", "nursery_count"}}
    """
    total_nurseries = len(SHIPPING_MAP)

    # Aggregate availability per species: list of (in_stock_days, total_days)
    species_avail: dict[str, list] = defaultdict(list)

    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        avail_file = nursery_dir / "availability.json"
        if not avail_file.exists():
            continue
        try:
            with open(avail_file) as f:
                avail_data = json.load(f)
        except Exception:
            continue

        for prod_data in avail_data.get("products", {}).values():
            title = prod_data.get("title", "")
            if not title:
                continue
            species = match_title(title, lookup)
            if not species:
                continue
            days = prod_data.get("days", {})
            if not days:
                continue
            in_stock_days = sum(1 for d in days.values() if d.get("a", False))
            species_avail[species["slug"]].append((in_stock_days, len(days)))

    scores = {}
    for slug, entry in by_species.items():
        prods = entry["products"]
        nursery_count = len({p["nursery_key"] for p in prods})

        # Average availability from historical data
        if species_avail.get(slug):
            total_in = sum(x[0] for x in species_avail[slug])
            total_days = sum(x[1] for x in species_avail[slug])
            avg_avail = total_in / total_days if total_days > 0 else 0.5
        else:
            # No history — fall back to current stock ratio
            in_stock = sum(1 for p in prods if p["available"])
            avg_avail = in_stock / len(prods) if prods else 0.5

        nursery_score = 1.0 - min(nursery_count / total_nurseries, 1.0)
        avail_score = 1.0 - avg_avail
        rarity_score = round((nursery_score * 0.6 + avail_score * 0.4) * 100, 1)

        scores[slug] = {
            "score": rarity_score,
            "hard_to_find": rarity_score >= 65,
            "avg_availability": round(avg_avail, 3),
            "nursery_count": nursery_count,
        }
    return scores


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


def build_species_description(species: dict) -> str:
    """Render the optional growing/description section for a species page."""
    description = species.get("description", "")
    if not description:
        return ""
    name = species["common_name"]
    paragraphs = [p.strip() for p in description.strip().split("\n\n") if p.strip()]
    paras_html = "\n".join(f'      <p class="text-gray-700 text-sm leading-relaxed mb-3">{p}</p>' for p in paragraphs)
    return f"""  <!-- Growing Guide -->
  <section class="mb-8">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Growing {name} in Australia</h3>
    <div class="prose prose-sm max-w-none">
{paras_html}
    </div>
  </section>"""


def build_related_species_html(slug: str, slug_to_name: dict[str, str], max_links: int = 5) -> str:
    """Render a 'Related species' section with links to up to max_links related species that have data."""
    related_slugs = RELATED_LOOKUP.get(slug, [])
    # Only link species we actually have pages for (i.e. in slug_to_name)
    available = [(s, slug_to_name[s]) for s in related_slugs if s in slug_to_name][:max_links]
    if not available:
        return ""
    links = "".join(
        f'<a href="/species/{s}.html" class="inline-block text-sm text-green-700 hover:underline mr-4 mb-1">{name} &rarr;</a>'
        for s, name in available
    )
    return f"""  <!-- Related species -->
  <section class="mb-6">
    <h3 class="text-base font-semibold text-gray-700 mb-2">Related species</h3>
    <div class="flex flex-wrap gap-y-1">{links}</div>
  </section>
"""


STATE_SLUGS = {
    "WA": "western-australia",
    "QLD": "queensland",
    "NSW": "new-south-wales",
    "VIC": "victoria",
}
STATE_FULL_NAMES = {
    "WA": "Western Australia",
    "QLD": "Queensland",
    "NSW": "New South Wales",
    "VIC": "Victoria",
}
MIN_COMBO_PRODUCTS = 3


def compute_state_links(species_slug: str, products: list[dict]) -> dict[str, str]:
    """Return state -> URL for states with enough in-stock products for this species."""
    links = {}
    for state, state_slug in STATE_SLUGS.items():
        state_nurseries = {k for k, v in SHIPPING_MAP.items() if state in v}
        count = sum(
            1 for p in products
            if p["available"] and p["nursery_key"] in state_nurseries
        )
        if count >= MIN_COMBO_PRODUCTS:
            links[state] = f"/buy-{species_slug}-trees-{state_slug}.html"
    return links


def build_species_page(species: dict, products: list[dict], slug_to_name: dict[str, str] | None = None,
                       rarity: dict | None = None) -> str:
    """Generate HTML for a single species page."""
    name = species["common_name"]
    latin = species["latin_name"]
    slug = species["slug"]
    region = species.get("region", "")
    if slug_to_name is None:
        slug_to_name = {}
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
        local_lbl = delivery_label(nk)
        ships = local_lbl if local_lbl else (", ".join(n["ships_to"]) if n["ships_to"] else "Local only")
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

    # Product listing (in-stock first). Title links to our internal variety
    # page when one exists (so users can see all nurseries + sign up for
    # variety alerts); nursery column links direct to the nursery's product
    # page for buy-now intent.
    product_rows = ""
    for p in sorted(products, key=lambda x: (not x["available"], x["price"] or 9999)):
        price_str = f"${p['price']:.2f}" if p["price"] else "—"
        avail_badge = (
            '<span class="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full">In stock</span>'
            if p["available"] else
            '<span class="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full">Out of stock</span>'
        )
        nursery_url = p["url"] + ("&" if "?" in p["url"] else "?") + "utm_source=treestock&utm_medium=referral" if p["url"] else ""
        v_slug = _variety_slug(p["title"])
        if v_slug:
            title_link = f'<a href="/variety/{v_slug}.html" class="hover:text-green-700 hover:underline">{p["title"]}</a>'
        elif nursery_url:
            title_link = f'<a href="{nursery_url}" target="_blank" rel="noopener" class="hover:text-green-700 hover:underline">{p["title"]}</a>'
        else:
            title_link = p["title"]
        nursery_cell = (
            f'<a href="{nursery_url}" target="_blank" rel="noopener" class="hover:text-green-700 hover:underline">{p["nursery_name"]}</a>'
            if nursery_url else p["nursery_name"]
        )
        product_rows += f"""
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-2 pr-3 text-sm">{title_link}</td>
        <td class="py-2 pr-3 text-xs text-gray-500">{nursery_cell}</td>
        <td class="py-2 pr-3 text-sm font-medium">{price_str}</td>
        <td class="py-2">{avail_badge}</td>
      </tr>"""

    in_stock_count = len(in_stock)
    total_count = len(products)
    nursery_count = len(nurseries_seen)
    total_nurseries = len(SHIPPING_MAP)

    # Rarity badge
    rarity_badge_html = ""
    if rarity and rarity.get("hard_to_find"):
        rarity_badge_html = (
            '<span class="px-3 py-1 bg-amber-50 text-amber-800 rounded-full font-medium '
            'border border-amber-200 text-sm" title="Found at fewer nurseries and often out of stock">'
            '&#11088; Hard to find</span>'
        )

    # State combo links (buy-[species]-trees-[state].html)
    state_links = compute_state_links(slug, products)
    state_links_html = ""
    if state_links:
        link_items = "".join(
            f'<a href="{url}" class="inline-block text-sm text-green-700 hover:underline mr-4 mb-1">'
            f'Buy {name} trees in {STATE_FULL_NAMES[state]} &rarr;</a>'
            for state, url in state_links.items()
        )
        state_links_html = f"""
  <!-- State combo links -->
  <section class="mb-6">
    <h3 class="text-base font-semibold text-gray-700 mb-2">Buy {name} trees by state</h3>
    <div class="flex flex-wrap gap-y-1">{link_items}</div>
  </section>
"""

    related_species_html = build_related_species_html(slug, slug_to_name)

    head = render_head(
        title=f"Buy {name} Tree Online Australia — treestock.com.au",
        description=f"Find {name} ({latin}) trees for sale across {nursery_count} Australian nurseries. {in_stock_count} varieties in stock. Price from {price_range}. Compare prices and availability.",
        og_title=f"{name} Trees for Sale in Australia",
        og_description=f"{in_stock_count} {name} varieties in stock across {nursery_count} nurseries. From {price_range}.",
    )
    header = render_header(active_path="/species/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Species", "/species/"), (name, "")])
    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-6">

  <!-- Hero -->
  <div class="mb-6">
    {breadcrumb}
    <h2 class="text-3xl font-bold text-green-900 mb-1">{name} Trees</h2>
    <p class="text-gray-500 italic mb-3">{latin}{f' — {region}' if region else ''}</p>
    <div class="flex flex-wrap gap-3 text-sm">
      <span class="px-3 py-1 bg-green-50 text-green-800 rounded-full font-medium">{in_stock_count} varieties in stock</span>
      {f'<span class="px-3 py-1 bg-gray-50 text-gray-600 rounded-full">{price_range} AUD</span>' if price_range else ''}
      <span class="px-3 py-1 bg-gray-50 text-gray-600 rounded-full">{nursery_count} nurseries</span>
      {rarity_badge_html}
    </div>
  </div>

  {f"""<!-- Out of stock: watch CTA shown prominently above results -->
  <div id="watchBox" class="p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm mb-6">
    <p class="font-semibold text-amber-800 mb-1">&#9888; {name} trees are currently out of stock</p>
    <p class="text-gray-600 mb-3">We monitor {total_nurseries} nurseries daily. Enter your email and we'll alert you the moment any {name} variety comes back in stock.</p>
    <form id="watchForm" class="flex flex-col sm:flex-row gap-2 flex-wrap">
      <input type="email" id="watchEmail" placeholder="your@email.com" required
        class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 flex-1 max-w-xs">
      <select id="watchState" class="px-2 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
        <option value="ALL">All states</option>
        <option value="NSW">NSW</option><option value="VIC">VIC</option>
        <option value="QLD">QLD</option><option value="WA">WA</option>
        <option value="SA">SA</option><option value="TAS">TAS</option>
        <option value="NT">NT</option><option value="ACT">ACT</option>
      </select>
      <button type="submit"
        class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium whitespace-nowrap">
        Alert me when back in stock
      </button>
    </form>
    <div id="watchMessage" class="mt-2 text-sm hidden"></div>
  </div>""" if in_stock_count == 0 else ''}

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

  {build_species_description(species)}

  {state_links_html}

  {related_species_html}

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

  {f"""<!-- Variety-watch suggestion CTA (shown below results when stock exists) -->
  <div class="p-4 bg-green-50 rounded-lg text-sm mb-6">
    <p class="font-medium text-green-800 mb-1">Want alerts for a specific {name} variety?</p>
    <p class="text-gray-600">Click a variety name above to open its page on treestock.com.au, where you can compare nurseries and sign up for restock alerts on that exact cultivar. (The nursery column links straight to the nursery if you want to buy now.)</p>
  </div>""" if in_stock_count > 0 else ''}

</main>

{footer}

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
        rarity = entry.get("rarity", {})
        hard_to_find = rarity.get("hard_to_find", False)
        rarity_cell = (
            '<span class="text-xs px-2 py-0.5 bg-amber-50 text-amber-700 rounded-full border border-amber-200 whitespace-nowrap">'
            '&#11088; Hard to find</span>'
            if hard_to_find else ""
        )
        rows += f"""
    <tr class="border-b border-gray-100 hover:bg-gray-50">
      <td class="py-3 pr-4">
        <a href="/species/{s['slug']}.html" class="font-medium text-green-700 hover:underline">{s['common_name']}</a>
        <div class="text-xs text-gray-400 italic">{s['latin_name']}</div>
      </td>
      <td class="py-3 pr-4 text-sm {'text-green-700 font-medium' if in_s > 0 else 'text-gray-400'}">{in_s} in stock</td>
      <td class="py-3 pr-4 text-sm text-gray-500">{total} varieties</td>
      <td class="py-3 pr-4 text-sm text-gray-500">{nurseries} nurseries</td>
      <td class="py-3 pr-4 text-sm text-gray-600">{price_range}</td>
      <td class="py-3">{rarity_cell}</td>
    </tr>"""

    head = render_head(
        title="Buy Fruit Trees Online Australia — treestock.com.au",
        description="Find fruit trees for sale across Australian nurseries. Track prices, availability, and shipping for 50+ species including mango, avocado, fig, lychee and more.",
    )
    header = render_header(active_path="/species/")
    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-6">
  <h2 class="text-2xl font-bold text-green-900 mb-2">Fruit Tree Species</h2>
  <p class="text-gray-500 text-sm mb-6">Browse by species to compare prices and availability across Australian nurseries. Updated daily.</p>

  <div class="overflow-x-auto">
    <table class="w-full text-left">
      <thead>
        <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
          <th class="pb-2 pr-4">Species</th>
          <th class="pb-2 pr-4">In Stock</th>
          <th class="pb-2 pr-4">Varieties</th>
          <th class="pb-2 pr-4">Nurseries</th>
          <th class="pb-2 pr-4">Price Range</th>
          <th class="pb-2">Rarity</th>
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

    print("Computing rarity scores...")
    rarity_scores = compute_rarity_scores(data_dir, by_species, lookup)
    hard_to_find_count = sum(1 for r in rarity_scores.values() if r["hard_to_find"])
    print(f"  {hard_to_find_count} species marked 'Hard to find'")

    # Save rarity scores for use by other build scripts (e.g. build_rare_finds.py)
    rarity_scores_file = data_dir.parent / "rarity_scores.json"
    with open(rarity_scores_file, "w") as f:
        json.dump(rarity_scores, f, indent=2)
    print(f"  Saved rarity scores to {rarity_scores_file}")

    # Build slug->name map for species that have product data (used for related links)
    slug_to_name = {
        slug: entry["species"]["common_name"]
        for slug, entry in by_species.items()
    }

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
        rarity = rarity_scores.get(slug, {})
        index_data.append({
            "species": species,
            "in_stock_count": len(in_stock),
            "total_count": len(prods),
            "nursery_count": len(nurseries),
            "price_range": price_range,
            "rarity": rarity,
        })

        html = build_species_page(species, prods, slug_to_name, rarity=rarity)
        out_file = species_dir / f"{slug}.html"
        out_file.write_text(html)
        generated += 1
        if generated <= 5 or generated % 10 == 0:
            htf = " [Hard to find]" if rarity.get("hard_to_find") else ""
            print(f"  {species['common_name']}: {len(in_stock)}/{len(prods)} in stock, {len(nurseries)} nurseries{htf}")

    # Build index
    index_html = build_species_index(index_data)
    index_file = species_dir / "index.html"
    index_file.write_text(index_html)

    print(f"\nGenerated {generated} species pages + index → {species_dir}")
    print(f"Index: {index_file}")


if __name__ == "__main__":
    main()
