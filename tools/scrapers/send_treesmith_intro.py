#!/usr/bin/env python3
"""
Send the one-off Treesmith introduction email to a treestock subscriber, about a
week after they subscribe, once and never again (DAL-173).

Benedict's brief on the ticket: "run it as a proof of concept first (send it as
an email only to me) that I can approve. I think it would be good if we could
send it to any new daily subscribers say ~1 week after they first subscribe
(and never again)."

So:

  --test EMAIL   sends one copy to that address and writes nothing to the sends
                 log. This is the proof of concept.
  --drip         the real run, intended for a daily cron. Picks subscribers who
                 signed up at least DRIP_DELAY_DAYS ago, on or after
                 DRIP_START_DATE, and who have never been sent this email.
                 Refuses to send unless ENABLED_FLAG exists, so the cron can be
                 installed before Benedict has approved the copy.
  --dry-run      with --drip, lists who would be emailed and sends nothing.

Two deliberate guards on the drip:

  DRIP_START_DATE excludes everyone who subscribed before the drip existed. The
  existing subscribers are the subject of a separate one-time broadcast that
  Benedict wants to approve on its own (DAL-221); the drip must not quietly
  send it to them first.

  MAX_PER_RUN caps a single run. If the cron is down for a month, the backlog is
  worked through over several days rather than in one burst that looks like a
  blast to a mailbox provider.

Australian Spam Act compliance: every send carries the shared unsubscribe and
preferences footer (stocklib.email_footer), same as the digests and alerts.

Usage:
    python3 send_treesmith_intro.py --test b@bjnoel.com
    python3 send_treesmith_intro.py --drip --dry-run
    python3 send_treesmith_intro.py --drip
"""

import argparse
import functools
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from stocklib.email_footer import inject_footer, inject_text_footer
from stocklib.mailer import (get_resend_api_key, get_unsubscribe_secret,
                             load_sends_log, load_subscribers,
                             make_unsubscribe_token, save_sends_log)
from stocklib.mailer import send_email as _send_email

send_email = functools.partial(_send_email, user_agent="treestock-treesmith-intro/1.0")

DATA_DIR = Path("/opt/dale/data")
SENDS_LOG = DATA_DIR / "treesmith_intro_sends.json"
# Benedict approves the copy by asking Dale to create this, or by touching it
# himself. Absent, --drip is a no-op. The cron can therefore be installed now.
ENABLED_FLAG = DATA_DIR / "treesmith-intro-enabled"

DRIP_DELAY_DAYS = 7
# Nobody who subscribed before the drip shipped is in scope. See module docstring.
DRIP_START_DATE = "2026-07-30"
MAX_PER_RUN = 10

SITE_URL = "https://treestock.com.au"
SUBJECT = "From the treestock team: a companion app for your collection"

UTM = "utm_source=treestock&utm_medium=email&utm_campaign=treesmith_intro"
# Direct store links: the reader is warm and the action we want is an install,
# so do not route them via a marketing page first. The landing-page link below
# carries a distinct utm_content instead, which is what makes this surface
# attributable in Plausible (DEC-239 instrumentation rule).
IOS_URL = "https://apps.apple.com/au/app/treesmith-plant-graft-tracker/id6761506742"
ANDROID_URL = "https://play.google.com/store/apps/details?id=app.treesmith"
LANDING_URL = f"{SITE_URL}/treesmith.html?{UTM}&utm_content=intro_email"

# Pricing per CLAUDE.md: Pro is a ONE-TIME purchase, not a subscription, and
# cloud backup is a separate yearly subscription. Cloud backup is deliberately
# not mentioned here; the free tier and the one-time unlock are all this email
# needs to say, and naming it invites the exact error the docs were corrected
# for on 2026-07-27.
FREE_PLANT_LIMIT = 30

