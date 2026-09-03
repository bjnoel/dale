#!/usr/bin/env python3
"""Weekly TreeSmith analytics digest, emailed via Resend.

Queries PostHog (EU region, project 166160) with HogQL, formats a
start-of-week digest, and emails it to the owner using the shared notify.py
helper. Degrades gracefully: any single query that errors is reported inline
rather than failing the whole digest, and events that don't exist yet simply
show as zero.

Usage:
    python3 treesmith_analytics.py            # query + email
    python3 treesmith_analytics.py --dry-run  # print to stdout, no email
    python3 treesmith_analytics.py --help     # this text, no email

Note: any UNRECOGNISED argument is rejected rather than ignored. Running this
with a stray flag used to fall through to the email path and send Benedict an
unscheduled digest, which is exactly what happened during DEC-252.

Schedule (VPS crontab, Monday 00:00 UTC = Monday 08:00 AWST):
    0 0 * * 1 /opt/dale/autonomous/treesmith_analytics.py \
        >> /opt/dale/autonomous/logs/treesmith_analytics.log 2>&1

Setup: create /opt/dale/secrets/posthog.env with
    POSTHOG_API_KEY=phx_...
    POSTHOG_HOST=https://eu.posthog.com   (optional; defaults to EU)
Locally it falls back to ~/.posthog/credentials.json (the PostHog CLI's file).

Revenue note: PostHog purchase/paywall events are CLIENT-SIDE and include
sandbox/TestFlight activity. RevenueCat is the source of truth for real
revenue (the app ships purchases_flutter), with App Store Connect behind it.
Money here is read from `purchase_succeeded`, the only event carrying price,
currency and environment together, and is counted as revenue ONLY when
environment is explicitly 'production'. Untagged events (before 2026-07-01,
when tagging began) are shown separately and never counted. Every figure is
reported all-time as well as weekly, so a sale cannot age out of the digest.
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request

PROJECT_ID = 166160
DEFAULT_HOST = "https://eu.posthog.com"
SECRETS_DIR = "/opt/dale/secrets"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Every app event name this digest reads, in one place.
#
# The names used to be string literals scattered across the metric queries.
# When the app renamed its onboarding events (commit f0117ee replaced the old
# OnboardingFlow with a welcome screen), the digest kept querying the dead
# names and reported "Onboarding completion 0/0 = n/a" plus a red "Biggest
# drop: opened -> onboarded: lost 22 (100%)" for eleven days. Both were false;
# the week actually ran 15 shown / 15 completed = 100%.
#
# A query against an event nobody sends returns 0, and 0 is a legal answer, so
# nothing could have caught this by inspecting the numbers. m_event_liveness
# watches this exact dict instead: any name with real history and no recent
# events is reported as SILENT rather than floored to zero.
EVENTS = {
    "opened": "Application Opened",
    "welcome_shown": "welcome_screen_shown",
    "welcome_completed": "welcome_screen_completed",
    "plant_added": "plant_added",
    "activity_logged": "activity_logged",
    "paywall_shown": "paywall_shown",
    "paywall_result": "paywall_result",
    "purchase_succeeded": "purchase_succeeded",
    # Reminders. `reminder_created` is the only legitimate denominator for
    # anything reminder-shaped; see REMINDER_DELIVERY_NOTE.
    "reminder_created": "reminder_created",
    "reminder_notification_tapped": "reminder_notification_tapped",
    "reminder_sweep": "reminder_sweep",
    # Content and structure.
    "graft_added": "graft_added",
    "zone_added": "zone_added",
    "photo_deleted": "photo_deleted",
    "plants_bulk_edited": "plants_bulk_edited",
    # Data portability. `data_imported` is the first instrument that can see a
    # plant arriving by any route other than the plant form, which is the blind
    # spot m_plants has been reporting as a percentage since DAL-265.
    "data_exported": "data_exported",
    "data_imported": "data_imported",
}

# Events the app declares that have not reached PostHog yet, and the date we
# started expecting each one.
#
# This is a third liveness state and it exists because the other two both lie
# about a freshly shipped event. `silent` needs history it does not have.
# `never_seen` is technically true but renders as "Typo in EVENTS, or an event
# that never shipped", in red, which is a false alarm every week until the
# build reaches users. Ten of those at once is how the liveness section stops
# being read, and that section is the one this digest cannot afford to lose.
#
# Suppressing them instead is the DEC-249 error pointing the other way: an
# absence of measurement would render identically to a clean result. So the
# wait is bounded. Within AWAITING_GRACE_DAYS the digest says "awaiting, N days
# in" in grey; past it the event escalates to a real red alarm, because an
# event declared six weeks ago that has still never fired is not a slow
# rollout, it is a capture that was never wired up or a name that does not
# match what the app sends.
#
# When an event starts arriving it needs no edit here: m_event_liveness keys on
# what the data actually holds, so a live event drops out of this state by
# itself. Delete the row when you next touch this file.
#
# 2026-08-31 is the day the events were declared. On that date the live builds
# were 1.0.11 (62/63/64) and none of these had ever fired.
AWAITING_FIRST_EVENT = {
    "reminder_created": "2026-08-31",
    "reminder_notification_tapped": "2026-08-31",
    "reminder_sweep": "2026-08-31",
    "graft_added": "2026-08-31",
    "zone_added": "2026-08-31",
    "photo_deleted": "2026-08-31",
    "plants_bulk_edited": "2026-08-31",
    "data_exported": "2026-08-31",
    "data_imported": "2026-08-31",
    # Declared in the app since June and never once fired: the app defined
    # captureActivityLogged and no code path called it, which m_funnel has been
    # rendering as "not instrumented" rather than blaming on users. It is
    # reported live as of 2026-08-31, so it is on the same clock as the rest.
    "activity_logged": "2026-08-31",
}

# How long an event may stay unseen after being declared before its absence is
# an alarm rather than a rollout.
#
# Sized from observed update behaviour, not from taste: on 2026-08-31 the data
# still carried 1.0.9 events from 2026-08-28, two builds and roughly six weeks
# after 1.0.10 shipped. A grace shorter than the tail of an update cycle would
# fire on every release. 42 days clears that tail and still catches a capture
# that was never wired up inside the same quarter.
AWAITING_GRACE_DAYS = 42

# Retired event names, mapped to what replaced them.
#
# NOT in EVENTS: these are supposed to be dead, so liveness must never report
# them as SILENT. They are kept because any funnel whose window reaches back
# into July has to union both names to be correct. In the real data
# `onboarding_started` ran 2026-06-08 to 2026-07-30 (148 events) while
# `welcome_screen_shown` began 2026-07-02 (101 events), so the two overlap for
# four weeks: a window covering July sees part of the population under each
# name, and reading either one alone undercounts.
#
# The union is over DISTINCT people, never a sum of counts. During the overlap
# one person who updated mid-window sends both names and would otherwise be
# counted twice.
RETIRED_ALIASES = {
    "welcome_screen_shown": ["onboarding_started"],
    "welcome_screen_completed": ["onboarding_completed"],
}

# The last day a retired onboarding name appears in the data. A window that
# starts after this needs no union, and saying so keeps the union from being
# quietly widened into a permanent double-count.
ALIAS_CUTOFF_DATE = "2026-07-30"

# Properties now attached to EVERY event, including events from users who have
# never signed in.
#
# They are EVENT properties, not person properties. Segment with
# `properties.is_pro`; `person.properties.is_pro` is a different store that
# these never reach, and it fails by returning NULL for everyone rather than by
# erroring, so a segment built on it reads as "nobody is Pro" instead of as a
# broken query. test_treesmith_super_properties.py fails the build on the
# person-scoped form for exactly that reason.
SUPER_PROPERTIES = (
    "pro_source",
    "cloud_backup_source",
    "is_sandbox",
    "plant_count_bucket",
    "location_count_bucket",
    "activity_count_bucket",
    "days_since_install_bucket",
)

# `pro_source` and `cloud_backup_source` replace the booleans `is_pro` and
# `has_cloud_backup`, which were never sent even once, so there is no mixed
# dataset to reconcile and no reason to read both spellings.
#
# The booleans could not answer the question their name asked. They were set
# from the RevenueCat snapshot alone, while the app's feature gates read
# RevenueCat OR a server-side comp grant (the gardening-club allowlist). A
# comped member therefore passed every Pro gate, created reminders and bulk
# edits, and sent every event stamped `is_pro: false`. The gate and the label
# disagreed, and the label is what every segment here is built on.
#
# Three values, ordered by precedence to match isProProvider:
#   paid   a RevenueCat entitlement. The revenue answer.
#   comp   no purchase, but a live comp grant. Full Pro experience, no money.
#   none   neither. The only value that means "sees the paywall".
#
# `paid` wins over `comp` because somebody who paid and was later comped is
# still a customer. The old boolean is recoverable as (pro_source == 'paid'),
# so nothing is lost by dropping it.
PRO_SOURCES = ("paid", "comp", "none")

# The property coverage and skew are reported against when several are equally
# covered. It is a tie-break and a label, NOT a fixed probe: coverage is read
# from whichever property is best covered.
#
# Reading a fixed one is what the first version did, and real data broke it
# within three days. Build 65 shipped on 2026-08-31 sending the old `is_pro`
# spelling; this file had already moved to `pro_source`, so the fixed probe
# read 0% while `is_sandbox` and the buckets sat at 7%, and the digest printed
# "0% coverage" directly above four populated splits. A section that
# contradicts itself in the same breath is worse than one that is merely
# wrong.
COVERAGE_PROBE = "pro_source"

# Events the app only lets a Pro user reach. Verified against the Flutter
# source 2026-09-03: `reminder_section.dart` renders "Pro feature" instead of
# the toggle, and `plant_list_screen._startSelection` shows the paywall.
#
# `reminder_sweep` is deliberately NOT here. It runs from `_reconcileReminders`
# on the cold-boot path in main.dart, ahead of any entitlement check, so a free
# user with no reminders still emits one with its counters at zero.
PRO_GATED_EVENTS = (
    "reminder_created",
    "reminder_notification_tapped",
    "plants_bulk_edited",
)

# No event in the historical data carries any of these: on 2026-08-31 the check
# returned 0 across all 15,401 events ever recorded. So a super property is
# absent for two entirely different reasons, and they must not be added
# together: the user is not Pro, or the event predates the build that attaches
# the property at all. Every segment below therefore reports coverage first and
# takes its denominator from events that carry the property, never from all
# events. An absent property is "unknown", never "false" (DEC-317).

# How many events a name must have carried historically before its silence is
# worth reporting. Low-volume events have quiet weeks all the time; a rename
# shows up as hundreds of events stopping dead.
MIN_HISTORY = 20


# ── Credentials ────────────────────────────────────────────────────────────

def load_posthog_credentials():
    """Return (host, api_key).

    Prefers the VPS secret file; falls back to the PostHog CLI credentials in
    the home directory so the script runs locally with --dry-run.
    """
    env_path = os.path.join(SECRETS_DIR, "posthog.env")
    if os.path.exists(env_path):
        host = DEFAULT_HOST
        key = None
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("POSTHOG_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                elif line.startswith("POSTHOG_HOST="):
                    host = line.split("=", 1)[1].strip()
        if not key:
            raise ValueError("POSTHOG_API_KEY not found in posthog.env")
        return host, key

    # Local fallback: PostHog CLI credentials file.
    home = os.path.expanduser("~/.posthog/credentials.json")
    if os.path.exists(home):
        with open(home) as f:
            c = json.load(f)
        return c.get("host", DEFAULT_HOST), c["token"]

    raise FileNotFoundError(
        "No PostHog credentials: expected /opt/dale/secrets/posthog.env or "
        "~/.posthog/credentials.json"
    )


# ── HogQL ──────────────────────────────────────────────────────────────────

def hogql(host, key, query):
    """Run a HogQL query; return list-of-rows. Raises on HTTP error."""
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": query}})
    req = urllib.request.Request(
        f"{host}/api/projects/{PROJECT_ID}/query/",
        data=body.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "treesmith-analytics/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp).get("results", [])


def scalar(rows, default=0):
    if rows and rows[0]:
        return rows[0][0]
    return default


def pct_delta(now, prev):
    if not prev:
        return None
    return round((now - prev) / prev * 100)


# ── Metrics ─────────────────────────────────────────────────────────────────
# Each metric function returns a small dict; failures are caught by run_metric
# so one broken query never sinks the digest.

def run_metric(fn, *args):
    try:
        return {"ok": True, "data": fn(*args)}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read()[:200].decode()
        except Exception:
            pass
        return {"ok": False, "error": f"HTTP {e.code} {detail}"}
    except Exception as e:  # noqa: BLE001 - report any failure inline
        return {"ok": False, "error": str(e)[:200]}


def m_installs(host, key):
    """New devices (first-ever event) this week vs the prior week."""
    rows = hogql(host, key, """
        WITH firsts AS (
          SELECT person_id, min(timestamp) AS first_seen
          FROM events GROUP BY person_id
        )
        SELECT
          countIf(first_seen >= now() - INTERVAL 7 DAY) AS this_week,
          countIf(first_seen >= now() - INTERVAL 14 DAY
                  AND first_seen < now() - INTERVAL 7 DAY) AS prev_week,
          count() AS all_time
        FROM firsts
    """)
    this_week = rows[0][0] if rows else 0
    prev_week = rows[0][1] if rows else 0
    all_time = rows[0][2] if rows else 0
    return {"this_week": this_week, "prev_week": prev_week,
            "all_time": all_time,
            "delta": pct_delta(this_week, prev_week)}


def m_active(host, key):
    """Active devices in the last 7 / 28 days."""
    rows = hogql(host, key, """
        SELECT
          count(DISTINCT if(timestamp >= now() - INTERVAL 7 DAY,
                            person_id, NULL)) AS w,
          count(DISTINCT if(timestamp >= now() - INTERVAL 28 DAY,
                            person_id, NULL)) AS m
        FROM events WHERE timestamp >= now() - INTERVAL 28 DAY
    """)
    return {"wau": rows[0][0] if rows else 0,
            "mau": rows[0][1] if rows else 0}


def m_identity(host, key):
    """How far `distinct_id` and `person_id` have drifted apart, all time.

    PostHog issues a fresh `distinct_id` per anonymous device and then aliases
    it onto a `person_id` when the user signs in, reinstalls or restores. Every
    people-count in this digest used to be `count(DISTINCT distinct_id)`, which
    counts one human once per id they have ever carried. One person in our data
    carries 27 ids on their own.

    The effect runs in the damaging direction: installs are inflated, so every
    conversion rate built on that denominator is understated, and each phantom
    id looks like somebody who arrived once and never came back, so retention
    is understated too.

    Printed every week rather than fixed once, because the only way to notice a
    metric quietly reverting to id-counting is to keep both numbers visible.
    """
    rows = hogql(host, key, """
        SELECT count(DISTINCT distinct_id), count(DISTINCT person_id)
        FROM events
    """)
    ids = rows[0][0] if rows else 0
    persons = rows[0][1] if rows else 0
    return {"ids": ids, "persons": persons, "phantom": ids - persons,
            "inflation_pct": (round((ids - persons) / persons * 100)
                              if persons else None)}


def m_event_liveness(host, key):
    """Which of the events this digest depends on have stopped arriving.

    Every other metric here answers "what did users do". This one answers "can
    we still see what users do", which is upstream of all of them: a metric
    reading an event the app no longer sends reports 0, and 0 is indistinguishable
    from a real zero. That is not hypothetical. `onboarding_completed` was
    renamed to `welcome_screen_completed` on 2026-07-02, the last stragglers on
    the old build stopped sending it on 2026-07-30, and for the eleven days after
    that the digest reported a 100%-converting funnel step as a total collapse.

    Three states, deliberately reported apart because they need different
    fixes:

      silent      the name has real history and nothing recent. Renamed, or the
                  code path that fired it was removed.
      awaiting    the name is in AWAITING_FIRST_EVENT, has never appeared, and
                  was declared less than AWAITING_GRACE_DAYS ago. A build on its
                  way to users, not a defect. Reported in grey with the age, so
                  it is visible without being an alarm.
      never_seen  the name has never appeared and is either undeclared or past
                  its grace. A typo in EVENTS, a capture that was never wired
                  up, or an event we planned and never shipped.

    The middle state is the one that keeps this section readable. Ten events
    were declared at once on 2026-08-31 while the live builds were 1.0.11 and
    none of them had ever fired; without `awaiting` every one of them would
    have rendered as a red defect every Monday until the next release reached
    users, and a section that cries wolf ten times is a section nobody reads.

    Anything below MIN_HISTORY is left alone; a low-volume event having a quiet
    week is ordinary and warning about it would train the reader to skip this
    section, which is the one failure this section cannot afford.
    """
    names = sorted(set(EVENTS.values()))
    in_list = ", ".join("'%s'" % n for n in names)
    rows = hogql(host, key, f"""
        SELECT event,
               toString(max(toDate(timestamp))) AS last_seen,
               count() AS all_time,
               countIf(timestamp >= now() - INTERVAL 7 DAY) AS recent
        FROM events
        WHERE event IN ({in_list})
        GROUP BY event
    """)

    silent = []
    seen = set()
    for event, last_seen, all_time, recent in rows:
        seen.add(event)
        if recent == 0 and all_time >= MIN_HISTORY:
            silent.append({
                "event": event,
                "last_seen": last_seen,
                "days_ago": _days_since(last_seen),
                "all_time": all_time,
            })
    silent.sort(key=lambda s: s["all_time"], reverse=True)

    # An event that HAS arrived is live regardless of what AWAITING_FIRST_EVENT
    # still says, so `seen` is checked before the declaration is. That way a
    # stale row in the dict cannot suppress a real silence later: once an event
    # has history it is scored by the silent rule above like any other.
    awaiting, never_seen = [], []
    for name in names:
        if name in seen:
            continue
        declared = AWAITING_FIRST_EVENT.get(name)
        waited = _days_since(declared) if declared else None
        if declared and waited is not None and waited <= AWAITING_GRACE_DAYS:
            awaiting.append({"event": name, "declared": declared,
                             "days_waiting": waited,
                             "grace_days": AWAITING_GRACE_DAYS})
        else:
            # Past grace, or never declared at all. Both are defects, but they
            # read differently, so the overdue ones carry their age.
            never_seen.append({"event": name, "declared": declared,
                               "days_waiting": waited})
    awaiting.sort(key=lambda a: a["event"])
    never_seen.sort(key=lambda n: n["event"])
    return {"silent": silent, "awaiting": awaiting, "never_seen": never_seen}


def _days_since(date_str):
    """Whole days from an ISO date to today, or None if it will not parse.

    Returns None rather than raising: a malformed date must not cost the
    reader the rest of the warning, which is still actionable without it.
    """
    try:
        seen = datetime.date.fromisoformat(str(date_str)[:10])
    except (ValueError, TypeError):
        return None
    return (datetime.date.today() - seen).days


def m_plants(host, key):
    """How many plants exist, and how many of them we ever saw being added.

    `plant_added` fires from exactly one place in the app,
    `plant_form_screen.dart`, so a plant created by restoring a backup or
    importing a file is never announced. Counting the event therefore counts
    plants typed in by hand, not plants owned.

    The truth was already in the payload and had never been read: `plant_added`
    carries `plant_count_after`, and the retired `plant_count_snapshot` carried
    `plant_count`. The high-water mark of those per person is a floor on how
    many plants that person holds.

    The gap between the two is reported deliberately. It is the size of the
    blind spot, and it is what Benedict noticed from the other side by having
    more plants in his own app than the digest said existed in total.

    `data_imported` (2026-08-31) narrows that gap without closing it. It
    carries `plants_imported`, so plants arriving by file import are now
    counted rather than merely inferred. Restore-from-backup still announces
    nothing, so the residual is the honest remainder: plants we hold no
    explanation for, rather than the whole non-form population.

    `plant_count_snapshot` is legacy and only old builds send it (245 events,
    2 of them in the week to 2026-08-31). It is read here only as one input to
    a max(), which is safe because a max cannot be dragged down by a shrinking
    sender. It must never become a denominator or a trend: that series is
    decaying as users update, and a decaying instrument reads as a decaying
    business.
    """
    rows = hogql(host, key, """
        WITH per_person AS (
          SELECT person_id,
                 max(greatest(
                   toIntOrZero(replaceAll(
                     JSONExtractRaw(properties, 'plant_count_after'), '"', '')),
                   toIntOrZero(replaceAll(
                     JSONExtractRaw(properties, 'plant_count'), '"', ''))
                 )) AS high_water
          FROM events
          WHERE event IN ('plant_added', 'plant_count_snapshot')
          GROUP BY person_id
        )
        SELECT count(), sum(high_water) FROM per_person WHERE high_water > 0
    """)
    owners = rows[0][0] if rows else 0
    plants = rows[0][1] if rows else 0
    observed = scalar(hogql(host, key, """
        SELECT count() FROM events WHERE event = 'plant_added'
    """))
    # Plants that arrived by file import. Counted alongside form adds as
    # "explained", never added to the high-water total: high_water already
    # includes them, this only says how they got there.
    imported = scalar(hogql(host, key, f"""
        SELECT sum({_num('plants_imported')}) FROM events
        WHERE event = 'data_imported'
    """)) or 0
    explained = observed + imported
    unobserved = max(plants - explained, 0)
    return {
        "owners": owners,
        "plants": plants,
        "observed_adds": observed,
        "imported_adds": imported,
        "explained": explained,
        "unobserved": unobserved,
        "unobserved_pct": (round(unobserved / plants * 100) if plants else None),
    }


def m_activation(host, key):
    """How many new people added a plant, this week and all time.

    The all-time figure is deliberately NOT computed over every device we have
    ever seen. `plant_added` did not exist for the app's first six weeks, so a
    device that installed before the event shipped looks identical to one that
    installed and never activated. DEC-254: dividing all-time activations by
    all-time installs understated activation by roughly 4x and was read as an
    activation crisis.

    So the cohort is clipped to devices first seen on or after the day
    `plant_added` first appears in the data, and that date is reported next to
    the number so nobody can silently widen the window again.
    """
    rows = hogql(host, key, """
        SELECT min(toDate(timestamp)) FROM events WHERE event = 'plant_added'
    """)
    coverage_start = rows[0][0] if rows and rows[0][0] else None
    if coverage_start is None:
        # No activation events at all: a rate would be meaningless, not zero.
        return {"installs": 0, "activated": 0, "rate": None,
                "coverage_start": None, "all_installs": 0,
                "all_activated": 0, "all_rate": None}

    rows = hogql(host, key, """
        WITH firsts AS (
          SELECT person_id, min(timestamp) AS first_seen
          FROM events GROUP BY person_id
        ),
        activated AS (
          SELECT DISTINCT person_id FROM events WHERE event = 'plant_added'
        )
        SELECT
          countIf(first_seen >= now() - INTERVAL 7 DAY) AS installs_7d,
          countIf(first_seen >= now() - INTERVAL 7 DAY
                  AND person_id IN (SELECT person_id FROM activated)) AS activated_7d,
          countIf(first_seen >= toDate({start})) AS installs_all,
          countIf(first_seen >= toDate({start})
                  AND person_id IN (SELECT person_id FROM activated)) AS activated_all,
          countIf(first_seen < toDate({start})) AS excluded
        FROM firsts
    """.replace("{start}", "'%s'" % coverage_start))

    installs, activated, all_installs, all_activated, excluded = (
        rows[0] if rows else (0, 0, 0, 0, 0))
    return {
        "installs": installs,
        "activated": activated,
        "rate": round(activated / installs * 100) if installs else None,
        "coverage_start": str(coverage_start),
        "all_installs": all_installs,
        "all_activated": all_activated,
        "all_rate": (round(all_activated / all_installs * 100)
                     if all_installs else None),
        "excluded_pre_coverage": excluded,
    }


def m_onboarding(host, key):
    """First-run screen starts vs completes in the last 7 days.

    Reads the welcome-screen events, NOT the retired onboarding_* pair alone.
    See EVENTS for what happened when this queried only the old names.

    Both names are unioned via RETIRED_ALIASES even though a 7-day window can
    no longer reach the retired ones (they stopped 2026-07-30). The union costs
    nothing today and means this stays correct if the window is ever widened,
    which is the change that would silently halve the number. People, not
    events: the two names overlapped 2026-07-02 to 2026-07-30 and anyone who
    updated inside that window sends both.
    """
    started_names = event_names(EVENTS["welcome_shown"])
    completed_names = event_names(EVENTS["welcome_completed"])
    rows = hogql(host, key, f"""
        SELECT
          count(DISTINCT if(event IN ({_in_list(started_names)}),
                            person_id, NULL)) AS started,
          count(DISTINCT if(event IN ({_in_list(completed_names)}),
                            person_id, NULL)) AS completed
        FROM events
        WHERE timestamp >= now() - INTERVAL 7 DAY
          AND event IN ({_in_list(started_names + completed_names)})
    """)
    started = rows[0][0] if rows else 0
    completed = rows[0][1] if rows else 0
    rate = round(completed / started * 100) if started else None
    return {"started": started, "completed": completed, "rate": rate}


def m_funnel(host, key):
    """Activation funnel over the last 7 days: distinct devices per step.

    Reports the biggest single drop-off so the digest can call it out.
    """
    steps = [
        ("opened", EVENTS["opened"]),
        ("onboarded", EVENTS["welcome_completed"]),
        ("plant_added", EVENTS["plant_added"]),
        ("activity_logged", EVENTS["activity_logged"]),
    ]
    counts = []
    for label, event in steps:
        # Unioned over every name the step has been sent under, so a funnel
        # whose window reaches back before ALIAS_CUTOFF_DATE does not lose the
        # half of the population that was still on the old build. DISTINCT
        # person_id makes the four-week overlap safe to union.
        rows = hogql(host, key, f"""
            SELECT count(DISTINCT if(timestamp >= now() - INTERVAL 7 DAY,
                                     person_id, NULL)) AS people_7d,
                   count() AS all_time
            FROM events WHERE event IN ({_in_list(event_names(event))})
        """)
        people_7d = rows[0][0] if rows else 0
        all_time = rows[0][1] if rows else 0
        # An event no code path has ever emitted reads as a step nobody
        # reached. `activity_logged` is the live example: the app declares
        # captureActivityLogged and never calls it, so this step sat at 0
        # while the digest blamed the users. Carry whether the step is
        # measurable at all, so the render and the drop calculation can both
        # refuse to treat "not instrumented" as "nobody did it".
        counts.append((label, people_7d, all_time > 0, event))

    # Biggest absolute drop between consecutive INSTRUMENTED steps. A step we
    # cannot see is skipped rather than scored: a 100% drop into an event that
    # has never existed is a fact about our telemetry, not about the funnel,
    # and printing it in red trains the reader to ignore the line that matters.
    measurable = [(label, n) for label, n, ok, _event in counts if ok]
    biggest = None
    for i in range(1, len(measurable)):
        prev_label, prev_n = measurable[i - 1]
        cur_label, cur_n = measurable[i]
        drop = prev_n - cur_n
        if prev_n and (biggest is None or drop > biggest[2]):
            pct = round(drop / prev_n * 100)
            biggest = (prev_label, cur_label, drop, pct)
    return {"steps": counts, "biggest_drop": biggest}


PURCHASE_OUTCOMES = (
    "'lifetime_purchased','annual_purchased',"
    "'cloud_backup_sub_purchased','cloud_backup_resubscribed'"
)


def m_paywall(host, key):
    """Paywall views and purchase outcomes in the last 7 days.

    This reports REACH (how many people saw the paywall and what they chose).
    It deliberately does not report money: `paywall_result` carries no price,
    and it only started carrying `environment` on 2026-07-01, so any
    environment split derived from it is unreliable for older events. The
    dollar figures come from m_purchases via `purchase_succeeded` instead.
    """
    rows = hogql(host, key, f"""
        SELECT
          countIf(event = 'paywall_shown') AS shown,
          countIf(event = 'paywall_result'
                  AND properties.outcome IN ({PURCHASE_OUTCOMES})) AS purchased,
          countIf(event = 'paywall_result'
                  AND properties.outcome = 'dismissed') AS dismissed
        FROM events
        WHERE timestamp >= now() - INTERVAL 7 DAY
          AND event IN ('paywall_shown', 'paywall_result')
    """)
    return {"shown": rows[0][0] if rows else 0,
            "purchased": rows[0][1] if rows else 0,
            "dismissed": rows[0][2] if rows else 0}


def m_purchases(host, key):
    """Purchases from `purchase_succeeded`: last 7 days AND all time.

    Two defects this exists to prevent, both found in DEC-252:

    1. The digest used to report purchases on a rolling 7-day window only, so
       a real sale appeared in exactly one Monday email and then vanished with
       nothing carrying it forward. Two production purchases went unnoticed for
       24 days. Every window here is reported alongside an all-time cumulative
       total, which cannot fall out of scope.
    2. It used to infer environment with coalesce(environment, 'production'),
       which silently relabels every untagged event as a real sale. Tagging
       only began 2026-07-01, so the 13 purchase outcomes before that are of
       genuinely unknown environment. They are counted as 'untagged', never as
       production.

    `purchase_succeeded` is the only event carrying price, currency and
    environment together, which is why money is reported from it alone.
    """
    rows = hogql(host, key, """
        SELECT
          coalesce(toString(properties.environment), 'untagged') AS env,
          coalesce(toString(properties.currency), '?') AS currency,
          count() AS n_all,
          sum(toFloat(properties.price)) AS revenue_all,
          countIf(timestamp >= now() - INTERVAL 7 DAY) AS n_7d,
          sumIf(toFloat(properties.price),
                timestamp >= now() - INTERVAL 7 DAY) AS revenue_7d
        FROM events
        WHERE event = 'purchase_succeeded'
        GROUP BY env, currency
        ORDER BY env, currency
    """)
    buckets = []
    for env, currency, n_all, rev_all, n_7d, rev_7d in rows:
        buckets.append({
            "env": env, "currency": currency,
            "n_all": n_all, "revenue_all": round(rev_all or 0, 2),
            "n_7d": n_7d, "revenue_7d": round(rev_7d or 0, 2),
        })
    return {"buckets": buckets,
            "production": [b for b in buckets if b["env"] == "production"]}


def m_revenuecat(_host=None, _key=None):
    """Validated revenue from RevenueCat: the receipt, not our own telemetry.

    PostHog's `purchase_succeeded` is fired by our own app and is wrong in
    both directions (DEC-260). It did not exist before 2026-07-01, so it
    never saw the 2026-06-26 production sale at all, and it records the
    sticker price the buyer saw rather than the money we receive. RevenueCat
    holds the store-validated receipt with a gross/commission/tax/proceeds
    breakdown.

    Proceeds is the only figure reported as revenue here. Anything whose
    environment is not literally "production" is excluded, never inferred.
    """
    sys.path.insert(0, SCRIPT_DIR)
    import revenuecat  # noqa: E402 - sibling module, VPS-only credentials

    summary = revenuecat.collect()
    summary.pop("purchases", None)  # the digest wants totals, not receipts
    return summary


# How long a series may go without a capture before the digest says so rather
# than reporting a quiet week. The capture runs weekly, so 10 days is one missed
# run plus slack.
RANK_STALE_DAYS = 10


def m_rank(_host=None, _key=None):
    """Store keyword rank movement, from the append-only series (DAL-257).

    Same "external system" shape as m_revenuecat: underscore-defaulted args and
    a deferred import, so a missing series surfaces through run_metric as an
    error on the section rather than killing the whole digest at import time.

    Movement, not 36 numbers. The first attempt at this was a pair of JSON files
    someone had to remember to diff by hand, and nobody did.
    """
    sys.path.insert(0, SCRIPT_DIR)
    import rank_history  # noqa: E402 - sibling module

    path = rank_history.series_path()
    records = rank_history.read(path)
    if not records:
        raise FileNotFoundError(f"no rank series at {path}")

    out = {"path": path, "stores": {}, "stale": False, "age_days": None}
    # The WORST store, not the best: if Play kept capturing and iOS stopped six
    # weeks ago, a min() here would report the series as healthy and iOS's dead
    # numbers would render as this week's news.
    oldest = None
    for store in rank_history.STORES:
        result = rank_history.diff(records, store)
        if result is None:
            continue
        age = rank_history.age_days(result["curr"])
        for bucket in ("moved", "entered", "dropped"):
            for item in result[bucket]:
                item["line"] = rank_history.describe(item)
        out["stores"][store] = {
            "prev": result["prev"],
            "curr": result["curr"],
            "age_days": age,
            "moved": result["moved"],
            "entered": result["entered"],
            "dropped": result["dropped"],
            "flat_n": result["flat_n"],
            "still_absent_n": result["still_absent_n"],
            "unmeasured_n": len(result["unmeasured"]),
        }
        oldest = age if oldest is None else max(oldest, age)

    out["age_days"] = oldest
    # A stopped capture must read as "no capture", never as "no movement".
    out["stale"] = oldest is None or oldest > RANK_STALE_DAYS
    return out


# The source series is pulled weekly, so 10 days is one missed run plus slack.
# Same number as RANK_STALE_DAYS and deliberately a separate constant: the two
# jobs can stop independently, and sharing the name would invite someone to
# "fix" one cadence by changing the other.
SOURCES_STALE_DAYS = 10

# The pull can run, succeed, and still bring back nothing new. Apple's
# ONE_TIME_SNAPSHOT stops producing instances, so every candidate row becomes a
# re-observation of a day already recorded as complete and `new_rows` correctly
# appends none of them. On 2026-08-30 that is exactly what happened: the job
# ran, reported "Data through 2026-08-27", and appended 0 of 161 rows.
#
# SOURCES_STALE_DAYS could not see it, because `pulled_at` only advances when a
# row lands. It would have caught this one a week late and only by luck: had a
# single restatement row landed, pull age would have reset to 0 and a
# permanently frozen series would have read as healthy forever.
#
# So the newest COMPLETE DAY is checked as well as the newest pull. A healthy
# cadence puts it 4 days back at digest time (Sunday 22:40 pull, minus Apple's
# 3-day tail, read Monday 00:00); one missed week puts it at 11. 10 therefore
# stays quiet on a good week and speaks up the first week the reportable window
# fails to grow, which is the week the reader needs it: a window that has not
# moved is not this week's news, however current the pull timestamp looks.
SOURCES_DATA_STALE_DAYS = 10


def m_appstore_sources(_host=None, _key=None):
    """Where App Store impressions come from: search vs browse.

    The denominator for the rank section above it. A rank is a position in a
    list; this is whether anybody was looking at the list. If browse supplies
    most of our impressions then keyword rank is not our lever, however well we
    rank, and that conclusion should arrive in the same email as the ranks.

    Reads the CSV series, never the App Store Connect API: the digest must not
    block on Apple, must not need PyJWT or the .p8 on this code path, and must
    not turn a credential problem at 00:00 Monday into a missing digest.
    """
    sys.path.insert(0, SCRIPT_DIR)
    import appstore_sources  # noqa: E402 - sibling module

    path = appstore_sources.series_path()
    records = appstore_sources.read(path)
    if not records:
        # Not zero traffic. Apple takes 24-48h to generate a snapshot and a
        # ONE_TIME_SNAPSHOT stops producing instances afterwards, so an absent
        # series is a normal early state and a stopped job later on. Either way
        # it is an absence of measurement (DEC-249), so it is raised.
        raise FileNotFoundError(f"no App Store source series at {path}")

    split = appstore_sources.split_on_rename(records)
    age = appstore_sources.series_age_days(records)
    data_age = appstore_sources.data_age_days(records)

    # Two independent failures, detected and reported apart because they need
    # different fixes: a stopped job is cron or credentials, a frozen series is
    # a new App Store Connect report request. Pull staleness is checked first
    # so a job that is not running is never described as a frozen report.
    pull_stale = age is None or age > SOURCES_STALE_DAYS
    data_stale = data_age is None or data_age > SOURCES_DATA_STALE_DAYS
    return {
        "path": path,
        "split": split,
        "age_days": age,
        "data_age_days": data_age,
        "newest_complete_date": appstore_sources.newest_complete_date(records),
        "stale": pull_stale or data_stale,
        "stale_reason": "pull" if pull_stale else ("data" if data_stale else None),
    }


def m_store_listing(_host=None, _key=None):
    """Does the live store copy still describe the app we actually ship?

    The listing is the conversion surface: DEC-261 found all three buyers
    purchased on install day, so the decision is made from the store page and
    the first run, before the product is experienced. The copy has been wrong
    twice (DEC-247, DEC-262) and both times a human found it by reading the
    page. Rules live in store_listing_check, which asserts against the Flutter
    source rather than against a snapshot of yesterday's text.
    """
    sys.path.insert(0, SCRIPT_DIR)
    import store_listing_check  # noqa: E402 - sibling module

    return store_listing_check.check()


def m_purchase_reconciliation(host, key):
    """Cross-check `paywall_result` purchase outcomes against `purchase_succeeded`.

    These are emitted by different code paths, so a divergence means one of
    them is dropping events and the money line cannot be trusted. Reported
    only for the period since environment tagging began, because before that
    `purchase_succeeded` was not being sent at all and a mismatch is expected.
    """
    rows = hogql(host, key, f"""
        SELECT
          countIf(event = 'paywall_result'
                  AND properties.outcome IN ({PURCHASE_OUTCOMES})) AS via_paywall,
          countIf(event = 'purchase_succeeded') AS via_purchase
        FROM events
        WHERE timestamp >= toDateTime('2026-07-01 00:00:00')
          AND event IN ('paywall_result', 'purchase_succeeded')
    """)
    via_paywall = rows[0][0] if rows else 0
    via_purchase = rows[0][1] if rows else 0
    return {"via_paywall": via_paywall, "via_purchase": via_purchase,
            "agrees": via_paywall == via_purchase}


def m_retention(host, key):
    """Of devices first seen 8-14 days ago, how many returned on a later day?

    A simple D1+ proxy: active on >=2 distinct calendar days.
    """
    rows = hogql(host, key, """
        WITH per_device AS (
          SELECT person_id,
                 min(timestamp) AS first_seen,
                 count(DISTINCT toDate(timestamp)) AS active_days
          FROM events GROUP BY person_id
        )
        SELECT
          count() AS cohort,
          countIf(active_days >= 2) AS returned
        FROM per_device
        WHERE first_seen >= now() - INTERVAL 14 DAY
          AND first_seen < now() - INTERVAL 7 DAY
    """)
    cohort = rows[0][0] if rows else 0
    returned = rows[0][1] if rows else 0
    rate = round(returned / cohort * 100) if cohort else None
    return {"cohort": cohort, "returned": returned, "rate": rate}


def m_top_screens(host, key):
    """Most-viewed screens in the last 7 days."""
    rows = hogql(host, key, """
        SELECT coalesce(properties.$screen_name, '(unnamed)') AS screen,
               count() AS views
        FROM events
        WHERE event = '$screen'
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY screen ORDER BY views DESC LIMIT 8
    """)
    return {"rows": rows}


def m_backup(host, key):
    """Backup completed vs failed (last 7 days), failures grouped by reason."""
    completed = scalar(hogql(host, key, """
        SELECT count() FROM events
        WHERE event = 'backup_completed'
          AND timestamp >= now() - INTERVAL 7 DAY
    """))
    failed_rows = hogql(host, key, """
        SELECT coalesce(properties.reason, 'unknown') AS reason, count()
        FROM events
        WHERE event = 'backup_failed'
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY reason ORDER BY count() DESC
    """)
    return {"completed": completed, "failed": failed_rows}


# ── New-event metrics (2026-08-31 instrumentation) ──────────────────────────

def _num(name):
    """HogQL fragment reading a numeric property.

    The SDK sends some of these as JSON numbers and some as quoted strings
    depending on the call site, and `toInt` on the wrong one is NULL, which
    then sums to NULL and renders as a blank rather than as an error. Extract
    raw, strip quotes, coerce. Zero for a missing property is correct here:
    every caller sums counts, and an event that omits the field contributes
    nothing.
    """
    return f"toIntOrZero(replaceAll(JSONExtractRaw(properties, '{name}'), '\"', ''))"


def _bool_true(name):
    """HogQL fragment that is true only when a boolean property is literally true.

    Deliberately not `!= 'false'`: a missing property is unknown, not false.
    """
    return f"toString(properties.{name}) = 'true'"


def event_names(primary):
    """Every name an event has been sent under, newest first.

    A window that reaches back before ALIAS_CUTOFF_DATE sees part of the
    population under the retired name and part under the current one, so
    reading either alone undercounts. Callers must aggregate over
    `count(DISTINCT person_id)`, never a sum of per-name counts: the two names
    overlapped for four weeks and one person who updated mid-window sends both.
    """
    return [primary] + RETIRED_ALIASES.get(primary, [])


def _in_list(names):
    return ", ".join("'%s'" % n for n in names)


def m_super_property_coverage(host, key):
    """Can we segment at all yet, and on how much of the traffic?

    This is to the segment section what m_event_liveness is to the digest: it
    is read before the splits below it, because a split of nothing renders
    exactly like a split of a population that is uniformly one value.

    The super properties attach to every event from the build that introduces
    them and to no event before it. On 2026-08-31 that was zero of 15,401
    events. So an absent `is_pro` means one of two unrelated things, and adding
    them together is the DEC-317 error: the user is not Pro, or the event
    predates the instrument. Coverage is what tells those apart, so every
    denominator below is drawn from events that carry the property rather than
    from all events.

    Coverage is measured BOTH by event and by person, and the gap between them
    is the finding. During an ordinary build rollout the two track each other,
    because the share of events carrying the property is roughly the share of
    people who have updated. They come apart when coverage correlates with
    something about the USER instead of with the build, and the case that
    matters is the properties attaching only once somebody signs in.

    That failure is invisible in the event figure alone. In the 28 days to
    2026-08-31 the app had 84 people: 13 signed in generating 3,590 events, and
    71 anonymous generating 2,382. Properties that needed a session would have
    reported 60% of events covered, which reads as an unremarkable mid-rollout
    number, while 85% of the people were missing entirely. Signed-in users are
    the heavy users, so weighting by event hides exactly the population the
    super properties exist to reach.
    """
    covered_events = ", ".join(
        f"countIf(JSONHas(properties, '{p}')) AS ev_{p}"
        for p in SUPER_PROPERTIES)
    covered_people = ", ".join(
        f"count(DISTINCT if(JSONHas(properties, '{p}'), person_id, NULL)) "
        f"AS pe_{p}"
        for p in SUPER_PROPERTIES)
    rows = hogql(host, key, f"""
        SELECT count() AS events_7d,
               count(DISTINCT person_id) AS people_7d,
               {covered_events},
               {covered_people}
        FROM events
        WHERE timestamp >= now() - INTERVAL 7 DAY
    """)
    if not rows:
        return {"events_7d": 0, "people_7d": 0, "by_property": {},
                "any": False, "skew": None}
    row = rows[0]
    events_7d, people_7d = row[0], row[1]
    n_props = len(SUPER_PROPERTIES)
    by_property = {}
    for i, prop in enumerate(SUPER_PROPERTIES):
        ev = row[2 + i]
        pe = row[2 + n_props + i]
        by_property[prop] = {
            "events": ev,
            "pct": round(ev / events_7d * 100) if events_7d else None,
            "people": pe,
            "people_pct": round(pe / people_7d * 100) if people_7d else None,
        }
    # Read from the BEST covered property rather than a named one, so a
    # property being renamed or failing to compute cannot zero the headline
    # while its siblings are plainly arriving. COVERAGE_PROBE breaks ties so
    # the label is stable on an ordinary week.
    probe = max(by_property,
                key=lambda p: (by_property[p]["events"], p == COVERAGE_PROBE))
    best = by_property[probe]
    return {
        "events_7d": events_7d,
        "people_7d": people_7d,
        "probe": probe,
        "covered_people": best["people"],
        "by_property": by_property,
        "any": any(v["events"] for v in by_property.values()),
        "skew": _coverage_skew(best),
        "spread": _coverage_spread(by_property),
    }


def _coverage_spread(by_property):
    """Do the super properties disagree with each other about coverage?

    They are registered in a single loop over one map, so every event carrying
    one should carry all of them. Verified in the live data: all 95 events from
    build 65 carry all seven. A spread therefore is not rollout noise, it means
    one of them is spelled differently from what this file expects, or its
    value failed to compute and was dropped.

    That is the single most likely defect during a property rename, and it is
    invisible in any one property's number.
    """
    counts = {p: v["events"] for p, v in by_property.items()}
    hi, lo = max(counts.values()), min(counts.values())
    if not hi or hi == lo:
        return None
    return {"high": hi, "low": lo,
            "behind": sorted(p for p, n in counts.items() if n < hi)}


# How far event coverage may run ahead of people coverage before the gap is
# reported as a finding rather than as rollout noise.
#
# A build rollout moves both together. Heavier users do update slightly sooner,
# so a few points of positive skew is ordinary. 20 points is not: that is the
# signature of coverage attached to a user attribute, and the attribute to
# suspect first is having a session, because signed-in users generate several
# times the events of anonymous ones (276 per person against 34, 28d to
# 2026-08-31).
COVERAGE_SKEW_POINTS = 20


def _coverage_skew(entry):
    """Report event-vs-people coverage divergence, or None when they agree."""
    ev, pe = entry.get("pct"), entry.get("people_pct")
    if ev is None or pe is None or not ev:
        return None
    gap = ev - pe
    if gap < COVERAGE_SKEW_POINTS:
        return None
    return {"events_pct": ev, "people_pct": pe, "gap": gap}


# Segments worth a line in a weekly email. The full SUPER_PROPERTIES tuple is
# checked for coverage above; only these are broken out, because seven
# distributions is a table nobody reads and the other three are better read as
# filters on a specific question than as a weekly split.
# `is_sandbox` measures a SANDBOX PURCHASE, not a test install. Verified in
# the Flutter source 2026-09-03: `EntitlementSnapshot.fromCustomerInfo` reads
# the flag off whichever entitlement is active and falls back to
# `active?.isSandbox ?? false`, so somebody who owns nothing reports `false`
# whether they are on TestFlight or the public build. Do not read a low
# `is_sandbox` share as "few testers"; tester traffic is separated by build
# number, not by this.
SEGMENT_PROPERTIES = ("pro_source", "cloud_backup_source", "is_sandbox",
                      "plant_count_bucket", "days_since_install_bucket")


def m_segments(host, key):
    """Who this week's active people are, split by the super properties.

    Segments on `properties.X`. NOT `person.properties.X`: these are event
    properties, they never reach the person store, and a person-scoped read
    returns NULL for everybody rather than erroring. That failure is invisible
    -- it renders as "no Pro users" rather than as a broken query -- which is
    why test_treesmith_super_properties.py fails the build on the person form.

    The point of these being event properties is that they cover anonymous
    users too, which is most of ours: 43 MAU against 28 lifetime auth_completed
    events. A person-property segment would have been blind to nearly all of
    them.
    """
    coverage = m_super_property_coverage(host, key)
    if not coverage["any"]:
        # No event carries them yet. Return the coverage alone: printing five
        # empty distributions would read as five findings about a flat
        # population rather than as an instrument that has not landed.
        return {"coverage": coverage, "splits": {}}

    splits = {}
    for prop in SEGMENT_PROPERTIES:
        rows = hogql(host, key, f"""
            SELECT coalesce(toString(properties.{prop}), '(null)') AS value,
                   count(DISTINCT person_id) AS people,
                   count() AS events
            FROM events
            WHERE timestamp >= now() - INTERVAL 7 DAY
              AND JSONHas(properties, '{prop}')
            GROUP BY value
            ORDER BY people DESC, value
        """)
        total_people = sum(r[1] for r in rows)
        splits[prop] = {
            "rows": [{"value": r[0], "people": r[1], "events": r[2],
                      "pct": (round(r[1] / total_people * 100)
                              if total_people else None)}
                     for r in rows],
            "people": total_people,
        }
    return {"coverage": coverage, "splits": splits}


def m_entitlement_integrity(host, key):
    """Did anybody reach a Pro-only feature without Pro?

    This check exists because `pro_source` makes it possible for the first
    time. A Pro-gated event carrying `pro_source = none` is a contradiction on
    its face: the app would not have shown that person the control. Exactly one
    of two things is wrong, and both matter.

      The gate leaked.   Somebody used a paid feature without paying, which is
                         a revenue bug.
      The label is wrong. The stamp disagrees with what the app actually did,
                         which is the DEC-317 failure in a new place: every
                         segment built on it would be quietly misfiled.

    The digest cannot tell those apart and does not try. It reports the
    contradiction and names both readings, because either one is worth an
    interruption and guessing between them would make the wrong one invisible.

    `comp` is reported alongside, not as a problem but as the answer to a
    question we could not previously ask at all: how many people hold Pro
    without having paid. Before this property the comped population was
    invisible in analytics, filed indistinguishably among free users.
    """
    rows = hogql(host, key, f"""
        SELECT event,
               coalesce(toString(properties.pro_source), '(absent)') AS pro_source,
               count() AS n,
               count(DISTINCT person_id) AS people
        FROM events
        WHERE event IN ({_in_list(PRO_GATED_EVENTS)})
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY event, pro_source
        ORDER BY n DESC
    """)
    by_source = {}
    contradictions = []
    for event, source, n, people in rows:
        by_source[source] = by_source.get(source, 0) + n
        if source == "none":
            contradictions.append({"event": event, "n": n, "people": people})

    # Who holds Pro at all, paid or comped, across everything this week. The
    # denominator the comp question needs.
    holders = hogql(host, key, """
        SELECT coalesce(toString(properties.pro_source), '(absent)') AS pro_source,
               count(DISTINCT person_id) AS people
        FROM events
        WHERE timestamp >= now() - INTERVAL 7 DAY
          AND JSONHas(properties, 'pro_source')
        GROUP BY pro_source
    """)
    people_by_source = {r[0]: r[1] for r in holders}
    return {
        "contradictions": contradictions,
        "gated_by_source": by_source,
        "people_by_source": people_by_source,
        "paid": people_by_source.get("paid", 0),
        "comped": people_by_source.get("comp", 0),
        "measurable": bool(people_by_source),
    }


# Why this digest has no notification delivery rate, stated once and rendered
# into the email so the absence is visible rather than looking like an
# oversight somebody should fix.
#
# The app is only ever woken by a tap. It cannot observe a notification being
# delivered, shown, or swiped away, so the denominator for a delivery rate does
# not exist on the device and never will. Dividing taps by anything and calling
# it delivery would be inventing the denominator.
#
# What can be measured honestly: `reminder_created` with `schedule_status` says
# what we asked the OS to do (and `blocker` says why it refused), and
# `reminder_sweep.left_due` counts reminders that were due and still sitting
# there at the next cold start, which is the closest thing to an ignored
# reminder that the device can actually see.
REMINDER_DELIVERY_NOTE = (
    "No delivery rate: the app is only woken by a tap, so a notification that "
    "was delivered and ignored is indistinguishable from one never delivered. "
    "left_due below is the ignored-proxy."
)


def m_reminders(host, key):
    """Reminders: what we scheduled, what the OS blocked, what got tapped.

    Three events, three different questions, and the digest keeps them apart:

      reminder_created   what the app asked for, and whether the OS accepted.
                         The only legitimate denominator here.
      reminder_sweep     one per cold start, so it is a sample of app launches
                         and not of reminders. `left_due` is the ignored-proxy.
      ..._tapped         the only thing the device can observe about delivery.

    See REMINDER_DELIVERY_NOTE for the rate that is deliberately absent.
    """
    created = hogql(host, key, """
        SELECT coalesce(toString(properties.schedule_status), '(unset)') AS status,
               coalesce(toString(properties.blocker), '') AS blocker,
               coalesce(toString(properties.activity_type), '(unset)') AS activity_type,
               count() AS n,
               count(DISTINCT person_id) AS people
        FROM events
        WHERE event = 'reminder_created'
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY status, blocker, activity_type
        ORDER BY n DESC
    """)
    tapped = hogql(host, key, """
        SELECT coalesce(toString(properties.launch), '(unset)') AS launch,
               coalesce(toString(properties.activity_type), '(unset)') AS activity_type,
               count() AS n,
               count(DISTINCT person_id) AS people
        FROM events
        WHERE event = 'reminder_notification_tapped'
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY launch, activity_type
        ORDER BY n DESC
    """)
    sweeps = hogql(host, key, f"""
        SELECT count() AS sweeps,
               count(DISTINCT person_id) AS people,
               sum({_num('active')}) AS active,
               sum({_num('already_pending')}) AS already_pending,
               sum({_num('scheduled')}) AS scheduled,
               sum({_num('blocked')}) AS blocked,
               sum({_num('failed')}) AS failed,
               sum({_num('left_due')}) AS left_due,
               countIf({_num('left_due')} > 0) AS sweeps_with_due
        FROM events
        WHERE event = 'reminder_sweep'
          AND timestamp >= now() - INTERVAL 7 DAY
    """)

    # All-time, so the render can tell "never arrived" from "quiet week".
    # Hiding a section on a 7-day zero would hide a reminder feature that has
    # been live for months and simply had a slow week, which is a real reading.
    ever = hogql(host, key, """
        SELECT count() FROM events
        WHERE event IN ('reminder_created', 'reminder_notification_tapped',
                        'reminder_sweep')
    """)

    created_total = sum(r[3] for r in created)
    scheduled_ok = sum(r[3] for r in created if r[0] == "scheduled")
    blocked_rows = [{"status": r[0], "blocker": r[1] or "(none given)",
                     "n": r[3], "people": r[4]}
                    for r in created if r[0] != "scheduled"]
    taps_total = sum(r[2] for r in tapped)
    s = sweeps[0] if sweeps else [0] * 9
    sweep = {
        "sweeps": s[0], "people": s[1], "active": s[2],
        "already_pending": s[3], "scheduled": s[4], "blocked": s[5],
        "failed": s[6], "left_due": s[7], "sweeps_with_due": s[8],
    }
    return {
        "all_time": scalar(ever),
        "created_total": created_total,
        "scheduled_ok": scheduled_ok,
        "by_status": [{"status": r[0], "blocker": r[1],
                       "activity_type": r[2], "n": r[3], "people": r[4]}
                      for r in created],
        "blocked": blocked_rows,
        "taps_total": taps_total,
        "by_launch": [{"launch": r[0], "activity_type": r[1],
                       "n": r[2], "people": r[3]} for r in tapped],
        "cold_taps": sum(r[2] for r in tapped if r[0] == "cold"),
        "warm_taps": sum(r[2] for r in tapped if r[0] == "warm"),
        # Taps per SCHEDULED reminder. Not a delivery rate and not per
        # notification: a repeating reminder is created once and fires many
        # times, so this can legitimately exceed 100% and must never be read as
        # a share of notifications. It is here because reminder_created is the
        # only denominator the instrument actually supports.
        "taps_per_scheduled": (round(taps_total / scheduled_ok * 100)
                               if scheduled_ok else None),
        "sweep": sweep,
    }


def m_feature_usage(host, key):
    """The content and structure events, 7 days and all time.

    All time as well as weekly for the same reason the purchase section carries
    it (DEC-252): these are low-volume events, and a feature used three times
    in six months looks identical to one never shipped if the only window is
    seven days long.
    """
    names = ("graft_added", "zone_added", "photo_deleted",
             "plants_bulk_edited", "activity_logged")
    totals = hogql(host, key, f"""
        SELECT event,
               count() AS all_time,
               countIf(timestamp >= now() - INTERVAL 7 DAY) AS n_7d,
               count(DISTINCT if(timestamp >= now() - INTERVAL 7 DAY,
                                 person_id, NULL)) AS people_7d
        FROM events
        WHERE event IN ({_in_list(names)})
        GROUP BY event
    """)
    by_event = {r[0]: {"all_time": r[1], "n_7d": r[2], "people_7d": r[3]}
                for r in totals}
    for n in names:
        by_event.setdefault(n, {"all_time": 0, "n_7d": 0, "people_7d": 0})

    grafts = hogql(host, key, f"""
        SELECT coalesce(toString(properties.type_family), '(unset)') AS type_family,
               coalesce(toString(properties.source), '(unset)') AS source,
               countIf({_bool_true('has_type')}) AS with_type,
               count() AS n
        FROM events
        WHERE event = 'graft_added'
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY type_family, source
        ORDER BY n DESC
    """)
    activities = hogql(host, key, f"""
        SELECT coalesce(toString(properties.activity_type), '(unset)') AS activity_type,
               count() AS n,
               countIf({_bool_true('created_reminder')}) AS created_reminder,
               countIf({_bool_true('has_notes')}) AS with_notes
        FROM events
        WHERE event = 'activity_logged'
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY activity_type
        ORDER BY n DESC
    """)
    bulk = hogql(host, key, f"""
        SELECT coalesce(toString(properties.operation), '(unset)') AS operation,
               coalesce(toString(properties.to_status), '') AS to_status,
               count() AS n,
               sum({_num('count')}) AS plants
        FROM events
        WHERE event = 'plants_bulk_edited'
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY operation, to_status
        ORDER BY plants DESC
    """)
    photos = hogql(host, key, f"""
        SELECT coalesce(toString(properties.category), '(unset)') AS category,
               count() AS n,
               countIf({_bool_true('was_last_photo')}) AS was_last,
               countIf({_bool_true('has_graft_link')}) AS graft_linked
        FROM events
        WHERE event = 'photo_deleted'
          AND timestamp >= now() - INTERVAL 7 DAY
        GROUP BY category
        ORDER BY n DESC
    """)
    return {
        "by_event": by_event,
        "grafts": [{"type_family": r[0], "source": r[1],
                    "with_type": r[2], "n": r[3]} for r in grafts],
        "activities": [{"activity_type": r[0], "n": r[1],
                        "created_reminder": r[2], "with_notes": r[3]}
                       for r in activities],
        "bulk": [{"operation": r[0], "to_status": r[1], "n": r[2],
                  "plants": r[3]} for r in bulk],
        "photos": [{"category": r[0], "n": r[1], "was_last": r[2],
                    "graft_linked": r[3]} for r in photos],
    }


def m_data_portability(host, key):
    """Exports and imports, 7 days and all time.

    `data_imported` is the reason this section is worth its space. m_plants has
    reported an unobservable share of the plant population since DAL-265,
    because `plant_added` fires only from the plant form and a plant arriving
    by import or restore announced nothing. `plants_imported` is the first
    instrument that can see that route, so the blind spot stops being a number
    we can only estimate. It does NOT close it: restore-from-backup is still
    unobserved, so the gap shrinks rather than disappearing.

    `replaced_existing` is reported separately and never added to the imported
    total: a replacing import overwrites a library rather than adding to it, so
    summing the two counts the same plants twice.
    """
    rows = hogql(host, key, f"""
        SELECT event,
               coalesce(toString(properties.format), '(unset)') AS format,
               count() AS all_time,
               countIf(timestamp >= now() - INTERVAL 7 DAY) AS n_7d,
               count(DISTINCT person_id) AS people,
               sumIf({_num('plants_exported')},
                     timestamp >= now() - INTERVAL 7 DAY) AS plants_exported_7d,
               sumIf({_num('plants_imported')},
                     timestamp >= now() - INTERVAL 7 DAY) AS plants_imported_7d,
               sumIf({_num('rows_imported')},
                     timestamp >= now() - INTERVAL 7 DAY) AS rows_imported_7d,
               sum({_num('plants_imported')}) AS plants_imported_all,
               countIf({_bool_true('replaced_existing')}) AS replaced
        FROM events
        WHERE event IN ('data_exported', 'data_imported')
        GROUP BY event, format
        ORDER BY event, all_time DESC
    """)
    exports = [r for r in rows if r[0] == "data_exported"]
    imports = [r for r in rows if r[0] == "data_imported"]

    def pack(rs):
        return [{"format": r[1], "all_time": r[2], "n_7d": r[3],
                 "people": r[4], "plants_exported_7d": r[5],
                 "plants_imported_7d": r[6], "rows_imported_7d": r[7],
                 "plants_imported_all": r[8], "replaced": r[9]} for r in rs]

    # Rows that did not become plants. A CSV with 400 rows that imports 12
    # plants is a parser or a column-mapping problem, and it is invisible in
    # either number on its own.
    rows_in = sum(r[7] for r in imports)
    plants_in = sum(r[6] for r in imports)
    return {
        "exports": pack(exports),
        "imports": pack(imports),
        "exports_7d": sum(r[3] for r in exports),
        "imports_7d": sum(r[3] for r in imports),
        "plants_imported_7d": plants_in,
        "rows_imported_7d": rows_in,
        "plants_imported_all": sum(r[8] for r in imports),
        "replaced_existing": sum(r[9] for r in imports),
        "unconverted_rows": max(rows_in - plants_in, 0),
        "row_conversion_pct": (round(plants_in / rows_in * 100)
                               if rows_in else None),
    }


def m_locations(host, key):
    """Locations per person, and the ceiling that makes it unreadable until now.

    `location_added` fired from one of the app's three location-creation paths,
    so `location_count_after` has a hard historical maximum of 1: on 2026-08-31
    every one of the 77 events ever recorded carried exactly 1, with no other
    value present. That is not a population where nobody has two locations. It
    is an instrument that could not count past one.

    So the fix produces a step change in any trend that spans it, and that step
    is an artefact of measurement, not a change in behaviour. Rather than
    hardcode a fix date that will drift out of step with the build that
    actually ships it, the boundary is DERIVED: the first day the data contains
    a value above 1 is the first day the other two paths were reporting. Before
    that day the series is clipped and reported as a ceiling; after it, the two
    windows are reported apart and never joined into one trend.

    The limitation is stated rather than hidden: if the fix ships and no user
    ever creates a second location, no value above 1 appears and this keeps
    reporting a ceiling. That reads as "still cannot tell", which is the honest
    answer, and the awaiting-events section above says whether the build has
    landed at all.
    """
    rows = hogql(host, key, f"""
        SELECT count() AS adds,
               count(DISTINCT person_id) AS people,
               max({_num('location_count_after')}) AS max_after,
               countIf({_num('location_count_after')} > 1) AS above_one,
               toString(min(toDate(timestamp))) AS first_seen,
               toString(minIf(toDate(timestamp),
                              {_num('location_count_after')} > 1)) AS first_multi
        FROM events
        WHERE event = 'location_added'
    """)
    if not rows or not rows[0][0]:
        return {"adds": 0, "people": 0, "max_after": 0, "capped": True,
                "boundary": None, "pre": None, "post": None}
    adds, people, max_after, above_one, first_seen, first_multi = rows[0]
    capped = max_after <= 1
    boundary = None if capped else first_multi

    out = {"adds": adds, "people": people, "max_after": max_after,
           "above_one": above_one, "first_seen": first_seen,
           "capped": capped, "boundary": boundary, "pre": None, "post": None}
    if capped:
        return out

    # Past the boundary the two windows are reported side by side and never
    # concatenated: joining them draws a line that steps up on the day the
    # instrument was fixed and invites the reader to explain a measurement
    # change as user behaviour.
    split = hogql(host, key, f"""
        SELECT toDate(timestamp) >= toDate('{boundary}') AS post,
               count() AS adds,
               count(DISTINCT person_id) AS people,
               max({_num('location_count_after')}) AS max_after,
               round(avg({_num('location_count_after')}), 2) AS avg_after
        FROM events
        WHERE event = 'location_added'
        GROUP BY post
    """)
    for is_post, n, ppl, mx, avg in split:
        bucket = {"adds": n, "people": ppl, "max_after": mx, "avg_after": avg}
        out["post" if is_post else "pre"] = bucket
    return out



# ── Rendering ────────────────────────────────────────────────────────────────

GREEN = "#2e7d32"
RED = "#c62828"
GREY = "#888"


STORE_LABELS = {"appstore": "iOS", "play": "Play"}
RANK_LIST_LIMIT = 5  # per bucket per store. The digest reports movement, and a
                     # 36-line table is a table nobody reads.


SEGMENT_VALUE_LIMIT = 4  # values per super property. A bucket property with a
                         # long tail is a distribution, and a weekly email is
                         # not where a distribution gets read.
FEATURE_LIST_LIMIT = 5   # breakdown rows per feature event.


def _hidden_while_awaiting(names, ever_seen):
    """Should a section be omitted entirely rather than rendered as zeros?

    Only when it has NEVER had data and every event feeding it is still inside
    its declared grace. That is not a silent suppression: every name here is in
    EVENTS, and m_event_liveness reports each one above, in grey while it is
    awaiting and in red the moment it is overdue. So the absence is stated
    once, in the section built for stating absences, instead of as four blocks
    of zeros that would be identical whether the build had landed or not.

    A quiet WEEK never triggers this: `ever_seen` is an all-time count, so a
    live feature with a slow week still renders its zeros, which is a real
    reading and belongs in the email.
    """
    return not ever_seen and all(n in AWAITING_FIRST_EVENT for n in names)


SOURCES_LIST_LIMIT = 4   # source types per window. Apple defines seven and the
                         # tail is App Clip / Notification / Unavailable noise.
# Kept as prose rather than importing INCOMPLETE_TAIL_DAYS, so rendering the
# digest never needs the puller module to be importable.
SOURCES_TAIL_NOTE = "3 days"


def _pct_or_na(value):
    """A share of no impressions is undefined, not 0%."""
    return "n/a" if value is None else f"{value}%"


def _esc(text):
    """Escape text we did not write.

    Competitor app names come straight from the stores and are the only strings
    in this digest with no author here. "Case Tracker for USCIS & NVC" is real.
    """
    return (str(text).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _stamp(captured_at):
    """`2026-08-13T01:56:00Z` -> `2026-08-13 01:56Z`.

    Minutes, not just the date: the Play baseline and the Play day-0 capture are
    the same date 59 minutes apart, and rendering both as "2026-08-13" would
    read as a bug.
    """
    return captured_at[:16].replace("T", " ") + "Z"


def _delta_str(delta):
    if delta is None:
        return "--"
    return f"{delta:+d}%"


def render(metrics):
    """Return (text, html) for the digest from the metrics dict."""
    t = []  # text lines
    h = []  # html parts

    def line(s=""):
        t.append(s)

    def html(s):
        h.append(s)

    line("TreeSmith Weekly")
    line("=" * 40)
    html('<h2 style="margin:0 0 4px 0;">TreeSmith Weekly</h2>')
    html('<p style="color:#888;font-size:12px;margin:0 0 16px 0;">'
         'Rates are last 7 days; purchase counts are shown weekly AND '
         'all-time so a sale cannot age out. Revenue is read from RevenueCat '
         '(store-validated receipts, proceeds after commission and tax); '
         'PostHog figures are our own client-side telemetry and are '
         'directional. Only environment=production counts as revenue.</p>')

    def section(title):
        line("")
        line(title)
        line("-" * len(title))
        html(f'<h3 style="margin:16px 0 4px 0;font-size:14px;">{title}</h3>')

    def kv(label, value, color=None):
        line(f"  {label:<26} {value}")
        c = f"color:{color};" if color else ""
        html(f'<div style="font-family:monospace;font-size:13px;">'
             f'<span style="display:inline-block;width:240px;">{label}</span>'
             f'<span style="{c}">{value}</span></div>')

    def err(name, msg):
        line(f"  {name}: ERROR {msg}")
        html(f'<div style="color:{RED};font-size:12px;">{name}: {msg}</div>')

    # Event liveness. Deliberately first: every number below is built on these
    # events, so a broken input has to be read before the figures derived from
    # it. Renders nothing at all when everything is arriving, because this runs
    # every week and a section that always says "fine" stops being read.
    lv = metrics.get("liveness")
    if lv and lv["ok"]:
        d = lv["data"]
        awaiting = d.get("awaiting") or []
        if d["silent"] or d["never_seen"] or awaiting:
            section("Event liveness")
            for s in d["silent"]:
                ago = ("" if s["days_ago"] is None
                       else f" ({s['days_ago']}d ago)")
                kv(s["event"],
                   f"SILENT. Last seen {s['last_seen']}{ago}, "
                   f"{s['all_time']} events historically. Renamed or dropped? "
                   f"Any metric reading it is showing zero.", RED)
            for entry in d["never_seen"]:
                # Tolerate the old list-of-strings shape so a half-deployed
                # pair of files reports the event rather than raising.
                name = entry["event"] if isinstance(entry, dict) else entry
                waited = entry.get("days_waiting") if isinstance(entry, dict) else None
                if waited is not None:
                    kv(name,
                       f"declared {waited}d ago and STILL never seen (grace was "
                       f"{AWAITING_GRACE_DAYS}d). The capture was never wired "
                       f"up, or the name does not match what the app sends.",
                       RED)
                else:
                    kv(name,
                       "never seen. Typo in EVENTS, or an event that never "
                       "shipped.", RED)
            # Grey, and last: this is a rollout in progress, not a defect. It
            # is printed rather than hidden so that "the build has not landed
            # yet" and "we forgot to instrument it" are never the same silence.
            #
            # Collapsed to one line per declaration date rather than one per
            # event. Ten events were declared together on 2026-08-31, and ten
            # copies of the same 40-word sentence is the wallpaper this whole
            # section exists to avoid: the reader who scrolls past it is the
            # reader who will also scroll past a real SILENT warning next to
            # it. The names still appear in full, which is what makes the line
            # actionable.
            by_date = {}
            for a in awaiting:
                by_date.setdefault((a["declared"], a["days_waiting"],
                                    a["grace_days"]), []).append(a["event"])
            for (declared, waited, grace), evs in sorted(by_date.items()):
                kv(f"Awaiting first event ({len(evs)})",
                   f"declared {declared}, none seen yet ({waited}d of {grace}d "
                   f"grace): " + ", ".join(sorted(evs)), GREY)
                kv("  ", "declared in the app and not yet arrived. Any metric "
                         "reading these is empty because of the rollout, not "
                         "the users.", GREY)
    elif lv and not lv["ok"]:
        # An errored liveness check is itself a blind spot, so say so rather
        # than letting the section's silence read as "all events healthy".
        section("Event liveness")
        err("Event liveness", lv["error"])

    # Growth
    section("Growth")
    g = metrics["installs"]
    if g["ok"]:
        d = g["data"]
        color = GREEN if (d["delta"] or 0) >= 0 else RED
        kv("New installs (7d)",
           f"{d['this_week']}  ({_delta_str(d['delta'])} WoW)", color)
    else:
        err("New installs", g["error"])
    a = metrics["active"]
    if a["ok"]:
        kv("Active people (7d / 28d)",
           f"{a['data']['wau']} / {a['data']['mau']}")
    else:
        err("Active people", a["error"])
    idm = metrics["identity"]
    if idm["ok"]:
        d = idm["data"]
        if d["persons"]:
            kv("  Counting people, not device ids",
               f"{d['persons']} people across {d['ids']} ids "
               f"({d['phantom']} phantom, id-count runs "
               f"+{d['inflation_pct']}%)", GREY)
        else:
            kv("  Counting people, not device ids", "no events recorded", GREY)
    else:
        err("Identity", idm["error"])

    # Who those people are. Inside Growth rather than in a section of its own,
    # because a headline count of 32 active people means something different
    # depending on how many of them are sandbox installs and how many are us.
    #
    # Renders nothing until the super properties actually arrive. That absence
    # is not hidden: every name in EVENTS is reported by the liveness section
    # above, as `awaiting` while the build rolls out and in red once it is
    # overdue, so there is exactly one place that says "not yet" and it is not
    # five empty distributions here.
    sg = metrics.get("segments")
    if sg and sg["ok"] and sg["data"]["coverage"]["any"]:
        d = sg["data"]
        cov = d["coverage"]
        entry = cov["by_property"].get(cov.get("probe", COVERAGE_PROBE), {})
        pct, people_pct = entry.get("pct"), entry.get("people_pct")
        if pct is not None and pct < 95:
            # The splits below describe the covered slice only. Saying so
            # matters most when coverage is partial, which is precisely the
            # period when the old and new builds are both in the field.
            kv("  Segment coverage",
               f"{pct}% of this week's {cov['events_7d']:,} events and "
               f"{people_pct}% of its {cov['people_7d']} people carry the "
               f"super properties; the splits below describe that slice, not "
               f"all traffic", GREY)
        spread = cov.get("spread")
        if spread:
            # One loop registers all of them, so they cannot legitimately
            # disagree. Named before the splits because it says which of the
            # numbers below are reading a property the app is not sending.
            kv("  !! super properties disagree",
               f"best covered has {spread['high']} events, worst has "
               f"{spread['low']}. Behind: {', '.join(spread['behind'])}. They "
               f"are registered together, so this is a spelling mismatch or a "
               f"value that failed to compute, not a partial rollout.", RED)
        skew = cov.get("skew")
        if skew:
            # The two figures coming apart is the finding, not the level of
            # either. A build rollout moves both together; a gap this wide
            # means coverage tracks the user rather than the release, and the
            # attribute to suspect first is having a session. Reported in red
            # because the event figure on its own reads as an ordinary
            # mid-rollout number while most PEOPLE are missing.
            kv("  !! coverage is skewed toward heavy users",
               f"{skew['events_pct']}% of events but only "
               f"{skew['people_pct']}% of people ({skew['gap']} points apart). "
               f"That is what super properties attaching only to signed-in "
               f"users looks like: they are 15% of people and 60% of events. "
               f"Anonymous users are the population these exist to reach.",
               RED)
        for prop, split in d["splits"].items():
            if not split["rows"]:
                continue
            shown = ", ".join(
                f"{r['value']} {r['people']} ({r['pct']}%)"
                for r in split["rows"][:SEGMENT_VALUE_LIMIT])
            more = len(split["rows"]) - SEGMENT_VALUE_LIMIT
            if more > 0:
                shown += f", +{more} more"
            kv(f"  {prop}", shown)
    elif sg and not sg["ok"]:
        err("Segments", sg["error"])

    # Who holds Pro, and whether anybody reached it without holding it.
    # Sits with the segments because it reads the same property, and above
    # the funnel because a contradiction here invalidates any split below.
    ei = metrics.get("entitlement")
    if ei and ei["ok"] and ei["data"]["measurable"]:
        d = ei["data"]
        kv("  Pro access",
           f"{d['paid']} paid, {d['comped']} comped",
           GREEN if d["paid"] else GREY)
        if d["comped"]:
            # Not a problem, an answer. Before pro_source these people were
            # filed among free users and could not be counted at all.
            kv("  ",
               f"comped users pass every Pro gate and pay nothing, so they "
               f"belong in neither the paid nor the paywall-eligible "
               f"population. Excluded from both by reading pro_source rather "
               f"than a boolean.", GREY)
        for c in d["contradictions"]:
            kv(f"  !! {c['event']} with pro_source=none",
               f"{c['n']} events from {c['people']} people reached a Pro-only "
               f"feature without Pro. Either the gate leaked (a revenue bug) "
               f"or the stamp disagrees with what the app did (every segment "
               f"below is misfiled). Both are worth chasing; this cannot tell "
               f"them apart.", RED)
    elif ei and not ei["ok"]:
        err("Entitlement integrity", ei["error"])

    # Search rank. After Growth because a rank move is upstream of an install,
    # and before Activation, which is about what people do once they arrive.
    #
    # metrics.get, not metrics[...]: the revenue tests hand-build a metrics dict
    # without this key and a direct index would KeyError all of them.
    rk = metrics.get("rank")
    if rk:
        section("Search rank (ASO)")

        def rank_line(s, color=None):
            line(f"    {s}")
            c = f"color:{color};" if color else ""
            html(f'<div style="font-family:monospace;font-size:12px;'
                 f'margin-left:12px;{c}">{_esc(s)}</div>')

        if not rk["ok"]:
            err("Search rank", rk["error"])
        else:
            d = rk["data"]
            if d["stale"]:
                # A stopped capture must read as "no capture", never as a quiet
                # week. Nothing below this line is this week's news.
                age = d["age_days"]
                when = "never" if age is None else f"{age} days ago"
                kv("!! NO CAPTURE", f"oldest store capture is {when}; the weekly "
                                    f"job may have stopped. Anything below is "
                                    f"older news.", RED)
            for store, s in d["stores"].items():
                label = STORE_LABELS.get(store, store)
                if s["prev"] is None:
                    stale_note = ("" if s["age_days"] <= RANK_STALE_DAYS
                                  else f" ({s['age_days']} days old)")
                    kv(label, f"first capture {_stamp(s['curr'])}{stale_note}, "
                              f"nothing to compare yet",
                       GREY if s["age_days"] <= RANK_STALE_DAYS else RED)
                    continue
                fresh = s["age_days"] <= RANK_STALE_DAYS
                kv(label,
                   f"{_stamp(s['prev'])} -> {_stamp(s['curr'])}"
                   + ("" if fresh else f"  ({s['age_days']} days old)"),
                   None if fresh else RED)
                movement = 0
                for title, key, color in (("dropped", "dropped", RED),
                                          ("entered", "entered", GREEN),
                                          ("moved", "moved", None)):
                    items = s[key]
                    movement += len(items)
                    for item in items[:RANK_LIST_LIMIT]:
                        c = color
                        if key == "moved":
                            c = RED if item["delta"] > 0 else GREEN
                        rank_line(item["line"], c)
                    if len(items) > RANK_LIST_LIMIT:
                        rank_line(f"...and {len(items) - RANK_LIST_LIMIT} more "
                                  f"{title}", GREY)
                if not movement:
                    rank_line("no term moved beyond the noise band", GREY)
                counts = (f"{s['flat_n']} flat, {s['still_absent_n']} still absent")
                if s["unmeasured_n"]:
                    # DEC-249: these did not move, they were never read.
                    counts += f", {s['unmeasured_n']} NOT MEASURED"
                rank_line(counts, RED if s["unmeasured_n"] else GREY)

    # App Store discovery. Immediately after the ranks, because it is the
    # denominator for them: the rank section says where we sit in the list, and
    # this says whether the list is where our impressions come from.
    #
    # metrics.get for the same reason as rank: the revenue tests build a
    # metrics dict without this key.
    src = metrics.get("sources")
    if src:
        section("App Store discovery (search vs browse)")

        def src_line(s, color=None):
            line(f"    {s}")
            c = f"color:{color};" if color else ""
            html(f'<div style="font-family:monospace;font-size:12px;'
                 f'margin-left:12px;{c}">{_esc(s)}</div>')

        if not src["ok"]:
            err("App Store discovery", src["error"])
        else:
            d = src["data"]
            sp = d["split"]
            if d["stale"] and d.get("stale_reason") == "data":
                # The job is running. Apple has simply stopped advancing the
                # report, so the windows below are the same windows as last
                # week and the week before. Named separately from NO PULL
                # because the fix is a new report request, not a cron repair.
                age = d.get("data_age_days")
                when = "never" if age is None else f"{age} days ago"
                newest = d.get("newest_complete_date") or "no complete day"
                kv("!! SERIES FROZEN",
                   f"the weekly pull is still running, but the newest complete "
                   f"day in the series is {newest} ({when}). Apple's "
                   f"ONE_TIME_SNAPSHOT has stopped producing instances, so the "
                   f"windows below have not grown since. Nothing here is this "
                   f"week's news.", RED)
            elif d["stale"]:
                age = d["age_days"]
                when = "never" if age is None else f"{age} days ago"
                kv("!! NO PULL", f"the App Store Connect series was last "
                                 f"written {when}; the weekly job may have "
                                 f"stopped, or the ONE_TIME_SNAPSHOT has "
                                 f"stopped producing instances. Figures below "
                                 f"are older news.", RED)

            def window_lines(w):
                total = w["impressions"]
                ordered = sorted(w["by_source"].items(),
                                 key=lambda kv_: (-kv_[1]["impressions"], kv_[0]))
                for source, m in ordered[:SOURCES_LIST_LIMIT]:
                    share = (f"{m['impressions'] / total * 100:.1f}%"
                             if total else "n/a")
                    src_line(f"{source:<20} {m['impressions']:>8,} impressions "
                             f"({share})")

            kv("Data through", f"{sp['last_complete_date']} "
                               f"(the last {SOURCES_TAIL_NOTE} excluded as "
                               f"incomplete, so this is never a drop)", GREY)
            # The line above is arithmetic: pull date minus Apple's tail. It is
            # what Apple SHOULD have given us, not what we hold. They agree on a
            # healthy week and diverge the moment the report stops advancing, so
            # a divergence is printed rather than left for the reader to infer
            # from a post window that quietly never grows.
            newest = d.get("newest_complete_date")
            if newest and newest != sp["last_complete_date"]:
                kv("  Newest day actually held",
                   f"{newest}; the series is behind its own cutoff, so the "
                   f"windows below stop here", RED)

            if not sp["has_post_window"]:
                # Presented as a baseline, deliberately without a comparison.
                # A handful of partial post-rename days against months of
                # pre-rename data would render as a result and be read as one.
                kv("No post-rename window yet",
                   f"the iOS listing changed {sp['rename_date']} and no later "
                   f"day is complete. Below is the PRE-RENAME BASELINE, not a "
                   f"result.", GREY)
                w = sp["pre"]
                if w["day_count"]:
                    kv("Search share of impressions",
                       f"{_pct_or_na(w['search_share'])} across "
                       f"{w['day_count']} days "
                       f"({w['days'][0]} to {w['days'][-1]})")
                    window_lines(w)
                else:
                    kv("Baseline", "no complete days in the series yet", GREY)
            else:
                pre, post = sp["pre"], sp["post"]
                pre_share, post_share = pre["search_share"], post["search_share"]
                if pre_share is not None and post_share is not None:
                    delta = post_share - pre_share
                    # Green when search grew: search share is the metric the
                    # rename was supposed to move.
                    color = GREEN if delta >= 0 else RED
                    kv("Search share of impressions",
                       f"{pre_share}% -> {post_share}% ({delta:+.1f} points)",
                       color)
                else:
                    kv("Search share of impressions",
                       f"{_pct_or_na(pre_share)} -> {_pct_or_na(post_share)}")
                # Rates, never the two totals side by side. The windows are
                # never the same length -- on the first readable day it is 108
                # against 1 -- and the pre-rename window reaches back through
                # months when the app was near-silent, so its lifetime rate
                # understates the real baseline by more than half. Both are
                # printed: the lifetime one for scale, the trailing one as the
                # only fair thing to compare a few post-rename days against.
                recent = sp.get("pre_recent") or {}
                kv("Impressions/day",
                   f"{pre['per_day']} lifetime ({pre['day_count']}d)  ·  "
                   f"{recent.get('per_day')} over the "
                   f"{sp.get('recent_baseline_days', 28)}d before  ->  "
                   f"{post['per_day']} ({post['day_count']}d)")
                if post["day_count"] < 7:
                    kv("  Not a trend yet",
                       f"{post['day_count']} complete post-rename day(s). "
                       f"Daily impressions already ranged widely before the "
                       f"rename, so wait for a full week before reading this.",
                       GREY)
                window_lines(post)

            if sp["boundary"]["day_count"]:
                src_line(f"{sp['rename_date']} is part one listing and part the "
                         f"other; its "
                         f"{sp['boundary']['impressions']:,} impressions are in "
                         f"neither window.", GREY)

    # Store listing accuracy. Sits with discovery rather than with the product
    # sections because it is part of the same surface: the ranks say where we
    # appear, discovery says whether anyone looked, and this says whether what
    # they read when they got there was true.
    sl = metrics.get("store_listing")
    if sl:
        section("Store listing accuracy")
        if not sl["ok"]:
            err("Store listing", sl["error"])
        else:
            d = sl["data"]
            lim = d["limits"]
            if d["ok"]:
                kv("All storefronts match the app",
                   f"{len(d['listings'])} checked against "
                   f"freePlantLimit={lim['freePlantLimit']}, "
                   f"freeLocationLimit={lim['freeLocationLimit']}", GREEN)
            else:
                for entry, finding in d["failures"]:
                    kv(f"!! {entry['store']}/{entry['country']} "
                       f"{finding['rule']}", finding["detail"], RED)
                if d["divergence"]:
                    kv("!! storefronts diverge", d["divergence"], RED)
                for entry in d["unreadable"]:
                    # Not a pass. DEC-249: an absence of measurement and a
                    # clean result must not look alike.
                    kv(f"?? {entry['store']}/{entry['country']} unreadable",
                       entry["error"], RED)

    # Activation
    section("Activation")
    pl = metrics["plants"]
    if pl["ok"]:
        d = pl["data"]
        kv("Plants held (high water)",
           f"{d['plants']} across {d['owners']} people")
        if d.get("imported_adds"):
            kv("  Arrived by import",
               f"{d['imported_adds']} plants (data_imported.plants_imported), "
               f"a route plant_added has never been able to see", GREEN)
        if d["unobserved"]:
            explained = d.get("explained", d["observed_adds"])
            kv("  Never seen being added",
               f"{d['unobserved']} of {d['plants']} = {d['unobserved_pct']}% "
               f"({explained} explained: plant_added fires only from the plant "
               f"form, data_imported covers file import, and restore-from-"
               f"backup still announces nothing)", RED)
    else:
        err("Plants", pl["error"])
    lo = metrics.get("locations")
    if lo and lo["ok"]:
        d = lo["data"]
        if d["adds"] and d["capped"]:
            # Not "our users have one location". The event fired from one of
            # three creation paths, so 1 is the largest number it could ever
            # have reported. Stated as a property of the instrument, because
            # read as a property of users it is an argument against building
            # multi-location features.
            kv("Locations per person",
               f"UNREADABLE. All {d['adds']} location_added events report "
               f"exactly 1, because the event fired from 1 of 3 creation "
               f"paths. This is the instrument's ceiling, not a fact about "
               f"users. Do not trend it.", RED)
        elif d["adds"]:
            pre, post = d.get("pre") or {}, d.get("post") or {}
            kv("Locations per person",
               f"ceiling lifted {d['boundary']}: "
               f"max {pre.get('max_after', 1)} before -> "
               f"{post.get('max_after')} after "
               f"(avg {post.get('avg_after')} across {post.get('adds', 0)} "
               f"adds)")
            kv("  Step change at the fix is an artefact",
               f"the two windows are shown apart deliberately. Any series "
               f"joining them steps up on {d['boundary']} because the other "
               f"two creation paths started reporting, not because anyone "
               f"added a location.", GREY)
    elif lo and not lo["ok"]:
        err("Locations", lo["error"])

    ac = metrics["activation"]
    if ac["ok"]:
        d = ac["data"]
        rate = "n/a" if d["rate"] is None else f"{d['rate']}%"
        color = GREEN if (d["rate"] or 0) >= 25 else RED
        kv("Added a plant (new users)",
           f"{d['activated']}/{d['installs']} = {rate}", color)
        # All-time, clipped to the period plant_added has actually existed.
        # Printing the start date is the point: DEC-254 was caused by an
        # all-time rate computed over weeks the event could not fire.
        if d.get("coverage_start"):
            all_rate = ("n/a" if d.get("all_rate") is None
                        else f"{d['all_rate']}%")
            all_color = GREEN if (d.get("all_rate") or 0) >= 25 else RED
            kv(f"Added a plant (all time, since {d['coverage_start']})",
               f"{d['all_activated']}/{d['all_installs']} = {all_rate}",
               all_color)
            excluded = d.get("excluded_pre_coverage") or 0
            if excluded:
                kv("  Excluded (installed before plant_added existed)",
                   f"{excluded} people, activation unknown not zero", GREY)
    else:
        err("Activation", ac["error"])
    ob = metrics["onboarding"]
    if ob["ok"]:
        d = ob["data"]
        rate = "n/a" if d["rate"] is None else f"{d['rate']}%"
        kv("Onboarding completion", f"{d['completed']}/{d['started']} = {rate}")
    else:
        err("Onboarding", ob["error"])

    # Funnel
    section("Activation funnel (7d, distinct people)")
    fn = metrics["funnel"]
    if fn["ok"]:
        for step in fn["data"]["steps"]:
            # 4-tuples carry the event name so an uninstrumented step can say
            # WHICH kind of uninstrumented it is. Older 3-tuples still render.
            label, n, instrumented = step[0], step[1], step[2]
            event = step[3] if len(step) > 3 else None
            if instrumented:
                kv(label, str(n))
            elif event in AWAITING_FIRST_EVENT:
                # Declared and on its way. Reported grey, not red, and
                # explicitly not as a user behaviour: this step is empty
                # because the build has not landed, and calling that a
                # conversion failure is how DEC-251's phantom drop happened.
                kv(label, f"awaiting rollout (declared "
                          f"{AWAITING_FIRST_EVENT[event]}, not yet arrived). "
                          f"Not a user behaviour.", GREY)
            else:
                kv(label, "not instrumented (the app has never sent this "
                          "event, so this is not a user behaviour)", RED)
        bd = fn["data"]["biggest_drop"]
        if bd:
            msg = f"{bd[0]} -> {bd[1]}: lost {bd[2]} ({bd[3]}%)"
            line(f"  >> Biggest drop: {msg}")
            html(f'<div style="margin-top:6px;color:{RED};font-weight:bold;'
                 f'font-size:13px;">Biggest drop: {msg}</div>')
    else:
        err("Funnel", fn["error"])

    # Revenue: the receipt. This section outranks the telemetry below it.
    section("Revenue (RevenueCat, store-validated)")
    rcm = metrics["revenuecat"]
    if rcm["ok"]:
        d = rcm["data"]
        n = d["production_n"]
        proceeds = d["production_proceeds_usd"]
        # Proceeds, not gross: this is what reaches the bank after the store
        # commission and tax. Quoting gross overstates us by about a third.
        kv("Revenue ALL TIME (proceeds)", f"US${proceeds:.2f}",
           GREEN if proceeds else GREY)
        kv("Paid purchases ALL TIME", str(n), GREEN if n else GREY)
        if d.get("production_gross_usd"):
            kv("  gross before store cut",
               f"US${d['production_gross_usd']:.2f}", GREY)
        if d.get("countries"):
            kv("  buyer countries", ", ".join(d["countries"]), GREY)
        for month, m in (d.get("by_month") or {}).items():
            kv(f"  {month}", f"{m['n']} paid, US${m['proceeds']:.2f}")

        # Which platform the money comes from. A blended rate averages two
        # populations that behave nothing alike, so it is never shown alone.
        for plat, b in (d.get("platforms") or {}).items():
            kv(f"  {plat}",
               f"{b['installs']} installs, {b['buyers']} buyers "
               f"({b['rate_pct']}%), US${b['proceeds']:.2f}",
               GREEN if b["buyers"] else GREY)

        # Days from install to purchase. If this is 0 the purchase decision is
        # made before the app is used, and activation/retention work sits
        # downstream of the money rather than upstream of it.
        lags = d.get("purchase_lag_days")
        if lags:
            kv("  days install -> purchase",
               ", ".join(str(x) for x in lags)
               + ("  (all same-day)" if set(lags) == {0} else ""))
        # Excluded buckets are printed, never dropped, so a sale that does not
        # count as revenue is still visible rather than silently missing.
        for env, b in sorted((d.get("by_env") or {}).items()):
            if env != "production":
                kv(f"Excluded: {env}",
                   f"{b['n']} purchases, US${b['proceeds']:.2f}, "
                   f"not counted as revenue", GREY)

        # Independent cross-check (DEC-259): the per-customer sweep against
        # the dashboard's own 28-day gross, which is computed by RevenueCat.
        ov = d.get("overview") or {}
        if isinstance(ov.get("revenue"), (int, float)):
            kv("  RevenueCat 28d gross", f"US${ov['revenue']}", GREY)

        # Two systems count installs and they disagree. Neither is authoritative
        # (RevenueCat opens a customer per SDK init, PostHog merges aliased ids
        # onto a person), so the point is to keep the gap visible rather than to
        # pick a winner and quietly divide by it.
        ins = metrics["installs"]
        rc_c = d.get("customers")
        if ins["ok"] and rc_c:
            ph_people = ins["data"].get("all_time")
            if ph_people:
                gap = round((rc_c - ph_people) / ph_people * 100)
                kv("  installs: RevenueCat vs PostHog",
                   f"{rc_c} customers vs {ph_people} people ({gap:+d}%)",
                   GREY)

        # And against our own telemetry, which is the number every strategy
        # note before DEC-260 was reasoned from.
        pu_chk = metrics["purchases"]
        if pu_chk["ok"]:
            ph_n = sum(b["n_all"] for b in pu_chk["data"]["production"])
            if ph_n != n:
                msg = (f"RevenueCat has {n} paid purchases, PostHog "
                       f"purchase_succeeded has {ph_n}. The receipt wins; "
                       f"our own telemetry is missing {n - ph_n}.")
                line(f"  !! {msg}")
                html(f'<div style="margin-top:6px;color:{RED};'
                     f'font-size:13px;">{msg}</div>')
    else:
        err("RevenueCat", rcm["error"])

    # Monetization
    section("Paywall reach (PostHog, directional)")
    pw = metrics["paywall"]
    if pw["ok"]:
        d = pw["data"]
        kv("Paywall views (7d)", str(d["shown"]))
        kv("Paywall dismissed (7d)", str(d["dismissed"]))
    else:
        err("Paywall", pw["error"])

    pu = metrics["purchases"]
    if pu["ok"]:
        prod = pu["data"]["production"]
        # 7-day figures, then the all-time totals that cannot fall out of scope.
        n_7d = sum(b["n_7d"] for b in prod)
        kv("Purchases this week (production)", str(n_7d),
           GREEN if n_7d else GREY)
        for b in prod:
            if b["n_7d"]:
                kv(f"  {b['currency']} this week",
                   f"{b['revenue_7d']:.2f}", GREEN)

        n_all = sum(b["n_all"] for b in prod)
        kv("Purchases ALL TIME (production)", str(n_all),
           GREEN if n_all else GREY)
        for b in prod:
            kv(f"  {b['currency']} all time (gross)",
               f"{b['revenue_all']:.2f}", GREEN if b["n_all"] else GREY)
        if not prod:
            kv("  revenue all time", "none recorded", GREY)

        # Everything not counted above, so an excluded sale is still visible.
        for b in pu["data"]["buckets"]:
            if b["env"] != "production":
                kv(f"Excluded: {b['env']} ({b['currency']})",
                   f"{b['n_all']} all time, not counted as revenue", GREY)
    else:
        err("Purchases", pu["error"])

    rc = metrics["reconciliation"]
    if rc["ok"]:
        d = rc["data"]
        if not d["agrees"]:
            msg = (f"paywall_result reports {d['via_paywall']} purchases "
                   f"since 2026-07-01 but purchase_succeeded reports "
                   f"{d['via_purchase']}. One of them is dropping events, so "
                   f"treat the revenue line above as incomplete.")
            line(f"  !! {msg}")
            html(f'<div style="margin-top:6px;color:{RED};font-weight:bold;'
                 f'font-size:13px;">Purchase events disagree: {msg}</div>')
    else:
        err("Reconciliation", rc["error"])

    # Retention
    section("Retention")
    rt = metrics["retention"]
    if rt["ok"]:
        d = rt["data"]
        rate = "n/a" if d["rate"] is None else f"{d['rate']}%"
        color = GREEN if (d["rate"] or 0) >= 20 else RED
        kv("Returned 2+ days (8-14d cohort)",
           f"{d['returned']}/{d['cohort']} = {rate}", color)
    else:
        err("Retention", rt["error"])

    # Reminders. Directly after retention because that is what they are for:
    # a reminder is the app's only way to start a session it did not already
    # have, so it belongs next to the number it is supposed to move.
    rm = metrics.get("reminders")
    if rm and rm["ok"] and not _hidden_while_awaiting(
            ("reminder_created", "reminder_notification_tapped",
             "reminder_sweep"), rm["data"].get("all_time")):
        section("Reminders (7d)")
        d = rm["data"]
        kv("Reminders created", f"{d['created_total']} "
                                f"({d['scheduled_ok']} accepted by the OS)",
           GREEN if d["scheduled_ok"] else GREY)
        for b in d["blocked"][:FEATURE_LIST_LIMIT]:
            # A blocked reminder is a reminder the user asked for and will
            # never get. It is a product failure, not a usage statistic.
            kv(f"  !! {b['status']}",
               f"{b['n']} across {b['people']} people, blocker="
               f"{b['blocker']}", RED)
        kv("Notification taps", f"{d['taps_total']} "
                                f"({d['cold_taps']} cold, {d['warm_taps']} warm)")
        if d["taps_per_scheduled"] is not None:
            kv("  Taps per scheduled reminder", f"{d['taps_per_scheduled']}%")
            kv("  ", "not a share of notifications: a repeating reminder is "
                     "created once and fires many times, so this can exceed "
                     "100%. The app cannot see deliveries, so this is not "
                     "one.", GREY)
        sw = d["sweep"]
        if sw["sweeps"]:
            kv("Cold-start sweeps", f"{sw['sweeps']} across {sw['people']} people")
            kv("  left due (ignored-proxy)", str(sw["left_due"]),
               RED if sw["left_due"] else GREY)
            kv("  scheduled / already pending",
               f"{sw['scheduled']} / {sw['already_pending']}", GREY)
            if sw["blocked"] or sw["failed"]:
                kv("  !! blocked / failed",
                   f"{sw['blocked']} / {sw['failed']}", RED)
        kv("  ", REMINDER_DELIVERY_NOTE, GREY)
    elif rm and not rm["ok"]:
        section("Reminders (7d)")
        err("Reminders", rm["error"])

    # Feature usage.
    fu = metrics.get("feature_usage")
    if fu and fu["ok"]:
        d = fu["data"]
        names = tuple(d["by_event"].keys())
        ever = sum(v["all_time"] for v in d["by_event"].values())
        if not _hidden_while_awaiting(names, ever):
            section("Feature usage (7d, all time)")
            for name, v in sorted(d["by_event"].items()):
                kv(name, f"{v['n_7d']} this week across {v['people_7d']} "
                         f"people  ·  {v['all_time']} all time",
                   GREEN if v["n_7d"] else GREY)
            for g in d["grafts"][:FEATURE_LIST_LIMIT]:
                kv(f"  graft {g['type_family']} / {g['source']}",
                   f"{g['n']} ({g['with_type']} with a specific type)")
            for a in d["activities"][:FEATURE_LIST_LIMIT]:
                kv(f"  activity {a['activity_type']}",
                   f"{a['n']} ({a['created_reminder']} created a reminder, "
                   f"{a['with_notes']} with notes)")
            for b in d["bulk"][:FEATURE_LIST_LIMIT]:
                label = b["operation"] + (f" -> {b['to_status']}"
                                          if b["to_status"] else "")
                kv(f"  bulk {label}",
                   f"{b['n']} operations over {b['plants']} plants")
            for p in d["photos"][:FEATURE_LIST_LIMIT]:
                # was_last_photo is the one worth a second look: deleting the
                # last photo of a plant leaves a record with nothing to show.
                kv(f"  photo deleted ({p['category']})",
                   f"{p['n']} ({p['was_last']} were the plant's last photo, "
                   f"{p['graft_linked']} linked to a graft)",
                   RED if p["was_last"] else None)
    elif fu and not fu["ok"]:
        section("Feature usage (7d, all time)")
        err("Feature usage", fu["error"])

    # Data portability.
    dp = metrics.get("data_portability")
    if dp and dp["ok"]:
        d = dp["data"]
        ever = sum(r["all_time"] for r in d["exports"] + d["imports"])
        if not _hidden_while_awaiting(("data_exported", "data_imported"), ever):
            section("Data portability (7d)")
            kv("Exports", str(d["exports_7d"]))
            for r in d["exports"][:FEATURE_LIST_LIMIT]:
                kv(f"  {r['format']}",
                   f"{r['n_7d']} this week ({r['plants_exported_7d']} plants) "
                   f"·  {r['all_time']} all time")
            kv("Imports", f"{d['imports_7d']} "
                          f"({d['plants_imported_7d']} plants this week, "
                          f"{d['plants_imported_all']} all time)",
               GREEN if d["imports_7d"] else GREY)
            for r in d["imports"][:FEATURE_LIST_LIMIT]:
                kv(f"  {r['format']}",
                   f"{r['n_7d']} this week ({r['plants_imported_7d']} plants "
                   f"from {r['rows_imported_7d']} rows) ·  {r['all_time']} "
                   f"all time")
            if d["unconverted_rows"]:
                # Rows that did not become plants. A 400-row CSV that yields 12
                # plants is a parser or column-mapping failure, and it is
                # invisible in either number on its own.
                kv("  !! rows that became nothing",
                   f"{d['unconverted_rows']} of {d['rows_imported_7d']} rows "
                   f"({d['row_conversion_pct']}% converted). A column mapping "
                   f"or parser problem, seen from the user's side as a broken "
                   f"import.", RED)
            if d["replaced_existing"]:
                kv("  replaced an existing library",
                   f"{d['replaced_existing']} imports (counted apart: a "
                   f"replacing import overwrites rather than adds, so summing "
                   f"it with the rest would count the same plants twice)",
                   GREY)
    elif dp and not dp["ok"]:
        section("Data portability (7d)")
        err("Data portability", dp["error"])

    # Top screens
    section("Top screens (7d)")
    ts = metrics["top_screens"]
    if ts["ok"]:
        for row in ts["data"]["rows"]:
            kv(str(row[0]), str(row[1]))
    else:
        err("Top screens", ts["error"])

    # Backup health
    section("Backup health (7d)")
    bk = metrics["backup"]
    if bk["ok"]:
        d = bk["data"]
        kv("Backups completed", str(d["completed"]),
           GREEN if d["completed"] else GREY)
        if d["failed"]:
            for reason, n in d["failed"]:
                kv(f"  failed: {reason}", str(n), RED)
        else:
            kv("Backups failed", "0", GREEN)
    else:
        err("Backup", bk["error"])

    html('<p style="color:#888;font-size:11px;margin-top:16px;">'
         'Generated by dale/treesmith_analytics.py from PostHog (EU).</p>')

    text = "\n".join(t)
    html_doc = ('<div style="font-family:-apple-system,Segoe UI,Roboto,'
                'sans-serif;max-width:640px;">' + "\n".join(h) + "</div>")
    return text, html_doc


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return
    unknown = [a for a in args if a != "--dry-run"]
    if unknown:
        # Never fall through to the email path on a typo.
        print(f"Unknown argument(s): {' '.join(unknown)}\n", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    dry_run = "--dry-run" in args
    host, key = load_posthog_credentials()

    metrics = {
        "liveness": run_metric(m_event_liveness, host, key),
        "installs": run_metric(m_installs, host, key),
        "active": run_metric(m_active, host, key),
        "identity": run_metric(m_identity, host, key),
        "segments": run_metric(m_segments, host, key),
        "entitlement": run_metric(m_entitlement_integrity, host, key),
        "plants": run_metric(m_plants, host, key),
        "locations": run_metric(m_locations, host, key),
        "activation": run_metric(m_activation, host, key),
        "onboarding": run_metric(m_onboarding, host, key),
        "funnel": run_metric(m_funnel, host, key),
        "paywall": run_metric(m_paywall, host, key),
        "purchases": run_metric(m_purchases, host, key),
        "revenuecat": run_metric(m_revenuecat),
        "rank": run_metric(m_rank),
        "sources": run_metric(m_appstore_sources),
        "store_listing": run_metric(m_store_listing),
        "reconciliation": run_metric(m_purchase_reconciliation, host, key),
        "retention": run_metric(m_retention, host, key),
        "reminders": run_metric(m_reminders, host, key),
        "feature_usage": run_metric(m_feature_usage, host, key),
        "data_portability": run_metric(m_data_portability, host, key),
        "top_screens": run_metric(m_top_screens, host, key),
        "backup": run_metric(m_backup, host, key),
    }

    text, html = render(metrics)

    if dry_run:
        print(text)
        return

    # Email via the shared dale helper.
    sys.path.insert(0, SCRIPT_DIR)
    from notify import send_email  # noqa: E402 - VPS-only import path

    ok = send_email("TreeSmith Weekly", html, text)
    if not ok:
        print("Email send failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
