#!/usr/bin/env python3
"""
Build the fruit-tree pollination guide (/fruit-tree-pollination-guide.html) for
treestock.com.au.

Targets: 'fruit tree pollination chart australia', 'do you need two apple trees',
'self pollinating fruit trees australia', 'type a and b avocado', 'kiwifruit
male female', and similar high-intent buying questions. Getting pollination
wrong costs a collector years of no fruit, so this is exactly the question the
treestock audience asks before buying.

Mirrors build_companion_guide.py: curated Python data, evidence-graded claims
(shared stocklib.evidence), per-family cards, species links validated against
the taxonomy so they cannot 404, variety links validated against the built
/variety/ pages at build time, FAQPage JSON-LD, cited throughout.

Usage:
    python3 build_pollination_guide.py /path/to/output/
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer, render_treesmith_promo

from stocklib.evidence import EVIDENCE_GRADES, grade_badge
from stocklib.taxonomy import enabled_species


# ----- Content data -----
# Each family card: self-fertility status (with an evidence grade), a short
# intro, an optional partner table (only where cross-pollination genuinely
# matters), practical notes, and per-family sources. `species_slugs` link to
# live stock pages; partner `vslug` (optional) links to a variety page when one
# exists. Facts here are the established horticultural consensus for Australian
# growing; sources are listed per card.

# status: (label, evidence_grade). need_partner drives the summary-table verdict.
FAMILIES = [
    {
        "key": "apple",
        "title": "Apple",
        "icon": "&#127823;",
        "species_slugs": ["apple"],
        "status": ("Needs a pollination partner", "research-backed"),
        "need_partner": True,
        "intro": (
            "Almost all apples need a second, different apple variety flowering at the same time to "
            "set a full crop. Nurseries group apples into flowering times (early, mid, late); a good "
            "partner is any other variety whose bloom overlaps. A flowering crabapple is the easiest "
            "universal partner and pollinates almost everything."
        ),
        "partners": [
            ("Most mid-season apples (Pink Lady, Fuji, Gala, Granny Smith)", None,
             "Pollinate each other freely: plant any two whose flowering overlaps.", "research-backed"),
            ("Triploid varieties (Gravenstein, Bramley's Seedling, Jonagold)", None,
             "Have sterile pollen and cannot pollinate anything, so they need TWO other diploid apples nearby, not one.", "research-backed"),
            ("Crabapple", None,
             "A long-flowering universal pollinator. One crab in the garden covers a mix of apple varieties.", "established-practice"),
        ],
        "notes": (
            "No room for two trees? A multi-graft apple (several varieties on one trunk) or a self-fertile "
            "variety such as some strains of Granny Smith solves it. Bees do the actual work, so avoid spraying "
            "insecticide during blossom."
        ),
        "sources": [
            ("Apples and pears pollination (BeeAware, Hort Innovation)", "https://beeaware.org.au/pollination/pollinator-reliant-crops/apples-pears/"),
            ("Apple pollination groups (Royal Horticultural Society)", "https://www.rhs.org.uk/advice/pdfs/applepollinationgroups.pdf"),
            ("Orchard pollination: pollinizers, pollinators and weather (Penn State Extension)", "https://extension.psu.edu/orchard-pollination-pollinizers-pollinators-and-weather"),
        ],
    },
    {
        "key": "pear",
        "title": "Pear (European and Nashi)",
        "icon": "&#127824;",
        "species_slugs": ["pear"],
        "status": ("Needs a pollination partner", "research-backed"),
        "need_partner": True,
        "intro": (
            "European pears (Williams, Beurre Bosc, Packham) crop poorly alone and want a second European "
            "variety flowering at the same time. Nashi (Asian pears) and European pears can pollinate each "
            "other when their bloom overlaps, so a Nashi can partner a European pear and the reverse."
        ),
        "partners": [
            ("Williams / Bartlett", None, "Partly self-fertile but crops far better with a partner such as Beurre Bosc or Packham.", "established-practice"),
            ("Beurre Bosc, Packham, Josephine", None, "Reliable mutual partners flowering mid-season.", "established-practice"),
            ("Nashi (Asian pear)", None, "Cross-pollinates European pears and vice versa where flowering overlaps.", "research-backed"),
        ],
        "notes": "A multi-graft pear carries its own partner. Corella and other coloured pears follow the same rules as their parent variety.",
        "sources": [
            ("Apples and pears pollination (BeeAware, Hort Innovation)", "https://beeaware.org.au/pollination/pollinator-reliant-crops/apples-pears/"),
            ("Manage Williams pear trees to boost yields (Tree Fruit, treefruit.com.au)", "https://www.treefruit.com.au/orchard/trees/tree-training-trellis/407-manage-williams-pear-trees-to-boost-yields"),
            ("Pears: pollination partners (Bulleen Art and Garden)", "https://baag.com.au/pears/"),
        ],
    },
    {
        "key": "cherry",
        "title": "Sweet cherry",
        "icon": "&#127826;",
        "species_slugs": ["cherry"],
        "status": ("Depends on the variety", "context-dependent"),
        "need_partner": True,
        "intro": (
            "Older sweet cherries are self-incompatible and sorted into 'incompatibility groups': two cherries "
            "in the same group will not pollinate each other, so you must pick a compatible pair from different "
            "groups with overlapping bloom. The modern shortcut is a self-fertile variety, which crops alone AND "
            "pollinates almost any other cherry."
        ),
        "partners": [
            ("Stella, Lapins, Sunburst, Sweetheart", None, "Self-fertile: one tree crops on its own, and each is a universal pollinator for other cherries.", "research-backed"),
            ("Older varieties (Bing, Napoleon, Ron's Seedling)", None, "Self-infertile and group-restricted. Pair with a self-fertile variety or a known compatible partner.", "research-backed"),
            ("Morello / sour cherry", None, "Self-fertile and crops alone.", "established-practice"),
        ],
        "notes": "If you only have room for one cherry, make it a self-fertile variety. Cherries also need enough winter chill, so match the variety to your climate as well.",
        "sources": [
            ("Sweet cherry pollination and incompatibility groups (WSU Tree Fruit)", "https://treefruit.wsu.edu/web-article/sweet-cherry-pollination/"),
            ("Pollination (The Heritage Fruit Trees)", "https://www.heritagefruittrees.com.au/pollination/"),
        ],
    },
    {
        "key": "plum",
        "title": "Plum (Japanese and European)",
        "icon": "&#127855;",
        "species_slugs": ["plum"],
        "status": ("Usually needs a partner", "research-backed"),
        "need_partner": True,
        "intro": (
            "Most Japanese plums (Santa Rosa, Mariposa, Satsuma) need a second Japanese plum for a good crop. "
            "European plums and prunes (D'Agen, Angelina) are more often self-fertile. The two types flower at "
            "different times and generally will not pollinate each other, so match a partner within the same type."
        ),
        "partners": [
            ("Santa Rosa", "plum-santa-rosa", "Partially self-fertile and the classic pollinator for other Japanese plums; a good single-tree choice that also partners the rest.", "established-practice"),
            ("Mariposa, Satsuma, Wickson", None, "Need a Japanese-plum partner such as Santa Rosa.", "research-backed"),
            ("Damson, Victoria (European)", None, "Reliably self-fertile European plums that crop alone. Other Europeans (Greengage, Angelina, D'Agen) want a European partner.", "established-practice"),
        ],
        "notes": "Blood plums and most supermarket-type plums are Japanese. If in doubt, plant Santa Rosa alongside and it will pollinate almost any other Japanese plum.",
        "sources": [
            ("Plum (Clemson Cooperative Extension, HGIC)", "https://hgic.clemson.edu/factsheet/plum/"),
            ("Pollination: Japanese and European plums (The Heritage Fruit Trees)", "https://www.heritagefruittrees.com.au/pollination/"),
            ("Plums: pollination pairings (Sabrina Hahn)", "https://sabrinahahn.com.au/factsheet/plums/"),
        ],
    },
    {
        "key": "avocado",
        "title": "Avocado (Type A and Type B)",
        "icon": "&#129361;",
        "species_slugs": ["avocado"],
        "status": ("Self-fertile, but a partner lifts yield", "context-dependent"),
        "need_partner": False,
        "intro": (
            "Avocado flowers are both male and female, but each opens as female one day and male the next on a "
            "timed cycle. Type A varieties are female in the morning; Type B in the afternoon. Pairing a Type A "
            "with a Type B overlaps the receptive and pollen-shedding windows and lifts the crop, but a single "
            "tree still sets useful fruit because the cycle blurs in real garden temperatures."
        ),
        "partners": [
            ("Hass, Reed, Wurtz, Lamb Hass", "avocado-hass", "Type A. Set fruit alone; pair with a Type B to lift yield.", "context-dependent"),
            ("Fuerte, Bacon, Sharwil, Shepard", "avocado-fuerte", "Type B. Same story: productive alone, better with a Type A nearby.", "context-dependent"),
            ("Wurtz (Little Cado)", None, "A naturally dwarf Type A, the usual pick where there is room for only one tree.", "established-practice"),
        ],
        "notes": "You do not strictly need two avocados. Drainage and frost protection matter far more to a young avocado than a pollination partner does.",
        "sources": [
            ("Avocado flowering basics: Type A and Type B (UC Riverside Avocado Collection)", "https://avocado.ucr.edu/avocado-flowering-basics"),
        ],
    },
    {
        "key": "kiwifruit",
        "title": "Kiwifruit",
        "icon": "&#129373;",
        "species_slugs": ["kiwifruit"],
        "status": ("Needs a male and female vine", "research-backed"),
        "need_partner": True,
        "intro": (
            "Kiwifruit vines are either male or female. Only the female fruits, and it needs a male vine "
            "flowering at the same time to pollinate it. One male can service several females, so a small "
            "garden needs at least one of each. Match the male's flowering to the female's."
        ),
        "partners": [
            ("Hayward (female)", None, "The standard fuzzy kiwifruit. Late flowering, so pair it with a late-flowering male.", "research-backed"),
            ("Bruno, Monty (female)", None, "Earlier flowering; pair with an early-flowering male.", "established-practice"),
            ("Jenny (self-fertile)", None, "Sets some fruit alone, but crops much better with a male nearby.", "context-dependent"),
        ],
        "notes": "Buy a male and a female together and check the labels; an all-female planting will flower beautifully and never fruit. Ask the nursery to match the male's flowering time to your female variety.",
        "sources": [
            ("Kiwifruit (Actinidia spp.): male and female vines (University of Wisconsin-Madison Extension)", "https://hort.extension.wisc.edu/articles/kiwifruit-actinidia-spp/"),
            ("Pollination of fruit trees, including dioecious kiwifruit (Daleys Fruit Tree Nursery)", "https://blog.daleysfruit.com.au/2014/11/pollination-of-fruit-trees.html"),
        ],
    },
    {
        "key": "pistachio",
        "title": "Pistachio",
        "icon": "&#127793;",
        "species_slugs": ["pistachio"],
        "status": ("Needs a male and female tree", "research-backed"),
        "need_partner": True,
        "intro": (
            "Like kiwifruit, pistachios are single-sex trees. Only the female bears nuts, and it needs a male "
            "tree flowering at the same time to pollinate it. Pistachios are wind pollinated (not by bees), so "
            "the male needs to be upwind and reasonably close. One male pollinates many females, so a home "
            "garden needs only a single male."
        ),
        "partners": [
            ("Female (Sirora, Kerman)", None, "Bears the nuts; needs a male flowering at the same time.", "research-backed"),
            ("Male (Peters)", None, "Pollen source only; a single male pollinates a whole backyard planting of females.", "established-practice"),
        ],
        "notes": "Pistachios are slow and need long hot dry summers and cold winters, so they suit inland and Mediterranean districts. Plan for both sexes from the start.",
        "sources": [
            ("Pistachio is dioecious and wind-pollinated (UC California Pistachio Research)", "https://ucanr.edu/site/california-pistachio-research/climate-cultivars"),
        ],
    },
    {
        "key": "blueberry",
        "title": "Blueberry",
        "icon": "&#129744;",
        "species_slugs": ["blueberry"],
        "status": ("Self-fertile, cross-pollination lifts yield", "research-backed"),
        "need_partner": False,
        "intro": (
            "Highbush blueberries (the common southern and northern highbush types) are largely self-fertile, "
            "but planting two different varieties gives bigger berries and heavier crops. Rabbiteye blueberries, "
            "grown in warmer areas, are mostly self-infertile and DO need a second rabbiteye variety."
        ),
        "partners": [
            ("Southern / northern highbush", None, "Crop alone, but two varieties with overlapping bloom lift size and yield.", "research-backed"),
            ("Rabbiteye types", None, "Need a second, different rabbiteye variety flowering at the same time.", "research-backed"),
        ],
        "notes": "Whatever the type, two varieties are a safe default: it improves crops and stretches the picking season. Blueberries also need acidic soil.",
        "sources": [
            ("Blueberry: highbush self-fertility and rabbiteye cross-pollination (Clemson Cooperative Extension, HGIC)", "https://hgic.clemson.edu/factsheet/blueberry/"),
        ],
    },
    {
        "key": "self-fertile",
        "title": "Fruit that crops on its own",
        "icon": "&#9989;",
        "species_slugs": ["lemon", "lime", "orange", "mandarin", "grapefruit", "fig", "mango", "mulberry", "pomegranate", "peach", "nectarine", "apricot"],
        "status": ("Self-fertile: one tree is enough", "established-practice"),
        "need_partner": False,
        "intro": (
            "Plenty of popular fruit trees crop perfectly well as a single tree, so you can plant just one. "
            "Citrus (lemons, limes, oranges, mandarins, grapefruit) are all self-fertile. Peaches, nectarines "
            "and most apricots set fruit alone. Common figs are parthenocarpic and fruit with no pollination "
            "at all. Mango, mulberry, pomegranate, guava, loquat and tamarillo also crop as single trees."
        ),
        "partners": [],
        "notes": (
            "'Self-fertile' does not mean 'no bees needed'. Most of these still rely on insects to move pollen "
            "within the flower or between flowers on the same tree, so a bee-friendly garden and no spraying at "
            "blossom still pays off. A few (olive, macadamia, some feijoa) are self-fertile but crop noticeably "
            "better with a second variety, covered below."
        ),
        "sources": [
            ("Pollination requirements for various fruits and nuts (Penn State Extension)", "https://extension.psu.edu/pollination-requirements-for-various-fruits-and-nuts"),
            ("Which fruit trees are self-pollinating (The Heritage Fruit Trees)", "https://www.heritagefruittrees.com.au/pollination/"),
        ],
    },
    {
        "key": "boost",
        "title": "Self-fertile, but much better in pairs",
        "icon": "&#127811;",
        "species_slugs": ["olive", "macadamia", "feijoa", "passionfruit", "persimmon", "almond"],
        "status": ("Crops alone, cross-pollination boosts it", "established-practice"),
        "need_partner": False,
        "intro": (
            "Some trees will fruit as a single specimen but reward you for a second variety with a markedly "
            "heavier crop. If you have the space, plant two."
        ),
        "partners": [
            ("Olive", None, "Most varieties are self-fertile, but a second variety noticeably lifts fruit set. A few (Frantoio) are strong pollinators.", "research-backed"),
            ("Macadamia", None, "Self-fertile, but cross-pollination between two cultivars gives more and larger nuts.", "research-backed"),
            ("Feijoa", None, "Some varieties (Mammoth, Unique) self-fertile; many crop far better with a second variety, and birds and bees both help pollinate it.", "context-dependent"),
            ("Almond", None, "Most almonds need a second variety; self-fertile types (All-in-One, Independence) crop alone.", "research-backed"),
            ("Passionfruit", None, "Common purple types are largely self-compatible (yellow and Panama types often need a second vine); hand-pollinate in wet weather when bees are scarce.", "context-dependent"),
            ("Persimmon", None, "Astringent types (Nightingale, Hachiya) fruit without pollination; non-astringent Fuyu is self-fertile and crops alone.", "context-dependent"),
        ],
        "notes": "None of these strictly need a partner, so a single tree is fine in a small garden; add a second variety when you want maximum yield.",
        "sources": [
            ("Macadamia cross-pollination lifts nut set and size (BeeAware, Hort Innovation)", "https://beeaware.org.au/pollination/pollinator-reliant-crops/macadamias/"),
            ("Passionfruit pollination (BeeAware, Hort Innovation)", "https://beeaware.org.au/pollination/pollinator-reliant-crops/passionfruit/"),
            ("Self-compatible almond variety Independence (UC Agriculture and Natural Resources)", "https://ucanr.edu/blog/bug-squad/article/researchers-announce-findings-self-compatible-almond-variety"),
            ("Home garden persimmons: astringent and non-astringent (University of Georgia Extension)", "https://fieldreport.caes.uga.edu/publications/C784/home-garden-persimmons/"),
            ("Feijoa: self-fertile cultivars and cross-pollination (Bulleen Art and Garden)", "https://baag.com.au/feijoa/"),
        ],
    },
]

# Quick-reference summary table (verdict per common fruit). grade drives the badge.
SUMMARY = [
    ("Apple", "Needs a different variety flowering at the same time (or a crabapple).", "research-backed"),
    ("Pear (European and Nashi)", "Needs a compatible partner; Nashi and European cross-pollinate.", "research-backed"),
    ("Sweet cherry", "Pick a self-fertile variety, or a compatible pair from different groups.", "research-backed"),
    ("Plum", "Most Japanese plums need a partner; Santa Rosa pollinates the others. European plums often self-fertile.", "research-backed"),
    ("Avocado", "Self-fertile; a Type A plus a Type B lifts yield.", "context-dependent"),
    ("Kiwifruit", "Needs a male vine to pollinate the female.", "research-backed"),
    ("Pistachio", "Needs a male tree; wind pollinated.", "research-backed"),
    ("Blueberry", "Highbush self-fertile; rabbiteye needs a second variety. Two varieties best either way.", "research-backed"),
    ("Citrus, peach, nectarine, apricot, fig, mango", "Self-fertile. One tree crops on its own.", "established-practice"),
    ("Olive, macadamia, feijoa, almond", "Crop alone but noticeably better with a second variety.", "established-practice"),
]

FAQS = [
    (
        "Do you need two apple trees to get fruit?",
        "Almost always, yes. Nearly all apples need pollen from a different apple variety flowering at the same time to set a full crop, so a lone apple usually disappoints. Your options are to plant a second variety with overlapping bloom, plant a flowering crabapple (a universal pollinator), grow a multi-graft tree with several varieties on one trunk, or choose a self-fertile variety. A neighbour's apple within a hundred metres or so can also do the job.",
    ),
    (
        "Which fruit trees are self pollinating in Australia?",
        "Citrus (lemons, limes, oranges, mandarins, grapefruit), peaches, nectarines, most apricots, common figs, mango, mulberry, pomegranate, guava, loquat and tamarillo all crop as a single tree. Olives, macadamias, some feijoas and a few plums (Santa Rosa) also fruit alone but crop better with a second variety. Apples, pears, sweet cherries, most Japanese plums, kiwifruit and pistachios genuinely need a partner.",
    ),
    (
        "What is the difference between Type A and Type B avocados?",
        "It describes when the flowers are receptive. Avocado flowers open female one day and male the next. Type A varieties (Hass, Reed, Wurtz) are female in the morning and male the next afternoon; Type B varieties (Fuerte, Bacon, Sharwil) are the reverse. Planting one of each overlaps the female and male windows and lifts the crop. You do not strictly need both: a single avocado still sets useful fruit because the timing blurs at real garden temperatures.",
    ),
    (
        "Do I need a male and female kiwifruit?",
        "Yes. Kiwifruit vines are single-sex. Only the female bears fruit, and it needs a male vine flowering at the same time to pollinate it. One male will pollinate several females, so even a small planting needs at least one male. Match the male's flowering time to the female, as a late-flowering female such as Hayward needs a late-flowering male. Self-fertile 'Jenny' is the exception, though it too crops better with a male.",
    ),
    (
        "Will a single cherry tree fruit on its own?",
        "Only if it is a self-fertile variety such as Stella, Lapins, Sunburst or Sweetheart, which crop alone and also pollinate other cherries. Older sweet cherries (Bing, Napoleon) are self-infertile and fussy about partners because of compatibility groups, so for one tree, choose a self-fertile variety. Sour cherries like Morello are self-fertile too.",
    ),
    (
        "Does self-fertile mean I do not need bees?",
        "No. Self-fertile means a tree can set fruit with its own pollen, but that pollen still usually has to be carried within the flower or between flowers by insects. Bees remain essential, so a garden that feeds pollinators and is not sprayed with insecticide during blossom will fruit far better. Wind-pollinated fruit (pistachio, some nuts) and parthenocarpic fruit (common figs, astringent persimmons) are the exceptions that manage without insects.",
    ),
    (
        "How close do pollinating fruit trees need to be?",
        "Close enough for a bee to fly easily between them, generally within about 30 to 40 metres, and the nearer the better. What matters more than distance is that the two varieties flower at the same time, so a compatible partner with overlapping bloom two metres away beats a mistimed one next door. A multi-graft tree removes the distance question entirely.",
    ),
]

# Page-level references (used for the general framing; per-family sources sit on each card).
GENERAL_SOURCES = [
    ("Pollination requirements for various fruits and nuts (Penn State Extension)", "https://extension.psu.edu/pollination-requirements-for-various-fruits-and-nuts"),
    ("Crop pollination (BeeAware, Hort Innovation and Plant Health Australia)", "https://beeaware.org.au/pollination/"),
    ("Which fruit trees need a pollination partner (The Heritage Fruit Trees)", "https://www.heritagefruittrees.com.au/pollination/"),
]


# ----- Helpers -----

def load_valid_species_slugs() -> set:
    try:
        return {s["slug"] for s in enabled_species() if s.get("slug")}
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return set()


def variety_page_exists(vslug: str, out_dir: Path) -> bool:
    """True when a /variety/<slug>.html has been built. Guides run after
    build_variety_pages in the pipeline, so an existing file cannot 404."""
    return bool(vslug) and (out_dir / "variety" / f"{vslug}.html").exists()


def _partner_name_html(name: str, vslug, out_dir: Path) -> str:
    if vslug and variety_page_exists(vslug, out_dir):
        return f'<a href="/variety/{vslug}.html" class="text-green-700 hover:underline">{name}</a>'
    return name


def _species_links_html(fam: dict, valid_slugs: set) -> str:
    links = [
        f'<a href="/species/{s}.html" class="text-green-700 hover:underline">{s.replace("-", " ")}</a>'
        for s in fam.get("species_slugs", []) if s in valid_slugs
    ]
    if not links:
        return ""
    return ('<p class="text-xs text-gray-500 mt-3">Current stock and prices: '
            + ", ".join(links) + ".</p>")


def _sources_html(fam: dict) -> str:
    srcs = fam.get("sources") or []
    if not srcs:
        return ""
    items = "".join(
        f'<li><a href="{url}" target="_blank" rel="noopener" class="text-green-700 hover:underline">{title}</a></li>'
        for title, url in srcs
    )
    return ('<details class="mt-3 text-xs text-gray-500">'
            '<summary class="cursor-pointer hover:text-gray-700">Sources and further reading</summary>'
            f'<ul class="list-disc pl-5 mt-1 space-y-0.5">{items}</ul></details>')


def build_family_card(fam: dict, valid_slugs: set, out_dir: Path) -> str:
    label, grade = fam["status"]
    status_badge = grade_badge(grade)
    partners_html = ""
    if fam.get("partners"):
        rows = "".join(
            f'<tr class="border-b border-gray-100 align-top">'
            f'<td class="py-2 pr-4 text-sm font-medium text-gray-800">{_partner_name_html(name, vslug, out_dir)}</td>'
            f'<td class="py-2 text-sm text-gray-600">{note}{grade_badge(g)}</td></tr>'
            for name, vslug, note, g in fam["partners"]
        )
        partners_html = f"""
  <div class="overflow-x-auto rounded-lg border border-gray-200 mb-3">
    <table class="w-full bg-white text-left">
      <tbody>
        {rows}
      </tbody>
    </table>
  </div>"""
    return f"""
