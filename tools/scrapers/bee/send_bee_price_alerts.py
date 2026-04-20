#!/usr/bin/env python3
"""
Send daily price drop email alerts to beestock.com.au subscribers.

Compares today's snapshots with yesterday's to find price drops. If any
are found, sends a digest email to all confirmed subscribers.

Usage:
    python3 send_bee_price_alerts.py                   # Today's drops
    python3 send_bee_price_alerts.py --date 2026-04-19 # Specific date
    python3 send_bee_price_alerts.py --dry-run          # Preview, no send
    python3 send_bee_price_alerts.py --redirect-to me@example.com  # Test send

--redirect-to sends every alert to the given address (with the original
recipient noted in the subject and a banner injected into the body) and
does NOT update the sends log. Useful for previewing.

Australian Spam Act compliance:
    - Every email includes a working unsubscribe link
    - Unsubscribe requests are honoured via bee_subscribe_server.py
"""

import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
SUBSCRIBERS_FILE = DATA_DIR / "bee-subscribers.json"
ALERT_SENDS_LOG = DATA_DIR / "bee-price-alert-sends.json"
RESEND_ENV = SECRETS_DIR / "resend.env"
APP_ENV = SECRETS_DIR / "app.env"

FROM_EMAIL = "alerts@mail.walkthrough.au"
FROM_NAME = "beestock.com.au"
SITE_URL = "https://beestock.com.au"
UNSUBSCRIBE_BASE = f"{SITE_URL}/unsubscribe"

# Import from sibling module
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).parent))
from bee_daily_digest import load_all_changes
from bee_retailers import RETAILER_NAMES, SHIPPING_MAP


