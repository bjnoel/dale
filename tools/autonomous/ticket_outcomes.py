#!/usr/bin/env python3
"""Close the loop on ticket outcomes.

Every Dale ticket ends with a trailer naming the metric it expects to move:

    `L2 · treesmith_downloads`

Until now nothing read it. `docs/ticket-format.md` said so outright: "Nothing
parses it; it is there so Benedict can see the altitude at a glance." So Dale
stated an intended outcome on roughly sixty tickets and was never once graded
against one, and Benedict got a stream of "done" with no way to tell which of
them mattered.

This module is the missing half:

  record    For each ticket completed in the last 24h, parse the trailer and
            stamp the metric's current value as a baseline, with a due date
            28 days out.
  verdict   For each record now due, re-read the metric, classify the change,
            post it as a comment on the original ticket, and leave it in the
            store for the daily digest to surface.
  show      Print the store as JSON (digest + debugging).

The baseline is read *at completion*, so it describes the 28 days leading up to
the change and the verdict describes the 28 days after it. That is a real
before/after, but it is emphatically **correlation, not attribution**: other
work ships in the same window, and seasonality moves nursery traffic on its
own. Every verdict says so in as many words. The point is not to prove Dale
caused something, it is to stop "shipped" from being the last word.

Usage:
  python3 ticket_outcomes.py record [--dry-run]
  python3 ticket_outcomes.py verdict [--dry-run]
  python3 ticket_outcomes.py show [--due-only]
"""

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

# How long to wait before grading a ticket. Four weeks: long enough for a
# content or SEO change to show up in Search Console at all, short enough that
# the answer still informs the next decision. DAL-257 picked the same horizon by
# hand ("re-measure 4 weeks after the rename"), which is the behaviour this
# automates.
VERDICT_HORIZON_DAYS = 28

# Comparison window for flow metrics (visitors, downloads, revenue).
WINDOW_DAYS = 28

# Below this relative change, call it flat. Treestock month-over-month visitors
# swing by more than this on season alone, so a smaller move is not evidence of
# anything.
FLAT_BAND_PCT = 10.0

# Below this absolute value, a percentage is theatre: 1 -> 2 subscribers is
# +100% and means nothing. Report the raw numbers and decline to call it.
MIN_ABS_FOR_PCT = 10

STORE_FILENAME = "ticket-outcomes.json"


class MetricUnavailable(Exception):
    """The metric could not be read. Distinct from "the metric is zero".

    Conflating the two is the DEC-236 mistake in another costume: a failed read
    that returns 0 produces a confident "declined 100%" verdict on a ticket that
    may have worked perfectly.
    """


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "cron.log"), "a") as f:
        f.write(f"{ts} ticket-outcomes: {msg}\n")


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def data_dir():
    return load_config().get("paths", {}).get("data", "/opt/dale/data")


def repo_dir():
    """Resolve the repo, working both on the server and in a dev checkout."""
    configured = load_config().get("paths", {}).get("repo")
    if configured and os.path.isdir(configured):
        return configured
    return os.path.dirname(os.path.dirname(SCRIPT_DIR))


def store_path():
    return os.path.join(data_dir(), STORE_FILENAME)


# ---------------------------------------------------------------------------
# Trailer parsing
# ---------------------------------------------------------------------------

# `L2 · treesmith_downloads`. The separator is a middle dot in the documented
# format, but hyphens and pipes show up in hand-written tickets, so accept them.
TRAILER_RE = re.compile(
    r"`\s*L(?P<level>[0-3])\s*[·|\-–—:]\s*(?P<metric>[^`]+?)\s*`"
)


def parse_trailer(description):
    """Return (level, metric) from a ticket description, or (None, None).

    Takes the LAST trailer in the body: the format puts it at the bottom, and a
    description that quotes the format in passing (the cap error message does)
    should not shadow the real one.
    """
    if not description:
        return None, None
    matches = list(TRAILER_RE.finditer(description))
    if not matches:
        return None, None
    m = matches[-1]
    metric = " ".join(m.group("metric").split())
    return f"L{m.group('level')}", metric


