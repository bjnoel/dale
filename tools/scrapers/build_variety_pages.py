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

from shipping import SHIPPING_MAP, NURSERY_NAMES, restriction_warning, delivery_label
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer

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
    "ausnurseries": "https://www.ausnurseries.com",
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
    "ornamental",  # ornamental trees/shrubs are not fruit trees
    "asparagus",   # vegetable, not a fruit tree
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
        restrict = restriction_warning(nursery_key)

        raw_products = data.get("products", [])
        for p in raw_products:
            title = p.get("title", "").strip()
            title_lower = title.lower()
            # Skip non-plant items
            if any(kw in title_lower for kw in NON_PLANT_KEYWORDS):
                continue
            # Skip seed packets (not nursery-grown trees)
            if re.search(r'\bseeds?\b', title_lower) and 'seedling' not in title_lower and 'seedless' not in title_lower:
                continue
            products.append({
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "title": title,
                "url": p.get("url", ""),
                "price": p.get("min_price") or 0,
                "available": p.get("any_available", False),
                "restrict": restrict,
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

    cheapest = in_stock[0] if in_stock else None

    # Build product rows
    rows = ""
    for p in in_stock + out_stock:
        price_str = f"${p['price']:.2f}" if p["price"] else "—"
        avail_badge = (
            '<span class="text-green-700 font-medium text-sm">✓ In stock</span>'
            if p["available"]
            else '<span class="text-red-400 text-sm">Out of stock</span>'
        )
        restrict_note = f'<span class="text-xs text-red-600">{p["restrict"]}</span>' if p["restrict"] else ''
        local_lbl = delivery_label(p["nursery_key"])
        states = local_lbl if local_lbl else (", ".join(p["ships_states"]) if p["ships_states"] else "—")
        nursery_url = NURSERY_URLS.get(p["nursery_key"], "#")
        product_link = p["url"] or nursery_url
        rows += f"""
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-3 pr-4">
          <a href="{product_link}" target="_blank" rel="nofollow noopener"
             class="font-medium text-green-800 hover:underline">{p["nursery_name"]}</a>
          {f'<div class="text-xs">{restrict_note}</div>' if restrict_note else ''}
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

    summary_html = " &nbsp;·&nbsp; ".join(summary_parts) if summary_parts else ""

    in_stock_count = len(in_stock)
    nursery_count = len(set(p["nursery_key"] for p in products))
    species_slug = slugify(species)
    variety_title = f"{species} - {variety}"
    # Escape single quotes for safe embedding in JS string literals
    variety_title_js = variety_title.replace("'", "\\'")
    slug_js = slug.replace("'", "\\'")
    species_slug_js = species_slug.replace("'", "\\'")

    meta_desc = (
        f"Find {title} trees for sale in Australia. "
        f"Compare prices across {nursery_count} nurseries. "
        f"{in_stock_count} nurseries currently in stock. Updated daily."
    )

    head = render_head(
        title=f"Buy {title} Trees in Australia — Prices & Availability — treestock.com.au",
        description=meta_desc,
        canonical_url=f"https://treestock.com.au/variety/{slug}.html",
    )
    header = render_header(active_path="/variety/")
    breadcrumb = render_breadcrumb([
        ("Home", "/"), ("Varieties", "/variety/"),
        (species, f"/species/{species_slug}.html"), (variety, ""),
    ])
    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-6">
  {breadcrumb}

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

  <!-- Per-variety restock alert -->
  <div id="watchSection" class="bg-amber-50 border border-amber-200 rounded-lg p-5 mb-6">
    <h3 class="font-semibold text-gray-900 mb-1">
      {"Notify me next time this comes back" if in_stock else "Get notified when this comes back in stock"}
    </h3>
    <p class="text-sm text-gray-600 mb-3">
      {"This variety is currently in stock. You can still set an alert for next time." if in_stock else "This specific variety is currently out of stock. Enter your email to get an alert the moment it's available again."}
    </p>
    <form id="watchForm" class="flex gap-2 flex-wrap">
      <input type="email" id="watchEmail" placeholder="your@email.com" required
        class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 flex-1 max-w-xs">
      <button type="submit"
        class="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 text-sm font-medium whitespace-nowrap">
        Notify me
      </button>
    </form>
    <div id="watchMsg" class="mt-2 text-sm hidden"></div>
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
      <select id="subState" class="px-2 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
        <option value="ALL">All states</option>
        <option value="NSW">NSW</option><option value="VIC">VIC</option>
        <option value="QLD">QLD</option><option value="WA">WA</option>
        <option value="SA">SA</option><option value="TAS">TAS</option>
        <option value="NT">NT</option><option value="ACT">ACT</option>
      </select>
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

{footer}

<script>
document.getElementById('subscribeForm').addEventListener('submit', function(e) {{
  e.preventDefault();
  var email = document.getElementById('subEmail').value.trim();
  var stateEl = document.getElementById('subState');
  var state = stateEl ? stateEl.value : 'ALL';
  var msg = document.getElementById('subMsg');
  fetch('/api/subscribe', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{email: email, state: state, action: 'subscribe'}})
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

document.getElementById('watchForm').addEventListener('submit', function(e) {{
  e.preventDefault();
  var email = document.getElementById('watchEmail').value.trim();
  var msg = document.getElementById('watchMsg');
  fetch('/api/watch-variety', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{
      email: email,
      variety_slug: '{slug_js}',
      species_slug: '{species_slug_js}',
      variety_title: '{variety_title_js}'
    }})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(d) {{
    msg.textContent = d.message === 'Already watching'
      ? 'You\\'re already watching this variety!'
      : '✓ Alert set! You\\'ll be notified when {variety_title_js} is back in stock.';
    msg.className = 'mt-2 text-sm text-amber-700';
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
            var_lower = v['variety'].lower().replace('"', '&quot;')
        rows += f"""
      <tr class="border-b border-gray-100 hover:bg-gray-50" data-var="{var_lower}">
        <td class="py-2 pr-4">
          <a href="/variety/{v['slug']}.html" class="text-green-800 hover:underline">{v['variety']}</a>
        </td>
        <td class="py-2 pr-4 text-sm text-gray-600">{n_count} nurseries</td>
        <td class="py-2 pr-4 text-sm">{in_s} in stock</td>
        <td class="py-2 text-sm font-medium">{price}</td>
      </tr>"""

        in_stock_count = sum(v["in_stock"] for v in varieties)
        species_sections += f"""
  <section class="mb-8" id="{sp_slug}" data-sp="{sp.lower()}">
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

    total_varieties = len(entries)
    total_in_stock = sum(e["in_stock"] for e in entries)

    head = render_head(
        title="Fruit Tree Varieties for Sale in Australia — treestock.com.au",
        description=f"Browse {total_varieties} named fruit tree varieties available from Australian nurseries. Find Hass avocado, R2E2 mango, Grimal jaboticaba, Brown Turkey fig and more. Compare prices and check availability. Updated daily.",
    )
    header = render_header(active_path="/variety/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Varieties", "")])
    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-6">
  {breadcrumb}

  <h2 class="text-3xl font-bold text-green-900 mb-2">Fruit Tree Varieties for Sale in Australia</h2>
  <p class="text-gray-600 mb-4">
    Browse {total_varieties} named cultivars tracked across {len(by_species)} species.
    {total_in_stock} currently in stock across all Australian nurseries. Updated daily.
  </p>

  <div class="mb-6">
    <input id="varietySearch" type="search" placeholder="Search varieties or species (e.g. Hass, Bowen, Valencia...)"
      class="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
      autocomplete="off">
    <p id="varietyCount" class="text-xs text-gray-400 mt-1">{total_varieties} varieties across {len(by_species)} species</p>
  </div>

  <div id="noResults" class="hidden text-center py-12 text-gray-500">
    <p class="text-lg">No varieties found matching your search.</p>
    <p class="text-sm mt-1">Try a different spelling or species name.</p>
  </div>

  {species_sections}

