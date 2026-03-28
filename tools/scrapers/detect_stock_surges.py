#!/usr/bin/env python3
"""Detect significant stock count changes across nurseries.

Compares today's in_stock_count with yesterday's for each nursery.
Sends an alert email to Benedict when any nursery has a big swing
(+/- 20% or absolute change of 10+).

Runs as part of the post-scraper pipeline in run-all-scrapers.sh.

Usage:
    python3 detect_stock_surges.py /opt/dale/data/nursery-stock
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Thresholds
PCT_THRESHOLD = 20    # 20% change triggers alert
ABS_THRESHOLD = 10    # or absolute change of 10+ items

SCRIPT_DIR = Path(__file__).parent


def load_snapshot_header(path):
    """Load just the header fields from a snapshot (not full product list)."""
    try:
        with open(path) as f:
            data = json.load(f)
        return {
            "nursery_name": data.get("nursery_name", ""),
            "product_count": data.get("product_count", 0),
            "in_stock_count": data.get("in_stock_count", 0),
            "out_of_stock_count": data.get("out_of_stock_count", 0),
            "scraped_at": data.get("scraped_at", ""),
        }
    except (json.JSONDecodeError, FileNotFoundError, KeyError):
        return None


def detect_surges(data_dir):
    """Compare today vs yesterday stock counts for all nurseries."""
    data_path = Path(data_dir)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    surges = []

    for nursery_dir in sorted(data_path.iterdir()):
        if not nursery_dir.is_dir():
            continue

        nursery_key = nursery_dir.name

        # Load today's data (latest.json)
        today_path = nursery_dir / "latest.json"
        today_data = load_snapshot_header(today_path)
        if not today_data:
            continue

        # Load yesterday's data
        yesterday_path = nursery_dir / f"{yesterday}.json"
        yesterday_data = load_snapshot_header(yesterday_path)
        if not yesterday_data:
            continue

        today_stock = today_data["in_stock_count"]
        yesterday_stock = yesterday_data["in_stock_count"]
        abs_change = today_stock - yesterday_stock

        if yesterday_stock > 0:
            pct_change = round((abs_change / yesterday_stock) * 100)
        elif today_stock > 0:
            pct_change = 100  # went from 0 to something
        else:
            continue  # 0 -> 0, skip

        if abs(pct_change) >= PCT_THRESHOLD or abs(abs_change) >= ABS_THRESHOLD:
            direction = "up" if abs_change > 0 else "down"
            surges.append({
                "nursery_key": nursery_key,
                "nursery_name": today_data["nursery_name"],
                "yesterday": yesterday_stock,
                "today": today_stock,
                "abs_change": abs_change,
                "pct_change": pct_change,
                "direction": direction,
                "total_products": today_data["product_count"],
            })

    return surges


def send_alert(surges):
    """Send email alert to Benedict about stock surges/drops."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "autonomous"))
    from notify import send_email

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Sort: biggest absolute changes first
    surges.sort(key=lambda s: abs(s["abs_change"]), reverse=True)

    # Build email
    rows_html = ""
    rows_text = []
    for s in surges:
        arrow = "\u2191" if s["direction"] == "up" else "\u2193"
        sign = "+" if s["abs_change"] > 0 else ""
        color = "#2e7d32" if s["direction"] == "up" else "#c62828"

        rows_html += (
            f'<tr style="border-bottom:1px solid #eee">'
            f'<td style="padding:6px 10px">{s["nursery_name"]}</td>'
            f'<td style="padding:6px 10px;text-align:right">{s["yesterday"]}</td>'
            f'<td style="padding:6px 10px;text-align:right;font-weight:bold;color:{color}">'
            f'{s["today"]}</td>'
            f'<td style="padding:6px 10px;text-align:right;color:{color}">'
            f'{sign}{s["abs_change"]} ({sign}{s["pct_change"]}%)</td>'
            f'</tr>'
        )
        rows_text.append(
            f"  {arrow} {s['nursery_name']}: {s['yesterday']} -> {s['today']} "
            f"({sign}{s['abs_change']}, {sign}{s['pct_change']}%)"
        )

    html = f"""<h2>Stock Movement Alert &mdash; {today}</h2>
<p>{len(surges)} nursery/ies with significant stock changes:</p>
<table style="font-family:monospace;font-size:13px;border-collapse:collapse;width:100%">
<tr style="border-bottom:2px solid #ddd;font-weight:bold">
<td style="padding:6px 10px">Nursery</td>
<td style="padding:6px 10px;text-align:right">Yesterday</td>
<td style="padding:6px 10px;text-align:right">Today</td>
<td style="padding:6px 10px;text-align:right">Change</td>
</tr>
{rows_html}
</table>
<p style="font-size:0.85em;color:#888;margin-top:16px">
Thresholds: {PCT_THRESHOLD}% change or {ABS_THRESHOLD}+ items.
<a href="https://treestock.com.au">treestock.com.au</a></p>"""

    text = f"Stock Movement Alert -- {today}\n\n" + "\n".join(rows_text)

    subject = f"Stock alert: {len(surges)} nursery changes -- {today}"
    send_email(subject, html, text)
    print(f"Stock surge alert sent: {len(surges)} nurseries")


def main():
    if len(sys.argv) < 2:
        print("Usage: detect_stock_surges.py <data_dir>")
        sys.exit(1)

    data_dir = sys.argv[1]
    surges = detect_surges(data_dir)

    if not surges:
        print("No significant stock changes detected.")
        return

    for s in surges:
        sign = "+" if s["abs_change"] > 0 else ""
        print(f"  {s['nursery_name']}: {s['yesterday']} -> {s['today']} "
              f"({sign}{s['abs_change']}, {sign}{s['pct_change']}%)")

    if "--dry-run" in sys.argv:
        print(f"[DRY RUN] Would send alert for {len(surges)} nurseries")
        return

    send_alert(surges)


if __name__ == "__main__":
    main()