<section class="mb-10" id="{fam['key']}">
  <h2 class="text-xl font-bold text-green-900 mb-1">{fam['icon']} {fam['title']}</h2>
  <p class="mb-3"><span class="text-sm font-semibold text-gray-700">{label}</span>{status_badge}</p>
  <p class="text-sm text-gray-600 mb-4">{fam['intro']}</p>
  {partners_html}
  <div class="p-3 bg-gray-50 rounded-lg text-xs text-gray-500 border border-gray-100">{fam['notes']}</div>
  {_species_links_html(fam, valid_slugs)}
  {_sources_html(fam)}
</section>
"""


def build_summary_table() -> str:
    rows = "".join(
        f'<tr class="border-b border-gray-100 align-top hover:bg-gray-50">'
        f'<td class="py-2 px-3 text-sm font-medium text-gray-800">{fruit}</td>'
        f'<td class="py-2 px-3 text-sm text-gray-600">{verdict}{grade_badge(grade)}</td></tr>'
        for fruit, verdict, grade in SUMMARY
    )
    return f"""
<section class="mb-10" id="chart">
  <h2 class="text-xl font-bold text-green-900 mb-3">Pollination Chart: Do You Need Two Trees?</h2>
  <p class="text-gray-600 text-sm mb-4">Check this before you buy a single tree. Getting it wrong can mean years of healthy growth and no fruit.</p>
  <div class="overflow-x-auto rounded-lg border border-gray-200">
    <table class="w-full bg-white text-left">
      <thead class="bg-gray-50 border-b border-gray-200">
        <tr>
          <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Fruit</th>
          <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">What it needs</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100">
        {rows}
      </tbody>
    </table>
  </div>
