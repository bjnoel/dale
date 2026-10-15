#!/usr/bin/env python3
"""
Build /finger-lime-guide.html on treestock.com.au.

This page used to be a hand-written one-off on the server, and every number on
it went stale: "Live Prices Across 7 Nurseries" in the title, "130+ varieties",
"$19.75 starting price", and a price table that was a frozen copy from months
earlier. Now the guide prose lives in finger_lime_guide.html.j2 and everything
that describes stock (counts, prices, who ships where, which varieties are in
stock) is computed from the same nightly snapshots the compare pages use.

"QLD only" listings: shipping is modelled per nursery (see the KNOWN LIMIT in
send_variety_alerts.reachable), but finger lime is where per-listing rules
matter most. Ladybird, Ross Creek and Fruitopia mark many finger limes "QLD
ONLY" in the title, so a listing whose title says so only counts as reachable
from QLD here. Without that the WA section would offer Queenslanders' stock.

Usage:
    python3 build_finger_lime_guide.py /path/to/nursery-stock /path/to/output/
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from build_compare_pages import load_all_products, load_species
from shipping import SHIPPING_MAP, NURSERY_NAMES, LOCAL_DELIVERY, delivery_label
from stocklib.flags import DIGEST_SIGNUP_ENABLED
from stocklib.registry import restriction_warning, STATE_SHIPPING_CAVEATS
from stocklib.species_match import build_species_lookup, match_title
from stocklib.templates import render as render_template

SPECIES_SLUG = "finger-lime"

QLD_ONLY = re.compile(r"\bqld\s*only\b|restricted to qld", re.I)

STATE_GROUPS = [
    ("NSW / ACT", ("NSW", "ACT")),
    ("QLD", ("QLD",)),
    ("VIC", ("VIC",)),
    ("SA", ("SA",)),
    ("WA", ("WA",)),
    ("TAS", ("TAS",)),
    ("NT", ("NT",)),
]

# A state card is green when at least this many in-stock nurseries reach it.
WELL_SERVED = 3

PRICE_TIERS = [(0, 25), (25, 65), (65, 100), (100, None)]

# (display name, title keywords, description). Keywords are matched as
# lowercase substrings of the listing title, so they must be specific enough
# not to catch other varieties ("red" alone would match half the catalogue).
VARIETIES = [
    ("Alstonville", ("alstonville",),
     "Green skin, pink flesh. Strong grower, reliable cropper. Good for beginners."),
    ("Red Champagne", ("champagne",),
     "Red-black skin, red-pink flesh. A collector favourite. Sold as both cuttings and grafted trees."),
    ("Green Sapphire", ("sapphire",),
     "Green skin, green-gold flesh. Large fruit, productive tree. Great for fresh eating and restaurant use."),
    ("Byron Sunrise", ("byron",),
     "Pink-orange skin, pink flesh. Named for its sunrise colouring. Popular with collectors. Some nurseries only sell it in QLD."),
    ("Torakina Pink", ("torakina",),
     "Pink skin, pink flesh. From the Torakina area of NSW. Compact growth habit, suitable for small gardens."),
    ("Judy's Everbearing", ("judy",),
     "Named for its long fruiting season (it doesn't crop all at once). Green skin, clear-yellow flesh. Popular for home gardens."),
    ("Chartreuse", ("chartreuse",),
     "Bright yellow-green skin, yellow flesh. Distinctive colour. Some nurseries only sell it in QLD."),
    ("Maleny Red", ("maleny",),
     "Dark red skin, red flesh. Named for the Maleny region of Queensland. A really striking deep colour."),
    ("Crystal / Green Crystal", ("crystal",),
     "Pale green skin, translucent flesh. A subtler one, loved for its clear pearls."),
    ("Sunshine Yellow", ("sunshine",),
     "Bright yellow skin and flesh. Good fresh and in drinks."),
    ("Wauchope", ("wauchope",),
     "Named for Wauchope, NSW. Green skin, reliable cropper. One of the original named varieties in commercial cultivation."),
    ("Tom Thumb", ("tom thumb",),
     "A compact dwarf variety. Smaller tree than standard finger limes. Good for pots and small gardens."),
]


def is_qld_only(title: str) -> bool:
    return bool(QLD_ONLY.search(title))


def listing_states(p: dict) -> set[str]:
    """States someone could buy this listing from."""
    ships = set(SHIPPING_MAP.get(p["nursery_key"], ()))
    return ships & {"QLD"} if is_qld_only(p["title"]) else ships


def money(x: float) -> str:
    """$19.75, but $25 rather than $25.00."""
    return f"${x:.0f}" if x == int(x) else f"${x:.2f}"


def price_range(prices: list[float]) -> str:
    if not prices:
        return "POA"
    lo, hi = min(prices), max(prices)
    return money(lo) if lo == hi else f"{money(lo)} to {money(hi)}"


def nursery_label(key: str) -> str:
    """Nursery name, with the local area for pickup or metro-only nurseries."""
    name = NURSERY_NAMES.get(key, key)
    local = LOCAL_DELIVERY.get(key)
    if not local:
        return name
    # "Adelaide (pickup)" inside brackets would nest them.
    return f"{name} ({local['area'].replace(' (pickup)', ' pickup')})"


def join_names(names: list[str], limit: int = 4) -> str:
    if len(names) > limit:
        rest = len(names) - limit
        names = names[:limit] + [f"{rest} other{'s' if rest != 1 else ''}"]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def plural(n: int, word: str, many: str = "") -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


def finger_lime_products(data_dir: Path) -> list[dict]:
    lookup = build_species_lookup(load_species())
    return [p for p in load_all_products(data_dir)
            if (match_title(p["title"], lookup) or {}).get("slug") == SPECIES_SLUG]


def build_context(products: list[dict]) -> dict:
    """Everything on the page that describes stock. Pure, so it can be tested."""
    in_stock = [p for p in products if p["available"]]
    priced = [p for p in in_stock if p["price"]]

    by_nursery: dict[str, list[dict]] = {}
    for p in in_stock:
        by_nursery.setdefault(p["nursery_key"], []).append(p)

    rows = []
    for key, items in by_nursery.items():
        prices = [p["price"] for p in items if p["price"]]
        qld_only = sum(is_qld_only(p["title"]) for p in items)
        note = delivery_label(key)
        restricted = False
        if not note:
            if qld_only == len(items):
                note, restricted = "QLD only", True
            else:
                note = restriction_warning(key) or "Ships nationwide"
                restricted = note != "Ships nationwide"
                if qld_only:
                    note += f" ({qld_only} QLD only)"
        rows.append({
            "key": key,
            "name": NURSERY_NAMES.get(key, key),
            "range": price_range(prices),
            "min": min(prices) if prices else float("inf"),
            "count": len(items),
            "note": note,
            "restricted": restricted,
        })
    rows.sort(key=lambda r: (r["min"], r["name"]))

    def reaching(states) -> list[str]:
        """In-stock nursery keys with at least one listing buyable in `states`."""
        keys = {p["nursery_key"] for p in in_stock if listing_states(p) & set(states)}
        return [r["key"] for r in rows if r["key"] in keys]

    state_cards = []
    for label, states in STATE_GROUPS:
        keys = reaching(states)
        if keys:
            info = join_names([nursery_label(k) for k in keys]) + "."
        else:
            info = "None of the nurseries with finger limes in stock can send one here right now."
        state_cards.append({"label": label, "info": info,
                            "ok": len(keys) >= WELL_SERVED})

    wa = []
    for key in reaching(("WA",)):
        items = [p for p in by_nursery[key] if "WA" in listing_states(p)]
        prices = [p["price"] for p in items if p["price"]]
        caveat = delivery_label(key) or STATE_SHIPPING_CAVEATS.get("WA", {}).get(key, "")
        line = f"{plural(len(items), 'listing')} in stock"
        if prices:
            line += f", from {money(min(prices))}"
        if caveat:
            line += f". {caveat[0].upper()}{caveat[1:]}"
        wa.append({"name": NURSERY_NAMES.get(key, key), "line": line + "."})

    tiers = []
    for lo, hi in PRICE_TIERS:
        n = sum(1 for p in priced if p["price"] >= lo and (hi is None or p["price"] < hi))
        tiers.append(f"{plural(n, 'listing')} in this range right now" if n
                     else "Nothing in this range right now")

    varieties = []
    for name, keys, desc in VARIETIES:
        hits = [p for p in in_stock if any(k in p["title"].lower() for k in keys)]
        nurseries = {p["nursery_key"] for p in hits}
        if not nurseries:
            badge = "Not in stock right now"
        else:
            badge = f"In stock at {plural(len(nurseries), 'nursery', 'nurseries')}"
            if all(is_qld_only(p["title"]) for p in hits):
                badge += " (QLD only)"
        varieties.append({"name": name, "desc": desc, "badge": badge,
                          "in_stock": bool(nurseries)})

    cheapest = min(priced, key=lambda p: p["price"]) if priced else None
    wa_priced = [p for p in priced if "WA" in listing_states(p)]
    cheapest_wa = min(wa_priced, key=lambda p: p["price"]) if wa_priced else None

    return {
        "listing_count": len(in_stock),
        "nursery_count": len(rows),
        "min_price": money(min(p["price"] for p in priced)) if priced else "",
        "max_price": money(max(p["price"] for p in priced)) if priced else "",
        "rows": rows,
        "state_cards": state_cards,
        "wa": wa,
        "wa_names": join_names([w["name"] for w in wa], limit=6) if wa else "",
        "tiers": tiers,
        "varieties": varieties,
        "cheapest": cheapest and {
            "title": cheapest["title"], "price": money(cheapest["price"]),
            "nursery": NURSERY_NAMES.get(cheapest["nursery_key"], cheapest["nursery_key"]),
            "qld_only": is_qld_only(cheapest["title"])},
        "cheapest_wa": cheapest_wa and cheapest_wa is not cheapest and {
            "title": cheapest_wa["title"], "price": money(cheapest_wa["price"]),
            "nursery": NURSERY_NAMES.get(cheapest_wa["nursery_key"], cheapest_wa["nursery_key"])},
    }


def build_page(products: list[dict], today: str) -> str:
    ctx = build_context(products)
    n = ctx["nursery_count"]
    if n >= 2:
        title = f"Buy Finger Lime Trees in Australia: Live Prices Across {n} Nurseries"
        description = (f"Compare finger lime tree prices across {n} Australian nurseries. "
                       "See which varieties are in stock now, compare grafted and seedling "
                       "options, and set free restock alerts. Updated daily.")
    else:
        title = "Buy Finger Lime Trees in Australia: Live Prices and Stock"
        description = ("Finger lime tree prices and stock across Australian nurseries. "
                       "See which varieties are in stock now and set free restock alerts. "
                       "Updated daily.")
    og_description = (f"{plural(ctx['listing_count'], 'finger lime listing')} in stock across "
                      f"{plural(n, 'Australian nursery', 'Australian nurseries')} today"
                      + (f", from {ctx['min_price']}." if ctx["min_price"] else "."))
    return render_template(
        "finger_lime_guide.html.j2",
        title=title, description=description, og_description=og_description,
        today=today, digest_signup=DIGEST_SIGNUP_ENABLED, **ctx,
    )


def main():
    if len(sys.argv) < 3:
        print("Usage: build_finger_lime_guide.py /path/to/nursery-stock /path/to/output/")
        sys.exit(1)
    data_dir, output_dir = Path(sys.argv[1]), Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html = build_page(finger_lime_products(data_dir), today)
    out_file = output_dir / "finger-lime-guide.html"
    tmp = out_file.with_suffix(".html.tmp")
    tmp.write_text(html)
    tmp.replace(out_file)
    print(f"Written: {out_file} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
