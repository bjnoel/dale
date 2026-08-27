#!/usr/bin/env python3
"""Multi-site traffic report: Plausible analytics + Google Search Console.

Generates a structured JSON report covering all Dale sites, used by notify.py
to render the traffic dashboard in the daily email.

Usage:
    python3 traffic_report.py
    python3 traffic_report.py --output /opt/dale/data/traffic_report.json
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

SECRETS_DIR = "/opt/dale/secrets"

# beestock.com.au (discontinued 2026-07-23, DEC-230) and walkthrough.au (paused
# 2026-04-27) were dropped 2026-08-24 at Benedict's request: neither is being
# worked on, so their rows were four numbers a week nobody could act on.
# treesmith.app took their place as the Track A web companion.
PLAUSIBLE_SITES = [
    "treestock.com.au",
    "treesmith.app",
    "vergeside.com.au",
    "bjnoel.com",
    "mushroom.guide",
]

GSC_SITES = [
    "sc-domain:treestock.com.au",
    "sc-domain:treesmith.app",
    "sc-domain:vergeside.com.au",
    "sc-domain:bjnoel.com",
    "sc-domain:mushroom.guide",
    "sc-domain:scion.exchange",
    "sc-domain:wanatca.org.au",
]

GSC_CREDENTIALS_PATH = "/opt/dale/secrets/gsc-credentials.json"
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# Benedict's personal OAuth token used to serve the properties the service
# account could not see. It served exactly one, treesmith.app, until he granted
# the service account Full on it (2026-08-24, both credentials then returning
# the same 15 days / 2 clicks / 119 impressions). The token is being revoked, so
# the second code path went with it. What the fallback was really for was
# diagnosis, and warn_on_unreadable_sites does that better: it names the
# unreadable property instead of quietly routing around it.

# Permission levels that can actually read search analytics. Anything else, or a
# property missing from the credential's list entirely, 403s on the analytics
# query. gsc_query catches every exception and returns [], and the caller turns
# [] into zeros, so the 403 lands in the cron log while the report and the admin
# snapshot record 0 clicks with nothing next to them saying why.
GSC_READABLE_PERMISSIONS = {"siteOwner", "siteFullUser", "siteRestrictedUser"}


# --- Plausible helpers ---

def load_plausible_config():
    env_path = os.path.join(SECRETS_DIR, "plausible.env")
    config = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                config[key] = val
    token = config.get("PLAUSIBLE_API_TOKEN")
    url = config.get("PLAUSIBLE_URL", "https://data.bjnoel.com")
    if not token:
        raise ValueError("PLAUSIBLE_API_TOKEN not found in plausible.env")
    return token, url.rstrip("/")


def plausible_get(base_url, token, endpoint, params=None):
    url = f"{base_url}{endpoint}"
    if params:
        query = "&".join(
            f"{k}={urllib.request.quote(str(v))}" for k, v in params.items()
        )
        url += f"?{query}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "dale-traffic-report/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        print(f"Plausible error for {params.get('site_id', '?')}: {e}", file=sys.stderr)
        return None


def get_plausible_aggregate(base_url, token, site_id, start_date, end_date):
    """Get visitors + pageviews for a date range."""
    data = plausible_get(base_url, token, "/api/v1/stats/aggregate", {
        "site_id": site_id,
        "period": "custom",
        "date": f"{start_date},{end_date}",
        "metrics": "visitors,pageviews",
    })
    if data and "results" in data:
        r = data["results"]
        return {
            "visitors": r.get("visitors", {}).get("value", 0),
            "pageviews": r.get("pageviews", {}).get("value", 0),
        }
    return {"visitors": 0, "pageviews": 0}


def pct_change(current, previous):
    """Calculate percentage change. Returns None if previous is 0."""
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100)


def collect_plausible_stats(sites):
    """Collect traffic stats for all Plausible sites."""
    try:
        token, base_url = load_plausible_config()
    except (FileNotFoundError, ValueError) as e:
        print(f"Plausible not configured: {e}", file=sys.stderr)
        return []

    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    day_before = (now - timedelta(days=2)).strftime("%Y-%m-%d")

    # 7-day windows
    week_end = yesterday
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    prev_week_end = (now - timedelta(days=8)).strftime("%Y-%m-%d")
    prev_week_start = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    # 30-day windows
    month_end = yesterday
    month_start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    prev_month_end = (now - timedelta(days=31)).strftime("%Y-%m-%d")
    prev_month_start = (now - timedelta(days=60)).strftime("%Y-%m-%d")

    results = []
    for site_id in sites:
        stat = {"site": site_id}

        # Yesterday
        yd = get_plausible_aggregate(base_url, token, site_id, yesterday, yesterday)
        stat["yesterday"] = yd

        # Day before (for daily trend)
        db = get_plausible_aggregate(base_url, token, site_id, day_before, day_before)

        # 7-day current and previous
        wk = get_plausible_aggregate(base_url, token, site_id, week_start, week_end)
        prev_wk = get_plausible_aggregate(base_url, token, site_id, prev_week_start, prev_week_end)
        stat["week"] = wk
        stat["week_change"] = pct_change(wk["visitors"], prev_wk["visitors"])

        # 30-day current and previous
        mo = get_plausible_aggregate(base_url, token, site_id, month_start, month_end)
        prev_mo = get_plausible_aggregate(base_url, token, site_id, prev_month_start, prev_month_end)
        stat["month"] = mo
        stat["month_change"] = pct_change(mo["visitors"], prev_mo["visitors"])

        results.append(stat)

    return results


# --- GSC helpers ---

def get_gsc_service():
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_file(
        GSC_CREDENTIALS_PATH, scopes=GSC_SCOPES
    )
    return build("searchconsole", "v1", credentials=creds)


GSC_PAGE_SIZE = 25000
GSC_MAX_PAGES = 40

# Thresholds for the "new queries" and "position movers" blocks in the daily
# email. These are MEASURED, not chosen (DEC-327, DAL-268). Backtested over 8
# consecutive 7-day treestock windows (2026-06-30..2026-08-24), scoring each
# candidate rule on whether the thing it reported was still there a week later.
#
# The old rule was "moved 5+ spots", with no impression floor at all. That
# produced ~316 qualifying rows a week, of which 45% were queries that vanished
# entirely the next week and only 31% held their new position. 98% of the rows
# it actually printed had <= 2 impressions in both weeks, because it sorted by
# size of move and the biggest moves live in the thinnest data: at 1-2
# impressions the MEDIAN week-over-week position swing is 4.0 spots and 45% of
# all queries clear 5, so the threshold sat below the noise floor of the
# population that dominated the list.
#
# The dial that was broken was the impression floor, not the spot count.
# Raising the spot threshold to 15 with no floor barely moved the hold rate
# (31% -> 27%); adding a floor of 5 took it to ~51% and dropped the "vanished
# next week" rate from 45% to 2%. Hold rate plateaus around 50-55% above a
# floor of 3, so a floor of 5 with 10 spots is one clear of the 10-29
# impression band's p90 drift (8.7 spots) and yields ~10 rows a week, which is
# what the block prints anyway.
MOVER_MIN_IMPRESSIONS = 5   # in BOTH weeks
MOVER_MIN_SPOTS = 10

# Same treatment for new queries. At >= 3 impressions, 123 rows a week, 48%
# never seen again and 4% ever earned a click. At >= 5 it is 23 rows a week,
# 76% still present the next week and 10% earned a click.
NEW_QUERY_MIN_IMPRESSIONS = 5


def gsc_query(service, site_url, start_date, end_date, dimensions,
              page_size=GSC_PAGE_SIZE, max_pages=GSC_MAX_PAGES):
    """Fetch ALL rows for a GSC query, following startRow until a short page.

    This used to issue one request with a fixed rowLimit and startRow 0. The
    query dimension returns thousands of rows (1,703 for a 7-day treestock
    window against the old 200-row cap), and the callers compute a SET
    DIFFERENCE from it, so truncation did not merely shorten the list, it
    inverted it: a query present in both periods but outside the top 200 of
    the earlier one was reported as brand new. Measured 2026-07-30: 9 of the
    10 "new queries" in the daily email were queries we already ranked for,
    and position movers saw 11 of a true 392.
    """
    rows = []
    start_row = 0
    for _ in range(max_pages):
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions,
            "rowLimit": page_size,
            "startRow": start_row,
        }
        try:
            response = (
                service.searchanalytics()
                .query(siteUrl=site_url, body=body)
                .execute()
            )
        except Exception as e:
            print(f"GSC error for {site_url} ({dimensions}): {e}", file=sys.stderr)
            return []
        page = response.get("rows", [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start_row += len(page)
    print(
        f"GSC pagination hit {max_pages} pages for {site_url} ({dimensions}); "
        f"returning {len(rows)} rows, which may be partial.",
        file=sys.stderr,
    )
    return rows


def warn_on_unreadable_sites(service, sites, label):
    """Say on stderr which properties this credential cannot actually read.

    Querying a property you lack access to 403s, but gsc_query catches it and
    returns [], which the caller records as 0 clicks. So the diagnosis ends up
    as a wall of HttpError in the cron log while the number that gets published
    is an ordinary-looking zero. Checked live 2026-08-24 against beestock.com.au
    (siteUnverifiedUser) and a made-up domain: both produced 403s and both still
    wrote a 0/0 row. This names the problem in plain words before the traffic
    calls run, and the caller stamps the permission level onto each row so a
    zero in the JSON is attributable without going back to the log.

    Returns {site_url: permission_level} for the sites checked.
    """
    try:
        entries = service.sites().list().execute().get("siteEntry", [])
    except Exception as e:
        print(f"GSC ({label}): site list failed, cannot check access: {e}", file=sys.stderr)
        return {}

    levels = {e.get("siteUrl"): e.get("permissionLevel") for e in entries}
    for site_url in sites:
        level = levels.get(site_url)
        if level is None:
            print(
                f"GSC ({label}): {site_url} is not on this credential's property "
                f"list at all. A zero from it is an access problem, not traffic.",
                file=sys.stderr,
            )
        elif level not in GSC_READABLE_PERMISSIONS:
            print(
                f"GSC ({label}): {site_url} has permission {level}, which cannot "
                f"read search analytics. A zero from it is an access problem, not "
                f"traffic.",
                file=sys.stderr,
            )
    return levels


def collect_gsc_stats(sites):
    """Collect GSC stats for all sites, with period comparison for query changes."""
    try:
        service = get_gsc_service()
    except Exception as e:
        print(f"GSC not configured: {e}", file=sys.stderr)
        return []

    # Check access before reading anything, so an empty result is attributable.
    permissions = warn_on_unreadable_sites(service, sites, "service account")

    now = datetime.now(timezone.utc).date()
    lag = timedelta(days=3)

    # Period A: last 7 days (with lag)
    a_end = now - lag
    a_start = a_end - timedelta(days=6)

    # Period B: previous 7 days
    b_end = a_start - timedelta(days=1)
    b_start = b_end - timedelta(days=6)

    # Full 14-day period for totals
    full_start = str(b_start)
    full_end = str(a_end)

    results = []
    for site_url in sites:
        domain = site_url.replace("sc-domain:", "")
        stat = {"site": domain, "gsc_site": site_url,
                "permission": permissions.get(site_url)}

        # 14-day totals
        date_rows = gsc_query(service, site_url, full_start, full_end, ["date"])
        if not date_rows:
            stat["totals"] = {"clicks": 0, "impressions": 0, "avg_position": 0}
            stat["new_queries"] = []
            stat["position_movers"] = []
            results.append(stat)
            continue

        total_clicks = sum(r["clicks"] for r in date_rows)
        total_impressions = sum(r["impressions"] for r in date_rows)
        avg_position = (
            sum(r["position"] * r["impressions"] for r in date_rows) / total_impressions
            if total_impressions else 0
        )
        stat["totals"] = {
            "clicks": int(total_clicks),
            "impressions": int(total_impressions),
            "avg_position": round(avg_position, 1),
        }

        # Period A queries
        a_rows = gsc_query(service, site_url, str(a_start), str(a_end), ["query"])
        a_queries = {r["keys"][0]: r for r in a_rows}

        # Period B queries
        b_rows = gsc_query(service, site_url, str(b_start), str(b_end), ["query"])
        b_queries = {r["keys"][0]: r for r in b_rows}

        # New queries: in A but not in B, sorted by impressions
        new_queries = []
        for q, r in sorted(a_queries.items(), key=lambda x: x[1]["impressions"], reverse=True):
            if q not in b_queries and r["impressions"] >= NEW_QUERY_MIN_IMPRESSIONS:
                new_queries.append({
                    "query": q,
                    "position": round(r["position"], 1),
                    "impressions": int(r["impressions"]),
                    "clicks": int(r["clicks"]),
                })
        stat["new_queries"] = new_queries[:10]

        # Position movers, thresholds measured rather than chosen: see DEC-327.
        movers = []
        for q in a_queries:
            if q in b_queries:
                if min(a_queries[q]["impressions"],
                       b_queries[q]["impressions"]) < MOVER_MIN_IMPRESSIONS:
                    continue
                pos_a = a_queries[q]["position"]
                pos_b = b_queries[q]["position"]
                diff = pos_b - pos_a  # positive = improved (lower position is better)
                if abs(diff) >= MOVER_MIN_SPOTS:
                    movers.append({
                        "query": q,
                        "old_position": round(pos_b, 0),
                        "new_position": round(pos_a, 0),
                        "change": round(diff, 0),
                        "impressions": int(a_queries[q]["impressions"]),
                    })
        # Sort by impressions, not by size of move. Sorting by change picks the
        # extreme tail of a noisy distribution, which is where the noise lives.
        movers.sort(key=lambda x: x["impressions"], reverse=True)
        stat["position_movers"] = movers[:10]

        results.append(stat)

    return results


# --- Main ---

def generate_report(output_path=None, skip_gsc=False):
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plausible": collect_plausible_stats(PLAUSIBLE_SITES),
        "gsc": [] if skip_gsc else collect_gsc_stats(GSC_SITES),
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Traffic report saved to {output_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-site traffic report")
    parser.add_argument("--output", default="/opt/dale/data/traffic_report.json")
    parser.add_argument("--skip-gsc", action="store_true", help="Skip GSC data collection")
    args = parser.parse_args()
    generate_report(output_path=args.output, skip_gsc=args.skip_gsc)
