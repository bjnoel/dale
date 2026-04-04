#!/usr/bin/env python3
"""
GSC Sitemap and URL submission for treestock.com.au
Uses OAuth credentials with refresh token (no interactive auth needed).

Usage:
    python3 gsc_submit.py                          # Submit/refresh sitemap
    python3 gsc_submit.py --list                   # List submitted sitemaps
    python3 gsc_submit.py --check-url <url>        # Check if URL is indexed
    python3 gsc_submit.py --bulk-check             # Check all new content pages
    python3 gsc_submit.py --bulk-check --urls-file FILE  # Check URLs from file (one per line)

Authentication: gsc-oauth-credentials.json (has refresh_token, no interactive auth needed)
Quota project: dale-490702 (required for GSC API calls)
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
SITE_URL = "sc-domain:treestock.com.au"
SITEMAP_URL = "https://treestock.com.au/sitemap.xml"
WEBMASTERS_BASE = "https://www.googleapis.com/webmasters/v3"


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


def submit_sitemap(creds, project_id, sitemap_url=SITEMAP_URL):
    site_enc = quote(SITE_URL, safe="")
    sitemap_enc = quote(sitemap_url, safe="")
    url = f"{WEBMASTERS_BASE}/sites/{site_enc}/sitemaps/{sitemap_enc}"
    resp = requests.put(url, headers=make_headers(creds, project_id))
    if resp.status_code == 204:
        print(f"Sitemap submitted: {sitemap_url}")
    else:
        print(f"Error {resp.status_code}: {resp.text[:300]}")
    return resp.status_code == 204


def list_sitemaps(creds, project_id):
    site_enc = quote(SITE_URL, safe="")
    url = f"{WEBMASTERS_BASE}/sites/{site_enc}/sitemaps"
    resp = requests.get(url, headers=make_headers(creds, project_id))
    if resp.status_code == 200:
        data = resp.json()
        sitemaps = data.get("sitemap", [])
        for s in sitemaps:
            path = s.get("path", "")
            last_submitted = s.get("lastSubmitted", "never")
            last_downloaded = s.get("lastDownloaded", "never")
            errors = s.get("errors", 0)
            warnings = s.get("warnings", 0)
            print(f"  {path}")
            print(f"    Submitted: {last_submitted} | Downloaded: {last_downloaded} | Errors: {errors} Warnings: {warnings}")
    else:
        print(f"Error {resp.status_code}: {resp.text[:300]}")


def check_url(creds, project_id, page_url, verbose=True):
    """Use URL Inspection API to check indexing status of a URL."""
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


DASHBOARD_DIR = "/opt/dale/dashboard"
BASE_URL = "https://treestock.com.au"


def discover_new_content_pages():
    """Auto-discover new SEO content pages from the dashboard directory."""
    pages = []

    if not os.path.isdir(DASHBOARD_DIR):
        return NEW_CONTENT_PAGES_FALLBACK

    # All species+state combo pages
    for fname in sorted(os.listdir(DASHBOARD_DIR)):
        if fname.startswith("buy-") and fname.endswith(".html"):
            pages.append(f"{BASE_URL}/{fname}")

    # Special content pages
    for fname in ["companion-planting-guide.html", "when-to-plant.html",
                  "finger-lime-guide.html", "bare-root-2026.html"]:
        path = os.path.join(DASHBOARD_DIR, fname)
        if os.path.exists(path):
            pages.append(f"{BASE_URL}/{fname}")

    return pages


# Fallback list if dashboard dir not accessible
NEW_CONTENT_PAGES_FALLBACK = [
    "https://treestock.com.au/companion-planting-guide.html",
    "https://treestock.com.au/buy-fruit-trees-wa.html",
    "https://treestock.com.au/buy-fruit-trees-qld.html",
    "https://treestock.com.au/buy-fruit-trees-nsw.html",
    "https://treestock.com.au/buy-fruit-trees-vic.html",
]


def bulk_check_urls(creds, project_id, urls, delay=0.5):
    """Check indexing status of multiple URLs, return summary."""
    results = []
    indexed = []
    not_indexed = []
    errors = []

    print(f"Checking {len(urls)} URLs (delay={delay}s between requests)...")
    print()

    for i, url in enumerate(urls, 1):
        result = check_url(creds, project_id, url, verbose=False)
        results.append(result)

        verdict = result["verdict"]
        coverage = result["coverage"]

        if verdict == "PASS":
            indexed.append(url)
            status = "INDEXED"
        elif verdict == "ERROR" or "Error" in coverage:
            errors.append(url)
            status = f"ERROR ({coverage})"
        else:
            not_indexed.append(url)
            status = f"NOT INDEXED ({coverage})"

        print(f"[{i:3d}/{len(urls)}] {status}: {url.replace('https://treestock.com.au/', '')}")

        if i < len(urls):
            time.sleep(delay)

    print()
    print("=" * 60)
    print(f"SUMMARY: {len(indexed)} indexed, {len(not_indexed)} not indexed, {len(errors)} errors")
    print("=" * 60)

    if not_indexed:
        print(f"\nNot indexed ({len(not_indexed)} pages):")
        for url in not_indexed:
            print(f"  {url}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for url in errors:
            print(f"  {url}")

    return results


def main():
    parser = argparse.ArgumentParser(description="GSC URL/Sitemap submission tool")
    parser.add_argument("--list", action="store_true", help="List submitted sitemaps")
    parser.add_argument("--check-url", metavar="URL", help="Check indexing status of a URL")
    parser.add_argument("--bulk-check", action="store_true", help="Check all new content pages")
    parser.add_argument("--urls-file", metavar="FILE", help="File with URLs to check (one per line)")
    parser.add_argument("--sitemap", metavar="URL", default=SITEMAP_URL, help="Sitemap URL to submit")
    args = parser.parse_args()

    creds, project_id = get_credentials()

    if args.list:
        print("Submitted sitemaps:")
        list_sitemaps(creds, project_id)
    elif args.check_url:
        check_url(creds, project_id, args.check_url)
    elif args.bulk_check:
        if args.urls_file:
            with open(args.urls_file) as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        else:
            urls = discover_new_content_pages()
            print(f"Discovered {len(urls)} content pages from {DASHBOARD_DIR}")
        bulk_check_urls(creds, project_id, urls)
    else:
        submit_sitemap(creds, project_id, args.sitemap)


if __name__ == "__main__":
    main()
