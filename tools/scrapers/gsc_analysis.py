#!/usr/bin/env python3
"""
GSC Analysis for treestock.com.au
DAL-12: Pull impressions, clicks, CTR, top queries via Search Console API.
DAL-104: URL inspection status for top SEO pages.

Usage:
    python3 gsc_analysis.py
    python3 gsc_analysis.py --output /opt/dale/data/gsc_report.json
    python3 gsc_analysis.py --days 30
    python3 gsc_analysis.py --inspect           # Also run URL inspection (requires OAuth creds)
    python3 gsc_analysis.py --inspect-only      # Run only URL inspection
"""

import json
import sys
import os
import argparse
import time
from datetime import datetime, timedelta
from collections import defaultdict

import requests
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

CREDENTIALS_PATH = "/opt/dale/secrets/gsc-credentials.json"
OAUTH_CREDS_PATH = "/opt/dale/secrets/gsc-oauth-credentials.json"
SITE_URL = "sc-domain:treestock.com.au"
SITE_BASE = "https://treestock.com.au"
DASHBOARD_DIR = "/opt/dale/dashboard"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
INSPECTION_API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH, scopes=SCOPES
    )
    return build("searchconsole", "v1", credentials=creds)


def get_oauth_credentials():
    """Load OAuth credentials with refresh token (from gsc_submit.py pattern)."""
    with open(OAUTH_CREDS_PATH) as f:
        creds_data = json.load(f)
    with open(CREDENTIALS_PATH) as f:
        sa_data = json.load(f)
    project_id = sa_data["project_id"]

    creds = Credentials(
        token=None,
        refresh_token=creds_data["refresh_token"],
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/webmasters"],
        quota_project_id=project_id,
    )
    creds.refresh(Request())
    return creds, project_id


def inspect_url(creds, project_id, page_url):
    """Call URL Inspection API for a single URL. Returns dict with verdict/coverage/crawled."""
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "x-goog-user-project": project_id,
        "Content-Type": "application/json",
    }
    body = {"inspectionUrl": page_url, "siteUrl": SITE_URL}
    try:
        resp = requests.post(INSPECTION_API, json=body, headers=headers, timeout=15)
        if resp.status_code == 200:
            result = resp.json().get("inspectionResult", {})
            index = result.get("indexStatusResult", {})
            return {
                "url": page_url,
                "verdict": index.get("verdict", "UNKNOWN"),
                "coverage": index.get("coverageState", "Unknown"),
                "last_crawled": index.get("lastCrawlTime", None),
                "robots_txt_state": index.get("robotsTxtState", None),
                "sitemap": index.get("sitemap", []),
                "error": None,
            }
        else:
            return {
                "url": page_url,
                "verdict": "API_ERROR",
                "coverage": f"HTTP {resp.status_code}",
                "last_crawled": None,
                "error": resp.text[:200],
            }
    except Exception as e:
        return {
            "url": page_url,
            "verdict": "API_ERROR",
            "coverage": str(e)[:100],
            "last_crawled": None,
            "error": str(e),
        }


def build_inspection_urls(top_gsc_pages=None):
    """
    Build list of key SEO URLs to inspect.
    Prioritises: pages with GSC data, new combo pages (WA), location pages, special pages.
    """
    urls = []
    seen = set()

    def add(url):
        if url not in seen:
            seen.add(url)
            urls.append(url)

    # 1. Homepage and key special pages
    add(f"{SITE_BASE}/")
    add(f"{SITE_BASE}/when-to-plant.html")
    add(f"{SITE_BASE}/rare.html")

    # 2. Location pages (4 total)
    for state in ["wa", "qld", "nsw", "vic"]:
        add(f"{SITE_BASE}/buy-fruit-trees-{state}.html")

    # 3. Pages from GSC impressions data (top by impressions, up to 15)
    if top_gsc_pages:
        for row in sorted(top_gsc_pages, key=lambda r: r["impressions"], reverse=True)[:15]:
            page = row.get("page", "")
            if page.startswith("https://treestock.com.au"):
                add(page)

    # 4. Top species pages (by alphabetical slug if no GSC data yet)
    species_dir = os.path.join(DASHBOARD_DIR, "species")
    if os.path.isdir(species_dir):
        slugs = [f.replace(".html", "") for f in sorted(os.listdir(species_dir))
                 if f.endswith(".html") and not f.startswith("species/")]
        for slug in slugs[:20]:
            add(f"{SITE_BASE}/species/{slug}.html")

    # 5. WA combo pages (all — unique quarantine content)
    wa_combos = [
        f for f in sorted(os.listdir(DASHBOARD_DIR))
        if f.endswith("-western-australia.html") and f.startswith("buy-")
    ]
    for fname in wa_combos[:25]:
        add(f"{SITE_BASE}/{fname}")

    # 6. Sample of other state combo pages (top 10 by alphabetical)
    other_combos = [
        f for f in sorted(os.listdir(DASHBOARD_DIR))
        if f.startswith("buy-") and f.endswith(".html")
        and not f.endswith("-western-australia.html")
        and not f.startswith("buy-fruit-trees-")
    ]
    for fname in other_combos[:10]:
        add(f"{SITE_BASE}/{fname}")

    return urls


