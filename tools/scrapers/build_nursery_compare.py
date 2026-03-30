#!/usr/bin/env python3
"""
Build nursery comparison table page for treestock.com.au.

Generates /compare/nurseries.html — a side-by-side comparison of all tracked nurseries.
Targets queries: "compare fruit tree nurseries Australia", "best online fruit tree nursery",
                 "fruit tree nurseries that ship to WA", "cheapest fruit tree nursery Australia"

Usage:
    python3 build_nursery_compare.py /path/to/data/nursery-stock /path/to/dashboard/
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from shipping import SHIPPING_MAP, NURSERY_NAMES, restriction_warning, LOCAL_DELIVERY, delivery_label
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer

SPECIES_FILE = Path(__file__).parent / "fruit_species.json"


def load_species_lookup() -> dict:
    if not SPECIES_FILE.exists():
        return {}
    with open(SPECIES_FILE) as f:
        species = json.load(f)
    lookup = {}
    for s in species:
        common = s["common_name"].lower()
        entry = {"cn": s["common_name"], "sl": s["slug"]}
        lookup[common] = entry
        for alias in s.get("aliases", []):
            lookup[alias.lower()] = entry
    return lookup


def count_species(products: list, species_lookup: dict) -> int:
    """Count distinct species in a nursery's product list."""
    found = set()
    for p in products:
        title = p.get("title", "").lower()
        for term, entry in species_lookup.items():
            if term and term in title:
                found.add(entry["cn"])
                break
    return len(found)


def load_nursery_data(data_dir: Path) -> dict:
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


