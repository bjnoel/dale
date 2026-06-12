#!/usr/bin/env python3
"""
Daily Digest Generator

Compares today's nursery snapshots with yesterday's and produces a
human-readable summary of changes. Outputs both plain text (for FB groups)
and HTML (for email).

Usage:
    python3 daily_digest.py /path/to/nursery-stock
    python3 daily_digest.py /path/to/nursery-stock --date 2026-03-08
    python3 daily_digest.py /path/to/nursery-stock --html
    python3 daily_digest.py /path/to/nursery-stock --wa-only
"""

import functools
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from shipping import SHIPPING_MAP, NURSERY_NAMES, nursery_ships_to
from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_footer

# Fruit species lookup for filtering non-fruit products

# Same filters as build-dashboard.py
FRUIT_FILTERS = {
    "ladybird": {
        "mode": "tags",
        "include_tags": ["Fruit Trees & Edibles"],
    },
    "forever-seeds": {
        "mode": "title_include",
        "include_keywords": ["fruit tree", "fruit plant", "vine plant", "fruiting"],
    },
}

from stocklib.classify import NON_PLANT_KEYWORDS
from stocklib import changes as _changes
from stocklib.changes import variant_key as _variant_key, variant_display_title as _variant_display_title, compare_snapshots

# Backwards-compat: set of nurseries that ship to WA (used by build_history.py)
WA_NURSERIES = {k for k, states in SHIPPING_MAP.items() if "WA" in states}

# All category keys a daily digest can contain. Order matters for rendering.
ALL_CATEGORIES = ("back_in_stock", "price_drops", "new_products")

# Plant categories a subscriber can opt into (DAL-199, per Benedict: opt-in at
# confirmation, bush tucker OFF by default). A subscriber's set drives which
# parts of the digest they receive: "fruit" -> the per-nursery fruit sections;
# "bush_tucker" -> the clearly labelled bush tucker section. The DEFAULT is
# fruit only, so the public digest page and any legacy subscriber stay
# fruit-focused and bush tucker reaches no one who has not ticked the box.
PLANT_CATEGORIES = ("fruit", "bush_tucker")
DEFAULT_PLANT_CATEGORIES = frozenset({"fruit"})


def _resolve_plant_categories(plant_categories):
    """None -> the default (fruit only). Otherwise the valid subset."""
    if plant_categories is None:
        return DEFAULT_PLANT_CATEGORIES
    return frozenset(c for c in plant_categories if c in PLANT_CATEGORIES)


def _resolve_categories(categories):
    """Normalise a categories argument into a frozenset. None = all categories."""
    if categories is None:
        return frozenset(ALL_CATEGORIES)
    return frozenset(c for c in categories if c in ALL_CATEGORIES)


@functools.lru_cache(maxsize=1)
def _bush_tucker_phrases() -> tuple:
    """Lowercased names/synonyms of the enabled category==bush_tucker species
    (the pilot records only, NOT the cross-listed fruits like Finger Lime, which
    stay in the main fruit flow). Used to route digest change items into the
    labelled bush tucker section. Longest first so the match is specific."""
    from stocklib.taxonomy import enabled_species
    phrases = set()
    for r in enabled_species():
        if r.get("category") != "bush_tucker":
            continue
        for n in [r.get("common_name", "")] + list(r.get("synonyms", []) or []):
            n = n.strip().lower()
            if n:
                phrases.add(n)
    return tuple(sorted(phrases, key=len, reverse=True))


def _is_bush_tucker(title: str) -> bool:
    """True if a change item's title names a bush tucker pilot species. Whole
    word/phrase match, so "Desert Lime" routes to bush tucker but "Tahitian
    Lime" does not."""
    t = title.lower()
    return any(re.search(r"\b" + re.escape(ph) + r"\b", t)
               for ph in _bush_tucker_phrases())


def _partition_bush_tucker(all_changes: dict) -> tuple[dict, dict]:
    """Split each nursery's change lists into (fruit, bush_tucker) by title.
    Only the pilot bush tucker species route to the bush tucker bucket; the
    cross-listed fruits stay with fruit. Same per-nursery shape on both sides."""
    fruit, bt = {}, {}
    for nk, changes in all_changes.items():
        f_c = {cat: [] for cat in ALL_CATEGORIES}
        b_c = {cat: [] for cat in ALL_CATEGORIES}
        for cat in ALL_CATEGORIES:
            for item in changes.get(cat, []):
                bucket = b_c if _is_bush_tucker(item.get("title", "")) else f_c
                bucket[cat].append(item)
        fruit[nk] = f_c
        bt[nk] = b_c
    return fruit, bt


