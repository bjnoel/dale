#!/usr/bin/env python3
"""
Build companion planting guide page for treestock.com.au.

Targets keywords: 'companion plants for citrus', 'companion planting mango',
'fruit tree pollinator requirements', 'what to plant with avocado', etc.

Usage:
    python3 build_companion_guide.py /path/to/output/
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from treestock_layout import render_head, render_header, render_breadcrumb, render_footer


# ----- Content Data -----

SPECIES_COMPANIONS = [
    {
        "name": "Citrus (Lemon, Orange, Mandarin, Lime)",
        "slug": "citrus",
        "icon": "🍋",
        "good": [
            ("Comfrey", "Deep roots mine nutrients from subsoil. Leaves make excellent mulch and liquid fertiliser. Plant 1m away to avoid root competition."),
            ("Nasturtium", "Repels aphids and whitefly. Edible flowers and leaves. Self-sows readily as a living groundcover."),
            ("Lavender", "Attracts beneficial insects including bees. Deters some pests. Suits the same Mediterranean climate as citrus."),
            ("Borage", "Attracts bees and predatory wasps. Said to improve citrus flavour. Easy to grow from seed."),
            ("Dill and fennel (NOT near citrus)", "Wait — see avoidances below. Fennel is allelopathic; dill is fine in moderation."),
        ],
        "avoid": ["Fennel (allelopathic — stunts growth)", "Other large citrus trees too close (root competition)", "Grass directly under canopy (competes for nitrogen)"],
        "pollinator": "Most citrus is self-fertile. A single tree will fruit. Cross-pollination from multiple varieties improves yield. Mandarins and tangelos benefit most from a pollinator partner.",
        "notes": "Citrus prefers well-drained, slightly acidic soil. Companions that fix nitrogen (like clover groundcover) reduce fertiliser needs.",
    },
    {
        "name": "Mango",
        "slug": "mango",
        "icon": "🥭",
        "good": [
            ("Turmeric", "Grown as a companion, turmeric suppresses weeds and the rhizomes are harvested separately. Suits the same tropical conditions."),
            ("Vetiver grass", "Deep-rooted grass that prevents erosion on slopes, doesn't compete heavily with tree roots, tolerates the same heat."),
            ("Sweet potato", "Low groundcover that suppresses weeds around young mangoes. Edible and easy to remove when no longer needed."),
            ("Lemongrass", "Repels some insects, tolerates tropical heat and humidity. Good border plant around mango groves."),
            ("Papaya", "Fast-growing companion that provides temporary shade for young mangoes while establishing. Harvest within 2 years."),
        ],
        "avoid": ["Avocado (deep root competition at maturity)", "Other large trees within 8m (canopy competition)", "Lawn grass under canopy (nitrogen depletion)"],
        "pollinator": "Most mango varieties are not fully self-fertile. Two trees of different varieties significantly improve yield. Bowen (Kensington Pride) is more self-fertile than most. Honey Golds and B90 produce better with a cross-pollinator nearby. Bees are the primary pollinator.",
        "notes": "Mango trees are large at maturity (6-10m). Allow plenty of space. Companion plants work best at the drip line, not under the canopy.",
    },
    {
        "name": "Avocado",
        "slug": "avocado",
        "icon": "🥑",
        "good": [
            ("Comfrey", "Excellent nutrient accumulator. Mines potassium, calcium, and phosphorus from deep soil layers. Mulch leaves around the drip line."),
            ("Passionfruit (on a fence)", "Vertical grower that doesn't compete at root level. Provides additional fruit from a small footprint."),
            ("Citrus", "Compatible root systems, similar water and fertility needs. Plant at least 5m apart at maturity."),
            ("Herbs (basil, chives, parsley)", "Aromatic herbs near avocado deter some pests and attract pollinators without competing for water."),
            ("Banana (short-term)", "Provides wind protection and humidity for young avocados in hot climates. Remove as avocado matures."),
        ],
        "avoid": ["Fennel", "Black walnut (juglone toxin)", "Grass or lawn directly under canopy", "Heavy nitrogen fixers (encourage vegetative growth over fruiting)"],
        "pollinator": "Avocados have an unusual flowering pattern (Type A vs Type B). Type A flowers open as female in the morning and male in the afternoon; Type B flowers open as female in the afternoon and male the next morning. Planting one A and one B variety dramatically improves set. Common pairings: Hass (A) + Shepard (B) or Hass (A) + Fuerte (B).",
        "notes": "Avocados are highly sensitive to root rot (Phytophthora). Companions that keep mulch thick and soil well-aerated are most beneficial.",
    },
    {
        "name": "Fig",
        "slug": "fig",
        "icon": "🫐",
        "good": [
            ("Rue", "Traditional companion for figs. Said to deter some pest insects. Has strong scent."),
            ("Marigold", "Deters nematodes in the soil, which can stress fig roots. French marigolds are most effective."),
            ("Comfrey", "Mines nutrients for the hungry fig. Tolerates partial shade under the canopy."),
            ("Strawberry", "Low groundcover that thrives in the dappled shade under figs in warm climates. Edible bonus."),
        ],
        "avoid": ["Fennel", "Other large trees within 4m (root competition is aggressive for figs)"],
        "pollinator": "Most commercial fig varieties grown in Australia (Brown Turkey, Black Genoa, White Adriatic) are parthenocarpic — they set fruit without pollination. No companion required for fruit set. The Smyrna fig (traditional dried fig) requires a specific wasp (Blastophaga psenes) not present in Australia — grow the self-fertile types instead.",
        "notes": "Figs have very invasive roots. Keep away from water pipes and house foundations. Companion plants near figs should be chosen for drought tolerance.",
    },
    {
        "name": "Stone Fruit (Peach, Plum, Apricot, Nectarine, Cherry)",
        "slug": "stone-fruit",
        "icon": "🍑",
        "good": [
            ("Garlic and chives", "Repel borers, curl leaf, and aphids. Plant densely around the drip line. Harvest bulbs annually."),
            ("Comfrey", "Provides potassium critical for fruit quality. Mulch leaves around trees 3-4 times per year."),
            ("Yarrow", "Attracts beneficial insects including hoverflies that predate aphids. Hardy and drought-tolerant."),
            ("Borage", "Attracts bees at bloom time, which is critical for stone fruit pollination. Plant nearby in flower by spring."),
            ("Tansy", "Historically used to repel flying insects. Use with caution — toxic to some animals, and spreads readily."),
        ],
        "avoid": ["Potatoes and tomatoes (share some diseases)", "Grass under canopy (competes for water and nutrients during critical spring growth)", "Fennel"],
        "pollinator": "Most peaches and nectarines are self-fertile. Plums, cherries, and apricots often need cross-pollinators. European plums are mostly self-fertile; Japanese plums need a cross-pollinator. Sweet cherries almost always need two different varieties. Check variety details before purchasing.",
        "notes": "Stone fruit blooms early in spring when bees are still establishing. Planting borage and comfrey that flower in late winter ensures bee activity during critical pollination windows.",
    },
    {
        "name": "Apple and Pear",
        "slug": "apple-pear",
        "icon": "🍏",
        "good": [
            ("Chives and garlic", "Apple scab and codling moth deterrent. Allium roots release sulfur compounds into soil."),
            ("Foxglove", "Traditionally grown under apple trees. Provides shelter for beneficial ground beetles."),
            ("Nasturtium", "Groundcover that attracts aphids away from trees (trap crop). Also attracts hoverflies."),
            ("Phacelia", "Excellent bee plant. Flowers in spring just as apples and pears bloom. Sow in autumn for spring flowers."),
            ("Clover (as groundcover)", "Fixes nitrogen, feeds the orchard floor. Low-growing varieties like white clover suit the understory."),
        ],
        "avoid": ["Potatoes and tomatoes (blight risk in wet years)", "Walnut trees (juglone toxin, keep 15m apart)", "Tall grass (harbours codling moth pupae)"],
        "pollinator": "Most apples and pears require cross-pollination. You need two different varieties that bloom at the same time. Crabapple trees are excellent universal pollinators for apples. For pears, Williams and Beurre Bosc are often used together. Check pollinators charts when buying.",
        "notes": "Apples and pears have specific chilling hour requirements. Ensure your chosen varieties suit your climate zone before planting companions.",
    },
    {
        "name": "Tropical Fruits (Lychee, Dragon Fruit, Banana, Longan)",
        "slug": "tropical",
        "icon": "🐉",
        "good": [
            ("Ginger and turmeric", "Thrive in the same humid, warm conditions. Groundlevel plants that don't shade trees. Edible rhizomes as bonus harvest."),
            ("Pawpaw (papaya)", "Fast-growing nurse plant for young tropical trees. Provides humidity and breaks strong winds while permanent trees establish."),
            ("Heliconia", "Provides windbreak and habitat for beneficial insects in tropical gardens. Controlled spread keeps it manageable."),
            ("Sweet potato", "Edible groundcover that suits tropical conditions. Suppresses weeds and retains soil moisture."),
        ],
        "avoid": ["Cold-climate plants (root activity and soil chemistry differ)", "Heavy nitrogen fixers with lychee (can delay fruiting)", "Competing tall trees"],
        "pollinator": "Lychee and longan are bee-pollinated. Dragon fruit flowers open only at night and are pollinated by moths and bats. Some dragon fruit varieties are self-fertile; others require two different varieties. Bananas do not require pollination — they fruit parthenocarpically.",
        "notes": "Tropical fruit trees in subtropical or temperate climates need wind protection. Dense companion plantings on the southern side (in Australia) reduce frost and wind exposure.",
    },
]

AVOID_ALL = [
    ("Fennel (Foeniculum vulgare)", "Highly allelopathic — releases chemicals that stunt many fruit trees. Keep at least 10m away from any orchard."),
    ("Black walnut (Juglans nigra)", "Produces juglone, a chemical toxic to many species including apple, pear, and most stone fruit. Not commonly grown in Australia but worth knowing."),
    ("Lawn grass (directly under canopy)", "Competes for nitrogen and water at the critical root zone. Keep a grass-free mulched circle at least 1m in diameter under all fruit trees."),
    ("Brassicas (long-term)", "Short-term companions are fine, but brassica roots harbour club root disease which can persist in soil."),
]

NITROGEN_FIXERS = [
    ("White clover", "Best groundcover for orchard floors. Low-growing, bee-attracting, frost-hardy."),
    ("Tagasaste (tree lucerne)", "Fast-growing nitrogen-fixing tree. Can be planted as a windbreak and slashed for mulch. Suits temperate climates."),
    ("Pigeon pea", "Tropical and subtropical nitrogen fixer. Deep taproot mines phosphorus. Short-lived (3-5 years) so replant regularly."),
    ("Comfrey (Bocking 14)", "Not a legume but mines nutrients from deep soil. Sterile variety won't spread. The single most useful companion for fruit trees."),
]

POLLINATOR_SUMMARY = [
    ("Mango", "Most need cross-pollinator for best yield. Bowen is most self-fertile."),
    ("Avocado", "Plant one Type A + one Type B variety for best results."),
    ("Apple", "Almost all need cross-pollinator. Crabapple works as universal partner."),
    ("Pear", "Most need cross-pollinator. Match bloom times."),
    ("Sweet cherry", "Almost all need cross-pollinator."),
    ("Japanese plum", "Needs cross-pollinator."),
    ("European plum", "Mostly self-fertile; cross-pollinator improves yield."),
    ("Fig", "Most Australian commercial varieties are self-fertile."),
    ("Citrus", "All self-fertile; cross-pollination improves yield."),
    ("Peach / Nectarine", "Self-fertile."),
    ("Apricot", "Mostly self-fertile; some varieties benefit from cross-pollinator."),
    ("Lychee / Longan", "Self-fertile but cross-pollination improves set."),
    ("Dragon fruit", "Varies by variety — check before buying."),
    ("Banana", "No pollination required."),
]

FAQS = [
    (
        "What is the best companion plant for all fruit trees?",
        "Comfrey (Bocking 14 sterile variety) is widely considered the single most useful companion for fruit trees. It mines nutrients from deep soil, provides excellent mulch, and doesn't spread invasively. Plant 1-2 comfrey plants per tree at the drip line."
    ),
    (
        "Do I need two fruit trees to get fruit?",
        "It depends on the species and variety. Most citrus, peach, nectarine, fig, and banana are self-fertile. Apples, pears, sweet cherries, and avocados almost always need two different varieties. Check the pollinator requirements for your specific variety before purchasing."
    ),
    (
        "Can I grow companion plants under a fruit tree?",
        "Yes, but avoid grass and fennel. The best understory plants are comfrey, nasturtium, strawberry, or white clover. Keep a clear mulched circle immediately around the trunk to prevent collar rot and pest harbourage."
    ),
    (
        "Why is fennel bad near fruit trees?",
        "Fennel produces allelopathic chemicals from its roots that inhibit the growth of many plants, including most fruit trees. It's one of the few plants that is genuinely harmful as a companion — not just neutral. Keep fennel at least 10m from your orchard."
    ),
    (
        "What can I plant to attract bees to my fruit trees?",
        "Borage, phacelia, white clover, lavender, and comfrey all attract bees and other pollinators. Borage and phacelia are especially useful because they flower heavily in spring, when most fruit trees need pollination. Sow phacelia seeds in autumn for spring flowers."
    ),
    (
        "How close should companion plants be to fruit trees?",
        "Most companion plants work best at the drip line (the outer edge of the canopy) rather than right against the trunk. Keep 30-50cm clear around the trunk with mulch. Tall companions (like tagasaste) should be planted 2-3m from the tree to avoid shading and root competition."
    ),
]


def build_species_card(sp: dict) -> str:
    good_rows = "".join(
        f'<li class="mb-2"><strong class="text-green-800">{name}</strong> — {desc}</li>'
        for name, desc in sp["good"]
        if "Wait" not in name and "NOT" not in name
    )
    avoid_items = " ".join(
        f'<span class="inline-block bg-red-50 border border-red-200 text-red-700 text-xs px-2 py-0.5 rounded-full mr-1 mb-1">{a}</span>'
        for a in sp["avoid"]
    )
    return f"""
