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

WA_NURSERIES = {"daleys", "primal-fruits", "guildford", "fruit-salad-trees", "diggers"}

NURSERY_NAMES = {
    "daleys": "Daleys Fruit Trees",
    "ross-creek": "Ross Creek Tropicals",
    "ladybird": "Ladybird Nursery",
    "fruitopia": "Fruitopia",
    "primal-fruits": "Primal Fruits Perth",
    "guildford": "Guildford Garden Centre",
    "fruit-salad-trees": "Fruit Salad Trees",
    "diggers": "The Diggers Club",
}


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


def load_snapshot(nursery_dir: Path, target_date: str) -> dict:
    """Load a snapshot for a specific date, return product lookup by URL/title."""
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
        key = p.get("url") or p.get("title", "")
        products[key] = p
    return products


def compare_snapshots(prev: dict, curr: dict) -> dict:
    """Compare two snapshots and return categorized changes."""
    changes = {
        "price_drops": [],
        "price_increases": [],
        "back_in_stock": [],
        "sold_out": [],
        "new_products": [],
        "removed": [],
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
        just_sold_out = not available and prev_available

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
        elif just_sold_out:
            changes["sold_out"].append({
                "title": title,
                "url": product.get("url", ""),
            })

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
            elif diff > 0.01:
                changes["price_increases"].append({
                    "title": title,
                    "old_price": prev_price,
                    "new_price": price,
                    "url": product.get("url", ""),
                })

    # Check for removed products
    for key in prev:
        if key not in curr:
            changes["removed"].append({
                "title": prev[key].get("title", key),
            })

    return changes


def format_text(all_changes: dict, target_date: str, wa_only: bool = False) -> str:
    """Format changes as plain text for FB groups."""
    lines = []
    lines.append(f"🌱 Nursery Stock Update — {target_date}")
    lines.append(f"via scion.exchange")
    lines.append("")

    has_any = False

    for nursery_key, changes in sorted(all_changes.items()):
        if wa_only and nursery_key not in WA_NURSERIES:
            continue

        name = NURSERY_NAMES.get(nursery_key, nursery_key)
        ships_wa = nursery_key in WA_NURSERIES

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

        if changes["sold_out"]:
            items = []
            for item in changes["sold_out"][:5]:
                items.append(f"  ❌ {item['title']}")
            extra = len(changes["sold_out"]) - 5
            if extra > 0:
                items.append(f"  ... and {extra} more")
            sections.append(("Sold out", items))

        if not sections:
            continue

        has_any = True
        wa_tag = " 🚛 Ships to WA" if ships_wa else ""
        lines.append(f"📦 {name}{wa_tag}")
        for section_name, items in sections:
            for item in items:
                lines.append(item)
        lines.append("")

    if not has_any:
        lines.append("No changes today — all quiet across the nurseries.")
        lines.append("")

    lines.append("—")
    lines.append("Full dashboard: https://stock.scion.exchange")
    lines.append("Tracking 8 nurseries, ~5,000 fruit & edible plants daily.")

    return "\n".join(lines)


def format_html(all_changes: dict, target_date: str, wa_only: bool = False) -> str:
    """Format changes as HTML for email."""
    sections_html = []

    has_any = False
    for nursery_key, changes in sorted(all_changes.items()):
        if wa_only and nursery_key not in WA_NURSERIES:
            continue

        name = NURSERY_NAMES.get(nursery_key, nursery_key)
        ships_wa = nursery_key in WA_NURSERIES

        items_html = []

        for item in changes["back_in_stock"]:
            price = f" &mdash; ${item['price']:.2f}" if item["price"] else ""
            url = item.get("url", "")
            link = f'<a href="{url}">{item["title"]}</a>' if url else item["title"]
            items_html.append(f'<li style="color:#059669">✅ {link}{price} <strong>Back in stock!</strong></li>')

        for item in changes["price_drops"]:
            url = item.get("url", "")
            link = f'<a href="{url}">{item["title"]}</a>' if url else item["title"]
            items_html.append(
                f'<li>📉 {link}: '
                f'<span style="text-decoration:line-through;color:#999">${item["old_price"]:.2f}</span> '
                f'→ <strong style="color:#059669">${item["new_price"]:.2f}</strong></li>'
            )

        for item in changes["new_products"][:10]:
            price = f" &mdash; ${item['price']:.2f}" if item["price"] else ""
            url = item.get("url", "")
            link = f'<a href="{url}">{item["title"]}</a>' if url else item["title"]
            items_html.append(f'<li>🆕 {link}{price}</li>')
        extra = len(changes["new_products"]) - 10
        if extra > 0:
            items_html.append(f'<li>... and {extra} more new listings</li>')

        for item in changes["sold_out"][:5]:
            items_html.append(f'<li style="color:#999">❌ {item["title"]} — sold out</li>')

        if not items_html:
            continue

        has_any = True
        wa_badge = ' <span style="background:#fef3c7;color:#92400e;padding:2px 6px;border-radius:4px;font-size:0.8em">Ships to WA</span>' if ships_wa else ""
        sections_html.append(
            f'<h3 style="margin:16px 0 8px">{name}{wa_badge}</h3>'
            f'<ul style="list-style:none;padding:0;margin:0">{"".join(items_html)}</ul>'
        )

    if not has_any:
        sections_html.append('<p>No changes today — all quiet across the nurseries.</p>')

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:16px">
<h2 style="color:#065f46">🌱 Nursery Stock Update — {target_date}</h2>
{"".join(sections_html)}
<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.9em;color:#6b7280">
  <a href="https://stock.scion.exchange">Full dashboard</a> &bull;
  Tracking 8 nurseries, ~5,000 fruit &amp; edible plants daily.<br>
  Built by <a href="https://scion.exchange">scion.exchange</a>
</p>
</body></html>"""


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate daily stock change digest")
    parser.add_argument("data_dir", help="Path to nursery-stock directory")
    parser.add_argument("--date", help="Date to compare (default: today)", default=None)
    parser.add_argument("--html", action="store_true", help="Output HTML instead of text")
    parser.add_argument("--wa-only", action="store_true", help="Only show WA-shipping nurseries")
    parser.add_argument("--save", help="Save output to file")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    target_date = args.date or date.today().isoformat()
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

        n_changes = sum(len(v) for v in changes.values())
        total_changes += n_changes

    if args.html:
        output = format_html(all_changes, target_date, wa_only=args.wa_only)
    else:
        output = format_text(all_changes, target_date, wa_only=args.wa_only)

    if args.save:
        Path(args.save).write_text(output)
        print(f"Saved to {args.save}", file=sys.stderr)
    else:
        print(output)

    print(f"\n({total_changes} total changes across {len(all_changes)} nurseries)", file=sys.stderr)


if __name__ == "__main__":
    main()
