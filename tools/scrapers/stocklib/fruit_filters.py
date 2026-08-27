"""
Per-nursery fruit-only product filters, shared by the dashboard and the daily
digest.

FRUIT_FILTERS and is_fruit_product() lived as two hand-synced copies in
build-dashboard.py and daily_digest.py, and they drifted badly: the digest's
dict had only 2 of the dashboard's 12 nurseries (so digest emails applied no
per-nursery filter for daleys, diggers, guildford, ross-creek, ...), and its
is_fruit_product() was missing the "categories" mode daleys relies on. This is
the single copy; both import it.

Junk/seed filtering is deliberately NOT in here: is_fruit_product answers
"does this nursery's own categorisation say fruit?". Callers combine it with
stocklib.classify.is_real_product for the "is it a plant at all?" question,
which is what the dashboard pipeline does for every mode.

If a nursery has useful categorization, only include products matching these.
"""

FRUIT_FILTERS = {
    "ladybird": {
        "mode": "tags",
        # Products with this tag prefix. "Nut Trees" is a second top-level tag,
        # not a child of "Fruit Trees & Edibles", so leaving it out dropped 14
        # real trees nightly: 7 pecans, English walnut, almond, hazelnut,
        # corkscrew hazel, sour cherry and kaffir plum. Same bug class as
        # DEC-207, one layer further down: that audit checked scrape-time
        # include-filters and passed ladybird as "no filter", never looking at
        # this build-time one.
        "include_tags": ["Fruit Trees & Edibles", "Nut Trees"],
    },
    "ross-creek": {
        "mode": "all",  # all products are fruit/plant related
    },
    "fruitopia": {
        "mode": "all",
    },
    "daleys": {
        "mode": "categories",
        # Two vocabularies, both live. The bare headings are the Plant-List.php
        # ones the HTML scraper read and the frozen category map still hands
        # back; the slashed ones are the breadcrumb paths the CSV feed started
        # carrying on 2026-08-27. Both must stay: yesterday's snapshot on disk
        # is filtered with this same list when stocklib.changes diffs it, and
        # dropping the old spellings would read as a mass delisting overnight.
        #
        # "Plant List/..." is the feed's own third spelling for the same three
        # buckets, and leaving it out cost 23 products: 5 buyable (Chinese Red
        # Bayberry, Kaffir Plum, OkeeDokee nectarine, Navelina orange, Carolina
        # Reaper) and 18 out of stock but watchable, which is the half that
        # matters more (Yuzu, Yellow Mangosteen grafted, Dwarf Macadamia A16,
        # Abiu Z4, Dorrigo Blood plum, Carambola B10). A variety absent from the
        # filtered set cannot restock, so a watch on it can never fire.
        "include_prefixes": [
            "Fruit and Nut Trees", "Fruit Trees/",
            "Plant List/Fruit and Nut Trees",
            "Bush Food Plants",
            "Plant List/Bush Food Plants",
            "Herbs, Spices & Perennial Vegetables",
            "Plant List/Herbs, Spices & Perennial Vegetables",
            # "Specials" is a merchandising bucket, not a taxonomy one, and it
            # REPLACES the product's real category rather than adding to it.
            # So a fruit tree put on special used to vanish from treestock,
            # which is exactly backwards: a discounted rare fruit tree is the
            # most interesting event we have and it is what feeds the
            # price-drop alerts. Mixed bucket by nature, so it leans on the
            # junk gate downstream rather than on this filter.
            "Specials",
        ],
        # Deliberately NOT included, see tests/test_fruit_filters.py:
        #   "Trees and Plants/Rainforest Trees"
        #                       holds "Fig - Small Leaved" and "Fig - White",
        #                       rainforest shade figs that species_match
        #                       resolves to Fig. Including them mints bogus
        #                       cultivars on /variety/fig. Needs an ornamental
        #                       guard on that path first (1.6a's bug class).
        #                       Until 2026-08-27 the species fallback was
        #                       admitting 26 of them anyway, under a category
        #                       string of its own invention.
        #   "Gardening Tools - Accessories/Scion Wood"
        #                       32 groups of 15cm grafting sticks at $9.75,
        #                       named by cultivar ("Scion Wood Apple - Pink
        #                       Lady"). species_match resolves them to Apple,
        #                       Cherry, Wampee and so on, so before the feed
        #                       carried categories they sat on the species and
        #                       state pages as the cheapest listing for their
        #                       fruit, undercutting real trees 3-5x. They mint
        #                       no variety slug, so the damage was confined to
        #                       price rank, which is precisely where it hurts
        #                       (DEC-314: those pages rank by price).
        #   ""                  Was 602 live rows before the feed carried a
        #                       category column. Now 0. The alarm if that ever
        #                       regresses is csv_feed_scraper's
        #                       min_feed_category_share, not a rule here:
        #                       admitting uncategorised rows is what let the
        #                       scion wood and the rainforest figs in.
    },
    "primal-fruits": {
        "mode": "all",
    },
    "guildford": {
        "mode": "all",  # already filtered at scrape time by WooCommerce categories
    },
    "fruit-salad-trees": {
        "mode": "all",  # all products are multi-graft fruit trees
    },
    "diggers": {
        "mode": "all",  # already filtered at scrape time by fruit/nut tags
    },
    "all-season-plants-wa": {
        "mode": "all",  # WA-based fruit tree nursery, all products are fruit
    },
    "ausnurseries": {
        "mode": "all",  # Dedicated fruit/nut tree nursery
    },
    "fruit-tree-cottage": {
        "mode": "all",  # Dedicated fruit tree nursery (Forest Glen, QLD)
    },
    "forever-seeds": {
        # Only include products that are grown plants/trees, not seed packets or herbs
        "mode": "title_include",
        "include_keywords": ["fruit tree", "fruit plant", "vine plant", "fruiting"],
    },
}


def is_fruit_product(product: dict, nursery_key: str) -> bool:
    """Check if a product should be included based on nursery-specific filters."""
    filt = FRUIT_FILTERS.get(nursery_key)
    if not filt or filt.get("mode") == "all":
        return True

    if filt.get("mode") == "tags":
        tags = product.get("tags", [])
        include_tags = filt.get("include_tags", [])
        for tag in tags:
            for inc in include_tags:
                if tag.startswith(inc):
                    return True
        return False

    if filt.get("mode") == "categories":
        cat = product.get("product_type", product.get("category", ""))
        include_prefixes = filt.get("include_prefixes", [])
        return any(cat.startswith(prefix) for prefix in include_prefixes)

    if filt.get("mode") == "title_include":
        title_lower = product.get("title", "").lower()
        include_keywords = filt.get("include_keywords", [])
        return any(kw in title_lower for kw in include_keywords)

    return True


def digest_product_filter(product: dict, nursery_key: str) -> bool:
    """The full treestock inclusion rule: the nursery's own fruit
    categorisation plus the junk/seed-packet filter.

    Lives here rather than in daily_digest.py because send_variety_alerts.py
    needs exactly the same rule to run stocklib.changes over the snapshots, and
    a second copy would drift the way FRUIT_FILTERS itself once did.
    """
    from stocklib.classify import is_real_product
    return (is_real_product(product.get("title", ""))
            and is_fruit_product(product, nursery_key))
