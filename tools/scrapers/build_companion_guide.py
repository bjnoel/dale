#!/usr/bin/env python3
"""
Build companion planting guide page for treestock.com.au.

Targets keywords: 'companion plants for citrus', 'companion planting mango',
'fruit tree pollinator requirements', 'what to plant with avocado', etc.

Every companion/avoidance claim carries an evidence grade (see EVIDENCE_GRADES)
so the page is honest about what is research-backed versus traditional folklore.
Content is Australia-specific (pests, climate zones, cultivars) and cited.

Usage:
    python3 build_companion_guide.py /path/to/output/
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from treestock_layout import render_head, render_header, render_breadcrumb, render_footer

SPECIES_FILE = Path(__file__).parent / "fruit_species.json"


# ----- Evidence grading -----

# Closed vocabulary. A test asserts every claim uses one of these.
EVIDENCE_GRADES = {
    "research-backed",       # peer-reviewed or university-extension support
    "established-practice",  # broad horticultural consensus, low controversy
    "traditional",           # folklore / anecdotal, plausible but little hard evidence
    "context-dependent",     # true only for certain varieties, climates or conditions
}

# label + Tailwind classes per grade (single styling source of truth).
GRADE_BADGE = {
    "research-backed": ("Research-backed", "bg-green-100 text-green-800 border-green-300"),
    "established-practice": ("Established practice", "bg-emerald-50 text-emerald-700 border-emerald-200"),
    "traditional": ("Traditional, limited evidence", "bg-amber-50 text-amber-800 border-amber-200"),
    "context-dependent": ("Depends on conditions", "bg-sky-50 text-sky-700 border-sky-200"),
}


def grade_badge(grade: str) -> str:
    label, cls = GRADE_BADGE[grade]
    return (
        f'<span class="inline-block text-xs px-1.5 py-0.5 rounded border {cls} '
        f'ml-1 align-middle whitespace-nowrap">{label}</span>'
    )


# ----- Content Data -----
# good:  (name, description, evidence_grade)
# avoid: (name, evidence_grade)

SPECIES_COMPANIONS = [
    {
        "name": "Citrus (Lemon, Orange, Mandarin, Lime)",
        "slug": "citrus",
        "species_slugs": ["lemon", "orange", "mandarin", "lime", "grapefruit", "pomelo", "finger-lime"],
        "icon": "🍋",
        "intro": "Citrus suits warm temperate and Mediterranean gardens across much of Australia. The most useful companions build soil and bring in bees and predatory insects, rather than directly repelling pests.",
        "good": [
            ("Comfrey", "Deep roots draw up nutrients and the cut leaves make a potassium-rich mulch. Plant about a metre out from the trunk so it does not compete with feeder roots.", "established-practice"),
            ("Clover or other legume groundcover", "A living, nitrogen-fixing groundcover feeds the tree and keeps the root zone cool, instead of bare soil or lawn.", "established-practice"),
            ("Lavender, alyssum and other flowering herbs", "Flowering diversity nearby brings in bees, hoverflies and lacewings whose larvae eat aphids.", "established-practice"),
            ("Nasturtium", "A sprawling groundcover often used as an aphid trap crop. Pull it back before it swamps a young tree.", "traditional"),
            ("Borage", "A reliable bee magnet when in flower. The old claim that it improves citrus flavour has no evidence.", "traditional"),
        ],
        "avoid": [
            ("Fennel (often called allelopathic)", "traditional"),
            ("Lawn or grass right under the canopy (competes for water and nitrogen)", "established-practice"),
            ("Another large tree crowded into the root zone", "established-practice"),
        ],
        "pollinator": "Citrus is self-fertile, so a single tree will set fruit. Extra varieties nearby can lift yield a little, and mandarins and tangelos respond most. Most home-garden citrus needs no pollinator partner.",
        "notes": "On the east coast, citrus gall wasp is the major pest. Prune out galls before the wasps emerge in spring; no companion plant controls it. Citrus likes free-draining, slightly acidic soil.",
        "sources": [
            ("Sustainable Gardening Australia, companion planting", "https://www.sgaonline.org.au/companion-planting/"),
            ("Yates, companion planting guide", "https://www.yates.com.au/garden-hub/companion-planting-guide/"),
        ],
    },
    {
        "name": "Mango",
        "slug": "mango",
        "species_slugs": ["mango"],
        "icon": "🥭",
        "intro": "Mango is a tropical and subtropical tree (coastal Queensland, the Top End, northern NSW and warm pockets of WA). Companions work best at the drip line, not under the dense canopy.",
        "good": [
            ("Marigold (Tagetes)", "Grown as a dense block or short rotation, French and African marigolds can suppress root-knot nematodes in the soil. A few scattered plants do little.", "research-backed"),
            ("Legume groundcover (pinto peanut, clover)", "Fixes nitrogen and protects bare tropical soil from heavy rain and heat.", "established-practice"),
            ("Lemongrass or vetiver", "Clumping grasses hold soil on slopes and edge a planting without competing heavily once the mango is established.", "established-practice"),
            ("Sweet potato", "A fast edible groundcover that suppresses weeds around young trees and is easy to pull back later.", "traditional"),
            ("Papaya (short term)", "A quick nurse plant for shelter and humidity while a young mango establishes. Remove it as the mango fills out.", "traditional"),
        ],
        "avoid": [
            ("Lawn grass under the canopy (competes for water and nitrogen)", "established-practice"),
            ("Large trees within about 8m (canopy and root competition)", "established-practice"),
        ],
        "pollinator": "Mango flowers are insect-pollinated. Most cultivars set some fruit alone, but yields improve with a second variety nearby. Kensington Pride (Bowen) is the most reliable single tree; Honey Gold and R2E2 crop better with another variety around.",
        "notes": "Mangoes grow large (6 to 10m). Bagging fruit or baiting protects against Queensland fruit fly, which no companion plant deters.",
        "sources": [
            ("Sustainable Gardening Australia, companion planting", "https://www.sgaonline.org.au/companion-planting/"),
            ("Very Edible Gardens, companion planting for orchards", "https://www.veryediblegardens.com.au/iveg/companion-planting-orchards/"),
        ],
    },
    {
        "name": "Avocado",
        "slug": "avocado",
        "species_slugs": ["avocado"],
        "icon": "🥑",
        "intro": "Avocados need free-draining soil and are very prone to root rot. The best companions keep the soil mulched, living and well aerated.",
        "good": [
            ("Thick organic mulch with comfrey at the drip line", "Comfrey leaves add a nutrient-rich mulch, and deep coarse mulch helps suppress the Phytophthora root rot that kills avocados.", "established-practice"),
            ("Legume groundcover", "A low nitrogen-fixing cover keeps soil alive and cool without crowding the shallow feeder roots.", "established-practice"),
            ("Flowering herbs nearby (not under the canopy)", "Bring in pollinators and beneficial insects during flowering.", "established-practice"),
            ("Passionfruit on a separate fence", "Uses vertical space for extra fruit without competing at the avocado's root zone.", "traditional"),
            ("Banana as a short-term nurse", "Gives wind shelter and humidity to a young tree in warm areas. Keep it clear of the trunk.", "traditional"),
        ],
        "avoid": [
            ("Anything that needs digging or heavy watering at the root zone (invites root rot)", "established-practice"),
            ("Grass or lawn under the canopy", "established-practice"),
            ("Black walnut (juglone)", "research-backed"),
        ],
        "pollinator": "Avocado flowers are type A or type B, opening female and male at different times of day. A single tree usually sets some fruit, but planting one type A (such as Hass or Reed) with one type B (such as Fuerte, Shepard or Bacon) lifts set noticeably. Wurtz (Little Cado) is a popular self-sufficient backyard tree.",
        "notes": "Root rot (Phytophthora cinnamomi) is the number one killer. Plant high, mulch heavily, and never let water pool.",
        "sources": [
            ("Sustainable Gardening Australia, companion planting", "https://www.sgaonline.org.au/companion-planting/"),
        ],
    },
    {
        "name": "Fig",
        "slug": "fig",
        "species_slugs": ["fig"],
        "icon": "🌳",
        "intro": "Figs are tough, drought-hardy trees with vigorous, invasive roots. Companions should tolerate dry shade and stay out of the root zone.",
        "good": [
            ("Comfrey", "A hardy nutrient miner that copes with the dry, shaded soil under a fig.", "established-practice"),
            ("Marigold (Tagetes)", "Dense plantings can reduce root-knot nematodes that stress fig roots.", "research-backed"),
            ("Drought-tolerant flowering herbs (rosemary, oregano, thyme)", "Suit the same dry conditions and bring in bees and hoverflies.", "established-practice"),
            ("Strawberry or other shallow groundcover", "Fills the dappled shade under the canopy in cooler-summer areas.", "traditional"),
            ("Rue", "A traditional fig companion said to deter pests. Evidence is thin, and the sap can irritate skin in sun.", "traditional"),
        ],
        "avoid": [
            ("Thirsty plants in the root zone (figs are aggressive competitors)", "established-practice"),
            ("Drains, pipes, paving and foundations (invasive roots)", "established-practice"),
        ],
        "pollinator": "The common figs grown in Australia (Brown Turkey, Black Genoa, White Adriatic, Preston Prolific) are parthenocarpic, so they set fruit with no pollination and no second tree. Avoid Smyrna types, which need a specific wasp not present here.",
        "notes": "Plant figs well away from drains, paths and foundations. They fruit well in a large pot, which conveniently restrains the roots.",
        "sources": [
            ("Sustainable Gardening Australia, companion planting", "https://www.sgaonline.org.au/companion-planting/"),
        ],
    },
    {
        "name": "Stone Fruit (Peach, Plum, Apricot, Nectarine, Cherry)",
        "slug": "stone-fruit",
        "species_slugs": ["peach", "nectarine", "apricot", "plum", "cherry"],
        "icon": "🍑",
        "intro": "Peaches, plums, apricots, nectarines and cherries flower early, often before pollinators are active. Companions that flower in late winter and early spring help bring bees in at the right time.",
        "good": [
            ("Early-flowering bee plants (borage, phacelia, alyssum)", "Flower as the stone fruit blooms, drawing in the bees that pollination depends on.", "established-practice"),
            ("Comfrey", "A potassium-rich mulch source that suits fruit development.", "established-practice"),
            ("Yarrow and other umbellifers", "Attract hoverflies and lacewings whose larvae eat aphids.", "established-practice"),
            ("Garlic and chives", "A traditional underplanting said to deter aphids and leaf curl. Evidence is weak, but they take little room and are useful in the kitchen.", "traditional"),
            ("Clover groundcover", "Fixes nitrogen and keeps the orchard floor living rather than bare.", "established-practice"),
        ],
        "avoid": [
            ("Grass right under the canopy (competes during critical spring growth)", "established-practice"),
            ("Tansy (toxic to stock and spreads readily)", "traditional"),
            ("Fennel (often called allelopathic)", "traditional"),
        ],
        "pollinator": "Most peaches and nectarines are self-fertile. Many plums, sweet cherries and some apricots need a compatible second variety flowering at the same time. Check the label: most Japanese plums need a partner, while European plums like d'Agen are largely self-fertile.",
        "notes": "Stone fruit needs winter chill. Matching the variety's chill requirement to your district matters far more than any companion plant.",
        "sources": [
            ("Sustainable Gardening Australia, companion planting", "https://www.sgaonline.org.au/companion-planting/"),
            ("Yates, companion planting guide", "https://www.yates.com.au/garden-hub/companion-planting-guide/"),
        ],
    },
    {
        "name": "Apple and Pear",
        "slug": "apple-pear",
        "species_slugs": ["apple", "pear"],
        "icon": "🍏",
        "intro": "Apples and pears need winter chill and, in most cases, a second variety for pollination. Companions can bring in pollinators and keep the orchard floor healthy.",
        "good": [
            ("Spring-flowering bee plants (phacelia, alyssum, clover)", "Flower with the blossom to bring in the bees that cross-pollination needs.", "established-practice"),
            ("Clover or legume groundcover", "Fixes nitrogen and feeds the orchard floor instead of leaving bare soil.", "established-practice"),
            ("Chives or daffodils ringing the trunk", "A grass-free low ring keeps lawn back from the trunk. The pest-repellent reputation is folklore, but the cleared zone genuinely helps.", "traditional"),
            ("Nasturtium", "A sprawling aphid trap crop and hoverfly attractant. Keep it from swamping young trees.", "traditional"),
            ("Yarrow and umbellifers", "Bring in the aphid predators that keep colonies down.", "established-practice"),
        ],
        "avoid": [
            ("Tall grass under the canopy (harbours pests and competes)", "established-practice"),
            ("Black walnut (juglone), keep well clear", "research-backed"),
        ],
        "pollinator": "Most apples and pears need a second compatible variety flowering at the same time; a lone tree often crops poorly. Crabapples are excellent universal pollinisers for apples. A few self-fertile apples exist but still fruit better with a partner.",
        "notes": "Codling moth is the main backyard pest. Grease bands, traps and sanitation help, but no companion plant controls it. Match chill requirements to your district.",
        "sources": [
            ("Sustainable Gardening Australia, companion planting", "https://www.sgaonline.org.au/companion-planting/"),
            ("Fruit Salad Trees, growing apples in Australia", "https://www.fruitsaladtrees.com/blogs/news/apples-companion-planting-and-other-helpful-tips-for-growing-the-backyard-favourite"),
        ],
    },
    {
        "name": "Tropical Fruits (Lychee, Dragon Fruit, Banana, Longan)",
        "slug": "tropical",
        "species_slugs": ["lychee", "longan", "dragon-fruit", "banana", "papaya"],
        "icon": "🍍",
        "intro": "Lychee, longan, dragon fruit and banana suit the tropics and warm subtropics. In cooler districts they need a warm, wind-sheltered, frost-free spot.",
        "good": [
            ("Ginger and turmeric", "Thrive in the same warm, humid, part-shaded conditions and give an edible rhizome harvest.", "established-practice"),
            ("Legume groundcover (pinto peanut)", "Protects bare tropical soil and fixes nitrogen between trees.", "established-practice"),
            ("Papaya or banana as a nurse", "Fast shelter and humidity for slow starters like lychee while they establish.", "traditional"),
            ("Sweet potato", "An edible groundcover that suppresses weeds and holds soil moisture.", "traditional"),
        ],
        "avoid": [
            ("Heavy nitrogen feeding around lychee (pushes leaf growth over fruiting)", "context-dependent"),
            ("Tall trees that crowd or shade the canopy", "established-practice"),
        ],
        "pollinator": "Lychee and longan are insect-pollinated and crop better with bees about. Many dragon fruit are self-fertile, but some need a second variety and even hand pollination at night. Bananas need no pollination.",
        "notes": "In subtropical and temperate zones, give tropical fruit a warm wall or windbreak and frost protection over winter.",
        "sources": [
            ("Sustainable Gardening Australia, companion planting", "https://www.sgaonline.org.au/companion-planting/"),
        ],
    },
]

# (name, description, evidence_grade)
AVOID_ALL = [
    ("Fennel (Foeniculum vulgare)", "Widely listed as allelopathic and bad near other plants. The evidence in garden soil is actually thin, but fennel also self-seeds into a serious weed, so keeping it out of the orchard is still sensible.", "traditional"),
    ("Black walnut (Juglans nigra)", "Roots release juglone, documented to harm many plants including apple, pear and stone fruit. Keep fruit trees well clear.", "research-backed"),
    ("Lawn and grass directly under the canopy", "Competes with feeder roots for water and nitrogen. Keep a mulched, grass-free circle around every fruit tree.", "established-practice"),
    ("Brassicas as a long-term underplanting", "Can build up clubroot in the soil, which then persists for years. Fine as an occasional short crop.", "context-dependent"),
]

# (name, description, evidence_grade)
NITROGEN_FIXERS = [
    ("White clover", "A low, bee-friendly living groundcover for orchard floors in temperate and subtropical gardens.", "established-practice"),
    ("Pinto peanut (Arachis pintoi)", "A tough perennial legume groundcover for tropical and subtropical orchards.", "established-practice"),
    ("Tagasaste (tree lucerne)", "A fast nitrogen-fixing small tree for windbreaks and mulch in temperate and Mediterranean zones. Cut it before it seeds, as it can become weedy.", "context-dependent"),
    ("Pigeon pea", "A short-lived tropical and subtropical legume with a deep taproot. Replant every few years.", "established-practice"),
    ("Comfrey (Bocking 14)", "Not a legume and fixes no nitrogen, but it mines deep nutrients and makes an excellent mulch. The sterile Bocking 14 will not seed everywhere.", "established-practice"),
]

POLLINATOR_SUMMARY = [
    ("Citrus", "Self-fertile. A single tree fruits; extra varieties lift yield slightly."),
    ("Mango", "Sets some fruit alone; a second variety improves yield. Kensington Pride most reliable solo."),
    ("Avocado", "Plant one type A and one type B for best set. Wurtz crops solo."),
    ("Apple", "Almost all need a cross-pollinator. Crabapple works as a universal partner."),
    ("Pear", "Most need a cross-pollinator. Match bloom times."),
    ("Sweet cherry", "Most need a compatible second variety."),
    ("Japanese plum", "Needs a cross-pollinator."),
    ("European plum", "Mostly self-fertile; a partner improves yield."),
    ("Peach / Nectarine", "Self-fertile."),
    ("Apricot", "Mostly self-fertile; some varieties benefit from a partner."),
    ("Fig", "Common Australian varieties are parthenocarpic (no pollination needed)."),
    ("Lychee / Longan", "Insect-pollinated; crop better with bees about."),
    ("Dragon fruit", "Varies by variety; some self-fertile, some need a partner or hand pollination."),
    ("Banana", "No pollination required."),
]

FAQS = [
    (
        "What is the best companion plant for all fruit trees?",
        "Comfrey (the sterile Bocking 14) is the most useful all-rounder. It mines nutrients from deep soil, makes excellent mulch, and does not spread by seed. Plant one or two per tree at the drip line. It does not fix nitrogen, so pair it with a legume groundcover for that.",
    ),
    (
        "Do companion plants actually repel pests?",
        "Mostly not in the way folklore claims. There is little evidence that a scattered herb repels a specific pest. What does work is biodiversity: a mix of flowering plants supports bees and natural predators (hoverflies, lacewings, parasitic wasps), and a few documented cases like dense marigolds suppressing soil nematodes. For Australia's main fruit pests, fruit fly and codling moth, rely on netting, bagging, traps and hygiene, not companions.",
    ),
    (
        "Do I need two fruit trees to get fruit?",
        "It depends on the species and variety. Most citrus, peaches, nectarines, figs and bananas are self-fertile. Apples, pears, sweet cherries and avocados crop far better with a second compatible variety. Check the pollinator requirements for your variety before buying.",
    ),
    (
        "Can I grow companion plants under a fruit tree?",
        "Yes, but avoid grass and keep a clear mulched circle right around the trunk to prevent collar rot. The most useful understorey plants are comfrey, white clover, alyssum and nasturtium. Plant them at the drip line, not against the trunk.",
    ),
    (
        "Why is fennel said to be bad near fruit trees?",
        "Fennel is the classic bad companion. The evidence that it chemically harms established fruit trees in garden soil is actually thin, but fennel self-seeds aggressively into a weed, so it is still sensible to keep it out of the orchard.",
    ),
    (
        "What can I plant to attract bees to my fruit trees?",
        "Borage, phacelia, alyssum, white clover and lavender all draw bees and other pollinators. Borage and phacelia are especially useful because they flower heavily in spring when most fruit trees bloom. Sow phacelia in autumn for spring flowers.",
    ),
    (
        "How close should companion plants be to fruit trees?",
        "Most companions work best at the drip line, the outer edge of the canopy, rather than against the trunk. Keep 30 to 50cm clear around the trunk with mulch. Tall companions like tagasaste should sit 2 to 3m out to avoid shading and root competition.",
    ),
]

# Page-level references for the evidence framing (not tied to one species).
GENERAL_SOURCES = [
    ("Sustainable Gardening Australia, Companion Planting", "https://www.sgaonline.org.au/companion-planting/"),
    ("WSU Extension, The Myth of Companion Planting (Linda Chalker-Scott)", "https://s3.wp.wsu.edu/uploads/sites/403/2015/03/companion-plantings.pdf"),
    ("University of Florida IFAS, Marigolds (Tagetes) for Nematode Management", "https://edis.ifas.ufl.edu/publication/NG045"),
    ("Garden Myths, Companion Planting: Truth or Myth", "https://www.gardenmyths.com/companion-planting-truth-myth/"),
]


# ----- Helpers -----

def load_valid_species_slugs() -> set:
    """Slugs that have a real /species/<slug>.html page. Empty set if the file is
    missing so internal links are silently omitted rather than 404."""
    try:
        with open(SPECIES_FILE) as f:
            return {s["slug"] for s in json.load(f)}
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return set()


def _species_link_html(sp: dict, valid_slugs: set) -> str:
    links = [
        f'<a href="/species/{s}.html" class="text-green-700 hover:underline">{s.replace("-", " ")}</a>'
        for s in sp.get("species_slugs", []) if s in valid_slugs
    ]
    if not links:
        return ""
    return (
        '<p class="text-xs text-gray-500 mt-3">Current stock and prices: '
        + ", ".join(links)
        + ".</p>"
    )


def _sources_html(sp: dict) -> str:
    srcs = sp.get("sources") or []
    if not srcs:
        return ""
    items = "".join(
        f'<li><a href="{url}" target="_blank" rel="noopener" class="text-green-700 hover:underline">{title}</a></li>'
        for title, url in srcs
    )
    return (
        '<details class="mt-3 text-xs text-gray-500">'
        '<summary class="cursor-pointer hover:text-gray-700">Sources and further reading</summary>'
        f'<ul class="list-disc pl-5 mt-1 space-y-0.5">{items}</ul></details>'
    )


def build_species_card(sp: dict, valid_slugs: set) -> str:
    good_rows = "".join(
        f'<li class="mb-2"><strong class="text-green-800">{name}</strong>. {desc}{grade_badge(grade)}</li>'
        for name, desc, grade in sp["good"]
    )
    avoid_items = "".join(
        '<span class="inline-flex items-center mr-2 mb-1">'
        f'<span class="bg-red-50 border border-red-200 text-red-700 text-xs px-2 py-0.5 rounded-full">{name}</span>'
        f"{grade_badge(grade)}</span>"
        for name, grade in sp["avoid"]
    )
    intro_html = f'\n  <p class="text-sm text-gray-600 mb-4">{sp["intro"]}</p>' if sp.get("intro") else ""
    return f"""
