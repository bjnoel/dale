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

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from shipping import SHIPPING_MAP, NURSERY_NAMES, nursery_ships_to

# Fruit species lookup for filtering non-fruit products
SPECIES_FILE = Path(__file__).parent / "fruit_species.json"

# Same filters as build-dashboard.py
FRUIT_FILTERS = {
    "ladybird": {
        "mode": "tags",
        "include_tags": ["Fruit Trees & Edibles"],
    },
}

NON_PLANT_KEYWORDS = [
    "fertilizer", "fertiliser", "potting mix", "soil mix",
    "seaweed solution", "fish emulsion", "worm castings",
    "secateurs", "pruning", "garden gloves", "plant label",
    "grafting tape", "grafting knife", "budding tape",
    "grow bag", "terracotta", "saucer",
    "pest spray", "insecticide", "fungicide", "neem oil",
    "insect killer", "insect control", "white oil",
    "weed killer", "herbicide", "concentrate spray",
    "shipping", "postage", "freight", "delivery charge",
    "gift card", "gift voucher", "gift certificate",
    "sharp shooter", "searles liquid", "ecofend",
]

# Backwards-compat: set of nurseries that ship to WA (used by build_history.py)
WA_NURSERIES = {k for k, states in SHIPPING_MAP.items() if "WA" in states}


def is_fruit_product(product: dict, nursery_key: str) -> bool:
    """Check if product is fruit/edible (same logic as dashboard)."""
    filt = FRUIT_FILTERS.get(nursery_key)
    if not filt or filt.get("mode") == "all":
        # Still filter non-plant items
        title_lower = product.get("title", "").lower()
        return not any(kw in title_lower for kw in NON_PLANT_KEYWORDS)

    if filt.get("mode") == "tags":
        tags = product.get("tags", [])
        include_tags = filt.get("include_tags", [])
        for tag in tags:
            for inc in include_tags:
                if tag.startswith(inc):
                    return True
        return False
    return True


def _variant_key(product_url: str, variant: dict) -> str:
    """Generate a unique key for a specific variant within a product."""
    base = product_url or ""
    # Prefer SKU (Daleys, Ecwid) — most stable identifier
    sku = variant.get("sku")
    if sku:
        return f"{base}|sku:{sku}"
    # Prefer variant ID (Shopify)
    vid = variant.get("id")
    if vid:
        return f"{base}|id:{vid}"
    # Fallback: variant title
    vtitle = variant.get("title", "Default")
    return f"{base}|v:{vtitle}"


def _variant_display_title(product_title: str, variant_title: str) -> str:
    """Build a display title for a variant, e.g. 'Acerola (Large)'."""
    if not variant_title or variant_title in ("Default", "Default Title"):
        return product_title
    return f"{product_title} ({variant_title})"


def load_snapshot(nursery_dir: Path, target_date: str) -> dict:
    """Load a snapshot for a specific date, return product lookup by variant key.

    Multi-variant products are flattened so each variant is tracked independently.
    This prevents false price changes when one variant goes out of stock and the
    min_price shifts to a different-priced variant.
    """
    snapshot = nursery_dir / f"{target_date}.json"
    if not snapshot.exists():
        return {}
    with open(snapshot) as f:
        data = json.load(f)
    products = {}
    nursery_key = nursery_dir.name
    for p in data.get("products", []):
        if not is_fruit_product(p, nursery_key):
            continue

        url = p.get("url", "")
        title = p.get("title", "")
        variants = p.get("variants", [])

        if not variants:
            # No variants at all (e.g. Ecwid flat products) — key by URL
            key = url or title
            products[key] = p
        else:
            # Always flatten to variant level, even single-variant products.
            # This ensures consistent keys when a product gains/loses variants.
            for v in variants:
                vkey = _variant_key(url, v)
                vprice = v.get("price")
                if isinstance(vprice, str):
                    try:
                        vprice = float(vprice)
                    except (ValueError, TypeError):
                        vprice = None

                products[vkey] = {
                    "title": _variant_display_title(title, v.get("title", "")),
                    "url": url,
                    "min_price": vprice,
                    "any_available": bool(v.get("available", False)),
                }

    return products


