#!/usr/bin/env python3
"""Daily digest email for Dale.

Runs once daily (22:00 UTC = 6am AWST). Compiles:
  1. Linear activity (last 24h): completed, created, in-progress tickets
  2. Traffic dashboard: Plausible + GSC via traffic_report.py
  3. Session summaries: aggregated token/cost from all session logs today
  4. Focus tracker: current reflection level

Usage: python3 daily-digest.py [--dry-run]
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
SECRETS_DIR = "/opt/dale/secrets"
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

GRAPHQL_URL = "https://api.linear.app/graphql"


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} daily-digest: {msg}\n"
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "cron.log"), "a") as f:
        f.write(line)


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_linear_token():
    env_path = os.path.join(SECRETS_DIR, "linear.env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("LINEAR_API_TOKEN="):
                return line.split("=", 1)[1]
    raise ValueError("LINEAR_API_TOKEN not found")


def graphql(query, variables=None):
    """Make a GraphQL request to Linear API."""
    import urllib.request
    import urllib.error

    token = get_linear_token()
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")

    req = urllib.request.Request(GRAPHQL_URL, data=body, method="POST", headers={
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "dale-daily-digest/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            if "errors" in result:
                log(f"GraphQL errors: {result['errors']}")
                return None
            return result.get("data")
    except Exception as e:
        log(f"Linear API error: {e}")
        return None


def get_team_id(team_name):
    data = graphql("""
        query($name: String!) {
            teams(filter: { name: { eq: $name } }) {
                nodes { id }
            }
        }
    """, {"name": team_name})
    if not data or not data["teams"]["nodes"]:
        return None
    return data["teams"]["nodes"][0]["id"]


def get_recent_activity(team_id, since_iso):
    """Fetch tickets completed/created in last 24h + currently in progress."""

    # Completed tickets: fetch all Done, filter by completedAt in Python
    completed_data = graphql("""
        query($teamId: ID!) {
            issues(
                filter: {
                    team: { id: { eq: $teamId } }
                    state: { type: { eq: "completed" } }
                }
                orderBy: updatedAt
                first: 50
            ) {
                nodes {
                    identifier title
                    completedAt
                    labels { nodes { name } }
                    comments(first: 3) {
                        nodes { body user { name } }
                    }
                }
            }
        }
    """, {"teamId": team_id})

    completed = []
    if completed_data and completed_data.get("issues"):
        for i in completed_data["issues"]["nodes"]:
            completed_at = i.get("completedAt", "")
            if completed_at and completed_at >= since_iso:
                summary = ""
                for c in i.get("comments", {}).get("nodes", []):
                    if c.get("user", {}).get("name", "").lower() == "dale":
                        summary = (c.get("body") or "")[:150]
                completed.append({
                    "id": i["identifier"],
                    "title": i["title"],
                    "summary": summary,
                })

    # Created tickets: fetch all Backlog, filter by createdAt in Python
    created_data = graphql("""
        query($teamId: ID!) {
            issues(
                filter: {
                    team: { id: { eq: $teamId } }
                    state: { type: { eq: "backlog" } }
                }
                orderBy: createdAt
                first: 50
            ) {
                nodes {
                    identifier title
                    description
                    createdAt
                    labels { nodes { name } }
                }
            }
        }
    """, {"teamId": team_id})

    created = []
    if created_data and created_data.get("issues"):
        for i in created_data["issues"]["nodes"]:
            created_at = i.get("createdAt", "")
            if created_at and created_at >= since_iso:
                desc = (i.get("description") or "")[:150]
                labels = [l["name"] for l in i.get("labels", {}).get("nodes", [])]
                created.append({
                    "id": i["identifier"],
                    "title": i["title"],
                    "description": desc,
                    "labels": labels,
                })

    # In Progress tickets
    in_progress_data = graphql("""
        query($teamId: ID!) {
            issues(
                filter: {
                    team: { id: { eq: $teamId } }
                    state: { type: { eq: "started" } }
                }
                first: 20
            ) {
                nodes {
                    identifier title
                    assignee { name }
                }
            }
        }
    """, {"teamId": team_id})

    in_progress = []
    if in_progress_data and in_progress_data.get("issues"):
        for i in in_progress_data["issues"]["nodes"]:
            assignee = (i.get("assignee") or {}).get("name", "")
            in_progress.append({
                "id": i["identifier"],
                "title": i["title"],
                "assignee": assignee,
            })

    return completed, created, in_progress


def aggregate_sessions(since):
    """Read all session-*.json files modified since the cutoff."""
    logs_dir = Path(LOG_DIR)
    sessions = []
    total_tokens_in = 0
    total_tokens_out = 0
    total_cost = 0.0
    total_turns = 0
    total_duration_s = 0

    for f in sorted(logs_dir.glob("session-*.json")):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < since:
                continue
            with open(f) as fh:
                data = json.load(fh)
            usage = data.get("usage", {})
            tokens_in = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
            tokens_out = usage.get("output_tokens", 0)
            cost = data.get("total_cost_usd", 0) or 0
            turns = data.get("num_turns", 0)
            duration = (data.get("duration_ms", 0) or 0) / 1000

            total_tokens_in += tokens_in
            total_tokens_out += tokens_out
            total_cost += cost
            total_turns += turns
            total_duration_s += duration
            sessions.append(f.name)
        except (json.JSONDecodeError, OSError):
            continue

    return {
        "count": len(sessions),
        "files": sessions,
        "tokens_in": total_tokens_in,
        "tokens_out": total_tokens_out,
        "cost_usd": round(total_cost, 2),
        "turns": total_turns,
        "duration_min": round(total_duration_s / 60, 1),
    }


def get_subscriber_stats():
    """Read subscriber data and return stats for the digest."""
    import sqlite3

    subs_path = "/opt/dale/data/subscribers.json"
    watches_db = "/opt/dale/data/variety_watches.db"

    stats = {
        "total_subscribers": 0,
        "variety_watch_count": 0,
        "variety_watch_emails": 0,
        "variety_watches": {},
    }

    # Read subscribers.json
    try:
        with open(subs_path) as f:
            subs = json.load(f)
        stats["total_subscribers"] = len(subs)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Read variety_watches.db
    try:
        con = sqlite3.connect(watches_db)
        rows = con.execute(
            "SELECT variety_title, COUNT(*) as cnt FROM watches GROUP BY variety_slug ORDER BY cnt DESC"
        ).fetchall()
        emails = con.execute("SELECT COUNT(DISTINCT email) FROM watches").fetchone()[0]
        con.close()
        stats["variety_watch_count"] = sum(r[1] for r in rows)
        stats["variety_watch_emails"] = emails
        stats["variety_watches"] = {r[0]: r[1] for r in rows}
    except Exception:
        pass

    return stats


def load_focus_summary(repo_dir):
    """Read focus tracker and compute a one-line summary."""
    tracker_path = os.path.join(repo_dir, "state", "focus-tracker.json")
    try:
        with open(tracker_path) as f:
            tracker = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return "Focus tracker not available."

    session_log = tracker.get("session_log", [])
    if not session_log:
        return "No session data in focus tracker yet."

    # Count categories in recent sessions
    recent = session_log[-5:]
    cat_counts = {}
    for entry in recent:
        for cat in entry.get("categories_worked", []):
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    if not cat_counts:
        return "No category data recorded."

    top = sorted(cat_counts.items(), key=lambda x: -x[1])
    top_str = ", ".join(f"{c} ({n}x)" for c, n in top[:3])
    return f"Top focus areas (last {len(recent)} sessions): {top_str}"


def build_digest_html(completed, created, in_progress, session_stats,
                      traffic_html, focus_summary, subscriber_stats, today,
                      resend_html=""):
    """Build the HTML email body."""
    parts = [f"<h2>Dale Daily Digest &mdash; {today}</h2>"]

    # Traffic dashboard
    if traffic_html:
        parts.append(traffic_html)

    # Email delivery report (Sundays)
    if resend_html:
        parts.append(resend_html)

    # Completed
    parts.append("<h3>Completed (last 24h)</h3>")
    if completed:
        parts.append("<ul>")
        for t in completed:
            summary = f" &mdash; {t['summary']}" if t["summary"] else ""
            parts.append(f"<li><strong>{t['id']}</strong>: {t['title']}{summary}</li>")
        parts.append("</ul>")
    else:
        parts.append("<p style='color: #888;'>No tickets completed.</p>")

    # Proposed
    parts.append("<h3>Proposed (last 24h)</h3>")
    if created:
        parts.append("<ul>")
        for t in created:
            labels = f" [{', '.join(t['labels'])}]" if t["labels"] else ""
            desc = f" &mdash; {t['description']}" if t["description"] else ""
            parts.append(f"<li><strong>{t['id']}</strong>: {t['title']}{labels}{desc}</li>")
        parts.append("</ul>")
    else:
        parts.append("<p style='color: #888;'>No new tickets proposed.</p>")

    # In Progress
    if in_progress:
        parts.append("<h3>In Progress</h3>")
        parts.append("<ul>")
        for t in in_progress:
            assignee = f" (assigned: {t['assignee']})" if t["assignee"] else ""
            parts.append(f"<li><strong>{t['id']}</strong>: {t['title']}{assignee}</li>")
        parts.append("</ul>")

    # Session stats
    s = session_stats
    if s["count"] > 0:
        parts.append("<h3>Sessions</h3>")
        parts.append(
            f"<p>{s['count']} session(s) | {s['duration_min']} min total | "
            f"{s['tokens_in'] + s['tokens_out']:,} tokens | ${s['cost_usd']:.2f} USD</p>"
        )
    else:
        parts.append("<h3>Sessions</h3>")
        parts.append("<p style='color: #888;'>No sessions ran in the last 24 hours.</p>")

    # Focus tracker
    parts.append(f"<h3>Focus Tracker</h3>")
    parts.append(f"<p>{focus_summary}</p>")

    # Subscriber stats
    ss = subscriber_stats
    parts.append("<h3>Subscribers</h3>")
    parts.append(
        f"<p>{ss['total_subscribers']} subscribers | "
        f"{ss['variety_watch_count']} variety watches ({ss['variety_watch_emails']} users)</p>"
    )
    if ss["variety_watches"]:
        vw = ", ".join(f"{t} ({n})" for t, n in list(ss["variety_watches"].items())[:10])
        parts.append(f"<p style='font-size:0.9em;color:#555'>Varieties: {vw}</p>")

    parts.append(
        '<p style="color: #888; font-size: 12px;">Autonomous Dale &mdash; '
        '<a href="https://github.com/bjnoel/Dale">repo</a></p>'
    )

    return "\n".join(parts)


def build_digest_text(completed, created, in_progress, session_stats,
                      traffic_text, focus_summary, subscriber_stats, today,
                      resend_text=""):
    """Build the plaintext email body."""
    lines = [f"Dale Daily Digest -- {today}", ""]

    if traffic_text:
        lines.append(traffic_text)
        lines.append("")

    if resend_text:
        lines.append(resend_text)
        lines.append("")

    lines.append("== Completed (last 24h) ==")
    if completed:
        for t in completed:
            summary = f" -- {t['summary']}" if t["summary"] else ""
            lines.append(f"  {t['id']}: {t['title']}{summary}")
    else:
        lines.append("  No tickets completed.")
    lines.append("")

    lines.append("== Proposed (last 24h) ==")
    if created:
        for t in created:
            lines.append(f"  {t['id']}: {t['title']}")
    else:
        lines.append("  No new tickets proposed.")
    lines.append("")

    if in_progress:
        lines.append("== In Progress ==")
        for t in in_progress:
            lines.append(f"  {t['id']}: {t['title']}")
        lines.append("")

    s = session_stats
    lines.append("== Sessions ==")
    if s["count"] > 0:
        lines.append(
            f"  {s['count']} session(s) | {s['duration_min']} min | "
            f"{s['tokens_in'] + s['tokens_out']:,} tokens | ${s['cost_usd']:.2f}"
        )
    else:
        lines.append("  No sessions ran.")
    lines.append("")

    lines.append(f"Focus: {focus_summary}")
    lines.append("")

    ss = subscriber_stats
    lines.append("== Subscribers ==")
    lines.append(
        f"  {ss['total_subscribers']} subscribers | "
        f"{ss['variety_watch_count']} variety watches"
    )
    if ss["variety_watches"]:
        vw = ", ".join(f"{t} ({n})" for t, n in list(ss["variety_watches"].items())[:10])
        lines.append(f"  Varieties: {vw}")

    return "\n".join(lines)


def main():
    dry_run = "--dry-run" in sys.argv
    log("=== Starting daily digest ===")

    config = load_config()
    repo_dir = config.get("paths", {}).get("repo", "/opt/dale/repo")
    team_name = config.get("linear", {}).get("team", "Dale")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    since_iso = since.isoformat()

    # 1. Linear activity
    team_id = get_team_id(team_name)
    if team_id:
        completed, created, in_progress = get_recent_activity(team_id, since_iso)
        log(f"Linear: {len(completed)} completed, {len(created)} created, {len(in_progress)} in progress")
    else:
        log("Warning: could not find Linear team")
        completed, created, in_progress = [], [], []

    # 2. Traffic report (generate fresh; GSC only on Sundays)
    traffic_html, traffic_text = "", ""
    is_sunday = datetime.now(timezone.utc).weekday() == 6
    try:
        import subprocess
        traffic_script = os.path.join(SCRIPT_DIR, "traffic_report.py")
        traffic_cmd = ["python3", traffic_script, "--output", "/opt/dale/data/traffic_report.json"]
        if not is_sunday:
            traffic_cmd.append("--skip-gsc")
        subprocess.run(traffic_cmd, timeout=120, capture_output=True)
        # Import the rendering function from notify.py
        sys.path.insert(0, SCRIPT_DIR)
        from notify import load_traffic_report
        traffic_html, traffic_text = load_traffic_report()
    except Exception as e:
        log(f"Warning: traffic report failed: {e}")

    # 2b. Resend email delivery report (Sundays only — generated by cron before this runs)
    resend_html, resend_text = "", ""
    if is_sunday:
        try:
            sys.path.insert(0, SCRIPT_DIR)
            from notify import load_resend_report
            resend_html, resend_text = load_resend_report()
            if resend_html:
                log("Resend report loaded for Sunday digest")
        except Exception as e:
            log(f"Warning: resend report load failed: {e}")

    # 3. Session summaries
    session_stats = aggregate_sessions(since)
    log(f"Sessions: {session_stats['count']} in last 24h, ${session_stats['cost_usd']:.2f}")

    # 4. Focus tracker
    focus_summary = load_focus_summary(repo_dir)

    # 5. Subscriber stats
    subscriber_stats = get_subscriber_stats()
    log(f"Subscribers: {subscriber_stats['total_subscribers']} total, "
        f"{subscriber_stats['variety_watch_count']} variety watches")

    # Build email
    html = build_digest_html(completed, created, in_progress, session_stats,
                             traffic_html, focus_summary, subscriber_stats, today,
                             resend_html=resend_html)
    text = build_digest_text(completed, created, in_progress, session_stats,
                             traffic_text, focus_summary, subscriber_stats, today,
                             resend_text=resend_text)

    if dry_run:
        print("=== HTML ===")
        print(html)
        print("\n=== TEXT ===")
        print(text)
        log("Dry run complete")
        return

    # Send via notify.py's send_email
    sys.path.insert(0, SCRIPT_DIR)
    from notify import send_email

    subject = f"Dale Daily Digest -- {today}"
    success = send_email(subject, html, text)
    if success:
        log("Digest email sent")
    else:
        log("Failed to send digest email")

    log("=== Daily digest complete ===")


if __name__ == "__main__":
    main()