<section class="mb-10" id="{sp['slug']}">
  <h2 class="text-xl font-bold text-green-900 mb-3">{sp['icon']} {sp['name']}</h2>{intro_html}

  <div class="grid md:grid-cols-2 gap-6">
    <div>
      <h3 class="font-semibold text-gray-700 mb-2 text-sm uppercase tracking-wide">Good companions</h3>
      <ul class="text-sm text-gray-600 space-y-1 list-none pl-0">
        {good_rows}
      </ul>
    </div>
    <div>
      <h3 class="font-semibold text-gray-700 mb-2 text-sm uppercase tracking-wide">Avoid nearby</h3>
      <div class="mb-4 flex flex-wrap">{avoid_items}</div>

      <h3 class="font-semibold text-gray-700 mb-2 text-sm uppercase tracking-wide">Pollination</h3>
      <p class="text-sm text-gray-600">{sp['pollinator']}</p>
    </div>
  </div>

  <div class="mt-3 p-3 bg-gray-50 rounded-lg text-xs text-gray-500 border border-gray-100">
    {sp['notes']}
  </div>
  {_species_link_html(sp, valid_slugs)}
  {_sources_html(sp)}
</section>
"""


def build_how_to_read() -> str:
    legend = "".join(
        f'<li class="flex items-start gap-2">{grade_badge(g)}<span class="text-gray-600">{meaning}</span></li>'
        for g, meaning in [
            ("research-backed", "Supported by peer-reviewed studies or university research."),
            ("established-practice", "Broad horticultural consensus, low controversy."),
            ("traditional", "Commonly recommended folklore with little hard evidence."),
            ("context-dependent", "True only for certain varieties, climates or conditions."),
        ]
    )
    return f"""
