#!/usr/bin/env python3
"""
Build static category landing pages for beestock.com.au SEO.

Generates one HTML page per product category at /category/{slug}.html
Target queries: "buy langstroth hive Australia", "honey extractor Australia", etc.

Usage:
    python3 build_bee_category_pages.py /path/to/bee-stock /path/to/bee-dashboard/
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

from bee_categories import CATEGORIES, CATEGORY_NAMES, categorise_product
from bee_retailers import RETAILER_NAMES
from beestock_layout import (
    render_head, render_header, render_footer,
    SITE_NAME, SITE_URL,
)

# ------------------------------------------------------------------ #
# SEO metadata per category
# ------------------------------------------------------------------ #

CATEGORY_SEO = {
    "hives-boxes": {
        "title": "Buy Beehives & Boxes in Australia",
        "description": (
            "Compare prices on beehives, Langstroth boxes, nucleus hives, and Flow Hives "
            "from 6 Australian beekeeping retailers. Updated daily."
        ),
        "intro": (
            "Looking to buy a beehive or hive box in Australia? beestock.com.au tracks live "
            "stock and prices from 6 Australian retailers every day, so you can compare "
            "Langstroth boxes, nucleus hives, brood boxes, and complete hive setups without "
            "checking each store separately. Whether you are setting up your first colony or "
            "expanding an existing apiary, use the list below to find the best available price. "
            "Prices updated daily. In-stock items shown first."
        ),
        "keywords": "buy beehive Australia, Langstroth hive Australia, beehive price comparison",
        "groups": ["Langstroth", "Flow Hive", "Nucleus", "Brood Box", "Super", "Lid", "Base"],
        "guide": (
            "<h2>Buying a beehive in Australia: what to know</h2>"
            "<p>The Langstroth hive is the standard in Australia. Most beekeeping equipment, "
            "frames, and accessories are built around the 10-frame Langstroth standard. Unless "
            "you have a specific reason to choose otherwise, start with a Langstroth brood box "
            "and one super.</p>"
            "<p>Flow Hives use a proprietary honey-harvesting mechanism. They cost more upfront "
            "but allow honey extraction without removing frames. The bees and management are "
            "identical to a standard Langstroth.</p>"
            "<p>A nucleus hive (nuc) is a starter colony in a small 4-5 frame box. It is the "
            "easiest way to start beekeeping with established brood, a laying queen, and bees "
            "already working together. Nucleus hives are seasonal and sell out quickly. Most "
            "Australian retailers supply nucs in spring (September to November).</p>"
            "<p>Australian timber boxes are usually made from kiln-dried pine. Plastic hive "
            "components are lighter and easier to clean but less popular among traditional "
            "beekeepers. All boxes should be treated or painted on the outside to protect from "
            "the weather.</p>"
        ),
    },
    "frames-foundation": {
        "title": "Buy Beekeeping Frames & Foundation in Australia",
        "description": (
            "Compare prices on beekeeping frames and wax foundation from Australian retailers. "
            "Langstroth deep, medium, and ideal frames. Updated daily."
        ),
        "intro": (
            "Frames and foundation are the backbone of any hive. beestock.com.au compares "
            "current stock and prices across 6 Australian beekeeping retailers so you can "
            "find deep frames, medium frames, ideal frames, and wax or plastic foundation "
            "at the best available price. Results show in-stock items first. Updated daily."
        ),
        "keywords": "beekeeping frames Australia, langstroth frames, wax foundation Australia",
        "groups": ["Deep", "Medium", "Ideal", "Wired", "Unwired", "Wax", "Plastic"],
        "guide": (
            "<h2>Choosing beekeeping frames and foundation in Australia</h2>"
            "<p>Langstroth frames come in three depths: deep (full depth), medium, and ideal "
            "(WSP). In Australia, the deep frame is the most common for brood boxes. Medium "
            "and ideal frames are popular for honey supers because they are lighter to lift "
            "when full.</p>"
            "<p>Foundation comes in wax or plastic. Wax foundation is traditional and well "
            "accepted by bees. Plastic foundation is more durable and reusable, but takes "
            "longer for bees to accept. Both are available wired (for structural strength) "
            "and unwired.</p>"
            "<p>Frames can be bought assembled or flat-packed. Flat-pack is cheaper but "
            "requires assembly. If you are starting out, buy 20-30 frames for a standard "
            "two-box hive setup. Always have spare drawn frames available for swarm "
            "prevention and splits.</p>"
            "<p>Australian beekeeping suppliers stock both 8-frame and 10-frame equipment. "
            "10-frame Langstroth is the most common nationally. If you are buying second-hand "
            "equipment, confirm the frame size before purchasing more boxes.</p>"
        ),
    },
    "extractors-processing": {
        "title": "Buy Honey Extractors & Processing Equipment in Australia",
        "description": (
            "Compare prices on honey extractors, uncapping knives, honey gates, strainers, "
            "and bottling tanks from 6 Australian retailers. Updated daily."
        ),
        "intro": (
            "Comparing honey extractor prices in Australia can save hundreds of dollars. "
            "beestock.com.au tracks prices across 6 Australian beekeeping stores every day "
            "and shows you who has the best deal right now. We cover manual and electric "
            "extractors from 2-frame to 9-frame, plus uncapping forks, honey gates, "
            "settling tanks, and other processing equipment. In-stock items shown first."
        ),
        "keywords": "honey extractor Australia, buy honey extractor, honey extractor price comparison",
        "groups": ["2 Frame", "4 Frame", "6 Frame", "9 Frame", "Electric", "Manual", "Uncapping"],
        "guide": (
            "<h2>Buying a honey extractor in Australia</h2>"
            "<p>Honey extractors spin frames to remove honey by centrifugal force without "
            "destroying the comb. This allows frames to be reused, saving you significant "
            "work and wax over time.</p>"
            "<p>For a small hobby apiary (1-4 hives), a manual 2-frame extractor is "
            "sufficient. For 5-10 hives, consider a 4-frame manual or a motorised 4-frame "
            "model. Larger operations benefit from 6-frame or 9-frame electric models.</p>"
            "<p>Extractors are available in radial (frames mounted like spokes) and "
            "tangential (frames face the wall) designs. Radial extractors extract both sides "
            "simultaneously and are preferred for larger operations. Tangential extractors "
            "require flipping frames mid-spin but are typically cheaper.</p>"
            "<p>Stainless steel extractors are food-safe and easiest to clean. Plastic "
            "drum models are lighter and cheaper but harder to keep clean over time. "
            "If you are new to beekeeping and unsure about long-term commitment, consider "
            "borrowing a club extractor or sharing one with nearby beekeepers before "
            "purchasing your own.</p>"
        ),
    },
    "protective-gear": {
        "title": "Buy Beekeeping Suits, Jackets & Protective Gear in Australia",
        "description": (
            "Compare prices on bee suits, jackets, veils, and gloves from Australian "
            "beekeeping retailers. Updated daily."
        ),
        "intro": (
            "Protective gear is essential for safe beekeeping. beestock.com.au tracks "
            "current stock and prices on bee suits, beekeeping jackets, veils, gloves, "
            "and hats across 6 Australian retailers. Compare full suits, ventilated "
            "mesh suits, cotton jackets, and round veils. Updated daily with in-stock "
            "items shown first."
        ),
        "keywords": "bee suit Australia, beekeeping jacket Australia, beekeeper protective gear",
        "groups": ["Full Suit", "Jacket", "Veil", "Gloves", "Hat", "Ventilated", "Cotton"],
        "guide": (
            "<h2>Choosing beekeeping protective gear in Australia</h2>"
            "<p>The right protective gear lets you inspect your hive calmly without rushing. "
            "Rushing increases the chance of stings, which increases bee agitation, which "
            "leads to more stings. Good gear is an investment in better beekeeping.</p>"
            "<p>For beginners, a full suit (hood, jacket, and pants together) provides "
            "the most confidence and protection. For experienced beekeepers who know their "
            "hive's temperament, a jacket and veil combination is often sufficient.</p>"
            "<p>Ventilated mesh suits are significantly cooler in Australian summers. "
            "Cotton and polycotton suits are cheaper and suitable for temperate climates, "
            "but hot in Queensland and northern WA summers. Round veils are easier to put "
            "on and take off than fencing veils.</p>"
            "<p>Gloves are personal preference. Some beekeepers work gloveless for better "
            "dexterity. Leather gloves provide maximum protection but reduce feel. Nitrile "
            "or latex gloves offer a compromise. Ensure your gloves attach securely to "
            "jacket sleeves with no gap.</p>"
            "<p>Always wash your suit regularly. Alarm pheromone builds up in fabric and "
            "makes bees more defensive at subsequent inspections.</p>"
        ),
    },
    "smokers-tools": {
        "title": "Buy Bee Smokers & Beekeeping Tools in Australia",
        "description": (
            "Compare prices on bee smokers, hive tools, queen catchers, and beekeeping "
            "accessories from Australian retailers. Updated daily."
        ),
        "intro": (
            "beestock.com.au compares bee smoker and beekeeping tool prices from 6 "
            "Australian retailers every day. Find the best price on smokers, hive tools, "
            "J-hook tools, bee brushes, queen marking pens, and frame lifters. "
            "In-stock items shown first. Updated daily."
        ),
        "keywords": "bee smoker Australia, hive tool Australia, beekeeping tools",
        "groups": ["Smoker", "Hive Tool", "J Hook", "Queen", "Frame Lifter", "Brush"],
        "guide": (
            "<h2>Essential beekeeping tools explained</h2>"
            "<p>A smoker is the single most important beekeeping tool. Smoke triggers a "
            "feeding response in bees, making them calmer and easier to inspect. Use dry "
            "smoker fuel: hessian, wood shavings, or dried grass. Always smoke the entrance "
            "before opening, then a light puff under the lid. Do not over-smoke.</p>"
            "<p>The hive tool is used to separate boxes and frames that bees have glued "
            "together with propolis. The J-hook hive tool is popular in Australia for "
            "lifting frames cleanly without scraping adjacent frames. A standard flatbar "
            "hive tool is the traditional alternative. Most experienced beekeepers carry both.</p>"
            "<p>Queen marking pens allow you to mark the queen's thorax for easy "
            "identification. The international colour code rotates by year (white, yellow, "
            "red, green, blue). Marking makes requeening and queen checking significantly "
            "faster.</p>"
            "<p>Bee brushes are used to gently move bees off a frame. Use light strokes "
            "from the side, not directly against the bee. Keep your brush clean and smoke "
            "lightly before brushing to reduce agitation.</p>"
        ),
    },
    "treatments": {
        "title": "Buy Varroa Mite Treatments & Beehive Health Products in Australia",
        "description": (
            "Compare prices on varroa mite treatments, Apistan, Apivar, oxalic acid, "
            "and hive health products from Australian beekeeping retailers. Updated daily."
        ),
        "intro": (
            "With varroa mite now established in Australia, treatment products are "
            "in high demand. beestock.com.au tracks current stock and prices on Apistan, "
            "Apivar, oxalic acid vaporisers, formic acid treatments, and small hive beetle "
            "traps across 6 Australian retailers. In-stock items shown first. Updated daily."
        ),
        "keywords": "varroa mite treatment Australia, Apistan Australia, Apivar Australia, oxalic acid beekeeping",
        "groups": ["Apistan", "Apivar", "Oxalic", "Formic", "Beetle Trap", "Thymol"],
        "guide": (
            "<h2>Varroa mite treatment in Australia: what beekeepers need to know</h2>"
            "<p>Varroa destructor arrived in NSW in 2022 and has spread significantly since. "
            "Treatment is now a normal part of Australian beekeeping in most states.</p>"
            "<p>Apistan (tau-fluvalinate strips) and Apivar (amitraz strips) are the most "
            "widely used treatments. Both are placed between frames for a set number of "
            "weeks. Resistance to these chemical treatments is a global concern, so rotate "
            "between treatment classes each season.</p>"
            "<p>Oxalic acid is an organic treatment that is highly effective against varroa "
            "when applied during a broodless period (mid-winter or after a split). It can "
            "be applied by drizzle, sublimation (vaporisation), or as a gel. Oxalic acid "
            "does not penetrate capped brood, so timing is critical.</p>"
            "<p>Small hive beetle (Aethina tumida) is a separate pest managed with in-hive "
            "traps (oil or boric acid) and by maintaining strong colonies. SHB is most "
            "problematic in warm, humid climates (QLD, northern NSW).</p>"
            "<p>Always follow withholding periods on treatment labels before harvesting honey. "
            "Check your state's biosecurity authority for current recommended protocols.</p>"
        ),
    },
    "feeders": {
        "title": "Buy Bee Feeders & Supplement Feed in Australia",
        "description": (
            "Compare prices on bee feeders, pollen substitutes, and syrup feeders "
            "from Australian beekeeping retailers. Updated daily."
        ),
        "intro": (
            "beestock.com.au tracks current bee feeder prices across Australian "
            "beekeeping retailers. Find frame feeders, entrance feeders, top feeders, "
            "pollen patties, and pollen substitutes at the best available price. "
            "Updated daily with in-stock items shown first."
        ),
        "keywords": "bee feeder Australia, pollen substitute Australia, beekeeping feeder",
        "groups": ["Frame Feeder", "Entrance Feeder", "Top Feeder", "Pollen", "Boardman"],
        "guide": (
            "<h2>When and how to feed your bees in Australia</h2>"
            "<p>Bees generally do not need supplemental feeding when there is a good nectar "
            "flow. Feed when establishing a new colony, after a swarm, in late summer dearth, "
            "or when a hive is light going into winter.</p>"
            "<p>Sugar syrup (1:1 sugar to water by weight in spring/summer, 2:1 in autumn) "
            "is the most common supplemental feed. Frame feeders sit inside the hive in place "
            "of a frame and hold 1-2 litres. Entrance feeders are simpler but expose the "
            "syrup to robbing. Top feeders hold more volume and are less disruptive to inspect.</p>"
            "<p>Pollen substitutes provide protein when natural pollen is scarce. They are "
            "especially useful for colonies building up in late winter before natural pollen "
            "is available. Pollen patties are placed directly on the frames above the brood cluster.</p>"
            "<p>Avoid feeding inside the hive during hot weather as fermentation can occur "
            "quickly. Fermented syrup can cause dysentery. Feed in small quantities and check "
            "daily during warm conditions.</p>"
        ),
    },
    "honey-containers": {
        "title": "Buy Honey Jars, Bottles & Labels in Australia",
        "description": (
            "Compare prices on honey jars, bottles, containers, and labels from "
            "Australian beekeeping retailers. Updated daily."
        ),
        "intro": (
            "beestock.com.au compares honey jar and container prices from Australian "
            "beekeeping supply stores. Find hex jars, round jars, squeeze bottles, "
            "bulk packs, and honey labels at the best price available right now. "
            "In-stock items shown first. Updated daily."
        ),
        "keywords": "honey jars Australia, honey bottles Australia, honey containers buy",
        "groups": ["Hex Jar", "Round Jar", "Squeeze", "Label", "Lid", "Bulk"],
        "guide": (
            "<h2>Choosing honey jars and containers in Australia</h2>"
            "<p>Presentation matters for selling or gifting honey. The jar is often the "
            "first thing a customer notices. Standard options in Australia are hex (hexagonal) "
            "glass jars, round glass jars, and plastic squeeze bottles.</p>"
            "<p>Glass jars are preferred for premium honey. They are inert, preserve flavour "
            "and aroma, and look professional. Hex jars in 250g, 500g, and 1kg sizes are "
            "the most popular in Australia for retail and markets.</p>"
            "<p>Plastic squeeze bottles are convenient for table use and popular with "
            "customers who want an everyday honey container. They are lighter and cheaper "
            "to ship but generally considered less premium than glass.</p>"
            "<p>Labels must meet Australian Food Standards requirements if you are selling "
            "commercially. You must include: product name (Australian Honey), net weight, "
            "your name and address, country of origin, and lot identification. Buy labels "
            "pre-designed or use online templates.</p>"
            "<p>Buy jars in bulk to reduce per-unit cost. A carton of 48 jars is standard "
            "for most Australian beekeeping suppliers. Lids are sold separately, so check "
            "compatibility before ordering.</p>"
        ),
    },
    "books-education": {
        "title": "Buy Beekeeping Books & Courses in Australia",
        "description": (
            "Compare prices on beekeeping books, guides, and educational resources "
            "from Australian retailers. Updated daily."
        ),
        "intro": (
            "beestock.com.au lists current beekeeping books and educational resources "
            "available from Australian suppliers. Find beginner guides, advanced "
            "management books, and reference manuals at the best available price. "
            "Updated daily with in-stock items shown first."
        ),
        "keywords": "beekeeping books Australia, beekeeping guide buy, learn beekeeping Australia",
        "groups": ["Beginner", "Advanced", "Manual", "Guide"],
        "guide": (
            "<h2>Best beekeeping books for Australian beekeepers</h2>"
            "<p>Books remain one of the best investments a new beekeeper can make. A good "
            "reference manual lets you diagnose problems at 2am when forums are slow and "
            "your mentor is unavailable.</p>"
            "<p>For beginners, look for Australian-specific content. Many UK and US "
            "beekeeping books reference pests, seasonal timing, and legal frameworks that "
            "do not apply in Australia. The Beekeeping chapter timing in particular differs "
            "significantly, since Australian seasons are the reverse of the northern "
            "hemisphere.</p>"
            "<p>Key topics to have covered in your library: colony inspection and record "
            "keeping, swarm prevention and management, queen rearing and introduction, "
            "disease and pest identification (AFB, EFB, varroa, SHB, chalkbrood), and "
            "honey extraction and processing.</p>"
            "<p>State beekeeping associations also produce their own guides and run "
            "courses. The Victorian Apiarists Association, NSW Apiarists Association, "
            "and Queensland Beekeepers Association all have member resources. Local "
            "beekeeping clubs are an underrated source of hands-on mentoring that no "
            "book fully replaces.</p>"
        ),
    },
}


# ------------------------------------------------------------------ #
# Product loading (mirrors build_bee_dashboard.py logic)
# ------------------------------------------------------------------ #

def load_products(data_dir: Path) -> list[dict]:
    """Load all products from bee-stock data directory."""
    products = []
    for retailer_dir in sorted(data_dir.iterdir()):
        if not retailer_dir.is_dir():
            continue
        latest = retailer_dir / "latest.json"
        if not latest.exists():
            continue
        with open(latest) as f:
            data = json.load(f)
        retailer_key = retailer_dir.name
        for p in data.get("products", []):
            title = p.get("title", "")
            if title.lower() in ("gift card", "gift voucher", "gift certificate"):
                continue
            tags = p.get("tags", [])
            product_type = p.get("product_type", "")
            cat = categorise_product(title, tags, product_type)

            variants = p.get("variants", [])
            # min price (prefer available variants)
            avail_prices = [float(v["price"]) for v in variants
                            if v.get("price") and v.get("available", True)]
            all_prices = [float(v["price"]) for v in variants if v.get("price")]
            min_price = min(avail_prices) if avail_prices else (
                min(all_prices) if all_prices else p.get("min_price") or p.get("price")
            )
            max_price = max(avail_prices) if avail_prices else (
                max(all_prices) if all_prices else None
            )
            if max_price and min_price and max_price <= min_price + 0.01:
                max_price = None

            available = p.get("any_available", p.get("available", False))
            if not available and avail_prices:
                available = True

            retailer_display = (
                p.get("retailer_name")
                or RETAILER_NAMES.get(retailer_key, retailer_key.replace("-", " ").title())
            )

            products.append({
                "title": title,
                "cat": cat,
                "retailer": retailer_display,
                "retailer_key": retailer_key,
                "url": p.get("url", ""),
                "min_price": round(float(min_price), 2) if min_price else None,
                "max_price": round(float(max_price), 2) if max_price else None,
                "available": bool(available),
            })

    return products


# ------------------------------------------------------------------ #
# Grouping logic
# ------------------------------------------------------------------ #

def group_products(products: list[dict], group_terms: list[str]) -> dict[str, list[dict]]:
    """
    Group products by keywords found in their titles.
    Products matching no group term go into 'Other'.
    Returns ordered dict: group_name -> [products].
    """
    groups: dict[str, list[dict]] = {}
    for term in group_terms:
        groups[term] = []
    groups["Other"] = []

    for p in products:
        title_lower = p["title"].lower()
        matched = False
        for term in group_terms:
            if term.lower() in title_lower:
                groups[term].append(p)
                matched = True
                break
        if not matched:
            groups["Other"].append(p)

    # Remove empty groups (except Other if there are items in it)
    return {k: v for k, v in groups.items() if v}


# ------------------------------------------------------------------ #
# HTML generation
# ------------------------------------------------------------------ #

def product_row(p: dict) -> str:
    """Render a single product row."""
    title = p["title"]
    url = p["url"]
    retailer = p["retailer"]
    available = p["available"]
    min_price = p["min_price"]
    max_price = p["max_price"]

    # Price display
    if min_price:
        if max_price:
            price_str = f"${min_price:.2f} – ${max_price:.2f}"
        else:
            price_str = f"${min_price:.2f}"
    else:
        price_str = "—"

    # Availability badge
    avail_cls = "bg-green-100 text-green-800" if available else "bg-gray-100 text-gray-500"
    avail_label = "In Stock" if available else "Out of Stock"

    link = f'<a href="{url}" target="_blank" rel="noopener" class="text-amber-800 hover:underline font-medium">{title}</a>' if url else title

    return f"""
      <tr class="{'bg-white' if available else 'bg-gray-50'}">
        <td class="py-2 px-3 text-sm">{link}</td>
        <td class="py-2 px-3 text-sm text-gray-600 whitespace-nowrap">{retailer}</td>
        <td class="py-2 px-3 text-sm font-semibold text-right whitespace-nowrap">{price_str}</td>
        <td class="py-2 px-3 text-right">
          <span class="text-xs px-2 py-0.5 rounded-full font-medium {avail_cls}">{avail_label}</span>
        </td>
      </tr>"""


def render_product_table(products: list[dict], group_terms: list[str]) -> str:
    """Render the product table, optionally with group headings."""
    if not products:
        return '<p class="text-gray-500 text-sm">No products found in this category.</p>'

    table_header = """
    <table class="w-full text-left border-collapse">
      <thead>
        <tr class="border-b border-gray-200 text-xs text-gray-500 uppercase">
          <th class="py-2 px-3 font-semibold">Product</th>
          <th class="py-2 px-3 font-semibold">Retailer</th>
          <th class="py-2 px-3 font-semibold text-right">Price</th>
          <th class="py-2 px-3 font-semibold text-right">Status</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100">"""

    # Sort: in-stock first, then by price
    products_sorted = sorted(
        products,
        key=lambda p: (not p["available"], p["min_price"] or 9999)
    )

    grouped = group_products(products_sorted, group_terms)
    tbody = ""

    if len(grouped) == 1:
        # Only one group (likely "Other") — no group headings
        for p in list(grouped.values())[0]:
            tbody += product_row(p)
    else:
        for group_name, group_products_list in grouped.items():
            if group_products_list:
                count = len(group_products_list)
                in_stock = sum(1 for p in group_products_list if p["available"])
                tbody += f"""
      <tr>
        <td colspan="4" class="py-2 px-3 bg-amber-50 text-xs font-semibold text-amber-900 uppercase tracking-wide">
          {group_name} <span class="font-normal text-gray-500">({in_stock} in stock of {count})</span>
        </td>
      </tr>"""
                for p in group_products_list:
                    tbody += product_row(p)

    return table_header + tbody + "\n      </tbody>\n    </table>"


