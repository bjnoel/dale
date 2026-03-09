#!/usr/bin/env python3
"""Email notifications for autonomous Dale via Resend API."""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

SECRETS_DIR = "/opt/dale/secrets"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_api_key():
    env_path = os.path.join(SECRETS_DIR, "resend.env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("RESEND_API_KEY="):
                return line.split("=", 1)[1]
    raise ValueError("RESEND_API_KEY not found in resend.env")


def send_email(subject, html_body, text_body=None):
    """Send an email via Resend API."""
    config = load_config()
    api_key = get_api_key()

    payload = {
        "from": f"Dale <{config['notifications']['from_email']}>",
        "to": [config["notifications"]["to_email"]],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        payload["text"] = text_body

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "dale-autonomous/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"Email sent: {result.get('id', 'ok')}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        print(f"Email failed ({e.code}): {error_body}", file=sys.stderr)
        return False


def send_summary(session_log_path):
    """Send daily session summary email."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Parse session output
    summary_text = "No session output available."
    tokens_in = tokens_out = num_turns = 0
    duration_s = cost_usd = 0.0
    stop_reason = "unknown"

    if os.path.exists(session_log_path):
        try:
            with open(session_log_path) as f:
                data = json.load(f)
            summary_text = data.get("result", "") or summary_text
            if not summary_text or summary_text == "No session output available.":
                sr = data.get("stop_reason", "")
                nt = data.get("num_turns", 0)
                summary_text = (f"Session ran {nt} turns but produced no final text output. "
                                f"Stop reason: {sr}. Check git log for any changes made.")
            usage = data.get("usage", {})
            tokens_in = usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
            tokens_out = usage.get("output_tokens", 0)
            duration_s = data.get("duration_ms", 0) / 1000
            num_turns = data.get("num_turns", 0)
            cost_usd = data.get("total_cost_usd", 0)
            stop_reason = data.get("stop_reason", "unknown")
        except (json.JSONDecodeError, KeyError):
            with open(session_log_path) as f:
                summary_text = f.read()[:2000]

    duration_min = duration_s / 60

    html = f"""<h2>Dale Session &mdash; {today}</h2>
<h3>Session Output</h3>
<pre style="white-space: pre-wrap; font-family: monospace; background: #f5f5f5; padding: 12px; border-radius: 4px;">{summary_text[:3000]}</pre>
<h3>Usage</h3>
<ul>
<li>Tokens: {tokens_in:,} in / {tokens_out:,} out</li>
<li>Turns: {num_turns} &bull; Cost: ${cost_usd:.4f} &bull; Stop: {stop_reason}</li>
<li>Duration: {duration_min:.1f} minutes</li>
</ul>
<p style="color: #888; font-size: 12px;">Autonomous Dale &mdash; <a href="https://github.com/bjnoel/Dale">repo</a></p>"""

    text = f"""Dale Session — {today}

{summary_text[:2000]}

Tokens: {tokens_in:,} in / {tokens_out:,} out
Turns: {num_turns} | Cost: ${cost_usd:.4f} | Duration: {duration_min:.1f} min"""

    send_email(f"Dale Session — {today}", html, text)


def send_alert(reason):
    """Send circuit breaker / error alert."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<h2>[ALERT] Dale autonomous run halted</h2>
<p><strong>Time:</strong> {today}</p>
<p><strong>Reason:</strong> {reason}</p>
<p>Check <code>/opt/dale/autonomous/logs/errors.log</code> on the server.</p>
<p>To resume: remove the issue or delete the STOP file, then Dale will retry next cron run.</p>"""

    send_email(f"[ALERT] Dale halted — {reason[:50]}", html)


def send_approval_request(filepath):
    """Send spending approval request email."""
    with open(filepath) as f:
        content = f.read()

    filename = os.path.basename(filepath)
    html = f"""<h2>[APPROVAL] Dale spending request</h2>
<pre style="white-space: pre-wrap; font-family: monospace; background: #f5f5f5; padding: 12px; border-radius: 4px;">{content}</pre>
<p>To approve: reply "approved" or SSH in and move the file:<br>
<code>mv /opt/dale/autonomous/approvals/pending/{filename} /opt/dale/autonomous/approvals/approved/</code></p>"""

    send_email(f"[APPROVAL] {filename}", html)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: notify.py <summary|alert|approval> [args...]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "summary":
        send_summary(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "alert":
        send_alert(sys.argv[2] if len(sys.argv) > 2 else "Unknown error")
    elif cmd == "approval":
        send_approval_request(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