<section class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-8 text-sm">
  <p class="font-semibold text-amber-900 mb-1">How to read this guide</p>
  <p class="text-gray-700 mb-3">Most companion planting advice online is tradition rather than tested science, so we grade every suggestion by how good the evidence is. The honest summary: a diverse, well-mulched garden that feeds bees and predatory insects helps your trees, while most specific "plant this to repel that" pairings are unproven.</p>
  <ul class="space-y-1">
    {legend}
  </ul>
</section>"""


def build_avoid_section() -> str:
    rows = "".join(
        '<div class="flex gap-3 mb-3"><span class="text-red-500 mt-0.5 flex-shrink-0">&#10060;</span>'
        f'<div><strong class="text-gray-800">{name}</strong>{grade_badge(grade)}'
        f'<p class="text-sm text-gray-600 mt-0.5">{desc}</p></div></div>'
        for name, desc, grade in AVOID_ALL
    )
    return f"""
<section class="mb-10" id="avoid">
  <h2 class="text-xl font-bold text-green-900 mb-4">Plants to Avoid Near Fruit Trees</h2>
  {rows}
</section>
"""


def build_nitrogen_fixers_section() -> str:
    rows = "".join(
        '<div class="flex gap-3 mb-3"><span class="text-green-500 mt-0.5 flex-shrink-0">&#9679;</span>'
        f'<div><strong class="text-gray-800">{name}</strong>{grade_badge(grade)}'
        f'<p class="text-sm text-gray-600 mt-0.5">{desc}</p></div></div>'
        for name, desc, grade in NITROGEN_FIXERS
    )
    return f"""
