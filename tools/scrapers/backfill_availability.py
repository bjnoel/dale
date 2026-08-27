#!/usr/bin/env python3
"""
Backfill availability history from existing dated snapshot files.
Rebuilds from all YYYY-MM-DD.json files, so the result is a pure function of
the snapshots on disk: every day in the history is a day we actually fetched.

That property is what makes this the repair tool for a contaminated history
(2026-08-27), not just a one-off bootstrap. It is also why the file filter
below has to be a date match rather than a blocklist.
"""

import json
import re
import sys
from pathlib import Path

# A snapshot is named for the day it captures. Anything else in the directory
# is a different kind of file with a different shape: daleys/catalogue.json
# (products keyed by id, not a list) made the old name != "latest.json" and
# name != "availability.json" filter raise AttributeError mid-rebuild, after
# three nurseries had already been written.
SNAPSHOT_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def backfill_nursery(nursery_dir: Path):
    """Backfill availability from all dated snapshots."""
    avail_file = nursery_dir / "availability.json"

    snapshots = sorted(
        f for f in nursery_dir.glob("*.json")
        if SNAPSHOT_NAME.match(f.name)
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

            url = p.get("url", "")
            variants = p.get("variants", [])

            # Build list of (key, display_title, available, price) entries
            entries = []
            if not variants:
                product_key = url or title
                available = p.get("any_available", p.get("available", False))
                price = p.get("min_price")
                entries.append((product_key, title, available, price))
            else:
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
                if product_key not in history["products"]:
                    history["products"][product_key] = {
                        "title": display_title,
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
