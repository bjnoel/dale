#!/usr/bin/env python3
"""
Daily Digest Generator for beestock.

Compares today's retailer snapshots with yesterday's and produces a
human-readable summary of changes. Outputs plain text, email HTML,
and shareable web page HTML.

Usage:
    python3 bee_daily_digest.py /path/to/bee-stock
    python3 bee_daily_digest.py /path/to/bee-stock --date 2026-03-20
    python3 bee_daily_digest.py /path/to/bee-stock --html
    python3 bee_daily_digest.py /path/to/bee-stock --page
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from bee_retailers import SHIPPING_MAP, RETAILER_NAMES, retailer_ships_to
from bee_categories import categorise_product, category_name
from beestock_layout import render_head, render_header, render_footer


def _variant_key(product_url: str, variant: dict) -> str:
    """Generate a unique key for a specific variant within a product."""
    base = product_url or ""
    sku = variant.get("sku")
    if sku:
        return f"{base}|sku:{sku}"
    vid = variant.get("id")
    if vid:
        return f"{base}|id:{vid}"
    vtitle = variant.get("title", "Default")
    return f"{base}|v:{vtitle}"


def _variant_display_title(product_title: str, variant_title: str) -> str:
    """Build a display title for a variant."""
    if not variant_title or variant_title in ("Default", "Default Title"):
        return product_title
    return f"{product_title} ({variant_title})"


def load_snapshot(retailer_dir: Path, target_date: str) -> dict:
    """Load a snapshot for a specific date, return product lookup by variant key."""
    snapshot = retailer_dir / f"{target_date}.json"
    if not snapshot.exists():
        return {}
    with open(snapshot) as f:
        data = json.load(f)
    products = {}

    for p in data.get("products", []):
        url = p.get("url", "")
        title = p.get("title", "")
        variants = p.get("variants", [])

        if not variants:
            key = url or title
            products[key] = p
        else:
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

        back_in_stock = available and not prev_available

        if back_in_stock:
            entry = {
                "title": title,
                "price": price,
                "url": product.get("url", ""),
            }
            if price and prev_price and abs(price - prev_price) > 0.01:
                entry["old_price"] = prev_price
            changes["back_in_stock"].append(entry)

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


def format_text(all_changes: dict, target_date: str, state: str = "") -> str:
    """Format changes as plain text for FB groups."""
    lines = []
    lines.append(f"Beekeeping Supply Price Update \u2014 {target_date}")
    lines.append(f"via beestock.com.au")
    lines.append("")

    has_any = False

    for retailer_key, changes in sorted(all_changes.items()):
        if state and not retailer_ships_to(retailer_key, state):
            continue

        name = RETAILER_NAMES.get(retailer_key, retailer_key)
        sections = []

        if changes["back_in_stock"]:
            items = []
            for item in changes["back_in_stock"]:
                price_str = ""
                if item.get("price"):
                    price_str = f" \u2014 ${item['price']:.2f}"
                    if item.get("old_price"):
                        price_str += f" (was ${item['old_price']:.2f})"
                items.append(f"  Back in stock: {item['title']}{price_str}")
            sections.append(("Back in stock", items))

        if changes["price_drops"]:
            items = []
            for item in changes["price_drops"]:
                items.append(f"  Price drop: {item['title']}: ${item['old_price']:.2f} -> ${item['new_price']:.2f}")
            sections.append(("Price drops", items))

        if changes["new_products"]:
            items = []
            for item in changes["new_products"][:10]:
                price_str = f" \u2014 ${item['price']:.2f}" if item["price"] else ""
                items.append(f"  New: {item['title']}{price_str}")
            extra = len(changes["new_products"]) - 10
            if extra > 0:
                items.append(f"  ... and {extra} more")
            sections.append(("New listings", items))

        if not sections:
            continue

        has_any = True
        lines.append(f"{name}")
        for section_name, items in sections:
            for item in items:
                lines.append(item)
        lines.append("")

    if not has_any:
        lines.append("No changes today. All quiet across the retailers.")
        lines.append("")

    lines.append("Full dashboard: https://beestock.com.au")
    lines.append(f"Tracking {len(SHIPPING_MAP)} retailers daily.")

    return "\n".join(lines)


def _build_change_sections(all_changes: dict, state: str = "") -> tuple[list[str], bool]:
    """Build HTML sections for each retailer's changes."""
    sections_html = []
    has_any = False

    for retailer_key, changes in sorted(all_changes.items()):
        if state and not retailer_ships_to(retailer_key, state):
            continue

        name = RETAILER_NAMES.get(retailer_key, retailer_key)
        items_html = []

        for item in changes["back_in_stock"]:
            price = f" &mdash; ${item['price']:.2f}" if item.get("price") else ""
            if item.get("old_price"):
                price += f" (was ${item['old_price']:.2f})"
            url = item.get("url", "")
            utm_url = url + ("&" if "?" in url else "?") + "utm_source=beestock&utm_medium=referral" if url else ""
            link = f'<a href="{utm_url}" target="_blank">{item["title"]}</a>' if url else item["title"]
            items_html.append(f'<li style="color:#059669;padding:4px 0">Back in stock: {link}{price}</li>')

        for item in changes["price_drops"]:
            url = item.get("url", "")
            utm_url = url + ("&" if "?" in url else "?") + "utm_source=beestock&utm_medium=referral" if url else ""
            link = f'<a href="{utm_url}" target="_blank">{item["title"]}</a>' if url else item["title"]
            items_html.append(
                f'<li style="padding:4px 0">Price drop: {link}: '
                f'<span style="text-decoration:line-through;color:#999">${item["old_price"]:.2f}</span> '
                f'-> <strong style="color:#059669">${item["new_price"]:.2f}</strong></li>'
            )

        for item in changes["new_products"][:10]:
            price = f" &mdash; ${item['price']:.2f}" if item.get("price") else ""
            url = item.get("url", "")
            utm_url = url + ("&" if "?" in url else "?") + "utm_source=beestock&utm_medium=referral" if url else ""
            link = f'<a href="{utm_url}" target="_blank">{item["title"]}</a>' if url else item["title"]
            items_html.append(f'<li style="padding:4px 0">New: {link}{price}</li>')
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