def filter_changes_by_plant_categories(all_changes: dict, plant_categories=None) -> dict:
    """Return all_changes keeping only items in the subscriber's plant categories
    (DAL-199), merged back into one per-nursery dict. For renderers that do not
    build a separate labelled section (the weekly digest): a fruit-only
    subscriber's bush tucker items are dropped, a bush-tucker-only subscriber
    keeps only those, and "both" is unchanged."""
    pc = _resolve_plant_categories(plant_categories)
    fruit_changes, bt_changes = _partition_bush_tucker(all_changes)
    out = {}
    for nk in all_changes:
        merged = {cat: [] for cat in ALL_CATEGORIES}
        for want, src in (("fruit", fruit_changes), ("bush_tucker", bt_changes)):
            if want in pc:
                for cat in ALL_CATEGORIES:
                    merged[cat].extend(src.get(nk, {}).get(cat, []))
        out[nk] = merged
    return out


def is_fruit_product(product: dict, nursery_key: str) -> bool:
    """Check if product is fruit/edible (same logic as dashboard)."""
    title_lower = product.get("title", "").lower()

    filt = FRUIT_FILTERS.get(nursery_key)
    if not filt or filt.get("mode") == "all":
        if any(kw in title_lower for kw in NON_PLANT_KEYWORDS):
            return False
        # Skip seed packets
        if re.search(r'\bseeds?\b', title_lower) and 'seedling' not in title_lower and 'seedless' not in title_lower:
            return False
        return True

    if filt.get("mode") == "tags":
        tags = product.get("tags", [])
        include_tags = filt.get("include_tags", [])
        for tag in tags:
            for inc in include_tags:
                if tag.startswith(inc):
                    return True
        return False

    if filt.get("mode") == "title_include":
        include_keywords = filt.get("include_keywords", [])
        return any(kw in title_lower for kw in include_keywords)

    return True






def load_snapshot(nursery_dir: Path, target_date: str) -> dict:
    """treestock snapshot load: fruit-filtered. Engine in stocklib.changes."""
    return _changes.load_snapshot(nursery_dir, target_date, product_filter=is_fruit_product)




def _bush_tucker_text(bt_changes: dict, filter_state: str, enabled) -> list:
    """Plain-text "Bush tucker" block (DAL-199): bush tucker changes flattened
    across nurseries (state-filtered), each line noting its nursery. [] if
    nothing qualifies."""
    rows = []
    for nursery_key, changes in sorted(bt_changes.items()):
        if filter_state and not nursery_ships_to(nursery_key, filter_state):
            continue
        nm = NURSERY_NAMES.get(nursery_key, nursery_key)
        if "back_in_stock" in enabled:
            for item in changes["back_in_stock"]:
                price_str = ""
                if item.get("price"):
                    price_str = f" — ${item['price']:.2f}"
                    if item.get("old_price"):
                        price_str += f" (was ${item['old_price']:.2f})"
                link = f"\n    {item['url']}" if item.get("url") else ""
                rows.append(f"  ✅ {item['title']} ({nm}){price_str}{link}")
        if "price_drops" in enabled:
            for item in changes["price_drops"]:
                link = f"\n    {item['url']}" if item.get("url") else ""
                rows.append(f"  📉 {item['title']} ({nm}): ${item['old_price']:.2f} → ${item['new_price']:.2f}{link}")
        if "new_products" in enabled:
            for item in changes["new_products"]:
                price_str = f" — ${item['price']:.2f}" if item["price"] else ""
                link = f"\n    {item['url']}" if item.get("url") else ""
                rows.append(f"  🆕 {item['title']} ({nm}){price_str}{link}")
    if not rows:
        return []
    return ["🌿 Bush tucker", *rows, ""]


