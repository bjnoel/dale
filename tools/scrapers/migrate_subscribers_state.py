#!/usr/bin/env python3
"""
One-time migration: convert wa_only boolean to state field on subscribers.

wa_only=true → state="WA"
wa_only=false or missing → state="ALL"

Safe to re-run: skips subscribers that already have a state field.

Usage:
    python3 migrate_subscribers_state.py                  # Dry run
    python3 migrate_subscribers_state.py --apply           # Apply changes
"""

import json
import sys
from pathlib import Path

SUBSCRIBERS_FILE = Path("/opt/dale/data/subscribers.json")


def main():
    apply = "--apply" in sys.argv

    if not SUBSCRIBERS_FILE.exists():
        print(f"No subscribers file at {SUBSCRIBERS_FILE}")
        return

    with open(SUBSCRIBERS_FILE) as f:
        subscribers = json.load(f)

    migrated = 0
    for s in subscribers:
        if "state" in s:
            continue  # Already migrated
        if s.get("wa_only"):
            s["state"] = "WA"
        else:
            s["state"] = "ALL"
        s.pop("wa_only", None)
        migrated += 1

    print(f"Total subscribers: {len(subscribers)}")
    print(f"To migrate: {migrated}")

    if migrated == 0:
        print("Nothing to migrate.")
        return

    if not apply:
        print("\nDry run. Use --apply to save changes.")
        for s in subscribers:
            print(f"  {s['email']}: state={s.get('state', '?')}")
        return

    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(subscribers, f, indent=2)
    print(f"Migrated {migrated} subscribers. Saved to {SUBSCRIBERS_FILE}")


if __name__ == "__main__":
    main()