def normalise_metric(metric):
    """Map a trailer's metric text to a registry key, or None if it is prose.

    Trailers carry two different things. Most name a metric we can actually
    read (`treesmith_downloads`). Some name an intention (`nursery
    relationships`, `unblocks DEC-248 step 3`, `protects every other metric`).
    The second kind is not a defect and should not be forced into a number, but
    it cannot be graded either, and the digest says so.
    """
    if not metric:
        return None
    key = re.sub(r"[^a-z0-9]+", "_", metric.strip().lower()).strip("_")
    return key if key in METRIC_READERS else None


# ---------------------------------------------------------------------------
# Metric registry
# ---------------------------------------------------------------------------

def _window(end_date, days=WINDOW_DAYS):
    """(start, end) ISO dates for a `days`-long window ending on end_date."""
    end = end_date - timedelta(days=1)          # yesterday: today is partial
    start = end - timedelta(days=days - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def read_treestock_organic_visitors(end_date):
    """Organic-search visitors to treestock.com.au over the window."""
    sys.path.insert(0, SCRIPT_DIR)
    try:
        from traffic_report import load_plausible_config, plausible_get
    except ImportError as e:
        raise MetricUnavailable(f"traffic_report import failed: {e}")

    try:
        token, base_url = load_plausible_config()
    except (FileNotFoundError, ValueError) as e:
        raise MetricUnavailable(f"Plausible not configured: {e}")

    start, end = _window(end_date)
    params = {
        "site_id": "treestock.com.au",
        "period": "custom",
        "date": f"{start},{end}",
        "metrics": "visitors",
    }

    # Organic only where the API supports it. Falling back to all-sources is
    # better than no reading, but it changes what the number means, so the note
    # travels with the value rather than being dropped.
    note = "organic search only"
    data = plausible_get(base_url, token, "/api/v1/stats/aggregate",
                         {**params, "filters": "visit:channel==Organic Search"})
    if data is None or "results" not in data:
        note = "all sources (organic filter unavailable)"
        data = plausible_get(base_url, token, "/api/v1/stats/aggregate", params)
    if data is None or "results" not in data:
        raise MetricUnavailable("Plausible returned no results")

    value = data["results"].get("visitors", {}).get("value")
    if value is None:
        raise MetricUnavailable("Plausible response had no visitors value")
    return int(value), "visitors/28d", note


def read_treesmith_downloads(end_date):
    """First-seen devices in the window, from PostHog."""
    sys.path.insert(0, SCRIPT_DIR)
    try:
        from treesmith_analytics import hogql, load_posthog_credentials
    except ImportError as e:
        raise MetricUnavailable(f"treesmith_analytics import failed: {e}")

    try:
        host, key = load_posthog_credentials()
    except (FileNotFoundError, ValueError) as e:
        raise MetricUnavailable(f"PostHog not configured: {e}")

    start, end = _window(end_date)
    try:
        rows = hogql(host, key, f"""
            WITH firsts AS (
              SELECT distinct_id, min(timestamp) AS first_seen
              FROM events GROUP BY distinct_id
            )
            SELECT count() FROM firsts
            WHERE first_seen >= toDateTime('{start} 00:00:00')
              AND first_seen <  toDateTime('{end} 23:59:59')
        """)
    except Exception as e:  # noqa: BLE001 - any transport failure is unavailable
        raise MetricUnavailable(f"PostHog query failed: {str(e)[:150]}")

    if not rows or not rows[0]:
        raise MetricUnavailable("PostHog returned no rows")
    return int(rows[0][0]), "installs/28d", "first-seen device ids"


def read_revenue_monthly(end_date):
    """Revenue booked in the ledger over the window.

    Deliberately the ledger and not PostHog `purchase_succeeded`. Q48 and
    DEC-252 turned on exactly this distinction: client-side telemetry is not a
    receipt, and a verdict that grades revenue off telemetry would re-import the
    error the ledger exists to keep out.
    """
    path = os.path.join(repo_dir(), "financials", "ledger.json")
    try:
        with open(path) as f:
            ledger = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise MetricUnavailable(f"ledger unreadable: {e}")

    start, end = _window(end_date)
    total = 0.0
    for entry in ledger.get("entries", []):
        if entry.get("type") != "revenue":
            continue
        day = str(entry.get("date", ""))[:10]
        if start <= day <= end:
            total += float(entry.get("amount", 0) or 0)
    return round(total, 2), f"{ledger.get('currency', 'AUD')}/28d", "booked in ledger"


def read_treestock_subscribers(end_date):
    """Confirmed subscriber count (a stock, read at the moment of the check)."""
    path = os.path.join(data_dir(), "subscribers.json")
    try:
        with open(path) as f:
            subs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise MetricUnavailable(f"subscribers.json unreadable: {e}")
    return len(subs), "subscribers", "point-in-time count"


def read_treestock_subscriber_engagement(end_date):
    """Variety watches on file: the one engagement action a subscriber takes."""
    path = os.path.join(data_dir(), "variety_watches.db")
    if not os.path.exists(path):
        raise MetricUnavailable("variety_watches.db not found")
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        count = con.execute("SELECT COUNT(*) FROM watches").fetchone()[0]
        con.close()
    except sqlite3.Error as e:
        raise MetricUnavailable(f"variety_watches.db unreadable: {e}")
    return int(count), "variety watches", "point-in-time count"


# Keys are the normalised metric names Dale already uses in trailers, measured
# across the open board on 2026-08-06. Adding a metric is one entry here; an
# unknown name degrades to "named a metric we cannot read", never to a number.
METRIC_READERS = {
    "treestock_organic_visitors": read_treestock_organic_visitors,
    "treesmith_downloads": read_treesmith_downloads,
    "revenue_monthly": read_revenue_monthly,
    "treestock_subscribers": read_treestock_subscribers,
    "treestock_subscriber_engagement": read_treestock_subscriber_engagement,
}


def read_metric(key, end_date=None):
    """Read a registry metric. Returns (value, unit, note). Raises on failure."""
    if end_date is None:
        end_date = datetime.now(timezone.utc).date()
    reader = METRIC_READERS.get(key)
    if reader is None:
        raise MetricUnavailable(f"no reader for metric '{key}'")
    return reader(end_date)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify(baseline, current):
    """Grade a change. Returns (call, pct) where pct may be None.

    Calls:
      moved       up by more than the flat band
      declined    down by more than the flat band
      flat        inside the band
      too-small   both readings below MIN_ABS_FOR_PCT, so a ratio is noise
    """
    if baseline is None or current is None:
        return "unmeasured", None

    if abs(baseline) < MIN_ABS_FOR_PCT and abs(current) < MIN_ABS_FOR_PCT:
        return "too-small", None

    if baseline == 0:
        return ("moved", None) if current > 0 else ("flat", None)

    pct = round((current - baseline) / abs(baseline) * 100, 1)
    if pct > FLAT_BAND_PCT:
        return "moved", pct
    if pct < -FLAT_BAND_PCT:
        return "declined", pct
    return "flat", pct


CALL_LABEL = {
    "moved": "moved",
    "declined": "went the wrong way",
    "flat": "did not move",
    "too-small": "too small to call",
    "unmeasured": "could not be measured",
}


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

def load_store(path=None):
    path = path or store_path()
    try:
        with open(path) as f:
            store = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"version": 1, "records": []}
    store.setdefault("records", [])
    return store


