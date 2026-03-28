"""
Product category taxonomy for beekeeping supplies (two-level hierarchy).

Used by dashboard and digest to classify products into browsable categories.
Categories are matched against product titles, tags, and product_type fields.

Structure: parent categories contain subcategories. Each subcategory has its
own keyword list. categorise_product() returns (parent_slug, sub_slug).
"""

import re

CATEGORIES = [
    # --- Hiveware ---
    {"parent": "hiveware", "parent_name": "Hiveware",
     "slug": "hive-bodies", "name": "Hive Bodies",
     "keywords": ["brood box", "super box", "langstroth", "flow hive",
                   "observation hive", "hive body", "bee box"]},
    {"parent": "hiveware", "parent_name": "Hiveware",
     "slug": "hive-kits", "name": "Hive Kits",
     "keywords": ["hive kit", "starter kit", "beginner kit", "complete hive"]},
    {"parent": "hiveware", "parent_name": "Hiveware",
     "slug": "nuc-boxes", "name": "Nuc Boxes",
     "keywords": ["nuc box", "nuc ", "nucleus"]},
    {"parent": "hiveware", "parent_name": "Hiveware",
     "slug": "lids-covers", "name": "Lids & Covers",
     "keywords": ["hive lid", "hive roof", "migratory lid", "migratory cover",
                   "inner cover", "hive mat", "crown board", "telescoping cover",
                   "ventilated lid", "hive cover"]},
    {"parent": "hiveware", "parent_name": "Hiveware",
     "slug": "bottom-boards", "name": "Bottom Boards",
     "keywords": ["bottom board", "base board", "screened bottom",
                   "drip tray", "varroa board", "mesh floor"]},
    {"parent": "hiveware", "parent_name": "Hiveware",
     "slug": "queen-excluders", "name": "Queen Excluders",
     "keywords": ["queen excluder"]},
    {"parent": "hiveware", "parent_name": "Hiveware",
     "slug": "entrance", "name": "Entrance Gear",
     "keywords": ["entrance reducer", "entrance closer", "entrance closure",
                   "entrance disc", "robber guard", "mouse guard",
                   "entrance block"]},
    {"parent": "hiveware", "parent_name": "Hiveware",
     "slug": "hive-stands", "name": "Hive Stands",
     "keywords": ["hive stand", "hive feet", "hive lifter", "hive strap",
                   "hive clamp", "hive carrier"]},
    {"parent": "hiveware", "parent_name": "Hiveware",
     "slug": "hive-accessories", "name": "Hive Accessories",
     "keywords": ["clearer board", "bee escape", "porter escape",
                   "hive ventilator", "hive spacer"]},

    # --- Frames & Foundation ---
    {"parent": "frames-foundation", "parent_name": "Frames & Foundation",
     "slug": "frames", "name": "Frames",
     "keywords": ["frame", "wired frame", "unwired frame", "manley frame",
                   "hoffman frame", "deep frame", "medium frame", "ideal frame",
                   "wsp frame"]},
    {"parent": "frames-foundation", "parent_name": "Frames & Foundation",
     "slug": "foundation", "name": "Foundation",
     "keywords": ["foundation", "wax sheet", "beeswax foundation",
                   "plastic foundation"]},
    {"parent": "frames-foundation", "parent_name": "Frames & Foundation",
     "slug": "frame-accessories", "name": "Frame Accessories",
     "keywords": ["frame wire", "brass eyelet", "frame grip", "frame spacer",
                   "castellated spacer", "starter strip", "frame nail",
                   "frame pin", "embedding tool"]},

    # --- Feeders ---
    {"parent": "feeders", "parent_name": "Feeders & Feed",
     "slug": "feeders", "name": "Feeders",
     "keywords": ["feeder", "frame feeder", "top feeder", "entrance feeder",
                   "boardman feeder", "rapid feeder"]},
    {"parent": "feeders", "parent_name": "Feeders & Feed",
     "slug": "bee-nutrition", "name": "Bee Nutrition",
     "keywords": ["pollen substitute", "pollen patty", "fondant",
                   "sugar syrup", "bee feed", "pollen supplement",
                   "pollen trap", "propolis trap"]},

    # --- Extractors & Processing ---
    {"parent": "extractors-processing", "parent_name": "Extractors & Processing",
     "slug": "extractors", "name": "Extractors",
     "keywords": ["extractor", "centrifuge", "extraction", "bellows",
                   "bellow"]},
    {"parent": "extractors-processing", "parent_name": "Extractors & Processing",
     "slug": "uncapping", "name": "Uncapping",
     "keywords": ["uncapping knife", "uncapping fork", "uncapping tray",
                   "uncapping roller", "uncapping tank", "uncapping"]},
    {"parent": "extractors-processing", "parent_name": "Extractors & Processing",
     "slug": "honey-handling", "name": "Honey Handling",
     "keywords": ["honey gate", "honey pump", "honey tank", "settling tank",
                   "strainer", "sieve", "filter", "bottling", "honey press",
                   "creaming", "warming", "decrystallizer", "heating"]},
    {"parent": "extractors-processing", "parent_name": "Extractors & Processing",
     "slug": "wax-processing", "name": "Wax Processing",
     "keywords": ["wax melter", "wax press", "solar wax", "wax mould",
                   "beeswax", "rosin", "paraffin", "wax dipping",
                   "candle mould", "candle making", "stearic acid"]},

    # --- Protective Gear ---
    {"parent": "protective-gear", "parent_name": "Protective Gear",
     "slug": "bee-suits", "name": "Bee Suits",
     "keywords": ["bee suit", "beesuit", "full suit", "half suit",
                   "ventilated suit", "cotton suit", "smock", "beekeeping suit"]},
    {"parent": "protective-gear", "parent_name": "Protective Gear",
     "slug": "jackets-veils", "name": "Jackets & Veils",
     "keywords": ["bee jacket", "bee veil", "veil", "hat",
                   "beekeeping jacket", "fencing veil", "round veil"]},
    {"parent": "protective-gear", "parent_name": "Protective Gear",
     "slug": "gloves", "name": "Gloves",
     "keywords": ["bee gloves", "glove", "leather glove",
                   "beekeeping gloves", "goatskin"]},

    # --- Smokers & Tools ---
    {"parent": "smokers-tools", "parent_name": "Smokers & Tools",
     "slug": "smokers", "name": "Smokers",
     "keywords": ["smoker", "smoker fuel", "hessian"]},
    {"parent": "smokers-tools", "parent_name": "Smokers & Tools",
     "slug": "hive-tools", "name": "Hive Tools",
     "keywords": ["hive tool", "j hook", "j-hook", "bee brush",
                   "frame lifter", "frame grip"]},
    {"parent": "smokers-tools", "parent_name": "Smokers & Tools",
     "slug": "queen-rearing", "name": "Queen Rearing",
     "keywords": ["queen cage", "queen catcher", "queen marking",
                   "queen cell", "cell cup", "grafting tool", "grafting frame",
                   "royal jelly", "queen bee", "queen clip", "queen muff",
                   "queen introduction", "queen rearing", "queen breeding",
                   "mating nuc"]},

    # --- Treatments & Health ---
    {"parent": "treatments", "parent_name": "Treatments & Health",
     "slug": "varroa", "name": "Varroa Treatments",
     "keywords": ["varroa", "apistan", "apivar", "oxalic", "formic",
                   "bayvarol", "thymol", "mite treatment", "mite wash",
                   "mite count"]},
    {"parent": "treatments", "parent_name": "Treatments & Health",
     "slug": "shb", "name": "Small Hive Beetle",
     "keywords": ["small hive beetle", "beetle trap", "diatomaceous",
                   "shb trap", "beetle blaster"]},
    {"parent": "treatments", "parent_name": "Treatments & Health",
     "slug": "bee-health", "name": "Bee Health",
     "keywords": ["nosema", "fumagilin", "treatment", "pest control",
                   "diagnostic", "test kit", "alcohol wash"]},

    # --- Containers & Packing ---
    {"parent": "containers-packing", "parent_name": "Containers & Packing",
     "slug": "jars-bottles", "name": "Jars & Bottles",
     "keywords": ["honey jar", "hex jar", "round jar", "squeeze bottle",
                   "jar", "bottle", "container", "honey pail", "bucket",
                   "pail", "honey tub"]},
    {"parent": "containers-packing", "parent_name": "Containers & Packing",
     "slug": "labels-seals", "name": "Labels & Seals",
     "keywords": ["label", "tamper seal", "tamper evident", "sticker",
                   "honey label"]},

    # --- Books & Education ---
    {"parent": "books-education", "parent_name": "Books & Education",
     "slug": "books-education", "name": "Books & Education",
     "keywords": ["book", "guide", "manual", "dvd", "course", "education",
                   "poster"]},
]

