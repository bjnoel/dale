#!/usr/bin/env python3
"""
Notion task poller for Dale.

Polls a Notion database for new tasks from Benedict. When changes settle
(no new edits for one poll cycle), triggers an autonomous Dale session.

Cron: every 2 minutes.
Usage: python3 notion_poller.py [--dry-run]

Flow:
  1. Query Notion for tasks with Status = "New"
  2. If none: clear pending state, exit
  3. If new tasks found: record timestamp of latest edit
  4. If pending tasks exist AND no new changes since last poll: trigger Dale
  5. If Dale is already running (PID file): skip trigger, Dale will pick them up
"""

import json
import os
import sys
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SECRETS_DIR = "/opt/dale/secrets"
STATE_FILE = "/opt/dale/data/notion-poller-state.json"
TASKS_FILE = "/opt/dale/data/notion-tasks.json"
PID_FILE = os.path.join(SCRIPT_DIR, "logs", "dale-session.pid")
LOG_FILE = os.path.join(SCRIPT_DIR, "logs", "notion-poller.log")
DATABASE_ID = "3227f8d53f8e804c9140fac60798b15f"
NOTION_VERSION = "2022-06-28"


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} notion-poller: {msg}\n"
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line)


def get_token():
    env_path = os.path.join(SECRETS_DIR, "notion.env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("NOTION_API_TOKEN="):
                return line.split("=", 1)[1]
    raise ValueError("NOTION_API_TOKEN not found in notion.env")


def notion_api(method, endpoint, body=None):
    """Make a request to the Notion API."""
    token = get_token()
    url = f"https://api.notion.com/v1{endpoint}"
    data = json.dumps(body).encode("utf-8") if body else None

    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "dale-autonomous/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        log(f"Notion API error ({e.code}): {error_body}")
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        log(f"Notion API unreachable: {e}")
        return None


def get_new_tasks():
    """Query Notion for tasks with Status = New."""
    result = notion_api("POST", f"/databases/{DATABASE_ID}/query", {
        "filter": {
            "property": "Status",
            "select": {"equals": "New"}
        },
        "sorts": [
            {"property": "Priority", "direction": "ascending"},
            {"timestamp": "created_time", "direction": "ascending"}
        ]
    })

    if not result or "results" not in result:
        return []

    tasks = []
    for page in result["results"]:
        props = page["properties"]
        task_title = ""
        if props.get("Task", {}).get("title"):
            task_title = "".join(t["plain_text"] for t in props["Task"]["title"])

        priority = props.get("Priority", {}).get("select", {})
        priority_name = priority.get("name", "Normal") if priority else "Normal"

        tasks.append({
            "id": page["id"],
            "task": task_title,
            "priority": priority_name,
            "created": page["created_time"],
            "last_edited": page["last_edited_time"],
        })

    return tasks


def get_all_active_tasks():
    """Query Notion for all non-Done tasks (for Dale's session context)."""
    result = notion_api("POST", f"/databases/{DATABASE_ID}/query", {
        "filter": {
            "and": [
                {"property": "Status", "select": {"does_not_equal": "Done"}},
            ]
        },
        "sorts": [
            {"property": "Priority", "direction": "ascending"},
            {"timestamp": "created_time", "direction": "ascending"}
        ]
    })

    if not result or "results" not in result:
        return []

    tasks = []
    for page in result["results"]:
        props = page["properties"]
        task_title = ""
        if props.get("Task", {}).get("title"):
            task_title = "".join(t["plain_text"] for t in props["Task"]["title"])

        priority = props.get("Priority", {}).get("select", {})
        priority_name = priority.get("name", "Normal") if priority else "Normal"

        status = props.get("Status", {}).get("select", {})
        status_name = status.get("name", "New") if status else "New"

        dale_text = ""
        if props.get("Dale", {}).get("rich_text"):
            dale_text = "".join(t["plain_text"] for t in props["Dale"]["rich_text"])

        tasks.append({
            "id": page["id"],
            "task": task_title,
            "priority": priority_name,
            "status": status_name,
            "dale_notes": dale_text,
            "created": page["created_time"],
            "last_edited": page["last_edited_time"],
        })

    return tasks


def update_task_status(page_id, status, dale_notes=None):
    """Update a task's status and optionally Dale's notes."""
    properties = {
        "Status": {"select": {"name": status}}
    }
    if dale_notes is not None:
        properties["Dale"] = {
            "rich_text": [{"type": "text", "text": {"content": dale_notes[:2000]}}]
        }
    return notion_api("PATCH", f"/pages/{page_id}", {"properties": properties})


def load_state():
    """Load poller state (last seen edit time, pending flag)."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"last_seen_edit": None, "pending_since": None, "task_count": 0}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def save_tasks_for_dale(tasks):
    """Save active tasks to a file Dale's session prompt can read."""
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        json.dump(tasks, f, indent=2)


def dale_is_running():
    """Check if an autonomous Dale session is currently running."""
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)  # signal 0 = check if process exists
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def trigger_dale():
    """Trigger an autonomous Dale session in the background."""
    runner = os.path.join(SCRIPT_DIR, "dale-runner.sh")
    if not os.path.exists(runner):
        log(f"dale-runner.sh not found at {runner}")
        return False

    log("Triggering autonomous Dale session")
    subprocess.Popen(
        ["bash", runner, "--notion"],
        stdout=open(os.path.join(SCRIPT_DIR, "logs", "notion-trigger.log"), "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return True


def main():
    dry_run = "--dry-run" in sys.argv

    new_tasks = get_new_tasks()
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()

    if not new_tasks:
        # No new tasks — clear pending state
        if state["pending_since"]:
            log("No new tasks remaining. Clearing pending state.")
        save_state({"last_seen_edit": None, "pending_since": None, "task_count": 0})
        return

    # Find the most recent edit time among new tasks
    latest_edit = max(t["last_edited"] for t in new_tasks)
    task_count = len(new_tasks)

    log(f"Found {task_count} new task(s). Latest edit: {latest_edit}")

    if state["last_seen_edit"] != latest_edit or state["task_count"] != task_count:
        # Changes detected — record and wait for next cycle to confirm settled
        log("Changes still incoming. Waiting for next cycle to confirm settled.")
        save_state({
            "last_seen_edit": latest_edit,
            "pending_since": state.get("pending_since") or now,
            "task_count": task_count,
        })
        return

    # No changes since last poll — tasks have settled
    log(f"Tasks settled. {task_count} task(s) ready for Dale.")

    # Save all active tasks for Dale's context
    all_tasks = get_all_active_tasks()
    save_tasks_for_dale(all_tasks)

    if dry_run:
        log("Dry run — would trigger Dale now.")
        print(f"Would trigger Dale for {task_count} task(s):")
        for t in new_tasks:
            print(f"  [{t['priority']}] {t['task']}")
        return

    if dale_is_running():
        log("Dale is already running. Tasks saved — Dale will pick them up.")
        return

    # Mark tasks as "In Progress" in Notion BEFORE triggering, so the poller
    # won't find them as "New" on the next cycle and re-trigger endlessly.
    for t in new_tasks:
        update_task_status(t["id"], "In Progress")
    log(f"Marked {len(new_tasks)} task(s) as In Progress in Notion.")

    trigger_dale()
    save_state({"last_seen_edit": None, "pending_since": None, "task_count": 0})


if __name__ == "__main__":
    main()
