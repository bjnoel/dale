"""
Shared shipping configuration for all nurseries.

Single source of truth for which states each nursery ships to.
Used by scrapers, dashboard builder, digest, history, and species pages.
"""

# States each nursery ships to. Verified via nursery websites March 2026.
# Quarantine states (WA, TAS, NT) require special permits; many QLD nurseries won't ship there.
SHIPPING_MAP = {
    "daleys": ["NSW", "VIC", "QLD", "SA", "WA", "ACT"],          # WA: seasonal window + extra fee
    "ross-creek": ["NSW", "VIC", "QLD", "ACT"],                   # Confirmed: QLD/NSW/VIC/ACT only
    "ladybird": ["NSW", "VIC", "QLD", "ACT"],                     # Confirmed 2026-03-16: ships to QLD/NSW/VIC/ACT only (not WA/NT/TAS)
    "fruitopia": ["NSW", "VIC", "QLD", "SA", "ACT"],              # QLD-based estimate
    "primal-fruits": ["WA"],                                       # WA-based, local only
    "guildford": ["WA"],                                           # WA-based, Perth metro
    "fruit-salad-trees": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT"],  # WA+TAS: 1st Tue/month
    "diggers": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"],      # Ships nationwide
    "all-season-plants-wa": ["WA"],                                          # WA-based, pickup only (Perth)
    "ausnurseries": ["NSW", "VIC", "QLD", "SA", "ACT"],           # Does not ship to WA, NT, or TAS
    "fruit-tree-cottage": ["NSW", "VIC", "QLD", "SA", "ACT"],     # Does not ship to WA, NT, or TAS
    "heritage-fruit-trees": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT"],  # VIC-based, ships nationally in winter/dormant season
    "perth-mobile-nursery": ["WA"],                                             # WA-based, Perth metro delivery only
    "yalca-fruit-trees": ["NSW", "VIC", "QLD", "SA", "ACT"],                   # Does not ship to WA, NT, or TAS. Seasonal: late June to Sep 15 only.
    "forever-seeds": ["NSW", "VIC", "QLD", "SA", "ACT"],                       # NSW-based. Does not ship to WA, NT, or TAS.
    "garden-express": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"],  # Ships nationwide; quarantine surcharge for WA/NT/TAS.
    "plantnet": ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT"],              # SA-based. Ships to WA via Olea Nurseries partner (Manjimup WA).
}

NURSERY_NAMES = {
    "daleys": "Daleys Fruit Trees",
    "ross-creek": "Ross Creek Tropicals",
    "ladybird": "Ladybird Nursery",
    "fruitopia": "Fruitopia",
    "primal-fruits": "Primal Fruits Perth",
    "guildford": "Guildford Garden Centre",
    "fruit-salad-trees": "Fruit Salad Trees",
    "diggers": "The Diggers Club",
    "all-season-plants-wa": "All Season Plants WA",
    "ausnurseries": "Aus Nurseries",
    "fruit-tree-cottage": "Fruit Tree Cottage",
    "heritage-fruit-trees": "Heritage Fruit Trees",
    "perth-mobile-nursery": "Perth Mobile Nursery",
    "yalca-fruit-trees": "Yalca Fruit Trees",
    "forever-seeds": "Forever Seeds",
    "garden-express": "Garden Express",
    "plantnet": "PlantNet",
}


def nursery_ships_to(nursery_key: str, state: str) -> bool:
    """Return True if this nursery ships to the given state code (e.g. 'WA')."""
    return state in SHIPPING_MAP.get(nursery_key, [])


# Quarantine states that are hard to ship to
QUARANTINE_STATES = ["WA", "NT", "TAS"]


def restriction_warning(nursery_key: str) -> str:
    """Return a restriction warning like 'No WA/NT/TAS', or '' if ships everywhere."""
    ships = set(SHIPPING_MAP.get(nursery_key, []))
    excluded = [s for s in QUARANTINE_STATES if s not in ships]
    if not excluded:
        return ""
    return "No " + "/".join(excluded)
