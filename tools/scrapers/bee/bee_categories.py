"""
Product category taxonomy for beekeeping supplies.

Used by dashboard and digest to classify products into browsable categories.
Categories are matched against product titles and tags.
"""

CATEGORIES = [
    {
        "slug": "hives-boxes",
        "name": "Hives & Boxes",
        "keywords": [
            "hive", "brood box", "super", "nuc", "nucleus",
            "langstroth", "flow hive", "observation hive",
            "lid", "roof", "base", "bottom board",
            "queen excluder", "inner cover", "hive mat",
            "hive stand", "entrance reducer",
        ],
    },
    {
        "slug": "frames-foundation",
        "name": "Frames & Foundation",
        "keywords": [
            "frame", "foundation", "wax sheet", "beeswax foundation",
            "plastic foundation", "wired frame", "unwired",
            "deep frame", "medium frame", "ideal frame",
            "frame grip", "frame spacer", "castellated spacer",
        ],
    },
    {
        "slug": "extractors-processing",
        "name": "Extractors & Processing",
        "keywords": [
            "extractor", "uncapping", "honey gate",
            "strainer", "sieve", "bottling", "settling tank",
            "uncapping knife", "uncapping fork", "honey pump",
            "wax melter", "wax press", "solar wax",
            "creaming", "warming", "decrystallizer",
        ],
    },
    {
        "slug": "protective-gear",
        "name": "Protective Gear",
        "keywords": [
            "suit", "jacket", "veil", "glove", "hat",
            "bee suit", "bee jacket", "bee veil", "bee gloves",
            "ventilated", "cotton suit", "mesh",
            "full suit", "half suit", "smock",
        ],
    },
    {
        "slug": "smokers-tools",
        "name": "Smokers & Tools",
        "keywords": [
            "smoker", "hive tool", "j hook", "j-hook",
            "bee brush", "frame lifter", "grafting tool",
            "queen cage", "queen catcher", "queen marking",
            "bee escape", "porter escape",
        ],
    },
    {
        "slug": "treatments",
        "name": "Treatments & Health",
        "keywords": [
            "varroa", "apistan", "apivar", "oxalic", "formic",
            "bayvarol", "treatment", "mite", "mite treatment",
            "nosema", "fumagilin", "small hive beetle",
            "beetle trap", "diatomaceous", "thymol",
        ],
    },
    {
        "slug": "feeders",
        "name": "Feeders & Feed",
        "keywords": [
            "feeder", "syrup", "sugar syrup", "pollen",
            "pollen substitute", "pollen patty", "fondant",
            "frame feeder", "top feeder", "entrance feeder",
            "boardman feeder",
        ],
    },
    {
        "slug": "honey-containers",
        "name": "Honey Containers & Labels",
        "keywords": [
            "jar", "bottle", "container", "honey jar",
            "hex jar", "round jar", "squeeze bottle",
            "label", "tamper seal", "lid", "cap",
        ],
    },
    {
        "slug": "books-education",
        "name": "Books & Education",
        "keywords": [
            "book", "guide", "manual", "dvd", "course",
        ],
    },
]


def categorise_product(title: str, tags: list[str] = None, product_type: str = "") -> str:
    """Match a product to a category slug. Returns 'other' if no match."""
    title_lower = title.lower()
    combined = title_lower
    if tags:
        combined += " " + " ".join(t.lower() for t in tags)
    if product_type:
        combined += " " + product_type.lower()

    for cat in CATEGORIES:
        for kw in cat["keywords"]:
            if kw in combined:
                return cat["slug"]

    return "other"


def category_name(slug: str) -> str:
    """Get display name for a category slug."""
    for cat in CATEGORIES:
        if cat["slug"] == slug:
            return cat["name"]
    return "Other"


# Quick lookup: slug -> name
CATEGORY_NAMES = {cat["slug"]: cat["name"] for cat in CATEGORIES}
CATEGORY_NAMES["other"] = "Other"
