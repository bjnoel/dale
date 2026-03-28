#!/usr/bin/env python3
"""
GSC Sitemap and URL submission for treestock.com.au
Uses OAuth credentials with refresh token (no interactive auth needed).

Usage:
    python3 gsc_submit.py                          # Submit/refresh sitemap
    python3 gsc_submit.py --list                   # List submitted sitemaps
    python3 gsc_submit.py --check-url <url>        # Check if URL is indexed

Authentication: gsc-oauth-credentials.json (has refresh_token, no interactive auth needed)
Quota project: dale-490702 (required for GSC API calls)
"""

import argparse
import json
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


def check_url(creds, project_id, page_url):
    """Use URL Inspection API to check indexing status of a URL."""
    # URL Inspection API endpoint
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
        print(f"URL: {page_url}")
        print(f"  Verdict: {verdict}")
        print(f"  Coverage: {coverage}")
        print(f"  Last crawled: {crawled}")
    else:
        print(f"Error {resp.status_code}: {resp.text[:300]}")


def main():
    parser = argparse.ArgumentParser(description="GSC URL/Sitemap submission tool")
    parser.add_argument("--list", action="store_true", help="List submitted sitemaps")
    parser.add_argument("--check-url", metavar="URL", help="Check indexing status of a URL")
    parser.add_argument("--sitemap", metavar="URL", default=SITEMAP_URL, help="Sitemap URL to submit")
    args = parser.parse_args()

    creds, project_id = get_credentials()

    if args.list:
        print("Submitted sitemaps:")
        list_sitemaps(creds, project_id)
    elif args.check_url:
        check_url(creds, project_id, args.check_url)
    else:
        submit_sitemap(creds, project_id, args.sitemap)


if __name__ == "__main__":
    main()
