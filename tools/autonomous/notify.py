#!/usr/bin/env python3
"""Email notifications for autonomous Dale via Resend API."""

import base64
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

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


def send_email(subject, html_body, text_body=None, attachments=None):
    """Send an email via Resend API. attachments: list of {"filename": str, "path": str}."""
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

    if attachments:
        payload["attachments"] = []
        for att in attachments:
            with open(att["path"], "rb") as f:
                content = base64.b64encode(f.read()).decode("ascii")
            payload["attachments"].append({
                "filename": att["filename"],
                "content": content,
            })

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


def find_new_deliverables(repo_dir):
    """Find deliverables modified today (untracked/changed, not in git)."""
    deliverables_dir = Path(repo_dir) / "deliverables"
    if not deliverables_dir.is_dir():
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    attachments = []
    for f in deliverables_dir.rglob("*"):
        if not f.is_file():
            continue
        # Only include files modified today
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if mtime.strftime("%Y-%m-%d") == today:
            attachments.append({
                "filename": f.name,
                "path": str(f),
            })
    return attachments


def load_traffic_report() -> tuple:
    """Load multi-site traffic report for the morning summary.

    Returns (html, text) tuple for inclusion in the email.
    """
    report_path = Path("/opt/dale/data/traffic_report.json")
    if not report_path.exists():
        return "", ""
    try:
        with open(report_path) as f:
            report = json.load(f)
    except Exception:
        return "", ""

    text_lines = []
    html_parts = []

    # --- Plausible traffic table ---
    plausible = report.get("plausible", [])
    if plausible:
        text_lines.append("Traffic Dashboard")
        text_lines.append(f"{'Site':<24} {'Yest':>6} {'7-day':>7} {'Wk':>7} {'Mo':>7}")
        text_lines.append("-" * 55)

        html_parts.append('<h3>Traffic Dashboard</h3>')
        html_parts.append('<table style="font-family: monospace; font-size: 12px; border-collapse: collapse; width: 100%;">')
        html_parts.append('<tr style="border-bottom: 1px solid #ddd; font-weight: bold;">'
                          '<td style="padding: 4px 8px;">Site</td>'
                          '<td style="padding: 4px 8px; text-align: right;">Yest</td>'
                          '<td style="padding: 4px 8px; text-align: right;">7-day</td>'
                          '<td style="padding: 4px 8px; text-align: right;">Wk</td>'
                          '<td style="padding: 4px 8px; text-align: right;">Mo</td></tr>')

        for site in plausible:
            name = site["site"]
            yd = site.get("yesterday", {}).get("visitors", 0)
            wk = site.get("week", {}).get("visitors", 0)
            wk_ch = site.get("week_change")
            mo_ch = site.get("month_change")

            wk_str = f"{wk_ch:+d}%" if wk_ch is not None else "--"
            mo_str = f"{mo_ch:+d}%" if mo_ch is not None else "--"

            text_lines.append(f"{name:<24} {yd:>6} {wk:>7} {wk_str:>7} {mo_str:>7}")

            # Color trends
            wk_color = "#2e7d32" if wk_ch and wk_ch > 0 else "#c62828" if wk_ch and wk_ch < 0 else "#888"
            mo_color = "#2e7d32" if mo_ch and mo_ch > 0 else "#c62828" if mo_ch and mo_ch < 0 else "#888"

            html_parts.append(
                f'<tr style="border-bottom: 1px solid #eee;">'
                f'<td style="padding: 4px 8px;">{name}</td>'
                f'<td style="padding: 4px 8px; text-align: right;">{yd}</td>'
                f'<td style="padding: 4px 8px; text-align: right;">{wk:,}</td>'
                f'<td style="padding: 4px 8px; text-align: right; color: {wk_color};">{wk_str}</td>'
                f'<td style="padding: 4px 8px; text-align: right; color: {mo_color};">{mo_str}</td></tr>'
            )

        html_parts.append('</table>')
        text_lines.append("")

    # --- GSC highlights per site ---
    gsc = report.get("gsc", [])
    for site_data in gsc:
        totals = site_data.get("totals", {})
        if totals.get("impressions", 0) == 0:
            continue

        domain = site_data["site"]
        clicks = totals["clicks"]
        impressions = totals["impressions"]
        avg_pos = totals["avg_position"]

        # Format impressions compactly
        impr_str = f"{impressions:,}" if impressions < 10000 else f"{impressions/1000:.1f}K"

        header = f"GSC: {domain} (14d: {clicks} clicks, {impr_str} impr, pos {avg_pos:.1f})"
        text_lines.append(header)
        html_parts.append(f'<h4 style="margin: 12px 0 4px 0; font-size: 13px;">{header}</h4>')
        html_parts.append('<pre style="font-size: 11px; background: #f5f5f5; padding: 6px 8px; border-radius: 4px; margin: 0 0 8px 0; white-space: pre-wrap;">')

        detail_lines = []

        new_queries = site_data.get("new_queries", [])
        if new_queries:
            for q in new_queries[:5]:
                line = f'New: "{q["query"]}" pos {q["position"]:.0f} ({q["impressions"]} impr)'
                detail_lines.append(line)

        movers = site_data.get("position_movers", [])
        if movers:
            for m in movers[:5]:
                direction = "Up" if m["change"] > 0 else "Down"
                line = (f'{direction}: "{m["query"]}" '
                        f'{m["old_position"]:.0f}->{m["new_position"]:.0f} '
                        f'({"+" if m["change"] > 0 else ""}{m["change"]:.0f} spots, '
                        f'{m["impressions"]} impr)')
                detail_lines.append(line)

        if not detail_lines:
            detail_lines.append("No notable query changes this period.")

        for line in detail_lines:
            text_lines.append(f"  {line}")
        html_parts.append("\n".join(detail_lines))
        html_parts.append('</pre>')
        text_lines.append("")

    html = "\n".join(html_parts)
    text = "\n".join(text_lines)
    return html, text