<section class="mb-10" id="{sp['slug']}">
  <h2 class="text-xl font-bold text-green-900 mb-3">{sp['icon']} {sp['name']}</h2>

  <div class="grid md:grid-cols-2 gap-6">
    <div>
      <h3 class="font-semibold text-gray-700 mb-2 text-sm uppercase tracking-wide">Good companions</h3>
      <ul class="text-sm text-gray-600 space-y-1 list-none pl-0">
        {good_rows}
      </ul>
    </div>
    <div>
      <h3 class="font-semibold text-gray-700 mb-2 text-sm uppercase tracking-wide">Avoid nearby</h3>
      <div class="mb-4">{avoid_items}</div>

      <h3 class="font-semibold text-gray-700 mb-2 text-sm uppercase tracking-wide">Pollination</h3>
      <p class="text-sm text-gray-600">{sp['pollinator']}</p>
    </div>
  </div>

  <div class="mt-3 p-3 bg-gray-50 rounded-lg text-xs text-gray-500 border border-gray-100">
    {sp['notes']}
  </div>
</section>
"""


def build_avoid_section() -> str:
    rows = "".join(
        f'<div class="flex gap-3 mb-3"><span class="text-red-500 mt-0.5 flex-shrink-0">&#10060;</span><div><strong class="text-gray-800">{name}</strong><p class="text-sm text-gray-600 mt-0.5">{desc}</p></div></div>'
        for name, desc in AVOID_ALL
    )
    return f"""
