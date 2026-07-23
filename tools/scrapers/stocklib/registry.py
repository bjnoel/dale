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
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="Verified 2026-06-15: ships QLD/NSW/VIC/SA/ACT (homepage banner). "
                 "No WA/NT/TAS ($10 refund fee on those)."),
    Nursery("ladybird", "Ladybird Nursery",
            ("NSW", "VIC", "QLD", "ACT"),
            note="Confirmed 2026-03-16: QLD/NSW/VIC/ACT only (not WA/NT/TAS)"),
    Nursery("fruitopia", "Fruitopia",
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="QLD-based. Verified 2026-06-15 (per-product policy): ships "
                 "QLD/NSW/ACT/VIC/SA, not WA/TAS/NT."),
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
            ("NSW", "VIC", "QLD", "ACT"),
            note="Does not ship to WA, SA, NT, or TAS (SA excluded per policy, "
                 "verified 2026-06-15). Seasonal: late June to Sep 15 only."),
    Nursery("forever-seeds", "Forever Seeds",
            ("NSW", "VIC", "QLD", "SA", "NT", "ACT"),
            note="NSW-based. Plants/bulbs not sent to WA or TAS (seeds ship "
                 "anywhere). NT served. Verified 2026-06-15."),
    Nursery("garden-express", "Garden Express",
            ("NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"),
            note="Ships nationwide; quarantine surcharge for WA/NT/TAS."),
    Nursery("plantnet", "PlantNet",
            ("NSW", "VIC", "QLD", "ACT"),
            note="Online shop does not ship to NT/TAS/SA/WA (state plant quarantine, "
                 "verified 2026-06-15). TAS/WA buyers directed to retail stockists."),
    Nursery("fruit-tree-lane", "Fruit Tree Lane",
            ("NSW", "VIC", "QLD", "SA", "ACT"),
            note="QLD-based (Helidon). Does not ship to WA, NT, or TAS (quarantine)."),
    Nursery("engalls", "Engall's Nursery",
            ("NSW", "VIC", "QLD", "ACT"),
            note="NSW-based (Dural). Does not ship to WA, NT, TAS. SA paused "
                 "(Red Imported Fire Ants emergency order, verified 2026-06-15; "
                 "bulk-only via SA stockist)."),
    Nursery("rayners", "Rayners Orchard",
            ("VIC",),
            local_delivery={"area": "Victoria", "state": "VIC"},
            note="VIC-based (Yarra Valley). Delivers within Victoria only; interstate only for bulk orders (50+)."),
    Nursery("garden-world", "Garden World",
            ("VIC",),
            local_delivery={"area": "Melbourne metro", "state": "VIC"},
            note="VIC-based (Braeside). Melbourne metro delivery (in-house vans) + in-store pickup; no interstate (no WA/NT/TAS)."),
    Nursery("diacos", "Diaco's Garden Nursery",
            ("VIC",),
            local_delivery={"area": "Melbourne metro", "state": "VIC"},
            note="VIC-based (Heatherton + other Melbourne stores). Melbourne metro delivery + in-store pickup; no interstate (no WA/NT/TAS)."),
    Nursery("wild-garden-organics", "Wild Garden Organics",
            ("QLD", "NSW", "VIC", "SA", "ACT"),
            note="QLD-based (Ecwid). Rare grafted tropicals. No WA/NT/TAS via "
                 "standard checkout (biosecurity; ships there on request for "
                 "~$300+). Free shipping over $170. Verified 2026-06-20."),
    Nursery("st-clements-citrus", "St Clements Citrus",
            ("WA",),
            local_delivery={"area": "WA", "state": "WA"},
            note="High Wycombe, Perth WA (Shopify). Rare-citrus specialist (yuzu, "
                 "Buddha's hand, blood lime, citron). Posts WA-wide only (citrus "
                 "interstate quarantine); postage included in price. Verified 2026-06-20."),
    Nursery("the-heritage-nursery", "The Heritage Nursery",
            ("ACT",),
            local_delivery={"area": "ACT + Queanbeyan", "state": "ACT"},
            note="Canberra garden centre (Shopify). Local delivery (ACT + "
                 "Queanbeyan, from $90) + click-and-collect only; no interstate "
                 "post. Distinct from Heritage Fruit Trees (VIC). Verified 2026-06-20."),
    Nursery("heaven-on-earth", "Heaven On Earth Fruit Trees",
            ("QLD", "NSW", "VIC", "SA", "NT", "ACT"),
            note="Far North QLD (Wix). Rare-tropical specialist (abiu, mamey "
                 "sapote, soursop, miracle fruit, durian). Ships AU-wide except "
                 "WA/TAS; NT included (per postage page). Citrus is QLD-only "
                 "(per-product rule, flagged in product names as 'QLD POSTAGE "
                 "ONLY', not modelled at nursery level). Verified 2026-06-20."),
    Nursery("all-rare-herbs", "All Rare Herbs",
            ("QLD", "NSW", "VIC", "SA", "NT", "ACT"),
            note="Mapleton QLD (WooCommerce). Herb specialist with a rare-fruit "
                 "branch (miracle fruit, acerola, vanilla, coffee, cocoa). No "
                 "plants to WA/TAS (shipping page + per-product lines, verified "
                 "2026-07-23); NT not excluded. A few products are stricter "
                 "(some also exclude SA, two are QLD-only), per-product rules "
                 "not modelled at nursery level."),
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
