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
from functools import lru_cache

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
    "pest spray", "plant food", "plant label", "planter bag", "poss-off",
    # "postage" was removed 2026-08-20. Every one of its 13 live matches was a
    # real fruit tree: heaven-on-earth suffixes citrus titles with "QLD
    # POSTAGE ONLY" as a shipping note, so the keyword had a 100%
    # false-positive rate and cost us 13 citrus trees (Blood Orange Cara Cara,
    # two Finger Limes, Imperial Mandarin, Key Lime, Meyer Lemon, Lemonade,
    # Kaffir Lime, Tahitian Lime, Ponkan Mandarin, two Pomelos, Tangelo
    # Minneola). Word boundaries do NOT save it, because "postage" is a whole
    # word there. "shipping", "delivery", "delivery charge" and "freight" stay
    # and still catch an actual postage line item.
    "potting mix", "powerfeed", "pruning", "resource book", "richgro",
    "rubber hook", "saucer", "searles", "searles liquid", "seasol",
    "seaweed", "seaweed solution", "secateur", "secateurs", "sharp shooter",
    "shipping", "soil", "soil mix", "spray", "stake", "staking kit",
    "starter kit", "support", "terracotta", "ticket", "tools",
    "dwarfing tool", "tree guard",
    "tree sealant", "tree stake",
    # "wire" removed 2026-08-20 for the same reason: 4 live matches, 4 real
    # plants (Barbed Wire Grass, Wire Netting Bush x2, Wire Vine), 0 junk.
    # They are ornamentals, so the per-nursery fruit filter is what actually
    # keeps them off the site; the junk gate was taking the credit for a
    # decision it was getting right by accident.
    "tree tube", "weed killer", "white oil", "workshop",
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

# "seed" in a title does not always mean the product IS seed. It is also used
# to say how a plant was raised, to name a trait, or as part of the plant's own
# name, and the bare \bseeds?\b test deleted all three. Live casualties on
# 2026-08-20, six of them:
#
#   Lychee Lin San Sue (Small Seed)      a real tree. Small-seed is a PRIZED
#                                        lychee trait, which is why it is in
#                                        the title at all.
#   Pomegranate Shepards Special Organic -60-80cm (Option For Seed Grown Also)
#                                        a real tree, with a seed-grown option
#   Grass Tree seed grown (Xanthorrhoea latifolia)
#   Seed of Heaven                       a plant (Aframomum)
#   Seed of Heaven - Aframomum sp uganda
#   Seed of Paradise Ginger
#
# Verified against all 106 live titles that match _SEED_RE: this keeps exactly
# those six and leaves the other 100 (guildford 56, forever-seeds 42, and four
# others) classified as packets.
_NOT_A_SEED_PACKET_RE = re.compile(
    r"\bseed[\s-]*grown\b"
    r"|\bgrown\s+from\s+seed\b"
    r"|\bfrom\s+seed\b"
    r"|\bseed[\s-]*raised\b"
    r"|\b(?:small|large|big|no)\s+seed\b"
    r"|\bseed\s+of\b"
)


@lru_cache(maxsize=8)
def _keyword_pattern(keywords: frozenset[str]) -> re.Pattern:
    """One alternation regex per keyword set, matched on word boundaries with
    an optional trailing plural.

    The boundaries are the point. Plain substring matching junked real plants
    whose names merely contain a keyword, and the precedent was already in the
    tree: bare "tool" was removed once because it ate Daleys' "Strawberry -
    Toolangi Choice". That fix was never generalised, so the same class of
    casualty was still live on 2026-08-20:

        Grevillea 'Ellabella' - Large            "ellabella" contains "label"
        Peperomia Red Stem (Peperomia glabella)  "glabella"  contains "label"
        Black Locust Frisia (Robinia pseudoacacia)  contains "acacia"
        Jack Pine (Pinus banksiana)                 contains "banksia"
        Flax Lily Seaspray (Dianella revoluta)      contains "spray"

    The optional plural is NOT decoration. Without it, making the match
    word-aware would have leaked seven real junk products back onto the site,
    because the keywords are singular and the products are not: "bonsai bag"
    stops matching "Bonsai Bags 15 litre", "grow bag" stops matching "Woven
    Planter Grow Bags", "planter bag" stops matching "Planter Bags - 4 Litre
    x 25". Measured on the live catalogue, word-aware alone freed 12 titles of
    which 7 were genuine junk; word-aware plus the plural frees exactly the 5
    real plants above and nothing else.

    Multi-word entries stay phrase matches, which falls out of the same
    pattern: "gift card" and "potting mix" match as written.
    """
    alternation = "|".join(re.escape(kw) for kw in sorted(keywords, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + alternation + r")s?(?!\w)")


def matches_keyword(title: str, keywords) -> bool:
    """True if the title contains any of `keywords` as a whole word or phrase.

    Shared by both junk-filtering sites. build-dashboard.py inlined its own
    `any(kw in title_lower for kw in ...)` and never called is_real_product at
    all, so fixing only this module left the homepage dropping the same
    products. It takes the keyword set as an argument because the two sites
    legitimately use different sets: the dashboard exempts native keywords
    (DEC-200 P1.5) and the variety/species/compare surfaces do not.
    """
    return bool(_keyword_pattern(frozenset(keywords)).search(title.lower()))


def is_junk_keyword(title: str) -> bool:
    """True if the title contains a non-plant junk keyword (whole word or
    phrase, not a substring)."""
    return matches_keyword(title, NON_PLANT_KEYWORDS)


def is_seed_packet(title: str) -> bool:
    """True if the title is a seed packet (not a nursery-grown tree).

    'seedling' and 'seedless' are explicitly NOT seed packets, and neither is
    a title that only uses the word to describe how a plant was raised
    ("Seed Grown Mango"), to name a trait ("Lychee ... (Small Seed)"), or as
    part of the plant's own name ("Seed of Heaven"). See
    _NOT_A_SEED_PACKET_RE.
    """
    tl = title.lower()
    if not _SEED_RE.search(tl):
        return False
    if "seedling" in tl or "seedless" in tl:
        return False
    return not _NOT_A_SEED_PACKET_RE.search(tl)


def is_real_product(title: str) -> bool:
    """True if the title looks like a real tree/plant for sale: not junk, not a
    seed packet. Bundles the keyword filter + seed exclusion used by the
    variety/compare builders."""
    return not is_junk_keyword(title) and not is_seed_packet(title)
