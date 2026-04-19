#!/usr/bin/env python3
"""
Build nursery profile pages for treestock.com.au.
Generates /nursery/<key>.html and /nursery/index.html.

Usage:
    python3 build_nursery_pages.py /path/to/data/nursery-stock /path/to/dashboard/
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from shipping import SHIPPING_MAP, NURSERY_NAMES, LOCAL_DELIVERY, delivery_label, restriction_warning
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer

SPECIES_FILE = Path(__file__).parent / "fruit_species.json"

# Per-nursery metadata: website URL, tags, description
NURSERY_META = {
    "daleys": {
        "url": "https://www.daleysfruit.com.au",
        "tags": ["tropical fruit", "subtropical fruit", "rare varieties"],
        "description": "Daleys Fruit Trees is one of Australia's largest online fruit tree nurseries, based in Kyogle NSW. They carry an enormous range including tropical, subtropical, and rare varieties, and ship to WA seasonally with special quarantine permits.",
    },
    "ross-creek": {
        "url": "https://www.rosscreektropicals.com.au",
        "tags": ["tropical fruit", "exotic varieties", "QLD grown"],
        "description": "Ross Creek Tropicals specialises in tropical and subtropical fruit trees grown in Queensland's ideal climate. They carry rare and hard-to-find tropical varieties not commonly available elsewhere in Australia.",
    },
    "ladybird": {
        "url": "https://www.ladybirdnursery.com.au",
        "tags": ["fruit trees", "edibles", "subtropical"],
        "description": "Ladybird Nursery is a Queensland-based nursery with a large range of edible plants and fruit trees. They carry both common and unusual varieties with a focus on plants suited to Queensland's subtropical climate.",
    },
    "fruitopia": {
        "url": "https://www.fruitopianursery.com.au",
        "tags": ["tropical fruit", "subtropical fruit", "rare varieties"],
        "description": "Fruitopia Nursery is a specialist fruit tree nursery in Queensland carrying a wide range of tropical and subtropical fruit trees, with a particular focus on rare and exotic varieties.",
    },
    "primal-fruits": {
        "url": "https://www.primalfruits.com.au",
        "tags": ["tropical fruit", "WA grown", "pickup available"],
        "description": "Primal Fruits Perth is a Western Australian nursery specialising in tropical and subtropical fruit trees suited to WA's climate. Local pickup available in Parkwood, Perth.",
    },
    "guildford": {
        "url": "https://www.guildfordgardencentre.com.au",
        "tags": ["fruit trees", "ornamentals", "WA climate"],
        "description": "Guildford Garden Centre is a full-service garden centre in Guildford, WA carrying a good range of fruit trees alongside ornamentals and garden supplies. Great option for Perth gardeners wanting to browse in person.",
    },
    "fruit-salad-trees": {
        "url": "https://www.fruitsaladtrees.com",
        "tags": ["multi-graft trees", "space-saving", "novelty"],
        "description": "Fruit Salad Trees specialises in unique multi-graft fruit trees — a single tree bearing multiple fruit varieties. Ideal for small gardens. Ships to WA on the first Tuesday of each month (quarantine permit required).",
    },
    "diggers": {
        "url": "https://www.diggers.com.au",
        "tags": ["heirloom varieties", "heritage fruit", "seeds & plants"],
        "description": "The Diggers Club is Australia's largest heritage seed and plant company, based in Dromana VIC. They carry a curated selection of heirloom and heritage fruit trees alongside vegetables, herbs, and seeds. Nationwide shipping.",
    },
    "all-season-plants-wa": {
        "url": "https://allseasonplantswa.com.au",
        "tags": ["tropical fruit", "WA grown", "rare varieties"],
        "description": "All Season Plants WA is a Perth-based nursery specialising in tropical and rare fruit trees suited to Western Australia's warm climate. Pickup available at their Perth location.",
    },
    "ausnurseries": {
        "url": "https://www.ausnurseries.com",
        "tags": ["fruit trees", "edibles"],
        "description": "Aus Nurseries is an online nursery offering a variety of fruit trees and edible plants across Australia. They carry a range of common and less common fruit species, shipping to most Australian states excluding WA, NT, and TAS.",
    },
    "fruit-tree-cottage": {
        "url": "https://www.fruittreecottage.com.au",
        "tags": ["tropical fruit", "subtropical fruit", "rare varieties"],
        "description": "Fruit Tree Cottage is a specialist fruit tree nursery on the Sunshine Coast, Queensland. They focus on tropical and subtropical varieties with an impressive range of lychee, fig, guava, persimmon, and other rare edibles. Does not ship to WA, NT, or TAS.",
    },
    "heritage-fruit-trees": {
        "url": "https://www.heritagefruittrees.com.au",
        "tags": ["heritage varieties", "heirloom", "temperate fruit", "apples", "pears", "plums"],
        "description": "Heritage Fruit Trees is a Victorian specialist nursery carrying one of Australia's largest collections of heritage and heirloom temperate fruit trees. Based in Beaufort, VIC, they stock hundreds of apple, pear, plum, cherry, quince, and nut tree varieties including many rare cultivars unavailable elsewhere. Does not ship to WA, NT, or TAS.",
    },
    "perth-mobile-nursery": {
        "url": "https://perthmobilenursery.com.au",
        "tags": ["WA grown", "tropical fruit", "mangoes", "figs", "rare varieties"],
        "description": "Perth Mobile Nursery is a premium WA-based nursery specialising in fruit trees suited to Perth's climate. They carry a range of tropical and subtropical varieties including rare mango cultivars, figs, pomegranates, and edibles grown locally in WA. Perth metro delivery available.",
    },
    "yalca-fruit-trees": {
        "url": "https://yalcafruittrees.com.au",
        "tags": ["heritage varieties", "dwarf fruit trees", "apples", "pears", "stone fruit", "temperate"],
        "description": "Yalca Fruit Trees is a specialist heritage and dwarf fruit tree nursery based in Yalca, Victoria. They carry a broad range of apple, pear, plum, cherry, apricot, nectarine, peach, fig, quince, persimmon and berry varieties. Shipping season is late June to 15 September (dormant bare-root season). Does not ship to WA, NT, or TAS.",
    },
    "forever-seeds": {
        "url": "https://forever-seeds.myshopify.com",
        "tags": ["rare tropicals", "exotic fruit trees", "NSW", "seedlings"],
        "description": "Forever Seeds is a NSW-based nursery specialising in rare and exotic tropical fruit trees. Their range includes unusual varieties such as Rollinia (Brazilian Custard Apple), Canistel (Yellow Sapote), Agarwood, Sudachi Lime, Yuzu, Longan, and other hard-to-find tropicals. Ships to NSW, VIC, QLD, SA and ACT. Does not ship to WA, NT, or TAS.",
    },
    "fruit-tree-lane": {
        "url": "https://fruittreelane.com.au",
        "tags": ["finger limes", "figs", "olives", "blueberries", "subtropical", "QLD"],
        "description": "Fruit Tree Lane is a Queensland-based nursery specialising in fruit trees, finger limes, figs, olives, blueberries, and subtropical varieties. Based in Helidon, QLD, they carry a wide range of edible trees suited to subtropical and warm temperate climates. Does not ship to WA, NT, or TAS.",
    },
    "plantnet": {
        "url": "https://plantnet.com.au",
        "tags": ["dwarf fruit trees", "SA grown", "pears", "peaches", "citrus"],
        "description": "PlantNet is a South Australian nursery specialising in dwarf and compact fruit tree varieties. They carry a good range of pears, peaches, nectarines, plums, and citrus in pot-friendly sizes. WA orders are fulfilled via their Olea Nurseries partner based in Manjimup WA (not direct interstate shipping), so WA buyers receive locally grown stock with no interstate quarantine issues.",
    },
}


def load_species_lookup() -> dict:
    if not SPECIES_FILE.exists():
        return {}
    with open(SPECIES_FILE) as f:
        species = json.load(f)
    lookup = {}
    for s in species:
        common = s["common_name"].lower()
        entry = {
            "cn": s["common_name"],
            "ln": s["latin_name"],
            "sl": s["slug"],
        }
        parts = s["latin_name"].split()
        if len(parts) >= 2:
            entry["g"] = parts[0]
        lookup[common] = entry
        for alias in s.get("aliases", []):
            lookup[alias.lower()] = entry
    return lookup


def match_species(title: str, lookup: dict):
    title_lower = title.lower()
    for term, entry in lookup.items():
        if term and term in title_lower:
            return entry
        if "g" in entry and entry["g"].lower() in title_lower:
            return entry
    return None


def load_nursery_data(data_dir: Path) -> dict:
    """Load latest.json for all nurseries. Returns dict keyed by nursery_key."""
    nurseries = {}
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        latest = nursery_dir / "latest.json"
        if not latest.exists():
            continue
        with open(latest) as f:
            data = json.load(f)
        nurseries[nursery_dir.name] = data
    return nurseries


def build_species_breakdown(products: list, species_lookup: dict) -> list:
    """Return list of {cn, ln, sl, in_stock, total} sorted by in_stock desc."""
    counts = {}
    for p in products:
        sp = match_species(p.get("title", ""), species_lookup)
        if not sp:
            continue
        key = sp["cn"]
        if key not in counts:
            counts[key] = {"cn": sp["cn"], "ln": sp["ln"], "sl": sp["sl"], "in_stock": 0, "total": 0}
        counts[key]["total"] += 1
        if p.get("any_available"):
            counts[key]["in_stock"] += 1
    return sorted(counts.values(), key=lambda x: (-x["in_stock"], -x["total"]))


def ships_to_wa(nursery_key: str) -> bool:
    return "WA" in SHIPPING_MAP.get(nursery_key, [])




def build_nursery_page(nursery_key: str, data: dict, species_lookup: dict, total_nurseries: int = 19) -> str:
    meta = NURSERY_META.get(nursery_key, {})
    name = NURSERY_NAMES.get(nursery_key, data.get("nursery_name", nursery_key))
    location = data.get("location", "Australia")
    url = meta.get("url", "")
    tags = meta.get("tags", [])
    description = meta.get("description", "")
    ships = sorted(SHIPPING_MAP.get(nursery_key, []))
    local_label = delivery_label(nursery_key)
    wa = ships_to_wa(nursery_key)

    products = data.get("products", [])
    in_stock_count = data.get("in_stock_count", sum(1 for p in products if p.get("any_available")))
    total_count = data.get("product_count", len(products))

    species_breakdown = build_species_breakdown(products, species_lookup)
    species_count = len(species_breakdown)
    nursery_count_minus_one = max(total_nurseries - 1, 1)

    restrict = "" if local_label else restriction_warning(nursery_key)
    tag_badges = "".join(f'<span class="badge bg-light text-dark border me-1 mb-1">{t}</span>' for t in tags)
    ship_badges = "".join(f'<span class="badge bg-secondary me-1">{s}</span>' for s in ships)
    wa_stat = "✓" if wa else "✗"

    species_rows = ""
    for sp in species_breakdown:
        in_s = sp["in_stock"]
        tot = sp["total"]
        stock_cell = f'<span class="text-success fw-bold">{in_s}</span>' if in_s > 0 else f'<span class="text-muted">{in_s}</span>'
        species_rows += f"""
        <tr>
            <td><a href="/species/{sp['sl']}.html">{sp['cn']}</a></td>
            <td class="text-muted fst-italic small">{sp['ln']}</td>
            <td class="text-center">{stock_cell}</td>
            <td class="text-center text-muted">{tot}</td>
        </tr>"""

    all_in_stock = [p for p in products if p.get("any_available")]
    in_stock_products = all_in_stock[:20]
    has_more_products = len(all_in_stock) > 20
    product_rows = ""
    for p in in_stock_products:
        price = f"${p['min_price']:.2f}" if p.get("min_price") else "POA"
        title = p.get("title", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        p_url = p.get("url", "#")
        product_rows += f"""
        <tr>
            <td><a href="{p_url}" target="_blank" rel="noopener">{title}</a></td>
            <td class="text-end">{price}</td>
        </tr>"""

    url_display = url.replace("https://", "").replace("http://", "")
    url_link = f'<a href="{url}" target="_blank" rel="noopener">{url_display}</a>' if url else ""
    location_line = f"📍 {location}" + (f"\n                &nbsp;·&nbsp;\n                {url_link}" if url_link else "")

    scraped_at = data.get("scraped_at", "")
    if scraped_at:
        try:
            dt = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
            scraped_at_fmt = dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            scraped_at_fmt = scraped_at
    else:
        scraped_at_fmt = "recently"

    restrict_badge = f'<span class="text-xs px-2 py-0.5 bg-red-100 text-red-800 rounded-full font-semibold ml-2">{restrict}</span>' if restrict else ''
    tag_badges_tw = "".join(f'<span class="text-xs px-2 py-0.5 bg-gray-100 text-gray-700 border border-gray-200 rounded mr-1 mb-1 whitespace-nowrap">{t}</span>' for t in tags)
    ship_badges_tw = "".join(f'<span class="text-xs px-2 py-0.5 bg-gray-600 text-white rounded mr-1">{s}</span>' for s in ships)

    # Rebuild species rows for Tailwind
    species_rows_tw = ""
    for sp in species_breakdown:
        in_s = sp["in_stock"]
        tot = sp["total"]
        stock_cell = f'<span class="text-green-700 font-bold">{in_s}</span>' if in_s > 0 else f'<span class="text-gray-400">{in_s}</span>'
        species_rows_tw += f"""
        <tr class="border-b border-gray-100 hover:bg-gray-50">
          <td class="py-1.5 px-3 text-sm"><a href="/species/{sp['sl']}.html" class="text-green-700 hover:underline">{sp['cn']}</a></td>
          <td class="py-1.5 px-3 text-xs text-gray-400 italic">{sp['ln']}</td>
          <td class="py-1.5 px-3 text-center text-sm">{stock_cell}</td>
          <td class="py-1.5 px-3 text-center text-sm text-gray-400">{tot}</td>
        </tr>"""

    # Rebuild product rows for Tailwind
    product_rows_tw = ""
    for p in in_stock_products:
        price = f"${p['min_price']:.2f}" if p.get("min_price") else "POA"
        title = p.get("title", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        p_url = p.get("url", "#")
        product_rows_tw += f"""
        <tr class="border-b border-gray-100 hover:bg-gray-50">
          <td class="py-1.5 px-3 text-sm"><a href="{p_url}" target="_blank" rel="noopener" class="text-green-700 hover:underline">{title}</a></td>
          <td class="py-1.5 px-3 text-right text-sm font-medium">{price}</td>
        </tr>"""

    extra_style = """\
  .stat-card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; padding: 1.2rem; text-align: center; }
  .stat-card .number { font-size: 2rem; font-weight: 700; color: #059669; }
  .stat-card .label { font-size: 0.85rem; color: #6b7280; }
  .scrollable-table { max-height: 420px; overflow-y: auto; }
  .scrollable-table thead { position: sticky; top: 0; background: #f9fafb; }"""

    head = render_head(
        title=f"{name} — Stock, Prices &amp; Shipping | treestock.com.au",
        description=f"Browse {name}'s current fruit tree stock. {total_count} products tracked, {in_stock_count} in stock. {('Delivers to: ' + local_label + '.') if local_label else ('Ships to: ' + ', '.join(ships) + '.')}",
        canonical_url=f"https://treestock.com.au/nursery/{nursery_key}.html",
        og_title=f"{name} — Stock, Prices &amp; Shipping",
        og_description=f"Browse {name}'s current fruit tree stock. {total_count} products tracked, {in_stock_count} in stock. {('Delivers to: ' + local_label + '.') if local_label else ('Ships to: ' + ', '.join(ships) + '.')}",
        og_type="website",
        extra_style=extra_style,
    )
    header_html = render_header(active_path="/nursery/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Nurseries", "/nursery/"), (name, "")])
    footer = render_footer()

    url_display = url.replace("https://", "").replace("http://", "")
    url_link = f'<a href="{url}" target="_blank" rel="noopener" class="text-green-700 hover:underline">{url_display}</a>' if url else ""

    return f"""{head}
{header_html}

<main class="max-w-3xl mx-auto px-4 py-6">
  {breadcrumb}

  <div class="mb-6">
    <h1 class="text-2xl font-bold text-gray-900 mb-1">{name} {restrict_badge}</h1>
    <p class="text-gray-500 text-sm mb-2">📍 {location}{(' · ' + url_link) if url_link else ''}</p>
    <div class="mb-2 flex flex-wrap gap-1">{tag_badges_tw}</div>
    <div class="text-sm text-gray-600">{'Delivers to:'  if local_label else 'Ships to:'}</div>
    <div class="mt-1">{'<span class="text-xs px-2 py-0.5 bg-amber-100 text-amber-800 rounded font-semibold">' + local_label + '</span>' if local_label else ship_badges_tw}</div>
  </div>

  <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
    <div class="stat-card"><div class="number">{in_stock_count}</div><div class="label">In Stock</div></div>
    <div class="stat-card"><div class="number">{total_count}</div><div class="label">Products Tracked</div></div>
    <div class="stat-card"><div class="number">{species_count}</div><div class="label">Species</div></div>
    <div class="stat-card"><div class="number">{len(ships)}</div><div class="label">States</div></div>
  </div>

  {f'<div class="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-6 text-sm text-gray-700">{description}</div>' if description else ''}

  <div class="grid md:grid-cols-2 gap-6">
    <div class="border border-gray-200 rounded-lg">
      <div class="flex justify-between items-center px-4 py-3 border-b border-gray-200 bg-gray-50 rounded-t-lg">
        <span class="font-semibold text-sm">Species Carried</span>
        <span class="text-xs text-gray-500">{species_count} species</span>
      </div>
      <div class="scrollable-table">
        <table class="w-full text-left">
          <thead>
            <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
              <th class="py-2 px-3">Species</th>
              <th class="py-2 px-3 italic text-gray-400">Latin name</th>
              <th class="py-2 px-3 text-center">In Stock</th>
              <th class="py-2 px-3 text-center">Total</th>
            </tr>
          </thead>
          <tbody>
            {species_rows_tw}
          </tbody>
        </table>
      </div>
    </div>

    <div class="border border-gray-200 rounded-lg">
      <div class="flex justify-between items-center px-4 py-3 border-b border-gray-200 bg-gray-50 rounded-t-lg">
        <span class="font-semibold text-sm">In Stock Now</span>
        <a href="/?nursery={nursery_key}" class="text-xs px-2 py-1 border border-green-600 text-green-700 rounded hover:bg-green-50">View all on dashboard →</a>
      </div>
      <div class="scrollable-table">
        <table class="w-full text-left">
          <thead>
            <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
              <th class="py-2 px-3">Product</th>
              <th class="py-2 px-3 text-right">Price</th>
            </tr>
          </thead>
          <tbody>
            {product_rows_tw}
          </tbody>
        </table>
      </div>
      {'<div class="px-4 py-2 border-t border-gray-200 text-xs text-gray-500">Showing top 20 in-stock products. <a href="/?nursery=' + nursery_key + '" class="text-green-700 hover:underline">See all →</a></div>' if has_more_products else ''}
    </div>
  </div>

  <p class="text-xs text-gray-400 mt-4">Data updated daily. Last checked: {scraped_at_fmt}.</p>

  <!-- Subscribe CTA -->
  <div class="mt-6 p-4 bg-green-50 border border-green-200 rounded-lg text-sm">
    <p class="font-medium text-green-800 mb-1">Get restock alerts for {name}</p>
    <p class="text-gray-600 mb-3">We monitor {name} and {nursery_count_minus_one} other nurseries daily. Free email when varieties restock or prices drop.</p>
    <form id="nurserySubForm" class="flex flex-col sm:flex-row gap-2 flex-wrap">
      <input type="email" id="nurserySubEmail" placeholder="your@email.com" required
        class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 flex-1 max-w-xs">
      <select id="nurserySubState" class="px-2 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
        <option value="ALL">All states</option>
        <option value="NSW">NSW</option><option value="VIC">VIC</option>
        <option value="QLD">QLD</option><option value="WA">WA</option>
        <option value="SA">SA</option><option value="TAS">TAS</option>
        <option value="NT">NT</option><option value="ACT">ACT</option>
      </select>
      <button type="submit" class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium whitespace-nowrap">
        Get free alerts
      </button>
    </form>
    <div id="nurserySubMessage" class="mt-2 text-sm hidden"></div>
  </div>
  <script>
  document.getElementById('nurserySubForm').addEventListener('submit', function(e) {{
    e.preventDefault();
    var email = document.getElementById('nurserySubEmail').value.trim();
    var state = document.getElementById('nurserySubState').value;
    var msg = document.getElementById('nurserySubMessage');
    fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email: email, state: state}})
    }})
    .then(function(r) {{ return r.json().then(function(d) {{ return {{status: r.status, data: d}}; }}); }})
    .then(function(res) {{
      if (res.status === 202) {{
        msg.textContent = '\u2713 Check your email \u2014 we sent you a confirmation link.';
      }} else if (res.data.message && res.data.message.includes('already')) {{
        msg.textContent = 'You\'re already subscribed.';
      }} else {{
        msg.textContent = '\u2713 Done! You\'ll get alerts when stock changes.';
      }}
      msg.className = 'mt-2 text-sm text-green-700';
      msg.classList.remove('hidden');
      document.getElementById('nurserySubForm').style.display = 'none';
    }})
    .catch(function() {{
      msg.textContent = 'Something went wrong \u2014 please try again.';
      msg.className = 'mt-2 text-sm text-red-600';
      msg.classList.remove('hidden');
    }});
  }});
  </script>
</main>

{footer}

</body>
</html>"""


def build_index_page(nurseries_data: dict, species_lookup: dict, today: str) -> str:
    count = len(nurseries_data)
    cards = ""
    for key in sorted(nurseries_data.keys()):
        data = nurseries_data[key]
        meta = NURSERY_META.get(key, {})
        name = NURSERY_NAMES.get(key, data.get("nursery_name", key))
        tags = meta.get("tags", [])
        ships = sorted(SHIPPING_MAP.get(key, []))
        local_lbl = delivery_label(key)
        wa = ships_to_wa(key)
        in_stock = data.get("in_stock_count", 0)
        total = data.get("product_count", len(data.get("products", [])))
        location = data.get("location", "Australia")

        restrict = "" if local_lbl else restriction_warning(key)
        restrict_badge = f'<span class="text-xs px-2 py-0.5 bg-red-100 text-red-800 rounded-full font-semibold">{restrict}</span>' if restrict else ''
        tag_badges = " ".join(f'<span class="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-700 border border-gray-200 rounded">{t}</span>' for t in tags[:3])
        ship_str = ", ".join(ships)

        cards += f"""
    <div class="border border-gray-200 rounded-lg hover:shadow-md transition-shadow">
      <div class="p-4">
        <div class="flex justify-between items-start mb-1">
          <h3 class="font-semibold text-sm">
            <a href="/nursery/{key}.html" class="text-gray-900 hover:text-green-700 no-underline">{name}</a>
          </h3>
          {restrict_badge}
        </div>
        <p class="text-xs text-gray-500 mb-2">📍 {location}</p>
        <div class="mb-2 flex flex-wrap gap-1">{tag_badges}</div>
        <p class="text-xs text-gray-500 mb-1"><strong>{in_stock}</strong> in stock · {total} tracked</p>
        <p class="text-xs text-gray-500 mb-0">{'Delivers to: ' + local_lbl if local_lbl else 'Ships to: ' + ship_str}</p>
      </div>
      <div class="px-4 pb-4">
        <a href="/nursery/{key}.html" class="block text-center text-sm px-3 py-1.5 border border-green-600 text-green-700 rounded hover:bg-green-50 no-underline">View Nursery →</a>
      </div>
    </div>"""

    head = render_head(
        title="Australian Fruit Tree Nurseries — Stock &amp; Shipping | treestock.com.au",
        description=f"Browse all {count} Australian fruit tree nurseries tracked by treestock.com.au. Compare stock, prices, and shipping to your state including WA.",
        canonical_url="https://treestock.com.au/nursery/",
        og_title="Australian Fruit Tree Nurseries — treestock.com.au",
    )
    header_html = render_header(active_path="/nursery/")
    footer = render_footer()

    return f"""{head}
{header_html}

<main class="max-w-3xl mx-auto px-4 py-6">
  <h1 class="text-2xl font-bold text-gray-900 mb-1">Australian Fruit Tree Nurseries</h1>
  <p class="text-gray-500 text-sm mb-2">Daily stock tracking across {count} nurseries. Updated {today}.</p>
  <p class="text-sm mb-6"><a href="/compare/nurseries.html" class="text-green-700 hover:underline">Compare all nurseries side-by-side &rarr;</a></p>

  <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
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
    nursery_dir = output_dir / "nursery"
    nursery_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    species_lookup = load_species_lookup()
    nurseries_data = load_nursery_data(data_dir)

    if not nurseries_data:
        print("No nursery data found.")
        sys.exit(1)

    for key, data in nurseries_data.items():
        name = NURSERY_NAMES.get(key, data.get("nursery_name", key))
        page = build_nursery_page(key, data, species_lookup, total_nurseries=len(nurseries_data))
        out = nursery_dir / f"{key}.html"
        out.write_text(page)
        in_stock = data.get("in_stock_count", 0)
        total = data.get("product_count", len(data.get("products", [])))
        print(f"  {name}: {in_stock} in stock / {total} total → {out}")

    index = build_index_page(nurseries_data, species_lookup, today)
    index_path = nursery_dir / "index.html"
    index_path.write_text(index)
    print(f"  Index → {index_path} ({len(nurseries_data)} nurseries)")


if __name__ == "__main__":
    main()
