#!/usr/bin/env python3
"""
Uptime monitor for Dale's websites.
Checks treestock.com.au and walkthrough.au every 5 minutes.
Sends email via Resend when a site goes down or recovers.
State is tracked in /opt/dale/data/uptime_state.json to avoid alert spam.
"""

import json
import os
import sys
import urllib.request
import urllib.error
import socket
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/opt/dale/autonomous")
from notify import send_email

STATE_PATH = "/opt/dale/data/uptime_state.json"

CHECKS = [
    {
        "name": "treestock.com.au",
        "url": "https://treestock.com.au",
        "id": "treestock",
    },
    {
        "name": "walkthrough.au",
        "url": "https://walkthrough.au",
        "id": "walkthrough",
    },
    {
        "name": "Subscribe API",
        "url": "https://treestock.com.au/api/subscribe",
        "id": "subscribe_api",
        # Server only handles POST; GET to /subscribe returns 404 (working as designed)
        "expected_status": [200, 400, 404, 405],
    },
]

TIMEOUT = 15  # seconds


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def check_url(check):
    url = check["url"]
    expected = check.get("expected_status", [200, 301, 302])
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Dale-UptimeMonitor/1.0")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            if status in expected:
                return True, status, None
            else:
                return False, status, f"Unexpected status {status}"
    except urllib.error.HTTPError as e:
        if e.code in expected:
            return True, e.code, None
        return False, e.code, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, None, str(e.reason)
    except socket.timeout:
        return False, None, f"Timeout after {TIMEOUT}s"
    except Exception as e:
        return False, None, str(e)


def format_down_email(check, error, down_since):
    name = check["name"]
    url = check["url"]
    return f"""
<h2>⚠️ Site Down: {name}</h2>
<p><strong>URL:</strong> <a href="{url}">{url}</a></p>
<p><strong>Error:</strong> {error}</p>
<p><strong>Down since:</strong> {down_since}</p>
<p>Dale's uptime monitor will notify you when it recovers.</p>
""".strip(), f"Site Down: {name}\n\nURL: {url}\nError: {error}\nDown since: {down_since}"


def format_recovered_email(check, down_since, now):
    name = check["name"]
    url = check["url"]
    try:
        ds = datetime.fromisoformat(down_since)
        duration = now - ds
        mins = int(duration.total_seconds() / 60)
        duration_str = f"{mins} minutes" if mins < 120 else f"{mins // 60} hours {mins % 60} minutes"
    except Exception:
        duration_str = "unknown duration"
    return f"""
<h2>✅ Site Recovered: {name}</h2>
<p><strong>URL:</strong> <a href="{url}">{url}</a></p>
<p><strong>Was down since:</strong> {down_since}</p>
<p><strong>Downtime duration:</strong> {duration_str}</p>
""".strip(), f"Site Recovered: {name}\n\nURL: {url}\nDown for: {duration_str}"


def main():
    state = load_state()
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    changed = False

    for check in CHECKS:
        cid = check["id"]
        is_up, status, error = check_url(check)
        prev = state.get(cid, {"status": "unknown", "alerted": False})

        if is_up:
            if prev.get("status") == "down" and prev.get("alerted"):
                # Recovery — send notification
                html, text = format_recovered_email(check, prev.get("down_since", "unknown"), now)
                try:
                    send_email(f"✅ Recovered: {check['name']}", html, text)
                    print(f"[{now_str}] RECOVERED: {check['name']} — alert sent")
                except Exception as e:
                    print(f"[{now_str}] RECOVERED: {check['name']} — failed to send alert: {e}")
            else:
                print(f"[{now_str}] UP: {check['name']} ({status})")

            state[cid] = {"status": "up", "last_checked": now_str, "alerted": False}
            changed = True

        else:
            if prev.get("status") != "down":
                # Just went down — record it
                state[cid] = {
                    "status": "down",
                    "down_since": now_str,
                    "last_checked": now_str,
                    "error": error,
                    "alerted": False,
                }
                changed = True
                print(f"[{now_str}] DOWN (first detection): {check['name']} — {error}")

            elif not prev.get("alerted"):
                # Still down and haven't alerted yet — send alert
                down_since = prev.get("down_since", now_str)
                html, text = format_down_email(check, error, down_since)
                try:
                    send_email(f"⚠️ Down: {check['name']}", html, text)
                    state[cid]["alerted"] = True
                    state[cid]["last_checked"] = now_str
                    state[cid]["error"] = error
                    changed = True
                    print(f"[{now_str}] DOWN: {check['name']} — alert sent")
                except Exception as e:
                    print(f"[{now_str}] DOWN: {check['name']} — failed to send alert: {e}")
            else:
                # Still down, already alerted
                state[cid]["last_checked"] = now_str
                state[cid]["error"] = error
                changed = True
                print(f"[{now_str}] DOWN (ongoing): {check['name']} — {error}")

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
