#!/usr/bin/env python3
"""
Send a subscription confirmation email to a pending treestock.com.au subscriber.

Usage:
    python3 send_confirmation_email.py EMAIL TOKEN [STATE]
    python3 send_confirmation_email.py --dry-run EMAIL TOKEN [STATE]
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

FROM_EMAIL = "alerts@mail.treestock.com.au"
FROM_NAME = "treestock.com.au"
SITE_URL = "https://treestock.com.au"
CONFIRM_BASE = "https://treestock.com.au/api/confirm"


def get_resend_api_key() -> str:
    with open(RESEND_ENV) as f:
        for line in f:
            line = line.strip()
            if line.startswith("RESEND_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise ValueError("RESEND_API_KEY not found in resend.env")


def build_confirmation_html(email: str, confirm_url: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Confirm your treestock.com.au subscription</title>
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:560px;margin:0 auto;padding:24px 16px;">

  <div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

    <!-- Header -->
    <div style="background:#065f46;padding:24px;text-align:center;">
      <h1 style="margin:0;color:white;font-size:1.4rem;font-weight:700;">treestock.com.au</h1>
      <p style="margin:6px 0 0;color:#a7f3d0;font-size:0.9rem;">Australian Nursery Stock Tracker</p>
    </div>

    <!-- Body -->
    <div style="padding:24px;">

      <h2 style="margin:0 0 12px;color:#065f46;font-size:1.1rem;">Confirm your subscription</h2>

      <p style="margin:0 0 16px;color:#374151;font-size:0.95rem;line-height:1.5;">
        You asked to subscribe to stock alerts from treestock.com.au.
        Click below to confirm and activate your subscription.
      </p>

      <div style="text-align:center;margin:28px 0;">
        <a href="{confirm_url}"
           style="display:inline-block;background:#065f46;color:white;text-decoration:none;
                  padding:12px 28px;border-radius:8px;font-weight:600;font-size:1rem;">
          Yes, subscribe me &rarr;
        </a>
      </div>

      <p style="margin:0 0 12px;color:#6b7280;font-size:0.85rem;line-height:1.5;">
        Or copy this link into your browser:
      </p>
      <p style="margin:0 0 20px;word-break:break-all;">
        <a href="{confirm_url}" style="color:#065f46;font-size:0.8rem;">{confirm_url}</a>
      </p>

      <p style="margin:0;color:#9ca3af;font-size:0.8rem;line-height:1.5;">
        If you didn't request this, you can safely ignore this email.
        No subscription will be created without clicking the link above.
      </p>

    </div>

    <!-- Footer -->
    <div style="border-top:1px solid #e5e7eb;padding:16px 24px;text-align:center;">
      <p style="margin:0;font-size:0.75rem;color:#9ca3af;">
        This request came from <a href="{SITE_URL}" style="color:#6b7280;">{SITE_URL}</a>.
      </p>
    </div>

  </div>
</div>
</body>
</html>"""


def build_confirmation_text(email: str, confirm_url: str) -> str:
    return f"""Confirm your treestock.com.au subscription
============================================

You asked to subscribe to stock alerts from treestock.com.au.
Click the link below to confirm and activate your subscription.

Confirm here: {confirm_url}

If you didn't request this, you can safely ignore this email.
No subscription will be created without clicking the link above.

-- treestock.com.au
"""


def send_confirmation(email: str, token: str, state: str = "ALL", dry_run: bool = False) -> bool:
    params = urllib.parse.urlencode({"email": email, "token": token})
    confirm_url = f"{CONFIRM_BASE}?{params}"
    html = build_confirmation_html(email, confirm_url)
    text = build_confirmation_text(email, confirm_url)
    subject = "Confirm your treestock.com.au subscription"

    if dry_run:
        print(f"[DRY RUN] Would send confirmation email to: {email}")
        print(f"  Subject: {subject}")
        print(f"  Confirm URL: {confirm_url}")
        return True

    api_key = get_resend_api_key()
    payload = {
        "from": f"{FROM_NAME} <{FROM_EMAIL}>",
        "to": [email],
        "subject": subject,
        "html": html,
        "text": text,
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
            print(f"Confirmation email sent to {email}: {result.get('id', 'ok')}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Failed to send confirmation email to {email}: HTTP {e.code} — {body}")
        return False
    except Exception as e:
        print(f"Failed to send confirmation email to {email}: {e}")
        return False


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("Usage: send_confirmation_email.py [--dry-run] EMAIL TOKEN [STATE]")
        sys.exit(1)
    email = args[0].strip().lower()
    token = args[1].strip()
    state = args[2].upper() if len(args) > 2 else "ALL"
    success = send_confirmation(email, token, state, dry_run=dry_run)
    sys.exit(0 if success else 1)
