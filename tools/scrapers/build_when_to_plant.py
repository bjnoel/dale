#!/usr/bin/env python3
"""
Build the "When to Plant Fruit Trees in Australia" planting-calendar page for
treestock.com.au.

Targets keywords: 'when to plant fruit trees australia', 'bare root season
australia', 'best time to plant citrus / mango / avocado', 'fruit tree planting
calendar', plus per-zone planting questions.

This re-homes an earlier static page (DEC-100, Mar 2026) that no builder
regenerated. It now:
  - renders the by-species calendar SERVER-SIDE (the old page rendered the table
    in client JS, so search engines saw an empty table),
  - uses the shared treestock_layout (versioned styles.css, sticky nav, footer),
  - covers five Australian growing zones (adds the arid / dry-inland zone),
  - cites authoritative Australian sources and lists them in a References block,
  - links each species to its /species/<slug>.html page, validated against
    fruit_species.json so links can never 404,
  - emits FAQPage JSON-LD,
  - drops the em dashes.

Usage:
    python3 build_when_to_plant.py /path/to/output/
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer, render_treesmith_promo

from stocklib.taxonomy import enabled_species


def load_valid_species_slugs() -> set:
    """Slugs that have a real /species/<slug>.html page. Used to validate the
    species links in the calendar so they can never point at a 404."""
    try:
        return {s["slug"] for s in enabled_species() if s.get("slug")}
    except (OSError, json.JSONDecodeError, KeyError):
        return set()


# ----- Content Data -----
# NOTE: planting months use 1-12 (Southern Hemisphere). best = ideal window,
# ok = acceptable window, bare_root = dormant bare-root window (deciduous only).

ZONES = [
    {
        "key": "tropical",
        "name": "Tropical",
        "regions": "Far North QLD, Cairns, Darwin and the Top End, Broome and the Kimberley.",
        "climate": "Hot wet summers, warm dry winters, effectively frost-free year-round.",
        "approach": "Plant at the start of the dry season (April to May) or the early wet (October to November). Many tropicals can go in year-round with watering.",
        "css": "zone-tropical",
    },
    {
        "key": "subtropical",
        "name": "Subtropical",
        "regions": "South-east QLD (Brisbane), the Gold and Sunshine Coasts, coastal NSW, the Perth coastal strip.",
        "climate": "Warm humid summers, mild winters, only occasional light frost inland.",
        "approach": "Spring (September to November) is the main window. Autumn works for hardy types in frost-free spots.",
        "css": "zone-subtropical",
    },
    {
        "key": "arid",
        "name": "Arid / dry inland",
        "regions": "Alice Springs, inland WA, SA and NSW, Mildura, Broken Hill.",
        "climate": "Hot dry summers, cold nights, low rainfall, frost inland in winter.",
        "approach": "Autumn (March to May) is usually best so roots establish over the mild winter before summer heat. Deciduous trees still go in as bare-root in winter. Protect frost-tender stock.",
        "css": "zone-arid",
    },
    {
        "key": "temperate",
        "name": "Temperate / Mediterranean",
        "regions": "Sydney, Melbourne, Adelaide, the Perth hills, coastal SA and VIC, most of southern WA.",
        "climate": "Warm to hot summers, cool winters with some frost.",
        "approach": "Spring for evergreens and subtropicals, winter bare-root for deciduous, and autumn for hardy evergreens like olive and feijoa.",
        "css": "zone-temperate",
    },
    {
        "key": "cool",
        "name": "Cool / cold",
        "regions": "Tasmania, the ACT, alpine VIC and NSW, Orange, Stanthorpe, the Adelaide Hills, southern WA ranges.",
        "climate": "Cold frosty winters, mild summers, plenty of winter chill.",
        "approach": "Ideal for high-chill deciduous fruit. Plant deciduous bare-root in winter. Plant frost-tender evergreens in spring only, with protection.",
        "css": "zone-cool",
    },
]

# Per-fruit-type planting guidance with inline citations. `sources` are indices
# into SOURCES (filled from verified research).
CATEGORY_GUIDANCE = [
    {
        "key": "deciduous",
        "title": "Deciduous fruit (bare-root in winter)",
        "icon": "&#127809;",  # fallen leaf
        "body": (
            "Apples, pears, plums, peaches, nectarines, apricots, cherries, figs, mulberries, grapes, "
            "persimmons, pomegranates and jujubes drop their leaves and go dormant in winter. That is when "
            "nurseries lift and sell them bare-root, with no soil around the roots. Bare-root stock is cheaper "
            "than potted trees and establishes quickly, because the roots start growing into your soil before "
            "the tree wakes up in spring. The bare-root season runs from about June to August, peaking in July. "
            "Order early, as the best varieties sell out fast."
        ),
        "key_fact": "Match the variety's chill-hour needs to your zone. High-chill cherries and many apples will not fruit in warm areas, but low-chill peach, apple and plum varieties are bred for the subtropics.",
    },
    {
        "key": "citrus",
        "title": "Citrus",
        "icon": "&#127819;",  # lemon
        "body": (
            "Lemons, limes, oranges, mandarins, grapefruit and the native finger lime are best planted in spring "
            "(September to November) once the soil has warmed. In frost-free coastal and subtropical areas you can "
            "also plant in autumn. Avoid putting young citrus into cold wet winter soil where frost is likely, as "
            "they are tender when small. Lemons (especially Meyer) and finger lime are the most cold-hardy."
        ),
        "key_fact": "Citrus wants warm soil and good drainage. Spring planting gives a full warm season to establish before the next winter.",
    },
    {
        "key": "subtropical",
        "title": "Subtropical evergreens",
        "icon": "&#129361;",  # avocado
        "body": (
            "Avocado, mango, custard apple, lychee, longan, macadamia, guava, white sapote and feijoa are evergreen "
            "and keep growing through the cool months, so they need warm soil to establish. Plant them in spring "
            "once frost risk has passed, not into cold winter soil. Avocados in particular need excellent drainage "
            "(plant on a mound if your soil is heavy) and shelter from frost for the first couple of winters. Some of "
            "this group, including feijoa, loquat, jaboticaba and white sapote, tolerate light frost once established."
        ),
        "key_fact": "Spring planting into warming soil, with frost protection for the first winter or two, is the safe default for this group.",
    },
    {
        "key": "tropical",
        "title": "Tropical fruit",
        "icon": "&#127820;",  # banana
        "body": (
            "Banana, papaya, jackfruit, rambutan, cacao, starfruit, sapodilla and black sapote need consistent warmth "
            "and no frost. In tropical Australia they can go in almost year-round, with the start of the dry season or "
            "the early wet the easiest times to establish. In subtropical or temperate gardens, plant in spring only, "
            "choose the warmest microclimate you have, and protect from any frost. Bananas and papaya grow fast and make "
            "useful short-term shade and shelter for slower trees."
        ),
        "key_fact": "Outside the tropics these are spring-only and frost is the main risk. A warm wall or canopy microclimate helps.",
    },
    {
        "key": "arid",
        "title": "Arid and dry-inland gardens",
        "icon": "&#9728;",  # sun
        "body": (
            "In hot dry inland districts the summer is the hardest season on a new tree, not the winter. Autumn planting "
            "(March to May) is usually best, giving roots a mild winter and spring to establish before the heat. Deciduous "
            "fruit still goes in as bare-root over winter. Watch for winter frost on tender evergreens, and plan deep "
            "watering and heavy mulch from day one. Heat and drought tolerant species (olive, pomegranate, fig, grape, "
            "jujube, loquat) suit these gardens best."
        ),
        "key_fact": "Plant in autumn so roots are established before the first hot summer. Mulch heavily and water deeply.",
    },
]

# Species planting data. zones: tropical | subtropical | temperate | cool | arid.
# Updated from the DEC-100 table after an adversarial research audit.
SPECIES = [
    {"name": "Mango", "slug": "mango", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Container grown, spring planting. Frost-tender. Most QLD/NSW nurseries do not ship to WA."},
    {"name": "Lychee", "slug": "lychee", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Spring planting. Needs a frost-free winter."},
    {"name": "Longan", "slug": "longan", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Spring planting. Similar needs to lychee."},
    {"name": "Rambutan", "slug": "rambutan", "zones": ["tropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Tropical only. Very sensitive to cold."},
    {"name": "Jackfruit", "slug": "jackfruit", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Fast growing. Protect from frost when young."},
    {"name": "Banana", "slug": "banana", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8, 1, 2, 3], "bareRoot": [], "notes": "Year-round in the tropics, spring in subtropical areas. Cold-sensitive."},
    {"name": "Papaya", "slug": "papaya", "zones": ["tropical", "subtropical"], "best": [9, 10, 11, 12], "ok": [8], "bareRoot": [], "notes": "Spring planting. Short-lived (3-5 years), replant regularly."},
    {"name": "Cacao", "slug": "cacao", "zones": ["tropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Strictly tropical. Needs humidity and no frost."},
    {"name": "Wax Jambu", "slug": "wax-jambu", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Spring planting. Frost-sensitive."},
    {"name": "Rollinia", "slug": "rollinia", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Spring planting. Frost-sensitive."},
    {"name": "Starfruit", "slug": "starfruit", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Container grown, spring planting."},
    {"name": "Sapodilla", "slug": "sapodilla", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Spring planting. Frost-sensitive."},
    {"name": "Avocado", "slug": "avocado", "zones": ["subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4, 12], "bareRoot": [], "notes": "Spring preferred. Drainage essential, frost-tender when young."},
    {"name": "Passionfruit", "slug": "passionfruit", "zones": ["subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4, 12], "bareRoot": [], "notes": "Spring planting. Short-lived vine (5-7 years)."},
    {"name": "Guava", "slug": "guava", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Spring planting. Hardy once established."},
    {"name": "Custard Apple", "slug": "custard-apple", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Spring planting. Frost-sensitive."},
    {"name": "Dragon Fruit", "slug": "dragon-fruit", "zones": ["tropical", "subtropical", "temperate"], "best": [9, 10, 11, 12], "ok": [8, 1], "bareRoot": [], "notes": "Spring to summer planting. A heat-loving cactus, but frost-tender. In temperate zones plant only in a warm, frost-free microclimate."},
    {"name": "Black Sapote", "slug": "black-sapote", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Spring planting. Light frost tolerance once established."},
    {"name": "White Sapote", "slug": "white-sapote", "zones": ["subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4, 12], "bareRoot": [], "notes": "Spring planting. More cold-tolerant than black sapote."},
    {"name": "Tamarillo", "slug": "tamarillo", "zones": ["subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4], "bareRoot": [], "notes": "Spring planting. Short-lived (4-5 years), frost-sensitive."},
    {"name": "Grumichama", "slug": "grumichama", "zones": ["subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4], "bareRoot": [], "notes": "Spring planting. Ornamental and fruiting."},
    {"name": "Pomelo", "slug": "pomelo", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Spring planting. The largest citrus."},
    {"name": "Jaboticaba", "slug": "jaboticaba", "zones": ["tropical", "subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4], "bareRoot": [], "notes": "Spring planting. Slow growing, tolerates mild frost."},
    {"name": "Miracle Fruit", "slug": "miracle-fruit", "zones": ["tropical", "subtropical"], "best": [9, 10, 11], "ok": [12, 8], "bareRoot": [], "notes": "Tropical and subtropical only. Likes acidic soil."},
    {"name": "Lemon", "slug": "lemon", "zones": ["subtropical", "temperate", "cool"], "best": [9, 10, 11], "ok": [3, 4, 5, 12, 8], "bareRoot": [], "notes": "Spring and autumn planting. The most frost-tolerant citrus."},
    {"name": "Lime", "slug": "lime", "zones": ["subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4, 12], "bareRoot": [], "notes": "Spring preferred. Protect from frost in the first winter."},
    {"name": "Orange", "slug": "orange", "zones": ["subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4, 12], "bareRoot": [], "notes": "Spring and autumn planting. Many varieties."},
    {"name": "Mandarin", "slug": "mandarin", "zones": ["subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4, 12], "bareRoot": [], "notes": "Spring and autumn planting. Easy to grow."},
    {"name": "Grapefruit", "slug": "grapefruit", "zones": ["subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4, 12], "bareRoot": [], "notes": "Spring planting. Needs heat to sweeten the fruit."},
    {"name": "Finger Lime", "slug": "finger-lime", "zones": ["subtropical", "temperate", "cool"], "best": [9, 10, 11], "ok": [3, 4, 5, 12], "bareRoot": [], "notes": "Australian native. More cold-tolerant than most citrus."},
    {"name": "Fig", "slug": "fig", "zones": ["temperate", "subtropical", "cool", "arid"], "best": [9, 10], "ok": [3, 4], "bareRoot": [6, 7, 8], "notes": "Deciduous. Bare-root in June to August, container in spring."},
    {"name": "Pomegranate", "slug": "pomegranate", "zones": ["temperate", "subtropical", "arid"], "best": [9, 10, 11], "ok": [3, 4], "bareRoot": [6, 7, 8], "notes": "Deciduous. Drought-tolerant once established. Suits hot dry areas."},
    {"name": "Olive", "slug": "olive", "zones": ["temperate", "subtropical", "cool", "arid"], "best": [3, 4, 5, 9, 10], "ok": [11, 2], "bareRoot": [], "notes": "Autumn and spring planting. Extremely drought-tolerant."},
    {"name": "Loquat", "slug": "loquat", "zones": ["temperate", "subtropical", "cool", "arid"], "best": [9, 10, 11], "ok": [3, 4], "bareRoot": [], "notes": "Spring and autumn planting. Hardy and drought-tolerant. One of the first fruits of the year."},
    {"name": "Mulberry", "slug": "mulberry", "zones": ["temperate", "subtropical", "cool"], "best": [9, 10], "ok": [3, 4], "bareRoot": [6, 7, 8], "notes": "Deciduous. Bare-root widely available in winter."},
    {"name": "Jujube", "slug": "jujube", "zones": ["temperate", "subtropical", "arid"], "best": [9, 10, 11], "ok": [3, 4], "bareRoot": [6, 7, 8], "notes": "Deciduous. Extremely drought-tolerant. Bare-root in winter."},
    {"name": "Macadamia", "slug": "macadamia", "zones": ["subtropical", "temperate"], "best": [9, 10, 11], "ok": [3, 4, 12], "bareRoot": [], "notes": "Spring planting. Slow growing, grafted trees fruit in 5-7 years."},
    {"name": "Feijoa", "slug": "feijoa", "zones": ["temperate", "subtropical", "cool"], "best": [3, 4, 5, 9, 10], "ok": [11], "bareRoot": [], "notes": "Very adaptable. Autumn and spring planting, hardy once established."},
    {"name": "Lilly Pilly", "slug": "lilly-pilly", "zones": ["tropical", "subtropical", "temperate", "cool"], "best": [9, 10, 11], "ok": [3, 4, 5, 12, 8], "bareRoot": [], "notes": "Australian native. Highly adaptable, plant most of the year."},
    {"name": "Pecan", "slug": "pecan", "zones": ["temperate", "subtropical"], "best": [9, 10, 11], "ok": [3, 4], "bareRoot": [6, 7, 8], "notes": "Large deciduous tree. Bare-root in winter, long-lived."},
    {"name": "Apple", "slug": "apple", "zones": ["temperate", "cool", "subtropical"], "best": [9, 10], "ok": [3, 4, 11], "bareRoot": [6, 7, 8], "notes": "Needs winter chill. Bare-root is the cheapest option. Low-chill varieties (Anna, Dorsett Golden) suit warm subtropical areas."},
    {"name": "Pear", "slug": "pear", "zones": ["temperate", "cool"], "best": [9, 10], "ok": [3, 4, 11], "bareRoot": [6, 7, 8], "notes": "Needs winter chill. Asian pears need less chill than European."},
    {"name": "Plum", "slug": "plum", "zones": ["temperate", "cool"], "best": [9, 10], "ok": [3, 4, 11], "bareRoot": [6, 7, 8], "notes": "Deciduous. Check chill hours for your area."},
    {"name": "Peach", "slug": "peach", "zones": ["temperate", "cool", "subtropical"], "best": [9, 10], "ok": [3, 4, 11], "bareRoot": [6, 7, 8], "notes": "Low-chill varieties available for warm areas (Brisbane, Perth)."},
    {"name": "Nectarine", "slug": "nectarine", "zones": ["temperate", "cool", "subtropical"], "best": [9, 10], "ok": [3, 4, 11], "bareRoot": [6, 7, 8], "notes": "A smooth-skinned peach. Low-chill varieties exist for warm areas."},
    {"name": "Apricot", "slug": "apricot", "zones": ["temperate", "cool", "arid"], "best": [9, 10], "ok": [3, 4, 11], "bareRoot": [6, 7, 8], "notes": "Needs cold winters. Thrives in dry inland districts (Riverland, Mildura). Not suited to subtropical or tropical climates."},
    {"name": "Cherry", "slug": "cherry", "zones": ["cool", "temperate"], "best": [9, 10], "ok": [3, 4], "bareRoot": [6, 7, 8], "notes": "High chill requirement. Best in VIC/TAS/NSW highlands and cold WA zones."},
    {"name": "Blueberry", "slug": "blueberry", "zones": ["temperate", "cool", "subtropical"], "best": [3, 4, 5], "ok": [9, 10, 11], "bareRoot": [6, 7, 8], "notes": "Likes acidic soil (pH 4.5-5.5). Cool-zone northern highbush types sell bare-root in winter; warm-zone southern highbush and rabbiteye types are evergreen and sold potted."},
    {"name": "Raspberry", "slug": "raspberry", "zones": ["cool", "temperate"], "best": [3, 4, 5], "ok": [6, 7], "bareRoot": [6, 7], "notes": "Autumn or winter planting. Needs cool winters to fruit well."},
    {"name": "Grape", "slug": "grape", "zones": ["temperate", "subtropical", "cool", "arid"], "best": [9, 10], "ok": [3, 4, 11], "bareRoot": [6, 7, 8], "notes": "Deciduous. Bare-root widely available in July, very easy to establish."},
]

FAQS = [
    (
        "What is the best month to plant fruit trees in Australia?",
        "It depends on your climate zone and the type of tree. For deciduous fruit (apples, pears, plums, peaches) the bare-root season from June to August is ideal and the cheapest time to buy. For citrus, subtropical and tropical fruit, spring (September to November) is best, once the soil has warmed and frost has passed. In hot dry inland areas, autumn (March to May) often works better so roots establish before summer.",
    ),
    (
        "What is the bare-root season in Australia?",
        "Bare-root season runs roughly from June to early August, peaking in July. Deciduous trees (apples, pears, cherries, plums, peaches, grapes and others) go fully dormant in winter and can be sold without soil around the roots. Bare-root trees are usually cheaper than potted stock and establish quickly. Order early, as popular varieties sell out within days of release.",
    ),
    (
        "Can I plant fruit trees in summer?",
        "It is possible but not ideal for most species. Summer heat stresses a newly planted tree before it has built a strong root system. If you must plant in summer, water deeply every two or three days, mulch heavily, and avoid heatwaves. Container-grown tropicals (bananas, papayas) cope better with warm-season planting than deciduous or subtropical trees.",
    ),
    (
        "When is the best time to plant citrus trees?",
        "Spring (September to November) is best in most of Australia, once the soil has warmed. In frost-free coastal and subtropical areas you can also plant in autumn. Avoid winter planting where frost is likely, as young citrus is frost-tender. Lemons and finger lime are the most cold-hardy citrus.",
    ),
    (
        "When should I plant avocados and mangoes?",
        "Both are best planted in spring (September to November) once frost risk has passed and the soil is warming. Avocados need excellent drainage, so plant on a mound if your soil holds water, and shelter young trees from frost for the first couple of winters. In the tropics, mangoes can go in at the start of the wet season.",
    ),
    (
        "What are chill hours and why do they matter?",
        "Chill hours are the number of winter hours below about 7 degrees Celsius. Deciduous fruit needs a certain amount of winter chill to flower and fruit properly. High-chill types (most cherries, many apples and apricots) will not fruit well in warm areas, while low-chill varieties are bred for the subtropics. Match the variety to your zone before you buy.",
    ),
    (
        "Where can I buy fruit trees online in Australia?",
        "treestock.com.au tracks stock and prices across Australian nurseries every day. Search by species, filter by your state, and subscribe to a free daily digest that flags back-in-stock items, price drops and new arrivals so you do not miss the bare-root window.",
    ),
]

# Authoritative sources, all verified to resolve (HTTP 200/202, June 2026) from a
# fan-out research pass that adversarially checked each claim against AU authorities.
# Each entry feeds the References section.
SOURCES = [
    {"name": "ABC Organic Gardener: understanding Australia's climate zones", "url": "https://www.organicgardener.com.au/understanding-climate-zones/"},
    {"name": "ABC Gardening Australia: bare-rooted plants", "url": "https://www.gardeningaustraliamag.com.au/bare-rooted-plants/"},
    {"name": "Sustainable Gardening Australia: bare-root fruit trees", "url": "https://www.sgaonline.org.au/bare-root-fruit-trees/"},
    {"name": "Sustainable Gardening Australia: cool-climate citrus", "url": "https://www.sgaonline.org.au/cool-climate-citrus/"},
    {"name": "NT Government: stone fruit for Central Australia (low-chill)", "url": "https://nt.gov.au/industry/agriculture/food-crops-plants-and-quarantine/fruit-crops/stone-fruit"},
    {"name": "Bureau of Meteorology: what is frost", "url": "https://www.bom.gov.au/climate/map/frost/what-is-frost.shtml"},
    {"name": "DPIRD Western Australia: waterwise gardening (mulch and irrigation)", "url": "https://library.dpird.wa.gov.au/cgi/viewcontent.cgi?article=1038&context=bulletins"},
    {"name": "Bayside City Council (VIC): fruit tree planting tips", "url": "https://www.bayside.vic.gov.au/fruit-tree-planting-tips"},
    {"name": "Daleys Fruit Tree Nursery: chill factor guide", "url": "https://www.daleysfruit.com.au/fruit%20pages/chillfactor.htm"},
    {"name": "Searles Gardening: inland (arid) climate guide", "url": "https://www.searlesgardening.com.au/climates/inland"},
]

# Short inline citations mapped to the verified SOURCES above.
CATEGORY_CITES = {
    "deciduous": ("Daleys chill guide", "https://www.daleysfruit.com.au/fruit%20pages/chillfactor.htm"),
    "citrus": ("SGA cool-climate citrus", "https://www.sgaonline.org.au/cool-climate-citrus/"),
    "subtropical": ("Bayside Council", "https://www.bayside.vic.gov.au/fruit-tree-planting-tips"),
    "tropical": ("ABC climate zones", "https://www.organicgardener.com.au/understanding-climate-zones/"),
    "arid": ("Searles inland guide", "https://www.searlesgardening.com.au/climates/inland"),
}


def inline_cite(label: str, url: str) -> str:
    """A small bracketed citation link to an authoritative source."""
    safe = url.replace("&", "&amp;")
    return (f' <a href="{safe}" rel="noopener nofollow" target="_blank" '
            f'class="text-xs text-green-700 hover:underline whitespace-nowrap">[{label}]</a>')

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

ZONE_LABELS = {
    "tropical": "Tropical",
    "subtropical": "Subtropical",
    "arid": "Arid",
    "temperate": "Temperate",
    "cool": "Cool",
}

# bespoke CSS for the calendar (month bar, zone cards, badges, filter buttons).
# Lives in the page <style> via extra_style, so it is not subject to the
# Tailwind purge that strips unused utility classes.
EXTRA_STYLE = """\
  .zone-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; }
  .zone-card { border-radius: 10px; padding: 14px; }
  .zone-card .zone-name { font-weight: 700; font-size: 0.95rem; margin-bottom: 4px; }
  .zone-card .zone-detail { font-size: 0.8rem; opacity: 0.9; }
  .zone-tropical { background: #fef3c7; color: #78350f; }
  .zone-subtropical { background: #fce7f3; color: #831843; }
  .zone-arid { background: #ffedd5; color: #7c2d12; }
  .zone-temperate { background: #dbeafe; color: #1e3a8a; }
  .zone-cool { background: #e0f2fe; color: #0c4a6e; }

  .filter-btn { padding: 5px 13px; border-radius: 20px; border: 1px solid #d1d5db; background: white; font-size: 0.82rem; cursor: pointer; color: #374151; font-weight: 500; }
  .filter-btn:hover { border-color: #059669; color: #059669; }
  .filter-btn.active { background: #059669; color: white; border-color: #059669; }

  .plant-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  .plant-table th { background: #f3f4f6; color: #374151; font-weight: 600; padding: 9px 11px; text-align: left; border-bottom: 2px solid #e5e7eb; white-space: nowrap; }
  .plant-table td { padding: 9px 11px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }
  .plant-table tr.hidden { display: none; }
  .species-link { color: #059669; font-weight: 600; text-decoration: none; white-space: nowrap; }
  .species-link:hover { text-decoration: underline; }
  .no-link { font-weight: 600; color: #111827; white-space: nowrap; }

  .zone-badge { display: inline-block; padding: 2px 7px; border-radius: 10px; font-size: 0.7rem; font-weight: 600; white-space: nowrap; margin: 1px; }
  .badge-tropical { background: #fef3c7; color: #78350f; }
  .badge-subtropical { background: #fce7f3; color: #831843; }
  .badge-arid { background: #ffedd5; color: #7c2d12; }
  .badge-temperate { background: #dbeafe; color: #1e3a8a; }
  .badge-cool { background: #e0f2fe; color: #0c4a6e; }

  .month-bar { display: flex; gap: 2px; min-width: 150px; }
  .month-bar span { flex: 1; height: 18px; border-radius: 2px; background: #e5e7eb; font-size: 0.55rem; text-align: center; line-height: 18px; color: #9ca3af; min-width: 11px; }
  .month-bar span.best { background: #16a34a; color: white; font-weight: 700; }
  .month-bar span.ok { background: #86efac; color: #065f46; }
  .month-bar span.bare-root { background: #f59e0b; color: white; font-weight: 700; }
  .note-text { font-size: 0.8rem; color: #6b7280; }
  .months-text { font-size: 0.8rem; color: #374151; }
  @media (max-width: 700px) {
    .plant-table th:nth-child(4), .plant-table td:nth-child(4) { display: none; }
  }"""

# Tiny progressive-enhancement filter. Rows are already in the HTML; this only
# toggles visibility, so the page works fully without JavaScript.
FILTER_SCRIPT = """\
<script>
(function() {
  var buttons = document.querySelectorAll('.filter-btn');
  function apply(zone) {
    document.querySelectorAll('#plantTable tbody tr').forEach(function(row) {
      var zones = (row.getAttribute('data-zones') || '').split(' ');
      row.classList.toggle('hidden', zone !== 'all' && zones.indexOf(zone) === -1);
    });
  }
  buttons.forEach(function(b) {
    b.addEventListener('click', function() {
      buttons.forEach(function(x) { x.classList.remove('active'); });
      b.classList.add('active');
      apply(b.getAttribute('data-filter'));
    });
  });
})();
</script>"""


def build_zone_cards() -> str:
    cards = "".join(
        f"""    <div class="zone-card {z['css']}">
      <div class="zone-name">{z['name']}</div>
      <div class="zone-detail"><strong>Where:</strong> {z['regions']}<br><strong>Climate:</strong> {z['climate']}<br><strong>Planting:</strong> {z['approach']}</div>
    </div>"""
        for z in ZONES
    )
    return f"""
<section class="mb-10" id="zones">
  <h2 class="text-xl font-bold text-green-900 mb-3">Australian Climate Zones</h2>
  <p class="text-gray-600 text-sm mb-4">Australia spans several growing climates. Your zone decides both the best planting season and which varieties will thrive. Find yours below, then use the calendar to time your planting.{inline_cite("ABC climate zones", "https://www.organicgardener.com.au/understanding-climate-zones/")}</p>
  <div class="zone-grid">
{cards}
  </div>
</section>
"""


def build_category_guidance() -> str:
    parts = []
    for c in CATEGORY_GUIDANCE:
        cite = ""
        if c["key"] in CATEGORY_CITES:
            cite = inline_cite(*CATEGORY_CITES[c["key"]])
        parts.append(f"""
  <div class="mb-6" id="type-{c['key']}">
    <h3 class="font-semibold text-green-900 mb-1">{c['icon']} {c['title']}</h3>
    <p class="text-sm text-gray-600 mb-1">{c['body']}</p>
    <p class="text-sm text-gray-700"><strong>Key point:</strong> {c['key_fact']}{cite}</p>
  </div>""")
    blocks = "".join(parts)
    return f"""
<section class="mb-10" id="by-type">
  <h2 class="text-xl font-bold text-green-900 mb-3">Planting by Type of Tree</h2>
  {blocks}
</section>
"""


def build_month_bar(best, ok, bare_root) -> str:
    best = best or []
    ok = ok or []
    bare_root = bare_root or []
    spans = []
    for m in range(1, 13):
        ab = MONTHS[m - 1][0]
        if m in bare_root:
            spans.append(f'<span class="bare-root" title="{MONTHS[m-1]}: bare-root season">{ab}</span>')
        elif m in best:
            spans.append(f'<span class="best" title="{MONTHS[m-1]}: best planting">{ab}</span>')
        elif m in ok:
            spans.append(f'<span class="ok" title="{MONTHS[m-1]}: acceptable">{ab}</span>')
        else:
            spans.append(f'<span title="{MONTHS[m-1]}">{ab}</span>')
    return '<div class="month-bar">' + "".join(spans) + "</div>"


def build_months_text(best, ok, bare_root) -> str:
    best = best or []
    bare_root = bare_root or []
    parts = []
    if best:
        parts.append(", ".join(MONTHS[m - 1] for m in best))
    if bare_root:
        parts.append("Bare-root: " + ", ".join(MONTHS[m - 1] for m in bare_root))
    return " | ".join(parts)


def build_calendar_table(valid_slugs: set) -> str:
    rows = []
    for s in SPECIES:
        zones_html = " ".join(
            f'<span class="zone-badge badge-{z}">{ZONE_LABELS.get(z, z.title())}</span>'
            for z in s["zones"]
        )
        if s.get("slug") and s["slug"] in valid_slugs:
            name_cell = f'<a href="/species/{s["slug"]}.html" class="species-link">{s["name"]}</a>'
        else:
            name_cell = f'<span class="no-link">{s["name"]}</span>'
        rows.append(
            f"""        <tr data-zones="{' '.join(s['zones'])}">
          <td>{name_cell}</td>
          <td>{zones_html}</td>
          <td>{build_month_bar(s['best'], s['ok'], s['bareRoot'])}</td>
          <td class="months-text">{build_months_text(s['best'], s['ok'], s['bareRoot'])}</td>
          <td class="note-text">{s['notes']}</td>
        </tr>"""
        )
    rows_html = "\n".join(rows)

    filter_buttons = '<button class="filter-btn active" data-filter="all">All zones</button>\n      ' + "\n      ".join(
        f'<button class="filter-btn" data-filter="{z["key"]}">{z["name"]}</button>'
        for z in ZONES
    )

    return f"""
<section class="mb-10" id="calendar">
  <h2 class="text-xl font-bold text-green-900 mb-3">Planting Calendar by Species</h2>
  <div class="flex gap-2 flex-wrap items-center mb-4">
    <span class="text-sm text-gray-500 font-medium mr-1">Filter by zone:</span>
    {filter_buttons}
  </div>
  <div style="overflow-x:auto;">
    <table class="plant-table" id="plantTable">
      <thead>
        <tr>
          <th>Species</th>
          <th>Climate zones</th>
          <th>Planting window</th>
          <th>Months</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>
{rows_html}
      </tbody>
    </table>
  </div>
  <p class="text-xs text-gray-500 mt-3">
    Green is the best planting window, light green is acceptable, amber is the bare-root season (deciduous trees only).
    Container-grown trees can often be planted outside these windows with care. Timing assumes the main southern growing
    pattern, so adjust for your own zone using the guide above (autumn-weight in arid areas, spring only for tender trees in cool zones).
  </p>
</section>
"""


def build_faq_section() -> str:
    items = "".join(
        f"""  <div class="mb-5">
    <h3 class="font-semibold text-gray-800 mb-1">{q}</h3>
    <p class="text-sm text-gray-600">{a}</p>
  </div>"""
        for q, a in FAQS
    )
    return f"""
<section class="mb-10" id="faq">
  <h2 class="text-xl font-bold text-green-900 mb-4">Frequently Asked Questions</h2>
  {items}
</section>
"""


def build_faq_jsonld() -> str:
    entities = [
        {
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a},
        }
        for q, a in FAQS
    ]
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": entities,
    }
    return '<script type="application/ld+json">\n' + json.dumps(data, indent=2) + "\n</script>"


def build_references() -> str:
    if not SOURCES:
        return ""
    items = "".join(
        f'<li><a href="{s["url"].replace("&", "&amp;")}" rel="noopener nofollow" target="_blank" class="text-green-700 hover:underline">{s["name"]}</a></li>'
        for s in SOURCES
    )
    return f"""
<section class="mb-10" id="references">
  <h2 class="text-xl font-bold text-green-900 mb-3">Sources</h2>
  <p class="text-gray-600 text-sm mb-3">Planting times and chill-hour guidance on this page draw on Australian state agriculture departments, ABC Gardening Australia, and established Australian nurseries.</p>
  <ul class="text-sm space-y-1 list-disc pl-5">
    {items}
  </ul>
</section>
"""


def build_cta() -> str:
    """Alerts CTA reusing the site-wide double-opt-in subscribe contract."""
    return """
<section class="bg-green-50 border border-green-200 rounded-lg p-6 mb-8" id="alerts">
  <h2 class="text-lg font-semibold text-green-900 mb-1">Know the moment bare-root trees drop</h2>
  <p class="text-sm text-green-900 mb-4">Each winter the best bare-root varieties sell out within days. Subscribe to the free treestock daily digest: back-in-stock items, price drops and new arrivals across every nursery we track. Filter by your state.</p>
  <form id="subscribeForm" class="flex flex-col sm:flex-row gap-2 flex-wrap">
    <input type="email" id="subEmail" placeholder="your@email.com" required
      class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 flex-1 max-w-xs">
    <select id="subState" class="px-2 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
      <option value="ALL">All states</option>
      <option value="NSW">NSW</option><option value="VIC">VIC</option>
      <option value="QLD">QLD</option><option value="WA">WA</option>
      <option value="SA">SA</option><option value="TAS">TAS</option>
      <option value="NT">NT</option><option value="ACT">ACT</option>
    </select>
    <button type="submit"
      class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium whitespace-nowrap">
      Subscribe free
    </button>
  </form>
  <div id="subMessage" class="mt-2 text-sm hidden"></div>
</section>
"""


SUBSCRIBE_SCRIPT = r"""
<script>
(function() {
  var subForm = document.getElementById('subscribeForm');
  if (!subForm) return;
  var msg = document.getElementById('subMessage');
  subForm.addEventListener('submit', function(e) {
    e.preventDefault();
    var email = document.getElementById('subEmail').value.trim();
    var stateEl = document.getElementById('subState');
    var state = stateEl ? stateEl.value : 'ALL';
    fetch('/api/subscribe', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email: email, state: state, action: 'subscribe'})
    })
    .then(function(r) { return r.json().then(function(d) { return {status: r.status, data: d}; }); })
    .then(function(res) {
      if (res.status === 202) {
        msg.textContent = 'Check your email. We sent you a confirmation link.';
      } else if (res.data && res.data.message === 'Already subscribed') {
        msg.textContent = 'You are already subscribed.';
      } else {
        msg.textContent = 'Subscribed. You will get the daily digest.';
      }
      msg.className = 'mt-2 text-sm text-green-700';
      msg.style.display = 'block';
      subForm.style.display = 'none';
    })
    .catch(function() {
      msg.textContent = 'Something went wrong. Please try again.';
      msg.className = 'mt-2 text-sm text-red-600';
      msg.style.display = 'block';
    });
  });
})();
</script>"""


def build_related_guides() -> str:
    return """
<section class="mb-10" id="related">
  <h2 class="text-xl font-bold text-green-900 mb-3">Related Guides</h2>
  <ul class="text-sm space-y-1 list-disc pl-5">
    <li><a href="/guide.html" class="text-green-700 hover:underline">Where to buy rare fruit trees in Australia</a> (nursery directory and shipping guide)</li>
    <li><a href="/companion-planting-guide.html" class="text-green-700 hover:underline">Companion planting guide for fruit trees</a> (what to grow alongside, pollinator partners)</li>
    <li><a href="/species/" class="text-green-700 hover:underline">Browse all tracked species</a> (in-stock counts, price history, restock alerts)</li>
  </ul>
</section>
"""


def build_page() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    valid_slugs = load_valid_species_slugs()

    head = render_head(
        title="When to Plant Fruit Trees in Australia (Seasonal Planting Calendar) - treestock.com.au",
        description="When to plant fruit trees in Australia by climate zone. Bare-root season, citrus, avocado and mango timing, chill hours, and a planting calendar for 50 species. Australian sources.",
        canonical_url="https://treestock.com.au/when-to-plant.html",
        extra_head=build_faq_jsonld(),
        extra_style=EXTRA_STYLE,
        og_title="When to Plant Fruit Trees in Australia (Planting Calendar)",
        og_description="Planting calendar for 50 fruit tree species across five Australian climate zones. Bare-root season, spring planting times, chill hours, and frost guidance.",
        og_image="https://treestock.com.au/og-image.png",
        og_type="article",
    )
    header = render_header(active_path="/when-to-plant.html")
    breadcrumb = render_breadcrumb([("Home", "/"), ("When to Plant", "")])
    footer = render_footer()

    return render_template(
        "when_to_plant_page.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        today=today,
        bareroot_cite=inline_cite("ABC Gardening Australia", "https://www.gardeningaustraliamag.com.au/bare-rooted-plants/"),
        zone_cards=build_zone_cards(),
        category_guidance=build_category_guidance(),
        calendar_table=build_calendar_table(valid_slugs),
        cta=build_cta(),
        faq_section=build_faq_section(),
        references=build_references(),
        related_guides=build_related_guides(),
        treesmith_promo=render_treesmith_promo("species"),
        filter_script=FILTER_SCRIPT,
        subscribe_script=SUBSCRIBE_SCRIPT,
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: build_when_to_plant.py /path/to/output/")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)

    html = build_page()
    out_file = output_dir / "when-to-plant.html"
    out_file.write_text(html)
    print(f"Written: {out_file} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
