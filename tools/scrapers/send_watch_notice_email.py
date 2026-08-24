#!/usr/bin/env python3
"""
Tell someone they are now watching a variety, at the moment they ask for it.

DEC-294 made per-variety alerts the product but never told anyone they had
subscribed. First contact could be weeks later, when a restock finally fired,
by which time the alert reads as unsolicited mail. This is the acknowledgement:
what you are watching, that one alert covers BOTH triggers, and two ways out.

Launched non-blocking from subscribe_server.py with subprocess.Popen, the same
shape as send_manage_link_email.py and send_confirmation_email.py, so the HTTP
response returns before Resend is called.

THE THROTTLE IS THE ANTI-ABUSE CONTROL, NOT A COURTESY. The server sends at
most one of these per address per hour (WATCH_NOTICE_RATE_LIMIT_SECONDS), which
caps a victim of a forged-address attack at 24 emails a day rather than one per
watch created. Because of that the email lists EVERY variety the address
currently watches, not just the newest: a watch added inside a throttled window
is acknowledged by the next notice rather than lost.

The residual gap, stated rather than hidden: a watch added inside the window
when no further watch is ever added gets no notice of its own. The person still
had a notice within the hour telling them what they watch and how to stop, and
every alert email carries the same links.

Usage:
    python3 send_watch_notice_email.py EMAIL TOKEN [NEW_SLUG]
    python3 send_watch_notice_email.py --dry-run EMAIL TOKEN [NEW_SLUG]

The token is the same HMAC-SHA256-of-the-lowercase-email used by every other
preferences and stop link.
"""

import html as _html
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
VARIETY_WATCHES_DB = DATA_DIR / "variety_watches.db"

from stocklib.mailer import (FROM_EMAIL, FROM_NAME, REPLY_TO_EMAIL,
                             get_resend_api_key)
from stocklib.email_footer import watch_urls
from stocklib.variety_index import DEFAULT_INDEX_PATH, get_variety_index

SITE_URL = "https://treestock.com.au"

# The one sentence this email exists to say. Kept as a constant because it is
# the honest description of what a watch does, and DEC-294's copy said "back in
# stock" only while the watch had already started firing on price drops too.
BOTH_TRIGGERS = ("One alert covers both: we email you when it comes back into "
                 "stock anywhere we track, and when it drops in price.")


def load_watches(email: str, db_path: Path = None) -> list[tuple[str, str]]:
    """[(slug, stored_title)] for `email`, oldest first.

    Read here rather than passed on argv: the list is always current at send
    time, and a long watch list can outgrow an argv limit.
    """
    path = Path(db_path or VARIETY_WATCHES_DB)
    if not path.exists():
        return []
    try:
        con = sqlite3.connect(path)
        rows = con.execute(
            "SELECT variety_slug, variety_title FROM watches "
            "WHERE email = ? ORDER BY added_at", (email.lower(),)
        ).fetchall()
        con.close()
    except sqlite3.Error:
        return []
    return [(r[0], r[1]) for r in rows]


