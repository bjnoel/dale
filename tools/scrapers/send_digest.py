#!/usr/bin/env python3
"""
Send daily nursery stock digest to email subscribers via Resend.

Reads the pre-generated digest-wa-email.html and sends it to all wa_only
subscribers. Tracks sends to avoid duplicates (idempotent — safe to re-run).

Usage:
    python3 send_digest.py                    # Send WA digest to all wa_only subscribers
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
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
DASHBOARD_DIR = Path("/opt/dale/dashboard")
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
SENDS_LOG_FILE = DATA_DIR / "digest_sends.json"
RESEND_ENV = SECRETS_DIR / "resend.env"
APP_ENV = SECRETS_DIR / "app.env"

FROM_EMAIL = "alerts@mail.scion.exchange"
FROM_NAME = "treestock.com.au"
SITE_URL = "https://treestock.com.au"
UNSUBSCRIBE_BASE = f"{SITE_URL}/unsubscribe.html"


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


def load_digest_html(target_date: str, wa_only: bool = True) -> str | None:
    """Load pre-generated digest HTML. Falls back to archive if current missing."""
    # Try current (today's) version first
    suffix = "-wa" if wa_only else ""
    current = DASHBOARD_DIR / f"digest{suffix}-email.html"
    if current.exists():
        return current.read_text()
    # Try archive
    archive = DASHBOARD_DIR / "archive" / f"digest{suffix}-{target_date}.html"
    if archive.exists():
        return archive.read_text()
    return None


def inject_unsubscribe(html: str, email: str, token: str) -> str:
    """Add personalised unsubscribe footer to email HTML."""
    unsubscribe_url = f"{UNSUBSCRIBE_BASE}?email={urllib.parse.quote(email)}&token={token}"
    footer = f"""
<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.75em;color:#9ca3af;text-align:center">
  You're receiving this because you subscribed at <a href="{SITE_URL}" style="color:#6b7280">{SITE_URL}</a>.<br>
  <a href="{unsubscribe_url}" style="color:#6b7280">Unsubscribe</a>
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

    # Load digest HTML
    digest_html = load_digest_html(target_date, wa_only=True)
    if not digest_html:
        print(f"ERROR: No digest HTML found for {target_date}", file=sys.stderr)
        sys.exit(1)

    # Load subscribers
    all_subscribers = load_subscribers()
    if test_email:
        subscribers = [{"email": test_email, "wa_only": True}]
        print(f"TEST MODE: Sending only to {test_email}")
    else:
        subscribers = [s for s in all_subscribers if s.get("wa_only", True)]

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

    if dry_run:
        for s in to_send:
            print(f"  Would send to: {s['email']}")
        return

    api_key = get_resend_api_key()
    secret = get_unsubscribe_secret()
    subject = f"Nursery Stock Update — {target_date}"

    sent_emails = list(already_sent)
    failed = 0

    for subscriber in to_send:
        email = subscriber["email"]
        token = make_unsubscribe_token(email, secret)
        personalised_html = inject_unsubscribe(digest_html, email, token)

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