def build_category_page(
    cat_slug: str,
    products: list[dict],
    total_in_stock: int,
    today: str,
) -> str:
    """Build the full HTML for one category page."""
    seo = CATEGORY_SEO.get(cat_slug, {
        "title": f"Buy {CATEGORY_NAMES.get(cat_slug, cat_slug.title())} in Australia",
        "description": f"Compare prices on {CATEGORY_NAMES.get(cat_slug, cat_slug)} from Australian beekeeping retailers.",
        "intro": f"Compare current prices on {CATEGORY_NAMES.get(cat_slug, cat_slug)} from Australian beekeeping retailers.",
        "keywords": f"beekeeping {cat_slug} Australia",
        "groups": [],
    })

    canonical = f"{SITE_URL}/category/{cat_slug}.html"
    cat_name = CATEGORY_NAMES.get(cat_slug, cat_slug.title())
    in_stock = sum(1 for p in products if p["available"])
    total = len(products)

    head = render_head(
        title=f"{seo['title']} | beestock.com.au",
        description=seo["description"],
        canonical_url=canonical,
        og_title=seo["title"],
        og_description=seo["description"],
        og_type="website",
    )
    header = render_header(active_path=f"/category/{cat_slug}.html")

    product_table = render_product_table(products, seo.get("groups", []))

    # Buying guide section (appears below product table)
    guide_html = ""
    if seo.get("guide"):
        guide_html = f"""
  <!-- Buying guide -->
  <section class="prose prose-sm max-w-2xl mb-8 text-gray-700">
    {seo["guide"]}
  </section>
"""

    # All category links for breadcrumb/navigation
    cat_links = " &middot; ".join(
        f'<a href="/category/{c["slug"]}.html" class="hover:text-amber-700">{c["name"]}</a>'
        for c in CATEGORIES
    )

    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-5xl mx-auto px-4 py-6">

  <!-- Breadcrumb -->
  <nav class="text-xs text-gray-400 mb-4">
    <a href="/" class="hover:text-amber-700">beestock.com.au</a>
    &rsaquo;
    <span class="text-gray-600">{cat_name}</span>
  </nav>

  <!-- Page header -->
  <div class="mb-6">
    <h1 class="text-2xl font-bold text-gray-900 mb-2">{seo["title"]}</h1>
    <p class="text-gray-600 text-sm leading-relaxed max-w-2xl">{seo["intro"]}</p>
    <p class="text-xs text-gray-400 mt-2">
      {in_stock} in stock of {total} products tracked &middot; Updated {today}
    </p>
  </div>

  <!-- Back to search -->
  <div class="mb-4">
    <a href="/?cat={cat_slug}" class="inline-block text-sm bg-amber-100 text-amber-900 px-3 py-1.5 rounded hover:bg-amber-200 transition-colors">
      Search &amp; filter within {cat_name} &rarr;
    </a>
  </div>

  <!-- Product table -->
  <div class="bg-white border border-gray-200 rounded-lg overflow-hidden mb-8">
    {product_table}
  </div>

  {guide_html}

  <!-- All categories -->
  <div class="text-sm text-gray-500 mb-8">
    <span class="font-medium text-gray-700">Browse by category:</span><br>
    <div class="mt-1 leading-loose">{cat_links}</div>
  </div>

  <!-- Subscribe CTA -->
  <div class="bg-amber-50 border border-amber-200 rounded-lg p-5 mb-6">
    <h2 class="font-semibold text-amber-900 mb-1">Get daily price alerts</h2>
    <p class="text-sm text-amber-800 mb-3">
      Subscribe for a daily digest showing price changes and restocks across all {total_in_stock:,} products we track.
    </p>
    <form id="subscribeForm" class="flex gap-2 max-w-md">
      <input id="subEmail" type="email" placeholder="your@email.com" required
        class="flex-1 border border-amber-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400">
      <button type="submit"
        class="bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium px-4 py-1.5 rounded transition-colors">
        Subscribe
      </button>
    </form>
    <p id="subMsg" class="hidden text-sm mt-2"></p>
  </div>