def build_compare_page(nurseries_data: dict, species_lookup: dict, today: str) -> str:
    """Build the nursery comparison table page."""

    # Compile row data for each nursery
    rows = []
    for key, data in nurseries_data.items():
        name = NURSERY_NAMES.get(key, data.get("nursery_name", key))
        ships = sorted(SHIPPING_MAP.get(key, []))
        wa = "WA" in ships
        in_stock = data.get("in_stock_count", 0)
        total = data.get("product_count", len(data.get("products", [])))
        products = data.get("products", [])
        species_count = count_species(products, species_lookup)
        restrict = restriction_warning(key)
        location = data.get("location", "Australia")
        pct = round(100 * in_stock / total) if total else 0

        rows.append({
            "key": key,
            "name": name,
            "in_stock": in_stock,
            "total": total,
            "pct": pct,
            "species": species_count,
            "wa": wa,
            "ships": ships,
            "restrict": restrict,
            "location": location,
        })

    # Sort by in-stock count descending
    rows.sort(key=lambda r: (-r["in_stock"], -r["total"]))

    total_nurseries = len(rows)

    # Build table rows
    table_rows = ""
    for i, r in enumerate(rows):
        local_lbl = delivery_label(r["key"])
        if r["wa"] and local_lbl:
            wa_cell = f'<span class="text-amber-700 font-semibold">{local_lbl}</span>'
        elif r["wa"]:
            wa_cell = '<span class="text-green-700 font-semibold">Yes</span>'
        else:
            wa_cell = '<span class="text-red-600">No</span>'
        restrict_cell = "" if local_lbl else (f'<span class="text-xs text-red-700">{r["restrict"]}</span>' if r["restrict"] else "")
        ship_str = local_lbl if local_lbl else (", ".join(r["ships"]) if r["ships"] else "Unknown")
        pct_bar = f'<div class="w-full bg-gray-100 rounded-full h-1.5 mt-1"><div class="bg-green-500 h-1.5 rounded-full" style="width:{r["pct"]}%"></div></div>'
        row_bg = "bg-white" if i % 2 == 0 else "bg-gray-50"

        table_rows += f"""
        <tr class="{row_bg} hover:bg-green-50 border-b border-gray-100">
          <td class="py-2 px-3 text-sm">
            <a href="/nursery/{r['key']}.html" class="text-green-700 hover:underline font-medium">{r['name']}</a>
            {('<br><span class="text-xs text-gray-400">' + r['location'] + '</span>') if r['location'] else ''}
          </td>
          <td class="py-2 px-3 text-center">
            <span class="font-semibold text-green-700">{r['in_stock']}</span>
            <span class="text-xs text-gray-400"> / {r['total']}</span>
            {pct_bar}
          </td>
          <td class="py-2 px-3 text-center text-sm">{r['species']}</td>
          <td class="py-2 px-3 text-center text-sm">{wa_cell}</td>
          <td class="py-2 px-3 text-xs text-gray-600">{ship_str} {restrict_cell}</td>
        </tr>"""

    # Summary stats
    wa_count = sum(1 for r in rows if r["wa"])
    total_in_stock = sum(r["in_stock"] for r in rows)
    total_products = sum(r["total"] for r in rows)

    extra_style = """\
  table { border-collapse: collapse; width: 100%; }
  .filter-btn { cursor: pointer; }
  .filter-btn.active { background-color: #065f46; color: white; }
  tr.hidden-row { display: none; }"""

    head = render_head(
        title="Compare Australian Fruit Tree Nurseries | treestock.com.au",
        description=f"Side-by-side comparison of {total_nurseries} Australian fruit tree nurseries. See stock levels, species range, prices, and shipping to WA and all states.",
        canonical_url="https://treestock.com.au/compare/nurseries.html",
        og_title="Compare Australian Fruit Tree Nurseries",
        og_description=f"Compare {total_nurseries} nurseries: stock levels, species range, and shipping to your state. Updated daily.",
        og_type="website",
        extra_style=extra_style,
    )
    header_html = render_header(active_path="/compare/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Compare", "/compare/"), ("Nurseries", "")])
    footer = render_footer()

    return f"""{head}
{header_html}

<main class="max-w-5xl mx-auto px-4 py-6">
  {breadcrumb}

  <h1 class="text-2xl font-bold text-gray-900 mb-1">Compare Australian Fruit Tree Nurseries</h1>
  <p class="text-gray-500 text-sm mb-4">
    {total_nurseries} nurseries tracked, {total_in_stock:,} products in stock across {total_products:,} tracked.
    {wa_count} nurseries ship to WA. Updated {today}.
  </p>

  <div class="flex flex-wrap gap-2 mb-4">
    <button class="filter-btn active text-xs px-3 py-1.5 rounded border border-gray-300 hover:border-green-600"
            onclick="filterNurseries('all', this)">All nurseries</button>
    <button class="filter-btn text-xs px-3 py-1.5 rounded border border-gray-300 hover:border-green-600"
            onclick="filterNurseries('wa', this)">Ships to WA</button>
    <button class="filter-btn text-xs px-3 py-1.5 rounded border border-gray-300 hover:border-green-600"
            onclick="filterNurseries('instock', this)">50+ in stock</button>
  </div>

  <div class="overflow-x-auto rounded-lg border border-gray-200">
    <table id="nursery-table" class="w-full text-left">
      <thead>
        <tr class="bg-gray-50 border-b border-gray-200 text-xs text-gray-500 uppercase">
          <th class="py-2 px-3">Nursery</th>
          <th class="py-2 px-3 text-center">In Stock / Total</th>
          <th class="py-2 px-3 text-center">Species</th>
          <th class="py-2 px-3 text-center">Ships to WA</th>
          <th class="py-2 px-3">States</th>
        </tr>
      </thead>
      <tbody id="nursery-tbody">
        {table_rows}
      </tbody>
    </table>
  </div>

  <div class="mt-6 bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm text-gray-700">
    <h2 class="font-semibold mb-2">About this comparison</h2>
    <p class="mb-2">This table compares all nurseries tracked by treestock.com.au on stock depth, species range, and shipping reach. Data is updated daily from each nursery's website.</p>
    <p class="mb-2"><strong>In Stock / Total:</strong> How many products are currently available vs the full range tracked. The progress bar shows the in-stock percentage.</p>
    <p class="mb-2"><strong>Species:</strong> The number of distinct fruit species (e.g., mango, avocado, lychee) stocked by that nursery, regardless of variety count.</p>
    <p><strong>Ships to WA:</strong> Western Australia has strict biosecurity requirements, so not all interstate nurseries can ship there. Nurseries marked Yes either ship directly to WA or have a WA partner arrangement.</p>
  </div>

  <div class="mt-4 text-xs text-gray-400">
    See also: <a href="/compare/" class="text-green-700 hover:underline">price comparisons by species</a> |
    <a href="/nursery/" class="text-green-700 hover:underline">individual nursery profiles</a>
  </div>
</main>

<script>
function filterNurseries(filter, btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const rows = document.querySelectorAll('#nursery-tbody tr');
  rows.forEach(row => {{
    const wa = row.querySelector('td:nth-child(4)')?.textContent.trim().toLowerCase() === 'yes';
    const instock = parseInt(row.querySelector('td:nth-child(2) .font-semibold')?.textContent || '0');
    if (filter === 'all') row.classList.remove('hidden-row');
    else if (filter === 'wa') row.classList.toggle('hidden-row', !wa);
    else if (filter === 'instock') row.classList.toggle('hidden-row', instock < 50);
  }});
}}
</script>

{footer}

</body>
</html>"""


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <data_dir> <output_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    compare_dir = output_dir / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    species_lookup = load_species_lookup()
    nurseries_data = load_nursery_data(data_dir)

    if not nurseries_data:
        print("No nursery data found.")
        sys.exit(1)

    page = build_compare_page(nurseries_data, species_lookup, today)
    out = compare_dir / "nurseries.html"
    out.write_text(page)
    print(f"Built nursery comparison page: {out}")
    print(f"  {len(nurseries_data)} nurseries compared")


if __name__ == "__main__":
    main()