</section>
"""


def build_how_to_read() -> str:
    legend = "".join(
        f'<li class="flex items-start gap-2">{grade_badge(g)}<span class="text-gray-600">{meaning}</span></li>'
        for g, meaning in [
            ("research-backed", "Supported by peer-reviewed studies or university/government research."),
            ("established-practice", "Broad horticultural consensus, low controversy."),
            ("context-dependent", "True only for certain varieties, climates or conditions."),
        ]
    )
    return f"""
<section class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-8 text-sm">
  <p class="font-semibold text-amber-900 mb-1">How to read this guide</p>
  <p class="text-gray-700 mb-3">Pollination advice is where a lot of fruit-tree buying goes wrong. We grade every claim by how good the evidence is, and note where a rule holds only for certain varieties. The short version is in the chart below; the cards explain each fruit.</p>
  <ul class="space-y-1">
    {legend}
  </ul>
</section>"""


def build_faq_section() -> str:
    items = "".join(
        f'<div class="mb-5"><h3 class="font-semibold text-gray-800 mb-1">{q}</h3>'
        f'<p class="text-sm text-gray-600">{a}</p></div>'
        for q, a in FAQS
    )
    return f"""
<section class="mb-10" id="faq">
  <h2 class="text-xl font-bold text-green-900 mb-4">Frequently Asked Questions</h2>
  {items}