def format_html(all_changes: dict, target_date: str, state: str = "") -> str:
    """Format changes as HTML for email."""
    sections_html, has_any = _build_change_sections(all_changes, state)

    if not has_any:
        sections_html.append('<p>No changes today. All quiet across the retailers.</p>')

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:16px">
<h2 style="color:#92400e">Beekeeping Supply Update \u2014 {target_date}</h2>
{"".join(sections_html)}
<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.9em;color:#6b7280">
  <a href="https://beestock.com.au">Full dashboard</a> &bull;
  Tracking {len(SHIPPING_MAP)} retailers daily.<br>
  Built by <a href="https://beestock.com.au">beestock.com.au</a>
</p>
</body></html>"""


def format_html_page(
    all_changes: dict,
    target_date: str,
    state: str = "",
    prev_date: str = None,
    next_date: str = None,
) -> str:
    """Format changes as a shareable web page."""
    sections_html, has_any = _build_change_sections(all_changes, state)

    if not has_any:
        sections_html.append(
            '<div style="text-align:center;padding:48px 0;color:#9ca3af">'
            'No changes today. All quiet across the retailers.</div>'
        )

    # Count changes
    total_by_type = {}
    for retailer_key, changes in all_changes.items():
        if state and not retailer_ships_to(retailer_key, state):
            continue
        for cat, items in changes.items():
            if items:
                total_by_type[cat] = total_by_type.get(cat, 0) + len(items)

    pills = []
    pill_config = [
        ("back_in_stock", "Back in stock"),
        ("price_drops", "Price drops"),
        ("new_products", "New"),
    ]
    for key, label in pill_config:
        count = total_by_type.get(key, 0)
        if count > 0:
            pills.append(
                f'<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 12px;'
                f'border-radius:9999px;font-size:0.875rem;background:#f3f4f6">'
                f'{count} {label}</span>'
            )

    pills_html = " ".join(pills) if pills else ""

    # Prev/next navigation
    nav_parts = []
    if prev_date:
        nav_parts.append(
            f'<a href="/digest/{prev_date}.html" class="text-sm text-yellow-800 hover:underline">'
            f'&larr; {prev_date}</a>'
        )
    else:
        nav_parts.append('<span></span>')
    nav_parts.append(
        '<a href="/digest/" class="text-sm text-gray-500 hover:underline">All digests</a>'
    )
    if next_date:
        nav_parts.append(
            f'<a href="/digest/{next_date}.html" class="text-sm text-yellow-800 hover:underline">'
            f'{next_date} &rarr;</a>'
        )
    else:
        nav_parts.append('<span></span>')
    date_nav_html = (
        '<div class="flex items-center justify-between mb-4">'
        + "".join(nav_parts)
        + "</div>"
    )

    extra_style = """\
  a { color: #92400e; }
  a:hover { text-decoration: underline; }
  li { border-bottom: 1px solid #f3f4f6; }
  li:last-child { border-bottom: none; }"""

    head = render_head(
        title=f"Beekeeping Supply Update \u2014 {target_date} \u2014 beestock.com.au",
        description=f"Daily beekeeping supply price changes for {target_date}. Price drops, back in stock alerts, and new listings.",
        canonical_url=f"https://beestock.com.au/digest/{target_date}.html",
        extra_style=extra_style,
    )
    header = render_header(
        max_width="max-w-2xl",
        active_path="/digest.html",
    )
    footer = render_footer(max_width="max-w-2xl")

    return f"""{head}
{header}

<main class="max-w-2xl mx-auto px-4 py-6">
  {date_nav_html}
  <div class="mb-6">
    <h2 class="text-2xl font-bold text-yellow-900 mb-2">{target_date}</h2>
    <div class="flex flex-wrap gap-2">{pills_html}</div>
  </div>

  {"".join(sections_html)}

  <div class="mt-8 p-4 bg-yellow-50 rounded-lg text-sm text-yellow-800">
    <p class="font-medium mb-1">Track beekeeping supply prices</p>
    <p>We track {len(SHIPPING_MAP)} Australian beekeeping retailers every day.</p>
    <p class="mt-2">
      <a href="/" class="font-medium">Search the dashboard &rarr;</a>
    </p>
  </div>
</main>

{footer}

</body>
</html>"""


def build_digest_index(digest_dir: "Path") -> str:
    """Build an archive index page listing all dated digest pages."""
    from beestock_layout import render_head, render_header, render_footer

    # Collect all dated digest files
    entries = []
    for f in sorted(digest_dir.glob("*.html"), reverse=True):
        if f.stem == "index":
            continue
        try:
            date.fromisoformat(f.stem)  # validate it's a date
            entries.append(f.stem)
        except ValueError:
            continue

    rows_html = []
    for d in entries:
        rows_html.append(
            f'<li class="py-2 border-b border-gray-100 last:border-0">'
            f'<a href="/digest/{d}.html" class="text-yellow-800 hover:underline font-medium">{d}</a>'
            f"</li>"
        )

    if not rows_html:
        content = '<p class="text-gray-500">No digest pages yet.</p>'
    else:
        content = f'<ul class="divide-y divide-gray-100">{"".join(rows_html)}</ul>'

    extra_style = """\
  a { color: #92400e; }
  a:hover { text-decoration: underline; }"""

    head = render_head(
        title="Daily Digest Archive \u2014 beestock.com.au",
        description="Archive of daily beekeeping supply price change digests.",
        canonical_url="https://beestock.com.au/digest/",
        extra_style=extra_style,
    )
    header = render_header(max_width="max-w-2xl", active_path="/digest.html")
    footer = render_footer(max_width="max-w-2xl")

    return f"""{head}
{header}

<main class="max-w-2xl mx-auto px-4 py-6">
  <h2 class="text-2xl font-bold text-yellow-900 mb-4">Daily Digest Archive</h2>
  <p class="text-sm text-gray-500 mb-6">
    Daily price and stock changes across {len(SHIPPING_MAP)} Australian beekeeping retailers.
  </p>
  {content}
</main>

{footer}

</body>
</html>"""


def load_all_changes(data_dir: Path, target_date: str) -> tuple[dict, int]:
    """Load and compare snapshots for a given date."""
    prev_date = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    all_changes = {}
    total_changes = 0

    for retailer_dir in sorted(data_dir.iterdir()):
        if not retailer_dir.is_dir():
            continue
        prev = load_snapshot(retailer_dir, prev_date)
        curr = load_snapshot(retailer_dir, target_date)
        if not prev or not curr:
            continue
        changes = compare_snapshots(prev, curr)
        retailer_key = retailer_dir.name
        all_changes[retailer_key] = changes
        total_changes += sum(len(v) for v in changes.values())

    return all_changes, total_changes


def _update_sitemap_for_digests(digest_dir: "Path") -> None:
    """Add dated digest pages to the site sitemap.xml."""
    import re as _re
    sitemap = digest_dir.parent / "sitemap.xml"
    if not sitemap.exists():
        return

    content = sitemap.read_text()

    # Remove existing digest entries (both new /digest/ and old /archive/digest- paths)
    content = _re.sub(
        r'\s*<url>\s*<loc>https://beestock\.com\.au/digest(?:/[^<]*)?</loc>.*?</url>',
        '',
        content,
        flags=_re.DOTALL,
    )
    content = _re.sub(
        r'\s*<url>\s*<loc>https://beestock\.com\.au/archive/digest-[^<]+</loc>.*?</url>',
        '',
        content,
        flags=_re.DOTALL,
    )

    # Collect dated pages
    entries = []
    for f in sorted(digest_dir.glob("*.html"), reverse=True):
        if f.stem == "index":
            continue
        try:
            date.fromisoformat(f.stem)
            entries.append(f.stem)
        except ValueError:
            continue

    if not entries:
        return

    new_entries = ""
    for d in entries:
        priority = "0.7" if d == entries[0] else "0.4"
        new_entries += f"""
  <url>
    <loc>https://beestock.com.au/digest/{d}.html</loc>
    <lastmod>{d}</lastmod>
    <changefreq>never</changefreq>
    <priority>{priority}</priority>
  </url>"""
    # Also add index
    new_entries += f"""
  <url>
    <loc>https://beestock.com.au/digest/</loc>
    <lastmod>{entries[0]}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.5</priority>
  </url>"""

    content = content.replace("</urlset>", new_entries + "\n</urlset>")
    sitemap.write_text(content)
    print(f"Sitemap updated: {len(entries)} digest pages + index", file=sys.stderr)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate daily bee stock change digest")
    parser.add_argument("data_dir", nargs="?", help="Path to bee-stock directory")
    parser.add_argument("--date", help="Date to compare (default: today)", default=None)
    parser.add_argument("--html", action="store_true", help="Output HTML (email format)")
    parser.add_argument("--page", action="store_true", help="Output HTML (shareable web page)")
    parser.add_argument("--state", help="Filter to retailers shipping to this state")
    parser.add_argument("--save", help="Save output to file")
    parser.add_argument("--prev-date", help="Previous date for page navigation", default=None)
    parser.add_argument("--next-date", help="Next date for page navigation", default=None)
    parser.add_argument("--build-index", metavar="DIGEST_DIR",
                        help="Build archive index.html in the given digest directory")
    args = parser.parse_args()

    # Build-index mode: scan digest dir and write index.html + update sitemap
    if args.build_index:
        digest_dir = Path(args.build_index)
        if not digest_dir.exists():
            print(f"Error: {digest_dir} does not exist", file=sys.stderr)
            sys.exit(1)
        html = build_digest_index(digest_dir)
        out = digest_dir / "index.html"
        out.write_text(html)
        print(f"Digest index written to {out}", file=sys.stderr)
        # Update sitemap if it exists in the parent directory
        _update_sitemap_for_digests(digest_dir)
        return

    if not args.data_dir:
        parser.error("data_dir is required unless --build-index is used")

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    state = (args.state or "").upper() if args.state else ""
    target_date = args.date or date.today().isoformat()
    all_changes, total_changes = load_all_changes(data_dir, target_date)

    if args.page:
        output = format_html_page(
            all_changes, target_date, state=state,
            prev_date=args.prev_date,
            next_date=args.next_date,
        )
    elif args.html:
        output = format_html(all_changes, target_date, state=state)
    else:
        output = format_text(all_changes, target_date, state=state)

    if args.save:
        Path(args.save).write_text(output)
        print(f"Saved to {args.save}", file=sys.stderr)
    else:
        print(output)

    print(f"\n({total_changes} total changes across {len(all_changes)} retailers)", file=sys.stderr)


if __name__ == "__main__":
    main()
