#!/usr/bin/env python3
"""
Build species+state SEO combo pages for treestock.com.au.

Generates pages like:
  /buy-mango-trees-queensland.html
  /buy-apple-trees-western-australia.html

Pages are created for species+state combinations with >= 3 in-stock products
at nurseries that ship to that state. Limits: WA (all), QLD/NSW/VIC (top 20 each).

Usage:
    python3 build_species_state_pages.py /path/to/nursery-stock /path/to/output/
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from shipping import SHIPPING_MAP, NURSERY_NAMES
from stocklib.snapshots import iter_nursery_snapshots, variant_min_price
from stocklib.templates import render as render_template
from treestock_layout import (
    render_head,
    render_header,
    render_breadcrumb,
    render_footer,
    render_treesmith_promo,
)
import growing_guides

SPECIES_FILE = Path(__file__).parent / "fruit_species.json"
MIN_PRODUCTS = 3
MAX_COMBOS_PER_STATE = 20  # Limit for QLD/NSW/VIC to avoid thin content

# State full names for URLs and headings
STATE_FULL_NAMES = {
    "WA": "Western Australia",
    "QLD": "Queensland",
    "NSW": "New South Wales",
    "VIC": "Victoria",
}
STATE_SLUGS = {
    "WA": "western-australia",
    "QLD": "queensland",
    "NSW": "new-south-wales",
    "VIC": "victoria",
}

# State-specific climate context per species category.
# Copy rule: no em or en dashes (use commas, periods, parentheses). The "mediterranean"
# category exists so olive and grape stop inheriting the stone/pome-fruit chill-hours note.
STATE_CLIMATE_NOTES = {
    "WA": {
        "tropical": "Perth and northern WA have a warm, dry climate that suits many tropical species, though summer heat requires regular watering. WA's strict quarantine rules mean only a handful of eastern states nurseries can ship here.",
        "subtropical": "Perth's Mediterranean climate suits subtropical species well, especially with summer irrigation. WA quarantine restrictions limit which nurseries can ship here.",
        "citrus": "Citrus trees thrive in Perth's warm, dry climate. WA has strict biosecurity rules, so not all eastern nurseries can ship here, which makes local options especially valuable.",
        "temperate": "South-west WA's mild winters suit temperate stone fruit and pome fruit, though winters are less cold than eastern states. Chilling hours may be lower, so choose low-chill varieties. WA quarantine rules apply.",
        "mediterranean": "South-west WA's Mediterranean climate (hot dry summers, mild wet winters) is close to ideal for olives, grapes and figs, which need summer heat to ripen and have only a low winter-chill requirement, far less than stone fruit. WA's strict quarantine rules limit which interstate nurseries can ship live plants here.",
        "banana": "Bananas grow in the warm, frost-free parts of WA, but live banana plants cannot simply be brought in from interstate. WA quarantine rules require planting material to meet strict import conditions, so source WA-grown, certified disease-free plants.",
        "cherry": "Cherries are the most chill-demanding of the common stone fruits, needing a long, cold winter that almost no part of WA reliably provides, so they crop only in the coldest southern hill and forest districts, and low-chill types are the realistic backyard option. WA's strict quarantine rules also limit which interstate nurseries can ship live cherry trees here.",
        "mulberry": "Mulberries are tough, widely adapted trees that grow across most of WA, from Perth gardens to the Wheatbelt and the warm Gascoyne. They need no winter chill and are very drought-tolerant once established, so they suit WA well with a little summer water. WA's strict quarantine rules limit which interstate nurseries can ship live plants here.",
        "jujube": "Western Australia is one of Australia's main jujube regions. Its hot, dry summers, mild winters and free-draining soils suit this deciduous, intensely drought and heat hardy tree, which also copes with the salty and alkaline ground that defeats most fruit trees. Quarantine rules apply to live trees sent in from other states, so locally grown stock is often the easiest to buy, and Mediterranean fruit fly is the pest to net against.",
        "passionfruit": "Passionfruit grows well on Perth's frost-free coastal plain and through the warm south-west, with a small industry in the hot north. Western Australia has Mediterranean fruit fly rather than Queensland fruit fly, and strict quarantine means only a handful of interstate nurseries can ship live vines here, so local stock and seed-grown plants are especially useful.",
        "pecan": "Pecans are large deciduous nut trees that need a long, hot summer to fill their kernels rather than much winter chill, so in Western Australia they suit the warm inland and the hotter parts of the south-west where summer water is on hand, not the cool, wet far south. WA's strict quarantine rules also limit which interstate nurseries can ship live pecan trees here.",
        "pomegranate": "South-west WA's Mediterranean climate (hot dry summers, mild wet winters) suits pomegranates, which need summer heat to ripen and have only a low winter-chill requirement. The dry WA summer also means far less of the fruit splitting and rot that humidity causes. WA's strict quarantine rules limit which interstate nurseries can ship live plants here.",
        "blueberry": "Blueberries are acid-soil shrubs, not chill-hungry stone fruit: the make-or-break factor is a strongly acidic soil (pH 4.5 to 5.5), which Perth's alkaline sands and hard bore water work against, so most WA growers raise them in beds or pots of acidic mix. Warm districts suit low-chill southern highbush and rabbiteye, while the cooler south coast can also ripen the deciduous northern highbush. WA's strict quarantine rules limit which interstate nurseries can ship live plants here.",
        "default": "WA's strict quarantine rules limit which nurseries can legally ship fruit trees here. These are the options that can.",
    },
    "QLD": {
        "tropical": "Queensland's warm, humid climate is ideal for tropical fruit trees. Most tropical species that struggle elsewhere in Australia thrive in QLD's long warm season.",
        "subtropical": "Southeast Queensland's subtropical climate suits a huge range of fruit trees, from mangoes and avocados to citrus and figs.",
        "citrus": "Queensland's warm climate produces excellent citrus. Summer humidity can cause some fungal issues, but most varieties do well with good air circulation.",
        "temperate": "Southern Queensland can grow many temperate fruit trees, though chilling hours are lower than further south. Choose low-chill apple, pear, and stone fruit varieties.",
        "mediterranean": "Olives, grapes and figs prefer a drier, Mediterranean-style climate, so in Queensland they do best in the cooler, drier inland and elevated districts (such as the Granite Belt) rather than the humid coast and tropics.",
        "banana": "Queensland's warm, humid, frost-free climate is ideal for bananas, which is why the far north grows almost all of Australia's crop. Biosecurity rules restrict moving banana plants between zones.",
        "cherry": "Cherries need far more winter chill than almost all of Queensland provides, so they are limited to the coldest, highest part of the state. Across the warm coast, the subtropics and the tropics, winters are too mild for sweet cherries to flower and fruit reliably.",
        "mulberry": "Mulberries are among the easiest fruit trees to grow in Queensland, cropping heavily from the subtropical south-east to the tropical north. They tolerate heat and humidity far better than most deciduous fruit trees and need no winter chill.",
        "jujube": "Jujube is a hot, dry climate tree, so in Queensland it belongs in the warm, dry inland rather than the humid coast or the wet tropics, where damp weather near harvest spoils the fruit and raises disease pressure. It needs a hot summer to ripen and only a little winter chill, both of which the inland supplies.",
        "passionfruit": "Queensland's warm, humid, largely frost-free climate is the heartland of Australian passionfruit, and the state grows most of the national crop. Purple and black types suit the cooler south-east, while larger Panama and golden types handle the humid tropical north.",
        "pecan": "Pecans need a long, hot growing season and deep, well-drained soil with plenty of summer water, so in Queensland they crop best in the warm inland and southern districts under irrigation rather than on the humid tropical coast. Australia is free of the pecan scab disease that troubles humid overseas regions, which is a real advantage here.",
        "pomegranate": "Pomegranates want hot dry summers, so in Queensland they fruit best in the cooler, drier inland and elevated districts rather than the humid coast, subtropics or tropics, where humidity and summer rain make the fruit split, rot and ripen poorly.",
        "blueberry": "Blueberries need a strongly acidic soil (pH 4.5 to 5.5) far more than they need winter chill, so in Queensland choose low-chill, often evergreen southern highbush and rabbiteye and skip the cold-climate northern highbush. In the warm subtropics the bushes crop earlier and a vigorous plant can give a second, lighter flush, though humidity lifts disease pressure.",
        "default": "Queensland nurseries and those that ship to QLD offer a wide selection suited to warm and subtropical climates.",
    },
    "NSW": {
        "tropical": "Coastal NSW has a warm temperate to subtropical climate that suits many tropical species, particularly in the north. Frost risk in inland and high-altitude areas.",
        "subtropical": "Coastal and northern NSW suits subtropical fruit trees well. Inland and southern areas have cooler winters, so choose frost-tolerant varieties.",
        "citrus": "Citrus does well across most of NSW, from the warm north coast to the cooler tablelands. Most popular citrus varieties suit NSW conditions.",
        "temperate": "NSW's diverse climate supports a wide range of temperate fruit trees, from the cool tablelands to the warmer coastal plains.",
        "mediterranean": "Olives, grapes and figs suit NSW's warmer inland and temperate districts with hot dry summers, and they have little winter-chill requirement. Young trees can be frost-sensitive in the coldest tableland areas.",
        "banana": "Warm, frost-free parts of coastal NSW, mainly the subtropical north, suit bananas. Banana bunchy top virus is a serious local risk, so plant only certified material and never move suckers between gardens.",
        "cherry": "Cherries are the most chill-demanding stone fruit and crop only where winters are genuinely cold, so in New South Wales they are a tree for the cool tablelands, not the warm coast or the hot inland plains.",
        "mulberry": "Mulberries grow almost anywhere in New South Wales, from the warm coast to the cold tablelands, and are one of the most reliable backyard fruit trees in the state. They need no winter chill and shrug off frost once established.",
        "jujube": "Jujube thrives on long, hot, dry summers and tolerates drought, frost and poor soils, so in New South Wales it suits the warm inland far better than the humid coast. A little winter chill and a dry ripening autumn give the best fruit.",
        "passionfruit": "The warm subtropical north coast of New South Wales suits passionfruit well, especially the purple and black types. Frost limits it on the cold tablelands and through the inland, so pick a sheltered, sunny spot away from cold hollows and choose a hardy grafted vine in cooler districts.",
        "pecan": "Pecans are a major inland New South Wales nut crop, suited to districts with hot summers, cool winters and reliable irrigation water, which is why the warm, irrigated northern valleys grow most of Australia's crop. They are very large, long-lived trees, so give them plenty of room.",
        "pomegranate": "Pomegranates suit the hot, dry inland of New South Wales. On the humid coast the fruit is prone to splitting and rot, and in the coldest tablelands frost can set back young plants, so the warm, dry interior is the reliable choice.",
        "blueberry": "Blueberries are acid-soil shrubs (they want a soil pH of 4.5 to 5.5, not lime), and New South Wales grows more of them than any other state. Evergreen low-chill southern highbush suit the warm coast, while the cold tablelands also ripen the deciduous northern highbush. Plant two of the same type for the heaviest crops.",
        "default": "NSW has a wide range of climates, so most fruit tree varieties available here are suited to warm temperate to subtropical conditions.",
    },
    "VIC": {
        "tropical": "Victoria's cool temperate climate is challenging for tropical species. Stick to cold-hardy varieties and sheltered positions. Most tropical nurseries do not ship to VIC.",
        "subtropical": "Victoria's cool winters suit subtropical varieties in sheltered, north-facing positions. Many subtropical nurseries do not ship to VIC.",
        "citrus": "Citrus can be grown in Victoria in warm, sheltered spots. Frost protection is essential in most areas. Choose cold-tolerant varieties like Meyer Lemon or Lisbon.",
        "temperate": "Victoria's cool temperate climate is ideal for stone fruit, apples, and pears. Cold winters provide the chilling hours these trees need. Heritage varieties do particularly well.",
        "mediterranean": "Victoria's warm dry summers and mild winters suit olives, grapes and figs, which have little winter-chill requirement. Cooler districts simply ripen the fruit later, and frost can set back young trees.",
        "banana": "Victoria is too cold and frost-prone for bananas to crop reliably. They can be grown as a foliage plant or in a warm, sheltered courtyard or pot, but expect little or no fruit.",
        "cherry": "Victoria's cold winters give cherries the deep chill they need, which is why it is one of Australia's main cherry states. They crop best in the cool hill and high-country districts, while the warmest lowland areas are more marginal.",
        "mulberry": "Mulberries are fully cold-hardy and crop reliably right across Victoria, including the cool central and southern districts. They need no winter chill, tolerate frost once established, and simply ripen a little later where summers are cooler.",
        "jujube": "Victoria's hot, dry northern inland suits jujube well, while the cooler, wetter south is more marginal because the fruit ripens late and damp autumn weather can spoil it. The tree is very frost hardy when dormant and needs a hot summer to ripen its fruit.",
        "passionfruit": "Victoria is cool and frost-prone for a subtropical vine, so passionfruit is a marginal, short-lived crop here. A grafted Nellie Kelly on hardy blue passionflower rootstock, grown against a hot sheltered wall, is the dependable choice, and some nurseries will not post perishable vines this far south.",
        "pecan": "Pecans need a long, hot summer to ripen and fill their nuts, which makes Victoria marginal for them. They crop best in the warm, irrigated northern districts and are unreliable in the cool, frost-prone south, where the season is often too short to finish the nuts.",
        "pomegranate": "Victoria's warm, dry inland summers and mild winters suit pomegranates, which have a low winter-chill requirement. Cooler southern and coastal districts ripen the fruit later and less reliably, and frost can set back young plants.",
        "blueberry": "Blueberries need a strongly acidic soil (pH 4.5 to 5.5) above all else, and Victoria's reliably cold winters also let it grow the full range, including the deciduous, high-chill northern highbush that warmer states struggle with. Cool conditions ripen the fruit later and larger, and birds are the main pest.",
        "default": "Victoria's cool temperate climate suits a wide range of stone fruit, apples, and pears. Heritage and heirloom varieties are a specialty of Victorian nurseries.",
    },
}

# Per-species climate category (for climate note lookup)
SPECIES_CLIMATE_CATEGORY = {
    "mango": "tropical", "lychee": "tropical", "longan": "tropical",
    "rambutan": "tropical", "durian": "tropical", "mangosteen": "tropical",
    "abiu": "tropical", "sapodilla": "tropical", "black sapote": "tropical",
    "rollinia": "tropical", "canistel": "tropical", "miracle fruit": "tropical",
    "papaya": "tropical", "carambola": "tropical", "starfruit": "tropical",
    "jackfruit": "tropical", "soursop": "tropical", "custard apple": "subtropical",
    "dragon fruit": "tropical", "wax jambu": "tropical",
    "avocado": "subtropical", "guava": "subtropical", "jaboticaba": "subtropical",
    "feijoa": "subtropical", "loquat": "subtropical",
    "persimmon": "temperate", "pawpaw": "subtropical", "tamarillo": "subtropical",
    "lemon": "citrus", "lime": "citrus", "orange": "citrus",
    "mandarin": "citrus", "grapefruit": "citrus", "tangelo": "citrus",
    "cumquat": "citrus", "pomelo": "citrus", "finger lime": "citrus",
    "apple": "temperate", "pear": "temperate", "plum": "temperate",
    "peach": "temperate", "nectarine": "temperate",
    "apricot": "temperate", "quince": "temperate",
    "raspberry": "temperate", "blackberry": "temperate",
    "strawberry": "temperate",
    # Mediterranean-climate crops: no winter-chill requirement, so they must not
    # inherit the stone/pome-fruit chill-hours note. Figs are a common fig
    # (Ficus carica) Mediterranean crop too, not a humid subtropical one.
    "olive": "mediterranean", "grape": "mediterranean", "fig": "mediterranean",
    # Banana has its own category so its WA note can carry the real story: live
    # banana planting material cannot simply be brought into WA (quarantine), and
    # banana bunchy top virus is the headline backyard risk in the eastern states.
    "banana": "banana",
    # Cherry is the highest-chill of the common stone fruits (most sweet cherries
    # want ~800 to 1200 hours), so the generic "temperate / choose low-chill
    # varieties" note is wrong for it: there are few low-chill cherries, and most
    # of WA and almost all of QLD cannot supply the chill at all. Its own category
    # lets each state note tell the true cold-climate story.
    "cherry": "cherry",
    # Mulberry gets its own category. It is one of the most climate-flexible fruit
    # trees grown here (subtropical Queensland through to cold-climate Victoria), needs
    # no winter chill, and is very frost and drought hardy, so it must NOT inherit the
    # "subtropical" note that wrongly implies it is marginal and frost-tender in the
    # cooler south. The per-state notes below tell the real story.
    "mulberry": "mulberry",
    # Jujube gets its own category. It is a hot-dry-climate deciduous tree that is
    # intensely heat and drought hardy, tolerates alkaline and saline soils, needs a
    # hot summer plus only a low winter chill, and does poorly in humid climates. No
    # existing category fits: "temperate / choose low-chill varieties" understates its
    # heat and drought love, "mediterranean" is about olives/grapes/figs, and the
    # generic WA note wrongly implies jujube is hard to get here when WA is in fact
    # one of Australia's two leading jujube-producing states.
    "jujube": "jujube",
    # Passionfruit is a frost-tender subtropical vine with a story the generic
    # "subtropical" note misses: Queensland grows most of the national crop; WA has
    # Mediterranean (not Queensland) fruit fly plus a quarantine hurdle on live vines;
    # Victoria leans on a grafted, cold-tolerant rootstock. Its own category lets each
    # state note carry that truth.
    "passionfruit": "passionfruit",
    # Pecan is a large deciduous nut tree, not a stone or pome fruit. Its limiting
    # factor is a long, hot summer (heat units fill the kernels), NOT winter chill,
    # which it needs only a little of, so the generic "temperate / choose low-chill
    # varieties" note is the wrong story for it. Its own category lets each state
    # note lead with summer heat, irrigation and the scab-free advantage instead.
    "pecan": "pecan",
    # Pomegranate gets its own category rather than joining "mediterranean". It shares
    # the low winter-chill, hot-dry-summer profile of olive/grape/fig, but its decisive
    # per-state story is fruit SPLITTING and rot in humidity (a non-issue for olives),
    # so the eastern-state notes below need to say that plainly instead of inheriting
    # the olive/grape mediterranean wording.
    "pomegranate": "pomegranate",
    # Blueberry gets its own category. Unlike a stone or pome fruit, its defining need
    # is not winter chill but a strongly acidic soil (pH 4.5 to 5.5), and it splits into
    # low-chill (southern highbush, rabbiteye) types for warm areas and high-chill
    # (northern highbush) types for cool ones. The generic "temperate / choose low-chill
    # varieties" note misses both points, so each state note leads with the acid-soil
    # rule and names the blueberry type that suits that climate.
    "blueberry": "blueberry",
}

from stocklib.classify import NON_PLANT_KEYWORDS


def load_species() -> list[dict]:
    with open(SPECIES_FILE) as f:
        return json.load(f)


def build_species_lookup(species_list: list[dict]) -> dict:
    lookup = {}
    for s in species_list:
        lookup[s["common_name"].lower()] = s
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = s
    return lookup


def match_title(title: str, lookup: dict) -> dict | None:
    t = title.lower()
    words = re.split(r"[\s\-\u2013\u2014]+", t)
    for n in range(min(len(words), 5), 0, -1):
        candidate = " ".join(words[:n])
        if candidate in lookup:
            return lookup[candidate]
    return None


def is_non_plant(title: str) -> bool:
    t = title.lower()
    if any(kw in t for kw in NON_PLANT_KEYWORDS):
        return True
    if re.search(r"\bseeds?\b", t) and "seedling" not in t and "seedless" not in t:
        return True
    return False


def load_all_products(data_dir: Path) -> list[dict]:
    products = []
    for nursery_key, data in iter_nursery_snapshots(data_dir):
        nursery_name = data.get("nursery_name") or NURSERY_NAMES.get(nursery_key, nursery_key)
        for p in data.get("products", []):
            title = p.get("title", "")
            min_price = p.get("min_price")
            if min_price is None:
                min_price = variant_min_price(p)
            products.append({
                "title": title,
                "url": p.get("url", ""),
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "price": round(float(min_price), 2) if min_price else None,
                "available": bool(p.get("any_available", False)),
            })
    return products


def compute_combos(
    products: list[dict], species_lookup: dict
) -> dict[str, dict[str, list[dict]]]:
    """
    Returns: state -> species_slug -> list of in-stock products (with species info).
    Only includes combos where nursery ships to that state.
    """
    result: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for p in products:
        if not p["available"]:
            continue
        if is_non_plant(p["title"]):
            continue
        species = match_title(p["title"], species_lookup)
        if not species:
            continue
        ships_to = SHIPPING_MAP.get(p["nursery_key"], [])
        species_slug = species["common_name"].lower().replace(" ", "-").replace("'", "")
        for state in ["WA", "QLD", "NSW", "VIC"]:
            if state in ships_to:
                result[state][species_slug].append({**p, "species": species})
    return result


def select_combos(
    combos: dict[str, dict[str, list[dict]]]
) -> dict[str, list[tuple[str, list[dict]]]]:
    """
    Select which combos to build pages for.
    WA: all with MIN_PRODUCTS+
    QLD/NSW/VIC: top MAX_COMBOS_PER_STATE by product count
    Returns: state -> [(species_slug, products), ...]
    """
    selected = {}
    for state in ["WA", "QLD", "NSW", "VIC"]:
        state_combos = [
            (slug, prods)
            for slug, prods in combos[state].items()
            if len(prods) >= MIN_PRODUCTS
        ]
        state_combos.sort(key=lambda x: -len(x[1]))
        limit = None if state == "WA" else MAX_COMBOS_PER_STATE
        selected[state] = state_combos[:limit] if limit else state_combos
    return selected


def get_climate_note(species_name: str, state: str) -> str:
    category = SPECIES_CLIMATE_CATEGORY.get(species_name.lower(), "default")
    notes = STATE_CLIMATE_NOTES.get(state, {})
    return notes.get(category, notes.get("default", ""))


def _no_dash(text: str) -> str:
    """Strip en and em dashes from external strings (nursery product titles and
    names) so passthrough data never breaks the treestock copy rule on the page."""
    return text.replace("—", "-").replace("–", "-")


def build_combo_page(
    state: str,
    species_slug: str,
    products: list[dict],
    today_str: str,
) -> str:
    species_info = products[0]["species"]
    species_name = species_info["common_name"]
    state_full = STATE_FULL_NAMES[state]
    state_slug = STATE_SLUGS[state]
    latin = species_info.get("latin_name", "")
    description = species_info.get("description", "")

    # Nursery breakdown
    nurseries: dict[str, list[dict]] = defaultdict(list)
    for p in products:
        nurseries[p["nursery_key"]].append(p)
    nursery_count = len(nurseries)

    climate_note = get_climate_note(species_name, state)

    # Price range across all products
    prices = [p["price"] for p in products if p["price"]]
    price_str = ""
    if prices:
        lo, hi = min(prices), max(prices)
        price_str = f"${lo:.0f}" if lo == hi else f"${lo:.0f}-${hi:.0f}"

    # Other states that have this species (for cross-links)
    other_states = [s for s in ["WA", "QLD", "NSW", "VIC"] if s != state]

    # Build product rows (limit to 60, sorted by price desc)
    sorted_products = sorted(products, key=lambda x: x["price"] or 0, reverse=True)[:60]

    product_view = []
    for p in sorted_products:
        product_view.append({
            "url": p["url"],
            "title": _no_dash(p["title"]),
            "nursery_name": _no_dash(p["nursery_name"]),
            "price_cell": f"${p['price']:.0f}" if p["price"] else "",
        })

    # Summary of nurseries carrying this species to this state
    nursery_list_items = ""
    for key, prods in sorted(nurseries.items(), key=lambda x: -len(x[1])):
        nname = _no_dash(prods[0]["nursery_name"])
        count = len(prods)
        nursery_list_items += f'<li><a href="/nursery/{key}.html" class="text-green-700 hover:underline">{nname}</a> ({count} {species_name.lower()} varieties)</li>\n'

    # Cross-links to other state combo pages (will exist if they were generated)
    cross_links = "".join(
        f'<a href="/buy-{species_slug}-trees-{STATE_SLUGS[s]}.html" class="inline-block text-sm text-green-700 hover:underline mr-4">{species_name} trees in {STATE_FULL_NAMES[s]} &rarr;</a>'
        for s in other_states
    )

    species_page_link = f"/species/{species_slug}.html"

    total_products = len(products)
    shown_count = len(sorted_products)
    shown_note = f" (showing {shown_count} of {total_products})" if total_products > shown_count else ""

    page_title = f"Buy {species_name} Trees in {state_full} | treestock.com.au"
    meta_desc = f"Compare {species_name} trees available in {state_full}. {total_products} in-stock options from {nursery_count} nurseries. Prices, varieties, and shipping details."
    if price_str:
        meta_desc = f"Compare {species_name} trees in {state_full}. {total_products} in-stock options from {nursery_count} nurseries, {price_str}. Updated daily."

    canonical = f"https://treestock.com.au/buy-{species_slug}-trees-{state_slug}.html"

    # Rich, cited per-state growing guide when this species has one; otherwise the
    # existing generic fruit_species.json blurb (graceful, additive fallback).
    # faq_ld feeds FAQPage JSON-LD into <head> to match the visible FAQ.
    has_rich_guide = growing_guides.has_guide(species_slug)
    faq_ld = growing_guides.faq_jsonld(species_slug, state) if has_rich_guide else ""

    head = render_head(
        page_title,
        meta_desc,
        canonical,
        extra_head=faq_ld,
        og_title=f"Buy {species_name} Trees in {state_full}",
        og_description=meta_desc,
        og_image="https://treestock.com.au/og-image.png",
        og_type="article",
    )
    header = render_header()
    breadcrumb = render_breadcrumb([
        ("Home", "/"),
        (f"Fruit trees in {state}", f"/buy-fruit-trees-{state.lower()}.html"),
        (f"{species_name} in {state_full}", ""),
    ])
    footer = render_footer()

    latin_note = f" <span class='text-gray-400 italic text-base'>({latin})</span>" if latin else ""

    desc_para = ""
    if description:
        desc_para = f'<div class="prose prose-sm text-gray-700 mt-3 mb-4 max-w-2xl">{description}</div>'

    # State-unique cited guide when available, else the generic blurb. This is what
    # makes the WA/QLD/NSW/VIC pages stop sharing a byte-identical editorial body.
    # Both are curated, first-party HTML, so the template renders the slot |safe.
    guide_body = (
        growing_guides.render_combo_guide(species_slug, state)
        if has_rich_guide else desc_para
    )
    treesmith_promo = render_treesmith_promo("species")

    climate_para = ""
    if climate_note:
        climate_para = f'<div class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6 text-sm text-amber-900">{climate_note}</div>'

    return render_template(
        "species_state_combo.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        species_name=species_name, state_full=state_full, state=state,
        state_lower=state.lower(), species_slug=species_slug,
        latin_note=latin_note, today_str=today_str, total_products=total_products,
        nursery_count=nursery_count, price_str=price_str, shown_note=shown_note,
        climate_para=climate_para, guide_body=guide_body, treesmith_promo=treesmith_promo,
        nursery_list_items=nursery_list_items, cross_links=cross_links,
        product_view=product_view,
    )


def build_index_page(
    selected: dict[str, list[tuple[str, list[dict]]]],
    today_str: str,
) -> str:
    """Build a simple index page listing all combo pages."""
    index_view = []
    for state in ["WA", "QLD", "NSW", "VIC"]:
        state_full = STATE_FULL_NAMES[state]
        state_slug = STATE_SLUGS[state]
        for species_slug, products in selected.get(state, []):
            index_view.append({
                "species_slug": species_slug,
                "state_slug": state_slug,
                "species_name": products[0]["species"]["common_name"],
                "state_full": state_full,
                "count": len(products),
            })

    total_pages = sum(len(v) for v in selected.values())

    head = render_head(
        "Buy Fruit Trees by Species and State | treestock.com.au",
        f"Find fruit trees available in your state. {total_pages} species+state guides, updated daily.",
        "https://treestock.com.au/buy-fruit-trees-by-species-state.html",
    )
    header = render_header()
    breadcrumb = render_breadcrumb([("Home", "/"), ("Fruit trees by species and state", "")])
    footer = render_footer()

    return render_template(
        "species_state_index.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        today_str=today_str, total_pages=total_pages, index_view=index_view,
    )


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 build_species_state_pages.py /path/to/nursery-stock /path/to/output/")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print("Loading species...", file=sys.stderr)
    species_list = load_species()
    species_lookup = build_species_lookup(species_list)

    print("Loading products...", file=sys.stderr)
    products = load_all_products(data_dir)

    print("Computing combos...", file=sys.stderr)
    combos = compute_combos(products, species_lookup)
    selected = select_combos(combos)

    total = sum(len(v) for v in selected.values())
    print(f"Building {total} combo pages...", file=sys.stderr)
    for state in ["WA", "QLD", "NSW", "VIC"]:
        state_combos = selected[state]
        state_slug = STATE_SLUGS[state]
        print(f"  {state}: {len(state_combos)} pages", file=sys.stderr)
        for species_slug, prods in state_combos:
            html = build_combo_page(state, species_slug, prods, today_str)
            filename = f"buy-{species_slug}-trees-{state_slug}.html"
            (output_dir / filename).write_text(html)

    # Build index page
    index_html = build_index_page(selected, today_str)
    (output_dir / "buy-fruit-trees-by-species-state.html").write_text(index_html)
    print(f"  Index page: buy-fruit-trees-by-species-state.html", file=sys.stderr)

    print(f"Done. {total + 1} pages written to {output_dir}", file=sys.stderr)

    # Print summary for sitemap integration
    pages = []
    for state in ["WA", "QLD", "NSW", "VIC"]:
        state_slug = STATE_SLUGS[state]
        for species_slug, _ in selected[state]:
            pages.append(f"buy-{species_slug}-trees-{state_slug}.html")
    pages.append("buy-fruit-trees-by-species-state.html")
    print(json.dumps(pages))


if __name__ == "__main__":
    main()