</section>
"""


def build_references_section() -> str:
    if not GENERAL_SOURCES:
        return ""
    items = "".join(
        f'<li><a href="{url}" target="_blank" rel="noopener" class="text-green-700 hover:underline">{title}</a></li>'
        for title, url in GENERAL_SOURCES
    )
    return f"""
<section class="mb-10" id="references">
  <h2 class="text-xl font-bold text-green-900 mb-3">References and Further Reading</h2>
  <p class="text-gray-600 text-sm mb-3">Pollination guidance on this page draws on Australian state agriculture departments, university horticulture extension and established nursery references. Per-fruit sources are on each card above.</p>
  <ul class="list-disc pl-5 text-sm text-gray-600 space-y-1">
    {items}
  </ul>
</section>
"""


def build_related_guides() -> str:
    return """
<section class="mb-10" id="related">
  <h2 class="text-xl font-bold text-green-900 mb-3">Related Guides</h2>
  <ul class="text-sm space-y-1 list-disc pl-5">
    <li><a href="/companion-planting-guide.html" class="text-green-700 hover:underline">Companion planting guide for fruit trees</a> (what to grow alongside, plus a pollinator quick reference)</li>
    <li><a href="/when-to-plant.html" class="text-green-700 hover:underline">When to plant fruit trees in Australia</a> (planting calendar by climate zone)</li>
    <li><a href="/species/" class="text-green-700 hover:underline">Browse all tracked species</a> (in-stock counts, prices, restock alerts)</li>
  </ul>
