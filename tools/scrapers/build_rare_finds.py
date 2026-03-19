#!/usr/bin/env python3
"""
Build a "Rare & Exotic" spotlight page for treestock.com.au.

Shows rare/unusual fruit species currently in stock across Australian nurseries.
Target audience: WA rare fruit community. Updates daily.

Usage:
    python3 build_rare_finds.py /path/to/nursery-stock /path/to/output/
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

SCRAPERS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRAPERS_DIR))
from build_compare_pages import load_species, build_species_lookup, match_title
from shipping import SHIPPING_MAP, NURSERY_NAMES
from treestock_layout import render_head, render_header, render_footer

# Species the rare fruit community genuinely cares about
# (not just apples, lemons, mangoes — those are covered on main dashboard)
RARE_SPECIES = {
    'Abiu', 'Acerola', 'Ackee', 'Bael Fruit',
    'Black Sapote', 'Canistel', 'Carambola', 'Che',
    'Custard Apple', 'Davidson Plum', 'Dragon Fruit',
    'Feijoa', 'Finger Lime', 'Grumichama',
    'Guava', 'Jakfruit', 'Jaboticaba', 'Jujube',
    'Longan', 'Loquat', 'Lychee', 'Macadamia',
    'Mangosteen', 'Miracle Fruit', 'Mulberry',
    'Paw Paw', 'Persimmon', 'Pomegranate', 'Rambutan',
    'Rollinia', 'Rose Apple', 'Sapodilla', 'Soursop',
    'Star Apple', 'Star Fruit', 'Surinam Cherry', 'Tamarind',
    'Wampee', 'White Sapote', 'Yellow Sapote',
    # "Hard to find" that people actively search for
    'Banana', 'Passionfruit', 'Pawpaw',
}

# Species to highlight as especially rare/sought-after
HIGHLIGHT_SPECIES = {
    'Jaboticaba', 'Rambutan', 'Mangosteen', 'Rollinia', 'Sapodilla',
    'White Sapote', 'Miracle Fruit', 'Wampee', 'Grumichama',
    'Black Sapote', 'Canistel', 'Star Apple', 'Soursop',
    'Abiu', 'Acerola',
}


def build_rare_page(data_dir: str, output_dir: str):
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    species_list = load_species()
    lookup = build_species_lookup(species_list)

    # Collect in-stock products matching rare species
    species_data = {}

    for nursery in sorted(os.listdir(data_dir)):
        latest = data_dir / nursery / 'latest.json'
        if not latest.exists():
            continue
        with open(latest) as f:
            raw = json.load(f)

        nursery_name = NURSERY_NAMES.get(nursery, nursery)
        ships_wa = 'WA' in SHIPPING_MAP.get(nursery, [])
        nursery_url = f'/nursery/{nursery}.html'

        for p in raw.get('products', []):
            if not p.get('any_available'):
                continue
            s = match_title(p.get('title', ''), lookup)
            if not s:
                continue
            sname = s['common_name']
            if sname not in RARE_SPECIES:
                continue

            if sname not in species_data:
                species_data[sname] = {
                    'species': s,
                    'products': [],
                    'nurseries': set(),
                }

            species_data[sname]['products'].append({
                'nursery': nursery,
                'nursery_name': nursery_name,
                'nursery_url': nursery_url,
                'title': p.get('title', ''),
                'price': p.get('min_price'),
                'max_price': p.get('max_price'),
                'url': p.get('url', ''),
                'ships_wa': ships_wa,
            })
            species_data[sname]['nurseries'].add(nursery)

    if not species_data:
        print("No rare species found in stock — skipping rare.html")
        return

    now = datetime.now(timezone.utc)
    date_str = now.strftime('%d %B %Y')

    # Sort: highlighted first, then by number of in-stock products (descending)
    def sort_key(item):
        sname, data = item
        is_highlight = sname in HIGHLIGHT_SPECIES
        return (not is_highlight, -len(data['products']))

    sorted_species = sorted(species_data.items(), key=sort_key)

    # Stats
    total_products = sum(len(d['products']) for d in species_data.values())
    wa_products = sum(
        sum(1 for p in d['products'] if p['ships_wa'])
        for d in species_data.values()
    )

    # Build species cards HTML
    cards_html = []
    for sname, data in sorted_species:
        s = data['species']
        products = data['products']
        nursery_count = len(data['nurseries'])

        # Price range
        prices = [p['price'] for p in products if p['price']]
        if prices:
            min_p = min(prices)
            max_p = max(prices)
            price_str = f'${min_p:.0f}' if min_p == max_p else f'${min_p:.0f}–${max_p:.0f}'
        else:
            price_str = 'POA'

        # WA shipping indicator
        wa_prods = [p for p in products if p['ships_wa']]
        if wa_prods:
            wa_badge = f'<span class="wa-badge">{len(wa_prods)} ship to WA</span>'
        else:
            wa_badge = '<span class="no-wa-badge">Eastern states only</span>'

        # Highlight badge
        highlight_badge = ''
        if sname in HIGHLIGHT_SPECIES:
            highlight_badge = '<span class="rare-badge">Rare find</span>'

        # Product rows (up to 6 per species)
        show_products = sorted(products, key=lambda x: (not x['ships_wa'], x['price'] or 999))
        prod_rows = []
        for p in show_products[:6]:
            wa_icon = '🚛' if p['ships_wa'] else '📦'
            price_disp = f'${p["price"]:.2f}' if p['price'] else '—'
            prod_rows.append(
                f'<tr>'
                f'<td class="prod-title"><a href="{p["url"]}" target="_blank" rel="noopener">{p["title"]}</a></td>'
                f'<td class="prod-nursery"><a href="{p["nursery_url"]}">{p["nursery_name"]}</a></td>'
                f'<td class="prod-price">{price_disp}</td>'
                f'<td class="prod-wa">{wa_icon}</td>'
                f'</tr>'
            )

        more_html = ''
        if len(products) > 6:
            slug = s.get('slug', sname.lower().replace(' ', '-'))
            more_html = f'<p class="more-link"><a href="/species/{slug}.html">See all {len(products)} listings →</a></p>'

        slug = s.get('slug', sname.lower().replace(' ', '-'))
        sci_name = s.get('scientific_name', '')

        cards_html.append(f'''
  <div class="species-card" id="{slug}">
    <div class="species-header">
      <div class="species-title-row">
        <h2 class="species-name"><a href="/species/{slug}.html">{sname}</a></h2>
        {highlight_badge}
      </div>
      <div class="species-meta">
        {f'<span class="sci-name">{sci_name}</span>' if sci_name else ''}
        <span class="stock-count">{len(products)} in stock</span>
        <span class="nursery-count">{nursery_count} {"nursery" if nursery_count == 1 else "nurseries"}</span>
        <span class="price-range">{price_str}</span>
        {wa_badge}
      </div>
    </div>
    <table class="prod-table">
      <tbody>
        {"".join(prod_rows)}
      </tbody>
    </table>
    {more_html}
  </div>''')

    all_cards = '\n'.join(cards_html)
    species_count = len(species_data)

    extra_style = """\
  .wa-badge { background: #dcfce7; color: #166534; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
  .no-wa-badge { background: #f3f4f6; color: #6b7280; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; }
  .rare-badge { background: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; margin-left: 4px; }
  .species-card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .species-card:hover { border-color: #86efac; }
  .species-header { margin-bottom: 12px; }
  .species-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
  .species-name { font-size: 1.1rem; font-weight: 700; color: #166534; margin: 0; }
  .species-name a { color: inherit; text-decoration: none; }
  .species-name a:hover { text-decoration: underline; }
  .species-meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 0.8rem; color: #6b7280; }
  .sci-name { font-style: italic; }
  .stock-count, .nursery-count, .price-range { font-weight: 500; color: #374151; }
  .prod-table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  .prod-table td { padding: 6px 8px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
  .prod-table tr:last-child td { border-bottom: none; }
  .prod-title { max-width: 300px; }
  .prod-title a { color: #1d4ed8; text-decoration: none; }
  .prod-title a:hover { text-decoration: underline; }
  .prod-nursery a { color: #374151; text-decoration: none; font-size: 0.8rem; }
  .prod-nursery a:hover { text-decoration: underline; }
  .prod-price { font-weight: 600; color: #166534; white-space: nowrap; }
  .prod-wa { text-align: center; }
  .more-link { font-size: 0.8rem; color: #6b7280; margin-top: 8px; text-align: right; }
  .more-link a { color: #16a34a; text-decoration: none; }
  .more-link a:hover { text-decoration: underline; }
  .subscribe-box { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 20px; }
  @media (max-width: 640px) {
    .prod-table { font-size: 0.8rem; }
    .prod-title { max-width: 160px; }
  }"""

    head = render_head(
        title="Rare &amp; Exotic Fruit Trees In Stock — treestock.com.au",
        description=f"Find rare and exotic fruit trees in stock at Australian nurseries right now. {species_count} unusual species tracked including jaboticaba, rambutan, sapodilla and more. Updated daily.",
        canonical_url="https://treestock.com.au/rare.html",
        og_title=f"Rare Fruit Trees In Stock in Australia — {date_str}",
        og_description=f"{total_products} rare &amp; exotic fruit trees in stock across {species_count} species. Including {wa_products} that ship to WA. Updated daily at treestock.com.au",
        og_image="https://treestock.com.au/og-image.png",
        extra_style=extra_style,
    )
    header = render_header(
        subtitle="Rare &amp; Exotic Finds",
        active_path="/rare.html",
    )
    footer = render_footer()

    html = f'''{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-6">

  <div class="mb-6">
    <h1 class="text-2xl font-bold text-green-900 mb-2">Rare &amp; Exotic Fruit Trees In Stock</h1>
    <p class="text-gray-600 text-sm">
      {species_count} unusual species currently available across Australian nurseries — updated daily.
      <strong>{total_products} total listings</strong>, including <strong>{wa_products} that ship to Western Australia</strong>.
      Last updated: {date_str}.
    </p>
  </div>

  <div class="subscribe-box mb-6">
    <p class="font-semibold text-green-900 mb-1">Get rare restock alerts by email — free.</p>
    <p class="text-sm text-gray-600 mb-3">Be first to know when hard-to-find species come back into stock. Daily digest of price drops and new arrivals. <a href="/sample-digest.html" class="text-green-700 underline">See what a digest looks like &rarr;</a></p>
    <form id="subscribeForm" class="flex gap-2 flex-wrap">
      <input type="email" id="emailInput" placeholder="your@email.com"
        class="flex-1 min-w-0 px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
      <select id="stateInput" class="px-2 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
        <option value="ALL">All states</option>
        <option value="NSW">NSW</option><option value="VIC">VIC</option>
        <option value="QLD">QLD</option><option value="WA">WA</option>
        <option value="SA">SA</option><option value="TAS">TAS</option>
        <option value="NT">NT</option><option value="ACT">ACT</option>
      </select>
      <button type="submit" id="subscribeBtn"
        class="bg-green-700 text-white px-4 py-2 rounded text-sm font-semibold hover:bg-green-800">
        Subscribe
      </button>
    </form>
    <p id="subscribeMsg" class="text-sm mt-2 text-gray-600"></p>
  </div>

  <div class="flex items-center gap-3 text-sm text-gray-500 mb-6 flex-wrap">
    <span>Legend:</span>
    <span>🚛 Ships to WA</span>
    <span>📦 Eastern states only</span>
    <span class="wa-badge">X ship to WA</span>
    <span class="rare-badge">Rare find</span>
  </div>

  {all_cards}

  <div class="subscribe-box mt-8">
    <p class="font-semibold text-green-900 mb-1">Want alerts when rare species restock?</p>
    <p class="text-sm text-gray-600 mb-3">Subscribe free — get daily emails with price drops, new arrivals, and rare restocks across {len(NURSERY_NAMES)} Australian nurseries.</p>
    <form id="subscribeForm2" class="flex gap-2 flex-wrap">
      <input type="email" id="emailInput2" placeholder="your@email.com"
        class="flex-1 min-w-0 px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
      <select id="stateInput2" class="px-2 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
        <option value="ALL">All states</option>
        <option value="NSW">NSW</option><option value="VIC">VIC</option>
        <option value="QLD">QLD</option><option value="WA">WA</option>
        <option value="SA">SA</option><option value="TAS">TAS</option>
        <option value="NT">NT</option><option value="ACT">ACT</option>
      </select>
      <button type="submit" id="subscribeBtn2"
        class="bg-green-700 text-white px-4 py-2 rounded text-sm font-semibold hover:bg-green-800">
        Subscribe
      </button>
    </form>
    <p id="subscribeMsg2" class="text-sm mt-2 text-gray-600"></p>
  </div>

</main>

{footer}

<script>
async function handleSubscribe(formId, inputId, stateId, btnId, msgId) {{
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener('submit', async (e) => {{
    e.preventDefault();
    const email = document.getElementById(inputId).value.trim();
    const stateEl = document.getElementById(stateId);
    const state = stateEl ? stateEl.value : 'ALL';
    const btn = document.getElementById(btnId);
    const msg = document.getElementById(msgId);
    if (!email) return;
    btn.disabled = true;
    btn.textContent = 'Subscribing...';
    try {{
      const resp = await fetch('/api/subscribe', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{email, state}})
      }});
      const data = await resp.json();
      msg.textContent = data.message || 'Subscribed!';
      msg.className = 'text-sm mt-2 ' + (resp.ok ? 'text-green-700' : 'text-red-600');
      if (resp.ok) {{ form.reset(); }}
    }} catch(err) {{
      msg.textContent = 'Error. Please try again.';
      msg.className = 'text-sm mt-2 text-red-600';
    }}
    btn.disabled = false;
    btn.textContent = 'Subscribe';
  }});
}}
handleSubscribe('subscribeForm', 'emailInput', 'stateInput', 'subscribeBtn', 'subscribeMsg');
handleSubscribe('subscribeForm2', 'emailInput2', 'stateInput2', 'subscribeBtn2', 'subscribeMsg2');
</script>

</body>
</html>'''

    out_path = output_dir / 'rare.html'
    with open(out_path, 'w') as f:
        f.write(html)

    print(f"Built {out_path}")
    print(f"  {species_count} rare species, {total_products} products, {wa_products} ship to WA")
    return species_count, total_products


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <data_dir> <output_dir>")
        sys.exit(1)
    build_rare_page(sys.argv[1], sys.argv[2])
