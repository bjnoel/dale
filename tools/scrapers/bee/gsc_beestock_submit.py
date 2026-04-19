#!/usr/bin/env python3
"""
GSC Sitemap and URL submission for beestock.com.au
Uses same OAuth credentials as treestock (same Google account / GSC property).

Usage:
    python3 gsc_beestock_submit.py                  # Submit/refresh sitemap
    python3 gsc_beestock_submit.py --list           # List submitted sitemaps
    python3 gsc_beestock_submit.py --compare-check  # Check indexing of all compare pages
    python3 gsc_beestock_submit.py --check-url URL  # Check a single URL

Authentication: /opt/dale/secrets/gsc-oauth-credentials.json (refresh_token present)
Quota project: dale-490702
"""

import argparse
import json
import os
import time
import requests
from urllib.parse import quote

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

OAUTH_CREDS_PATH = "/opt/dale/secrets/gsc-oauth-credentials.json"
SA_CREDS_PATH = "/opt/dale/secrets/gsc-credentials.json"
SITE_URL = "sc-domain:beestock.com.au"
SITEMAP_URL = "https://beestock.com.au/sitemap.xml"
WEBMASTERS_BASE = "https://www.googleapis.com/webmasters/v3"
BEE_DASHBOARD = "/opt/dale/bee-dashboard"
BASE_URL = "https://beestock.com.au"


def get_credentials():
    with open(OAUTH_CREDS_PATH) as f:
        creds_data = json.load(f)
    with open(SA_CREDS_PATH) as f:
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


def make_headers(creds, project_id):
    return {
        "Authorization": f"Bearer {creds.token}",
        "x-goog-user-project": project_id,
    }


def submit_sitemap(creds, project_id):
    site_enc = quote(SITE_URL, safe="")
    sitemap_enc = quote(SITEMAP_URL, safe="")
    url = f"{WEBMASTERS_BASE}/sites/{site_enc}/sitemaps/{sitemap_enc}"
    resp = requests.put(url, headers=make_headers(creds, project_id))
    if resp.status_code == 204:
        print(f"Sitemap submitted: {SITEMAP_URL}")
    elif resp.status_code == 403:
        print(f"403 Forbidden — beestock.com.au may not be verified in this GSC account.")
        print(f"Response: {resp.text[:400]}")
    else:
        print(f"Error {resp.status_code}: {resp.text[:400]}")
    return resp.status_code == 204


def list_sitemaps(creds, project_id):
    site_enc = quote(SITE_URL, safe="")
    url = f"{WEBMASTERS_BASE}/sites/{site_enc}/sitemaps"
    resp = requests.get(url, headers=make_headers(creds, project_id))
    if resp.status_code == 200:
        data = resp.json()
        sitemaps = data.get("sitemap", [])
        if not sitemaps:
            print("No sitemaps found. Site may not be verified in this GSC account.")
            return
        for s in sitemaps:
            path = s.get("path", "")
            last_submitted = s.get("lastSubmitted", "never")
            last_downloaded = s.get("lastDownloaded", "never")
            errors = s.get("errors", 0)
            warnings = s.get("warnings", 0)
            print(f"  {path}")
            print(f"    Submitted: {last_submitted} | Downloaded: {last_downloaded} | Errors: {errors} Warnings: {warnings}")
    elif resp.status_code == 403:
        print("403 Forbidden — beestock.com.au may not be verified in this GSC account.")
    else:
        print(f"Error {resp.status_code}: {resp.text[:300]}")


def check_url(creds, project_id, page_url, verbose=True):
    url = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
    body = {
        "inspectionUrl": page_url,
        "siteUrl": SITE_URL,
    }
    headers = {**make_headers(creds, project_id), "Content-Type": "application/json"}
    resp = requests.post(url, json=body, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        result = data.get("inspectionResult", {})
        index_status = result.get("indexStatusResult", {})
        coverage = index_status.get("coverageState", "unknown")
        verdict = index_status.get("verdict", "unknown")
        crawled = index_status.get("lastCrawlTime", "never")
        if verbose:
            print(f"URL: {page_url}")
            print(f"  Verdict: {verdict}")
            print(f"  Coverage: {coverage}")
            print(f"  Last crawled: {crawled}")
        return {"url": page_url, "verdict": verdict, "coverage": coverage, "crawled": crawled}
    else:
        if verbose:
            print(f"Error {resp.status_code}: {resp.text[:300]}")
        return {"url": page_url, "verdict": "ERROR", "coverage": str(resp.status_code), "crawled": "never"}


def get_compare_urls():
    compare_dir = os.path.join(BEE_DASHBOARD, "compare")
    urls = []
    if os.path.isdir(compare_dir):
        for fname in sorted(os.listdir(compare_dir)):
            if fname.endswith("-prices.html"):
                urls.append(f"{BASE_URL}/compare/{fname}")
    return urls


def bulk_check_urls(creds, project_id, urls, delay=0.5):
    indexed = []
    not_indexed = []
    errors = []

    print(f"Checking {len(urls)} URLs...")
    print()

    for i, url in enumerate(urls, 1):
        result = check_url(creds, project_id, url, verbose=False)
        verdict = result["verdict"]
        coverage = result["coverage"]

        if verdict == "PASS":
            indexed.append(url)
            status = "INDEXED"
        elif verdict == "ERROR" or "Error" in str(coverage):
            errors.append(url)
            status = f"ERROR ({coverage})"
        else:
            not_indexed.append(url)
            status = f"NOT INDEXED ({coverage})"

        print(f"[{i:3d}/{len(urls)}] {status}: {url.replace(BASE_URL + '/compare/', '')}")

        if i < len(urls):
            time.sleep(delay)

    print()
    print("=" * 60)
    print(f"SUMMARY: {len(indexed)} indexed, {len(not_indexed)} not indexed, {len(errors)} errors")
    print("=" * 60)

    if not_indexed:
        print(f"\nNot indexed ({len(not_indexed)}):")
        for url in not_indexed:
            print(f"  {url}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for url in errors:
            print(f"  {url}")

    return indexed, not_indexed, errors


def main():
    parser = argparse.ArgumentParser(description="GSC submission tool for beestock.com.au")
    parser.add_argument("--list", action="store_true", help="List submitted sitemaps")
    parser.add_argument("--check-url", metavar="URL", help="Check indexing status of a single URL")
    parser.add_argument("--compare-check", action="store_true", help="Check indexing status of all compare pages")
    args = parser.parse_args()

    creds, project_id = get_credentials()

    if args.list:
        print("Submitted sitemaps for beestock.com.au:")
        list_sitemaps(creds, project_id)
    elif args.check_url:
        check_url(creds, project_id, args.check_url)
    elif args.compare_check:
        urls = get_compare_urls()
        print(f"Found {len(urls)} compare pages in {BEE_DASHBOARD}/compare/")
        bulk_check_urls(creds, project_id, urls)
    else:
        ok = submit_sitemap(creds, project_id)
        if ok:
            print(f"\nSitemap includes {len(get_compare_urls())} compare pages.")
            print("Google will crawl them based on the sitemap. To verify indexing later:")
            print("  python3 gsc_beestock_submit.py --compare-check")


if __name__ == "__main__":
    main()