<section class="mb-10" id="avoid">
  <h2 class="text-xl font-bold text-green-900 mb-4">Plants to Avoid Near Fruit Trees</h2>
  {rows}
</section>
"""


def build_nitrogen_fixers_section() -> str:
    rows = "".join(
        f'<div class="flex gap-3 mb-3"><span class="text-green-500 mt-0.5 flex-shrink-0">&#9679;</span><div><strong class="text-gray-800">{name}</strong><p class="text-sm text-gray-600 mt-0.5">{desc}</p></div></div>'
        for name, desc in NITROGEN_FIXERS
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
  </ul>
</div>
"""


def build_page() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    species_sections = "".join(build_species_card(sp) for sp in SPECIES_COMPANIONS)

    head = render_head(
        title="Companion Planting Guide for Fruit Trees — treestock.com.au",
        description="What to plant near citrus, mango, avocado, fig, stone fruit, apple and pear. Pollinator requirements, nitrogen fixers, and plants to avoid. Australian conditions.",
        canonical_url="https://treestock.com.au/companion-planting-guide.html",
        og_title="Companion Planting for Fruit Trees — Complete Australian Guide",
        og_description="Which plants grow well with citrus, mango, avocado, fig, and stone fruit? Pollinator requirements, soil builders, and plants to avoid near fruit trees.",
    )
    header = render_header()
    breadcrumb = render_breadcrumb([("Home", "/"), ("Companion Planting Guide", "")])
    footer = render_footer()

    return f"""{head}
{header}

<main class="max-w-3xl mx-auto px-4 py-8">
  {breadcrumb}

  <h1 class="text-2xl font-bold text-green-900 mb-2">Companion Planting Guide for Fruit Trees</h1>
  <p class="text-gray-600 text-sm mb-6">What to grow near citrus, mango, avocado, fig, and stone fruit. Includes pollinator requirements and plants to avoid. Updated {today}.</p>

  <div class="prose prose-sm text-gray-700 mb-6 max-w-2xl">
    <p>Companion planting is the practice of growing plants near each other for mutual benefit. For fruit trees, the right companions can attract pollinators, suppress weeds, build soil fertility, deter pests, and reduce water needs. The wrong companions, like fennel planted too close, can actively harm your trees.</p>
    <p>This guide covers the most common fruit trees grown in Australian gardens. Use the pollinator table before buying any single tree, and the avoidance list before planting anything new near your orchard.</p>
  </div>

  {build_toc()}

  {species_sections}

  {build_avoid_section()}

  {build_nitrogen_fixers_section()}

  {build_pollinator_table()}

  {build_faq_section()}

  <!-- CTA -->
  <section class="bg-green-50 border border-green-200 rounded-lg p-6 mt-6">
    <h2 class="text-lg font-semibold text-green-900 mb-2">Find fruit trees for sale in Australia</h2>
    <p class="text-sm text-green-800 mb-4">treestock.com.au tracks stock and prices across 19 nurseries daily. Search by species, filter by your state.</p>
    <div class="flex gap-3 flex-wrap">
      <a href="/" class="inline-block bg-green-700 text-white px-4 py-2 rounded text-sm font-medium hover:bg-green-800">Search all nurseries</a>
      <a href="/species/" class="inline-block bg-white border border-green-300 text-green-700 px-4 py-2 rounded text-sm font-medium hover:bg-green-50">Browse by species</a>
      <a href="/when-to-plant.html" class="inline-block bg-white border border-green-300 text-green-700 px-4 py-2 rounded text-sm font-medium hover:bg-green-50">Planting calendar</a>
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
