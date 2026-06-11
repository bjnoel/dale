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

Native-tree / ornamental keywords (banksia, eucalyptus, callistemon, wattle,
melaleuca, ornamental, ...) are KEPT: this is a fruit-stock site, so flowering
ornamentals and native non-fruit trees are correctly filtered. When the site
later covers more than fruit, that distinction moves to stocklib.taxonomy's
ENABLED_CATEGORIES rather than this junk list.

is_real_product() bundles the keyword filter with the seed-packet exclusion that
the variety/compare builders apply. Consumers that only need the list import
NON_PLANT_KEYWORDS directly (substring-matched against a lowercased title).
"""
from __future__ import annotations

import re

# Canonical junk filter: union of the 10 former copies, minus the three
# substring false-positives (pot/bag/class). Keep sorted for reviewability.
NON_PLANT_KEYWORDS = frozenset({
    "acacia", "allocasuarina", "asparagus", "banana bunch cover", "banksia",
    "biochar", "blackbutt", "bonsai bag", "book", "bottlebrush", "brachychiton",
    "brown tamarind", "budding tape", "callistemon", "catalogue",
    "concentrate spray", "connector", "cordyline", "delivery", "delivery charge",
    "dynamic lifter", "eco oil", "eco-oil", "ecofend", "eucalyptus",
    "exclusion net", "fertiliser",
    "fertilizer", "fish emulsion", "flame tree", "flooded gum", "forest mat rush",
    "freight", "fungicide", "garden gloves", "gift card", "gift certificate",
    "gift voucher", "glove", "gloves", "grafting knife", "grafting tape", "gropod",
    "grow bag", "guide", "herbicide", "insect control", "insect killer",
    "insecticide", "irrigation", "ivory curl", "kurrajong", "label", "labels",
    "lemon scented gum", "lomandra", "melaleuca", "mushroom kit",
    "narrow-leaved ironbark", "naturalure",
    "neem oil", "orchard kit", "ornamental", "osmocote", "pest spray",
    "plant label", "planter bag", "poss-off", "postage", "potting mix",
    "powerfeed", "pruning",
    "red bean", "resource book", "richgro", "river red gum", "rubber hook",
    "saucer", "searles", "searles liquid", "seasol", "seaweed", "seaweed solution",
    "secateur", "secateurs", "sharp shooter", "sheoak", "shipping", "soil",
    "soil mix", "spray", "stake", "staking kit", "support", "swamp paperbark",
    "swamp turpentine",
    "terracotta", "ticket", "tool", "tree guard", "tree stake", "tree tube",
    "wattle", "weed killer", "white beech", "white cedar", "white oil", "wire",
    "workshop", "worm castings", "yates",
})

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
