"""
Product classification: the "is this a real tree/plant, or junk?" filter.

NON_PLANT_KEYWORDS was copy-pasted into 10 files as SIX different lists (15-78
keywords) that had drifted badly -- the worst "updated in one place, not the
others" case in the codebase. This is the single canonical list: the union of
all ten copies, vetted against the real product catalogue to remove substring
false-positives that were wrongly dropping real fruit:

  - 'pot'   matched 'Sa(pot)e' and every '400mm Pot' size -> 119 fruit titles
            (build_species_trends carried 'pot' and was hiding all sapotes etc.)
  - 'bag'   matched '45Ltr (Bag)' on a real "Fraser Island Apple"
  - 'class' matched '(Class)ic' (e.g. 'Mulberry Black Classic')
  - 'tool'  matched '(Tool)angi' (Daleys "Strawberry - Toolangi Choice");
            now 'tools' + 'dwarfing tool' (the one real tool product)

Since DEC-200 (category expansion) the list is split by what the keyword
actually names:

  - TRUE_JUNK: not a plant in any category (fertiliser, gift cards, tools,
    books, chemicals, freight). Junk forever.
  - CATEGORY_KEYWORDS: real plants this fruit-stock site deliberately filters
    (banksia, eucalyptus, cordyline, ...), each mapped to the category it
    hints at ("native", "ornamental", "vegetable"). The categorize ladder
    also uses these as its lowest-confidence signal.

NON_PLANT_KEYWORDS is DERIVED: TRUE_JUNK plus the keywords of categories not
in taxonomy.ENABLED_CATEGORIES. Today only "fruit" is enabled, so the derived
set equals the old hand-maintained list and behaviour is unchanged. Enabling a
category (e.g. "native") automatically stops junking its plants and routes
them to classification instead.

is_real_product() bundles the keyword filter with the seed-packet exclusion
that the variety/compare builders apply. Consumers that only need the list
import NON_PLANT_KEYWORDS directly (substring-matched against a lowercased
title).
"""
from __future__ import annotations

import re

from .taxonomy import ENABLED_CATEGORIES

# Non-plant junk: consumables, hardware, merch, services. Junk in every
# category, forever. Keep sorted for reviewability.
TRUE_JUNK = frozenset({
    "banana bunch cover", "biochar", "bonsai bag", "book", "budding tape",
    "catalogue", "combo pack", "concentrate spray", "connector", "delivery",
    "delivery charge", "dynamic lifter", "eco oil", "eco-oil", "ecofend",
    "end stop terminator", "exclusion net", "fertiliser", "fertilizer",
    "fish emulsion", "freight",
    "fungicide", "garden gloves", "gift card", "gift certificate",
    "gift voucher", "glove", "gloves", "grafting knife", "grafting tape",
    "gropod", "grow bag", "guide", "herbicide", "insect control",
    "insect killer", "insecticide", "irrigation", "label", "labels",
    "mushroom kit", "naturalure", "neem oil", "orchard kit", "osmocote",
    "pest spray", "plant label", "planter bag", "poss-off", "postage",
    "potting mix", "powerfeed", "pruning", "resource book", "richgro",
    "rubber hook", "saucer", "searles", "searles liquid", "seasol",
    "seaweed", "seaweed solution", "secateur", "secateurs", "sharp shooter",
    "shipping", "soil", "soil mix", "spray", "stake", "staking kit",
    "starter kit", "support", "terracotta", "ticket", "tools",
    "dwarfing tool", "tree guard",
    "tree sealant", "tree stake",
    "tree tube", "weed killer", "white oil", "wire", "workshop",
    "worm castings", "yates",
})

# Real plants this fruit-stock site deliberately filters, keyword -> the
# category it hints at. When a category joins taxonomy.ENABLED_CATEGORIES its
# keywords drop out of the derived junk set automatically, and the categorize
# ladder picks them up as its lowest-confidence classification signal.
CATEGORY_KEYWORDS: dict[str, str] = {
    "acacia": "native",
    "allocasuarina": "native",
    "banksia": "native",
    "blackbutt": "native",
    "bottlebrush": "native",
    "brachychiton": "native",
    "brown tamarind": "native",
    "callistemon": "native",
    "eucalyptus": "native",
    "flame tree": "native",
    "flooded gum": "native",
    "forest mat rush": "native",
    "ivory curl": "native",
    "kurrajong": "native",
    "lemon scented gum": "native",
    "lomandra": "native",
    "melaleuca": "native",
    "narrow-leaved ironbark": "native",
    "red bean": "native",
    "river red gum": "native",
    "sheoak": "native",
    "swamp paperbark": "native",
    "swamp turpentine": "native",
    "wattle": "native",
    "white beech": "native",
    "white cedar": "native",
    "cordyline": "ornamental",
    "ornamental": "ornamental",
    "asparagus": "vegetable",
}


def derived_non_plant_keywords(enabled_categories=None) -> frozenset[str]:
    """TRUE_JUNK plus the keywords of categories that are NOT enabled. The
    parameter exists for tests; production uses taxonomy.ENABLED_CATEGORIES."""
    enabled = ENABLED_CATEGORIES if enabled_categories is None else enabled_categories
    return TRUE_JUNK | {
        kw for kw, cat in CATEGORY_KEYWORDS.items() if cat not in enabled
    }


# Canonical junk filter, derived (set-equal to the pre-split list while only
# "fruit" is enabled). Public API: unchanged.
NON_PLANT_KEYWORDS = derived_non_plant_keywords()

_SEED_RE = re.compile(r"\bseeds?\b")


def is_junk_keyword(title: str) -> bool:
    """True if the title contains a non-plant junk keyword (substring match)."""
    tl = title.lower()
    return any(kw in tl for kw in NON_PLANT_KEYWORDS)


def is_seed_packet(title: str) -> bool:
    """True if the title is a seed packet (not a nursery-grown tree). 'seedling'
    and 'seedless' are explicitly NOT seed packets."""
    tl = title.lower()
    return bool(_SEED_RE.search(tl)) and "seedling" not in tl and "seedless" not in tl


def is_real_product(title: str) -> bool:
    """True if the title looks like a real tree/plant for sale: not junk, not a
    seed packet. Bundles the keyword filter + seed exclusion used by the
    variety/compare builders."""
    return not is_junk_keyword(title) and not is_seed_packet(title)
