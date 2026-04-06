#!/usr/bin/env python3
"""
Send weekly nursery stock digest to email subscribers via Resend.

Compares today's snapshot against 7 days ago to produce a curated weekly
summary: biggest price drops, notable restocks, interesting new arrivals.

Runs Sundays at 23:00 UTC (= Monday 7am AWST).

Usage:
    python3 send_weekly_digest.py                    # Send to all subscribers
    python3 send_weekly_digest.py --dry-run          # Preview without sending
    python3 send_weekly_digest.py --test EMAIL       # Send to one address only
    python3 send_weekly_digest.py --date 2026-04-06  # Use specific end date

Australian Spam Act compliance:
    - Every email includes a working unsubscribe link
    - From address is clearly identified
    - Unsubscribe requests are honoured immediately via subscribe_server.py
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

sys.path.insert(0, str(Path(__file__).parent))
from daily_digest import load_snapshot, compare_snapshots, NURSERY_NAMES
from shipping import SHIPPING_MAP, nursery_ships_to

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
NURSERY_STOCK_DIR = DATA_DIR / "nursery-stock"
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
WEEKLY_SENDS_LOG = DATA_DIR / "weekly_digest_sends.json"
RESEND_ENV = SECRETS_DIR / "resend.env"
APP_ENV = SECRETS_DIR / "app.env"

FROM_EMAIL = "alerts@mail.treestock.com.au"
FROM_NAME = "treestock.com.au"
SITE_URL = "https://treestock.com.au"

# Caps to keep emails scannable
MAX_PRICE_DROPS = 8
MAX_RESTOCKS = 8
MAX_NEW_ARRIVALS = 8


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
        return json.load(f)


def load_sends_log() -> dict:
    if not WEEKLY_SENDS_LOG.exists():
        return {}
    with open(WEEKLY_SENDS_LOG) as f:
        return json.load(f)


def save_sends_log(log: dict):
    WEEKLY_SENDS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(WEEKLY_SENDS_LOG, "w") as f:
        json.dump(log, f, indent=2)


def get_subscriber_state(subscriber: dict) -> str:
    if "state" in subscriber:
        return subscriber["state"]
    if subscriber.get("wa_only"):
        return "WA"
    return "ALL"


def load_weekly_changes(end_date: str, state_filter: str = "") -> dict:
    """
    Compare snapshot from 7 days ago vs end_date snapshot for all nurseries.

    Returns dict of {nursery_key: changes} where changes has price_drops,
    back_in_stock, new_products. Items are enriched with significance scores.
    """
    end = date.fromisoformat(end_date)
    start = end - timedelta(days=7)
    start_date = start.isoformat()

    all_changes = {}

    for nursery_dir in sorted(NURSERY_STOCK_DIR.iterdir()):
        if not nursery_dir.is_dir():
            continue
        nursery_key = nursery_dir.name

        if state_filter and not nursery_ships_to(nursery_key, state_filter):
            continue

        # Try to find the best "start" snapshot within the window
        # (may not have data from exactly 7 days ago, try 6-8 days back)
        prev = {}
        for delta in [7, 6, 8, 5, 9]:
            try_date = (end - timedelta(days=delta)).isoformat()
            prev = load_snapshot(nursery_dir, try_date)
            if prev:
                break

        curr = load_snapshot(nursery_dir, end_date)
        if not prev or not curr:
            continue

        changes = compare_snapshots(prev, curr)

        # Score price drops by % discount descending
        for item in changes["price_drops"]:
            old = item["old_price"]
            new = item["new_price"]
            item["pct_drop"] = round((old - new) / old * 100, 1) if old > 0 else 0
        changes["price_drops"].sort(key=lambda x: -x.get("pct_drop", 0))

        # New arrivals: sort by price ascending (value items first)
        changes["new_products"].sort(
            key=lambda x: x.get("price") or 999999
        )

        all_changes[nursery_key] = changes

    return all_changes


def format_weekly_html(all_changes: dict, end_date: str, state_filter: str = "") -> str:
    """Build a curated weekly digest HTML email."""
    start = (date.fromisoformat(end_date) - timedelta(days=7)).strftime("%-d %b")
    end_fmt = date.fromisoformat(end_date).strftime("%-d %b %Y")
    date_range = f"{start} — {end_fmt}"

    # Collect top items across all nurseries
    top_price_drops = []
    top_restocks = []
    top_new_arrivals = []

    for nursery_key, changes in sorted(all_changes.items()):
        name = NURSERY_NAMES.get(nursery_key, nursery_key)

        for item in changes["price_drops"]:
            top_price_drops.append({**item, "nursery": name, "nursery_key": nursery_key})

        for item in changes["back_in_stock"]:
            top_restocks.append({**item, "nursery": name, "nursery_key": nursery_key})

        for item in changes["new_products"]:
            top_new_arrivals.append({**item, "nursery": name, "nursery_key": nursery_key})

    # Sort globally and cap
    top_price_drops.sort(key=lambda x: -x.get("pct_drop", 0))
    top_price_drops = top_price_drops[:MAX_PRICE_DROPS]

    top_new_arrivals.sort(key=lambda x: x.get("price") or 999999)
    top_new_arrivals = top_new_arrivals[:MAX_NEW_ARRIVALS]

    top_restocks = top_restocks[:MAX_RESTOCKS]

    has_any = top_price_drops or top_restocks or top_new_arrivals

    # Build content sections
    sections = []

    def utm(url):
        if not url:
            return url
        sep = "&" if "?" in url else "?"
        return url + sep + "utm_source=treestock&utm_medium=email&utm_campaign=weekly"

    if top_price_drops:
        rows = []
        for item in top_price_drops:
            url = utm(item.get("url", ""))
            link = (
                f'<a href="{url}" style="color:#065f46;text-decoration:none">{item["title"]}</a>'
                if url else item["title"]
            )
            pct = f' <span style="color:#059669;font-size:0.85em">(-{item["pct_drop"]}%)</span>' if item.get("pct_drop") else ""
            rows.append(
                f'<tr>'
                f'<td style="padding:8px 0;border-bottom:1px solid #f3f4f6">'
                f'{link}<br>'
                f'<span style="font-size:0.85em;color:#6b7280">{item["nursery"]}</span>'
                f'</td>'
                f'<td style="padding:8px 0 8px 16px;border-bottom:1px solid #f3f4f6;text-align:right;white-space:nowrap">'
                f'<span style="text-decoration:line-through;color:#9ca3af">${item["old_price"]:.2f}</span>'
                f' <strong style="color:#059669">${item["new_price"]:.2f}</strong>{pct}'
                f'</td>'
                f'</tr>'
            )
        sections.append(
            f'<h3 style="color:#065f46;margin:24px 0 8px;font-size:1rem">📉 Price drops</h3>'
            f'<table style="width:100%;border-collapse:collapse">{"".join(rows)}</table>'
        )

    if top_restocks:
        rows = []
        for item in top_restocks:
            url = utm(item.get("url", ""))
            link = (
                f'<a href="{url}" style="color:#065f46;text-decoration:none">{item["title"]}</a>'
                if url else item["title"]
            )
            price_str = f' — <strong>${item["price"]:.2f}</strong>' if item.get("price") else ""
            rows.append(
                f'<li style="padding:6px 0;border-bottom:1px solid #f3f4f6">'
                f'{link}{price_str}'
                f'<br><span style="font-size:0.85em;color:#6b7280">{item["nursery"]}</span>'
                f'</li>'
            )
        sections.append(
            f'<h3 style="color:#065f46;margin:24px 0 8px;font-size:1rem">✅ Back in stock</h3>'
            f'<ul style="list-style:none;padding:0;margin:0">{"".join(rows)}</ul>'
        )

    if top_new_arrivals:
        rows = []
        for item in top_new_arrivals:
            url = utm(item.get("url", ""))
            link = (
                f'<a href="{url}" style="color:#065f46;text-decoration:none">{item["title"]}</a>'
                if url else item["title"]
            )
            price_str = f' — <strong>${item["price"]:.2f}</strong>' if item.get("price") else ""
            rows.append(
                f'<li style="padding:6px 0;border-bottom:1px solid #f3f4f6">'
                f'{link}{price_str}'
                f'<br><span style="font-size:0.85em;color:#6b7280">{item["nursery"]}</span>'
                f'</li>'
            )
        sections.append(
            f'<h3 style="color:#065f46;margin:24px 0 8px;font-size:1rem">🆕 New this week</h3>'
            f'<ul style="list-style:none;padding:0;margin:0">{"".join(rows)}</ul>'
        )

    if not has_any:
        sections.append('<p style="color:#6b7280">All quiet this week — no notable changes across the nurseries.</p>')

    # Stats line
    total_drops = sum(len(c["price_drops"]) for c in all_changes.values())
    total_restocks = sum(len(c["back_in_stock"]) for c in all_changes.values())
    total_new = sum(len(c["new_products"]) for c in all_changes.values())
    nursery_count = len(SHIPPING_MAP)

    stats_parts = []
    if total_drops:
        stats_parts.append(f"{total_drops} price drop{'s' if total_drops != 1 else ''}")
    if total_restocks:
        stats_parts.append(f"{total_restocks} restock{'s' if total_restocks != 1 else ''}")
    if total_new:
        stats_parts.append(f"{total_new} new listing{'s' if total_new != 1 else ''}")
    stats_str = ", ".join(stats_parts) if stats_parts else "no changes"

    state_note = f" (filtered to {state_filter})" if state_filter else ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:560px;margin:0 auto;padding:24px 16px;">
<div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

  <!-- Header -->
  <div style="background:#065f46;padding:24px;text-align:center;">
    <h1 style="margin:0;color:white;font-size:1.3rem;font-weight:700;">treestock.com.au</h1>
    <p style="margin:6px 0 0;color:#a7f3d0;font-size:0.85rem;">Weekly Stock Digest</p>
  </div>

  <!-- Body -->
  <div style="padding:24px;">
    <h2 style="margin:0 0 4px;color:#065f46;font-size:1.1rem;">This week{state_note}</h2>
    <p style="margin:0 0 20px;color:#6b7280;font-size:0.85rem;">{date_range} across {nursery_count} nurseries — {stats_str}</p>

    {"".join(sections)}

    <div style="margin-top:24px;text-align:center;">
      <a href="{SITE_URL}?utm_source=treestock&utm_medium=email&utm_campaign=weekly"
         style="display:inline-block;background:#065f46;color:white;text-decoration:none;padding:10px 24px;border-radius:8px;font-weight:600;font-size:0.95rem;">
        Browse all current stock &rarr;
      </a>
    </div>

  </div>

</div>
</div>
</body>
</html>"""