</main>

{footer}

<script>
const subForm = document.getElementById('subscribeForm');
const subMsg = document.getElementById('subMsg');
if (subForm) {{
  subForm.addEventListener('submit', function(e) {{
    e.preventDefault();
    const email = document.getElementById('subEmail').value.trim();
    if (!email) return;
    const btn = subForm.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Subscribing...';
    fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email}}),
    }})
    .then(r => r.json())
    .then(d => {{
      subMsg.classList.remove('hidden', 'text-red-700');
      subMsg.classList.add('text-green-700');
      subMsg.textContent = d.message === 'Already subscribed'
        ? "You're already subscribed."
        : "Subscribed! Check your inbox.";
      subForm.reset();
      btn.disabled = false;
      btn.textContent = 'Subscribe';
    }})
    .catch(() => {{
      subMsg.classList.remove('hidden', 'text-green-700');
      subMsg.classList.add('text-red-700');
      subMsg.textContent = 'Something went wrong. Please try again.';
      btn.disabled = false;
      btn.textContent = 'Subscribe';
    }});
  }});
}}
</script>

</body>
</html>"""


# ------------------------------------------------------------------ #
# Sitemap update
# ------------------------------------------------------------------ #

def update_sitemap(output_dir: Path, today: str) -> None:
    """Add category pages to sitemap.xml."""
    sitemap_path = output_dir / "sitemap.xml"
    if not sitemap_path.exists():
        return

    content = sitemap_path.read_text()

    # Remove existing category entries
    content = re.sub(
        r'\s*<url>\s*<loc>https://beestock\.com\.au/category/[^<]+</loc>.*?</url>',
        '',
        content,
        flags=re.DOTALL,
    )

    # Build new category entries
    cat_entries = ""
    for cat in CATEGORIES:
        cat_entries += f"""
  <url>
    <loc>https://beestock.com.au/category/{cat["slug"]}.html</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>"""

    # Insert before </urlset>
    content = content.replace("</urlset>", cat_entries + "\n</urlset>")
    sitemap_path.write_text(content)
    print(f"Sitemap updated: added {len(CATEGORIES)} category URLs")


