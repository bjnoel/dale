#!/usr/bin/env python3
"""
Build a price/stock change history page from all available nursery snapshots.

Generates a single self-contained HTML page showing daily changes across
all nurseries, browsable by date. Designed to be shareable and linkable.

Usage:
    python3 build_history.py /path/to/nursery-stock /path/to/output/
    python3 build_history.py /path/to/nursery-stock /path/to/output/ --wa-only
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

# Reuse digest's comparison logic
from daily_digest import (
    WA_NURSERIES,
    NURSERY_NAMES,
    compare_snapshots,
    load_snapshot,
)
from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_footer


def get_available_dates(data_dir: Path) -> list[str]:
    """Find all dates that have snapshot data, sorted newest first."""
    import re
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    dates = set()
    for nursery_dir in data_dir.iterdir():
        if not nursery_dir.is_dir():
            continue
        for f in nursery_dir.glob("*.json"):
            if date_pattern.match(f.stem):
                dates.add(f.stem)
    return sorted(dates, reverse=True)


def build_history_data(data_dir: Path, wa_only: bool = False) -> list[dict]:
    """Build change data for all available date pairs."""
    dates = get_available_dates(data_dir)
    history = []

    for i, target_date in enumerate(dates):
        # Find previous date
        prev_date = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()

        day_changes = []
        total_changes = 0

        for nursery_dir in sorted(data_dir.iterdir()):
            if not nursery_dir.is_dir():
                continue
            nursery_key = nursery_dir.name
            if wa_only and nursery_key not in WA_NURSERIES:
                continue

            prev = load_snapshot(nursery_dir, prev_date)
            curr = load_snapshot(nursery_dir, target_date)
            if not prev or not curr:
                continue

            changes = compare_snapshots(prev, curr)
            n_changes = sum(len(v) for v in changes.values())
            if n_changes == 0:
                continue

            total_changes += n_changes
            nursery_data = {
                "key": nursery_key,
                "name": NURSERY_NAMES.get(nursery_key, nursery_key),
                "wa": nursery_key in WA_NURSERIES,
                "changes": {},
            }
            # Only include non-empty change categories
            for cat, items in changes.items():
                if items:
                    nursery_data["changes"][cat] = items
            day_changes.append(nursery_data)

        history.append({
            "date": target_date,
            "total": total_changes,
            "nurseries": day_changes,
        })

    return history


def build_html(history: list[dict], wa_only: bool = False) -> str:
    """Generate the history page HTML with embedded data."""
    history_json = json.dumps(history, separators=(",", ":"))
    title_suffix = " (Ships to WA)" if wa_only else ""

    extra_style = """\
  .change-card { border-left: 3px solid #d1d5db; }
  .change-card.has-changes { border-left-color: #059669; }
  .wa-badge { background: #fef3c7; color: #92400e; padding: 2px 6px; border-radius: 9999px; font-size: 0.7rem; }
  .day-header { cursor: pointer; }
  .day-header:hover { background: #f9fafb; }
  .change-item { padding: 4px 0; border-bottom: 1px solid #f3f4f6; }
  .change-item:last-child { border-bottom: none; }
  .back-in-stock { color: #059669; }
  .price-drop { color: #059669; }
  .price-up { color: #dc2626; }
  .sold-out { color: #6b7280; }
  .new-product { color: #1e40af; }
  .stat-pill { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px;
    border-radius: 9999px; font-size: 0.75rem; background: #f3f4f6; }"""

    head = render_head(
        title=f"Price &amp; Stock History{title_suffix} — treestock.com.au",
        description="Daily price changes and stock updates across Australian fruit nurseries.",
        extra_style=extra_style,
    )
    header = render_header(
        active_path="/history.html",
    )
    footer = render_footer()

    return render_template(
        "history_page.html.j2",
        head=head, header=header, footer=footer, history_json=history_json,
    )


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build price/stock change history page")
    parser.add_argument("data_dir", help="Path to nursery-stock directory")
    parser.add_argument("output_dir", help="Output directory for history.html")
    parser.add_argument("--wa-only", action="store_true", help="Only show WA-shipping nurseries")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    print(f"Building history from {data_dir}...")
    history = build_history_data(data_dir, wa_only=args.wa_only)

    total_changes = sum(d["total"] for d in history)
    active_days = sum(1 for d in history if d["total"] > 0)
    print(f"  {len(history)} days of data, {active_days} with changes, {total_changes} total changes")

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = "history-wa.html" if args.wa_only else "history.html"
    html = build_html(history, wa_only=args.wa_only)
    out_file = output_dir / filename
    out_file.write_text(html)
    print(f"History written to {out_file} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
