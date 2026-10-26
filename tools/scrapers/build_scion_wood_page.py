#!/usr/bin/env python3
"""
Build the scion wood page (/scion-wood.html) for treestock.com.au.

Scion wood and unrooted cuttings are propagation material, not trees: Daleys
sells "Scion Wood Apple - Gala" at $9.75 against $40+ for the tree. In a
species price table they read as the cheapest tree, so every tree surface
drops them (stocklib.classify.is_propagation_material, applied by in_scope)
and they list here instead, all species on one page (Benedict, 2026-10-26).

Grouped by species, each with an anchor (#apple) that species pages link to.
Sold-out listings stay visible: scion wood is cut in winter and sells out
fast, so who sells it matters more than what is in stock tonight.

The nursery's own category is deliberately NOT consulted (Daleys files scion
wood under "Gardening Tools - Accessories"); the title is the evidence.

Usage:
    python3 build_scion_wood_page.py /path/to/data/nursery-stock /path/to/output/ [--today YYYY-MM-DD]
"""

import argparse
import html
from datetime import date, datetime, timezone
from pathlib import Path

from stocklib.classify import is_propagation_material, is_real_product
from stocklib.registry import NURSERY_NAMES
from stocklib.snapshots import iter_nursery_snapshots
from stocklib.species_match import build_species_lookup, match_title
from stocklib.templates import render as render_template
from stocklib.utm import outbound
from treestock_layout import render_breadcrumb, render_footer, render_head, render_header

from build_bare_root_page import _fmt_price, _product_available, _product_price, _shipping_cell

PAGE_PATH = "/scion-wood.html"
OTHER_SLUG = "other"


def collect_scion_wood(data_dir, today: str | None = None) -> list[dict]:
    """Every scion wood / cuttings listing in today's snapshots, as flat rows
    carrying the species slug and name (None for unmatched)."""
    lookup = build_species_lookup()
    rows = []
    for nursery_key, snap in iter_nursery_snapshots(data_dir, today):
        for p in snap.get("products", []):
            title = p.get("title", "")
            if not is_propagation_material(title) or not is_real_product(title):
                continue
            species = match_title(title, lookup)
            rows.append({
                "title": title,
                "url": outbound(p.get("url", ""), "scion-wood"),
                "nursery_key": nursery_key,
                "nursery": NURSERY_NAMES.get(nursery_key, snap.get("nursery_name", nursery_key)),
                "price": _product_price(p),
                "available": _product_available(p),
                "species_slug": species["slug"] if species else None,
                "species_name": species["common_name"] if species else None,
            })
    return rows


def counts_by_species(rows: list[dict]) -> dict[str, dict]:
    """slug -> {"total", "in_stock"}, for the species page link."""
    out: dict[str, dict] = {}
    for r in rows:
        if r["species_slug"]:
            c = out.setdefault(r["species_slug"], {"total": 0, "in_stock": 0})
            c["total"] += 1
            c["in_stock"] += r["available"]
    return out


def species_link_html(slug: str, counts: dict[str, dict], name: str) -> str:
    """One line for a species page, or "" when there is no scion wood."""
    c = counts.get(slug)
    if not c:
        return ""
    stock = f"{c['in_stock']} in stock" if c["in_stock"] else "none in stock right now"
    return (f'<p class="text-sm text-gray-600 mt-2">Grafting? <a href="{PAGE_PATH}#{slug}" '
            f'class="text-green-700 hover:underline">{html.escape(name)} scion wood and cuttings</a>: '
            f'{c["total"]} listed, {stock}.</p>')


def _sort_key(r: dict):
    return (not r["available"], r["price"] is None, r["price"] or 0, r["title"])


def build_groups(rows: list[dict]) -> list[dict]:
    """Species groups, most in-stock listings first; unmatched last."""
    groups: dict[str, dict] = {}
    for r in rows:
        slug = r["species_slug"] or OTHER_SLUG
        g = groups.setdefault(slug, {"slug": slug, "name": r["species_name"] or "Other", "rows": []})
        g["rows"].append(r)
    for g in groups.values():
        g["rows"].sort(key=_sort_key)
        g["in_stock"] = sum(r["available"] for r in g["rows"])
    return sorted(groups.values(),
                  key=lambda g: (g["slug"] == OTHER_SLUG, -g["in_stock"], g["name"]))


