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

import json
import os
import sys
import urllib.error
import urllib.request

PROJECT_ID = 166160
DEFAULT_HOST = "https://eu.posthog.com"
SECRETS_DIR = "/opt/dale/secrets"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


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
          SELECT distinct_id, min(timestamp) AS first_seen
          FROM events GROUP BY distinct_id
        )
        SELECT
          countIf(first_seen >= now() - INTERVAL 7 DAY) AS this_week,
          countIf(first_seen >= now() - INTERVAL 14 DAY
                  AND first_seen < now() - INTERVAL 7 DAY) AS prev_week
        FROM firsts
    """)
    this_week = rows[0][0] if rows else 0
    prev_week = rows[0][1] if rows else 0
    return {"this_week": this_week, "prev_week": prev_week,
            "delta": pct_delta(this_week, prev_week)}


def m_active(host, key):
    """Active devices in the last 7 / 28 days."""
    rows = hogql(host, key, """
        SELECT
          count(DISTINCT if(timestamp >= now() - INTERVAL 7 DAY,
                            distinct_id, NULL)) AS w,
          count(DISTINCT if(timestamp >= now() - INTERVAL 28 DAY,
                            distinct_id, NULL)) AS m
        FROM events WHERE timestamp >= now() - INTERVAL 28 DAY
    """)
    return {"wau": rows[0][0] if rows else 0,
            "mau": rows[0][1] if rows else 0}


def m_activation(host, key):
    """How many new devices added a plant, this week and all time.

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
          SELECT distinct_id, min(timestamp) AS first_seen
          FROM events GROUP BY distinct_id
        ),
        activated AS (
          SELECT DISTINCT distinct_id FROM events WHERE event = 'plant_added'
        )
        SELECT
          countIf(first_seen >= now() - INTERVAL 7 DAY) AS installs_7d,
          countIf(first_seen >= now() - INTERVAL 7 DAY
                  AND distinct_id IN (SELECT distinct_id FROM activated)) AS activated_7d,
          countIf(first_seen >= toDate({start})) AS installs_all,
          countIf(first_seen >= toDate({start})
                  AND distinct_id IN (SELECT distinct_id FROM activated)) AS activated_all,
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
    """Onboarding starts vs completes in the last 7 days."""
    rows = hogql(host, key, """
        SELECT
          countIf(event = 'onboarding_started') AS started,
          countIf(event = 'onboarding_completed') AS completed
        FROM events
        WHERE timestamp >= now() - INTERVAL 7 DAY
          AND event IN ('onboarding_started', 'onboarding_completed')
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
        ("opened", "Application Opened"),
        ("onboarded", "onboarding_completed"),
        ("plant_added", "plant_added"),
        ("activity_logged", "activity_logged"),
    ]
    counts = []
    for label, event in steps:
        rows = hogql(host, key, f"""
            SELECT count(DISTINCT distinct_id) FROM events
            WHERE event = '{event}'
              AND timestamp >= now() - INTERVAL 7 DAY
        """)
        counts.append((label, rows[0][0] if rows else 0))
    # Biggest absolute drop between consecutive steps.
    biggest = None
    for i in range(1, len(counts)):
        prev_label, prev_n = counts[i - 1]
        cur_label, cur_n = counts[i]
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
          SELECT distinct_id,
                 min(timestamp) AS first_seen,
                 count(DISTINCT toDate(timestamp)) AS active_days
          FROM events GROUP BY distinct_id
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
         'all-time so a sale cannot age out. Client-side and directional: '
         'RevenueCat is the source of truth. Only environment=production '
         'counts as revenue.</p>')

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
        kv("Active devices (7d / 28d)",
           f"{a['data']['wau']} / {a['data']['mau']}")
    else:
        err("Active devices", a["error"])

    # Activation
    section("Activation")
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
                   f"{excluded} devices, activation unknown not zero", GREY)
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
    section("Activation funnel (7d, distinct devices)")
    fn = metrics["funnel"]
    if fn["ok"]:
        for label, n in fn["data"]["steps"]:
            kv(label, str(n))
        bd = fn["data"]["biggest_drop"]
        if bd:
            msg = f"{bd[0]} -> {bd[1]}: lost {bd[2]} ({bd[3]}%)"
            line(f"  >> Biggest drop: {msg}")
            html(f'<div style="margin-top:6px;color:{RED};font-weight:bold;'
                 f'font-size:13px;">Biggest drop: {msg}</div>')
    else:
        err("Funnel", fn["error"])

    # Monetization
    section("Monetization (directional - verify in RevenueCat)")
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
        "installs": run_metric(m_installs, host, key),
        "active": run_metric(m_active, host, key),
        "activation": run_metric(m_activation, host, key),
        "onboarding": run_metric(m_onboarding, host, key),
        "funnel": run_metric(m_funnel, host, key),
        "paywall": run_metric(m_paywall, host, key),
        "purchases": run_metric(m_purchases, host, key),
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