# Catch-all keywords: products matching these go to the parent with sub "other"
# These are broad terms checked LAST, only if no subcategory matched.
_PARENT_FALLBACKS = {
    "hiveware": ["hive", "super", "brood", "roof"],
    "frames-foundation": [],
    "feeders": ["pollen", "syrup"],
    "extractors-processing": [],
    "protective-gear": ["suit", "jacket", "mesh", "ventilated"],
    "smokers-tools": [],
    "treatments": ["mite"],
    "containers-packing": ["lid", "cap"],
    "books-education": [],
}


# --- Lookups (built once at import time) ---

PARENTS = {}  # slug -> name (ordered by first appearance)
for cat in CATEGORIES:
    if cat["parent"] not in PARENTS:
        PARENTS[cat["parent"]] = cat["parent_name"]

PARENT_NAMES = dict(PARENTS)
PARENT_NAMES["other"] = "Other"

SUBCATEGORY_NAMES = {cat["slug"]: cat["name"] for cat in CATEGORIES}
SUBCATEGORY_NAMES["other"] = "Other"

PARENT_FOR_SUB = {cat["slug"]: cat["parent"] for cat in CATEGORIES}

# Combined flat lookup: both parent names and subcategory names
CATEGORY_NAMES = {}
CATEGORY_NAMES.update(PARENT_NAMES)
CATEGORY_NAMES.update(SUBCATEGORY_NAMES)

