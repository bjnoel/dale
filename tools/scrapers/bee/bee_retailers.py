"""
Beekeeping retailer configurations for beestock.

Single source of truth for retailer metadata, shipping, and scraper config.
"""

# Retailer configurations
RETAILERS = {
    "ecrotek": {
        "name": "Ecrotek",
        "domain": "ecrotek.com.au",
        "platform": "shopify",
        "location": "Melbourne, VIC",
    },
    "the-bee-store": {
        "name": "The Bee Store",
        "domain": "thebeestore.com.au",
        "platform": "shopify",
        "location": "Australia",
    },
    "buzzbee": {
        "name": "Buzzbee",
        "domain": "buzzbee.com.au",
        "platform": "shopify",
        "location": "Australia",
    },
    # "australian-bee-supplies" - JSON API disabled (404/406). Revisit later.
    # "hornsby-beekeeping" - Neto platform, needs custom scraper. Phase 2.
    "flow-hive": {
        "name": "Flow Hive",
        "domain": "www.honeyflow.com.au",
        "platform": "shopify",
        "location": "Byron Bay, NSW",
    },
}

# Shipping: most beekeeping retailers ship nationally (no live quarantine issues
# like nurseries). Adjust per retailer as we learn their actual policies.
SHIPPING_MAP = {
    "ecrotek": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"],
    "the-bee-store": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"],
    "buzzbee": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"],
    "flow-hive": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"],
}

RETAILER_NAMES = {k: v["name"] for k, v in RETAILERS.items()}

# Quarantine states (same as treestock, though less relevant for bee gear)
QUARANTINE_STATES = ["WA", "NT", "TAS"]


def retailer_ships_to(retailer_key: str, state: str) -> bool:
    """Return True if this retailer ships to the given state code."""
    return state in SHIPPING_MAP.get(retailer_key, [])


def restriction_warning(retailer_key: str) -> str:
    """Return a restriction warning like 'No WA/NT/TAS', or '' if ships everywhere."""
    ships = set(SHIPPING_MAP.get(retailer_key, []))
    excluded = [s for s in QUARANTINE_STATES if s not in ships]
    if not excluded:
        return ""
    return "No " + "/".join(excluded)