def compare_snapshots(prev: dict, curr: dict) -> dict:
    """Compare two snapshots and return categorized changes."""
    changes = {
        "price_drops": [],
        "back_in_stock": [],
        "new_products": [],
    }

    for key, product in curr.items():
        title = product.get("title", "")
        price = product.get("min_price")
        available = product.get("any_available", product.get("available", False))

        if key not in prev:
            if available:
                changes["new_products"].append({
                    "title": title,
                    "price": price,
                    "url": product.get("url", ""),
                })
            continue

        prev_product = prev[key]
        prev_price = prev_product.get("min_price")
        prev_available = prev_product.get("any_available", prev_product.get("available", False))

        # Stock changes first (affects how we report price changes)
        back_in_stock = available and not prev_available

        if back_in_stock:
            entry = {
                "title": title,
                "price": price,
                "url": product.get("url", ""),
            }
            # Include old price if it changed (so we can show "back at $X, was $Y")
            if price and prev_price and abs(price - prev_price) > 0.01:
                entry["old_price"] = prev_price
            changes["back_in_stock"].append(entry)

        # Price changes (only for items that stayed available — back-in-stock
        # items already show their price change above)
        if price and prev_price and available and not back_in_stock:
            diff = price - prev_price
            if diff < -0.01:
                changes["price_drops"].append({
                    "title": title,
                    "old_price": prev_price,
                    "new_price": price,
                    "url": product.get("url", ""),
                })

    return changes


def format_text(all_changes: dict, target_date: str, wa_only: bool = False, state: str = "") -> str:
    """Format changes as plain text for FB groups."""
    # --wa-only is an alias for --state WA
    filter_state = "WA" if wa_only else state

    lines = []
    lines.append(f"🌱 Nursery Stock Update — {target_date}")
    lines.append(f"via treestock.com.au")
    lines.append("")

    has_any = False

    for nursery_key, changes in sorted(all_changes.items()):
        if filter_state and not nursery_ships_to(nursery_key, filter_state):
            continue

        name = NURSERY_NAMES.get(nursery_key, nursery_key)

        sections = []

        if changes["back_in_stock"]:
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

        if changes["price_drops"]:
            items = []
            for item in changes["price_drops"]:
                link = f"\n    {item['url']}" if item.get("url") else ""
                items.append(f"  📉 {item['title']}: ${item['old_price']:.2f} → ${item['new_price']:.2f}{link}")
            sections.append(("Price drops", items))

        if changes["new_products"]:
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

    if not has_any:
        lines.append("No changes today — all quiet across the nurseries.")
        lines.append("")

    lines.append("—")
    lines.append("Full dashboard: https://treestock.com.au")
    lines.append(f"Tracking {len(SHIPPING_MAP)} nurseries daily.")

    return "\n".join(lines)


def _build_change_sections(all_changes: dict, wa_only: bool = False, state: str = "") -> tuple[list[str], bool]:
    """Build HTML sections for each nursery's changes. Returns (sections_html, has_any)."""
    filter_state = "WA" if wa_only else state
    sections_html = []
    has_any = False

    for nursery_key, changes in sorted(all_changes.items()):
        if filter_state and not nursery_ships_to(nursery_key, filter_state):
            continue

        name = NURSERY_NAMES.get(nursery_key, nursery_key)

        items_html = []

        for item in changes["back_in_stock"]:
            price = f" &mdash; ${item['price']:.2f}" if item["price"] else ""
            if item.get("old_price"):
                price += f" (was ${item['old_price']:.2f})"
            url = item.get("url", "")
            utm_url = url + ("&" if "?" in url else "?") + "utm_source=treestock&utm_medium=referral" if url else ""
            link = f'<a href="{utm_url}" target="_blank">{item["title"]}</a>' if url else item["title"]
            items_html.append(f'<li style="color:#059669;padding:4px 0"><span title="Was out of stock, now available again" style="cursor:help">✅</span> {link}{price} <strong>Back in stock!</strong></li>')

        for item in changes["price_drops"]:
            url = item.get("url", "")
            utm_url = url + ("&" if "?" in url else "?") + "utm_source=treestock&utm_medium=referral" if url else ""
            link = f'<a href="{utm_url}" target="_blank">{item["title"]}</a>' if url else item["title"]
            items_html.append(
                f'<li style="padding:4px 0"><span title="Price decreased" style="cursor:help">📉</span> {link}: '
                f'<span style="text-decoration:line-through;color:#999">${item["old_price"]:.2f}</span> '
                f'→ <strong style="color:#059669">${item["new_price"]:.2f}</strong></li>'
            )

        for item in changes["new_products"][:10]:
            price = f" &mdash; ${item['price']:.2f}" if item["price"] else ""
            url = item.get("url", "")
            utm_url = url + ("&" if "?" in url else "?") + "utm_source=treestock&utm_medium=referral" if url else ""
            link = f'<a href="{utm_url}" target="_blank">{item["title"]}</a>' if url else item["title"]
            items_html.append(f'<li style="padding:4px 0"><span title="Newly listed on the nursery website" style="cursor:help">🆕</span> {link}{price}</li>')
        extra = len(changes["new_products"]) - 10
        if extra > 0:
            items_html.append(f'<li style="padding:4px 0">... and {extra} more new listings</li>')

        if not items_html:
            continue

        has_any = True
        sections_html.append(
            f'<h3 style="margin:16px 0 8px">{name}</h3>'
            f'<ul style="list-style:none;padding:0;margin:0">{"".join(items_html)}</ul>'
        )

    return sections_html, has_any


