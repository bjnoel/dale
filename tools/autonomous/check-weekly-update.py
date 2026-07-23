#!/usr/bin/env python3
"""
Engagement gate for autonomous Dale sessions.

Dale strikes only if there has been NO sign of Benedict for GRACE_DAYS
(default 28). Signs of Benedict, newest wins:

  1. A weekly-update file (weekly-updates/YYYY-WNN.md) that Benedict wrote
     himself, or a Dale auto-draft he signed off by deleting the
     auto-draft marker line. Files still containing the marker do not count.
  2. The engagement stamp at {data}/benedict-engagement.json, written by
     daily-digest.py whenever it sees non-Dale activity in Linear
     (ticket moves, comments). Can also be written manually to end a
     strike immediately.

This replaced the old weekly-writing gate (2026-07-23). That gate had a
loophole: Monday and Tuesday always passed regardless of staleness, so a
long-lapsed update meant Dale worked Mon-Tue and struck Wed-Sun forever.
The new gate applies every day of the week.

Exit codes:
    0 = OK to proceed
    1 = STRIKE (no engagement signal within GRACE_DAYS)

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

# Days without any engagement signal before Dale downs tools.
GRACE_DAYS = 28

# Dale's weekly auto-drafts carry this marker; Benedict signs one off by
# deleting the marker line. Drafts with the marker do not count as engagement.
AUTO_DRAFT_MARKER = "auto-drafted by Dale"

STAMP_FILENAME = "benedict-engagement.json"

FILENAME_RE = re.compile(r"^(\d{4})-W(\d{2})\.md$")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _counts_as_benedict(path):
    """A weekly-update file counts if it has real content and is not an
    unsigned Dale auto-draft."""
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            content = f.read().strip()
    except IOError:
        return False
    if AUTO_DRAFT_MARKER in content:
        return False
    lines = [l for l in content.split("\n") if l.strip() and not l.strip().startswith("#")]
    return len("".join(lines)) >= 10


def latest_update_week(data_dir, search_dirs=None):
    """Return (year, week) of the most recent Benedict-authored (or
    Benedict-signed-off) weekly-update file, or None.

    Scans both /opt/dale/data/weekly-updates/ and the repo's
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
            if not _counts_as_benedict(os.path.join(dir_path, name)):
                continue
            candidates.append((int(m.group(1)), int(m.group(2))))
    return max(candidates) if candidates else None


def read_engagement_stamp(data_dir):
    """Return the date of the last recorded Benedict engagement, or None.

    The stamp file is JSON: {"last_seen": "YYYY-MM-DD", "source": "..."}.
    """
    path = os.path.join(data_dir, STAMP_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            stamp = json.load(f)
        return date.fromisoformat(stamp["last_seen"][:10])
    except (IOError, ValueError, KeyError, TypeError):
        return None


def weeks_between(earlier, later):
    """Number of ISO weeks between two (year, week) tuples.

    Returns 0 if same week, positive if later is after earlier, negative otherwise.
    Handles ISO year boundaries (incl. 53-week years) by resolving each week to
    its Monday date and diffing days.
    """
    earlier_monday = date.fromisocalendar(earlier[0], earlier[1], 1)
    later_monday = date.fromisocalendar(later[0], later[1], 1)
    return (later_monday - earlier_monday).days // 7


def gate_decision(today, latest_week, stamp_date, grace_days=GRACE_DAYS):
    """Pure gate logic: given today's state, decide proceed vs. strike.

    Args:
        today: datetime.date for today.
        latest_week: (year, week) of most recent Benedict weekly update, or None.
        stamp_date: date of last Linear engagement stamp, or None.
        grace_days: days without any signal before striking.

    Returns:
        (ok: bool, message: str)
    """
    signals = []
    if latest_week is not None:
        signals.append(("weekly update %d-W%02d" % latest_week,
                        date.fromisocalendar(latest_week[0], latest_week[1], 1)))
    if stamp_date is not None:
        signals.append(("Linear activity", stamp_date))

    if not signals:
        return False, (
            "STRIKE! No engagement signal from Benedict at all "
            "(no weekly update, no Linear activity stamp). "
            "Dale refuses to work until Benedict shows signs of life."
        )

    label, latest = max(signals, key=lambda s: s[1])
    gap = (today - latest).days

    if gap <= grace_days:
        return True, (
            f"Benedict engaged {gap} day(s) ago ({label}). "
            f"Grace is {grace_days} days. Proceeding."
        )

    return False, (
        f"STRIKE! No sign of Benedict for {gap} days "
        f"(last: {label}, {latest.isoformat()}; grace is {grace_days} days). "
        f"Dale refuses to work until Benedict moves a Linear ticket, "
        f"writes a weekly update, or signs off the latest auto-draft."
    )


def check():
    """Return (ok, message). ok=True means proceed, ok=False means strike."""
    config = load_config()
    data_dir = config["paths"]["data"]
    return gate_decision(
        today=datetime.now(timezone.utc).date(),
        latest_week=latest_update_week(data_dir),
        stamp_date=read_engagement_stamp(data_dir),
    )


def main():
    quiet = "--quiet" in sys.argv
    ok, message = check()
    if not quiet:
        print(message)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
