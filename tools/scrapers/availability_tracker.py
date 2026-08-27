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


def snapshot_day(scrape: dict):
    """The date the snapshot was actually taken, from its own `scraped_at`.

    Returns an ISO date string, or None when the snapshot cannot say. Every
    scraper that writes a snapshot writes `scraped_at` (bigcommerce, csv_feed,
    daleys, ecwid, shopify, wix, woocommerce), so None means something is wrong
    rather than merely old, and the caller treats it as such.
    """
    raw = scrape.get("scraped_at")
    if not isinstance(raw, str) or len(raw) < 10:
        return None
    day = raw[:10]
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    return day


def update_nursery(nursery_dir: Path):
    """Update availability history for a single nursery.

    Skips a nursery whose latest.json is not from today. A failed scrape does
    not overwrite latest.json, so without this guard yesterday's stock enters
    the history stamped with today's date, prices included: 52 such days and
    24,567 such rows accumulated between 2026-03 and 2026-08-27, and one of
    them put a wrong sentence on a live tombstone (Cox's Orange Pippin claimed
    a 20 August last-seen when Garden Express was last reachable on the 17th).

    The date comes from the snapshot rather than from the clock deliberately.
    `date.today()` answers "when is this script running", which is not the
    question; `scraped_at` answers "when was this observed", which is.
    """
    latest_file = nursery_dir / "latest.json"
    avail_file = nursery_dir / "availability.json"

    if not latest_file.exists():
        return

    # Load today's scrape
    with open(latest_file) as f:
        scrape = json.load(f)

    nursery_key = nursery_dir.name
    today = date.today().isoformat()
    day = snapshot_day(scrape)

    # Fail closed. Losing a day of history is recoverable; fabricating one is
    # not, because nothing downstream can tell the two apart afterwards.
    if day is None:
        print(f"  {nursery_key}: SKIPPED, snapshot has no usable scraped_at")
        return
    if day != today:
        print(f"  {nursery_key}: SKIPPED, latest.json is from {day}, not {today} "
              f"(scrape failed tonight; not recording it as today's stock)")
        return

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
                    "first_seen": day,
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

            prod["days"][day] = day_entry
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
