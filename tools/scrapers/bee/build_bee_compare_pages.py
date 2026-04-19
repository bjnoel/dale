#!/usr/bin/env python3
"""
Build price comparison pages for beekeeping subcategories.

Each page answers: "Which retailer has the cheapest [subcategory] gear?"
Target keywords: "cheapest [sub] Australia", "compare [sub] prices",
                 "buy [sub] Australia online"

Generates /compare/{sub}-prices.html for subcategories with
multi-retailer coverage (>= MIN_RETAILERS).

Only uses snapshots from the last 3 days to avoid stale pricing.

Usage:
    python3 build_bee_compare_pages.py /path/to/bee-stock /path/to/bee-dashboard/
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
from collections import defaultdict

from bee_categories import (
    CATEGORIES, SUBCATEGORY_NAMES, PARENT_NAMES, PARENT_FOR_SUB,
    categorise_product,
)
from bee_retailers import RETAILERS, SHIPPING_MAP
from beestock_layout import (
    render_head, render_header, render_footer, render_breadcrumb,
    SITE_NAME, SITE_URL,
)

# Minimum number of distinct retailers needed for a compare page
MIN_RETAILERS = 3

# Max age of snapshot data (days) -- excludes stale retailer data
MAX_SNAPSHOT_AGE_DAYS = 3

# --- SEO copy per subcategory (intro + guide paragraph) ---
SUB_SEO = {
    "hive-bodies": {
        "title": "Compare Beehive Prices in Australia",
        "description": "Compare prices on Langstroth hives, brood boxes, supers, and Flow Hives from {n} Australian beekeeping retailers. In-stock products, updated daily.",
        "intro": "Looking for the cheapest beehive in Australia? beestock.com.au tracks daily stock and prices from {n} beekeeping retailers so you can compare Langstroth boxes, brood boxes, and complete hive setups without visiting every site. In-stock items shown first.",
        "guide": "Langstroth hives are the Australian standard. Start with a brood box and one super. Flow Hives are Langstroth-compatible with a premium honey-harvest mechanism. Timber boxes should be treated or painted on the outside for weather protection.",
    },
    "hive-kits": {
        "title": "Compare Beehive Starter Kit Prices in Australia",
        "description": "Compare prices on complete beehive starter kits and beginner kits from {n} Australian retailers. Updated daily.",
        "intro": "A hive kit gives you everything to get started in one purchase. beestock.com.au tracks {n} Australian beekeeping retailers daily so you can compare starter kit prices and contents before buying.",
        "guide": "Hive kits typically include a brood box, super, frames, foundation, a lid, and a base board. Some include a smoker, veil, or hive tool. Check the kit contents carefully -- cheaper kits may omit foundation or protective gear.",
    },
    "nuc-boxes": {
        "title": "Compare Nucleus Hive (Nuc Box) Prices in Australia",
        "description": "Compare prices on nuc boxes and nucleus hives from {n} Australian beekeeping retailers. Updated daily.",
        "intro": "Nucleus hives (nucs) are the easiest way to start beekeeping with an established colony. beestock.com.au tracks {n} Australian retailers daily. Nucs are seasonal and sell out quickly -- check availability below.",
        "guide": "A nuc is a 4-5 frame box with brood, workers, and a mated queen. Most Australian retailers supply nucs in spring (September to November). The box itself is usually a 5-frame Langstroth-compatible design. Buy from a reputable supplier who can confirm the queen is laying.",
    },
    "lids-covers": {
        "title": "Compare Beehive Lid & Cover Prices in Australia",
        "description": "Compare prices on hive lids, migratory lids, inner covers, and hive mats from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks hive lid and cover prices from {n} Australian beekeeping retailers daily. Migratory lids are the most popular style in Australia -- flat, light, and easy to stack on a truck.",
        "guide": "Migratory lids are flat timber boards that sit directly on the top super -- the standard for Australian commercial beekeepers. Telescoping lids overlap the box edges and give better weather protection. Inner covers (crown boards) help with ventilation in hot climates.",
    },
    "bottom-boards": {
        "title": "Compare Beehive Bottom Board Prices in Australia",
        "description": "Compare prices on hive bottom boards, varroa boards, and screened floors from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au compares bottom board and base board prices across {n} Australian retailers daily. Screened bottom boards are popular for monitoring varroa levels.",
        "guide": "Solid bottom boards are the traditional choice. Screened (mesh) bottom boards improve ventilation and allow varroa mites to fall through the mesh for monitoring. Varroa boards slide in below the mesh to catch mites for counting. Now that varroa has arrived in Australia, screened floors are increasingly recommended.",
    },
    "queen-excluders": {
        "title": "Compare Queen Excluder Prices in Australia",
        "description": "Compare prices on queen excluders from {n} Australian beekeeping retailers. Metal, plastic, and framed styles. Updated daily.",
        "intro": "beestock.com.au tracks queen excluder prices across {n} Australian retailers daily. Metal wire excluders are the most common in Australia.",
        "guide": "Queen excluders go between the brood box and supers to stop the queen from laying in honey storage. Metal wire (zinc or stainless) is more durable than plastic. Framed excluders are easier to handle. Some beekeepers choose not to use excluders at all -- the queen usually prefers to lay in the lower brood box.",
    },
    "frames": {
        "title": "Compare Beekeeping Frame Prices in Australia",
        "description": "Compare prices on Langstroth frames (full depth, WSP, ideal) from {n} Australian retailers. Updated daily.",
        "intro": "Frames are the most frequently replaced consumable in a hive. beestock.com.au tracks frame prices from {n} Australian retailers daily -- compare prices for deep frames, ideal frames, and WSP frames before buying in bulk.",
        "guide": "Australian beekeepers use three common Langstroth frame sizes: full depth (FD), WSP (Warrre Standard Periodic, similar to US medium), and ideal. Buy frames pre-assembled or unassembled. Wired frames hold foundation securely and are recommended for beginners. Buy more than you need -- having spare frames makes inspections easier.",
    },
    "foundation": {
        "title": "Compare Beeswax Foundation Prices in Australia",
        "description": "Compare prices on beeswax foundation sheets and plastic foundation from {n} Australian beekeeping retailers. Updated daily.",
        "intro": "beestock.com.au tracks beeswax and plastic foundation prices from {n} Australian retailers daily. Foundation gives bees a template to draw comb straight and uniform.",
        "guide": "Wax foundation is the traditional choice and is readily accepted by bees. Plastic foundation is more durable and can be reused. Wax-coated plastic foundation is a compromise. Match the foundation size to your frame depth -- full depth, WSP, and ideal all have different dimensions.",
    },
    "bee-suits": {
        "title": "Compare Bee Suit Prices in Australia",
        "description": "Compare prices on beekeeping suits, full suits, and beekeeping smocks from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au compares bee suit prices from {n} Australian beekeeping retailers daily. Find full suits, half suits, and ventilated options at the best available price.",
        "guide": "Full suits (suit + integrated veil) give the most protection and are recommended for beginners. Ventilated suits with 3-layer mesh stay cooler in Australian summers but cost more. Cotton suits are comfortable and durable. Polycotton blends are lighter and easier to wash. Always buy a size up -- you wear it over your normal clothes.",
    },
    "jackets-veils": {
        "title": "Compare Bee Jacket & Veil Prices in Australia",
        "description": "Compare prices on beekeeping jackets, bee veils, and hats from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks beekeeping jacket and veil prices from {n} Australian retailers daily. Jackets are lighter and quicker to put on than full suits -- a popular choice for experienced beekeepers.",
        "guide": "Jackets cover the torso and arms but leave the legs unprotected -- fine for calm hives. Veils attach to the jacket collar or are worn separately with a hat. Fencing veils have a round metal frame that keeps the veil away from your face. Round veils are more compact. Bees can't sting through a good-quality veil, but check for gaps around the collar.",
    },
    "gloves": {
        "title": "Compare Beekeeping Glove Prices in Australia",
        "description": "Compare prices on beekeeping gloves, leather gloves, and bee gloves from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks beekeeping glove prices from {n} Australian retailers daily. Leather gloves protect your hands while still allowing enough feel to handle frames gently.",
        "guide": "Goatskin gloves are the standard for beekeeping -- thin enough to feel what you are doing, thick enough to stop stings. Cowhide gloves are thicker and harder to work in. Some experienced beekeepers prefer thin nitrile gloves or no gloves at all for better sensitivity. Gloves with long gauntlet cuffs protect the wrist gap between suit and glove.",
    },
    "smokers": {
        "title": "Compare Bee Smoker Prices in Australia",
        "description": "Compare prices on bee smokers and smoker fuel from {n} Australian beekeeping retailers. Updated daily.",
        "intro": "beestock.com.au tracks bee smoker prices from {n} Australian retailers daily. A good smoker is one of the most important tools in beekeeping.",
        "guide": "Stainless steel smokers last longer than galvanised steel. A larger bellows makes it easier to keep the smoker lit during a long inspection. Hessian roll, pine needles, and dried grass are common smoker fuels in Australia. Keep your smoker clean -- blocked nozzles cause problems.",
    },
    "hive-tools": {
        "title": "Compare Hive Tool Prices in Australia",
        "description": "Compare prices on hive tools, J-hook hive tools, and bee brushes from {n} Australian beekeeping retailers. Updated daily.",
        "intro": "beestock.com.au tracks hive tool prices from {n} Australian retailers daily. A hive tool is used to pry apart frames and boxes stuck together with propolis.",
        "guide": "The J-hook (or J-tool) is the most popular style in Australia -- one end is hooked to lift frames, the other is a flat pry. Standard flat hive tools work fine too. Stainless steel is more durable than mild steel. Buy two -- you will lose one.",
    },
    "extractors": {
        "title": "Compare Honey Extractor Prices in Australia",
        "description": "Compare prices on honey extractors from {n} Australian beekeeping retailers. Radial and tangential, manual and electric. Updated daily.",
        "intro": "beestock.com.au compares honey extractor prices from {n} Australian retailers daily. Extractors are the biggest single equipment investment beyond the hive itself -- compare before buying.",
        "guide": "Tangential extractors hold frames flat against the drum and extract one side at a time. Radial extractors hold frames like spokes and extract both sides simultaneously. A 2-frame manual extractor is adequate for 1-3 hives. Electric extractors save effort for larger operations. Many beekeeping clubs have extractors you can borrow.",
    },
    "honey-handling": {
        "title": "Compare Honey Processing Equipment Prices in Australia",
        "description": "Compare prices on honey gates, strainers, settling tanks, and bottling equipment from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks honey processing equipment prices from {n} Australian retailers daily. Find honey gates, strainers, warming cabinets, and bottling gear at the best available price.",
        "guide": "After extraction, honey needs to be strained, settled, and bottled. A honey gate (valve at the bottom of a tank) makes bottling clean and easy. A settling tank lets wax and air bubbles rise to the surface before bottling. Warming cabinets decrystallise honey without damaging it.",
    },
    "varroa": {
        "title": "Compare Varroa Treatment Prices in Australia",
        "description": "Compare prices on varroa treatments (Apivar, oxalic acid, formic acid) from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks varroa treatment prices from {n} Australian retailers daily. Varroa mite arrived in NSW in 2022 and is now spreading across Australia -- treatment is becoming essential.",
        "guide": "Apivar (amitraz strips) and Bayvarol (flumethrin strips) are chemical treatments placed inside the hive. Oxalic acid and formic acid are organic acids registered for varroa treatment in Australia. Rotate treatments to reduce the chance of resistance developing. Always follow label instructions and observe the withholding period before harvesting honey.",
    },
    "shb": {
        "title": "Compare Small Hive Beetle Trap Prices in Australia",
        "description": "Compare prices on small hive beetle (SHB) traps and controls from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au compares SHB trap prices from {n} Australian retailers daily. Small hive beetle is a major pest for Australian beekeepers, especially in warmer climates.",
        "guide": "Beetle Blaster traps fit between frames and use mineral oil or vegetable oil to trap beetles that fall in. Diatomaceous earth around the hive entrance damages the beetle's exoskeleton. A strong colony is the best defence -- beetles struggle to establish in a populous hive. Keep the entrance small in summer.",
    },
    "jars-bottles": {
        "title": "Compare Honey Jar & Bottle Prices in Australia",
        "description": "Compare prices on honey jars, honey bottles, pails, and containers from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks honey jar and container prices from {n} Australian retailers daily. Buy in bulk from the retailer with the best current price.",
        "guide": "Hex (hexagonal) jars are traditional for honey retail. Round jars are cheaper. Squeeze bottles appeal to buyers who want easy dispensing. For retail, food-grade containers with tamper-evident lids are required. Buy in larger quantities to reduce the cost per jar.",
    },
    "queen-rearing": {
        "title": "Compare Queen Rearing Equipment Prices in Australia",
        "description": "Compare prices on queen cages, grafting tools, cell cups, and mating nucs from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks queen rearing equipment prices from {n} Australian retailers daily. Rearing your own queens is one of the most rewarding parts of advanced beekeeping.",
        "guide": "Queen rearing requires: cell cups or cell bars for queen cells, a grafting tool to move young larvae, an incubator or finishing colony, and introduction cages. Mating nuc boxes (small 3-5 frame boxes) let virgin queens mate before being introduced to a full hive.",
    },
    "feeders": {
        "title": "Compare Bee Feeder Prices in Australia",
        "description": "Compare prices on bee feeders (frame feeders, top feeders, entrance feeders) from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks bee feeder prices from {n} Australian retailers daily. Feeders let you supplement your colony with sugar syrup during dearth periods.",
        "guide": "Frame feeders sit inside the hive and hold the most syrup. Top feeders sit above the top box and are easy to refill without disturbing the bees. Entrance feeders (Boardman feeders) use an inverted bottle at the entrance -- small capacity but easy to monitor. Feeders are essential when establishing new colonies or supporting hives through winter.",
    },
    "wax-processing": {
        "title": "Compare Beeswax Processing Equipment Prices in Australia",
        "description": "Compare prices on wax melters, wax presses, candle moulds, and beeswax blocks from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks beeswax processing equipment prices from {n} Australian retailers daily. Rendering beeswax is a valuable secondary product from every hive.",
        "guide": "Solar wax melters use the sun to render cappings and old comb without electricity. Electric wax melters are faster and can handle larger quantities. Wax presses squeeze rendered wax out of slumgum (the residue). Filtered beeswax can be used for cosmetics, woodworking, candles, and grafting tape.",
    },
    "uncapping": {
        "title": "Compare Uncapping Equipment Prices in Australia",
        "description": "Compare prices on uncapping knives, forks, rollers, and trays from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks uncapping equipment prices from {n} Australian retailers daily. Uncapping removes the wax cappings from honey cells before extraction.",
        "guide": "Uncapping knives (electric or cold) are fastest but require the most skill to use straight. Uncapping forks scratch rather than cut the cappings and work well for beginners. Uncapping rollers spike the cappings and leave them on the frame. Uncapping trays collect cappings and let honey drain through into a bucket below.",
    },
    "bee-health": {
        "title": "Compare Bee Health & Disease Treatment Prices in Australia",
        "description": "Compare prices on nosema treatments, diagnostic kits, and bee health products from {n} Australian retailers. Updated daily.",
        "intro": "beestock.com.au tracks bee health product prices from {n} Australian retailers daily. Monitoring and treating disease keeps colonies strong and productive.",
        "guide": "Nosema is a gut fungus that weakens adult bees. Fumagilin-B is registered for nosema in Australia (check current registration). Alcohol wash and sugar roll kits are used to monitor varroa levels. Pest control strips may be used for European foulbrood. Good hygiene -- clean equipment, replacing old brood comb -- is the best prevention.",
    },
}


def load_all_products(data_dir: Path) -> list[dict]:
    """Load products from current retailer snapshots (max 3 days old).

    Only includes retailers configured in bee_retailers.py to avoid
    serving stale data from retailers removed from the active pipeline.
    """
    today = date.today()
    cutoff = today - timedelta(days=MAX_SNAPSHOT_AGE_DAYS)
    active_retailers = set(RETAILERS.keys())
    products = []

    for rd in sorted(data_dir.iterdir()):
        if not rd.is_dir():
            continue
        retailer_key = rd.name
        if retailer_key not in active_retailers:
            continue

        # Try today first, then fall back to recent dated files
        snapshot = None
        for offset in range(MAX_SNAPSHOT_AGE_DAYS + 1):
            candidate = rd / f"{(today - timedelta(days=offset)).isoformat()}.json"
            if candidate.exists():
                snapshot = candidate
                break

        if snapshot is None:
            continue

        with open(snapshot) as f:
            data = json.load(f)

        retailer_name = data.get("retailer_name") or RETAILERS[retailer_key]["name"]

        for p in data.get("products", []):
            title = p.get("title", "").strip()
            if not title:
                continue
            tags = p.get("tags", [])
            ptype = p.get("product_type", "")
            parent, sub = categorise_product(title, tags, ptype)
            if parent == "other":
                continue

            variants = p.get("variants", [])
            min_price = p.get("min_price")
            if min_price is None and variants:
                avail_prices = [float(v["price"]) for v in variants if v.get("price") and v.get("available", True)]
                all_prices = [float(v["price"]) for v in variants if v.get("price")]
                min_price = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)

            available = p.get("any_available", p.get("available", False))
            on_sale = p.get("on_sale", False)
            url = p.get("url", "")

            products.append({
                "title": title,
                "url": url,
                "retailer_key": retailer_key,
                "retailer_name": retailer_name,
                "price": round(float(min_price), 2) if min_price else None,
                "available": bool(available),
                "on_sale": bool(on_sale),
                "parent": parent,
                "sub": sub,
            })

    return products


def group_by_sub(products: list[dict]) -> dict:
    """Group products by subcategory slug."""
    by_sub = defaultdict(list)
    for p in products:
        by_sub[p["sub"]].append(p)
    return dict(by_sub)


def _utm(url: str, source: str = "beestock", medium: str = "compare") -> str:
    if not url:
        return ""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source={source}&utm_medium={medium}"


def build_compare_page(sub_slug: str, sub_name: str, parent_slug: str,
                       parent_name: str, products: list[dict]) -> str:
    now = date.today().isoformat()
    seo = SUB_SEO.get(sub_slug, {})

    in_stock = [p for p in products if p["available"] and p["price"]]
    retailer_keys = set(p["retailer_key"] for p in products)
    n_retailers = len(retailer_keys)

    in_stock_prices = [p["price"] for p in in_stock]
    min_price = min(in_stock_prices) if in_stock_prices else None
    max_price = max(in_stock_prices) if in_stock_prices else None

    price_range_str = ""
    if min_price:
        if min_price == max_price:
            price_range_str = f"${min_price:.2f}"
        else:
            price_range_str = f"${min_price:.2f} to ${max_price:.2f}"

    # Per-retailer best price
    retailer_best = {}
    for p in products:
        rk = p["retailer_key"]
        if rk not in retailer_best:
            retailer_best[rk] = {
                "name": p["retailer_name"],
                "best_price": None,
                "best_title": None,
                "best_url": None,
                "in_stock_count": 0,
                "total": 0,
                "ships_to": SHIPPING_MAP.get(rk, []),
            }
        retailer_best[rk]["total"] += 1
        if p["available"]:
            retailer_best[rk]["in_stock_count"] += 1
        if p["available"] and p["price"]:
            if retailer_best[rk]["best_price"] is None or p["price"] < retailer_best[rk]["best_price"]:
                retailer_best[rk]["best_price"] = p["price"]
                retailer_best[rk]["best_title"] = p["title"]
                retailer_best[rk]["best_url"] = p["url"]

    # Sort: in-stock + price first, out-of-stock last
    sorted_retailers = sorted(
        retailer_best.items(),
        key=lambda x: (
            x[1]["best_price"] is None or x[1]["in_stock_count"] == 0,
            x[1]["best_price"] or 9999
        )
    )

    # Retailer table rows
    retailer_rows = ""
    for i, (rk, r) in enumerate(sorted_retailers):
        if r["best_price"] and r["in_stock_count"] > 0:
            badge = (' <span class="text-xs px-1.5 py-0.5 bg-amber-100 text-amber-800 rounded font-semibold">Cheapest</span>'
                     if i == 0 else "")
            price_cell = f'${r["best_price"]:.2f}{badge}'
            title_link = (
                f'<a href="{_utm(r["best_url"])}" target="_blank" rel="noopener" '
                f'class="text-amber-700 hover:underline text-xs">{r["best_title"]}</a>'
                if r["best_url"] else
                f'<span class="text-xs">{r["best_title"]}</span>'
            )
            avail_text = f'<span class="text-amber-700">{r["in_stock_count"]} in stock</span>'
        else:
            price_cell = '<span class="text-gray-400">Out of stock</span>'
            title_link = '<span class="text-gray-400 text-xs">Nothing available</span>'
            avail_text = '<span class="text-gray-400">out of stock</span>'

        ships = ", ".join(r["ships_to"]) if r["ships_to"] else "Check retailer"
        retailer_rows += f"""
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-3 pr-3 font-medium text-sm">{r['name']}</td>
        <td class="py-3 pr-3 text-sm font-semibold">{price_cell}</td>
        <td class="py-3 pr-3 text-sm">{title_link}</td>
        <td class="py-3 pr-3 text-sm">{avail_text}</td>
        <td class="py-3 text-xs text-gray-400">{ships}</td>
      </tr>"""

    # All products table (price-sorted, in-stock first)
    sorted_prods = sorted(products, key=lambda p: (not p["available"], p["price"] or 9999, p["title"]))
    product_rows = ""
    for p in sorted_prods:
        price_str = f"${p['price']:.2f}" if p["price"] else "Call"
        avail_badge = (
            '<span class="text-xs px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full">In stock</span>'
            if p["available"] else
            '<span class="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded-full">Out of stock</span>'
        )
        sale_badge = (' <span class="text-xs px-1 bg-red-100 text-red-700 rounded">SALE</span>'
                      if p.get("on_sale") else "")
        link = (
            f'<a href="{_utm(p["url"])}" target="_blank" rel="noopener" '
            f'class="hover:text-amber-700 hover:underline">{p["title"]}</a>'
            if p["url"] else p["title"]
        )
        product_rows += f"""
      <tr class="border-b border-gray-100 hover:bg-gray-50">
        <td class="py-2 pr-3 text-sm">{link}{sale_badge}</td>
        <td class="py-2 pr-3 text-xs text-gray-500">{p['retailer_name']}</td>
        <td class="py-2 pr-3 text-sm font-medium">{price_str}</td>
        <td class="py-2">{avail_badge}</td>
      </tr>"""

    cheapest_line = ""
    if sorted_retailers and sorted_retailers[0][1]["best_price"] and sorted_retailers[0][1]["in_stock_count"] > 0:
        _, cheapest = sorted_retailers[0]
        cheapest_line = (f'<p class="text-sm text-gray-600 mt-2">Cheapest in stock: '
                         f'<strong>{cheapest["name"]}</strong> from '
                         f'<strong>${cheapest["best_price"]:.2f}</strong>.</p>')

    intro = seo.get("intro", f"Compare {sub_name} prices from {n_retailers} Australian beekeeping retailers. Updated daily.").replace("{n}", str(n_retailers))
    guide_text = seo.get("guide", "")
    guide_section = ""
    if guide_text:
        guide_section = f"""
  <section class="mt-8 text-sm text-gray-600 border-t border-gray-100 pt-6">
    <h3 class="font-semibold text-gray-800 mb-2">{sub_name}: what to know</h3>
    <p>{guide_text}</p>
  </section>"""

    meta_title = seo.get("title", f"Compare {sub_name} Prices in Australia").replace("{n}", str(n_retailers))
    meta_desc = seo.get("description", f"Compare {sub_name} prices from {n_retailers} Australian beekeeping retailers. Updated daily.").replace("{n}", str(n_retailers))
    if price_range_str:
        meta_desc += f" Prices from {price_range_str} AUD."

    head = render_head(
        title=f"{meta_title} — {SITE_NAME}",
        description=meta_desc,
        og_title=meta_title,
        og_description=meta_desc,
    )
    header = render_header()
    breadcrumb = render_breadcrumb([
        ("Home", "/"),
        ("Compare", "/compare/"),
        (sub_name, ""),
    ])
    footer = render_footer()

    in_stock_badge = (
        f'<span class="px-3 py-1 bg-amber-50 text-amber-800 rounded-full font-medium">{len(in_stock)} in stock</span>'
        if in_stock else
        '<span class="px-3 py-1 bg-gray-100 text-gray-500 rounded-full">Currently out of stock</span>'
    )
    price_badge = (
        f'<span class="px-3 py-1 bg-gray-50 text-gray-600 rounded-full">{price_range_str} AUD</span>'
        if price_range_str else ""
    )

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-6">

  {breadcrumb}

  <div class="mb-6">
    <p class="text-xs text-yellow-700 font-medium uppercase tracking-wide mb-1">
      <a href="/category/{parent_slug}.html" class="hover:underline">{parent_name}</a>
    </p>
    <h2 class="text-3xl font-bold text-yellow-900 mb-2">{sub_name} Prices</h2>
    <p class="text-gray-600 text-sm mb-3">{intro}</p>
    <div class="flex flex-wrap gap-3 text-sm">
      {in_stock_badge}
      {price_badge}
      <span class="px-3 py-1 bg-gray-50 text-gray-600 rounded-full">{n_retailers} retailers tracked</span>
    </div>
    {cheapest_line}
  </div>

  <!-- Price Comparison Table -->
  <section class="mb-8">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Price comparison by retailer</h3>
    <p class="text-sm text-gray-500 mb-3">Lowest available price per retailer. Updated {now}.</p>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
            <th class="pb-2 pr-3">Retailer</th>
            <th class="pb-2 pr-3">Best price</th>
            <th class="pb-2 pr-3">Cheapest product</th>
            <th class="pb-2 pr-3">Stock</th>
            <th class="pb-2">Ships to</th>
          </tr>
        </thead>
        <tbody>{retailer_rows}
        </tbody>
      </table>
    </div>
  </section>

  <!-- All products price-sorted -->
  <section class="mb-8">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">All {sub_name} products, sorted by price</h3>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
            <th class="pb-2 pr-3">Product</th>
            <th class="pb-2 pr-3">Retailer</th>
            <th class="pb-2 pr-3">Price</th>
            <th class="pb-2">Status</th>
          </tr>
        </thead>
        <tbody>{product_rows}
        </tbody>
      </table>
    </div>
  </section>

  <!-- Subscribe CTA -->
  <div class="p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm mb-6">
    <p class="font-semibold text-amber-900 mb-1">Get price drop alerts for {sub_name}</p>
    <p class="text-gray-600 mb-3">We check {n_retailers} retailers every day. Get an email when {sub_name} prices drop or new products appear.</p>
    <form id="cmpSubForm" class="flex flex-col sm:flex-row gap-2">
      <input type="email" id="cmpEmail" placeholder="your@email.com" required
        class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 flex-1 max-w-xs">
      <button type="submit"
        class="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 text-sm font-medium whitespace-nowrap">
        Alert me
      </button>
    </form>
    <div id="cmpMsg" class="mt-2 text-sm hidden"></div>
  </div>

  <script>
  document.getElementById('cmpSubForm').addEventListener('submit', function(e) {{
    e.preventDefault();
    var email = document.getElementById('cmpEmail').value.trim();
    var msg = document.getElementById('cmpMsg');
    fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email: email}})
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{
      msg.textContent = d.ok ? 'You are subscribed to beestock price alerts.' : (d.message || 'Subscribed.');
      msg.className = 'mt-2 text-sm text-amber-700';
      msg.style.display = 'block';
      document.getElementById('cmpSubForm').style.display = 'none';
    }})
    .catch(function() {{
      msg.textContent = 'Something went wrong. Please try again.';
      msg.className = 'mt-2 text-sm text-red-600';
      msg.style.display = 'block';
    }});
  }});
  </script>

  <!-- About / SEO footer -->
  <section class="mt-8 text-sm text-gray-500 border-t border-gray-100 pt-6">
    <h3 class="font-medium text-gray-700 mb-2">About this comparison</h3>
    <p>beestock.com.au monitors {n_retailers} Australian beekeeping retailers every day and compares
    current {sub_name} prices so you do not have to check every site yourself. Prices shown are
    the lowest available variant per retailer at the time of the last daily scrape. Always verify
    current pricing on the retailer website before ordering.</p>
    <p class="mt-2">Retailers monitored: {", ".join(r["name"] for _, r in sorted_retailers)}.</p>
    <p class="mt-2">See also: <a href="/category/{parent_slug}.html" class="text-amber-700 hover:underline">{parent_name} category page</a>.</p>
  </section>

  {guide_section}

</main>

{footer}

</body>
</html>"""