# ------------------------------------------------------------------ #
# Dashboard footer patch — add category links
# ------------------------------------------------------------------ #

def patch_dashboard_footer(output_dir: Path) -> None:
    """
    Add category page links to the beestock dashboard footer if not already present.
    """
    index_path = output_dir / "index.html"
    if not index_path.exists():
        return
    content = index_path.read_text()
    if "Browse by category" in content:
        print("Dashboard already has category links — skipping patch")
        return

    cat_links_html = "\n".join(
        f'<a href="/category/{cat["slug"]}.html" class="hover:text-gray-600">{cat["name"]}</a>'
        for cat in CATEGORIES
    )

    # Inject before the closing </footer> tag
    section = f"""
  <div class="mt-3">
    <p class="text-xs text-gray-500 mb-1 font-medium">Browse by category:</p>
    <div class="flex flex-wrap justify-center gap-x-3 gap-y-1 text-xs text-gray-400">
{cat_links_html}
    </div>
  </div>
"""
    content = content.replace("</footer>", section + "</footer>", 1)
    tmp = output_dir / "index.html.tmp"
    tmp.write_text(content)
    tmp.rename(index_path)
    print("Dashboard footer patched with category links")


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build beestock category pages")
    parser.add_argument("data_dir", help="Path to bee-stock/ data directory")
    parser.add_argument("output_dir", nargs="?", default="/opt/dale/bee-dashboard",
                        help="Output directory (bee-dashboard)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    if not data_dir.exists():
        print(f"Error: data_dir {data_dir} does not exist")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    category_dir = output_dir / "category"
    category_dir.mkdir(exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"Loading products from {data_dir}...")
    all_products = load_products(data_dir)
    print(f"Loaded {len(all_products)} products")

    total_in_stock = sum(1 for p in all_products if p["available"])

    # Map from categorise_product parent slug -> CATEGORY_SEO page slug
    # Some parent slugs differ from the page slug used in CATEGORY_SEO
    PARENT_TO_PAGE = {
        "hiveware": "hives-boxes",
        "containers-packing": "honey-containers",
    }

    # Group products by CATEGORY_SEO page slug
    # cat field is a (parent_slug, sub_slug) tuple from categorise_product
    by_cat: dict[str, list[dict]] = {}
    for p in all_products:
        parent_slug = p["cat"][0] if isinstance(p["cat"], tuple) else p["cat"]
        page_slug = PARENT_TO_PAGE.get(parent_slug, parent_slug)
        by_cat.setdefault(page_slug, []).append(p)

    # Build one page per CATEGORY_SEO entry (these are the actual page slugs)
    pages_written = 0
    for slug in CATEGORY_SEO:
        products = by_cat.get(slug, [])
        if not products:
            print(f"  {slug}: no products, skipping")
            continue

        html = build_category_page(slug, products, total_in_stock, today)
        out_path = category_dir / f"{slug}.html"
        tmp_path = category_dir / f"{slug}.html.tmp"
        tmp_path.write_text(html)
        tmp_path.rename(out_path)
        in_stock = sum(1 for p in products if p["available"])
        print(f"  {slug}: {len(products)} products ({in_stock} in stock) -> {out_path}")
        pages_written += 1

    print(f"\nWrote {pages_written} category pages to {category_dir}")

    # Update sitemap
    update_sitemap(output_dir, today)

    # Patch dashboard footer
    patch_dashboard_footer(output_dir)

    print("Done.")


if __name__ == "__main__":
    main()
