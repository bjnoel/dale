#!/usr/bin/env python3
"""
Build state-based location pages for fruit tree availability.

Generates /buy-fruit-trees-[state].html for every state in
stocklib.registry.BUY_PAGE_STATE_SLUGS.
Shows nurseries that ship to each state, with in-stock product lists.

Products are filtered to fruit/edible species only using fruit_species.json.
Non-plant items (supplies, ornamentals) are excluded.

Usage:
    python3 build_location_pages.py /path/to/nursery-stock /path/to/output/
"""

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from cultivar_parsing import product_variety_slug
from shipping import SHIPPING_MAP, NURSERY_NAMES, nursery_note_for_state
from stocklib.registry import BUY_PAGE_STATE_SLUGS
from stocklib.snapshots import iter_nursery_snapshots, variant_min_price
from stocklib.flags import DIGEST_SIGNUP_ENABLED
from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer


# Non-plant keywords to exclude regardless of species match
from stocklib.classify import is_real_product
from stocklib.species_match import build_species_lookup, match_title
from stocklib.taxonomy import enabled_species
from stocklib.utm import outbound

# States to generate pages for
STATE_SLUGS = BUY_PAGE_STATE_SLUGS
STATES = list(STATE_SLUGS)

# State display names
STATE_NAMES = {
    "WA": "Western Australia",
    "QLD": "Queensland",
    "NSW": "New South Wales",
    "VIC": "Victoria",
    "SA": "South Australia",
}

# State-specific intro text
STATE_INTROS = {
    "WA": (
        # An earlier pass stripped a dash out of this sentence and left the two clauses
        # jammed together ("surprisingly hard most nurseries"). Removing a dash means
        # rewriting the sentence, not deleting the character.
        "Finding fruit trees online that ship to WA is surprisingly hard, because "
        "most nurseries are east coast only. These are the ones that do."
    ),
    "QLD": (
        "Queensland is warm enough to plant fruit trees most of the year. Plenty of "
        "good fruit tree nurseries are based here, and they're strong on tropical and "
        "subtropical varieties."
    ),
    "NSW": (
        "NSW runs from the subtropical north coast to the cool Southern Highlands. "
        "Most of these nurseries ship statewide, so it doesn't matter which part "
        "you're in."
    ),
    "VIC": (
        "Victoria's cold winters give stone fruit and apples the chill hours they need. "
        "Bare-root season (June to September) is when most people here stock up. "
        "These nurseries all ship to VIC."
    ),
    "SA": (
        "South Australia's Mediterranean climate runs from the cool Adelaide Hills, "
        "cold enough for apples and cherries, to the hot irrigated Riverland that "
        "grows some of the country's best citrus. These nurseries ship to SA."
    ),
}

# State-specific info box (None = no box)
STATE_INFO_BOX = {
    "WA": (
        "WA has strict quarantine rules, so only a handful of nurseries can legally "
        "send fruit trees here. These are the ones we track."
    ),
    "QLD": (
        "Queensland has its own biosecurity rules, and some stone fruit and citrus "
        "stock has to be treated before it can come across the border. The nurseries "
        "below all ship to QLD."
    ),
    "NSW": (
        "Most fruit trees can be sent into NSW from other states. If you're near a "
        "fruit fly exclusion zone in the Riverina or Murray region, check with your "
        "local council first."
    ),
    "VIC": (
        "Plants coming into Victoria from interstate need a plant health "
        "certificate. The nurseries below ship to VIC and sort out that paperwork "
        "for you."
    ),
    "SA": (
        "South Australia has fruit fly free status, so there are strict rules on "
        "bringing fruit across the border. Those rules are about fruit. Nursery trees "
        "are fine, and the nurseries below ship to SA and handle the plant health "
        "paperwork."
    ),
}

