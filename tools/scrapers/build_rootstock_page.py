#!/usr/bin/env python3
"""
Build the fruit-tree rootstock guide (/rootstock.html) for treestock.com.au (DAL-209).

Targets long-tail grafter/collector questions that are genuinely sparse for Australia:
'apple rootstock dwarfing chart australia', 'MM106 vs M26', 'grow peach rootstock from
seed', 'plum rootstock from cuttings', 'where to buy fruit tree rootstock australia',
'get rootstock into WA quarantine'. This deepens the grafter moat that is treestock's
core audience.

Architecture (Benedict, DAL-209): a hub page rendered from a per-species JSON layer
(rootstock_guides.py + rootstock_guides/<slug>.json), mirroring growing_guides and
variety_descriptions. Static, curated, cited. NOT a live tracker: rootstock is sold
wholesale/seasonal/bare-root by phone and order form, so there is nothing to scrape.

The per-species content (rootstock tables + grow-your-own) comes from the JSON layer.
The cross-species pieces (what rootstock is, where to buy it in Australia, WA/NT/TAS
quarantine, page FAQs) are curated here, cited inline with the shared stocklib.citations
helper. Species links are validated against the taxonomy so they cannot 404.

No em dashes or en dashes anywhere (treestock copy rule); tests guard this.

Usage:
    python3 build_rootstock_page.py /path/to/output/
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer, render_treesmith_promo

from stocklib.citations import inline_cite
from stocklib.taxonomy import enabled_species

import rootstock_guides as rg

# Species covered on the page, in order (stone fruit, then pome, then citrus). Add a
# species by dropping in a JSON file (rootstock_guides/<slug>.json) and adding its slug
# here. Note: the shared citrus guide is keyed to the "lemon" slug (common_name "Citrus")
# because "citrus" is not itself an enabled species; only the lemon species page deep-links.
SPECIES = ["peach", "plum", "apricot", "cherry", "apple", "pear", "lemon"]

# Curated cross-species citations (label, url) for the buying and quarantine sections.
CITE_DALEYS = ("Daleys rootstock", "https://www.daleysfruit.com.au/Rootstock.htm")
CITE_HERITAGE = ("Heritage Fruit Trees", "https://www.heritagefruittrees.com.au/rootstocks/")
CITE_OLEA = ("Olea Nurseries WA", "https://www.oleanurseries.com.au/CommercialGrowers/rootstock")
CITE_FLEMINGS = ("Fleming's Nurseries", "https://www.flemings.com.au/where-to-buy")
CITE_DPIRD = ("Quarantine WA", "https://www.dpird.wa.gov.au/businesses/biosecurity/importing-and-exporting-quarantine-wa/importing-plants-and-plant-products/")
CITE_ICA62 = ("WA ICA-62", "https://www.interstatequarantine.org.au/wp-content/uploads/2017/09/WA-ICA-62.pdf")
CITE_INTERSTATE = ("Interstate Quarantine", "https://interstatequarantine.org.au/producers/moving-plant-goods/")
CITE_YALCA = ("Yalca Fruit Trees", "https://www.yalcafruittrees.com.au/")

# Page-level references (per-species sources sit collapsed under each section above).
REFERENCES = [
    ("Daleys Fruit Tree Nursery: rootstocks for grafting (retail, Australia)", "https://www.daleysfruit.com.au/Rootstock.htm"),
    ("Heritage Fruit Trees: apple and pear rootstocks (retail, Australia)", "https://www.heritagefruittrees.com.au/rootstocks/"),
    ("Olea Nurseries, Manjimup WA: commercial rootstock range (wholesale)", "https://www.oleanurseries.com.au/CommercialGrowers/rootstock"),
    ("DPIRD (Quarantine WA): importing plants and plant products into WA", "https://www.dpird.wa.gov.au/businesses/biosecurity/importing-and-exporting-quarantine-wa/importing-plants-and-plant-products/"),
    ("Interstate Quarantine WA ICA-62: treatment and inspection of carrier nursery stock", "https://www.interstatequarantine.org.au/wp-content/uploads/2017/09/WA-ICA-62.pdf"),
    ("Australian Interstate Quarantine: moving plant goods between states", "https://interstatequarantine.org.au/producers/moving-plant-goods/"),
]

# Page-level FAQs (buying + quarantine). Per-species FAQs are pulled from the JSON layer.
PAGE_FAQS = [
    (
        "Where can I buy fruit tree rootstock in Australia?",
        "Two nurseries sell rootstock direct to the public: Daleys Fruit Tree Nursery in NSW sells apple, plum and peach rootstock as single potted plants, and Heritage Fruit Trees sells apple and pear rootstock in bundles of three as dormant bare-root plants for winter grafting. Most other rootstock is wholesale, sold to commercial growers and garden centres only. Olea Nurseries in Manjimup WA carries the full deciduous range (apple, plum, peach) but to commercial growers only, and Fleming's does not sell to the public at all. Rootstock is a winter, bare-root product, usually ordered by phone, email or an order form rather than bought online day to day.",
    ),
    (
        "Can I get rootstock or a fruit tree into Western Australia?",
        "It is restricted, not impossible. To enter WA a plant must be listed as permitted on the Western Australian Organism List, and in most cases it must be chemically treated and travel with plant health certification from the exporting state. Private importers can apply to bring in fewer than 20 plants that skip some treatments, but they must be washed free of all soil and potting mix and inspected on arrival. In quarantine terms rootstock is carrier nursery stock, so it needs a Plant Health Assurance Certificate to cross. This is why many eastern nurseries simply will not post to WA, and to the Northern Territory and Tasmania, which apply their own conditions. A WA grower who wants to avoid interstate quarantine buys from a WA nursery, though the main WA rootstock supplier is wholesale only.",
    ),
]


def load_valid_species_slugs() -> set:
    try:
        return {s["slug"] for s in enabled_species() if s.get("slug")}
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return set()


def build_intro_box(valid_slugs: set) -> str:
    """Framing box: what rootstock is, why it matters, and jump links to each species."""
    jumps = "".join(
        f'<a href="#{s}" class="text-green-700 hover:underline">{rg.common_name(s)}</a>'
        for s in SPECIES if rg.has_guide(s)
    )
    jump_line = " &middot; ".join(
        f'<a href="#{s}" class="text-green-700 hover:underline">{rg.common_name(s)} rootstock</a>'
        for s in SPECIES if rg.has_guide(s)
    )
    live = _species_links_line(valid_slugs)
    return f"""
