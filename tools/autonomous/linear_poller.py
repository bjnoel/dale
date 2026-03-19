#!/usr/bin/env python3
"""
Linear task poller for Dale.

Fetches issues from the Dale team in Linear and writes them to a JSON file
that session-prompt.py reads. Runs pre-session (called by dale-runner.sh).

Usage: python3 linear_poller.py [--dry-run]
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
SECRETS_DIR = "/opt/dale/secrets"
TASKS_FILE = "/opt/dale/data/linear-tasks.json"
LOG_FILE = os.path.join(SCRIPT_DIR, "logs", "linear-poller.log")

GRAPHQL_URL = "https://api.linear.app/graphql"


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} linear-poller: {msg}\n"
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line)


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_token():
    env_path = os.path.join(SECRETS_DIR, "linear.env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("LINEAR_API_TOKEN="):
                return line.split("=", 1)[1]
    raise ValueError("LINEAR_API_TOKEN not found in linear.env")


def graphql(query, variables=None):
    """Make a GraphQL request to the Linear API."""
    token = get_token()
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")

    req = urllib.request.Request(GRAPHQL_URL, data=body, method="POST", headers={
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "dale-autonomous/2.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            if "errors" in result:
                log(f"GraphQL errors: {result['errors']}")
                return None
            return result.get("data")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        log(f"Linear API error ({e.code}): {error_body}")
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        log(f"Linear API unreachable: {e}")
        return None


def get_team_id(team_name):
    """Find the team ID by name."""
    data = graphql("""
        query($name: String!) {
            teams(filter: { name: { eq: $name } }) {
                nodes { id name }
            }
        }
    """, {"name": team_name})

    if not data or not data["teams"]["nodes"]:
        return None
    return data["teams"]["nodes"][0]["id"]


def get_issues_by_state(team_id, state_type):
    """Fetch issues for a team filtered by state type (backlog, unstarted, started, completed)."""
    data = graphql("""
        query($teamId: String!, $stateType: String!) {
            issues(
                filter: {
                    team: { id: { eq: $teamId } }
                    state: { type: { eq: $stateType } }
                }
                orderBy: updatedAt
                first: 50
            ) {
                nodes {
                    id
                    identifier
                    title
                    description
                    priority
                    createdAt
                    updatedAt
                    state { name type }
                    assignee { name email }
                    labels { nodes { name } }
                }
            }
        }
    """, {"teamId": team_id, "stateType": state_type})

    if not data or not data.get("issues"):
        return []
    return data["issues"]["nodes"]


def format_issue(issue):
    """Convert a Linear issue node to a simplified dict."""
    labels = [l["name"] for l in issue.get("labels", {}).get("nodes", [])]
    assignee = issue.get("assignee")
    priority_map = {0: "None", 1: "Urgent", 2: "High", 3: "Normal", 4: "Low"}

    return {
        "id": issue["identifier"],
        "title": issue["title"],
        "description": (issue.get("description") or "")[:500],
        "state": issue["state"]["name"],
        "state_type": issue["state"]["type"],
        "priority": priority_map.get(issue.get("priority", 0), "Normal"),
        "priority_num": issue.get("priority", 0),
        "labels": labels,
        "assignee": assignee["name"] if assignee else None,
        "created": issue["createdAt"],
        "updated": issue["updatedAt"],
    }


def main():
    dry_run = "--dry-run" in sys.argv
    config = load_config()
    team_name = config.get("linear", {}).get("team", "Dale")
    max_backlog = config.get("linear", {}).get("max_backlog", 20)

    log(f"Fetching Linear issues for team: {team_name}")

    team_id = get_team_id(team_name)
    if not team_id:
        log(f"Team '{team_name}' not found in Linear")
        print(f"Error: Team '{team_name}' not found", file=sys.stderr)
        sys.exit(1)

    # Fetch issues by state type
    todo_raw = get_issues_by_state(team_id, "unstarted")      # Todo
    in_progress_raw = get_issues_by_state(team_id, "started")  # In Progress
    backlog_raw = get_issues_by_state(team_id, "backlog")      # Backlog

    todo = [format_issue(i) for i in todo_raw]
    in_progress = [format_issue(i) for i in in_progress_raw]
    backlog = [format_issue(i) for i in backlog_raw]

    # Sort by priority (1=Urgent first)
    todo.sort(key=lambda x: x["priority_num"])
    in_progress.sort(key=lambda x: x["priority_num"])

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "team": team_name,
        "team_id": team_id,
        "todo": todo,
        "in_progress": in_progress,
        "backlog_count": len(backlog),
        "max_backlog": max_backlog,
        "backlog_full": len(backlog) >= max_backlog,
    }

    if dry_run:
        print(json.dumps(result, indent=2))
        log(f"Dry run: {len(todo)} todo, {len(in_progress)} in progress, {len(backlog)}/{max_backlog} backlog")
        return

    # Write to file for session-prompt.py
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        json.dump(result, f, indent=2)

    log(f"Saved: {len(todo)} todo, {len(in_progress)} in progress, {len(backlog)}/{max_backlog} backlog")


if __name__ == "__main__":
    main()