def format_text(all_changes: dict, target_date: str, wa_only: bool = False, state: str = "", categories=None, plant_categories=None) -> str:
    """Format changes as plain text for FB groups."""
    # --wa-only is an alias for --state WA
    filter_state = "WA" if wa_only else state
    enabled = _resolve_categories(categories)
    pc = _resolve_plant_categories(plant_categories)
    # Always partition; render each plant category only if the subscriber wants
    # it. Fruit-only (the default) drops bush tucker items entirely.
    fruit_changes, bt_changes = _partition_bush_tucker(all_changes)
    render_changes = fruit_changes if "fruit" in pc else {}
    bt_changes = bt_changes if "bush_tucker" in pc else None

    lines = []
    lines.append(f"🌱 Nursery Stock Update — {target_date}")
    lines.append(f"via treestock.com.au")
    lines.append("")

    has_any = False

    for nursery_key, changes in sorted(render_changes.items()):
        if filter_state and not nursery_ships_to(nursery_key, filter_state):
            continue

        name = NURSERY_NAMES.get(nursery_key, nursery_key)

        sections = []

        if "back_in_stock" in enabled and changes["back_in_stock"]:
            items = []
            for item in changes["back_in_stock"]:
                price_str = ""
                if item.get("price"):
                    price_str = f" — ${item['price']:.2f}"
                    if item.get("old_price"):
                        price_str += f" (was ${item['old_price']:.2f})"
                link = f"\n    {item['url']}" if item.get("url") else ""
                items.append(f"  ✅ {item['title']}{price_str}{link}")
            sections.append(("Back in stock", items))

        if "price_drops" in enabled and changes["price_drops"]:
            items = []
            for item in changes["price_drops"]:
                link = f"\n    {item['url']}" if item.get("url") else ""
                items.append(f"  📉 {item['title']}: ${item['old_price']:.2f} → ${item['new_price']:.2f}{link}")
            sections.append(("Price drops", items))

        if "new_products" in enabled and changes["new_products"]:
            items = []
            for item in changes["new_products"][:10]:  # Cap at 10
                price_str = f" — ${item['price']:.2f}" if item["price"] else ""
                link = f"\n    {item['url']}" if item.get("url") else ""
                items.append(f"  🆕 {item['title']}{price_str}{link}")
            extra = len(changes["new_products"]) - 10
            if extra > 0:
                items.append(f"  ... and {extra} more")
            sections.append(("New listings", items))

        if not sections:
            continue

        has_any = True
        lines.append(f"📦 {name}")
        for section_name, items in sections:
            for item in items:
                lines.append(item)
        lines.append("")

    if bt_changes is not None:
        bt_lines = _bush_tucker_text(bt_changes, filter_state, enabled)
        if bt_lines:
            has_any = True
            lines.extend(bt_lines)

    if not has_any:
        lines.append("No changes today — all quiet across the nurseries.")
        lines.append("")

    lines.append("—")
    lines.append("Full dashboard: https://treestock.com.au")
    lines.append(f"Tracking {len(SHIPPING_MAP)} nurseries daily.")

    return "\n".join(lines)


def _utm(url: str) -> str:
    return url + ("&" if "?" in url else "?") + "utm_source=treestock&utm_medium=referral" if url else ""


def _bush_tucker_section(bt_changes: dict, filter_state: str, enabled) -> dict | None:
    """One flattened "Bush tucker" section (DAL-199) across nurseries
    (state-filtered); each entry notes its nursery. None if nothing qualifies."""
    entries = []
    for nursery_key, changes in sorted(bt_changes.items()):
        if filter_state and not nursery_ships_to(nursery_key, filter_state):
            continue
        note = NURSERY_NAMES.get(nursery_key, nursery_key)
        if "back_in_stock" in enabled:
            for item in changes["back_in_stock"]:
                url = item.get("url", "")
                entries.append({
                    "kind": "back", "has_url": bool(url), "utm_url": _utm(url),
                    "title": item["title"], "price": item["price"],
                    "old_price": item.get("old_price"), "note": note,
                })
        if "price_drops" in enabled:
            for item in changes["price_drops"]:
                url = item.get("url", "")
                entries.append({
                    "kind": "price", "has_url": bool(url), "utm_url": _utm(url),
                    "title": item["title"], "old_price": item["old_price"],
                    "new_price": item["new_price"], "note": note,
                })
        if "new_products" in enabled:
            for item in changes["new_products"]:
                url = item.get("url", "")
                entries.append({
                    "kind": "new", "has_url": bool(url), "utm_url": _utm(url),
                    "title": item["title"], "price": item["price"], "note": note,
                })
    if not entries:
        return None
    return {"name": "🌿 Bush tucker", "entries": entries}


