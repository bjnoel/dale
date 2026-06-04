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
from shipping import SHIPPING_MAP, NURSERY_NAMES, restriction_warning
from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_footer

# Rarity scores are computed daily by build_species_pages.py and saved here.
# Fallback: empty (no badges shown) if file not yet generated.
RARITY_SCORES_FILE = Path("/opt/dale/data/rarity_scores.json")


def load_rarity_scores() -> dict:
    if RARITY_SCORES_FILE.exists():
        try:
            with open(RARITY_SCORES_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


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


def build_rare_page(data_dir: str, output_dir: str):
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    species_list = load_species()
    lookup = build_species_lookup(species_list)
    rarity_scores = load_rarity_scores()

    # Collect in-stock products matching rare species
    species_data = {}

    for nursery in sorted(os.listdir(data_dir)):
        latest = data_dir / nursery / 'latest.json'
        if not latest.exists():
            continue
        with open(latest) as f:
            raw = json.load(f)

        nursery_name = NURSERY_NAMES.get(nursery, nursery)
        restrict = restriction_warning(nursery)
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
                    'slug': s.get('slug', sname.lower().replace(' ', '-')),
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
                'restrict': restrict,
            })
            species_data[sname]['nurseries'].add(nursery)

    if not species_data:
        print("No rare species found in stock — skipping rare.html")
        return

    now = datetime.now(timezone.utc)
    date_str = now.strftime('%d %B %Y')

    # Sort: hard-to-find first (by rarity score desc), then by product count desc
    def sort_key(item):
        sname, data = item
        slug = data['slug']
        score = rarity_scores.get(slug, {}).get("score", 0)
        return (-score, -len(data['products']))

    sorted_species = sorted(species_data.items(), key=sort_key)

    # Stats
    total_products = sum(len(d['products']) for d in species_data.values())

    # Card view-data. The template autoescapes each scraped product title and
    # URL (the escaping targets) plus the species/nursery names. highlight_badge
    # (data-driven rarity, populated on the VPS) and the more-link are prebuilt
    # safe HTML; sci_html is always empty today (the species data has no
    # scientific_name field) but kept faithful to the original.
    cards = []
    for sname, data in sorted_species:
        s = data['species']
        products = data['products']
        nursery_count = len(data['nurseries'])
        slug = data['slug']

        # Price range
        prices = [p['price'] for p in products if p['price']]
        if prices:
            min_p = min(prices)
            max_p = max(prices)
            price_str = f'${min_p:.0f}' if min_p == max_p else f'${min_p:.0f}–${max_p:.0f}'
        else:
            price_str = 'POA'

        # Highlight badge: data-driven from computed rarity score
        rarity = rarity_scores.get(slug, {})
        highlight_badge = ''
        if rarity.get('hard_to_find'):
            score = rarity.get('score', 0)
            label = 'Very rare' if score >= 80 else 'Hard to find'
            highlight_badge = f'<span class="rare-badge">{label}</span>'

        # Product rows (up to 6 per species), price-sorted
        show_products = sorted(products, key=lambda x: (x['price'] or 999))
        prod_rows = [
            {
                'url': p['url'],
                'title': p['title'],
                'nursery_url': p['nursery_url'],
                'nursery_name': p['nursery_name'],
                'restrict': p['restrict'],
                'price': p['price'],
            }
            for p in show_products[:6]
        ]

        more_html = ''
        if len(products) > 6:
            more_html = f'<p class="more-link"><a href="/species/{slug}.html">See all {len(products)} listings →</a></p>'

        sci_name = s.get('scientific_name', '')
        sci_html = f'<span class="sci-name">{sci_name}</span>' if sci_name else ''

        cards.append({
            'slug': slug,
            'sname': sname,
            'highlight_badge': highlight_badge,
            'sci_html': sci_html,
            'product_count': len(products),
            'nursery_count': nursery_count,
            'nursery_noun': 'nursery' if nursery_count == 1 else 'nurseries',
            'price_str': price_str,
            'prod_rows': prod_rows,
            'more_html': more_html,
        })

    species_count = len(species_data)

    extra_style = """\
  .restrict-badge { background: #fee2e2; color: #991b1b; padding: 1px 6px; border-radius: 4px; font-size: 0.65rem; }
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
        og_description=f"{total_products} rare &amp; exotic fruit trees in stock across {species_count} species. Updated daily at treestock.com.au",
        og_image="https://treestock.com.au/og-image.png",
        extra_style=extra_style,
    )
    header = render_header(
        active_path="/rare.html",
    )
    footer = render_footer()

    html = render_template(
        "rare_page.html.j2",
        head=head, header=header, footer=footer,
        species_count=species_count, total_products=total_products,
        date_str=date_str, cards=cards, nursery_total=len(NURSERY_NAMES),
    )

    out_path = output_dir / 'rare.html'
    with open(out_path, 'w') as f:
        f.write(html)

    print(f"Built {out_path}")
    print(f"  {species_count} rare species, {total_products} products")
    return species_count, total_products


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <data_dir> <output_dir>")
        sys.exit(1)
    build_rare_page(sys.argv[1], sys.argv[2])