# State-specific growing guide content (unique per state for SEO differentiation)
STATE_GROWING_GUIDE = {
    "WA": None,  # WA already has unique quarantine content
    "QLD": """<section class="mb-8">
    <h2 class="text-lg font-semibold mb-3">Growing fruit trees in Queensland</h2>
    <div class="prose prose-sm max-w-none text-gray-700 space-y-3">
      <p>Queensland's climate divides into three fruit-growing zones. The far north (Cairns, Townsville) is true tropical territory: mangoes, bananas, carambola, durian and rambutan thrive here with little fuss. The southeast (Brisbane, Gold Coast, Sunshine Coast) is subtropical, supporting avocados, lychees, custard apples, macadamias and most citrus. The Darling Downs and granite belt at elevation can grow stone fruit and even apples with adequate chill hours.</p>
      <p>In QLD you don't need to wait for a planting window. Pot-grown trees can go in the ground any time of year, as long as you water them through the first summer. Bare-root stone fruit is still best planted in winter while it's dormant (June to September).</p>
      <p>Good choices for Brisbane and southeast QLD are avocado, lychee, mango (dwarf varieties do well in suburban yards), macadamia, dragon fruit, mulberry, fig and feijoa. Cherries, apples and pears struggle because they don't get enough chill, except up on the Granite Belt.</p>
    </div>
  </section>""",
    "NSW": """<section class="mb-8">
    <h2 class="text-lg font-semibold mb-3">Growing fruit trees in New South Wales</h2>
    <div class="prose prose-sm max-w-none text-gray-700 space-y-3">
      <p>NSW has a huge range of growing conditions. The north coast (Byron Bay, Coffs Harbour) is subtropical and suits avocados, macadamias, lychees and citrus. Sydney and the Central Coast are warm temperate, good for figs, citrus, stone fruit and subtropical exotics like feijoa and guava. The Southern Highlands and tablelands are cool enough for apples, pears, cherries and plums, the same varieties that thrive in Victoria.</p>
      <p>In the Riverina and Murray basin, hot dry summers and cold winters are great for stone fruit, almonds and table grapes. It's commercial orchard country. Wherever you are in NSW, match the variety to your chill: low-chill stone fruit on the coast, high-chill varieties up in the ranges.</p>
      <p>Most NSW growers can plant pot-grown trees year-round. Bare-root stock (available June to September) is cheaper and transplants well for deciduous species. As a rough guide, if your winter temperatures regularly drop below 7°C you can grow temperate stone fruit. If they rarely do, stick to subtropical varieties.</p>
    </div>
  </section>""",
    "VIC": """<section class="mb-8">
    <h2 class="text-lg font-semibold mb-3">Growing fruit trees in Victoria</h2>
    <div class="prose prose-sm max-w-none text-gray-700 space-y-3">
      <p>Victoria is great for cool-climate fruit. Its reliably cold winters give apples, pears, cherries, plums, peaches, nectarines and quinces the chill hours they need to fruit well. Heritage apples that would struggle in Queensland or WA do really well in the Yarra Ranges, the Mornington Peninsula and the central highlands.</p>
      <p>Bare-root season (June to September) is the main time to buy in Victoria. Bare-root trees are cheaper, they settle in quickly, and that's when you get the widest choice of varieties. Heritage Fruit Trees (in VIC) and Aus Nurseries both have big bare-root ranges then, so set an alert and you won't miss it.</p>
      <p>Melbourne and coastal Victoria can also support subtropical species in sheltered spots: figs, feijoas, persimmons and mulberries all do well. Avocados are marginal in Melbourne but succeed in frost-free microclimates on the Mornington Peninsula. Frost is the main limit. If your site regularly gets frost below -3°C, stick to fully cold-hardy deciduous fruit.</p>
    </div>
  </section>""",
    "SA": """<section class="mb-8">
    <h2 class="text-lg font-semibold mb-3">Growing fruit trees in South Australia</h2>
    <div class="prose prose-sm max-w-none text-gray-700 space-y-3">
      <p>South Australia packs an unusual range of growing conditions into a short drive. The Adelaide Hills sit high enough to bank real winter chill, which is why they are long-established apple, pear and cherry country around Lenswood and Forest Range. The Adelaide plains are warm, dry and close to frost free on the coast, suiting citrus, figs, olives, pomegranates, loquats and almonds. An hour east, the irrigated Riverland has the long hot summers that ripen some of the country's best oranges, mandarins and grapefruit.</p>
      <p>SA is the driest state in Australia, so summer watering matters more than frost or variety choice when it comes to keeping a young tree alive. Sort out your watering before you plant. Soils through much of the settled south are alkaline, which rules out acid-loving blueberries in open ground (grow them in pots or raised beds of acidic mix) but suits pomegranates, figs, olives and jujubes, all of which tolerate alkaline and even mildly salty ground.</p>
      <p>Pick varieties by how much winter chill you get. If you're in the hills, high-chill apples, pears, cherries and plums will fruit well. On the plains and through the Riverland the chill drops off quickly, so go for low-chill stone fruit and lean on citrus, Mediterranean and subtropical species that don't need cold winters at all.</p>
      <p>South Australia has fruit fly free status, and the well-known border rules on carrying fruit are about fruit only. Buying a tree from an interstate nursery listed here is normal and legal, and those nurseries handle the plant health certificates. The good news is that backyard growers here deal with far less fruit fly than people in the eastern states.</p>
    </div>
  </section>""",
}

