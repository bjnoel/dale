#!/usr/bin/env python3
"""
Per-subscriber email engagement report from Resend.

Shows each subscriber's email history and engagement status (delivered, opened,
clicked, bounced). Run this to understand which subscribers are actually engaging
with the treestock.com.au emails.

Usage:
    python3 resend_engagement.py             # Print report for all treestock subscribers
    python3 resend_engagement.py --days 30   # Look back 30 days (default: 90)
    python3 resend_engagement.py --json      # Output JSON instead of text
    python3 resend_engagement.py --dry-run   # Don't save, just print

NOTE: Open and click tracking require Resend open/click tracking to be enabled
in the Resend dashboard (Domains > mail.treestock.com.au > Tracking settings).
Until that is enabled, all events will show as "delivered" only.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import urllib.request
import urllib.error

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
OUTPUT_FILE = DATA_DIR / "resend_engagement.json"

TREESTOCK_SENDERS = {
    "alerts@mail.treestock.com.au",
    "alerts@mail.scion.exchange",
}


def get_resend_key() -> str:
    env_path = SECRETS_DIR / "resend-readonly.env"
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("RESEND_FULL_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise ValueError("RESEND_FULL_API_KEY not found in resend-readonly.env")


def fetch_emails(api_key: str, limit: int = 100) -> list:
    url = f"https://api.resend.com/emails?limit={limit}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "dale-engagement-report/1.0",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        return data.get("data", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else str(e)
        raise RuntimeError(f"Resend API error ({e.code}): {body}")


def parse_ts(ts_str: str) -> datetime:
    ts = ts_str.replace(" ", "T")
    if not ts.endswith("+00:00") and "+" not in ts[10:] and "Z" not in ts:
        ts += "+00:00"
    return datetime.fromisoformat(ts)


def sender_addr(from_field: str) -> str:
    if "<" in from_field:
        return from_field.split("<")[-1].rstrip(">").strip().lower()
    return from_field.strip().lower()


def load_subscribers() -> list:
    if not SUBSCRIBERS_FILE.exists():
        return []
    with open(SUBSCRIBERS_FILE) as f:
        return json.load(f)


def build_engagement(emails: list, days: int = 90) -> dict:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Filter to treestock emails within the window
    treestock_emails = []
    for e in emails:
        if sender_addr(e.get("from", "")) not in TREESTOCK_SENDERS:
            continue
        try:
            if parse_ts(e["created_at"]) < cutoff:
                continue
        except Exception:
            continue
        treestock_emails.append(e)

    # Group by recipient
    by_recipient: dict[str, list] = defaultdict(list)
    for e in treestock_emails:
        for recipient in e.get("to", []):
            by_recipient[recipient.lower()].append(e)

    # Load current subscribers for cross-reference
    subscribers = load_subscribers()
    sub_emails = {s["email"].lower() for s in subscribers}
    sub_map = {s["email"].lower(): s for s in subscribers}

    # Build per-subscriber report
    subscriber_stats = []
    for sub_email in sorted(sub_emails):
        history = sorted(
            by_recipient.get(sub_email, []),
            key=lambda e: e["created_at"],
            reverse=True,
        )

        sent = len(history)
        delivered = sum(1 for e in history if e["last_event"] in ("delivered", "opened", "clicked"))
        opened = sum(1 for e in history if e["last_event"] in ("opened", "clicked"))
        clicked = sum(1 for e in history if e["last_event"] == "clicked")
        bounced = sum(1 for e in history if e["last_event"] == "bounced")

        # Most recent email details
        last_email = history[0] if history else None
        last_sent_at = last_email["created_at"][:10] if last_email else None
        last_subject = last_email.get("subject", "") if last_email else None
        last_event = last_email.get("last_event", "") if last_email else None

        # Classify engagement
        if bounced:
            engagement = "bounced"
        elif opened or clicked:
            engagement = "engaged"
        elif delivered:
            engagement = "delivered_no_open"
        elif sent == 0:
            engagement = "never_emailed"
        else:
            engagement = "unknown"

        sub_info = sub_map.get(sub_email, {})

        subscriber_stats.append({
            "email": sub_email,
            "state": sub_info.get("state", "ALL"),
            "subscribed_at": sub_info.get("subscribed_at", "")[:10],
            "emails_sent": sent,
            "delivered": delivered,
            "opened": opened,
            "clicked": clicked,
            "bounced": bounced,
            "last_sent_at": last_sent_at,
            "last_subject": last_subject,
            "last_event": last_event,
            "engagement": engagement,
        })

    # Recipients in Resend history who are NOT active subscribers
    unsub_recipients = [
        addr for addr in by_recipient
        if addr not in sub_emails and by_recipient[addr]
    ]

    total_sent = sum(s["emails_sent"] for s in subscriber_stats)
    total_delivered = sum(s["delivered"] for s in subscriber_stats)
    total_opened = sum(s["opened"] for s in subscriber_stats)
    total_clicked = sum(s["clicked"] for s in subscriber_stats)
    tracking_enabled = any(s["opened"] > 0 or s["clicked"] > 0 for s in subscriber_stats)

    return {
        "generated_at": now.isoformat(),
        "period_days": days,
        "period_start": cutoff.strftime("%Y-%m-%d"),
        "period_end": now.strftime("%Y-%m-%d"),
        "tracking_enabled": tracking_enabled,
        "summary": {
            "active_subscribers": len(sub_emails),
            "emails_sent": total_sent,
            "delivered": total_delivered,
            "opened": total_opened,
            "clicked": total_clicked,
            "open_rate_pct": round(total_opened / total_delivered * 100, 1) if total_delivered > 0 else None,
            "click_rate_pct": round(total_clicked / total_delivered * 100, 1) if total_delivered > 0 else None,
            "engagement_breakdown": {
                status: sum(1 for s in subscriber_stats if s["engagement"] == status)
                for status in ["engaged", "delivered_no_open", "never_emailed", "bounced", "unknown"]
            },
        },
        "subscribers": subscriber_stats,
        "unsubscribed_recipients_in_history": unsub_recipients,
    }


def render_text(report: dict) -> str:
    lines = [
        f"Subscriber Engagement Report ({report['period_days']}d: {report['period_start']} to {report['period_end']})",
        "=" * 60,
        "",
    ]

    if not report["tracking_enabled"]:
        lines += [
            "  WARNING: Open/click tracking is NOT enabled in Resend.",
            "  All events show as 'delivered' only. To enable:",
            "  1. Go to Resend dashboard > Domains > mail.treestock.com.au",
            "  2. Enable 'Open tracking' and 'Click tracking'",
            "  3. Re-send a digest and check this report again.",
            "",
        ]

    s = report["summary"]
    lines += [
        f"  Active subscribers: {s['active_subscribers']}",
        f"  Emails sent:        {s['emails_sent']}",
        f"  Delivered:          {s['delivered']}",
        (f"  Opened:             {s['opened']}  (open rate: {s['open_rate_pct']}%)" if s["open_rate_pct"] is not None else f"  Opened:             {s['opened']}  (tracking not enabled)"),
        f"  Clicked:            {s['clicked']}",
        "",
        "Engagement breakdown:",
    ]
    for status, count in s["engagement_breakdown"].items():
        if count > 0:
            lines.append(f"  {status:<25} {count}")
    lines.append("")

    lines.append("Per-subscriber detail:")
    lines.append("-" * 60)
    for sub in report["subscribers"]:
        engagement_icon = {
            "engaged": "[ENGAGED]",
            "delivered_no_open": "[delivered, no open]",
            "never_emailed": "[never emailed]",
            "bounced": "[BOUNCED]",
            "unknown": "[unknown]",
        }.get(sub["engagement"], sub["engagement"])
        lines.append(
            f"  {sub['email']:<35} {engagement_icon}"
        )
        lines.append(
            f"    subscribed: {sub['subscribed_at']}  state: {sub['state']}  "
            f"sent: {sub['emails_sent']}  opened: {sub['opened']}  clicked: {sub['clicked']}"
        )
        if sub["last_sent_at"]:
            subject_preview = (sub["last_subject"] or "")[:50]
            lines.append(
                f"    last email: {sub['last_sent_at']} — {subject_preview!r}  (event: {sub['last_event']})"
            )
        lines.append("")

    if report["unsubscribed_recipients_in_history"]:
        lines.append(f"Emails sent to non-subscribers in history ({len(report['unsubscribed_recipients_in_history'])}):")
        for addr in report["unsubscribed_recipients_in_history"]:
            lines.append(f"  {addr}")
        lines.append("")

    return "\n".join(lines)


def main():
    days = 90
    output_json = False
    dry_run = False

    args = sys.argv[1:]
    if "--days" in args:
        idx = args.index("--days")
        days = int(args[idx + 1])
    if "--json" in args:
        output_json = True
    if "--dry-run" in args:
        dry_run = True

    api_key = get_resend_key()
    print("Fetching Resend email data...")
    emails = fetch_emails(api_key, limit=100)
    print(f"Fetched {len(emails)} emails")

    report = build_engagement(emails, days=days)

    if output_json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))

    if not dry_run:
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
