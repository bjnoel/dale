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

Schedule (VPS crontab, Monday 00:00 UTC = Monday 08:00 AWST):
    0 0 * * 1 /opt/dale/autonomous/treesmith_analytics.py \
        >> /opt/dale/autonomous/logs/treesmith_analytics.log 2>&1

Setup: create /opt/dale/secrets/posthog.env with
    POSTHOG_API_KEY=phx_...
    POSTHOG_HOST=https://eu.posthog.com   (optional; defaults to EU)
Locally it falls back to ~/.posthog/credentials.json (the PostHog CLI's file).

Revenue note: PostHog purchase/paywall events are CLIENT-SIDE and include
sandbox/TestFlight activity. RevenueCat is the source of truth for real
revenue. This digest filters monetization to environment='production' where
the event carries it, but still labels those numbers "directional".
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
    """Of devices first seen in the last 7 days, how many added a plant?"""
    rows = hogql(host, key, """
        WITH cohort AS (
          SELECT distinct_id, min(timestamp) AS first_seen
          FROM events GROUP BY distinct_id
          HAVING first_seen >= now() - INTERVAL 7 DAY
        )
        SELECT
          count() AS installs,
          countIf(distinct_id IN (
            SELECT DISTINCT distinct_id FROM events
            WHERE event = 'plant_added'
          )) AS activated
        FROM cohort
    """)
    installs = rows[0][0] if rows else 0
    activated = rows[0][1] if rows else 0
    rate = round(activated / installs * 100) if installs else None
    return {"installs": installs, "activated": activated, "rate": rate}


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


def m_paywall(host, key):
    """Paywall views and outcomes (last 7 days), production-only where tagged.

    `environment` may be absent on older events; we treat missing as
    production so we don't silently hide everything, but the digest still
    labels purchase counts as directional.
    """
    rows = hogql(host, key, """
        SELECT
          countIf(event = 'paywall_shown') AS shown,
          countIf(event = 'paywall_result'
                  AND properties.outcome IN
                    ('lifetime_purchased','annual_purchased',
                     'cloud_backup_sub_purchased','cloud_backup_resubscribed')
                  AND coalesce(properties.environment, 'production')
                      = 'production') AS purchased_prod,
          countIf(event = 'paywall_result'
                  AND properties.outcome IN
                    ('lifetime_purchased','annual_purchased',
                     'cloud_backup_sub_purchased','cloud_backup_resubscribed')
                  AND properties.environment = 'sandbox') AS purchased_sandbox
        FROM events
        WHERE timestamp >= now() - INTERVAL 7 DAY
          AND event IN ('paywall_shown', 'paywall_result')
    """)
    shown = rows[0][0] if rows else 0
    prod = rows[0][1] if rows else 0
    sandbox = rows[0][2] if rows else 0
    return {"shown": shown, "purchased_prod": prod,
            "purchased_sandbox": sandbox}


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
         'Last 7 days. Revenue = RevenueCat (source of truth); paywall/'
         'purchase counts here are client-side, sandbox-excluded, '
         'directional only.</p>')

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
        kv("Paywall views", str(d["shown"]))
        kv("Purchases (production)", str(d["purchased_prod"]),
           GREEN if d["purchased_prod"] else GREY)
        kv("Purchases (sandbox, excluded)", str(d["purchased_sandbox"]), GREY)
    else:
        err("Paywall", pw["error"])

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
    dry_run = "--dry-run" in sys.argv
    host, key = load_posthog_credentials()

    metrics = {
        "installs": run_metric(m_installs, host, key),
        "active": run_metric(m_active, host, key),
        "activation": run_metric(m_activation, host, key),
        "onboarding": run_metric(m_onboarding, host, key),
        "funnel": run_metric(m_funnel, host, key),
        "paywall": run_metric(m_paywall, host, key),
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