def save_store(store, path=None):
    path = path or store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(store, f, indent=2)
    os.replace(tmp, path)


def find_record(store, ticket):
    for r in store["records"]:
        if r.get("ticket") == ticket:
            return r
    return None


# ---------------------------------------------------------------------------
# Linear access
# ---------------------------------------------------------------------------

def _linear():
    sys.path.insert(0, SCRIPT_DIR)
    from linear_poller import LinearAPIError, get_team_id, graphql
    return graphql, get_team_id, LinearAPIError


def fetch_recently_completed(hours=24):
    """Tickets completed in the last `hours`, with descriptions."""
    graphql, get_team_id, _ = _linear()
    team_name = load_config().get("linear", {}).get("team", "Dale")
    team_id = get_team_id(team_name)
    if not team_id:
        raise MetricUnavailable(f"Linear team '{team_name}' not found")

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    data = graphql("""
        query($teamId: ID!) {
            issues(
                filter: {
                    team: { id: { eq: $teamId } }
                    state: { type: { eq: "completed" } }
                }
                orderBy: updatedAt
                first: 50
            ) {
                nodes { identifier title description completedAt }
            }
        }
    """, {"teamId": team_id})

    out = []
    for node in data["issues"]["nodes"]:
        completed_at = node.get("completedAt") or ""
        if completed_at and completed_at >= since:
            out.append(node)
    return out