def _build_change_sections(all_changes: dict, wa_only: bool = False, state: str = "", categories=None, plant_categories=None) -> list[dict]:
    """Build per-nursery change sections as view-data: a list of
    {name, entries}. The digest_sections template renders these and autoescapes
    the scraped product title and the utm URL (which carries a raw &)."""
    filter_state = "WA" if wa_only else state
    enabled = _resolve_categories(categories)
    pc = _resolve_plant_categories(plant_categories)
    fruit_changes, bt_changes = _partition_bush_tucker(all_changes)
    render_changes = fruit_changes if "fruit" in pc else {}
    bt_changes = bt_changes if "bush_tucker" in pc else None
    sections = []

    for nursery_key, changes in sorted(render_changes.items()):
        if filter_state and not nursery_ships_to(nursery_key, filter_state):
            continue

        name = NURSERY_NAMES.get(nursery_key, nursery_key)
        entries = []

        if "back_in_stock" in enabled:
            for item in changes["back_in_stock"]:
                url = item.get("url", "")
                entries.append({
                    "kind": "back", "has_url": bool(url), "utm_url": _utm(url),
                    "title": item["title"], "price": item["price"],
                    "old_price": item.get("old_price"),
                })

        if "price_drops" in enabled:
            for item in changes["price_drops"]:
                url = item.get("url", "")
                entries.append({
                    "kind": "price", "has_url": bool(url), "utm_url": _utm(url),
                    "title": item["title"], "old_price": item["old_price"],
                    "new_price": item["new_price"],
                })

        if "new_products" in enabled:
            for item in changes["new_products"][:10]:
                url = item.get("url", "")
                entries.append({
                    "kind": "new", "has_url": bool(url), "utm_url": _utm(url),
                    "title": item["title"], "price": item["price"],
                })
            extra = len(changes["new_products"]) - 10
            if extra > 0:
                entries.append({"kind": "more", "extra": extra})

        if not entries:
            continue
        sections.append({"name": name, "entries": entries})

    if bt_changes is not None:
        bt_section = _bush_tucker_section(bt_changes, filter_state, enabled)
        if bt_section:
            sections.append(bt_section)

    return sections


def _render_sections(sections: list[dict]) -> str:
    """Render the change sections to (autoescaped) HTML."""
    return render_template("digest_sections.html.j2", sections=sections)


def has_any_changes(all_changes: dict, wa_only: bool = False, state: str = "", categories=None, plant_categories=None) -> bool:
    """True if at least one item survives the state + change-type + plant-category
    filter, so a fruit-only subscriber is not emailed when only bush tucker
    changed (and vice versa)."""
    filter_state = "WA" if wa_only else state
    enabled = _resolve_categories(categories)
    pc = _resolve_plant_categories(plant_categories)
    fruit_changes, bt_changes = _partition_bush_tucker(all_changes)
    buckets = []
    if "fruit" in pc:
        buckets.append(fruit_changes)
    if "bush_tucker" in pc:
        buckets.append(bt_changes)
    for bucket in buckets:
        for nursery_key, changes in bucket.items():
            if filter_state and not nursery_ships_to(nursery_key, filter_state):
                continue
            for cat in enabled:
                if changes.get(cat):
                    return True
    return False


def format_html(all_changes: dict, target_date: str, wa_only: bool = False, state: str = "", categories=None, plant_categories=None) -> str:
    """Format changes as HTML for email (inline styles, no external deps)."""
    sections = _build_change_sections(all_changes, wa_only, state, categories, plant_categories)
    body_html = _render_sections(sections) if sections else \
        '<p>No changes today — all quiet across the nurseries.</p>'
    return render_template(
        "digest_email.html.j2",
        target_date=target_date, body_html=body_html,
        nursery_count=len(SHIPPING_MAP),
    )


