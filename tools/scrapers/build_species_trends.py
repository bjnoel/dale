#!/usr/bin/env python3
"""
Build species availability and price trend page for treestock.com.au.

Processes all historical daily snapshots (from first scrape date) and generates:
- Per-species 30-day availability trend (in-stock count per day)
- Per-species 30-day price trend (min price per day)
- A market intelligence page at /trends.html

Run daily after scrapers. Takes ~5-10s to load historical data.

Usage:
    python3 build_species_trends.py <data_dir> <output_dir>
    python3 build_species_trends.py /opt/dale/data/nursery-stock /opt/dale/dashboard
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from treestock_layout import render_head, render_header, render_footer, render_breadcrumb

DATA_DIR = Path("/opt/dale/data/nursery-stock")
FRUIT_SPECIES = Path(__file__).parent / "fruit_species.json"
OUTPUT_DIR = Path("/opt/dale/dashboard")

NON_PLANT_KEYWORDS = {"fertiliser", "fertilizer", "potting mix", "soil", "spray", "book", "guide",
                      "label", "tool", "bag", "pot", "glove", "support", "stake", "wire"}


def load_species():
    with open(FRUIT_SPECIES) as f:
        return json.load(f)


def build_lookup(species_list):
    lookup = {}
    for s in species_list:
        lookup[s["common_name"].lower()] = s
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = s
    return lookup


def match_title(title: str, lookup: dict):
    title_lower = title.lower()
    words = re.split(r'[\s\-\u2013\u2014]+', title_lower)
    for n in range(min(len(words), 5), 0, -1):
        candidate = " ".join(words[:n])
        if candidate in lookup:
            return lookup[candidate]
    return None


def get_all_dates(data_dir: Path) -> list[str]:
    """Return all unique dates across all nursery snapshots, sorted."""
    dates = set()
    for nursery_dir in data_dir.iterdir():
        if not nursery_dir.is_dir():
            continue
        for jf in nursery_dir.glob("2026-*.json"):
            dates.add(jf.stem)
    return sorted(dates)


def build_species_trends(data_dir: Path):
    """
    Load all historical snapshots and compute per-species, per-day availability and price.

    Returns:
        all_dates: sorted list of date strings
        species_data: {species_slug: {date: {in_stock: N, min_price: X, total: N}}}
    """
    species_list = load_species()
    lookup = build_lookup(species_list)
    slug_set = {s["slug"] for s in species_list}

    all_dates = get_all_dates(data_dir)
    # Keep last 35 days max
    all_dates = all_dates[-35:]

    # {species_slug: {date: {in_stock: N, min_price: X, total: N}}}
    species_data: dict[str, dict[str, dict]] = {s["slug"]: {} for s in species_list}

    for date in all_dates:
        # Aggregate across nurseries for this date
        day_species: dict[str, list] = {s["slug"]: [] for s in species_list}

        for nursery_dir in sorted(data_dir.iterdir()):
            if not nursery_dir.is_dir():
                continue
            jf = nursery_dir / f"{date}.json"
            if not jf.exists():
                continue
            with open(jf) as f:
                d = json.load(f)
            for p in d.get("products", []):
                title = p.get("title", "")
                title_lower = title.lower()
                if any(kw in title_lower for kw in NON_PLANT_KEYWORDS):
                    continue
                if re.search(r'\bseeds?\b', title_lower) and 'seedling' not in title_lower and 'seedless' not in title_lower:
                    continue
                species = match_title(title, lookup)
                if not species:
                    continue
                slug = species["slug"]
                available = bool(p.get("any_available", p.get("available", False)))
                min_price = p.get("min_price")
                if min_price is None:
                    variants = p.get("variants", [])
                    prices = [float(v["price"]) for v in variants if v.get("price")]
                    min_price = min(prices) if prices else None

                day_species[slug].append({
                    "available": available,
                    "price": float(min_price) if min_price else None,
                })

        # Summarise each species for this date
        for slug, items in day_species.items():
            if not items:
                continue
            in_stock = sum(1 for i in items if i["available"])
            prices = [i["price"] for i in items if i["price"] is not None and i["available"]]
            min_price = min(prices) if prices else None
            species_data[slug][date] = {
                "in_stock": in_stock,
                "total": len(items),
                "min_price": round(min_price, 2) if min_price else None,
            }

    return all_dates, species_data


def make_sparkline(values: list[float | None], width: int = 80, height: int = 24, color: str = "#16a34a") -> str:
    """Generate an inline SVG sparkline for a list of values."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'

    lo = min(clean)
    hi = max(clean)
    span = hi - lo if hi != lo else 1

    points = []
    n = len(values)
    for i, v in enumerate(values):
        if v is None:
            continue
        x = int(i / (n - 1) * (width - 4)) + 2
        y = int((1 - (v - lo) / span) * (height - 4)) + 2
        points.append((x, y))

    if len(points) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'

    path = "M " + " L ".join(f"{x},{y}" for x, y in points)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'class="inline-block align-middle">'
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f'</svg>'
    )