def format_html(all_changes: dict, target_date: str, wa_only: bool = False, state: str = "") -> str:
    """Format changes as HTML for email (inline styles, no external deps)."""
    sections_html, has_any = _build_change_sections(all_changes, wa_only, state)

    if not has_any:
        sections_html.append('<p>No changes today — all quiet across the nurseries.</p>')

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:16px">
<h2 style="color:#065f46">🌱 Nursery Stock Update — {target_date}</h2>
{"".join(sections_html)}
<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.9em;color:#6b7280">
  <a href="https://treestock.com.au">Full dashboard</a> &bull;
  Tracking {len(SHIPPING_MAP)} nurseries daily.<br>
  Built by <a href="https://treestock.com.au">treestock.com.au</a>
</p>
</body></html>"""


def format_html_page(all_changes: dict, target_date: str, wa_only: bool = False, state: str = "") -> str:
    """Format changes as a shareable web page with proper styling and navigation."""
    filter_state = "WA" if wa_only else state
    sections_html, has_any = _build_change_sections(all_changes, wa_only, state)

    if not has_any:
        sections_html.append(
            '<div style="text-align:center;padding:48px 0;color:#9ca3af">'
            'No changes today — all quiet across the nurseries.</div>'
        )

    title_suffix = f" (Ships to {filter_state})" if filter_state else ""

    # Count changes by type for summary pills
    total_by_type = {}
    for nursery_key, changes in all_changes.items():
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

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nursery Stock Update — {target_date}{title_suffix} — treestock.com.au</title>
<meta name="description" content="Daily fruit nursery stock changes for {target_date}. Price drops, back in stock alerts, and new listings.">
<meta property="og:title" content="Nursery Stock Update — {target_date}">
<meta property="og:description" content="Daily price and stock changes across Australian fruit nurseries.">
<meta property="og:type" content="article">
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
<script defer data-domain="treestock.com.au" src="https://data.bjnoel.com/js/script.outbound-links.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
  a {{ color: #065f46; }}
  a:hover {{ text-decoration: underline; }}
  li {{ border-bottom: 1px solid #f3f4f6; }}
  li:last-child {{ border-bottom: none; }}
</style>
</head>
<body class="bg-white text-gray-900">

<header class="border-b border-gray-200 bg-white sticky top-0 z-10">
  <div class="max-w-2xl mx-auto px-4 py-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-green-800">
          <a href="/" class="hover:no-underline">treestock.com.au</a>
        </h1>
        <p class="text-sm text-gray-500">Nursery Stock Update{title_suffix}</p>
      </div>
      <div class="flex gap-2 text-sm">
        <a href="/" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 no-underline">Dashboard</a>
        <a href="/history.html" class="px-3 py-1 rounded border border-gray-300 hover:bg-gray-50 no-underline">History</a>
      </div>
    </div>
  </div>
</header>

<main class="max-w-2xl mx-auto px-4 py-6">
  <div class="mb-6">
    <h2 class="text-2xl font-bold text-green-900 mb-2">🌱 {target_date}</h2>
    <div class="flex flex-wrap gap-2">{pills_html}</div>
  </div>

  {"".join(sections_html)}

  <div class="mt-8 p-4 bg-green-50 rounded-lg text-sm text-green-800">
    <p class="font-medium mb-1">Get daily updates</p>
    <p>We track {len(SHIPPING_MAP)} Australian nurseries every day — price drops, restocks, new arrivals.</p>
    <p class="mt-2">
      <a href="/" class="font-medium">Search the dashboard →</a> &nbsp;|&nbsp;
      <a href="/history.html" class="font-medium">View price history →</a>
    </p>
  </div>
</main>

<footer class="border-t border-gray-200 mt-8 py-6 text-center text-xs text-gray-400">
  <p>Data scraped daily from public nursery websites. Prices and availability may change.</p>
</footer>

</body>
</html>"""


def load_all_changes(data_dir: Path, target_date: str) -> tuple[dict, int]:
    """Load and compare snapshots for a given date. Returns (all_changes, total_changes)."""
    prev_date = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    all_changes = {}
    total_changes = 0

    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        prev = load_snapshot(nursery_dir, prev_date)
        curr = load_snapshot(nursery_dir, target_date)
        if not prev or not curr:
            continue
        changes = compare_snapshots(prev, curr)
        nursery_key = nursery_dir.name
        all_changes[nursery_key] = changes
        total_changes += sum(len(v) for v in changes.values())

    return all_changes, total_changes


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
