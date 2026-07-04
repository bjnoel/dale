#!/usr/bin/env python3
"""
Uptime monitor for Dale's websites.
Checks treestock.com.au and walkthrough.au every 5 minutes.
Sends email via Resend when a site goes down or recovers.
State is tracked in /opt/dale/data/uptime_state.json to avoid alert spam.
"""

import json
import os
import shutil
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

# --- Disk-space monitoring -------------------------------------------------
# A full disk silently truncates scraper snapshots (corrupting the dataset) and
# crashes the digest builder. On 2026-07-04 the root FS sat at 100% for ~10 days
# undetected because this monitor only checked HTTP endpoints. The thresholds
# below give days of lead time on the 38 GB VPS.
# See memory/project_server_disk_clickhouse.md for the runbook.
DISK_PATH = "/"
DISK_WARN_PCT = 85       # first heads-up
DISK_CRIT_PCT = 93       # urgent
DISK_RECOVER_PCT = 80    # hysteresis: only clear the alert once back below this
_DISK_SEVERITY = {"ok": 0, "warning": 1, "critical": 2}


def load_state():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        # Corrupt or empty state file — treat as fresh start; next save_state() rewrites it.
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


def disk_level(pct):
    """Pure: map a used-percentage to an alert level."""
    if pct >= DISK_CRIT_PCT:
        return "critical"
    if pct >= DISK_WARN_PCT:
        return "warning"
    return "ok"


def disk_alert_decision(prev_level, pct):
    """Pure: decide what to do given the previously-alerted level and current % used.

    Returns (new_level, action) where action is one of:
      "alert"     — severity increased (ok->warning, ok/warning->critical); email.
      "recovered" — dropped back below the recover threshold; send an all-clear.
      "none"      — nothing worth emailing (including silent de-escalation).

    Hysteresis: once alerting, we don't clear to "ok" until usage falls below
    DISK_RECOVER_PCT, so usage hovering around the warn line doesn't flap.
    """
    level = disk_level(pct)
    if level == "ok" and prev_level != "ok" and pct >= DISK_RECOVER_PCT:
        level = prev_level  # hold the alert; not recovered yet
    if _DISK_SEVERITY[level] > _DISK_SEVERITY.get(prev_level, 0):
        return level, "alert"
    if level == "ok" and prev_level != "ok":
        return level, "recovered"
    return level, "none"


def format_disk_email(level, pct, used_gb, total_gb, free_gb):
    icon = "🔴" if level == "critical" else "⚠️"
    html = f"""
<h2>{icon} Disk {level}: {pct:.0f}% used on the Dale server</h2>
<p><strong>Filesystem {DISK_PATH}:</strong> {used_gb:.1f} GB used of {total_gb:.1f} GB
({pct:.0f}%), {free_gb:.1f} GB free.</p>
<p>A full disk silently truncates scraper snapshots and crashes the digest builder,
so act before it reaches 100%. Common culprits: Plausible ClickHouse internal log
tables (system.text_log), ClickHouse server logs, and old weekly backups in
/opt/dale/backups.</p>
<p>Runbook: memory/project_server_disk_clickhouse.md in the repo.</p>
""".strip()
    text = (f"Disk {level}: {pct:.0f}% used on the Dale server\n\n"
            f"{DISK_PATH}: {used_gb:.1f} GB used of {total_gb:.1f} GB "
            f"({pct:.0f}%), {free_gb:.1f} GB free.\n"
            f"Culprits: ClickHouse system.text_log, ClickHouse logs, old /opt/dale/backups.\n"
            f"Runbook: memory/project_server_disk_clickhouse.md")
    return html, text


def format_disk_recovered_email(pct, free_gb):
    html = (f"<h2>✅ Disk recovered: {pct:.0f}% used</h2>"
            f"<p>Free space is back to {free_gb:.1f} GB on {DISK_PATH}.</p>")
    text = f"Disk recovered: {pct:.0f}% used, {free_gb:.1f} GB free on {DISK_PATH}."
    return html, text


def check_disk(state, now_str):
    """Check root-filesystem usage; alert on threshold crossings.

    Mirrors the URL checks: de-dupes via state["disk"], and on a failed send keeps
    the previous level so the alert is retried next run. Returns True (state always
    updated with the latest reading).
    """
    try:
        usage = shutil.disk_usage(DISK_PATH)
    except Exception as e:
        print(f"[{now_str}] DISK: check failed: {e}")
        return False

    total_gb = usage.total / 1e9
    free_gb = usage.free / 1e9
    used_gb = total_gb - free_gb
    pct = (usage.total - usage.free) / usage.total * 100

    prev_level = state.get("disk", {}).get("level", "ok")
    new_level, action = disk_alert_decision(prev_level, pct)
    committed_level = new_level

    if action == "alert":
        html, text = format_disk_email(new_level, pct, used_gb, total_gb, free_gb)
        icon = "🔴" if new_level == "critical" else "⚠️"
        try:
            send_email(f"{icon} Disk {new_level}: {pct:.0f}% on Dale server", html, text)
            print(f"[{now_str}] DISK {new_level.upper()}: {pct:.0f}% used — alert sent")
        except Exception as e:
            committed_level = prev_level  # keep prev level so we retry next run
            print(f"[{now_str}] DISK {new_level.upper()}: {pct:.0f}% used — failed to send alert: {e}")
    elif action == "recovered":
        html, text = format_disk_recovered_email(pct, free_gb)
        try:
            send_email(f"✅ Disk recovered: {pct:.0f}% on Dale server", html, text)
            print(f"[{now_str}] DISK RECOVERED: {pct:.0f}% used — alert sent")
        except Exception as e:
            committed_level = prev_level  # retry the all-clear next run
            print(f"[{now_str}] DISK RECOVERED: {pct:.0f}% used — failed to send alert: {e}")
    else:
        print(f"[{now_str}] DISK {new_level.upper()}: {pct:.0f}% used ({free_gb:.1f}GB free)")

    state["disk"] = {"level": committed_level, "pct": round(pct, 1), "last_checked": now_str}
    return True


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

    # Disk space — the failure mode HTTP checks can't see (full disk corrupts data silently).
    if check_disk(state, now_str):
        changed = True

    if changed:
        save_state(state)


if __name__ == "__main__":
    main()