FEATURES = [
    "A catalogue for the whole collection: variety, source, when and where you got it",
    "Graft tracking, including where the scion came from",
    "A photo timeline for each plant",
    "Activity logs for watering, pruning, feeding, harvest and pest treatment",
    "A GPS map of your garden",
]


def build_text() -> str:
    features = "\n".join(f"- {f}" for f in FEATURES)
    return f"""Hi,

I built treestock.com.au to track what is available at Australian nurseries.
You are subscribed, so you already know the problem it solves.

The next part is what happens after you buy something rare. It disappears into
a spreadsheet or a notes app, and you lose track of what you grafted it onto,
when it fruited, or where the scion came from.

I built Treesmith to fix that. It is a mobile app for plant collectors:

{features}

Free for up to {FREE_PLANT_LIMIT} plants. Pro is a one-time purchase, not a
subscription, and unlocks unlimited plants, multiple locations, reminders and
bulk edits.

Download it:
  iOS: {IOS_URL}
  Android: {ANDROID_URL}

Or read more first: {LANDING_URL}

If you try it, I would genuinely like to hear what is missing. Just reply to
this email.

Benedict
Perth, WA
"""


def build_html() -> str:
    features = "".join(
        f'<li style="margin:0 0 6px;">{f}</li>' for f in FEATURES
    )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Treesmith, a companion app for your collection</title>
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:560px;margin:0 auto;padding:24px 16px;">
  <div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

    <div style="background:#065f46;padding:24px;text-align:center;">
      <h1 style="margin:0;color:white;font-size:1.4rem;font-weight:700;">treestock.com.au</h1>
      <p style="margin:6px 0 0;color:#a7f3d0;font-size:0.9rem;">Australian Nursery Stock Tracker</p>
    </div>

    <div style="padding:24px;color:#374151;font-size:0.95rem;line-height:1.55;">

      <p style="margin:0 0 16px;">Hi,</p>

      <p style="margin:0 0 16px;">
        I built treestock.com.au to track what is available at Australian nurseries.
        You are subscribed, so you already know the problem it solves.
      </p>

      <p style="margin:0 0 16px;">
        The next part is what happens after you buy something rare. It disappears into a
        spreadsheet or a notes app, and you lose track of what you grafted it onto, when it
        fruited, or where the scion came from.
      </p>

      <p style="margin:0 0 12px;">
        I built <strong>Treesmith</strong> to fix that. It is a mobile app for plant collectors:
      </p>

      <ul style="margin:0 0 20px;padding-left:20px;">{features}</ul>

      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:14px 16px;margin-bottom:24px;">
        <p style="margin:0;font-size:0.9rem;color:#166534;">
          Free for up to {FREE_PLANT_LIMIT} plants. Pro is a one-time purchase, not a subscription,
          and unlocks unlimited plants, multiple locations, reminders and bulk edits.
        </p>
      </div>

      <div style="text-align:center;margin:0 0 24px;">
        <a href="{IOS_URL}" style="display:inline-block;background:#065f46;color:white;text-decoration:none;padding:10px 24px;border-radius:8px;font-weight:600;font-size:0.95rem;margin:0 4px 8px;">Download for iPhone</a>
        <a href="{ANDROID_URL}" style="display:inline-block;background:#065f46;color:white;text-decoration:none;padding:10px 24px;border-radius:8px;font-weight:600;font-size:0.95rem;margin:0 4px 8px;">Download for Android</a>
        <p style="margin:8px 0 0;font-size:0.85rem;">
          <a href="{LANDING_URL}" style="color:#065f46;">Or read more first</a>
        </p>
      </div>

      <p style="margin:0;color:#6b7280;font-size:0.875rem;">
        If you try it, I would genuinely like to hear what is missing. Just reply to this email.
      </p>

      <p style="margin:16px 0 0;color:#6b7280;font-size:0.875rem;">
        Benedict<br>Perth, WA
      </p>

    </div>
  </div>
