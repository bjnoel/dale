#!/usr/bin/env python3
"""Auto-draft the previous week's update file.

Runs Mondays (cron). If weekly-updates/YYYY-WNN.md for the just-finished
ISO week doesn't exist yet (in /opt/dale/data/weekly-updates/ or the repo),
drafts one from Linear activity and git commits over that week.

The draft carries the auto-draft marker line, so it does NOT count as
Benedict engagement for the strike gate (check-weekly-update.py). Benedict
signs it off by deleting the marker line, or replaces it with his own note.
Either way the historical record stays continuous.

Usage: python3 weekly_update_draft.py [--dry-run]
"""

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
SECRETS_DIR = "/opt/dale/secrets"
GRAPHQL_URL = "https://api.linear.app/graphql"

AUTO_DRAFT_MARKER = "auto-drafted by Dale"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_linear_token():
    with open(os.path.join(SECRETS_DIR, "linear.env")) as f:
        for line in f:
            line = line.strip()
            if line.startswith("LINEAR_API_TOKEN="):
                return line.split("=", 1)[1]
    raise ValueError("LINEAR_API_TOKEN not found")


def graphql(query, variables):
    import urllib.request

    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(GRAPHQL_URL, data=body, method="POST", headers={
        "Authorization": get_linear_token(),
        "Content-Type": "application/json",
        "User-Agent": "dale-weekly-draft/1.0",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    if "errors" in result:
        raise RuntimeError(f"GraphQL errors: {result['errors']}")
    return result["data"]


def previous_iso_week(today=None):
    """Return (year, week, monday, sunday) for the ISO week before today's."""
    today = today or datetime.now(timezone.utc).date()
    monday_this_week = today - timedelta(days=today.isoweekday() - 1)
    monday = monday_this_week - timedelta(days=7)
    sunday = monday + timedelta(days=6)
    iso = monday.isocalendar()
    return iso[0], iso[1], monday, sunday


def linear_completed(team_name, start, end):
    data = graphql("""
        query($team: String!) {
            issues(
                filter: {
                    team: { name: { eq: $team } }
                    state: { type: { eq: "completed" } }
                }
                orderBy: updatedAt
                first: 50
            ) {
                nodes { identifier title completedAt }
            }
        }
    """, {"team": team_name})
    out = []
    for i in data["issues"]["nodes"]:
        done = (i.get("completedAt") or "")[:10]
        if done and start.isoformat() <= done <= end.isoformat():
            out.append(f"{i['identifier']} {i['title']}")
    return out


def git_commit_subjects(repo_dir, start, end):
    result = subprocess.run(
        ["git", "-C", repo_dir, "log",
         f"--since={start.isoformat()}T00:00:00Z",
         f"--until={end.isoformat()}T23:59:59Z",
         "--format=%s"],
        capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return []
    return [l for l in result.stdout.splitlines() if l.strip()]


def build_draft(label, monday, sunday, tickets, commits):
    lines = [
        f"# Week {label} ({monday} to {sunday})",
        "",
        f"<!-- {AUTO_DRAFT_MARKER}: delete this line to sign off, or replace "
        "the file with your own note. Unsigned drafts don't count as "
        "engagement for the strike gate. -->",
        "",
    ]
    if tickets:
        lines.append("## Shipped (Linear)")
        lines += [f"- {t}" for t in tickets]
        lines.append("")
    if commits:
        lines.append("## Commits")
        lines += [f"- {c}" for c in commits[:20]]
        if len(commits) > 20:
            lines.append(f"- ...and {len(commits) - 20} more")
        lines.append("")
    if not tickets and not commits:
        lines.append("Quiet week: no Linear tickets completed and no commits.")
        lines.append("")
    lines.append("## Benedict's notes")
    lines.append("")
    lines.append("(nothing yet)")
    lines.append("")
    return "\n".join(lines)


def main():
    dry_run = "--dry-run" in sys.argv
    config = load_config()
    data_dir = config["paths"]["data"]
    repo_dir = config["paths"].get("repo", "/opt/dale/repo")
    team_name = config.get("linear", {}).get("team", "Dale")

    year, week, monday, sunday = previous_iso_week()
    label = f"{year}-W{week:02d}"
    filename = f"{label}.md"

    for existing_dir in (os.path.join(data_dir, "weekly-updates"),
                         os.path.join(repo_dir, "weekly-updates")):
        if os.path.exists(os.path.join(existing_dir, filename)):
            print(f"{filename} already exists in {existing_dir}, nothing to do")
            return

    try:
        tickets = linear_completed(team_name, monday, sunday)
    except Exception as e:
        print(f"Warning: Linear fetch failed ({e}), drafting without tickets")
        tickets = []
    commits = git_commit_subjects(repo_dir, monday, sunday)

    draft = build_draft(label, monday, sunday, tickets, commits)
    if dry_run:
        print(draft)
        return

    out_dir = os.path.join(data_dir, "weekly-updates")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, filename)
    with open(out_path, "w") as f:
        f.write(draft)
    print(f"Drafted {out_path} ({len(tickets)} tickets, {len(commits)} commits)")


if __name__ == "__main__":
    main()