<section class="mb-10" id="nitrogen">
  <h2 class="text-xl font-bold text-green-900 mb-4">Nitrogen Fixers and Soil Builders</h2>
  <p class="text-gray-600 text-sm mb-4">These plants improve soil fertility, reducing fertiliser needs across your whole orchard.</p>
  {rows}
</section>
"""


def build_pollinator_table() -> str:
    rows = "".join(
        f'<tr class="border-b border-gray-100 hover:bg-gray-50"><td class="py-2 pr-4 font-medium text-sm text-gray-800">{species}</td><td class="py-2 text-sm text-gray-600">{note}</td></tr>'
        for species, note in POLLINATOR_SUMMARY
    )
    return f"""
<section class="mb-10" id="pollinators">
  <h2 class="text-xl font-bold text-green-900 mb-3">Pollinator Requirements Quick Reference</h2>
  <p class="text-gray-600 text-sm mb-4">Check this before buying a single tree. Getting it wrong means years without fruit.</p>
  <div class="overflow-x-auto rounded-lg border border-gray-200">
    <table class="w-full bg-white text-left">
      <thead class="bg-gray-50 border-b border-gray-200">
        <tr>
          <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Species</th>
          <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Pollination</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100">
        {rows}
      </tbody>
    </table>
  </div>