def format_html_page(all_changes: dict, target_date: str, wa_only: bool = False, state: str = "", categories=None, plant_categories=None) -> str:
    """Format changes as a shareable web page with proper styling and navigation."""
    filter_state = "WA" if wa_only else state
    sections = _build_change_sections(all_changes, wa_only, state, categories, plant_categories)

    title_suffix = f" (Ships to {filter_state})" if filter_state else ""

    # Count changes by type for summary pills, scoped to the page's plant
    # categories so the fruit page does not count bush tucker items (and vice
    # versa).
    pc = _resolve_plant_categories(plant_categories)
    fruit_changes, bt_changes = _partition_bush_tucker(all_changes)
    pill_buckets = []
    if "fruit" in pc:
        pill_buckets.append(fruit_changes)
    if "bush_tucker" in pc:
        pill_buckets.append(bt_changes)
    total_by_type = {}
    for bucket in pill_buckets:
        for nursery_key, changes in bucket.items():
            if filter_state and not nursery_ships_to(nursery_key, filter_state):
                continue
            for cat, items in changes.items():
                if items:
                    total_by_type[cat] = total_by_type.get(cat, 0) + len(items)

    pills = []
    pill_config = [
        ("back_in_stock", "✅", "Back in stock"),
        ("price_drops", "📉", "Price drops"),
        ("new_products", "🆕", "New"),
    ]
    for key, icon, label in pill_config:
        count = total_by_type.get(key, 0)
        if count > 0:
            pills.append(
                f'<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 12px;'
                f'border-radius:9999px;font-size:0.875rem;background:#f3f4f6">'
                f'{icon} {count} {label}</span>'
            )

    pills_html = " ".join(pills) if pills else ""

    extra_style = """\
  a { color: #065f46; }
  a:hover { text-decoration: underline; }
  li { border-bottom: 1px solid #f3f4f6; }
  li:last-child { border-bottom: none; }"""

    head = render_head(
        title=f"Nursery Stock Update for {target_date}{title_suffix} | treestock.com.au",
        description=f"Daily fruit nursery stock changes for {target_date}. Price drops, back in stock alerts, and new listings.",
        og_title=f"Nursery Stock Update for {target_date}",
        og_description="Daily price and stock changes across Australian fruit nurseries.",
        og_type="article",
        extra_style=extra_style,
    )
    header = render_header(
        max_width="max-w-2xl",
        active_path="/digest.html",
    )
    footer = render_footer(max_width="max-w-2xl")

    body_html = _render_sections(sections) if sections else \
        ('<div style="text-align:center;padding:48px 0;color:#9ca3af">'
         'No changes today — all quiet across the nurseries.</div>')
    return render_template(
        "digest_page.html.j2",
        head=head, header=header, footer=footer,
        target_date=target_date, pills_html=pills_html,
        body_html=body_html, nursery_count=len(SHIPPING_MAP),
    )


def load_all_changes(data_dir: Path, target_date: str) -> tuple[dict, int]:
    """treestock changes: fruit-filtered, all nursery dirs. Engine in stocklib.changes."""
    return _changes.load_all_changes(data_dir, target_date, product_filter=is_fruit_product)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate daily stock change digest")
    parser.add_argument("data_dir", help="Path to nursery-stock directory")
    parser.add_argument("--date", help="Date to compare (default: today)", default=None)
    parser.add_argument("--html", action="store_true", help="Output HTML (email format)")
    parser.add_argument("--page", action="store_true", help="Output HTML (shareable web page)")
    parser.add_argument("--wa-only", action="store_true", help="Alias for --state WA")
    parser.add_argument("--state", help="Filter to nurseries shipping to this state (e.g. WA, TAS, NSW)")
    parser.add_argument("--save", help="Save output to file")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    state = (args.state or "").upper() if args.state else ""

    target_date = args.date or date.today().isoformat()
    all_changes, total_changes = load_all_changes(data_dir, target_date)

    if args.page:
        output = format_html_page(all_changes, target_date, wa_only=args.wa_only, state=state)
    elif args.html:
        output = format_html(all_changes, target_date, wa_only=args.wa_only, state=state)
    else:
        output = format_text(all_changes, target_date, wa_only=args.wa_only, state=state)

    if args.save:
        Path(args.save).write_text(output)
        print(f"Saved to {args.save}", file=sys.stderr)
    else:
        print(output)

    print(f"\n({total_changes} total changes across {len(all_changes)} nurseries)", file=sys.stderr)


if __name__ == "__main__":
    main()