def load_indexing_report() -> tuple:
    """Load GSC indexing progress for inclusion in the weekly Sunday email.

    Returns (html, text) tuple. Empty strings if no report available or stale.
    Only shown if the report was generated within the last 8 days (stays visible
    through the week following each Sunday run).
    """
    from datetime import datetime, timezone, timedelta
    report_path = Path("/opt/dale/data/gsc_report.json")
    if not report_path.exists():
        return "", ""
    try:
        with open(report_path) as f:
            report = json.load(f)
    except Exception:
        return "", ""

    indexing = report.get("indexing_progress")
    if not indexing:
        return "", ""

    # Only show if generated within last 8 days
    try:
        generated = datetime.fromisoformat(indexing["collected_at"])
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - generated > timedelta(days=8):
            return "", ""
    except Exception:
        pass

    page_types = indexing.get("page_types", {})
    total_indexed = indexing.get("total_indexed", 0)
    total_known = indexing.get("total_known", 0)
    total_pct = indexing.get("total_pct", 0)

    text_lines = [f"GSC Indexing Progress (90-day window)"]
    html_rows = []

    for ptype, stats in sorted(page_types.items()):
        indexed = stats["indexed"]
        total = stats["total"]
        pct = stats["pct"]
        bar = "#" * (pct // 10) + "." * (10 - pct // 10)
        text_lines.append(f"  {ptype:<22} {indexed:>3}/{total:<3} [{bar}] {pct}%")

        color = "#2e7d32" if pct >= 75 else "#e65100" if pct >= 25 else "#c62828"
        html_rows.append(
            f'<tr style="border-bottom: 1px solid #eee;">'
            f'<td style="padding: 3px 8px; font-size: 12px;">{ptype}</td>'
            f'<td style="padding: 3px 8px; text-align: right; font-size: 12px;">{indexed}/{total}</td>'
            f'<td style="padding: 3px 8px; text-align: right; font-size: 12px; color: {color};">{pct}%</td>'
            f'</tr>'
        )

    text_lines.append(f"  {'TOTAL':<22} {total_indexed:>3}/{total_known:<3}  {total_pct}%")
    text_lines.append("")

    html = (
        f'<h4 style="margin: 12px 0 4px 0; font-size: 13px;">GSC Indexing Progress (90-day window)</h4>'
        f'<table style="font-family: monospace; font-size: 12px; border-collapse: collapse; width: 100%;">'
        f'<tr style="border-bottom: 1px solid #ddd; font-weight: bold;">'
        f'<td style="padding: 3px 8px;">Page type</td>'
        f'<td style="padding: 3px 8px; text-align: right;">Indexed</td>'
        f'<td style="padding: 3px 8px; text-align: right;">%</td></tr>'
        + "".join(html_rows)
        + f'<tr style="border-top: 2px solid #ddd; font-weight: bold;">'
        f'<td style="padding: 3px 8px; font-size: 12px;">TOTAL</td>'
        f'<td style="padding: 3px 8px; text-align: right; font-size: 12px;">{total_indexed}/{total_known}</td>'
        f'<td style="padding: 3px 8px; text-align: right; font-size: 12px;">{total_pct}%</td></tr>'
        f'</table>'
    )

    return html, "\n".join(text_lines)


def load_resend_report() -> tuple:
    """Load weekly email delivery report for inclusion in daily digest.

    Returns (html, text) tuple. Empty strings if no report available.
    Only returns content if the report was generated within the last 8 days
    (so it appears in the Sunday digest and stays visible through the week).
    """
    from datetime import datetime, timezone, timedelta
    report_path = Path("/opt/dale/data/resend_report.json")
    if not report_path.exists():
        return "", ""
    try:
        with open(report_path) as f:
            report = json.load(f)
    except Exception:
        return "", ""

    # Only show if generated within last 8 days
    try:
        generated = datetime.fromisoformat(report["generated_at"])
        if datetime.now(timezone.utc) - generated > timedelta(days=8):
            return "", ""
    except Exception:
        pass

    # Import render functions from resend_report.py
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        from resend_report import render_html, render_text
        return render_html(report), render_text(report)
    except Exception:
        return "", ""


def send_summary(session_log_path):
    """Send daily session summary email with any new deliverables attached."""
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

    traffic_html, traffic_text = load_traffic_report()
    indexing_html, indexing_text = load_indexing_report()

    html = f"""<h2>Dale Session &mdash; {today}</h2>
{traffic_html}{indexing_html}
<h3>Session Output</h3>
<pre style="white-space: pre-wrap; font-family: monospace; background: #f5f5f5; padding: 12px; border-radius: 4px;">{summary_text[:3000]}</pre>
<h3>Usage</h3>
<ul>
<li>Tokens: {tokens_in:,} in / {tokens_out:,} out</li>
<li>Turns: {num_turns} &bull; Duration: {duration_min:.1f} minutes</li>
<li>Stop reason: {stop_reason}</li>
</ul>
<p style="color: #888; font-size: 12px;">Autonomous Dale &mdash; <a href="https://github.com/bjnoel/Dale">repo</a></p>"""

    # Find deliverables to attach
    config = load_config()
    repo_dir = config.get("paths", {}).get("repo", "/opt/dale/repo")
    attachments = find_new_deliverables(repo_dir)

    if attachments:
        att_list = "".join(f"<li>{a['filename']}</li>" for a in attachments)
        html += f"\n<h3>Deliverables</h3>\n<ul>{att_list}</ul>"

    text = f"""Dale Session — {today}

{traffic_text}
{indexing_text}
{summary_text[:2000]}

Tokens: {tokens_in:,} in / {tokens_out:,} out
Turns: {num_turns} | Duration: {duration_min:.1f} min"""

    if attachments:
        text += f"\n\nDeliverables attached: {', '.join(a['filename'] for a in attachments)}"

    send_email(f"Dale Session — {today}", html, text, attachments=attachments)


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