def run_url_inspection(urls=None, top_gsc_pages=None, delay_seconds=0.5):
    """
    Inspect a list of URLs via GSC URL Inspection API.
    Returns list of inspection results plus alert list.
    """
    if not os.path.exists(OAUTH_CREDS_PATH):
        print("  SKIP: OAuth credentials not found at", OAUTH_CREDS_PATH)
        return None

    try:
        creds, project_id = get_oauth_credentials()
    except Exception as e:
        print(f"  ERROR: Could not load OAuth credentials: {e}")
        return None

    if urls is None:
        urls = build_inspection_urls(top_gsc_pages=top_gsc_pages)

    print(f"\n--- URL INSPECTION ({len(urls)} URLs) ---")
    results = []
    alerts = []

    verdict_counts = defaultdict(int)

    for i, url in enumerate(urls):
        result = inspect_url(creds, project_id, url)
        results.append(result)
        verdict = result["verdict"]
        coverage = result["coverage"]
        last_crawled = result.get("last_crawled", "never")

        verdict_counts[verdict] += 1

        # Format display
        short_url = url.replace(SITE_BASE, "")
        crawl_str = last_crawled[:10] if last_crawled else "never"
        print(f"  [{verdict:<12}] {short_url:<60} (crawled: {crawl_str})")

        # Alert conditions
        if verdict == "FAIL":
            alerts.append({"url": url, "reason": f"FAIL — {coverage}", "severity": "critical"})
        elif verdict == "NEUTRAL" and "Crawl anomaly" in coverage:
            alerts.append({"url": url, "reason": f"Crawl anomaly: {coverage}", "severity": "warning"})
        elif verdict == "API_ERROR":
            alerts.append({"url": url, "reason": f"API error: {coverage}", "severity": "info"})

        # Refresh token periodically and throttle
        if (i + 1) % 20 == 0:
            try:
                creds.refresh(Request())
            except Exception:
                pass
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    print()
    print(f"  Summary: ", end="")
    for verdict, count in sorted(verdict_counts.items()):
        print(f"{verdict}: {count}  ", end="")
    print()

    if alerts:
        print(f"\n  ALERTS ({len(alerts)}):")
        for alert in alerts:
            print(f"    [{alert['severity'].upper()}] {alert['url']}")
            print(f"      {alert['reason']}")
    else:
        print("  No alerts.")

    return {
        "inspected_at": datetime.utcnow().isoformat(),
        "total_urls": len(urls),
        "verdict_summary": dict(verdict_counts),
        "results": results,
        "alerts": alerts,
    }


def date_range(days_back=30):
    end = datetime.utcnow().date() - timedelta(days=3)  # GSC has 3-day lag
    start = end - timedelta(days=days_back - 1)
    return str(start), str(end)


def query_gsc(service, site_url, start_date, end_date, dimensions, row_limit=500):
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
    except HttpError as e:
        print(f"  ERROR querying GSC ({dimensions}): {e}", file=sys.stderr)
        return []


def format_pct(v):
    return f"{v*100:.1f}%"


def format_num(v, decimals=1):
    return f"{v:.{decimals}f}"


