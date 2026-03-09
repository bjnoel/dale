#!/usr/bin/env python3
"""
Availability Tracker

Maintains a compact daily record of whether each product is in stock.
Designed to run after each scrape to build up historical availability data.

Data format (availability.json per nursery):
{
  "nursery": "daleys",
  "products": {
    "Product Title": {
      "first_seen": "2026-03-05",
      "days": {
        "2026-03-05": {"a": true, "p": 49.0},
        "2026-03-06": {"a": true, "p": 49.0},
        "2026-03-07": {"a": false},
        ...
      }
    }
  }
}

Each day entry is minimal:
  - "a": bool (available/in stock)
  - "p": float (price, only recorded when it changes from previous)

Usage:
  python3 availability_tracker.py /path/to/nursery-stock

Intended to be called from run-all-scrapers.sh after scraping completes.
"""

import json
import sys
from datetime import date
from pathlib import Path


def update_nursery(nursery_dir: Path):
    """Update availability history for a single nursery."""
    latest_file = nursery_dir / "latest.json"
    avail_file = nursery_dir / "availability.json"

    if not latest_file.exists():
        return

    # Load today's scrape
    with open(latest_file) as f:
        scrape = json.load(f)

    today = date.today().isoformat()
    nursery_key = nursery_dir.name

    # Load or create availability history
    if avail_file.exists():
        with open(avail_file) as f:
            history = json.load(f)
    else:
        history = {
            "nursery": nursery_key,
            "nursery_name": scrape.get("nursery_name", nursery_key),
            "products": {},
        }

    products = scrape.get("products", [])
    updated = 0
    new = 0

    for p in products:
        title = p.get("title", "")
        if not title:
            continue

        url = p.get("url", "")
        variants = p.get("variants", [])

        # Build list of (key, display_title, available, price) entries
        # All variants are flattened so each is tracked independently
        entries = []
        if not variants:
            # No variants (e.g. Ecwid flat products) — key by URL
            product_key = url or title
            available = p.get("any_available", p.get("available", False))
            price = p.get("min_price")
            entries.append((product_key, title, available, price))
        else:
            # Multi-variant: one entry per variant
            for v in variants:
                sku = v.get("sku")
                vid = v.get("id")
                vtitle = v.get("title", "Default")
                if sku:
                    vkey = f"{url}|sku:{sku}"
                elif vid:
                    vkey = f"{url}|id:{vid}"
                else:
                    vkey = f"{url}|v:{vtitle}"

                display = title
                if vtitle and vtitle not in ("Default", "Default Title"):
                    display = f"{title} ({vtitle})"

                vprice = v.get("price")
                if isinstance(vprice, str):
                    try:
                        vprice = float(vprice)
                    except (ValueError, TypeError):
                        vprice = None

                entries.append((vkey, display, bool(v.get("available", False)), vprice))

        for product_key, display_title, available, price in entries:
            # Get or create product history
            if product_key not in history["products"]:
                history["products"][product_key] = {
                    "title": display_title,
                    "first_seen": today,
                    "days": {},
                }
                new += 1

            prod = history["products"][product_key]
            day_entry = {"a": bool(available)}

            # Only record price if it changed from most recent entry
            if price is not None:
                prev_days = prod["days"]
                if prev_days:
                    # Find most recent day
                    last_day = max(prev_days.keys())
                    last_price = prev_days[last_day].get("p")
                    if last_price is None or abs(price - last_price) > 0.01:
                        day_entry["p"] = round(price, 2)
                else:
                    day_entry["p"] = round(price, 2)

            prod["days"][today] = day_entry
            updated += 1

    # Save
    with open(avail_file, "w") as f:
        json.dump(history, f, separators=(",", ":"))

    total_products = len(history["products"])
    total_days = len(set(
        day for prod in history["products"].values()
        for day in prod["days"]
    ))
    print(f"  {scrape.get('nursery_name', nursery_key)}: "
          f"{updated} updated, {new} new, "
          f"{total_products} total products, {total_days} days tracked")


def main():
    if len(sys.argv) < 2:
        print("Usage: availability_tracker.py <nursery-stock-dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist")
        sys.exit(1)

    print("Updating availability history...")
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        update_nursery(nursery_dir)


if __name__ == "__main__":
    main()
