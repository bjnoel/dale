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
from datetime import datetime, timedelta, timezone

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


def get_issues_by_state(team_id, state_type, since_days=None):
    """Fetch issues for a team filtered by state type.

    Valid state_type values (Linear WorkflowStateType enum, American spelling):
    backlog, unstarted, started, completed, canceled.

    When since_days is set, also include archived issues whose updatedAt is
    within the last N days. This is used for completed/canceled lists so the
    session prompt keeps seeing recent done/cancelled tickets even after the
    auto-archiver runs.
    """
    variables = {"teamId": team_id, "stateType": state_type}
    extra_filter = ""
    extra_args = ""
    if since_days is not None:
        since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        variables["since"] = since
        extra_filter = "updatedAt: { gte: $since }"
        extra_args = ", $since: DateTimeOrDuration!"
    include_archived = "true" if since_days is not None else "false"

    data = graphql(f"""
        query($teamId: ID!, $stateType: String!{extra_args}) {{
            issues(
                includeArchived: {include_archived}
                filter: {{
                    team: {{ id: {{ eq: $teamId }} }}
                    state: {{ type: {{ eq: $stateType }} }}
                    {extra_filter}
                }}
                orderBy: updatedAt
                first: 50
            ) {{
                nodes {{
                    id
                    identifier
                    title
                    description
                    priority
                    createdAt
                    updatedAt
                    state {{ name type }}
                    assignee {{ name email }}
                    labels {{ nodes {{ name }} }}
                    comments(first: 10) {{
                        nodes {{
                            body
                            createdAt
                            user {{ name }}
                        }}
                    }}
                }}
            }}
        }}
    """, variables)

    if not data or not data.get("issues"):
        return []
    return data["issues"]["nodes"]


def format_issue_title_only(issue):
    """Minimal format for cancelled/completed tickets -- just enough for duplicate detection."""
    return {
        "id": issue["identifier"],
        "title": issue["title"],
    }


def format_issue(issue):
    """Convert a Linear issue node to a simplified dict."""
    labels = [l["name"] for l in issue.get("labels", {}).get("nodes", [])]
    assignee = issue.get("assignee")
    priority_map = {0: "None", 1: "Urgent", 2: "High", 3: "Normal", 4: "Low"}

    # Extract comments (newest first)
    comments = []
    for c in issue.get("comments", {}).get("nodes", []):
        user = c.get("user", {}).get("name", "Unknown")
        comments.append({
            "author": user,
            "body": (c.get("body") or "")[:300],
            "created": c.get("createdAt", ""),
        })

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
        "comments": comments,
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

    # Fetch cancelled/completed for duplicate prevention.
    # Use "canceled" (American spelling — Linear's WorkflowStateType enum value).
    # Pass since_days so the auto-archiver does not hide recent context from the
    # session prompt: includeArchived is enabled and the window covers the
    # archive horizon plus a margin.
    cancelled_raw = get_issues_by_state(team_id, "canceled", since_days=90)
    completed_raw = get_issues_by_state(team_id, "completed", since_days=90)

    # Filter Todo/In Progress to only tickets Dale should work on:
    # - Has "Dale" label, OR
    # - Is unassigned
    # Tickets assigned to Benedict without "Dale" label are his to handle.
    def is_dale_ticket(issue):
        labels = [l["name"] for l in issue.get("labels", {}).get("nodes", [])]
        assignee = issue.get("assignee")
        if "Dale" in labels:
            return True
        if assignee is None:
            return True
        return False

    todo_raw = [i for i in todo_raw if is_dale_ticket(i)]
    in_progress_raw = [i for i in in_progress_raw if is_dale_ticket(i)]

    todo = [format_issue(i) for i in todo_raw]
    in_progress = [format_issue(i) for i in in_progress_raw]
    backlog = [format_issue(i) for i in backlog_raw]
    cancelled = [format_issue_title_only(i) for i in cancelled_raw]
    completed = [format_issue_title_only(i) for i in completed_raw]

    # Sort by priority (1=Urgent first)
    todo.sort(key=lambda x: x["priority_num"])
    in_progress.sort(key=lambda x: x["priority_num"])

    result = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "team": team_name,
        "team_id": team_id,
        "todo": todo,
        "in_progress": in_progress,
        "backlog": backlog,
        "backlog_count": len(backlog),
        "max_backlog": max_backlog,
        "backlog_full": len(backlog) >= max_backlog,
        "cancelled": cancelled,
        "completed": completed,
    }

    if dry_run:
        print(json.dumps(result, indent=2))
        log(f"Dry run: {len(todo)} todo, {len(in_progress)} in progress, {len(backlog)}/{max_backlog} backlog")
        return

    # Write to file for session-prompt.py
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        json.dump(result, f, indent=2)

    log(f"Saved: {len(todo)} todo, {len(in_progress)} in progress, {len(backlog)}/{max_backlog} backlog, {len(cancelled)} cancelled, {len(completed)} completed")


if __name__ == "__main__":
    main()