def build_group_html(g: dict) -> str:
    rows_html = []
    for r in g["rows"]:
        price = _fmt_price(r["price"]) if r["price"] else "POA"
        stock = ('<span class="text-green-700">In stock</span>' if r["available"]
                 else '<span class="text-gray-400">Sold out</span>')
        rows_html.append(
            f"""        <tr{'' if r['available'] else ' class="text-gray-500"'}>
          <td><a href="{html.escape(r['url'])}" rel="noopener nofollow" target="_blank" class="text-green-700 hover:underline">{html.escape(r['title'])}</a></td>
          <td><a href="/nursery/{r['nursery_key']}.html" class="text-gray-700 hover:underline">{html.escape(r['nursery'])}</a></td>
          <td class="whitespace-nowrap">{price}</td>
          <td>{stock}</td>
          <td>{_shipping_cell(r['nursery_key'])}</td>
        </tr>""")
    heading = html.escape(g["name"])
    if g["slug"] != OTHER_SLUG:
        heading = f'<a href="/species/{g["slug"]}.html" class="hover:underline">{heading}</a>'
    return f"""
<section class="mb-8" id="{g['slug']}">
  <h2 class="text-lg font-bold text-green-900 mb-2">{heading} <span class="text-sm font-normal text-gray-500">({g['in_stock']} of {len(g['rows'])} in stock)</span></h2>
  <div style="overflow-x:auto;">
    <table class="sw-table">
      <thead><tr><th>Listing</th><th>Nursery</th><th>Price</th><th>Stock</th><th>Shipping</th></tr></thead>
      <tbody>
{chr(10).join(rows_html)}
      </tbody>
    </table>
  </div>
</section>"""


EXTRA_STYLE = """\
  .sw-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  .sw-table th { background: #f3f4f6; color: #374151; font-weight: 600; padding: 9px 11px; text-align: left; border-bottom: 2px solid #e5e7eb; white-space: nowrap; }
  .sw-table td { padding: 8px 11px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }"""


def build_page(data_dir, today: date) -> str:
    rows = collect_scion_wood(data_dir, today.isoformat())
    groups = build_groups(rows)
    in_stock = sum(r["available"] for r in rows)
    nurseries = len({r["nursery_key"] for r in rows})
    jump = " &middot; ".join(
        f'<a href="#{g["slug"]}" class="text-green-700 hover:underline">{html.escape(g["name"])}</a>'
        for g in groups)

    head = render_head(
        title="Scion Wood and Cuttings for Sale in Australia - treestock.com.au",
        description="Fruit tree scion wood and cuttings from Australian nurseries in one place: apple, plum, cherry, fig, mulberry and more. Prices, stock and shipping limits, updated daily.",
        canonical_url=f"https://treestock.com.au{PAGE_PATH}",
        extra_style=EXTRA_STYLE,
        og_title="Scion Wood and Cuttings for Sale in Australia",
        og_description="Fruit tree scion wood and cuttings across Australian nurseries, updated daily.",
        og_image="https://treestock.com.au/og-image.png",
    )
    return render_template(
        "scion_wood_page.html.j2",
        head=head,
        header=render_header(active_path=PAGE_PATH),
        breadcrumb=render_breadcrumb([("Home", "/"), ("Scion Wood", "")]),
        footer=render_footer(),
        today=today.isoformat(),
        total=len(rows), in_stock=in_stock, nurseries=nurseries,
        jump_links=jump,
        groups_html="\n".join(build_group_html(g) for g in groups),
    )


def main():
    parser = argparse.ArgumentParser(description="Build the scion wood page")
    parser.add_argument("data_dir", help="Path to data/nursery-stock")
    parser.add_argument("out_dir", help="Output directory")
    parser.add_argument("--today", help="Build date YYYY-MM-DD (for deterministic tests)")
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    page = build_page(args.data_dir, today)
    out_file = out_dir / "scion-wood.html"
    out_file.write_text(page)
    print(f"Written: {out_file} ({len(page)} bytes)")


if __name__ == "__main__":
    main()
