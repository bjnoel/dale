#!/usr/bin/env python3
"""
Send a welcome email to a new beestock.com.au subscriber.

Usage:
    python3 send_bee_welcome_email.py EMAIL          # Send welcome to this email
    python3 send_bee_welcome_email.py --dry-run EMAIL  # Show what would be sent
"""

import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SECRETS_DIR = Path("/opt/dale/secrets")
RESEND_ENV = SECRETS_DIR / "resend.env"
APP_ENV = SECRETS_DIR / "app.env"

FROM_EMAIL = "alerts@mail.walkthrough.au"
FROM_NAME = "beestock.com.au"
SITE_URL = "https://beestock.com.au"
UNSUBSCRIBE_BASE = "https://beestock.com.au/unsubscribe"


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


def build_welcome_html(email: str, unsubscribe_url: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Welcome to beestock.com.au</title>
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:560px;margin:0 auto;padding:24px 16px;">

  <div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

    <!-- Header -->
    <div style="background:#92400e;padding:24px;text-align:center;">
      <h1 style="margin:0;color:white;font-size:1.4rem;font-weight:700;">beestock.com.au</h1>
      <p style="margin:6px 0 0;color:#fcd34d;font-size:0.9rem;">Australian Beekeeping Supply Price Tracker</p>
    </div>

    <!-- Body -->
    <div style="padding:24px;">

      <h2 style="margin:0 0 12px;color:#92400e;font-size:1.1rem;">You're subscribed!</h2>

      <p style="margin:0 0 16px;color:#374151;font-size:0.95rem;line-height:1.5;">
        Each day you'll get a digest of price changes and restocks across Australian
        beekeeping supply retailers. Find the best deals on extractors, hives,
        protective gear, varroa treatments, and more.
      </p>

      <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:16px;margin-bottom:20px;">
        <p style="margin:0 0 8px;font-weight:600;color:#92400e;font-size:0.9rem;">Retailers tracked:</p>
        <ul style="margin:0;padding-left:20px;color:#374151;font-size:0.9rem;line-height:1.6;">
          <li>Ecrotek (VIC)</li>
          <li>Buzzbee</li>
          <li>The Bee Store</li>
          <li>Flow Hive (NSW)</li>
        </ul>
      </div>

      <p style="margin:0 0 16px;color:#374151;font-size:0.95rem;line-height:1.5;">
        You'll only hear from us when there are actual price changes or restocks.
        No spam, no marketing. Just daily supply price data.
      </p>

      <div style="text-align:center;margin:24px 0;">
        <a href="{SITE_URL}" style="display:inline-block;background:#92400e;color:white;text-decoration:none;padding:10px 24px;border-radius:8px;font-weight:600;font-size:0.95rem;">
          Browse current prices &rarr;
        </a>
      </div>

      <p style="margin:0;color:#6b7280;font-size:0.85rem;line-height:1.5;">
        Questions? Just reply to this email. This is a small project built in Perth, WA.
        Feedback is very welcome.
      </p>

    </div>

    <!-- Footer -->
    <div style="border-top:1px solid #e5e7eb;padding:16px 24px;text-align:center;">
      <p style="margin:0;font-size:0.75rem;color:#9ca3af;">
        You subscribed at <a href="{SITE_URL}" style="color:#6b7280;">{SITE_URL}</a>.<br>
        <a href="{unsubscribe_url}" style="color:#6b7280;">Unsubscribe</a>
      </p>
    </div>

  </div>
</div>
</body>
</html>"""


def send_welcome(email: str, dry_run: bool = False) -> bool:
    secret = get_unsubscribe_secret()
    token = make_unsubscribe_token(email, secret) if secret else ""
    unsubscribe_url = f"{UNSUBSCRIBE_BASE}?email={urllib.parse.quote(email)}&token={token}"
    html = build_welcome_html(email, unsubscribe_url)
    subject = "Welcome to beestock.com.au"

    if dry_run:
        print(f"[DRY RUN] Would send welcome email to: {email}")
        print(f"  Subject: {subject}")
        print(f"  Unsubscribe: {unsubscribe_url}")
        return True

    api_key = get_resend_api_key()
    payload = {
        "from": f"{FROM_NAME} <{FROM_EMAIL}>",
        "to": [email],
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
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            print(f"Welcome email sent to {email}: {result.get('id', 'ok')}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Failed to send welcome email to {email}: HTTP {e.code} -- {body}")
        return False
    except Exception as e:
        print(f"Failed to send welcome email to {email}: {e}")
        return False


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Usage: send_bee_welcome_email.py [--dry-run] EMAIL")
        sys.exit(1)
    email = args[0].strip().lower()
    success = send_welcome(email, dry_run=dry_run)
    sys.exit(0 if success else 1)
