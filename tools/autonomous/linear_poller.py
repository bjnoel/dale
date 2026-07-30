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

PAGE_SIZE = 50
MAX_PAGES = 20  # 1000 issues, far above any real Dale queue


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


class LinearAPIError(RuntimeError):
    """The Linear API could not be reached, or returned errors.

    Deliberately distinct from "the query succeeded and matched nothing".
    Collapsing the two is what caused the 2026-07-27 duplicate burst: a failed
    backlog fetch returned [], the runner read backlog_count 0, started a
    generation session with no duplicate-prevention list in the prompt, and
    Dale re-created 13 tickets it already had (DAL-224 through DAL-236).

    Callers must let this propagate rather than substituting an empty list.
    An empty list means "no tickets"; that claim must only ever be made about
    a request that actually succeeded.
    """


def graphql(query, variables=None):
    """Make a GraphQL request to the Linear API.

    Raises LinearAPIError on any failure. Never returns None to mean "failed".
    """
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
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        log(f"Linear API error ({e.code}): {error_body}")
        raise LinearAPIError(f"Linear API error ({e.code}): {error_body}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        log(f"Linear API unreachable: {e}")
        raise LinearAPIError(f"Linear API unreachable: {e}") from e
    except json.JSONDecodeError as e:
        log(f"Linear API returned non-JSON: {e}")
        raise LinearAPIError(f"Linear API returned non-JSON: {e}") from e

    if "errors" in result:
        log(f"GraphQL errors: {result['errors']}")
        raise LinearAPIError(f"GraphQL errors: {result['errors']}")

    data = result.get("data")
    if data is None:
        log("GraphQL response had no data field")
        raise LinearAPIError("GraphQL response had no data field")
    return data


def get_team_id(team_name):
    """Find the team ID by name."""
    data = graphql("""
        query($name: String!) {
            teams(filter: { name: { eq: $name } }) {
                nodes { id name }
            }
        }
    """, {"name": team_name})

    if not data["teams"]["nodes"]:
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

    Pages through the full result set. This used to stop at the first 50 issues
    ordered by updatedAt, which silently hid the least-recently-touched tickets
    from the duplicate-prevention list in the session prompt -- exactly the old
    tickets a new proposal is most likely to duplicate.

    Raises LinearAPIError if any page fails. Returning a short list on error
    would understate the backlog to every caller downstream.
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

    query = f"""
        query($teamId: ID!, $stateType: String!, $after: String{extra_args}) {{
            issues(
                includeArchived: {include_archived}
                filter: {{
                    team: {{ id: {{ eq: $teamId }} }}
                    state: {{ type: {{ eq: $stateType }} }}
                    {extra_filter}
                }}
                orderBy: updatedAt
                first: {PAGE_SIZE}
                after: $after
            ) {{
                pageInfo {{ hasNextPage endCursor }}
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
    """

    nodes = []
    cursor = None
    for _ in range(MAX_PAGES):
        data = graphql(query, {**variables, "after": cursor})
        page = data.get("issues")
        if page is None:
            raise LinearAPIError(f"No issues field in response for state '{state_type}'")
        nodes.extend(page.get("nodes", []))
        info = page.get("pageInfo") or {}
        if not info.get("hasNextPage") or not info.get("endCursor"):
            return nodes
        cursor = info["endCursor"]

    log(f"Hit MAX_PAGES ({MAX_PAGES}) fetching '{state_type}'; list may be truncated")
    return nodes


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
    try:
        poll()
    except LinearAPIError as e:
        # Exit non-zero and leave the previous tasks file untouched. A partial
        # or empty file here reads downstream as "no work, no backlog", which
        # is how the runner ends up generating tickets blind.
        log(f"Poll failed, keeping previous tasks file: {e}")
        print(f"Error: Linear poll failed: {e}", file=sys.stderr)
        sys.exit(1)


def poll():
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
        # Only ever written by a poll where every fetch succeeded. Consumers
        # that create tickets must refuse to act on a file without it.
        "poll_ok": True,
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

    # Write to file for session-prompt.py. Write to a temp file and rename so
    # a crash mid-write cannot leave truncated JSON that parses as no tickets.
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    tmp_path = TASKS_FILE + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(result, f, indent=2)
    os.replace(tmp_path, TASKS_FILE)

    log(f"Saved: {len(todo)} todo, {len(in_progress)} in progress, {len(backlog)}/{max_backlog} backlog, {len(cancelled)} cancelled, {len(completed)} completed")


if __name__ == "__main__":
    main()
