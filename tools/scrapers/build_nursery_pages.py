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

from shipping import SHIPPING_MAP, NURSERY_NAMES

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
        "url": "https://www.ausnurseries.com.au",
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
        "description": "Heritage Fruit Trees is a Victorian specialist nursery carrying one of Australia's largest collections of heritage and heirloom temperate fruit trees. Based in Beaufort, VIC, they stock hundreds of apple, pear, plum, cherry, quince, and nut tree varieties including many rare cultivars unavailable elsewhere. They ship to WA during the dormant/winter season (approximately May to September).",
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


NAV = """    <nav class="navbar navbar-light bg-white border-bottom">
        <div class="container">
            <a class="navbar-brand fw-bold" href="/">🌱 treestock.com.au</a>
            <div class="d-flex gap-3 align-items-center">
                <a href="/species/" class="text-muted small">Browse Species</a>
                <a href="/nursery/" class="text-muted small">Nurseries</a>
                <a href="/digest.html" class="text-muted small">Daily Digest</a>
            </div>
        </div>
    </nav>"""


def build_nursery_page(nursery_key: str, data: dict, species_lookup: dict) -> str:
    meta = NURSERY_META.get(nursery_key, {})
    name = NURSERY_NAMES.get(nursery_key, data.get("nursery_name", nursery_key))
    location = data.get("location", "Australia")
    url = meta.get("url", "")
    tags = meta.get("tags", [])
    description = meta.get("description", "")
    ships = sorted(SHIPPING_MAP.get(nursery_key, []))
    wa = ships_to_wa(nursery_key)

    products = data.get("products", [])
    in_stock_count = data.get("in_stock_count", sum(1 for p in products if p.get("any_available")))
    total_count = data.get("product_count", len(products))

    species_breakdown = build_species_breakdown(products, species_lookup)
    species_count = len(species_breakdown)

    wa_badge = '<span class="badge bg-success ms-2">Ships to WA</span>' if wa else '<span class="badge bg-warning text-dark ms-2">Does not ship to WA</span>'
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

    in_stock_products = [p for p in products if p.get("any_available")][:20]
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

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{name} — Stock, Prices &amp; Shipping | treestock.com.au</title>
    <meta name="description" content="Browse {name}'s current fruit tree stock. {total_count} products tracked, {in_stock_count} in stock. Ships to: {', '.join(ships)}.">
    <meta property="og:title" content="{name} — Stock, Prices &amp; Shipping">
    <meta property="og:description" content="Browse {name}'s current fruit tree stock. {total_count} products tracked, {in_stock_count} in stock. Ships to: {', '.join(ships)}.">
    <meta property="og:url" content="https://treestock.com.au/nursery/{nursery_key}.html">
    <meta property="og:type" content="website">
    <link rel="canonical" href="https://treestock.com.au/nursery/{nursery_key}.html">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <link rel="icon" href="/favicon.svg" type="image/svg+xml">
    <script defer data-domain="treestock.com.au" src="https://data.bjnoel.com/js/script.js"></script>
    <style>
        body {{ background: #f8f9fa; }}
        .nursery-header {{ background: white; border-bottom: 1px solid #dee2e6; padding: 2rem 0; }}
        .stat-card {{ background: white; border-radius: 8px; border: 1px solid #dee2e6; padding: 1.2rem; text-align: center; }}
        .stat-card .number {{ font-size: 2rem; font-weight: 700; color: #198754; }}
        .stat-card .label {{ font-size: 0.85rem; color: #6c757d; }}
        table {{ background: white; }}
        .back-link {{ color: #6c757d; text-decoration: none; font-size: 0.9rem; }}
        .back-link:hover {{ color: #000; }}
        footer {{ color: #6c757d; font-size: 0.85rem; }}
    </style>
</head>
<body>
{NAV}

    <div class="nursery-header">
        <div class="container">
            <a href="/nursery/" class="back-link mb-2 d-inline-block">← All Nurseries</a>
            <h1 class="mb-1">{name} {wa_badge}</h1>
            <p class="text-muted mb-2">
                {location_line}
            </p>
            <div class="mb-2">{tag_badges}</div>
            <div>Ships to: {ship_badges}</div>
        </div>
    </div>

    <div class="container py-4">
        <div class="row g-3 mb-4">
            <div class="col-6 col-md-3">
                <div class="stat-card">
                    <div class="number">{in_stock_count}</div>
                    <div class="label">In Stock</div>
                </div>
            </div>
            <div class="col-6 col-md-3">
                <div class="stat-card">
                    <div class="number">{total_count}</div>
                    <div class="label">Products Tracked</div>
                </div>
            </div>
            <div class="col-6 col-md-3">
                <div class="stat-card">
                    <div class="number">{species_count}</div>
                    <div class="label">Species</div>
                </div>
            </div>
            <div class="col-6 col-md-3">
                <div class="stat-card">
                    <div class="number">{wa_stat}</div>
                    <div class="label">Ships to WA</div>
                </div>
            </div>
        </div>

        <div class="card mb-4"><div class="card-body"><p class="mb-0">{description}</p></div></div>

        <div class="row g-4">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <strong>Species Carried</strong>
                        <span class="text-muted small">{species_count} species</span>
                    </div>
                    <div class="table-responsive" style="max-height: 420px; overflow-y: auto;">
                        <table class="table table-sm table-hover mb-0">
                            <thead class="table-light sticky-top">
                                <tr>
                                    <th>Species</th>
                                    <th class="text-muted fst-italic">Latin name</th>
                                    <th class="text-center">In Stock</th>
                                    <th class="text-center">Total</th>
                                </tr>
                            </thead>
                            <tbody>
                                {species_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <strong>In Stock Now</strong>
                        <a href="/?nursery={nursery_key}" class="btn btn-sm btn-outline-success">View all on dashboard →</a>
                    </div>
                    <div class="table-responsive" style="max-height: 420px; overflow-y: auto;">
                        <table class="table table-sm table-hover mb-0">
                            <thead class="table-light sticky-top">
                                <tr>
                                    <th>Product</th>
                                    <th class="text-end">Price</th>
                                </tr>
                            </thead>
                            <tbody>
                                {product_rows}
                            </tbody>
                        </table>
                    </div>
                    <div class="card-footer text-muted small">Showing top 20 in-stock products. <a href="/?nursery={nursery_key}">See all →</a></div>
                </div>
            </div>
        </div>

        <p class="text-muted small mt-4">Data updated daily. Last checked: {scraped_at_fmt}.</p>
    </div>

    <footer class="border-top py-3 mt-4">
        <div class="container">
            <a href="/nursery/" class="text-muted me-3">All Nurseries</a>
            <a href="/species/" class="text-muted me-3">Browse Species</a>
            <a href="/" class="text-muted me-3">Dashboard</a>
            <a href="/digest.html" class="text-muted">Daily Digest</a>
        </div>
    </footer>
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
        wa = ships_to_wa(key)
        in_stock = data.get("in_stock_count", 0)
        total = data.get("product_count", len(data.get("products", [])))
        location = data.get("location", "Australia")

        wa_badge = '<span class="badge bg-success">Ships WA</span>' if wa else '<span class="badge bg-warning text-dark">No WA</span>'
        tag_badges = " ".join(f'<span class="badge bg-light text-dark border small">{t}</span>' for t in tags[:3])
        ship_str = ", ".join(ships)

        cards += f"""
        <div class="col-md-6 col-lg-4">
            <div class="card h-100">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-1">
                        <h5 class="card-title mb-0">
                            <a href="/nursery/{key}.html" class="text-decoration-none text-dark">{name}</a>
                        </h5>
                        {wa_badge}
                    </div>
                    <p class="text-muted small mb-2">📍 {location}</p>
                    <div class="mb-2">{tag_badges}</div>
                    <p class="small text-muted mb-1">
                        <strong>{in_stock}</strong> in stock &middot; {total} tracked
                    </p>
                    <p class="small text-muted mb-0">Ships to: {ship_str}</p>
                </div>
                <div class="card-footer bg-transparent border-top-0">
                    <a href="/nursery/{key}.html" class="btn btn-sm btn-outline-success w-100">View Nursery →</a>
                </div>
            </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Australian Fruit Tree Nurseries — Stock &amp; Shipping | treestock.com.au</title>
    <meta name="description" content="Browse all {count} Australian fruit tree nurseries tracked by treestock.com.au. Compare stock, prices, and shipping to your state including WA.">
    <meta property="og:title" content="Australian Fruit Tree Nurseries — treestock.com.au">
    <meta property="og:url" content="https://treestock.com.au/nursery/">
    <link rel="canonical" href="https://treestock.com.au/nursery/">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
    <link rel="icon" href="/favicon.svg" type="image/svg+xml">
    <script defer data-domain="treestock.com.au" src="https://data.bjnoel.com/js/script.js"></script>
    <style>
        body {{ background: #f8f9fa; }}
        .card {{ transition: box-shadow 0.2s; }}
        .card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.12); }}
    </style>
</head>
<body>
{NAV}

    <div class="container py-4">
        <h1 class="mb-1">Australian Fruit Tree Nurseries</h1>
        <p class="text-muted mb-4">
            Daily stock tracking across {count} nurseries. Updated {today}.
        </p>

        <div class="row g-3">
            {cards}
        </div>
    </div>

    <footer class="border-top py-3 mt-4">
        <div class="container">
            <a href="/" class="text-muted me-3">Dashboard</a>
            <a href="/species/" class="text-muted me-3">Browse Species</a>
            <a href="/digest.html" class="text-muted">Daily Digest</a>
        </div>
    </footer>
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
        page = build_nursery_page(key, data, species_lookup)
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