def build_compare_index(entries: list[dict]) -> str:
    """Build /compare/index.html."""
    rows = ""
    for e in sorted(entries, key=lambda x: (-x["retailer_count"], -x["in_stock"])):
        sub = e["sub_slug"]
        sub_name = e["sub_name"]
        price = f'${e["min_price"]:.2f}' if e["min_price"] else "Check retailer"
        rows += f"""
    <tr class="border-b border-gray-100 hover:bg-gray-50">
      <td class="py-3 pr-4">
        <a href="/compare/{sub}-prices.html" class="font-medium text-amber-800 hover:underline">{sub_name}</a>
        <div class="text-xs text-gray-400">{e["parent_name"]}</div>
      </td>
      <td class="py-3 pr-4 text-sm">{e["retailer_count"]} retailers</td>
      <td class="py-3 pr-4 text-sm">{e["in_stock"]} in stock</td>
      <td class="py-3 text-sm font-medium text-amber-700">{price}</td>
    </tr>"""

    n = len(entries)
    head = render_head(
        title=f"Beekeeping Supply Price Comparisons Australia — {SITE_NAME}",
        description=f"Compare beekeeping supply prices across {n} product categories from Australian retailers. Find the cheapest hives, extractors, bee suits, frames, and more. Updated daily.",
        og_title="Beekeeping Price Comparisons — Australia",
        og_description=f"Compare prices across {n} beekeeping categories from Australian retailers. Updated daily.",
    )
    header = render_header()
    breadcrumb = render_breadcrumb([("Home", "/"), ("Compare Prices", "")])
    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-6">
  {breadcrumb}

  <h2 class="text-3xl font-bold text-yellow-900 mb-2">Beekeeping Price Comparisons</h2>
  <p class="text-gray-600 mb-6">
    Compare beekeeping supply prices across {n} categories from Australian retailers.
    Find the cheapest hives, extractors, bee suits, frames, and more.
    Updated daily.
  </p>

  <div class="overflow-x-auto">
    <table class="w-full text-left">
      <thead>
        <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
          <th class="pb-2 pr-4">Category</th>
          <th class="pb-2 pr-4">Coverage</th>
          <th class="pb-2 pr-4">In stock</th>
          <th class="pb-2">From</th>
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


