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
from daily_digest import load_all_changes, format_html, has_any_changes, ALL_CATEGORIES, PLANT_CATEGORIES
from stocklib.email_footer import inject_footer

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
NURSERY_STOCK_DIR = DATA_DIR / "nursery-stock"
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
SENDS_LOG_FILE = DATA_DIR / "digest_sends.json"
RESEND_ENV = SECRETS_DIR / "resend.env"
APP_ENV = SECRETS_DIR / "app.env"

FROM_EMAIL = "alerts@mail.treestock.com.au"
FROM_NAME = "treestock.com.au"


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


def get_subscriber_categories(subscriber: dict) -> frozenset:
    """Categories the subscriber wants in their digest.

    Default (missing field) is all three — preserves behaviour for legacy records.
    Unknown values are dropped silently.
    """
    raw = subscriber.get("categories")
    if raw is None:
        return frozenset(ALL_CATEGORIES)
    return frozenset(c for c in raw if c in ALL_CATEGORIES)


def get_subscriber_plant_categories(subscriber: dict) -> frozenset:
    """Plant categories the subscriber opted into (DAL-199). Default (missing
    field) is fruit only, so legacy subscribers and anyone who has not ticked
    bush tucker keep getting the fruit digest only. Unknown values dropped."""
    raw = subscriber.get("plant_categories")
    if raw is None:
        return frozenset({"fruit"})
    return frozenset(c for c in raw if c in PLANT_CATEGORIES)


def get_subscriber_frequency(subscriber: dict) -> str:
    """'daily' | 'weekly' | 'off'. Default 'daily' preserves legacy behaviour."""
    freq = subscriber.get("frequency", "daily")
    if freq not in ("daily", "weekly", "off"):
        return "daily"
    return freq


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
        # Look up actual preferences if subscriber exists, else default
        existing = next((s for s in all_subscribers if s["email"] == test_email.lower()), None)
        if existing:
            subscribers = [existing]
        else:
            subscribers = [{"email": test_email, "state": "ALL"}]
        ts = get_subscriber_state(subscribers[0])
        tc = sorted(get_subscriber_categories(subscribers[0]))
        tp = sorted(get_subscriber_plant_categories(subscribers[0]))
        tf = get_subscriber_frequency(subscribers[0])
        print(f"TEST MODE: Sending only to {test_email} (state={ts}, frequency={tf}, categories={','.join(tc)}, plant={','.join(tp)})")
    else:
        # Daily run: only address subscribers whose frequency is "daily"
        subscribers = [s for s in all_subscribers if get_subscriber_frequency(s) == "daily"]

    if not subscribers:
        print("No subscribers to send to.")
        return

    # Load send log (skip already-sent today; test mode bypasses idempotency)
    sends_log = load_sends_log()
    already_sent = set() if test_email else set(sends_log.get(target_date, []))

    to_send = [s for s in subscribers if s["email"] not in already_sent]
    skipped = len(subscribers) - len(to_send)

    print(f"Subscribers: {len(subscribers)} daily, {len(to_send)} to send, {skipped} already sent today")

    if not to_send:
        print("All subscribers already received today's digest.")
        return

    # Group subscribers by (state, change-categories, plant-categories) — same
    # combo can reuse rendered HTML. Empty sets fall through to the "skip" branch.
    by_bucket: dict[tuple, list] = {}
    for s in to_send:
        state = get_subscriber_state(s)
        cats = get_subscriber_categories(s)
        pcats = get_subscriber_plant_categories(s)
        by_bucket.setdefault((state, cats, pcats), []).append(s)

    bucket_summary = ", ".join(
        f"{st}/{','.join(sorted(cs)) or '(none)'}/{','.join(sorted(pc)) or '(none)'}({len(subs)})"
        for (st, cs, pc), subs in sorted(by_bucket.items(),
                                         key=lambda kv: (kv[0][0], sorted(kv[0][1]), sorted(kv[0][2])))
    )
    print(f"Buckets: {bucket_summary}")

    if dry_run:
        for s in to_send:
            state = get_subscriber_state(s)
            cats = ",".join(sorted(get_subscriber_categories(s))) or "(none)"
            pcats = ",".join(sorted(get_subscriber_plant_categories(s))) or "(none)"
            print(f"  Would send to: {s['email']} (state={state}, categories={cats}, plant={pcats})")
        return

    api_key = get_resend_api_key()
    secret = get_unsubscribe_secret()
    subject = f"Nursery Stock Update — {target_date}"

    # Cache generated HTML per (state, categories) bucket
    html_cache: dict[tuple, str] = {}

    sent_emails = list(already_sent)
    failed = 0
    empty_skipped = 0

    for (state, cats, pcats), bucket_subscribers in sorted(
        by_bucket.items(), key=lambda kv: (kv[0][0], sorted(kv[0][1]), sorted(kv[0][2]))
    ):
        filter_state = "" if state == "ALL" else state

        # Subscribers who muted every change-type or every plant category — skip
        # outright (variety alerts still reach them via send_variety_alerts.py).
        if not cats or not pcats:
            empty_skipped += len(bucket_subscribers)
            print(f"  Skipping {len(bucket_subscribers)} subscribers with no categories enabled")
            continue

        # Skip the whole bucket if there's nothing to show after filtering — no
        # point emailing "No changes today" to people who explicitly narrowed scope.
        if not has_any_changes(all_changes, state=filter_state, categories=cats, plant_categories=pcats):
            empty_skipped += len(bucket_subscribers)
            print(f"  Skipping {len(bucket_subscribers)} subscribers — no matching changes for {state}/{','.join(sorted(cats))}/{','.join(sorted(pcats))}")
            continue

        cache_key = (state, cats, pcats)
        if cache_key not in html_cache:
            html_cache[cache_key] = format_html(
                all_changes, target_date, state=filter_state, categories=cats,
                plant_categories=pcats,
            )
        digest_html = html_cache[cache_key]

        for subscriber in bucket_subscribers:
            email = subscriber["email"]
            token = make_unsubscribe_token(email, secret)
            personalised_html = inject_footer(digest_html, email, token, state)

            success = send_email(api_key, email, subject, personalised_html)
            if success:
                sent_emails.append(email)
            else:
                failed += 1

    # Save updated log — skip in test mode to avoid corrupting production sends log
    if not test_email:
        sends_log[target_date] = sent_emails
        save_sends_log(sends_log)

    sent_count = len(sent_emails) - len(already_sent)
    print(f"Done: {sent_count} sent, {empty_skipped} skipped (empty/muted), {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