<section class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-8 text-sm">
  <p class="font-semibold text-amber-900 mb-1">What a rootstock is, and why it matters</p>
  <p class="text-gray-700 mb-2">Nearly every fruit tree you buy is two plants in one: a named fruiting variety (the scion) grafted onto a separate root system (the rootstock){inline_cite(*CITE_DALEYS)}. The rootstock is not just roots. It sets how big the tree grows, how soon it fruits, and how well it stands up to your soil, drainage, pests and diseases. Choosing the rootstock is half of choosing the tree, and for a grafter it is the half you get to decide.</p>
  <p class="text-gray-700">On this page: {jump_line}, plus where to buy rootstock in Australia and how to get it into the quarantine states.</p>
  {live}
</section>"""


def _species_links_line(valid_slugs: set) -> str:
    links = [
        f'<a href="/species/{s}.html" class="text-green-700 hover:underline">{rg.common_name(s).lower()}</a>'
        for s in SPECIES if s in valid_slugs
    ]
    if not links:
        return ""
    return ('<p class="text-xs text-gray-500 mt-3">Track live stock and prices for the grafted trees: '
            + ", ".join(links) + ".</p>")


def build_buying_section() -> str:
    """Cross-species: where to buy rootstock, how it is sold, and the quarantine states.

    Framed as restriction warnings (no 'ships to WA' positivity), per the house rule.
    """
    return f"""
<section class="mb-10" id="buying">
  <h2 class="text-xl font-bold text-green-900 mb-3">Where to buy rootstock in Australia</h2>
  <p class="text-sm text-gray-600 mb-4">Rootstock is a niche, seasonal product, so the retail options are few. Daleys Fruit Tree Nursery in NSW sells apple, plum and peach rootstock as single potted plants{inline_cite(*CITE_DALEYS)}, and Heritage Fruit Trees sells apple and pear rootstock in bundles of three, as dormant bare-root plants for winter grafting or late-summer budding{inline_cite(*CITE_HERITAGE)}. Beyond those, most rootstock moves through the trade: Olea Nurseries in Manjimup, WA grows the full deciduous range (apple, plum, peach, and more) but supplies commercial growers and garden centres only{inline_cite(*CITE_OLEA)}, and Fleming's is wholesale and does not sell to the public{inline_cite(*CITE_FLEMINGS)}.</p>

  <h3 class="text-lg font-semibold text-gray-800 mt-6 mb-2">How rootstock is sold (and why we do not track it)</h3>
  <p class="text-sm text-gray-600 mb-4">Rootstock is sold as dormant bare-root whips or liners in winter, often in fixed bundles or wholesale minimums, and usually ordered by phone, email or an order form rather than bought online. Unit sizes are inconsistent between sellers (single pots at Daleys, bundles of three at Heritage), and much of the supply is commercial-only. There is no continuously priced retail listing to compare day to day, which is exactly why treestock tracks finished, grafted trees and keeps rootstock as a maintained reference page instead of a live tracker{inline_cite(*CITE_HERITAGE)}.</p>

  <h3 class="text-lg font-semibold text-gray-800 mt-6 mb-2">Getting rootstock into WA, NT and Tasmania</h3>
  <p class="text-sm text-gray-600 mb-4">Every state and territory sets its own plant-import quarantine conditions{inline_cite(*CITE_INTERSTATE)}, and Western Australia, the Northern Territory and Tasmania are the hard ones. To enter WA, a plant must be listed as permitted on the Western Australian Organism List, and in most cases it has to be chemically treated and certified by the exporting state before it crosses{inline_cite(*CITE_DPIRD)}. Private importers can apply to bring in fewer than 20 plants that skip some treatments, but only washed free of all soil and potting mix and inspected on arrival{inline_cite(*CITE_DPIRD)}. In quarantine terms rootstock counts as carrier nursery stock, so it can only move interstate under treatment, inspection and a Plant Health Assurance Certificate{inline_cite(*CITE_ICA62)}. This is why many eastern nurseries simply will not post to WA, SA or Tasmania: one Victorian bare-root nursery ships Australia-wide except South Australia, WA and Tasmania, citing quarantine difficulties{inline_cite(*CITE_YALCA)}. For a WA grower, the way around interstate quarantine is to buy from a WA nursery, though the main WA rootstock supplier is wholesale only{inline_cite(*CITE_OLEA)}.</p>
