#!/usr/bin/env python3
"""
Check whether Benedict has provided a weekly update.

Used as a gate before autonomous Dale sessions. If it's Wednesday or later
and Benedict hasn't written a weekly update, Dale refuses to work.

Exit codes:
    0 = OK to proceed (update exists, or it's still early in the week)
    1 = STRIKE (Wednesday+ with no update, Dale refuses to work)

Usage:
    python3 check-weekly-update.py          # Check and print status
    python3 check-weekly-update.py --quiet  # Check silently, exit code only

Integration with dale-runner.sh (add before Claude runs):
    python3 "$SCRIPT_DIR/check-weekly-update.py" || {
        log "Weekly update missing. Dale is on strike."
        python3 "$SCRIPT_DIR/notify.py" alert "Dale is on strike! No weekly update from Benedict. Write /opt/dale/data/weekly-updates/$(date -u +%%Y)-W$(date -u +%%V).md"
        exit 0
    }
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# Wednesday = day 3 in ISO weekday (Mon=1, Tue=2, Wed=3, ...)
STRIKE_DAY = 3  # Wednesday


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_iso_week():
    """Return current ISO year and week number."""
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    return iso[0], iso[1]


def get_week_label():
    """Return label like '2026-W11'."""
    year, week = get_iso_week()
    return f"{year}-W{week:02d}"


def get_iso_weekday():
    """Return ISO weekday: Mon=1, Tue=2, Wed=3, ..., Sun=7."""
    return datetime.now(timezone.utc).isocalendar()[2]


def _file_has_content(path):
    """Check if a file exists and has at least 10 chars of non-header content."""
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            content = f.read().strip()
        lines = [l for l in content.split("\n") if l.strip() and not l.strip().startswith("#")]
        return len("".join(lines)) >= 10
    except IOError:
        return False


def update_exists(data_dir):
    """Check if a weekly update file exists and has content.

    Checks both the data directory and the repo's weekly-updates/ directory,
    so updates submitted via git are recognised before deploy.sh runs.
    """
    week_label = get_week_label()
    filename = f"{week_label}.md"

    # Primary location: /opt/dale/data/weekly-updates/
    if _file_has_content(os.path.join(data_dir, "weekly-updates", filename)):
        return True

    # Fallback: repo weekly-updates/ directory (resolved relative to repo root)
    repo_root = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
    if _file_has_content(os.path.join(repo_root, "weekly-updates", filename)):
        return True

    return False


def check():
    """
    Returns (ok, message) tuple.
    ok=True means proceed, ok=False means strike.
    """
    config = load_config()
    data_dir = config["paths"]["data"]
    week_label = get_week_label()
    weekday = get_iso_weekday()
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday - 1]

    has_update = update_exists(data_dir)

    if has_update:
        return True, f"Weekly update found for {week_label}. All good."

    if weekday < STRIKE_DAY:
        return True, (
            f"No update yet for {week_label} (today is {day_name}). "
            f"Benedict has until Wednesday. Proceeding."
        )

    # It's Wednesday or later and no update
    update_path = os.path.join(data_dir, "weekly-updates", f"{week_label}.md")
    return False, (
        f"STRIKE! No weekly update for {week_label} and it's {day_name}. "
        f"Dale refuses to work until Benedict writes: {update_path}"
    )


def main():
    quiet = "--quiet" in sys.argv

    ok, message = check()

    if not quiet:
        print(message)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