def update_sitemap(output_dir: Path, sub_slugs: list[str], today: str) -> None:
    """Add/refresh compare pages in sitemap.xml."""
    sitemap_path = output_dir / "sitemap.xml"
    if not sitemap_path.exists():
        return
    content = sitemap_path.read_text()

    # Remove existing compare entries
    content = re.sub(
        r'\s*<url>\s*<loc>https://beestock\.com\.au/compare/[^<]+</loc>.*?</url>',
        '',
        content,
        flags=re.DOTALL,
    )

    entries = ""
    for slug in sub_slugs:
        entries += f"""
  <url>
    <loc>https://beestock.com.au/compare/{slug}-prices.html</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.7</priority>
  </url>"""
    # Index page
    entries += f"""
  <url>
    <loc>https://beestock.com.au/compare/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>"""

    content = content.replace("</urlset>", entries + "\n</urlset>")
    sitemap_path.write_text(content)
    print(f"Sitemap updated: added {len(sub_slugs)} compare URLs + index")


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <bee-stock-data-dir> <bee-dashboard-dir>", file=sys.stderr)
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    compare_dir = output_dir / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)

    products = load_all_products(data_dir)
    print(f"Loaded {len(products)} categorised products from {data_dir}")

    by_sub = group_by_sub(products)

    index_entries = []
    pages_written = 0

    for sub_slug, prods in by_sub.items():
        retailer_keys = set(p["retailer_key"] for p in prods)
        if len(retailer_keys) < MIN_RETAILERS:
            continue

        parent_slug = PARENT_FOR_SUB.get(sub_slug, "other")
        parent_name = PARENT_NAMES.get(parent_slug, "Other")
        sub_name = SUBCATEGORY_NAMES.get(sub_slug, sub_slug)

        in_stock = [p for p in prods if p["available"] and p["price"]]
        min_price = min((p["price"] for p in in_stock), default=None)

        html = build_compare_page(sub_slug, sub_name, parent_slug, parent_name, prods)
        out_path = compare_dir / f"{sub_slug}-prices.html"
        with open(out_path, "w") as f:
            f.write(html)

        index_entries.append({
            "sub_slug": sub_slug,
            "sub_name": sub_name,
            "parent_slug": parent_slug,
            "parent_name": parent_name,
            "retailer_count": len(retailer_keys),
            "in_stock": len(in_stock),
            "min_price": min_price,
        })
        pages_written += 1
        print(f"  {sub_slug}: {len(prods)} products, {len(retailer_keys)} retailers")

    index_html = build_compare_index(index_entries)
    with open(compare_dir / "index.html", "w") as f:
        f.write(index_html)

    # Update sitemap
    written_slugs = [e["sub_slug"] for e in index_entries]
    update_sitemap(output_dir, written_slugs, date.today().isoformat())

    print(f"\nWritten {pages_written} compare pages + index.html to {compare_dir}/")


if __name__ == "__main__":
    main()
