#!/usr/bin/env python3
"""Alert when a subscriber silently stops receiving digests (DAL-262).

DAL-260 found two of thirteen subscribers had been receiving nothing, one for
ten days and one since the day they signed up. Both had frequency=daily, both
were among our best converters (DEC-250), and both were invisible: the sender
printed a bare count of who it mailed, never a count of who it skipped. It took
a human reading digest_sends.json to notice. The DAL-260 fix closed the specific
cause (an empty plant_categories list). This closes the class: any future bug
that drops a subscriber out of the send loop now says so.

THE THRESHOLD IS COUNTED IN SENDS, NOT IN DAYS, AND THAT IS THE WHOLE DESIGN.

The ticket proposed "no digest in 14 days". Measured against the real log, that
rule would have false-fired: three healthy subscribers have a 20-day calendar
gap (2026-03-31 to 2026-04-20), because the digest was not running at all in
that window. Nothing was wrong with those subscribers. Counting calendar days
conflates "this person was skipped" with "nobody was sent anything", which are
different faults with different owners.

So a gap is measured in OPPORTUNITIES: send-log entries on which somebody,
anybody, was mailed. On that measure the worst gap any healthy subscriber has
ever had is 2 (daily) and 1 (weekly), so the thresholds below sit just above the
observed noise floor rather than at a round number somebody liked the look of.

The whole-list case is not silently dropped, it gets its own line: if no digest
has reached anyone for LIST_SILENT_DAYS, that is reported as a pipeline outage
instead of as N broken subscribers.

Report only. No auto-repair: resubscribing somebody is customer-facing and
stays a human decision, which is why DAL-260's data fix went to Benedict.

Usage:
    python3 detect_silent_subscribers.py [--dry-run] [--force]

--dry-run prints the email it would send, without sending or marking sent.
"""

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from send_digest import get_subscriber_frequency
from stocklib.mailer import load_sends_log, load_subscribers, save_sends_log

DATA_DIR = Path("/opt/dale/data")
DAILY_SENDS = DATA_DIR / "digest_sends.json"
WEEKLY_SENDS = DATA_DIR / "weekly_digest_sends.json"
MARKER_FILE = DATA_DIR / "silent_subscriber_alerts.json"

# Consecutive missed opportunities before we call it. Observed worst case for a
# healthy subscriber is 2 daily / 1 weekly, so these fire one clear of noise.
MISSED_THRESHOLD = {"daily": 3, "weekly": 2}

# Opportunities that must have passed since signup before a subscriber who has
# NEVER received anything counts as broken rather than as merely new. A weekly
# subscriber who joins on Monday legitimately waits six days for their first.
NEVER_THRESHOLD = {"daily": 3, "weekly": 2}

# Calendar days of total list silence before that is reported as an outage.
# Since April the longest real stretch is 4 days (2026-07-01 to 07-04).
LIST_SILENT_DAYS = 7


def opportunity_keys(sends_log: dict) -> list:
    """Send-log keys on which at least one person was actually mailed, in order.

    A key with an empty list is a run that mailed nobody. It is not an
    opportunity a subscriber can be said to have missed.
    """
    return sorted(k for k, v in sends_log.items() if v)


def key_to_date(key: str) -> date:
    """Daily keys are '2026-08-27'. Weekly keys are 'week-2026-08-23'."""
    return date.fromisoformat(key[5:] if key.startswith("week-") else key)