def build_html(email: str, token: str, watches: list[tuple[str, str]],
               new_slug: str = "", index_path: Path = None) -> str:
    """The notice body.

    Titles come from the canonical index, exactly as the alert emails do, and
    are escaped regardless: a slug that has left the dataset keeps whatever
    title was stored for it, and the older of those were caller-supplied.
    """
    index = get_variety_index(index_path or DEFAULT_INDEX_PATH)
    _, stop_all, manage_url = watch_urls(email, token, site_url=SITE_URL)

    def title_for(slug, stored):
        return index.display_title(slug, stored)

    lead_title = ""
    for slug, stored in watches:
        if slug == new_slug:
            lead_title = title_for(slug, stored)
            break
    if not lead_title and watches:
        lead_title = title_for(*watches[-1])

    rows = ""
    for slug, stored in watches:
        title = title_for(slug, stored)
        stop_one, _, _ = watch_urls(email, token, slug, title, site_url=SITE_URL)
        variety_url = f"{SITE_URL}/variety/{slug}.html"
        rows += f"""
      <tr>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6">
          <a href="{_html.escape(variety_url, quote=True)}" style="color:#15803d;text-decoration:none">{_html.escape(title)}</a>
        </td>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;text-align:right;font-size:0.85em">
          <a href="{_html.escape(stop_one, quote=True)}" style="color:#9ca3af">Stop</a>
        </td>
      </tr>"""

    heading = (f"You're now watching {_html.escape(lead_title)}"
               if lead_title else "Your treestock alerts")

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;margin:0;padding:24px">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb">

  <div style="background:#14532d;padding:20px 24px">
    <h1 style="color:white;margin:0;font-size:1.1em;font-weight:600">treestock.com.au</h1>
    <p style="color:#86efac;margin:4px 0 0;font-size:0.85em">Australian Nursery Stock Tracker</p>
  </div>

  <div style="padding:24px">
    <h2 style="margin:0 0 8px;color:#14532d;font-size:1.25em">
      &#128276; {heading}
    </h2>
    <p style="color:#6b7280;margin:0 0 20px;font-size:0.9em">
      {BOTH_TRIGGERS}
    </p>

    <p style="color:#374151;margin:0 0 8px;font-size:0.9em;font-weight:600">
      Everything {_html.escape(email)} is watching
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:0.9em">
      <tbody>{rows}
      </tbody>
    </table>

    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 14px;margin:20px 0 0">
      <p style="margin:0;color:#374151;font-size:0.85em">
        &#128205; <strong>Only want stock you can actually get?</strong>
        Tell us your state and we will skip nurseries that cannot deliver
        there. Right now more than half the varieties people watch cannot be
        bought in WA at all.
      </p>
    </div>

    <div style="margin-top:20px">
      <a href="{_html.escape(manage_url, quote=True)}" style="display:inline-block;background:#15803d;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:0.9em;font-weight:500">
        Set my state and see my alerts
      </a>
    </div>

    <p style="margin-top:16px;font-size:0.8em;color:#9ca3af">
      We only email about these varieties. No digest, no newsletter, nothing else.
    </p>
  </div>

  <div style="padding:0 24px 24px">
    <hr style="margin:0 0 12px;border:none;border-top:1px solid #e5e7eb">
    <p style="font-size:0.75em;color:#9ca3af;text-align:center;margin:0">
      You're receiving this because an alert was set for this address at
      <a href="{SITE_URL}" style="color:#6b7280">{SITE_URL}</a>.<br>
      Didn't do that?
      <a href="{_html.escape(stop_all, quote=True)}" style="color:#6b7280">Stop all my treestock alerts</a>
    </p>
  </div>

</div>
</body>
</html>"""


def send(email: str, token: str, new_slug: str = "", dry_run: bool = False,
         db_path: Path = None, index_path: Path = None) -> bool:
    watches = load_watches(email, db_path)
    if not watches:
        # Nothing to acknowledge. Happens if the watch was removed between the
        # server launching this and the process starting.
        print(f"No watches for {email}; no notice sent.")
        return True

    index = get_variety_index(index_path or DEFAULT_INDEX_PATH)
    lead = ""
    for slug, stored in watches:
        if slug == new_slug:
            lead = index.display_title(slug, stored)
            break
    if not lead:
        lead = index.display_title(*watches[-1])

    subject = f"You're now watching {lead} -- treestock.com.au"
    body = build_html(email, token, watches, new_slug, index_path)

    if dry_run:
        print(f"[DRY RUN] Would send watch notice to {email}")
        print(f"  Subject: {subject}")
        print(f"  Watching: {len(watches)} variety/varieties")
        return True

    api_key = get_resend_api_key()
    payload = {
        "from": f"{FROM_NAME} <{FROM_EMAIL}>",
        "reply_to": REPLY_TO_EMAIL,
        "to": [email],
        "subject": subject,
        "html": body,
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "treestock-watch-notice/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            print(f"Watch notice sent to {email}: {result.get('id', 'ok')}")
            return True
    except urllib.error.HTTPError as e:
        detail = e.read().decode() if e.fp else str(e)
        print(f"Failed to send watch notice to {email}: HTTP {e.code} -- {detail}",
              file=sys.stderr)
        return False
    except Exception as e:
        print(f"Failed to send watch notice to {email}: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("Usage: send_watch_notice_email.py [--dry-run] EMAIL TOKEN [NEW_SLUG]")
        sys.exit(1)
    ok = send(args[0].strip().lower(), args[1].strip(),
              args[2].strip() if len(args) > 2 else "", dry_run=dry_run)
    sys.exit(0 if ok else 1)
