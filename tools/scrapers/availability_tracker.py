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

        # Use URL as key to distinguish products with same title (e.g. different pot sizes)
        # Fall back to title for products without URLs
        product_key = p.get("url") or title

        available = p.get("any_available", p.get("available", False))
        price = p.get("min_price")
        if price is None:
            variants = p.get("variants", [])
            if variants:
                avail_prices = [float(v.get("price", 0)) for v in variants if v.get("price") and v.get("available", True)]
                all_prices = [float(v.get("price", 0)) for v in variants if v.get("price")]
                price = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)

        # Get or create product history
        if product_key not in history["products"]:
            history["products"][product_key] = {
                "title": title,
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