</section>
"""


def build_faq_section() -> str:
    items = "".join(
        f"""<div class="mb-5">
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


def build_references_section() -> str:
    items = "".join(
        f'<li><a href="{url}" target="_blank" rel="noopener" class="text-green-700 hover:underline">{title}</a></li>'
        for title, url in GENERAL_SOURCES
    )
    return f"""
<section class="mb-10" id="references">
  <h2 class="text-xl font-bold text-green-900 mb-3">References and Further Reading</h2>
  <ul class="list-disc pl-5 text-sm text-gray-600 space-y-1">
    {items}
  </ul>
</section>
"""


def build_toc() -> str:
    species_links = "".join(
        f'<li><a href="#{sp["slug"]}" class="text-green-700 hover:underline text-sm">{sp["icon"]} {sp["name"]}</a></li>'
        for sp in SPECIES_COMPANIONS
    )
    return f"""
<div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-8">
  <p class="font-semibold text-green-900 mb-2 text-sm">Contents</p>
  <ul class="space-y-1">
    {species_links}
    <li><a href="#avoid" class="text-green-700 hover:underline text-sm">Plants to avoid</a></li>
    <li><a href="#nitrogen" class="text-green-700 hover:underline text-sm">Nitrogen fixers and soil builders</a></li>
    <li><a href="#pollinators" class="text-green-700 hover:underline text-sm">Pollinator requirements quick reference</a></li>
    <li><a href="#faq" class="text-green-700 hover:underline text-sm">FAQs</a></li>
    <li><a href="#references" class="text-green-700 hover:underline text-sm">References and further reading</a></li>
  </ul>
</div>
"""