# Subcategories grouped by parent
SUBS_BY_PARENT = {}
for cat in CATEGORIES:
    SUBS_BY_PARENT.setdefault(cat["parent"], []).append(cat)


def categorise_product(title: str, tags: list[str] = None,
                       product_type: str = "") -> tuple[str, str]:
    """Match a product to (parent_slug, subcategory_slug).

    Returns ('other', 'other') if no match.

    Uses word-boundary matching to avoid false positives. Multi-word keywords
    are checked before single-word keywords so more specific terms win.
    """
    title_lower = title.lower()
    combined = title_lower
    if tags:
        combined += " " + " ".join(t.lower() for t in tags)
    if product_type:
        combined += " " + product_type.lower()

    # Build list of (keyword, parent, sub) sorted by keyword length descending
    all_keywords = []
    for cat in CATEGORIES:
        for kw in cat["keywords"]:
            all_keywords.append((kw, cat["parent"], cat["slug"]))
    all_keywords.sort(key=lambda x: len(x[0]), reverse=True)

    for kw, parent, sub in all_keywords:
        pattern = r"\b" + re.escape(kw) + r"s?\b"
        if re.search(pattern, combined):
            return (parent, sub)

    # Try parent fallback keywords (broad terms, checked last)
    fallback_keywords = []
    for parent_slug, keywords in _PARENT_FALLBACKS.items():
        for kw in keywords:
            fallback_keywords.append((kw, parent_slug))
    fallback_keywords.sort(key=lambda x: len(x[0]), reverse=True)

    for kw, parent_slug in fallback_keywords:
        pattern = r"\b" + re.escape(kw) + r"s?\b"
        if re.search(pattern, combined):
            return (parent_slug, "other")

    return ("other", "other")


def category_name(slug: str) -> str:
    """Get display name for a category slug (parent or sub)."""
    return CATEGORY_NAMES.get(slug, "Other")