</section>
"""


def build_faq_jsonld() -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in FAQS
        ],
    }
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"


def build_page(out_dir: Path) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    valid_slugs = load_valid_species_slugs()
    family_sections = "".join(build_family_card(f, valid_slugs, out_dir) for f in FAMILIES)

    head = render_head(
        title="Fruit Tree Pollination Guide Australia: Which Trees Need a Partner | treestock.com.au",
        description="Which fruit trees need a pollination partner and which crop alone. Apple, pear, cherry, plum, avocado Type A and B, kiwifruit and more, with an Australian pollination chart and evidence grades.",
        canonical_url="https://treestock.com.au/fruit-tree-pollination-guide.html",
        og_title="Fruit Tree Pollination Guide for Australia",
        og_description="Do you need two trees? An evidence-graded pollination chart for apple, pear, cherry, plum, avocado, kiwifruit and the self-fertile fruits, for Australian gardens.",
        og_type="article",
        og_image="https://treestock.com.au/og-image.png",
        extra_head=build_faq_jsonld(),
    )
    header = render_header()
    breadcrumb = render_breadcrumb([("Home", "/"), ("Pollination Guide", "")])
    footer = render_footer()

    return render_template(
        "pollination_guide_page.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        today=today,
        how_to_read=build_how_to_read(),
        summary_table=build_summary_table(),
        family_sections=family_sections,
        faq_section=build_faq_section(),
        references_section=build_references_section(),
        related_guides=build_related_guides(),
        treesmith_promo=render_treesmith_promo("species"),
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: build_pollination_guide.py /path/to/output/")
        sys.exit(1)
    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)
    html = build_page(output_dir)
    out_file = output_dir / "fruit-tree-pollination-guide.html"
    out_file.write_text(html)
    print(f"Written: {out_file} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