def build_faq_jsonld() -> str:
    """schema.org FAQPage structured data, kept in sync with FAQS."""
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in FAQS
        ],
    }
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"


def build_page() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    valid_slugs = load_valid_species_slugs()

    species_sections = "".join(build_species_card(sp, valid_slugs) for sp in SPECIES_COMPANIONS)

    head = render_head(
        title="Companion Planting Guide for Fruit Trees (Australia) | treestock.com.au",
        description="Evidence-graded companion planting for citrus, mango, avocado, fig, stone fruit, apple and pear in Australia. Pollinator requirements, soil builders, plants to avoid, and which pest claims actually hold up.",
        canonical_url="https://treestock.com.au/companion-planting-guide.html",
        og_title="Companion Planting for Fruit Trees, an Evidence-Graded Australian Guide",
        og_description="Which companions actually help citrus, mango, avocado, fig and stone fruit in Australia, which are folklore, and what your trees really need for pollination.",
        og_type="article",
        og_image="https://treestock.com.au/og-image.png",
        extra_head=build_faq_jsonld(),
    )
    header = render_header()
    breadcrumb = render_breadcrumb([("Home", "/"), ("Companion Planting Guide", "")])
    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-8">
  {breadcrumb}

  <h1 class="text-2xl font-bold text-green-900 mb-2">Companion Planting Guide for Fruit Trees</h1>
  <p class="text-gray-600 text-sm mb-6">What to grow near citrus, mango, avocado, fig, stone fruit, apple and pear in Australian conditions, with honest evidence grades and pollinator requirements. Updated {today}.</p>

  <div class="prose prose-sm text-gray-700 mb-6 max-w-2xl">
    <p>Companion planting means growing other plants near your fruit trees for some benefit: attracting pollinators and predatory insects, building soil, suppressing weeds, or holding moisture. It is genuinely useful, but it is also one of the most myth-laden topics in gardening.</p>
    <p>This guide covers the fruit trees most commonly grown in Australian gardens. We grade every suggestion by how good the evidence is, check the pollination advice carefully (getting it wrong can cost you years of fruit), and note the Australian pests and climates that actually matter. Use the pollinator table before you buy a single tree.</p>
  </div>

  {build_how_to_read()}

  {build_toc()}

  {species_sections}

  {build_avoid_section()}

  {build_nitrogen_fixers_section()}

  {build_pollinator_table()}

  {build_faq_section()}

  {build_references_section()}

  <!-- CTA -->
  <section class="bg-green-50 border border-green-200 rounded-lg p-6 mt-6">
    <h2 class="text-lg font-semibold text-green-900 mb-2">Find fruit trees for sale in Australia</h2>
    <p class="text-sm text-green-800 mb-4">treestock.com.au tracks stock and prices across nurseries daily. Search by species, filter by your state.</p>
    <div class="flex gap-3 flex-wrap">
      <a href="/" class="inline-block bg-green-700 text-white px-4 py-2 rounded text-sm font-medium hover:bg-green-800">Search all nurseries</a>
      <a href="/species/" class="inline-block bg-white border border-green-300 text-green-700 px-4 py-2 rounded text-sm font-medium hover:bg-green-50">Browse by species</a>
      <a href="/rare.html" class="inline-block bg-white border border-green-300 text-green-700 px-4 py-2 rounded text-sm font-medium hover:bg-green-50">Rare and unusual finds</a>
    </div>
  </section>
</main>

{footer}
</body>
</html>"""


def main():
    if len(sys.argv) < 2:
        print("Usage: build_companion_guide.py /path/to/output/")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)

    html = build_page()
    out_file = output_dir / "companion-planting-guide.html"
    out_file.write_text(html)
    print(f"Written: {out_file} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
