#!/usr/bin/env python3
"""
Weekly email delivery report from Resend analytics.

Fetches recent email data from Resend API, groups by program,
and reports delivery rate, bounce tracking, and open rates.

Usage:
    python3 resend_report.py                     # Generate JSON + print summary
    python3 resend_report.py --email             # Generate + send report email
    python3 resend_report.py --days 14           # Look back 14 days
    python3 resend_report.py --output /path.json # Custom output path
    python3 resend_report.py --dry-run           # Print only, no save/send
"""

import json
import sys
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
DEFAULT_OUTPUT = DATA_DIR / "resend_report.json"

# Map Resend "from" addresses to program names
SENDER_PROGRAM = {
    "alerts@mail.treestock.com.au": "treestock_digest",
    "alerts@mail.scion.exchange": "treestock_digest",    # old domain, same program
    "alerts@mail.walkthrough.au": "beestock_welcome",
    "dale@mail.walkthrough.au": "dale_ops",
}

PROGRAM_LABELS = {
    "treestock_digest": "treestock.com.au subscriber digests",
    "beestock_welcome": "beestock.com.au welcome emails",
    "dale_ops": "Dale internal ops (not tracked)",
    "other": "Other / transactional",
}

# Programs to include in marketing summary and breakdown
MARKETING_PROGRAMS = {"treestock_digest", "beestock_welcome"}


