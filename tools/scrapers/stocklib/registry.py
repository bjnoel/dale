"""
Nursery registry -- one record per nursery, the single source of truth for
which states each nursery ships to, its display name, and any local-delivery
restriction.

Previously these lived as three parallel dicts in shipping.py (SHIPPING_MAP,
NURSERY_NAMES, LOCAL_DELIVERY), all keyed by the same nursery key and required
to stay in sync by hand -- adding a nursery meant editing three places. Here a
nursery is one Nursery record; the three dicts are *derived* from the list, so
they cannot drift. shipping.py is now a thin re-export shim, so the ~15 callers
that do `from shipping import SHIPPING_MAP, ...` keep working unchanged.

Scope note: the per-platform scrape config (domain, store id, category/tag
filters) still lives in each scraper's own NURSERIES dict. Folding that in (and
having scrapers select their nurseries from here by platform) is a follow-up;
it touches network-bound scraper code that can't be verified offline, so it is
deliberately not part of this change.

Verified by tests/test_registry.py (the derived dicts are pinned to the exact
pre-refactor values) and the golden SEO net.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Nursery:
    key: str
    name: str
    ships_to: tuple[str, ...]                 # state codes this nursery ships to
    local_delivery: dict | None = None        # {"area": ..., "state": ...} or None
    note: str = ""                            # provenance / shipping caveats


# Verified via nursery websites March 2026. Quarantine states (WA, TAS, NT)
# require special permits; many QLD/eastern nurseries won't ship there.
NURSERIES: list[Nursery] = [
    Nursery("daleys", "Daleys Fruit Trees",
            ("NSW", "VIC", "QLD", "SA", "WA", "ACT"),
            note="WA: seasonal window + extra fee"),
    Nursery("ross-creek", "Ross Creek Tropicals",
            ("NSW", "VIC", "QLD", "ACT"),
            note="Confirmed: QLD/NSW/VIC/ACT only"),
    Nursery("ladybird", "Ladybird Nursery",
            ("NSW", "VIC", "QLD", "ACT"),
            note="Confirmed 2026-03-16: QLD/NSW/VIC/ACT only (not WA/NT/TAS)"),
    Nursery("fruitopia", "Fruitopia",
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="QLD-based estimate"),
    Nursery("primal-fruits", "Primal Fruits Perth",
            ("WA",),
            local_delivery={"area": "Perth metro", "state": "WA"},
            note="WA-based, local only"),
    Nursery("guildford", "Guildford Garden Centre",
            ("WA",),
            local_delivery={"area": "Perth metro", "state": "WA"},
            note="WA-based, Perth metro"),
    Nursery("fruit-salad-trees", "Fruit Salad Trees",
            ("NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT"),
            note="WA+TAS: 1st Tue/month"),
    Nursery("diggers", "The Diggers Club",
            ("NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"),
            note="Ships nationwide"),
    Nursery("all-season-plants-wa", "All Season Plants WA",
            ("WA",),
            local_delivery={"area": "Perth (pickup)", "state": "WA"},
            note="WA-based, pickup only (Perth)"),
    Nursery("ausnurseries", "Aus Nurseries",
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="Does not ship to WA, NT, or TAS"),
    Nursery("fruit-tree-cottage", "Fruit Tree Cottage",
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="Does not ship to WA, NT, or TAS"),
    Nursery("heritage-fruit-trees", "Heritage Fruit Trees",
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="VIC-based. No WA/TAS: accreditation discontinued (Mar 2026)."),
    Nursery("perth-mobile-nursery", "Perth Mobile Nursery",
            ("WA",),
            local_delivery={"area": "Perth metro", "state": "WA"},
            note="WA-based, Perth metro delivery only"),
    Nursery("yalca-fruit-trees", "Yalca Fruit Trees",
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="Does not ship to WA, NT, or TAS. Seasonal: late June to Sep 15 only."),
    Nursery("forever-seeds", "Forever Seeds",
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="NSW-based. Does not ship to WA, NT, or TAS."),
    Nursery("garden-express", "Garden Express",
            ("NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"),
            note="Ships nationwide; quarantine surcharge for WA/NT/TAS."),
    Nursery("plantnet", "PlantNet",
            ("NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT"),
            note="SA-based. Ships to WA via Olea Nurseries partner (Manjimup WA)."),
    Nursery("fruit-tree-lane", "Fruit Tree Lane",
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="QLD-based (Helidon). Does not ship to WA, NT, or TAS (quarantine)."),
    Nursery("engalls", "Engall's Nursery",
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="NSW-based (Dural). Does not ship to WA, NT, TAS, or some SA areas (quarantine)."),
]

_BY_KEY: dict[str, Nursery] = {n.key: n for n in NURSERIES}

# Derived lookups -- kept for backward compatibility with the shipping.py API.
SHIPPING_MAP: dict[str, list[str]] = {n.key: list(n.ships_to) for n in NURSERIES}
NURSERY_NAMES: dict[str, str] = {n.key: n.name for n in NURSERIES}
LOCAL_DELIVERY: dict[str, dict] = {n.key: n.local_delivery for n in NURSERIES if n.local_delivery}

# Quarantine states that are hard to ship to.
QUARANTINE_STATES = ["WA", "NT", "TAS"]


def delivery_label(nursery_key: str) -> str:
    """Return 'Perth metro only' for local nurseries, or '' for statewide shippers."""
    local = LOCAL_DELIVERY.get(nursery_key)
    return f"{local['area']} only" if local else ""


def nursery_ships_to(nursery_key: str, state: str) -> bool:
    """Return True if this nursery ships to the given state code (e.g. 'WA')."""
    return state in SHIPPING_MAP.get(nursery_key, [])


def restriction_warning(nursery_key: str) -> str:
    """Return a restriction warning like 'No WA/NT/TAS', or '' if ships everywhere."""
    ships = set(SHIPPING_MAP.get(nursery_key, []))
    excluded = [s for s in QUARANTINE_STATES if s not in ships]
    if not excluded:
        return ""
    return "No " + "/".join(excluded)