def inject_footer(html: str, email: str, token: str, state: str) -> str:
    encoded_email = urllib.parse.quote(email)
    unsubscribe_url = f"{SITE_URL}/unsubscribe.html?email={encoded_email}&token={token}"
    preferences_url = f"{SITE_URL}/api/preferences?email={encoded_email}&token={token}"
    state_label = f"Filtered to: {state}" if state != "ALL" else "Showing: all states"

    footer = f"""
<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.75em;color:#9ca3af;text-align:center">
  You're receiving this because you subscribed at <a href="{SITE_URL}" style="color:#6b7280">{SITE_URL}</a>.<br>
  {state_label} &middot; <a href="{preferences_url}" style="color:#6b7280">Change state</a> &middot; <a href="{unsubscribe_url}" style="color:#6b7280">Unsubscribe</a>
</p>
"""
    if "</body>" in html:
        return html.replace("</body>", footer + "</body>", 1)
    return html + footer


def send_email(api_key: str, to_email: str, subject: str, html_body: str) -> bool:
    payload = {
        "from": f"{FROM_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "treestock-weekly/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            print(f"  Sent to {to_email}: {result.get('id', 'ok')}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.fp.read().decode() if e.fp else str(e)
        print(f"  FAILED {to_email} ({e.code}): {error_body}", file=sys.stderr)
        return False


def main():
    dry_run = "--dry-run" in sys.argv
    test_email = None
    end_date = date.today().isoformat()
    week_key = f"week-{end_date}"

    if "--test" in sys.argv:
        idx = sys.argv.index("--test")
        test_email = sys.argv[idx + 1]

    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        end_date = sys.argv[idx + 1]
        week_key = f"week-{end_date}"

    print(f"send_weekly_digest.py — week ending {end_date}{' [DRY RUN]' if dry_run else ''}")

    # Load subscribers
    all_subscribers = load_subscribers()
    if test_email:
        existing = next((s for s in all_subscribers if s["email"] == test_email.lower()), None)
        test_state = (existing or {}).get("state", "ALL")
        subscribers = [{"email": test_email, "state": test_state}]
        print(f"TEST MODE: Sending only to {test_email} (state={test_state})")
    else:
        subscribers = all_subscribers

    if not subscribers:
        print("No subscribers.")
        return

    # Idempotency
    sends_log = load_sends_log()
    already_sent = set() if test_email else set(sends_log.get(week_key, []))
    to_send = [s for s in subscribers if s["email"] not in already_sent]
    skipped = len(subscribers) - len(to_send)

    print(f"Subscribers: {len(subscribers)} total, {len(to_send)} to send, {skipped} already sent this week")

    if not to_send:
        print("All subscribers already received this week's digest.")
        return

    # Group by state for efficient digest generation
    by_state: dict[str, list] = {}
    for s in to_send:
        state = s.get("state", "ALL")
        if s.get("wa_only"):
            state = "WA"
        by_state.setdefault(state, []).append(s)

    print(f"States: {', '.join(f'{st}({len(subs)})' for st, subs in sorted(by_state.items()))}")

    if dry_run:
        for s in to_send:
            state = s.get("state", "ALL")
            print(f"  Would send to: {s['email']} (state={state})")
            # Load and preview changes
        all_changes = load_weekly_changes(end_date)
        total_drops = sum(len(c["price_drops"]) for c in all_changes.values())
        total_restocks = sum(len(c["back_in_stock"]) for c in all_changes.values())
        total_new = sum(len(c["new_products"]) for c in all_changes.values())
        print(f"  Changes found: {total_drops} price drops, {total_restocks} restocks, {total_new} new arrivals")
        return

    api_key = get_resend_api_key()
    secret = get_unsubscribe_secret()
    start_fmt = (date.fromisoformat(end_date) - timedelta(days=7)).strftime("%-d %b")
    end_fmt = date.fromisoformat(end_date).strftime("%-d %b %Y")
    subject = f"Weekly Nursery Digest — {start_fmt} to {end_fmt}"

    html_cache: dict[str, str] = {}
    sent_emails = list(already_sent)
    failed = 0

    for state, state_subscribers in sorted(by_state.items()):
        if state not in html_cache:
            filter_state = "" if state == "ALL" else state
            all_changes = load_weekly_changes(end_date, state_filter=filter_state)
            html_cache[state] = format_weekly_html(all_changes, end_date, state_filter=filter_state)

        digest_html = html_cache[state]

        for subscriber in state_subscribers:
            email = subscriber["email"]
            token = make_unsubscribe_token(email, secret)
            personalised_html = inject_footer(digest_html, email, token, state)
            success = send_email(api_key, email, subject, personalised_html)
            if success:
                sent_emails.append(email)
            else:
                failed += 1

    if not test_email:
        sends_log[week_key] = sent_emails
        save_sends_log(sends_log)

    print(f"Done: {len(sent_emails) - len(already_sent)} sent, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