def get_resend_key() -> str:
    env_path = SECRETS_DIR / "resend-readonly.env"
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("RESEND_FULL_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise ValueError("RESEND_FULL_API_KEY not found in resend-readonly.env")


def fetch_emails(api_key: str, limit: int = 100) -> list:
    """Fetch recent emails from Resend list endpoint."""
    url = f"https://api.resend.com/emails?limit={limit}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "dale-resend-report/1.0",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        return data.get("data", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else str(e)
        raise RuntimeError(f"Resend API error ({e.code}): {body}")


def classify_sender(from_field: str) -> str:
    """Extract the email address from 'Name <addr>' and map to program."""
    if "<" in from_field:
        addr = from_field.split("<")[-1].rstrip(">").strip().lower()
    else:
        addr = from_field.strip().lower()
    return SENDER_PROGRAM.get(addr, "other")


def parse_ts(ts_str: str) -> datetime:
    """Parse Resend timestamp string to timezone-aware datetime."""
    ts = ts_str.replace(" ", "T")
    if not ts.endswith("+00:00") and "+" not in ts[10:] and "Z" not in ts:
        ts += "+00:00"
    return datetime.fromisoformat(ts)


def load_subscriber_counts() -> dict:
    """Return current subscriber counts from local data files."""
    counts = {}
    try:
        with open(SUBSCRIBERS_FILE) as f:
            subs = json.load(f)
        counts["treestock"] = len(subs)
    except Exception:
        pass

    # Beestock subscribers file (if it exists)
    bee_subs = DATA_DIR / "bee_subscribers.json"
    try:
        with open(bee_subs) as f:
            bee = json.load(f)
        counts["beestock"] = len(bee)
    except Exception:
        pass

    return counts


def build_report(emails: list, days: int = 7) -> dict:
    """Build weekly delivery report from raw email list."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Filter to look-back window
    recent = []
    for e in emails:
        try:
            if parse_ts(e["created_at"]) >= cutoff:
                recent.append(e)
        except Exception:
            pass

    # Group by program
    by_program: dict[str, list] = defaultdict(list)
    for e in recent:
        prog = classify_sender(e["from"])
        by_program[prog].append(e)

    # Build per-program stats
    programs = {}
    for prog, prog_emails in sorted(by_program.items()):
        event_counts: dict[str, int] = defaultdict(int)
        for e in prog_emails:
            event_counts[e["last_event"]] += 1

        sent = len(prog_emails)
        delivered = event_counts.get("delivered", 0)
        bounced = event_counts.get("bounced", 0)
        opened = event_counts.get("opened", 0)
        clicked = event_counts.get("clicked", 0)

        # Collect unique recipients
        recipients: set = set()
        for e in prog_emails:
            recipients.update(e.get("to", []))

        # Recent bounced emails for detail
        bounced_details = [
            {
                "to": e["to"],
                "date": e["created_at"][:10],
                "subject": e["subject"],
            }
            for e in prog_emails if e["last_event"] == "bounced"
        ][:10]

        programs[prog] = {
            "label": PROGRAM_LABELS.get(prog, prog),
            "sent": sent,
            "delivered": delivered,
            "bounced": bounced,
            "opened": opened,
            "clicked": clicked,
            "delivery_rate_pct": round(delivered / sent * 100, 1) if sent > 0 else None,
            "open_rate_pct": round(opened / delivered * 100, 1) if delivered > 0 else None,
            "unique_recipients": len(recipients),
            "bounced_details": bounced_details,
        }

    # Aggregate marketing summary (treestock + beestock only)
    marketing_emails = [
        e for prog, es in by_program.items()
        if prog in MARKETING_PROGRAMS
        for e in es
    ]
    m_sent = len(marketing_emails)
    m_delivered = sum(1 for e in marketing_emails if e["last_event"] == "delivered")
    m_bounced = sum(1 for e in marketing_emails if e["last_event"] == "bounced")
    m_opened = sum(1 for e in marketing_emails if e["last_event"] == "opened")

    return {
        "generated_at": now.isoformat(),
        "period_days": days,
        "period_start": cutoff.strftime("%Y-%m-%d"),
        "period_end": now.strftime("%Y-%m-%d"),
        "total_emails_fetched": len(emails),
        "total_emails_in_window": len(recent),
        "marketing_summary": {
            "sent": m_sent,
            "delivered": m_delivered,
            "bounced": m_bounced,
            "opened": m_opened,
            "delivery_rate_pct": round(m_delivered / m_sent * 100, 1) if m_sent > 0 else None,
            "open_rate_pct": round(m_opened / m_delivered * 100, 1) if m_delivered > 0 else None,
        },
        "programs": programs,
        "subscribers": load_subscriber_counts(),
    }


def render_html(report: dict) -> str:
    """Render report as HTML email section."""
    p_days = report["period_days"]
    p_start = report["period_start"]
    p_end = report["period_end"]
    ms = report["marketing_summary"]

    parts = [
        f'<h3>Email Delivery Report ({p_days}-day window: {p_start} to {p_end})</h3>',
    ]

    if ms["sent"] == 0:
        parts.append('<p style="color:#888;">No marketing emails sent in this period.</p>')
    else:
        dr = ms["delivery_rate_pct"]
        dr_color = "#2e7d32" if dr and dr >= 95 else "#e65100" if dr and dr >= 80 else "#c62828"
        parts.append(
            '<table style="font-family:monospace;font-size:12px;border-collapse:collapse;margin-bottom:8px;">'
        )
        rows = [
            ("Sent", ms["sent"]),
            ("Delivered", ms["delivered"]),
            ("Bounced", ms["bounced"]),
        ]
        for label, val in rows:
            parts.append(f'<tr><td style="padding:2px 10px 2px 0;">{label}</td>'
                         f'<td style="padding:2px 0;"><strong>{val}</strong></td></tr>')
        dr_str = f"{dr}%" if dr is not None else "N/A"
        parts.append(f'<tr><td style="padding:2px 10px 2px 0;">Delivery rate</td>'
                     f'<td style="padding:2px 0;color:{dr_color};"><strong>{dr_str}</strong></td></tr>')
        if ms.get("open_rate_pct") is not None and ms["opened"] > 0:
            parts.append(f'<tr><td style="padding:2px 10px 2px 0;">Open rate</td>'
                         f'<td style="padding:2px 0;"><strong>{ms["open_rate_pct"]}%</strong></td></tr>')
        parts.append('</table>')

    # Per-program breakdown
    prog_items = [(k, v) for k, v in report["programs"].items()
                  if k in MARKETING_PROGRAMS]
    for prog, stats in prog_items:
        if stats["sent"] == 0:
            continue
        parts.append(f'<p style="font-size:12px;font-family:monospace;margin:6px 0 2px 0;">'
                     f'<strong>{stats["label"]}</strong><br>'
                     f'Sent: {stats["sent"]} | '
                     f'Delivered: {stats["delivered"]} | '
                     f'Bounced: {stats["bounced"]} | '
                     f'Delivery: {stats["delivery_rate_pct"]}%')
        if stats["opened"] > 0:
            parts.append(f' | Open rate: {stats["open_rate_pct"]}%')
        else:
            parts.append(' | Opens: not tracked yet')
        parts.append('</p>')
        if stats["bounced_details"]:
            parts.append('<ul style="font-size:11px;color:#c62828;margin:2px 0 6px 0;">')
            for b in stats["bounced_details"]:
                to_str = ", ".join(b["to"])
                parts.append(f'<li>{b["date"]} — {to_str} (subject: {b["subject"][:50]})</li>')
            parts.append('</ul>')

    # Subscriber counts
    subs = report.get("subscribers", {})
    sub_lines = []
    if subs.get("treestock") is not None:
        sub_lines.append(f'treestock.com.au: {subs["treestock"]} subscribers')
    if subs.get("beestock") is not None:
        sub_lines.append(f'beestock.com.au: {subs["beestock"]} subscribers')
    if sub_lines:
        parts.append(f'<p style="font-size:12px;font-family:monospace;color:#555;">'
                     f'Subscribers: {" | ".join(sub_lines)}</p>')

    if ms["sent"] > 0 and ms.get("open_rate_pct") is None:
        parts.append(
            '<p style="font-size:11px;color:#aaa;">Open rate tracking: enable open tracking '
            'in Resend dashboard settings to get open rates.</p>'
        )

    return "\n".join(parts)


def render_text(report: dict) -> str:
    """Render report as plaintext."""
    p_days = report["period_days"]
    p_start = report["period_start"]
    p_end = report["period_end"]
    ms = report["marketing_summary"]

    lines = [
        f"Email Delivery Report ({p_days}d: {p_start} to {p_end})",
        "-" * 50,
    ]
    if ms["sent"] == 0:
        lines.append("No marketing emails sent in this period.")
    else:
        dr_str = f'{ms["delivery_rate_pct"]}%' if ms["delivery_rate_pct"] is not None else "N/A"
        lines += [
            f'  Sent:          {ms["sent"]}',
            f'  Delivered:     {ms["delivered"]}',
            f'  Bounced:       {ms["bounced"]}',
            f'  Delivery rate: {dr_str}',
        ]
        if ms["opened"] > 0:
            lines.append(f'  Open rate:     {ms["open_rate_pct"]}%')
        else:
            lines.append('  Open rate:     not tracked yet')
    lines.append("")

    for prog, stats in report["programs"].items():
        if prog not in MARKETING_PROGRAMS or stats["sent"] == 0:
            continue
        dr_str = f'{stats["delivery_rate_pct"]}%' if stats["delivery_rate_pct"] is not None else "N/A"
        lines.append(f'{stats["label"]}:')
        lines.append(f'  {stats["sent"]} sent, {stats["delivered"]} delivered, '
                     f'{stats["bounced"]} bounced ({dr_str} delivery)')
        for b in stats["bounced_details"]:
            lines.append(f'  BOUNCE: {b["date"]} {", ".join(b["to"])}')
        lines.append("")

    subs = report.get("subscribers", {})
    if subs.get("treestock") is not None:
        lines.append(f'treestock subscribers: {subs["treestock"]}')
    if subs.get("beestock") is not None:
        lines.append(f'beestock subscribers: {subs["beestock"]}')

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--email", action="store_true", help="Send report email")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no save/send")
    args = parser.parse_args()

    api_key = get_resend_key()
    print("Fetching Resend email data...")
    emails = fetch_emails(api_key)
    print(f"Fetched {len(emails)} emails")

    report = build_report(emails, days=args.days)
    html = render_html(report)
    text = render_text(report)

    print(text)

    if args.dry_run:
        return

    # Save JSON
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Saved: {out_path}")

    if args.email:
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from notify import send_email
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subject = f"Email Delivery Report — {today}"
        if send_email(subject, html, text):
            print("Report email sent")
        else:
            print("ERROR: Failed to send report email", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