def signup_date(subscriber: dict) -> date | None:
    raw = subscriber.get("subscribed_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def check_subscriber(subscriber: dict, sends_log: dict, keys: list) -> dict | None:
    """Return a finding for this subscriber, or None if they look healthy."""
    email = subscriber["email"]
    freq = get_subscriber_frequency(subscriber)
    if freq == "off":
        return None

    received = [i for i, k in enumerate(keys) if email in sends_log[k]]

    if received:
        missed = len(keys) - 1 - received[-1]
        if missed >= MISSED_THRESHOLD[freq]:
            return {
                "email": email,
                "frequency": freq,
                "type": "stopped",
                "missed": missed,
                "detail": (
                    f"missed the last {missed} {freq} digests; last received "
                    f"{keys[received[-1]]}"
                ),
            }
        return None

    # Never received one. Only meaningful once enough sends have gone out since
    # they signed up, otherwise every new subscriber is an alert for a day.
    joined = signup_date(subscriber)
    since = [k for k in keys if joined is None or key_to_date(k) >= joined]
    if len(since) >= NEVER_THRESHOLD[freq]:
        return {
            "email": email,
            "frequency": freq,
            "type": "never",
            "missed": len(since),
            "detail": (
                f"has never received a {freq} digest, through {len(since)} sends "
                f"since signing up on {joined}"
            ),
        }
    return None


def list_silence(keys: list, today: date) -> int | None:
    """Days since anybody at all was mailed, if that exceeds LIST_SILENT_DAYS."""
    if not keys:
        return None
    days = (today - key_to_date(keys[-1])).days
    return days if days >= LIST_SILENT_DAYS else None


def detect(subscribers, daily_log, weekly_log, today):
    """Returns (findings, outages). Findings are per subscriber, outages global."""
    logs = {"daily": (daily_log, opportunity_keys(daily_log)),
            "weekly": (weekly_log, opportunity_keys(weekly_log))}

    outages = []
    for freq, (log, keys) in logs.items():
        silent = list_silence(keys, today)
        if silent is not None:
            outages.append({
                "frequency": freq,
                "days": silent,
                "detail": (f"no {freq} digest has reached anyone for {silent} days "
                           f"(last send {keys[-1]}). This is the sender, not a subscriber."),
            })

    # A subscriber cannot be judged against a channel that is not running, and
    # saying so once beats saying it once per subscriber.
    stalled = {o["frequency"] for o in outages}

    findings = []
    for s in subscribers:
        freq = get_subscriber_frequency(s)
        if freq == "off" or freq in stalled:
            continue
        log, keys = logs[freq]
        found = check_subscriber(s, log, keys)
        if found:
            findings.append(found)
    return findings, outages


def build_email(findings, outages, today, total):
    rows_html = ""
    rows_text = []
    for o in outages:
        rows_html += (
            f'<tr style="border-bottom:1px solid #eee">'
            f'<td style="padding:6px 10px">(whole list)</td>'
            f'<td style="padding:6px 10px;color:#c62828;font-weight:bold">sender stalled</td>'
            f'<td style="padding:6px 10px">{o["detail"]}</td></tr>'
        )
        rows_text.append(f"  (whole list): sender stalled - {o['detail']}")
    for f in findings:
        label = "never received one" if f["type"] == "never" else "stopped receiving"
        rows_html += (
            f'<tr style="border-bottom:1px solid #eee">'
            f'<td style="padding:6px 10px">{f["email"]}</td>'
            f'<td style="padding:6px 10px;color:#c62828;font-weight:bold">{label}</td>'
            f'<td style="padding:6px 10px">{f["detail"]}</td></tr>'
        )
        rows_text.append(f"  {f['email']}: {label} - {f['detail']}")

    count = len(findings) + len(outages)
    html = f"""<h2>Subscriber delivery alert &mdash; {today}</h2>
<p>{count} of {total} subscribers are not receiving what they signed up for.</p>
<table style="font-family:monospace;font-size:13px;border-collapse:collapse;width:100%">
<tr style="border-bottom:2px solid #ddd;font-weight:bold">
<td style="padding:6px 10px">Subscriber</td>
<td style="padding:6px 10px">Condition</td>
<td style="padding:6px 10px">Detail</td></tr>
{rows_html}
</table>
<p style="font-size:0.85em;color:#888;margin-top:16px">
Gaps are counted in sends that reached somebody else, not in calendar days, so a
night the digest did not run is not held against anyone. Thresholds:
{MISSED_THRESHOLD['daily']} consecutive daily or {MISSED_THRESHOLD['weekly']} weekly.
A digest is also legitimately skipped when nothing matches a subscriber's state and
category filters, so check before changing anything. Nothing has been repaired
automatically: resubscribing somebody is your call. Subscribers: treestock.com.au/admin.</p>"""

    text = f"Subscriber delivery alert -- {today}\n\n" + "\n".join(rows_text)
    subject = f"Subscriber delivery: {count} not receiving digests -- {today}"
    return subject, html, text


def send_alert(subject, html, text):
    sys.path.insert(0, str(Path(__file__).parent.parent / "autonomous"))
    from notify import send_email
    send_email(subject, html, text)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    dry_run = "--dry-run" in argv
    force = "--force" in argv

    today = date.today()
    subscribers = load_subscribers()
    daily_log = load_sends_log(DAILY_SENDS)
    weekly_log = load_sends_log(WEEKLY_SENDS)

    findings, outages = detect(subscribers, daily_log, weekly_log, today)
    active = [s for s in subscribers if get_subscriber_frequency(s) != "off"]

    if not findings and not outages:
        print(f"Subscriber delivery: {len(active)} active subscribers, all receiving.")
        return 0

    for o in outages:
        print(f"  (whole list): {o['detail']}")
    for f in findings:
        print(f"  {f['email']}: {f['type']} - {f['detail']}")

    subject, html, text = build_email(findings, outages, today.isoformat(), len(active))

    if dry_run:
        print(f"\n[DRY RUN] Would send:\nSubject: {subject}\n\n{text}")
        return 0

    marker = load_sends_log(MARKER_FILE)
    if marker.get("last_sent") == today.isoformat() and not force:
        print(f"Subscriber delivery alert already sent today ({today.isoformat()}), skipping.")
        return 0

    send_alert(subject, html, text)
    marker["last_sent"] = today.isoformat()
    save_sends_log(MARKER_FILE, marker)
    print(f"Subscriber delivery alert sent: {len(findings) + len(outages)} conditions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