# Per-state nursery notes now live in stocklib.registry.STATE_SHIPPING_NOTES,
# because the variety alert emails need exactly the same thing and
# tests/test_no_forking.py exists to stop a second copy appearing. The delivery
# half is derived from delivery_label() rather than typed: that is how
# "pickup only, Ellenbrook" survived here for five months, a suburb no record
# supports, contradicted by the registry, the scraper config and the nursery's
# own site, on a nursery that has never been contacted.


def nursery_note(state: str, key: str) -> str:
    """The note shown beside a nursery on a state page."""
    return nursery_note_for_state(key, state)

# Cross-state links per state: every other state we build a page for, in STATES
# order. Derived rather than typed, so adding a state cannot leave the new page
# unlinked from the four that already exist (which is how it would have shipped
# for SA in DAL-297).
CROSS_LINKS = {
    state: [(s, f"Buy in {s}") for s in STATES if s != state]
    for state in STATES
}

# Manual entries for local pickup nurseries not in the scraper
# Shown as an additional section on state pages
LOCAL_NURSERIES = {
    "WA": [
        {
            "name": "Leeming Fruit Trees",
            "address": "4a Westmorland Drive, Leeming, WA 6149",
            "hours": "Call 0413 062 856 to confirm hours",
            "phone": "0413 062 856",
            "facebook": "https://www.facebook.com/Leeming.Fruit.Trees/",
            "specialty": "Rare tropical fruit trees: lychee, rambutan, mangosteen, durian, abiu, wampee, custard apple, and more.",
            "note": "Pickup only, no online shop",
        },
    ],
}


def load_species() -> set[str]:
    """Load all known fruit species names and synonyms."""
    species_list = enabled_species()
    names = set()
    for s in species_list:
        names.add(s["common_name"].lower())
        for syn in s.get("synonyms", []):
            if syn:
                names.add(syn.lower())
    return names


def load_all_products(data_dir: Path) -> list[dict]:
    """Load all products from today's snapshot (or latest.json fallback)."""
    products = []
    for nursery_key, data in iter_nursery_snapshots(data_dir):
        nursery_name = data.get("nursery_name") or NURSERY_NAMES.get(nursery_key, nursery_key)
        in_stock_count = sum(1 for p in data.get("products", []) if p.get("any_available"))
        total_count = len(data.get("products", []))
        for p in data.get("products", []):
            title = p.get("title", "")
            min_price = p.get("min_price")
            if min_price is None:
                min_price = variant_min_price(p)
            available = bool(p.get("any_available", False))
            url = p.get("url", "")
            products.append({
                "title": title,
                "url": url,
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "nursery_in_stock": in_stock_count,
                "nursery_total": total_count,
                "price": round(float(min_price), 2) if min_price else None,
                "available": available,
            })
    return products


