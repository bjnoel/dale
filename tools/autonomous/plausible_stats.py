#!/usr/bin/env python3
"""Query Plausible analytics for treestock.com.au traffic data."""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

SECRETS_DIR = "/opt/dale/secrets"
SITE_ID = "treestock.com.au"


def load_plausible_config():
    """Load Plausible API token and URL from secrets."""
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


def api_get(base_url, token, endpoint, params=None):
    """Make a GET request to the Plausible API."""
    url = f"{base_url}{endpoint}"
    if params:
        query = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url += f"?{query}"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "dale-autonomous/1.0",
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        print(f"Plausible API error ({e.code}): {error_body}", file=sys.stderr)
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"Plausible API unreachable: {e}", file=sys.stderr)
        return None


def get_stats_summary():
    """Get a text summary of traffic stats for the session prompt."""
    try:
        token, base_url = load_plausible_config()
    except (FileNotFoundError, ValueError) as e:
        return f"Plausible not configured: {e}"

    lines = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    # Realtime visitors
    realtime = api_get(base_url, token, "/api/v1/stats/realtime/visitors",
                       {"site_id": SITE_ID})
    if realtime is not None:
        lines.append(f"Current visitors: {realtime}")

    # Today's aggregate
    agg_today = api_get(base_url, token, "/api/v1/stats/aggregate", {
        "site_id": SITE_ID,
        "period": "day",
        "date": today,
        "metrics": "visitors,pageviews,bounce_rate,visit_duration",
    })
    if agg_today and "results" in agg_today:
        r = agg_today["results"]
        lines.append(f"Today: {r.get('visitors', {}).get('value', 0)} visitors, "
                     f"{r.get('pageviews', {}).get('value', 0)} pageviews, "
                     f"{r.get('bounce_rate', {}).get('value', 0)}% bounce, "
                     f"{r.get('visit_duration', {}).get('value', 0)}s avg duration")

    # Yesterday's aggregate
    agg_yesterday = api_get(base_url, token, "/api/v1/stats/aggregate", {
        "site_id": SITE_ID,
        "period": "day",
        "date": yesterday,
        "metrics": "visitors,pageviews",
    })
    if agg_yesterday and "results" in agg_yesterday:
        r = agg_yesterday["results"]
        lines.append(f"Yesterday: {r.get('visitors', {}).get('value', 0)} visitors, "
                     f"{r.get('pageviews', {}).get('value', 0)} pageviews")

    # Last 7 days
    agg_week = api_get(base_url, token, "/api/v1/stats/aggregate", {
        "site_id": SITE_ID,
        "period": "custom",
        "date": f"{week_ago},{today}",
        "metrics": "visitors,pageviews",
    })
    if agg_week and "results" in agg_week:
        r = agg_week["results"]
        lines.append(f"Last 7 days: {r.get('visitors', {}).get('value', 0)} visitors, "
                     f"{r.get('pageviews', {}).get('value', 0)} pageviews")

    # Top pages today
    pages = api_get(base_url, token, "/api/v1/stats/breakdown", {
        "site_id": SITE_ID,
        "period": "day",
        "date": today,
        "property": "event:page",
        "metrics": "visitors,pageviews",
        "limit": "10",
    })
    if pages and "results" in pages and pages["results"]:
        lines.append("Top pages today:")
        for p in pages["results"][:10]:
            lines.append(f"  {p['page']}: {p.get('visitors', 0)} visitors, "
                         f"{p.get('pageviews', 0)} views")

    # Top referrers today
    sources = api_get(base_url, token, "/api/v1/stats/breakdown", {
        "site_id": SITE_ID,
        "period": "day",
        "date": today,
        "property": "visit:source",
        "metrics": "visitors",
        "limit": "10",
    })
    if sources and "results" in sources and sources["results"]:
        lines.append("Top referrers today:")
        for s in sources["results"][:10]:
            lines.append(f"  {s['source']}: {s.get('visitors', 0)} visitors")

    # Top referrers last 7 days (to catch FB traffic even if it's not today)
    sources_week = api_get(base_url, token, "/api/v1/stats/breakdown", {
        "site_id": SITE_ID,
        "period": "custom",
        "date": f"{week_ago},{today}",
        "property": "visit:source",
        "metrics": "visitors",
        "limit": "10",
    })
    if sources_week and "results" in sources_week and sources_week["results"]:
        lines.append("Top referrers (7 days):")
        for s in sources_week["results"][:10]:
            lines.append(f"  {s['source']}: {s.get('visitors', 0)} visitors")

    if not lines:
        return "Plausible: no data available yet."

    return "\n".join(lines)


if __name__ == "__main__":
    print(get_stats_summary())
