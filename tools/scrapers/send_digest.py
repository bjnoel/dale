#!/usr/bin/env python3
"""
Send daily nursery stock digest to email subscribers via Resend.

Generates state-filtered digests per subscriber and sends individually.
Tracks sends to avoid duplicates (idempotent, safe to re-run).

Usage:
    python3 send_digest.py                    # Send to all subscribers
    python3 send_digest.py --dry-run          # Show who would receive it, no actual send
    python3 send_digest.py --test EMAIL       # Send to one address only (for testing)
    python3 send_digest.py --date 2026-03-11  # Use a specific date's digest

Australian Spam Act compliance:
    - Every email includes a working unsubscribe link
    - From address is clearly identified
    - Unsubscribe requests are honoured immediately (via subscribe_server.py)
"""

import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

# Import digest generation for per-state filtering
sys.path.insert(0, str(Path(__file__).parent))
from daily_digest import load_all_changes, format_html

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
NURSERY_STOCK_DIR = DATA_DIR / "nursery-stock"
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
SENDS_LOG_FILE = DATA_DIR / "digest_sends.json"
RESEND_ENV = SECRETS_DIR / "resend.env"
APP_ENV = SECRETS_DIR / "app.env"

FROM_EMAIL = "alerts@mail.scion.exchange"
FROM_NAME = "treestock.com.au"
SITE_URL = "https://treestock.com.au"
UNSUBSCRIBE_BASE = f"{SITE_URL}/unsubscribe.html"
PREFERENCES_BASE = f"{SITE_URL}/api/preferences"


def get_resend_api_key() -> str:
    with open(RESEND_ENV) as f:
        for line in f:
            line = line.strip()
            if line.startswith("RESEND_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise ValueError("RESEND_API_KEY not found in resend.env")


def get_unsubscribe_secret() -> str:
    """Load or create a stable HMAC secret for unsubscribe tokens."""
    if APP_ENV.exists():
        with open(APP_ENV) as f:
            for line in f:
                line = line.strip()
                if line.startswith("UNSUBSCRIBE_SECRET="):
                    return line.split("=", 1)[1].strip()
    # Generate a new secret and store it
    import secrets as _secrets
    secret = _secrets.token_hex(32)
    APP_ENV.parent.mkdir(parents=True, exist_ok=True)
    with open(APP_ENV, "a") as f:
        f.write(f"UNSUBSCRIBE_SECRET={secret}\n")
    print(f"Generated new UNSUBSCRIBE_SECRET in {APP_ENV}")
    return secret


def make_unsubscribe_token(email: str, secret: str) -> str:
    """Generate HMAC-SHA256 token for unsubscribe link."""
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
    """Returns dict of {date_str: [email, ...]} of already-sent digests."""
    if not SENDS_LOG_FILE.exists():
        return {}
    with open(SENDS_LOG_FILE) as f:
        return json.load(f)


def save_sends_log(log: dict):
    SENDS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SENDS_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


def get_subscriber_state(subscriber: dict) -> str:
    """Get subscriber's state preference, with backwards compat for wa_only."""
    if "state" in subscriber:
        return subscriber["state"]
    # Legacy: wa_only=true means WA
    if subscriber.get("wa_only"):
        return "WA"
    return "ALL"


def inject_footer(html: str, email: str, token: str, state: str) -> str:
    """Add personalised footer with unsubscribe + preferences links."""
    encoded_email = urllib.parse.quote(email)
    unsubscribe_url = f"{UNSUBSCRIBE_BASE}?email={encoded_email}&token={token}"
    preferences_url = f"{PREFERENCES_BASE}?email={encoded_email}&token={token}"

    state_label = f"Filtered to: {state}" if state != "ALL" else "Showing: all states"

    footer = f"""
<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.75em;color:#9ca3af;text-align:center">
  You're receiving this because you subscribed at <a href="{SITE_URL}" style="color:#6b7280">{SITE_URL}</a>.<br>
  {state_label} · <a href="{preferences_url}" style="color:#6b7280">Change state</a> · <a href="{unsubscribe_url}" style="color:#6b7280">Unsubscribe</a>
</p>
"""
    # Insert before </body> if present, else append
    if "</body>" in html:
        return html.replace("</body>", footer + "</body>", 1)
    return html + footer


def send_email(api_key: str, to_email: str, subject: str, html_body: str) -> bool:
    """Send a single email via Resend API."""
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
            "User-Agent": "treestock-digest/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"  Sent to {to_email}: {result.get('id', 'ok')}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        print(f"  FAILED {to_email} ({e.code}): {error_body}", file=sys.stderr)
        return False


def main():
    dry_run = "--dry-run" in sys.argv
    test_email = None
    target_date = date.today().isoformat()

    if "--test" in sys.argv:
        idx = sys.argv.index("--test")
        test_email = sys.argv[idx + 1]

    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        target_date = sys.argv[idx + 1]

    print(f"send_digest.py — {target_date}{' [DRY RUN]' if dry_run else ''}")

    # Load change data for state-filtered digest generation
    all_changes, total_changes = load_all_changes(NURSERY_STOCK_DIR, target_date)
    if not all_changes:
        print(f"WARNING: No change data for {target_date}", file=sys.stderr)

    # Load subscribers
    all_subscribers = load_subscribers()
    if test_email:
        subscribers = [{"email": test_email, "state": "ALL"}]
        print(f"TEST MODE: Sending only to {test_email}")
    else:
        subscribers = all_subscribers

    if not subscribers:
        print("No subscribers to send to.")
        return

    # Load send log (skip already-sent today)
    sends_log = load_sends_log()
    already_sent = set(sends_log.get(target_date, []))

    to_send = [s for s in subscribers if s["email"] not in already_sent]
    skipped = len(subscribers) - len(to_send)

    print(f"Subscribers: {len(subscribers)} total, {len(to_send)} to send, {skipped} already sent today")

    if not to_send:
        print("All subscribers already received today's digest.")
        return

    # Group subscribers by state for efficient digest generation
    by_state: dict[str, list] = {}
    for s in to_send:
        state = get_subscriber_state(s)
        by_state.setdefault(state, []).append(s)

    print(f"States: {', '.join(f'{st}({len(subs)})' for st, subs in sorted(by_state.items()))}")

    if dry_run:
        for s in to_send:
            state = get_subscriber_state(s)
            print(f"  Would send to: {s['email']} (state={state})")
        return

    api_key = get_resend_api_key()
    secret = get_unsubscribe_secret()
    subject = f"Nursery Stock Update — {target_date}"

    # Cache generated HTML per state
    html_cache: dict[str, str] = {}

    sent_emails = list(already_sent)
    failed = 0

    for state, state_subscribers in sorted(by_state.items()):
        # Generate digest HTML for this state (cached)
        if state not in html_cache:
            filter_state = "" if state == "ALL" else state
            html_cache[state] = format_html(all_changes, target_date, state=filter_state)

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

    # Save updated log
    sends_log[target_date] = sent_emails
    save_sends_log(sends_log)

    print(f"Done: {len(sent_emails) - len(already_sent)} sent, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
