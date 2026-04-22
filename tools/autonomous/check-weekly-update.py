#!/usr/bin/env python3
"""
Check whether Benedict has provided a weekly update.

Used as a gate before autonomous Dale sessions. If it's Wednesday or later
and there hasn't been a weekly update within the grace period (2 ISO weeks),
Dale refuses to work.

Exit codes:
    0 = OK to proceed (update within grace period, or still early in the week)
    1 = STRIKE (Wednesday+ with no recent update, Dale refuses to work)

Usage:
    python3 check-weekly-update.py          # Check and print status
    python3 check-weekly-update.py --quiet  # Check silently, exit code only
"""

import json
import os
import re
import sys
from datetime import date, datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
REPO_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))

# Wednesday = day 3 in ISO weekday (Mon=1, Tue=2, Wed=3, ...)
STRIKE_DAY = 3

# Number of ISO weeks of grace. If the most recent weekly update is this many
# weeks ago or less, Dale keeps working. 2 weeks means a Sunday update covers
# the next two Wednesdays without striking.
GRACE_WEEKS = 2

FILENAME_RE = re.compile(r"^(\d{4})-W(\d{2})\.md$")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_iso_week_today():
    """Return current (year, week) tuple."""
    iso = datetime.now(timezone.utc).isocalendar()
    return iso[0], iso[1]


def get_iso_weekday():
    """Return ISO weekday: Mon=1, Tue=2, Wed=3, ..., Sun=7."""
    return datetime.now(timezone.utc).isocalendar()[2]


def week_label(year_week):
    year, week = year_week
    return f"{year}-W{week:02d}"


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


def latest_update_week(data_dir, search_dirs=None):
    """Return (year, week) of the most recent weekly-update file, or None.

    By default scans both /opt/dale/data/weekly-updates/ and the repo's
    weekly-updates/ directory, so updates submitted via git count before
    deploy.sh runs. Tests can pass an explicit `search_dirs` list to isolate.
    """
    if search_dirs is None:
        search_dirs = [
            os.path.join(data_dir, "weekly-updates"),
            os.path.join(REPO_ROOT, "weekly-updates"),
        ]
    candidates = []
    for dir_path in search_dirs:
        if not os.path.isdir(dir_path):
            continue
        for name in os.listdir(dir_path):
            m = FILENAME_RE.match(name)
            if not m:
                continue
            if not _file_has_content(os.path.join(dir_path, name)):
                continue
            candidates.append((int(m.group(1)), int(m.group(2))))
    return max(candidates) if candidates else None


def weeks_between(earlier, later):
    """Number of ISO weeks between two (year, week) tuples.

    Returns 0 if same week, positive if later is after earlier, negative otherwise.
    Handles ISO year boundaries (incl. 53-week years) by resolving each week to
    its Monday date and diffing days.
    """
    earlier_monday = date.fromisocalendar(earlier[0], earlier[1], 1)
    later_monday = date.fromisocalendar(later[0], later[1], 1)
    return (later_monday - earlier_monday).days // 7


def gate_decision(current_week, weekday, latest_week, grace_weeks=GRACE_WEEKS):
    """Pure gate logic: given today's state, decide proceed vs. strike.

    Args:
        current_week: (year, week) tuple for today.
        weekday: ISO weekday (Mon=1 .. Sun=7).
        latest_week: (year, week) of most recent weekly update, or None.
        grace_weeks: number of ISO weeks of grace before striking.

    Returns:
        (ok: bool, message: str)
    """
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday"][weekday - 1]
    current_label = week_label(current_week)

    if latest_week == current_week:
        return True, f"Weekly update found for {current_label}. All good."

    if latest_week is not None:
        gap = weeks_between(latest_week, current_week)
        if 0 <= gap <= grace_weeks:
            return True, (
                f"Grace period: most recent update is {week_label(latest_week)} "
                f"({gap} week(s) ago, grace={grace_weeks}). Proceeding."
            )

    if weekday < STRIKE_DAY:
        return True, (
            f"No update yet for {current_label} (today is {day_name}). "
            f"Benedict has until Wednesday. Proceeding."
        )

    latest_desc = week_label(latest_week) if latest_week else "never"
    return False, (
        f"STRIKE! No weekly update within {grace_weeks} weeks "
        f"(latest: {latest_desc}) and it's {day_name}. "
        f"Dale refuses to work until Benedict writes weekly-updates/{current_label}.md"
    )


def check():
    """Return (ok, message). ok=True means proceed, ok=False means strike."""
    config = load_config()
    data_dir = config["paths"]["data"]
    return gate_decision(
        current_week=get_iso_week_today(),
        weekday=get_iso_weekday(),
        latest_week=latest_update_week(data_dir),
    )


def main():
    quiet = "--quiet" in sys.argv
    ok, message = check()
    if not quiet:
        print(message)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