def trend_direction(values: list[float | None]) -> str:
    """Return 'up', 'down', or 'flat' based on recent trend."""
    clean = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(clean) < 4:
        return "flat"
    # Compare last 7 days average vs previous 7 days
    recent = [v for _, v in clean[-7:]]
    prior = [v for _, v in clean[-14:-7]]
    if not prior:
        return "flat"
    avg_recent = sum(recent) / len(recent)
    avg_prior = sum(prior) / len(prior)
    diff_pct = (avg_recent - avg_prior) / (avg_prior + 0.001)
    if diff_pct > 0.1:
        return "up"
    if diff_pct < -0.1:
        return "down"
    return "flat"


def build_page(all_dates: list[str], species_data: dict, output_dir: Path):
    species_list = load_species()

    # Compute summary stats per species
    summaries = []
    for s in species_list:
        slug = s["slug"]
        name = s["common_name"]
        dates_data = species_data.get(slug, {})

        # Build value series aligned to all_dates
        stock_series = [dates_data.get(d, {}).get("in_stock") for d in all_dates]
        price_series = [dates_data.get(d, {}).get("min_price") for d in all_dates]

        # Current stats
        latest = next(
            (dates_data[d] for d in reversed(all_dates) if d in dates_data), None
        )
        in_stock_now = latest["in_stock"] if latest else 0
        min_price_now = latest["min_price"] if latest else None

        stock_direction = trend_direction(stock_series)
        price_direction = trend_direction(price_series)

        # Availability rate: % days this species had any stock
        days_in_stock = sum(1 for v in stock_series if v and v > 0)
        availability_pct = int(days_in_stock / len(all_dates) * 100) if all_dates else 0

        summaries.append({
            "slug": slug,
            "name": name,
            "in_stock_now": in_stock_now,
            "min_price_now": min_price_now,
            "stock_series": stock_series,
            "price_series": price_series,
            "stock_direction": stock_direction,
            "price_direction": price_direction,
            "availability_pct": availability_pct,
            "days_in_stock": days_in_stock,
        })

    # Sort: most in stock now first, then alphabetical
    summaries_by_stock = sorted(summaries, key=lambda x: (-x["in_stock_now"], x["name"]))

    # "Buy now" signals: high availability, price dropping or flat
    buy_now = [s for s in summaries_by_stock if s["in_stock_now"] > 0 and s["price_direction"] in ("down", "flat") and s["availability_pct"] >= 60][:6]

    # "Act fast": low availability but in stock now (rare, grab it)
    act_fast = [s for s in summaries_by_stock if s["in_stock_now"] > 0 and s["availability_pct"] < 30][:6]

    # "Coming back": stock trending up
    trending_up = [s for s in summaries_by_stock if s["stock_direction"] == "up" and s["in_stock_now"] > 0][:8]

    date_range = f"{all_dates[0]} to {all_dates[-1]}" if all_dates else "N/A"
    days_count = len(all_dates)

    arrow = {"up": "↑", "down": "↓", "flat": "→"}
    arrow_color = {"up": "text-green-600", "down": "text-red-500", "flat": "text-gray-400"}

    def signal_card(s: dict) -> str:
        spark = make_sparkline(s["stock_series"], width=60, height=20)
        price_str = f"from ${s['min_price_now']:.0f}" if s["min_price_now"] else "price varies"
        return f"""
      <a href="/species/{s['slug']}.html" class="block p-3 bg-white border border-gray-200 rounded-lg hover:border-green-300 no-underline transition-colors">
        <div class="flex items-center justify-between gap-2 mb-1">
          <span class="font-medium text-gray-900 text-sm">{s['name']}</span>
          {spark}
        </div>
        <div class="text-xs text-gray-500">{s['in_stock_now']} in stock &middot; {price_str}</div>
      </a>"""

    buy_now_html = "".join(signal_card(s) for s in buy_now) if buy_now else "<p class='text-sm text-gray-400'>No clear signals yet. Check back as more data accumulates.</p>"
    act_fast_html = "".join(signal_card(s) for s in act_fast) if act_fast else "<p class='text-sm text-gray-400'>No rare in-stock species right now.</p>"
    trending_html = "".join(signal_card(s) for s in trending_up) if trending_up else "<p class='text-sm text-gray-400'>No species with notably rising stock right now.</p>"

    # Full species table
    rows = []
    for s in summaries_by_stock:
        stock_spark = make_sparkline(s["stock_series"], width=80, height=22)
        price_spark_color = "#dc2626" if s["price_direction"] == "up" else "#16a34a"
        price_spark = make_sparkline(s["price_series"], width=60, height=22, color=price_spark_color)
        stock_arrow = arrow[s["stock_direction"]]
        stock_class = arrow_color[s["stock_direction"]]
        price_arrow = arrow[s["price_direction"]]
        price_class = arrow_color[s["price_direction"]]
        avail_class = "text-green-700" if s["availability_pct"] >= 70 else ("text-amber-600" if s["availability_pct"] >= 30 else "text-red-500")
        price_str = f"${s['min_price_now']:.0f}" if s["min_price_now"] else "—"
        rows.append(f"""
        <tr class="border-b border-gray-100 hover:bg-gray-50">
          <td class="py-2 pr-3 text-sm font-medium"><a href="/species/{s['slug']}.html" class="text-gray-900 hover:text-green-700 no-underline">{s['name']}</a></td>
          <td class="py-2 pr-3 text-sm text-right font-semibold {'text-green-700' if s['in_stock_now'] > 0 else 'text-gray-400'}">{s['in_stock_now']}</td>
          <td class="py-2 pr-3">{stock_spark} <span class="text-xs {stock_class}">{stock_arrow}</span></td>
          <td class="py-2 pr-3 text-sm text-gray-600">{price_str} <span class="text-xs {price_class}">{price_arrow}</span></td>
          <td class="py-2 pr-3">{price_spark}</td>
          <td class="py-2 text-xs {avail_class}">{s['availability_pct']}%</td>
        </tr>""")

    table_html = "\n".join(rows)

    head = render_head(
        title="Species Trends — treestock.com.au Market Intelligence",
        description=f"30-day availability and price trends for 50 fruit tree species across 19 Australian nurseries. Data from {date_range}.",
        canonical_url="https://treestock.com.au/trends.html",
    )
    header = render_header(active_path="/trends.html")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Market Trends", "/trends.html")])
    footer = render_footer()

    html = f"""{head}
{header}
<main class="max-w-3xl mx-auto px-4 py-6">
{breadcrumb}
  <div class="mb-6">
    <h1 class="text-3xl font-bold text-green-900 mb-2">Market Trends</h1>
    <p class="text-gray-600 mb-3">
      Availability and price trends for 50 species across 19 Australian nurseries.
      Updated daily. {days_count} days of data ({date_range}).
    </p>
    <p class="text-xs text-gray-400">
      Trends compare last 7 days vs prior 7 days. ↑ = rising, ↓ = falling, → = stable.
      Availability % = days this species had any stock in the tracked period.
    </p>
  </div>

  <!-- Buy now signals -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold text-gray-800 mb-1">Good time to buy</h2>
    <p class="text-sm text-gray-500 mb-3">Well-stocked species with stable or falling prices.</p>
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {buy_now_html}
    </div>
  </section>

  <!-- Act fast -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold text-gray-800 mb-1">Act fast</h2>
    <p class="text-sm text-gray-500 mb-3">Rare species that are in stock now but hard to find (in stock less than 30% of tracked days).</p>
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {act_fast_html}
    </div>
  </section>

  <!-- Trending up -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold text-gray-800 mb-1">Stock trending up</h2>
    <p class="text-sm text-gray-500 mb-3">Species with more stock available recently than last week.</p>
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {trending_html}
    </div>
  </section>

  <!-- Full table -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold text-gray-800 mb-3">All species</h2>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
            <th class="pb-2 pr-3">Species</th>
            <th class="pb-2 pr-3 text-right">In stock</th>
            <th class="pb-2 pr-3">30-day stock</th>
            <th class="pb-2 pr-3">Price</th>
            <th class="pb-2 pr-3">30-day price</th>
            <th class="pb-2">Avail.</th>
          </tr>
        </thead>
        <tbody>
          {table_html}
        </tbody>
      </table>
    </div>
    <p class="text-xs text-gray-400 mt-3">
      Availability = % of days tracked that species had at least one product in stock.
      Price shown is current lowest available price across all nurseries.
    </p>
  </section>

  <section class="p-4 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-600">
    <p class="font-medium text-gray-700 mb-1">About this data</p>
    <p>
      treestock.com.au scrapes 19 Australian nurseries daily. This page shows {days_count} days of accumulated
      data (since {all_dates[0] if all_dates else 'launch'}). Seasonal patterns become clearer with 90+ days.
      Check back monthly for stronger signals.
    </p>
  </section>
</main>
{footer}
</html>
"""

    out = output_dir / "trends.html"
    out.write_text(html, encoding="utf-8")
    print(f"Built trends.html ({len(all_dates)} days, {len(species_list)} species, {out.stat().st_size // 1024}KB)")


def main():
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT_DIR

    print("Loading historical data (this may take a few seconds)...")
    all_dates, species_data = build_species_trends(data_dir)
    print(f"Loaded {len(all_dates)} days of data")
    build_page(all_dates, species_data, output_dir)


if __name__ == "__main__":
    main()