</main>

<script>
(function() {{
  const input = document.getElementById('varietySearch');
  const countEl = document.getElementById('varietyCount');
  const noResultsEl = document.getElementById('noResults');
  const sections = document.querySelectorAll('section[data-sp]');
  const totalVarieties = {total_varieties};
  const totalSpecies = {len(by_species)};

  input.addEventListener('input', function() {{
    const q = this.value.toLowerCase().trim();
    let visibleVarieties = 0;
    let visibleSpecies = 0;

    sections.forEach(function(section) {{
      const sp = section.getAttribute('data-sp');
      const rows = section.querySelectorAll('tr[data-var]');
      let sectionMatch = false;

      if (!q) {{
        // No filter: show everything
        rows.forEach(r => r.style.display = '');
        section.style.display = '';
        sectionMatch = true;
        visibleVarieties += rows.length;
        visibleSpecies++;
      }} else {{
        // Filter rows by variety name or species name
        const spMatch = sp.includes(q);
        let rowsShown = 0;
        rows.forEach(function(row) {{
          const varName = row.getAttribute('data-var');
          if (spMatch || varName.includes(q)) {{
            row.style.display = '';
            rowsShown++;
          }} else {{
            row.style.display = 'none';
          }}
        }});
        if (rowsShown > 0) {{
          section.style.display = '';
          visibleVarieties += rowsShown;
          visibleSpecies++;
          sectionMatch = true;
        }} else {{
          section.style.display = 'none';
        }}
      }}
    }});

    if (!q) {{
      countEl.textContent = totalVarieties + ' varieties across ' + totalSpecies + ' species';
      noResultsEl.classList.add('hidden');
    }} else if (visibleVarieties === 0) {{
      countEl.textContent = 'No matches found';
      noResultsEl.classList.remove('hidden');
    }} else {{
      countEl.textContent = visibleVarieties + ' varieties across ' + visibleSpecies + ' species';
      noResultsEl.classList.add('hidden');
    }}
  }});
}})();
</script>

{footer}

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
    print(f"  Multi-nursery: {multi}, In-stock varieties: {in_stock_count}")


if __name__ == "__main__":
    main()