</section>
"""


def build_faq_section(faqs) -> str:
    items = "".join(
        f'<div class="mb-5"><h3 class="font-semibold text-gray-800 mb-1">{q}</h3>'
        f'<p class="text-sm text-gray-600">{a}</p></div>'
        for q, a in faqs
    )
    return f"""
<section class="mb-10" id="faq">
  <h2 class="text-xl font-bold text-green-900 mb-3">Frequently Asked Questions</h2>
  {items}
</section>
"""


def build_faq_jsonld(faqs) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faqs
        ],
    }
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"


def build_references_section() -> str:
    items = "".join(
        f'<li><a href="{url}" target="_blank" rel="noopener nofollow" class="text-green-700 hover:underline">{title}</a></li>'
        for title, url in REFERENCES
    )
    return f"""
<section class="mb-10" id="references">
  <h2 class="text-xl font-bold text-green-900 mb-3">References and Further Reading</h2>
  <p class="text-gray-600 text-sm mb-3">Rootstock guidance on this page draws on horticultural research, university extension, the Royal Horticultural Society and Australian nursery references. Per-species sources are collapsed under each section above.</p>
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
    <li><a href="/fruit-tree-pollination-guide.html" class="text-green-700 hover:underline">Fruit tree pollination guide</a> (which trees need a partner to fruit)</li>
    <li><a href="/bare-root.html" class="text-green-700 hover:underline">Bare root season</a> (when dormant, grafted trees go on sale)</li>
    <li><a href="/when-to-plant.html" class="text-green-700 hover:underline">When to plant fruit trees in Australia</a> (planting calendar by climate)</li>
    <li><a href="/species/" class="text-green-700 hover:underline">Browse all tracked species</a> (in-stock counts, prices, restock alerts)</li>
  </ul>
</section>
"""


def build_page(out_dir: Path) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    valid_slugs = load_valid_species_slugs()

    species_sections = "".join(
        rg.render_species_section(s) for s in SPECIES if rg.has_guide(s)
    )

    # One FAQPage for the whole page: page-level questions first, then per-species.
    faqs = list(PAGE_FAQS)
    for s in SPECIES:
        faqs.extend(rg.get_faqs(s))

    head = render_head(
        title="Fruit Tree Rootstock Guide Australia: Types, Suppliers, Grow Your Own | treestock.com.au",
        description="Fruit tree rootstock explained for Australia. Peach, plum and apple rootstock types with vigour, soil and disease traits, an apple dwarfing guide, where to buy rootstock, WA quarantine rules, and growing your own from seed and cuttings.",
        canonical_url="https://treestock.com.au/rootstock.html",
        og_title="Fruit Tree Rootstock Guide for Australia",
        og_description="Peach, plum and apple rootstock types, an apple dwarfing chart, where to buy rootstock in Australia, WA quarantine, and how to grow your own.",
        og_type="article",
        og_image="https://treestock.com.au/og-image.png",
        extra_head=build_faq_jsonld(faqs),
    )
    header = render_header(active_path="/rootstock.html")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Rootstock Guide", "")])
    footer = render_footer()

    return render_template(
        "rootstock_page.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        today=today,
        intro_box=build_intro_box(valid_slugs),
        species_sections=species_sections,
        buying_section=build_buying_section(),
        faq_section=build_faq_section(faqs),
        references_section=build_references_section(),
        related_guides=build_related_guides(),
        treesmith_promo=render_treesmith_promo("species"),
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: build_rootstock_page.py /path/to/output/")
        sys.exit(1)
    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)
    html = build_page(output_dir)
    out_file = output_dir / "rootstock.html"
    out_file.write_text(html)
    print(f"Written: {out_file} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