def run_analysis(days=16, output_path=None, inspect=False):
    print("=== GSC Analysis: treestock.com.au ===")
    print(f"Period: last {days} days (with 3-day GSC lag)")
    print()

    try:
        service = get_service()
    except Exception as e:
        print(f"ERROR: Could not authenticate with GSC: {e}")
        sys.exit(1)

    start_date, end_date = date_range(days)
    print(f"Date range: {start_date} to {end_date}")
    print()

    # 1. Overall site totals
    print("--- OVERALL SITE PERFORMANCE ---")
    totals_rows = query_gsc(service, SITE_URL, start_date, end_date, ["date"])
    if not totals_rows:
        print("  No data returned. Check that the service account has access to treestock.com.au in GSC.")
        print("  Service account email: firebase-adminsdk-fbsvc@dale-490702.iam.gserviceaccount.com")
        return None

    total_clicks = sum(r["clicks"] for r in totals_rows)
    total_impressions = sum(r["impressions"] for r in totals_rows)
    total_ctr = total_clicks / total_impressions if total_impressions else 0
    avg_position = sum(r["position"] * r["impressions"] for r in totals_rows) / total_impressions if total_impressions else 0

    print(f"  Clicks:       {int(total_clicks)}")
    print(f"  Impressions:  {int(total_impressions)}")
    print(f"  CTR:          {format_pct(total_ctr)}")
    print(f"  Avg Position: {format_num(avg_position)}")
    print()

    # Daily trend
    print("--- DAILY TREND ---")
    daily = sorted(totals_rows, key=lambda r: r["keys"][0])
    for row in daily:
        day = row["keys"][0]
        c = int(row["clicks"])
        i = int(row["impressions"])
        ctr = format_pct(row["ctr"])
        pos = format_num(row["position"])
        print(f"  {day}: {i:>5} impr, {c:>3} clicks, CTR {ctr:>6}, pos {pos}")
    print()

    # 2. Top queries
    print("--- TOP 20 QUERIES (by impressions) ---")
    query_rows = query_gsc(service, SITE_URL, start_date, end_date, ["query"], row_limit=200)
    query_rows.sort(key=lambda r: r["impressions"], reverse=True)
    for row in query_rows[:20]:
        q = row["keys"][0]
        c = int(row["clicks"])
        i = int(row["impressions"])
        ctr = format_pct(row["ctr"])
        pos = format_num(row["position"])
        print(f"  [{i:>4} impr | {c:>3} clicks | CTR {ctr:>6} | pos {pos:>5}] {q}")
    print()

    # Top queries by clicks
    print("--- TOP 20 QUERIES (by clicks) ---")
    click_sorted = sorted(query_rows, key=lambda r: r["clicks"], reverse=True)
    for row in click_sorted[:20]:
        q = row["keys"][0]
        c = int(row["clicks"])
        i = int(row["impressions"])
        ctr = format_pct(row["ctr"])
        pos = format_num(row["position"])
        print(f"  [{c:>3} clicks | {i:>4} impr | CTR {ctr:>6} | pos {pos:>5}] {q}")
    print()

    # Low position (high opportunity) queries with decent impressions
    print("--- HIGH OPPORTUNITY: pos 11-30, impressions >= 5 ---")
    opportunity = [
        r for r in query_rows
        if 10 < r["position"] <= 30 and r["impressions"] >= 5
    ]
    opportunity.sort(key=lambda r: r["impressions"], reverse=True)
    for row in opportunity[:20]:
        q = row["keys"][0]
        c = int(row["clicks"])
        i = int(row["impressions"])
        ctr = format_pct(row["ctr"])
        pos = format_num(row["position"])
        print(f"  [pos {pos:>5} | {i:>4} impr | {c:>3} clicks] {q}")
    print()

    # 3. Top pages
    print("--- TOP 20 PAGES (by impressions) ---")
    page_rows = query_gsc(service, SITE_URL, start_date, end_date, ["page"], row_limit=500)
    page_rows.sort(key=lambda r: r["impressions"], reverse=True)
    for row in page_rows[:20]:
        page = row["keys"][0].replace("https://treestock.com.au", "")
        c = int(row["clicks"])
        i = int(row["impressions"])
        ctr = format_pct(row["ctr"])
        pos = format_num(row["position"])
        print(f"  [{i:>4} impr | {c:>3} clicks | CTR {ctr:>6} | pos {pos:>5}] {page}")
    print()

    # 4. Page type breakdown
    print("--- PAGE TYPE BREAKDOWN ---")
    page_types = defaultdict(lambda: {"impressions": 0, "clicks": 0, "pages": 0})
    for row in page_rows:
        url = row["keys"][0]
        path = url.replace("https://treestock.com.au", "")
        if path.startswith("/variety/"):
            ptype = "variety pages"
        elif path.startswith("/species/"):
            ptype = "species pages"
        elif path.startswith("/compare/"):
            ptype = "compare pages"
        elif path.startswith("/nursery/"):
            ptype = "nursery pages"
        elif path in ("/", ""):
            ptype = "homepage"
        elif path.startswith("/buy-fruit-trees"):
            ptype = "location pages"
        elif path.startswith("/buy-") and path.endswith(".html"):
            ptype = "species+state pages"
        elif "/guide" in path:
            ptype = "guide page"
        elif "/when-to-plant" in path:
            ptype = "planting calendar"
        elif "/rare" in path:
            ptype = "rare finds page"
        elif "/digest" in path or "/daily" in path:
            ptype = "digest pages"
        else:
            ptype = "other"
        page_types[ptype]["impressions"] += row["impressions"]
        page_types[ptype]["clicks"] += row["clicks"]
        page_types[ptype]["pages"] += 1

    for ptype, stats in sorted(page_types.items(), key=lambda x: x[1]["impressions"], reverse=True):
        c = int(stats["clicks"])
        i = int(stats["impressions"])
        n = stats["pages"]
        ctr = format_pct(stats["clicks"] / stats["impressions"]) if stats["impressions"] else "0.0%"
        print(f"  {ptype:<22} {n:>4} pages | {i:>5} impr | {c:>3} clicks | CTR {ctr}")
    print()

    # 5. Best performing variety/species pages
    print("--- TOP 10 VARIETY PAGES (by impressions) ---")
    variety_pages = [r for r in page_rows if "/variety/" in r["keys"][0]]
    variety_pages.sort(key=lambda r: r["impressions"], reverse=True)
    for row in variety_pages[:10]:
        page = row["keys"][0].replace("https://treestock.com.au/variety/", "")
        c = int(row["clicks"])
        i = int(row["impressions"])
        pos = format_num(row["position"])
        print(f"  [pos {pos:>5} | {i:>4} impr | {c:>3} clicks] {page}")
    print()

    print("--- TOP 10 SPECIES PAGES (by impressions) ---")
    species_pages = [r for r in page_rows if "/species/" in r["keys"][0]]
    species_pages.sort(key=lambda r: r["impressions"], reverse=True)
    for row in species_pages[:10]:
        page = row["keys"][0].replace("https://treestock.com.au/species/", "")
        c = int(row["clicks"])
        i = int(row["impressions"])
        pos = format_num(row["position"])
        print(f"  [pos {pos:>5} | {i:>4} impr | {c:>3} clicks] {page}")
    print()

    # Build structured output
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "period": {"start": start_date, "end": end_date, "days": days},
        "totals": {
            "clicks": int(total_clicks),
            "impressions": int(total_impressions),
            "ctr": round(total_ctr, 4),
            "avg_position": round(avg_position, 1),
        },
        "daily": [
            {
                "date": r["keys"][0],
                "clicks": int(r["clicks"]),
                "impressions": int(r["impressions"]),
                "ctr": round(r["ctr"], 4),
                "position": round(r["position"], 1),
            }
            for r in sorted(totals_rows, key=lambda r: r["keys"][0])
        ],
        "top_queries_by_impressions": [
            {
                "query": r["keys"][0],
                "clicks": int(r["clicks"]),
                "impressions": int(r["impressions"]),
                "ctr": round(r["ctr"], 4),
                "position": round(r["position"], 1),
            }
            for r in query_rows[:50]
        ],
        "top_pages_by_impressions": [
            {
                "page": r["keys"][0],
                "clicks": int(r["clicks"]),
                "impressions": int(r["impressions"]),
                "ctr": round(r["ctr"], 4),
                "position": round(r["position"], 1),
            }
            for r in page_rows[:50]
        ],
        "high_opportunity_queries": [
            {
                "query": r["keys"][0],
                "clicks": int(r["clicks"]),
                "impressions": int(r["impressions"]),
                "ctr": round(r["ctr"], 4),
                "position": round(r["position"], 1),
            }
            for r in opportunity[:30]
        ],
        "page_type_breakdown": {
            ptype: {
                "pages": stats["pages"],
                "impressions": int(stats["impressions"]),
                "clicks": int(stats["clicks"]),
            }
            for ptype, stats in page_types.items()
        },
    }

    # 6. URL Inspection (optional, requires OAuth creds)
    if inspect:
        print("\n=== URL INSPECTION ===")
        inspection = run_url_inspection(
            top_gsc_pages=report["top_pages_by_impressions"]
        )
        if inspection:
            report["url_inspection"] = inspection
            # Surface alerts in the overall report
            if inspection["alerts"]:
                print(f"\n*** {len(inspection['alerts'])} ALERT(S) REQUIRE ATTENTION ***")
            print()

    # Save report
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report saved to {output_path}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GSC Analysis for treestock.com.au")
    parser.add_argument("--days", type=int, default=16, help="Days of data to pull (default 16)")
    parser.add_argument("--output", type=str, default="/opt/dale/data/gsc_report.json")
    parser.add_argument("--inspect", action="store_true", help="Also run URL inspection for key SEO pages")
    parser.add_argument("--inspect-only", action="store_true", help="Run only URL inspection (skip search analytics)")
    args = parser.parse_args()

    if args.inspect_only:
        print("=== GSC URL Inspection: treestock.com.au ===")
        result = run_url_inspection()
        if result and args.output:
            os.makedirs(os.path.dirname(args.output), exist_ok=True)
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2)
            print(f"Inspection report saved to {args.output}")
    else:
        run_analysis(days=args.days, output_path=args.output, inspect=args.inspect)