def get_nursery_stats(products: list[dict], state: str) -> list[dict]:
    """Get per-nursery stats for nurseries that ship to this state."""
    nursery_products = defaultdict(list)
    for p in products:
        nursery_products[p["nursery_key"]].append(p)

    stats = []
    for key, ships_to in SHIPPING_MAP.items():
        if state not in ships_to:
            continue
        prods = nursery_products.get(key, [])
        in_stock = sum(1 for p in prods if p.get("available"))
        total = len(prods)
        if total == 0:
            continue
        note = nursery_note(state, key)
        stats.append({
            "key": key,
            "name": NURSERY_NAMES.get(key, key),
            "in_stock": in_stock,
            "total": total,
            "note": note,
        })

    # Sort by in-stock count descending
    stats.sort(key=lambda x: x["in_stock"], reverse=True)
    return stats


SHOWCASE_SIZE = 60
MAX_PER_NURSERY = 10
MAX_PER_SPECIES = 3

# Weights. Scarcity dominates on purpose: on a state page the question is "what
# can I get here that is hard to get", and the number of state-reaching
# nurseries carrying a cultivar answers it directly from data we already have.
SCARCITY_WEIGHT = 40.0
HARD_TO_FIND_BONUS = 25.0

RARITY_SCORES_FILE = Path("/opt/dale/data/rarity_scores.json")


