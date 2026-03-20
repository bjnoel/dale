#!/usr/bin/env python3
"""
GSC Analysis for treestock.com.au
DAL-12: Pull impressions, clicks, CTR, top queries via Search Console API.

Usage:
    python3 gsc_analysis.py
    python3 gsc_analysis.py --output /opt/dale/data/gsc_report.json
    python3 gsc_analysis.py --days 30
"""

import json
import sys
import os
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

CREDENTIALS_PATH = "/opt/dale/secrets/gsc-credentials.json"
SITE_URL = "sc-domain:treestock.com.au"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH, scopes=SCOPES
    )
    return build("searchconsole", "v1", credentials=creds)


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


def run_analysis(days=16, output_path=None):
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
        elif "/guide" in path:
            ptype = "guide page"
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
    args = parser.parse_args()

    run_analysis(days=args.days, output_path=args.output)
