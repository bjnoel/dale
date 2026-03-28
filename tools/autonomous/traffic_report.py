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

PLAUSIBLE_SITES = [
    "treestock.com.au",
    "vergeside.com.au",
    "bjnoel.com",
    "beestock.com.au",
    "mushroom.guide",
    "walkthrough.au",
]

GSC_SITES = [
    "sc-domain:treestock.com.au",
    "sc-domain:vergeside.com.au",
    "sc-domain:bjnoel.com",
    "sc-domain:mushroom.guide",
    "sc-domain:walkthrough.au",
    "sc-domain:scion.exchange",
    "sc-domain:wanatca.org.au",
    "sc-domain:beestock.com.au",
]

GSC_CREDENTIALS_PATH = "/opt/dale/secrets/gsc-credentials.json"
GSC_OAUTH_CREDENTIALS_PATH = "/opt/dale/secrets/gsc-oauth-credentials.json"
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# beestock requires personal OAuth token (service account is unverified for this site)
GSC_OAUTH_SITES = {"sc-domain:beestock.com.au"}


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

def get_gsc_service(use_oauth=False):
    from googleapiclient.discovery import build
    if use_oauth:
        from google.oauth2.credentials import Credentials as UserCredentials
        with open(GSC_OAUTH_CREDENTIALS_PATH) as f:
            token_data = json.load(f)
        creds = UserCredentials.from_authorized_user_info(token_data)
        creds = creds.with_quota_project("dale-490702")
    else:
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            GSC_CREDENTIALS_PATH, scopes=GSC_SCOPES
        )
    return build("searchconsole", "v1", credentials=creds)


def gsc_query(service, site_url, start_date, end_date, dimensions, row_limit=500):
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "rowLimit": row_limit,
        "startRow": 0,
    }
    try:
        response = (
            service.searchanalytics()
            .query(siteUrl=site_url, body=body)
            .execute()
        )
        return response.get("rows", [])
    except Exception as e:
        print(f"GSC error for {site_url} ({dimensions}): {e}", file=sys.stderr)
        return []


def collect_gsc_stats(sites):
    """Collect GSC stats for all sites, with period comparison for query changes."""
    try:
        service = get_gsc_service()
    except Exception as e:
        print(f"GSC not configured: {e}", file=sys.stderr)
        return []

    # Build OAuth service for sites that need it
    oauth_service = None
    if GSC_OAUTH_SITES & set(sites):
        try:
            oauth_service = get_gsc_service(use_oauth=True)
        except Exception as e:
            print(f"GSC OAuth not configured: {e}", file=sys.stderr)

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
        stat = {"site": domain, "gsc_site": site_url}

        # Use OAuth service for sites that need it
        svc = oauth_service if (site_url in GSC_OAUTH_SITES and oauth_service) else service

        # 14-day totals
        date_rows = gsc_query(svc, site_url, full_start, full_end, ["date"])
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
        a_rows = gsc_query(svc, site_url, str(a_start), str(a_end), ["query"], row_limit=200)
        a_queries = {r["keys"][0]: r for r in a_rows}

        # Period B queries
        b_rows = gsc_query(svc, site_url, str(b_start), str(b_end), ["query"], row_limit=200)
        b_queries = {r["keys"][0]: r for r in b_rows}

        # New queries: in A but not in B, sorted by impressions
        new_queries = []
        for q, r in sorted(a_queries.items(), key=lambda x: x[1]["impressions"], reverse=True):
            if q not in b_queries and r["impressions"] >= 3:
                new_queries.append({
                    "query": q,
                    "position": round(r["position"], 1),
                    "impressions": int(r["impressions"]),
                    "clicks": int(r["clicks"]),
                })
        stat["new_queries"] = new_queries[:10]

        # Position movers: in both periods, position changed 5+ spots
        movers = []
        for q in a_queries:
            if q in b_queries:
                pos_a = a_queries[q]["position"]
                pos_b = b_queries[q]["position"]
                diff = pos_b - pos_a  # positive = improved (lower position is better)
                if abs(diff) >= 5:
                    movers.append({
                        "query": q,
                        "old_position": round(pos_b, 0),
                        "new_position": round(pos_a, 0),
                        "change": round(diff, 0),
                        "impressions": int(a_queries[q]["impressions"]),
                    })
        # Sort: biggest improvements first, then biggest drops
        movers.sort(key=lambda x: x["change"], reverse=True)
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