def post_comment(ticket, body):
    graphql, _, _ = _linear()
    sys.path.insert(0, SCRIPT_DIR)
    from linear_update import get_issue_id
    issue_id = get_issue_id(ticket)
    graphql("""
        mutation($issueId: String!, $body: String!) {
            commentCreate(input: { issueId: $issueId, body: $body }) {
                comment { id }
            }
        }
    """, {"issueId": issue_id, "body": body})


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------

def cmd_record(args):
    dry_run = "--dry-run" in args
    store = load_store()
    today = datetime.now(timezone.utc).date()

    try:
        completed = fetch_recently_completed()
    except Exception as e:  # noqa: BLE001
        log(f"record: could not fetch completed tickets: {e}")
        print(f"Error: {e}", file=sys.stderr)
        return 1

    added, skipped = [], []
    for node in completed:
        ticket = node["identifier"]
        if find_record(store, ticket):
            skipped.append(ticket)
            continue

        level, metric_text = parse_trailer(node.get("description"))
        key = normalise_metric(metric_text)

        record = {
            "ticket": ticket,
            "title": node.get("title", ""),
            "level": level,
            "metric_text": metric_text,
            "metric": key,
            "completed_at": node.get("completedAt"),
            "verdict_due": (today + timedelta(days=VERDICT_HORIZON_DAYS)).isoformat(),
            "baseline": None,
            "verdict": None,
        }

        if key:
            try:
                value, unit, note = read_metric(key, today)
                record["baseline"] = {
                    "value": value, "unit": unit, "note": note,
                    "read_at": today.isoformat(),
                }
            except MetricUnavailable as e:
                # No baseline means no verdict is possible later. Say so now,
                # rather than storing a null that reads as zero in 28 days.
                record["baseline_error"] = str(e)
                log(f"record: {ticket} baseline unavailable: {e}")

        store["records"].append(record)
        added.append(record)

    if dry_run:
        print(json.dumps(added, indent=2))
        print(f"(dry run) would add {len(added)}, already tracked {len(skipped)}",
              file=sys.stderr)
        return 0

    if added:
        save_store(store)
    log(f"record: added {len(added)}, already tracked {len(skipped)}")
    for r in added:
        base = r.get("baseline")
        shown = f"{base['value']} {base['unit']}" if base else (
            r.get("baseline_error") or "no readable metric")
        print(f"{r['ticket']}: {r['metric'] or r['metric_text'] or '(no trailer)'} = {shown}")
    return 0


# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------

