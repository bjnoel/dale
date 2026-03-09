#!/usr/bin/env python3
"""
Backfill availability history from existing dated snapshot files.
Run once to populate history from all YYYY-MM-DD.json files.
"""

import json
import sys
from pathlib import Path


def backfill_nursery(nursery_dir: Path):
    """Backfill availability from all dated snapshots."""
    avail_file = nursery_dir / "availability.json"

    # Find all dated snapshots (not latest.json)
    snapshots = sorted(
        f for f in nursery_dir.glob("*.json")
        if f.name != "latest.json" and f.name != "availability.json"
    )

    if not snapshots:
        return

    history = {
        "nursery": nursery_dir.name,
        "nursery_name": "",
        "products": {},
    }

    for snapshot_file in snapshots:
        day = snapshot_file.stem  # e.g., "2026-03-05"

        with open(snapshot_file) as f:
            scrape = json.load(f)

        if not history["nursery_name"]:
            history["nursery_name"] = scrape.get("nursery_name", nursery_dir.name)

        for p in scrape.get("products", []):
            title = p.get("title", "")
            if not title:
                continue

            # Use URL as key to distinguish same-titled products
            product_key = p.get("url") or title

            available = p.get("any_available", p.get("available", False))
            price = p.get("min_price")
            if price is None:
                variants = p.get("variants", [])
                if variants:
                    avail_prices = [float(v.get("price", 0)) for v in variants if v.get("price") and v.get("available", True)]
                    all_prices = [float(v.get("price", 0)) for v in variants if v.get("price")]
                    price = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)

            if product_key not in history["products"]:
                history["products"][product_key] = {
                    "title": title,
                    "first_seen": day,
                    "days": {},
                }

            prod = history["products"][product_key]
            day_entry = {"a": bool(available)}

            # Only record price if changed
            if price is not None:
                prev_days = {k: v for k, v in prod["days"].items() if k < day}
                if prev_days:
                    last_day = max(prev_days.keys())
                    last_price = prev_days[last_day].get("p")
                    if last_price is None or abs(price - last_price) > 0.01:
                        day_entry["p"] = round(price, 2)
                else:
                    day_entry["p"] = round(price, 2)

            prod["days"][day] = day_entry

    # Save
    with open(avail_file, "w") as f:
        json.dump(history, f, separators=(",", ":"))

    total_products = len(history["products"])
    days_tracked = len(set(
        day for prod in history["products"].values()
        for day in prod["days"]
    ))
    print(f"  {history['nursery_name']}: {total_products} products, "
          f"{days_tracked} days, {len(snapshots)} snapshots")


def main():
    if len(sys.argv) < 2:
        print("Usage: backfill_availability.py <nursery-stock-dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    print("Backfilling availability history...")
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        backfill_nursery(nursery_dir)
    print("Done.")


if __name__ == "__main__":
    main()