def load_rarity_scores() -> dict:
    """Species rarity written by build_species_pages.compute_rarity_scores.

    Missing file is not an error: these pages must still build on a machine
    that has never run the species builder, and compute_rarity_scores itself
    degrades the same way when a nursery has no availability history.
    """
    try:
        with open(RARITY_SCORES_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _showcase_species_slug(title: str, species_lookup: dict) -> str:
    sp = match_title(title, species_lookup)
    if not sp:
        return ""
    return sp["common_name"].lower().replace(" ", "-").replace("'", "")


def showcase_scores(products: list[dict], species_lookup: dict,
                    rarity_scores: dict) -> dict[int, float]:
    """Score each product by how hard it is to get in THIS state.

    Replaces a straight price-descending sort, whose comment read "interesting
    and rare plants tend to cost more". They do not reliably, and using price as
    the proxy handed the page to whichever nursery prices highest. Measured on
    2026-08-24: Perth Mobile Nursery held 53 of 60 rows on the WA page with
    everything between $349 and $1,400, and Ladybird held 37 of 60 on QLD, NSW
    and VIC, which made the QLD and NSW tables identical to each other in all 60
    rows. Nothing under $199.95 appeared on any eastern page.

    Two signals, both already on disk:

      scarcity     how few state-reaching nurseries stock this cultivar. A
                   cultivar one nursery has is the thing worth surfacing; one
                   that six have is a commodity. Keyed on the variety slug so
                   pot sizes of the same cultivar do not read as separate finds,
                   and falls back to the title when a title names no cultivar.
      hard_to_find the species-level flag from rarity_scores.json, itself built
                   from months of availability history (60% nursery scarcity,
                   40% time out of stock).

    Deliberately NOT included: a recency bonus. The only per-product "newly
    listed" field in the snapshots is Shopify's created_at, so scoring on it
    would quietly rank Shopify nurseries above WooCommerce ones. The unbiased
    source is first_seen in availability.json, which is server-only and absent
    from the golden fixture, so it would ship untested. Left for a follow-up.
    """
    keys = {}
    nurseries_per_key: dict[str, set] = defaultdict(set)
    for i, p in enumerate(products):
        key = product_variety_slug(p["title"]) or p["title"].strip().lower()
        keys[i] = key
        nurseries_per_key[key].add(p["nursery_key"])

    scores = {}
    for i, p in enumerate(products):
        score = SCARCITY_WEIGHT / len(nurseries_per_key[keys[i]])
        slug = _showcase_species_slug(p["title"], species_lookup)
        if rarity_scores.get(slug, {}).get("hard_to_find"):
            score += HARD_TO_FIND_BONUS
        scores[i] = score
    return scores


def pick_showcase(products: list[dict], species_lookup: dict,
                  rarity_scores: dict, size: int = SHOWCASE_SIZE) -> list[dict]:
    """Take the top `size` products, capped per nursery and per species.

    The caps are what stop one catalogue owning the page. Without the species
    cap the same prototype put five Daleys lilly pillies in the top ten, which
    is a different monopoly with the same effect on the reader.
    """
    scores = showcase_scores(products, species_lookup, rarity_scores)
    order = sorted(range(len(products)),
                   key=lambda i: (-scores[i], products[i]["title"]))

    species_of = {i: _showcase_species_slug(p["title"], species_lookup)
                  for i, p in enumerate(products)}

    # The caps stop one catalogue crowding OUT the others. Where there are no
    # others they have nothing to protect, so they lift to whatever the material
    # can support rather than shrinking the page: a state served by only three
    # nurseries would otherwise show 30 rows while 60 good products sat unshown.
    # On the real data this never binds (WA has 9 nurseries and ~106 species in
    # stock, so 10 and 3 already allow 90 and 318 rows); it only decides what a
    # thin state page does.
    n_nurseries = len({p["nursery_key"] for p in products}) or 1
    n_species = len({s for s in species_of.values() if s}) or 1
    nursery_cap = max(MAX_PER_NURSERY, -(-size // n_nurseries))
    species_cap = max(MAX_PER_SPECIES, -(-size // n_species))

    per_nursery: Counter = Counter()
    per_species: Counter = Counter()
    shown = []
    for i in order:
        p = products[i]
        sp = species_of[i]
        if per_nursery[p["nursery_key"]] >= nursery_cap:
            continue
        if sp and per_species[sp] >= species_cap:
            continue
        per_nursery[p["nursery_key"]] += 1
        if sp:
            per_species[sp] += 1
        shown.append(p)
        if len(shown) == size:
            break
    return shown


def build_page(state: str, products: list[dict], species_lookup: dict, today_str: str,
               output_dir: Path = None, rarity_scores: dict | None = None) -> str:
    state_name = STATE_NAMES[state]
    state_abbr = state
    rarity_scores = rarity_scores or {}
    intro = STATE_INTROS[state]
    info_box = STATE_INFO_BOX.get(state)

    # Nurseries that ship to this state
    nursery_stats = get_nursery_stats(products, state)
    total_in_stock = sum(n["in_stock"] for n in nursery_stats)
    nursery_count = len(nursery_stats)

    # Products for this state: nurseries that ship here, fruit/edible only, no non-plants
    state_nurseries = {n["key"] for n in nursery_stats}
    state_products = []
    for p in products:
        if p["nursery_key"] not in state_nurseries:
            continue
        if not p["available"]:
            continue
        if not is_real_product(p["title"]):
            continue
        # Must match a known fruit species
        if not match_title(p["title"], species_lookup):
            continue
        state_products.append(p)

    shown = pick_showcase(state_products, species_lookup, rarity_scores)
    shown_count = len(shown)

    # Species combo links: count in-stock products per species for this state, build links
    species_counts: Counter = Counter()
    species_names: dict[str, str] = {}
    for p in state_products:
        sp = match_title(p["title"], species_lookup)
        if sp:
            sp_slug = sp["common_name"].lower().replace(" ", "-").replace("'", "")
            species_counts[sp_slug] += 1
            species_names[sp_slug] = sp["common_name"]
    state_slug_str = STATE_SLUGS[state]
    MIN_COMBO = 3
    species_combo_links = [
        (slug, species_names[slug], count)
        for slug, count in species_counts.most_common()
        if count >= MIN_COMBO
    ]

    # Cross-state links
    cross_links = CROSS_LINKS[state]
    cross_html = " &middot; ".join(
        f'<a href="/buy-fruit-trees-{s.lower()}.html" class="text-green-700 hover:underline">{label}</a>'
        for s, label in cross_links
    )

    # Local pickup nurseries (manual, non-scraped) -- rendered in the template
    local_nurseries = LOCAL_NURSERIES.get(state, [])

    # Canonical date string
    try:
        dt = datetime.strptime(today_str, "%Y-%m-%d")
        date_display = dt.strftime("%-d %B %Y")
    except Exception:
        date_display = today_str

    # State-specific growing guide (pre-built HTML, rendered |safe in the template)
    growing_guide_html = STATE_GROWING_GUIDE.get(state) or ""

    # Species combo links -- only to species/state pages that actually exist
    valid_combo_links = [
        (sp_slug, sp_name, count)
        for sp_slug, sp_name, count in species_combo_links
        if output_dir is None or (output_dir / f"buy-{sp_slug}-trees-{state_slug_str}.html").exists()
    ]

    slug = state.lower()

    head = render_head(
        title=f"Buy Fruit Trees Online in {state_name} | treestock.com.au",
        description=f"Find fruit trees for sale online that ship to {state_name}. {total_in_stock} varieties in stock across {nursery_count} nurseries, updated daily. Compare prices and check availability.",
        canonical_url=f"https://treestock.com.au/buy-fruit-trees-{slug}.html",
        og_title=f"Fruit Trees for Sale Online in {state_name}",
        og_description=f"Find fruit trees for sale online that ship to {state_name}. {total_in_stock} varieties in stock across {nursery_count} nurseries, updated daily.",
        extra_head='<meta name="robots" content="index, follow">',
    )
    header = render_header()
    breadcrumb = render_breadcrumb([("Home", "/"), (f"Fruit trees for sale, {state_name}", "")])
    footer = render_footer()

    shown_view = [
        {
            "url": outbound(p["url"], "location-page"),
            "title": p["title"],
            "price_str": f"${p['price']:.2f}" if p["price"] else "POA",
            "nursery_name": p["nursery_name"],
        }
        for p in shown
    ]
    combo_view = [{"slug": s, "name": n, "count": c} for s, n, c in valid_combo_links]

    return render_template(
        "location_page.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        state_name=state_name, state_abbr=state_abbr,
        date_display=date_display, total_in_stock=total_in_stock,
        nursery_count=nursery_count, intro=intro, info_box=info_box,
        nursery_stats=nursery_stats, products=shown_view, shown_count=shown_count,
        local_nurseries=local_nurseries, combo_links=combo_view,
        state_slug_str=state_slug_str, growing_guide_html=growing_guide_html,
        cross_html=cross_html, digest_signup=DIGEST_SIGNUP_ENABLED,
    )


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} /path/to/nursery-stock /path/to/output/")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print("Loading species...")
    species_list = enabled_species()
    species_lookup = build_species_lookup(species_list)
    print(f"  {len(species_lookup)} species/synonyms loaded")

    print("Loading products...")
    products = load_all_products(data_dir)
    print(f"  {len(products)} products loaded")

    # Resolve rarity_scores.json relative to data_dir so the golden fixture is
    # used in tests rather than the live server path (same trick as
    # build_rare_finds.py and build-dashboard.py).
    global RARITY_SCORES_FILE
    RARITY_SCORES_FILE = data_dir.parent / "rarity_scores.json"
    rarity_scores = load_rarity_scores()
    print(f"  {len(rarity_scores)} species rarity scores loaded")

    for state in STATES:
        print(f"\nBuilding {state} page...")
        html = build_page(state, products, species_lookup, today, output_dir, rarity_scores)
        out_file = output_dir / f"buy-fruit-trees-{state.lower()}.html"
        out_file.write_text(html)

        # Count for summary
        state_nurseries = {
            k for k, v in SHIPPING_MAP.items() if state in v
        }
        in_stock = sum(
            1 for p in products
            if p["nursery_key"] in state_nurseries
            and p["available"]
            and is_real_product(p["title"])
            and match_title(p["title"], species_lookup)
        )
        print(f"  Written: {out_file} ({in_stock} matched in-stock products)")

    print("\nDone.")


if __name__ == "__main__":
    main()
