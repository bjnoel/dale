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
}

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

    Two failure modes, deliberately reported apart because they need different
    fixes:

      silent      the name has real history and nothing recent. Renamed, or the
                  code path that fired it was removed.
      never_seen  the name has never appeared at all. A typo in EVENTS, or an
                  event we planned and never shipped.

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
    return {"silent": silent,
            "never_seen": [n for n in names if n not in seen]}


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
    unobserved = max(plants - observed, 0)
    return {
        "owners": owners,
        "plants": plants,
        "observed_adds": observed,
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

    Reads the welcome-screen events, NOT the retired onboarding_* pair. See
    EVENTS for what happened when this queried the old names.
    """
    started_event = EVENTS["welcome_shown"]
    completed_event = EVENTS["welcome_completed"]
    rows = hogql(host, key, f"""
        SELECT
          countIf(event = '{started_event}') AS started,
          countIf(event = '{completed_event}') AS completed
        FROM events
        WHERE timestamp >= now() - INTERVAL 7 DAY
          AND event IN ('{started_event}', '{completed_event}')
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
        rows = hogql(host, key, f"""
            SELECT count(DISTINCT if(timestamp >= now() - INTERVAL 7 DAY,
                                     person_id, NULL)) AS people_7d,
                   count() AS all_time
            FROM events WHERE event = '{event}'
        """)
        people_7d = rows[0][0] if rows else 0
        all_time = rows[0][1] if rows else 0
        # An event no code path has ever emitted reads as a step nobody
        # reached. `activity_logged` is the live example: the app declares
        # captureActivityLogged and never calls it, so this step sat at 0
        # while the digest blamed the users. Carry whether the step is
        # measurable at all, so the render and the drop calculation can both
        # refuse to treat "not instrumented" as "nobody did it".
        counts.append((label, people_7d, all_time > 0))

    # Biggest absolute drop between consecutive INSTRUMENTED steps. A step we
    # cannot see is skipped rather than scored: a 100% drop into an event that
    # has never existed is a fact about our telemetry, not about the funnel,
    # and printing it in red trains the reader to ignore the line that matters.
    measurable = [(label, n) for label, n, ok in counts if ok]
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
    return {
        "path": path,
        "split": split,
        "age_days": age,
        "stale": age is None or age > SOURCES_STALE_DAYS,
    }


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


# ── Rendering ────────────────────────────────────────────────────────────────

GREEN = "#2e7d32"
RED = "#c62828"
GREY = "#888"


STORE_LABELS = {"appstore": "iOS", "play": "Play"}
RANK_LIST_LIMIT = 5  # per bucket per store. The digest reports movement, and a
                     # 36-line table is a table nobody reads.


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
        if d["silent"] or d["never_seen"]:
            section("Event liveness")
            for s in d["silent"]:
                ago = ("" if s["days_ago"] is None
                       else f" ({s['days_ago']}d ago)")
                kv(s["event"],
                   f"SILENT. Last seen {s['last_seen']}{ago}, "
                   f"{s['all_time']} events historically. Renamed or dropped? "
                   f"Any metric reading it is showing zero.", RED)
            for name in d["never_seen"]:
                kv(name,
                   "never seen. Typo in EVENTS, or an event that never shipped.",
                   RED)
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
            if d["stale"]:
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

    # Activation
    section("Activation")
    pl = metrics["plants"]
    if pl["ok"]:
        d = pl["data"]
        kv("Plants held (high water)",
           f"{d['plants']} across {d['owners']} people")
        if d["unobserved"]:
            kv("  Never seen being added",
               f"{d['unobserved']} of {d['plants']} = {d['unobserved_pct']}% "
               f"(plant_added fires only from the plant form, "
               f"not on import or restore)", RED)
    else:
        err("Plants", pl["error"])
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
        for label, n, instrumented in fn["data"]["steps"]:
            if instrumented:
                kv(label, str(n))
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
        "plants": run_metric(m_plants, host, key),
        "activation": run_metric(m_activation, host, key),
        "onboarding": run_metric(m_onboarding, host, key),
        "funnel": run_metric(m_funnel, host, key),
        "paywall": run_metric(m_paywall, host, key),
        "purchases": run_metric(m_purchases, host, key),
        "revenuecat": run_metric(m_revenuecat),
        "rank": run_metric(m_rank),
        "sources": run_metric(m_appstore_sources),
        "reconciliation": run_metric(m_purchase_reconciliation, host, key),
        "retention": run_metric(m_retention, host, key),
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