</div>
</body>
</html>"""


def _parse_subscribed_at(value: str):
    """subscribers.json stores naive local ISO timestamps from the subscribe
    server. Return an aware UTC datetime, or None if unparseable."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def eligible_subscribers(subscribers: list, sends_log: dict, now: datetime,
                         delay_days: int = DRIP_DELAY_DAYS,
                         start_date: str = DRIP_START_DATE) -> list:
    """Subscribers due the intro email: signed up at least `delay_days` ago, on
    or after `start_date`, and never sent it before. Oldest first, so a backlog
    drains in subscribe order."""
    start = _parse_subscribed_at(start_date)
    cutoff = now - timedelta(days=delay_days)
    already = {e.lower() for e in sends_log}
    due = []
    for sub in subscribers:
        email = (sub.get("email") or "").strip().lower()
        if not email or email in already:
            continue
        subscribed_at = _parse_subscribed_at(sub.get("subscribed_at", ""))
        if subscribed_at is None:
            continue
        if subscribed_at < start:
            continue
        if subscribed_at > cutoff:
            continue
        due.append((subscribed_at, sub))
    due.sort(key=lambda pair: pair[0])
    return [sub for _, sub in due]


def send_to(sub: dict, api_key: str, secret: str) -> bool:
    email = sub["email"].strip().lower()
    state = sub.get("state", "ALL")
    token = make_unsubscribe_token(email, secret)
    html = inject_footer(build_html(), email, token, state, SITE_URL)
    text = inject_text_footer(build_text(), email, token, state, SITE_URL)
    return send_email(api_key, email, SUBJECT, html, text)


def run_drip(dry_run: bool = False, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    subscribers = load_subscribers()
    sends_log = load_sends_log(SENDS_LOG)
    due = eligible_subscribers(subscribers, sends_log, now)

    if not due:
        print("No subscribers due the Treesmith intro email.")
        return 0

    capped = due[:MAX_PER_RUN]
    if len(due) > len(capped):
        print(f"{len(due)} due, sending {len(capped)} this run (MAX_PER_RUN).")

    if dry_run:
        for sub in capped:
            print(f"[DRY RUN] would send to {sub['email']} "
                  f"(subscribed {sub.get('subscribed_at', '?')})")
        return 0

    if not ENABLED_FLAG.exists():
        print(f"Drip not enabled: {ENABLED_FLAG} does not exist. "
              f"{len(capped)} subscriber(s) waiting. Sending nothing.")
        return 0

    api_key = get_resend_api_key()
    secret = get_unsubscribe_secret()
    sent = 0
    for sub in capped:
        if send_to(sub, api_key, secret):
            sends_log[sub["email"].strip().lower()] = now.isoformat()
            save_sends_log(SENDS_LOG, sends_log)
            sent += 1
    print(f"Sent {sent} of {len(capped)} Treesmith intro email(s).")
    return 0 if sent == len(capped) else 1


def run_test(email: str, dry_run: bool = False) -> int:
    """Proof of concept: send exactly what a subscriber would get, to one
    address, and record nothing. Safe to run repeatedly."""
    email = email.strip().lower()
    subscribers = {s.get("email", "").strip().lower(): s for s in load_subscribers()}
    state = subscribers.get(email, {}).get("state", "ALL")
    if dry_run:
        print(f"[DRY RUN] would send test to {email}")
        print(f"  Subject: {SUBJECT}")
        print(build_text())
        return 0
    api_key = get_resend_api_key()
    secret = get_unsubscribe_secret()
    ok = send_to({"email": email, "state": state}, api_key, secret)
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--drip", action="store_true",
                      help="send to subscribers due the email (cron mode)")
    group.add_argument("--test", metavar="EMAIL",
                      help="send one copy here and log nothing")
    parser.add_argument("--dry-run", action="store_true", help="send nothing")
    args = parser.parse_args(argv)
    if args.test:
        return run_test(args.test, dry_run=args.dry_run)
    return run_drip(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