def get_resend_api_key() -> str:
    with open(RESEND_ENV) as f:
        for line in f:
            line = line.strip()
            if line.startswith("RESEND_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise ValueError("RESEND_API_KEY not found in resend.env")


def get_unsubscribe_secret() -> str:
    if APP_ENV.exists():
        with open(APP_ENV) as f:
            for line in f:
                line = line.strip()
                if line.startswith("UNSUBSCRIBE_SECRET="):
                    return line.split("=", 1)[1].strip()
    return ""


def make_unsubscribe_token(email: str, secret: str) -> str:
    return hmac.new(
        secret.encode(),
        email.lower().encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def load_subscribers() -> list:
    if not SUBSCRIBERS_FILE.exists():
        return []
    with open(SUBSCRIBERS_FILE) as f:
        data = json.load(f)
    return [s for s in data if s.get("email")]


def load_sends_log() -> dict:
    if not ALERT_SENDS_LOG.exists():
        return {}
    with open(ALERT_SENDS_LOG) as f:
        return json.load(f)


def save_sends_log(log: dict):
    with open(ALERT_SENDS_LOG, "w") as f:
        json.dump(log, f, indent=2)


def collect_price_drops(all_changes: dict) -> list:
    """Flatten all price drops across all retailers into a single sorted list."""
    drops = []
    for retailer_key, changes in sorted(all_changes.items()):
        name = RETAILER_NAMES.get(retailer_key, retailer_key)
        for item in changes.get("price_drops", []):
            old_price = item.get("old_price", 0)
            new_price = item.get("new_price", 0)
            if old_price > 0:
                pct = (old_price - new_price) / old_price * 100
            else:
                pct = 0
            drops.append({
                "retailer": name,
                "retailer_key": retailer_key,
                "title": item["title"],
                "old_price": old_price,
                "new_price": new_price,
                "pct_off": pct,
                "url": item.get("url", ""),
            })
    # Sort by percentage discount descending
    drops.sort(key=lambda x: x["pct_off"], reverse=True)
    return drops


def build_email_html(drops: list, target_date: str, unsubscribe_url: str,
                     redirect_banner: str = "") -> str:
    """Build the HTML email body for a price drop digest."""
    # Group drops by retailer for display
    by_retailer: dict[str, list] = {}
    for d in drops:
        by_retailer.setdefault(d["retailer"], []).append(d)

    # Build retailer sections
    sections_html = []
    for retailer_name, items in by_retailer.items():
        rows = []
        for item in items:
            url = item["url"]
            utm_url = url + ("&" if "?" in url else "?") + "utm_source=beestock&utm_medium=email&utm_campaign=pricedrop" if url else ""
            link = (
                f'<a href="{utm_url}" style="color:#92400e;text-decoration:none;font-weight:600;">'
                f'{item["title"]}</a>'
            ) if utm_url else f'<strong>{item["title"]}</strong>'
            pct_label = f'<span style="background:#dcfce7;color:#166534;font-size:0.8rem;padding:2px 6px;border-radius:9999px;font-weight:600;">{item["pct_off"]:.0f}% off</span>'
            rows.append(
                f'<tr style="border-bottom:1px solid #f3f4f6;">'
                f'<td style="padding:10px 0;">{link}<br>'
                f'<span style="color:#6b7280;font-size:0.85rem;">'
                f'<span style="text-decoration:line-through;">${item["old_price"]:.2f}</span>'
                f' &rarr; <strong style="color:#166534;">${item["new_price"]:.2f}</strong>'
                f' {pct_label}</span>'
                f'</td>'
                f'</tr>'
            )
        sections_html.append(
            f'<h3 style="margin:20px 0 8px;font-size:0.95rem;color:#374151;font-weight:600;">'
            f'{retailer_name}</h3>'
            f'<table style="width:100%;border-collapse:collapse;">{"".join(rows)}</table>'
        )

    total = len(drops)
    retailer_count = len(by_retailer)
    subject_context = (
        f"{total} price drop{'s' if total != 1 else ''} "
        f"across {retailer_count} retailer{'s' if retailer_count != 1 else ''}"
    )

    banner_html = ""
    if redirect_banner:
        banner_html = (
            f'<div style="background:#fef3c7;border:2px solid #f59e0b;padding:12px;margin-bottom:16px;'
            f'border-radius:6px;font-size:0.85rem;color:#92400e;">'
            f'<strong>TEST REDIRECT:</strong> {redirect_banner}'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Beekeeping Price Drops - {target_date}</title>
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:560px;margin:0 auto;padding:24px 16px;">

  <div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

    <!-- Header -->
    <div style="background:#92400e;padding:20px 24px;">
      <h1 style="margin:0;color:white;font-size:1.2rem;font-weight:700;">beestock.com.au</h1>
      <p style="margin:4px 0 0;color:#fcd34d;font-size:0.85rem;">Price Drop Alert</p>
    </div>

    <!-- Body -->
    <div style="padding:20px 24px;">

      {banner_html}

      <p style="margin:0 0 4px;color:#374151;font-size:0.9rem;">
        {target_date}
      </p>
      <p style="margin:0 0 16px;color:#92400e;font-size:1.05rem;font-weight:600;">
        {subject_context} today
      </p>

      {"".join(sections_html)}

      <div style="margin-top:20px;text-align:center;">
        <a href="{SITE_URL}?utm_source=beestock&utm_medium=email&utm_campaign=pricedrop"
           style="display:inline-block;background:#92400e;color:white;text-decoration:none;padding:10px 24px;border-radius:8px;font-weight:600;font-size:0.9rem;">
          Browse all prices &rarr;
        </a>
      </div>

    </div>

    <!-- Footer -->
    <div style="border-top:1px solid #e5e7eb;padding:14px 24px;text-align:center;">
      <p style="margin:0;font-size:0.75rem;color:#9ca3af;">
        You subscribed at <a href="{SITE_URL}" style="color:#6b7280;">{SITE_URL}</a>.
        Tracking {len(SHIPPING_MAP)} Australian beekeeping retailers daily.<br>
        <a href="{unsubscribe_url}" style="color:#6b7280;">Unsubscribe</a>
      </p>
    </div>

  </div>
</div>
</body>
</html>"""


def send_email(
    to_email: str,
    subject: str,
    html: str,
    dry_run: bool = False,
) -> str | None:
    """Send email via Resend. Returns message ID on success, None on failure."""
    if dry_run:
        print(f"[DRY RUN] Would send to: {to_email}")
        print(f"  Subject: {subject}")
        return "dry-run"

    api_key = get_resend_api_key()
    payload = {
        "from": f"{FROM_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "beestock-alerts/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            msg_id = result.get("id", "ok")
            print(f"Sent to {to_email}: {msg_id}")
            return msg_id
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR sending to {to_email}: HTTP {e.code} -- {body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR sending to {to_email}: {e}", file=sys.stderr)
        return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Send beestock daily price drop alerts")
    parser.add_argument("--date", help="Date to check (default: today)", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--redirect-to", metavar="EMAIL",
                        help="Send all alerts to this address (test mode)")
    parser.add_argument("--data-dir", help="Path to bee-stock directory",
                        default="/opt/dale/data/bee-stock")
    args = parser.parse_args()

    target_date = args.date or date.today().isoformat()
    data_dir = Path(args.data_dir)

    if not data_dir.exists():
        print(f"ERROR: data dir {data_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    # Load changes
    all_changes, total_changes = load_all_changes(data_dir, target_date)
    drops = collect_price_drops(all_changes)

    print(f"Date: {target_date}")
    print(f"Total price drops found: {len(drops)}")

    if not drops:
        print("No price drops today. Skipping email send.")
        return

    # Load subscribers
    subscribers = load_subscribers()
    confirmed = subscribers  # No double opt-in for beestock (single opt-in)
    print(f"Subscribers: {len(confirmed)}")

    if not confirmed:
        print("No subscribers. Skipping email send.")
        return

    # Load sends log to avoid re-sending
    sends_log = load_sends_log()
    already_sent = sends_log.get(target_date, {})

    secret = get_unsubscribe_secret()

    total_count = len(drops)
    retailer_count = len({d["retailer_key"] for d in drops})
    subject = (
        f"{total_count} price drop{'s' if total_count != 1 else ''} today "
        f"({retailer_count} retailer{'s' if retailer_count != 1 else ''}) - beestock.com.au"
    )

    sent_count = 0
    for sub in confirmed:
        email = sub["email"]

        if email in already_sent and not args.redirect_to:
            print(f"Already sent to {email} for {target_date}, skipping.")
            continue

        token = make_unsubscribe_token(email, secret) if secret else ""
        unsubscribe_url = (
            f"{UNSUBSCRIBE_BASE}?email={urllib.parse.quote(email)}&token={token}"
        )

        redirect_banner = ""
        to_email = email
        send_subject = subject

        if args.redirect_to:
            to_email = args.redirect_to
            send_subject = f"[REDIRECT from {email}] {subject}"
            redirect_banner = f"Original recipient: {email}"

        html = build_email_html(drops, target_date, unsubscribe_url, redirect_banner)

        msg_id = send_email(to_email, send_subject, html, dry_run=args.dry_run)

        if msg_id and not args.redirect_to and not args.dry_run:
            if target_date not in sends_log:
                sends_log[target_date] = {}
            sends_log[target_date][email] = msg_id
            save_sends_log(sends_log)

        if msg_id:
            sent_count += 1

    print(f"Done. Sent {sent_count}/{len(confirmed)} alerts for {target_date}.")


if __name__ == "__main__":
    main()