def build_verdict_comment(record, verdict):
    """The comment posted back on the graded ticket."""
    base = record["baseline"]
    call = verdict["call"]
    lines = [
        f"**Outcome check, {VERDICT_HORIZON_DAYS} days on.**",
        "",
        f"This ticket said it would move `{record['metric']}`.",
        "",
        f"- At completion ({base['read_at']}): **{base['value']}** {base['unit']}",
        f"- Now ({verdict['settled_at'][:10]}): **{verdict['value']}** {base['unit']}",
    ]
    if verdict["pct"] is not None:
        delta = verdict["value"] - base["value"]
        lines.append(f"- Change: **{delta:+g}** ({verdict['pct']:+.1f}%)")
    lines += [
        "",
        f"**Verdict: {CALL_LABEL[call]}.**",
        "",
        "Correlation over a 28-day window, not attribution. Other work shipped in "
        "the same period and nursery traffic is seasonal, so this says what "
        "happened, not what caused it. Recorded automatically by "
        "`ticket_outcomes.py`.",
    ]
    return "\n".join(lines)


def due_records(store, today=None):
    """Records whose verdict is due and not yet settled."""
    today = today or datetime.now(timezone.utc).date()
    out = []
    for r in store["records"]:
        if r.get("verdict"):
            continue
        if not r.get("baseline"):
            continue
        try:
            due = datetime.strptime(r["verdict_due"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if due <= today:
            out.append(r)
    return out


def cmd_verdict(args):
    dry_run = "--dry-run" in args
    store = load_store()
    today = datetime.now(timezone.utc).date()
    due = due_records(store, today)

    if not due:
        log("verdict: nothing due")
        print("Nothing due.")
        return 0

    settled = []
    for record in due:
        try:
            value, _unit, _note = read_metric(record["metric"], today)
        except MetricUnavailable as e:
            # Leave it due. A metric that is unreadable today is often readable
            # tomorrow, and a permanent "unmeasured" verdict would bury the
            # ticket for good.
            log(f"verdict: {record['ticket']} deferred, {e}")
            continue

        call, pct = classify(record["baseline"]["value"], value)
        verdict = {
            "settled_at": datetime.now(timezone.utc).isoformat(),
            "value": value,
            "pct": pct,
            "call": call,
        }
        record["verdict"] = verdict
        settled.append(record)

        body = build_verdict_comment(record, verdict)
        if dry_run:
            print(f"--- {record['ticket']} ---\n{body}\n")
        else:
            try:
                post_comment(record["ticket"], body)
            except Exception as e:  # noqa: BLE001
                log(f"verdict: {record['ticket']} comment failed: {e}")
                print(f"Warning: comment on {record['ticket']} failed: {e}",
                      file=sys.stderr)

    if not dry_run and settled:
        save_store(store)
    log(f"verdict: settled {len(settled)} of {len(due)} due")
    for r in settled:
        print(f"{r['ticket']}: {r['metric']} {CALL_LABEL[r['verdict']['call']]}")
    return 0


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

def recent_verdicts(store, days=1, today=None):
    """Verdicts settled in the last `days` days, newest first (for the digest)."""
    today = today or datetime.now(timezone.utc).date()
    cutoff = (today - timedelta(days=days)).isoformat()
    out = [r for r in store["records"]
           if r.get("verdict") and r["verdict"].get("settled_at", "") >= cutoff]
    return sorted(out, key=lambda r: r["verdict"]["settled_at"], reverse=True)


def pending_summary(store, today=None):
    """Counts for the digest: how much is awaiting a verdict, and how much
    shipped without naming a readable metric."""
    today = today or datetime.now(timezone.utc).date()
    awaiting = [r for r in store["records"] if not r.get("verdict") and r.get("baseline")]
    ungraded = [r for r in store["records"] if not r.get("baseline")]
    return {
        "awaiting": len(awaiting),
        "ungraded": len(ungraded),
        "next_due": min((r["verdict_due"] for r in awaiting), default=None),
    }


def cmd_show(args):
    store = load_store()
    if "--due-only" in args:
        print(json.dumps(due_records(store), indent=2))
    else:
        print(json.dumps(store, indent=2))
    return 0


COMMANDS = {"record": cmd_record, "verdict": cmd_verdict, "show": cmd_show}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: ticket_outcomes.py <{'|'.join(COMMANDS)}> [--dry-run]",
              file=sys.stderr)
        return 1
    return COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
