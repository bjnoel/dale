#!/usr/bin/env python3
"""
Fortnightly GSC page-review generator (DAL-143)

Selects top-5 pages from GSC by impressions, prioritising pages that have never
been reviewed. For each page, generates a review brief: current metrics, top
queries, opportunity queries (pos 11-30), content snapshot, and recommended
improvement actions.

Usage:
    python3 gsc_page_review.py                  # Generate report, post to Linear
    python3 gsc_page_review.py --dry-run        # Print to stdout, no Linear post
    python3 gsc_page_review.py --pages 10       # Review top 10 instead of 5
    python3 gsc_page_review.py --days 28        # Use last 28 days of GSC data
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from html.parser import HTMLParser

from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

REVIEW_LOG_PATH = "/opt/dale/data/page_review_log.json"
REVIEW_OUTPUT_DIR = "/opt/dale/data/page_reviews"
DASHBOARD_DIR = "/opt/dale/dashboard"
GSC_REPORT_PATH = "/opt/dale/data/gsc_report.json"
CREDENTIALS_PATH = "/opt/dale/secrets/gsc-credentials.json"
SITE_URL = "sc-domain:treestock.com.au"
SITE_BASE = "https://treestock.com.au"
LINEAR_SCRIPT = "/opt/dale/autonomous/linear_update.py"

# CTR benchmarks by average position (industry approximations)
# If actual CTR < UNDERPERFORM_THRESHOLD * expected, flag it
CTR_BENCHMARKS = [
    (1.5, 0.28), (2.5, 0.15), (3.5, 0.10), (4.5, 0.07), (5.5, 0.05),
    (7.5, 0.04), (10.5, 0.025), (15.5, 0.015), (20.5, 0.008), (float("inf"), 0.004),
]
UNDERPERFORM_THRESHOLD = 0.45  # flag if CTR < 45% of expected


def expected_ctr(position):
    for threshold, ctr in CTR_BENCHMARKS:
        if position <= threshold:
            return ctr
    return 0.004


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
    )
    return build("searchconsole", "v1", credentials=creds)


def normalise_url(url):
    """Normalise www/non-www to canonical base."""
    return url.replace("https://www.treestock.com.au", SITE_BASE)


def url_to_local_path(url):
    """Map a treestock.com.au URL to its local HTML file path."""
    url = normalise_url(url)
    path = url.replace(SITE_BASE, "").lstrip("/")
    if not path or path == "index.html":
        path = "index.html"
    return os.path.join(DASHBOARD_DIR, path)


def load_review_log():
    if os.path.exists(REVIEW_LOG_PATH):
        with open(REVIEW_LOG_PATH) as f:
            return json.load(f)
    return {"pages": {}, "last_run": None}


def save_review_log(log):
    os.makedirs(os.path.dirname(REVIEW_LOG_PATH), exist_ok=True)
    with open(REVIEW_LOG_PATH, "w") as f:
        json.dump(log, f, indent=2)


def score_page(url, impressions, review_log):
    """
    Return a sort key (lower = higher priority).
    Priority: never-reviewed first, then oldest-reviewed, within each group
    sort by impressions (descending).
    """
    normalised = normalise_url(url)
    record = review_log["pages"].get(normalised, {})
    last_reviewed = record.get("last_reviewed")

    if last_reviewed is None:
        # Never reviewed: top priority (0), sort by impressions desc
        return (0, -impressions)
    else:
        # Reviewed before: sort by how long ago (older = higher priority)
        days_since = (datetime.utcnow().date() - datetime.fromisoformat(last_reviewed).date()).days
        return (1, -days_since, -impressions)


def query_page_queries(service, page_url, start_date, end_date, row_limit=50):
    """Fetch top queries for a specific page from GSC."""
    # Use both www and non-www variants to catch all data
    urls_to_try = [normalise_url(page_url), page_url.replace(SITE_BASE, "https://www.treestock.com.au")]
    combined = {}

    for url_variant in urls_to_try:
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": ["query"],
            "dimensionFilterGroups": [{
                "filters": [{
                    "dimension": "page",
                    "operator": "equals",
                    "expression": url_variant,
                }]
            }],
            "rowLimit": row_limit,
        }
        try:
            resp = (
                service.searchanalytics()
                .query(siteUrl=SITE_URL, body=body)
                .execute()
            )
            for row in resp.get("rows", []):
                q = row["keys"][0]
                if q not in combined:
                    combined[q] = row
                else:
                    # Merge impressions/clicks
                    combined[q]["impressions"] += row["impressions"]
                    combined[q]["clicks"] += row["clicks"]
        except HttpError as e:
            print(f"  WARNING: GSC query failed for {url_variant}: {e}", file=sys.stderr)

    rows = list(combined.values())
    rows.sort(key=lambda r: r["impressions"], reverse=True)
    return rows


class ContentExtractor(HTMLParser):
    """Extract title, meta description, h1s, body text, and internal links from HTML."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta_description = ""
        self.h1s = []
        self.h2s = []
        self.text_chunks = []
        self.internal_links = 0
        self.external_links = 0
        self._in_title = False
        self._in_h1 = False
        self._in_h2 = False
        self._in_body = False
        self._skip_tags = {"script", "style", "noscript"}
        self._skip_depth = 0
        self._current_h1 = []
        self._current_h2 = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in self._skip_tags:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and attrs_dict.get("name", "").lower() == "description":
            self.meta_description = attrs_dict.get("content", "")
        elif tag == "body":
            self._in_body = True
        elif tag == "h1":
            self._in_h1 = True
            self._current_h1 = []
        elif tag == "h2":
            self._in_h2 = True
            self._current_h2 = []
        elif tag == "a" and self._in_body:
            href = attrs_dict.get("href", "")
            if href.startswith("/") or "treestock.com.au" in href:
                self.internal_links += 1
            elif href.startswith("http"):
                self.external_links += 1

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
            if self._current_h1:
                self.h1s.append(" ".join(self._current_h1).strip())
        elif tag == "h2":
            self._in_h2 = False
            if self._current_h2:
                self.h2s.append(" ".join(self._current_h2).strip())

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title += text
        if self._in_h1:
            self._current_h1.append(text)
        if self._in_h2:
            self._current_h2.append(text)
        if self._in_body and text:
            self.text_chunks.append(text)

    @property
    def word_count(self):
        full_text = " ".join(self.text_chunks)
        return len(re.findall(r"\b\w+\b", full_text))


def extract_page_content(local_path):
    """Extract title, meta desc, h1, word count, link counts from an HTML file."""
    if not os.path.exists(local_path):
        return None
    try:
        with open(local_path, encoding="utf-8") as f:
            html = f.read()
        parser = ContentExtractor()
        parser.feed(html)
        return {
            "title": parser.title.strip(),
            "meta_description": parser.meta_description.strip(),
            "h1": parser.h1s[0] if parser.h1s else "",
            "h1_count": len(parser.h1s),
            "h2_count": len(parser.h2s),
            "h2_sample": parser.h2s[:4],
            "word_count": parser.word_count,
            "internal_links": parser.internal_links,
            "external_links": parser.external_links,
        }
    except Exception as e:
        return {"error": str(e)}


def build_recommendations(gsc_metrics, page_queries, content):
    """
    Generate a prioritised list of recommended improvements for a page.

    gsc_metrics: dict with clicks, impressions, ctr, position
    page_queries: list of query rows for this page
    content: dict from extract_page_content
    """
    recs = []

    if gsc_metrics:
        pos = gsc_metrics.get("position", 0)
        ctr = gsc_metrics.get("ctr", 0)
        impressions = gsc_metrics.get("impressions", 0)
        clicks = gsc_metrics.get("clicks", 0)

        expected = expected_ctr(pos) if pos > 0 else 0
        if impressions >= 20 and pos > 0 and ctr < UNDERPERFORM_THRESHOLD * expected:
            recs.append(
                f"CTR underperforming: {ctr*100:.1f}% actual vs "
                f"{expected*100:.1f}% expected at pos {pos:.1f}. "
                f"Improve title and meta description to better match search intent."
            )

        # High position but zero clicks
        if impressions >= 50 and clicks == 0 and pos <= 15:
            recs.append(
                f"Zero clicks despite {impressions} impressions at pos {pos:.1f}. "
                f"Title or meta description may not match user intent — rewrite both."
            )

    # Opportunity queries: pos 11-30, >= 3 impressions
    opportunity = [
        q for q in page_queries
        if 10 < q.get("position", 999) <= 30 and q.get("impressions", 0) >= 3
    ]
    if opportunity:
        top_opps = sorted(opportunity, key=lambda r: r["impressions"], reverse=True)[:3]
        for opp in top_opps:
            q = opp["keys"][0]
            recs.append(
                f"Opportunity query: '{q}' ranks pos {opp['position']:.1f} "
                f"({opp['impressions']} impr, {opp['clicks']} clicks). "
                f"Add a section or improve existing coverage of this topic."
            )

    if content:
        wc = content.get("word_count", 0)
        if wc < 200:
            recs.append(
                f"Thin content: only ~{wc} words. Add substantive content (aim for 400+) "
                f"to give Google more signals and users more value."
            )
        elif wc < 400:
            recs.append(
                f"Moderate content depth: ~{wc} words. Consider expanding with more detail, "
                f"FAQs, or related species/product coverage."
            )

        if not content.get("meta_description"):
            recs.append("Missing meta description. Add a 150-160 character description targeting primary keywords.")

        if content.get("h1_count", 0) == 0:
            recs.append("No H1 found. Ensure the page has exactly one H1 with the primary keyword.")
        elif content.get("h1_count", 0) > 1:
            recs.append(f"Multiple H1s ({content['h1_count']}). Consolidate to exactly one H1.")

        if content.get("internal_links", 0) < 3:
            recs.append(
                f"Only {content.get('internal_links', 0)} internal links. Add more internal links "
                f"to related species, nurseries, or guides."
            )

    if not recs:
        recs.append("Page appears well-optimised. No immediate improvements identified.")

    return recs


def format_review_brief(pages_data, review_date):
    """Format the full markdown review brief."""
    lines = [
        f"# GSC Page Review Brief — {review_date}",
        "",
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"Pages reviewed: {len(pages_data)}",
        "",
        "This fortnightly review identifies the top pages by GSC impressions, prioritising "
        "pages that have never been reviewed. Each entry includes current metrics, per-page "
        "queries, content snapshot, and specific improvement recommendations.",
        "",
        "---",
        "",
    ]

    for i, pd in enumerate(pages_data, 1):
        url = pd["url"]
        path = url.replace(SITE_BASE, "") or "/"
        gsc = pd.get("gsc_metrics", {})
        queries = pd.get("top_queries", [])
        opportunity = pd.get("opportunity_queries", [])
        content = pd.get("content", {})
        recs = pd.get("recommendations", [])
        last_reviewed = pd.get("last_reviewed", "Never")

        lines.append(f"## {i}. `{path}`")
        lines.append("")
        lines.append(f"**Last reviewed:** {last_reviewed}")
        lines.append(f"**URL:** {url}")
        lines.append("")

        # GSC metrics
        if gsc:
            lines.append("**GSC metrics (last 28 days):**")
            lines.append(
                f"- Impressions: {gsc.get('impressions', 0):,} | "
                f"Clicks: {gsc.get('clicks', 0):,} | "
                f"CTR: {gsc.get('ctr', 0)*100:.1f}% | "
                f"Avg Position: {gsc.get('position', 0):.1f}"
            )
            lines.append("")

        # Top queries for this page
        if queries:
            lines.append("**Top queries driving this page:**")
            lines.append("")
            lines.append("| Query | Impr | Clicks | CTR | Pos |")
            lines.append("|-------|------|--------|-----|-----|")
            for q in queries[:8]:
                qtext = q["keys"][0]
                lines.append(
                    f"| {qtext} | {q['impressions']} | {q['clicks']} | "
                    f"{q['ctr']*100:.1f}% | {q['position']:.1f} |"
                )
            lines.append("")

        # Opportunity queries
        if opportunity:
            lines.append("**Opportunity queries (pos 11-30, 3+ impressions):**")
            lines.append("")
            lines.append("| Query | Impr | Clicks | Pos |")
            lines.append("|-------|------|--------|-----|")
            for q in opportunity[:5]:
                qtext = q["keys"][0]
                lines.append(
                    f"| {qtext} | {q['impressions']} | {q['clicks']} | {q['position']:.1f} |"
                )
            lines.append("")

        # Content snapshot
        if content and not content.get("error"):
            lines.append("**Content snapshot:**")
            lines.append(f"- Title: {content.get('title', '(none)')}")
            lines.append(f"- Meta desc: {content.get('meta_description', '(none)')[:100]}")
            lines.append(f"- H1: {content.get('h1', '(none)')}")
            if content.get("h2_sample"):
                lines.append(f"- H2s: {', '.join(content['h2_sample'][:3])}")
            lines.append(
                f"- Word count: ~{content.get('word_count', 0):,} | "
                f"Internal links: {content.get('internal_links', 0)}"
            )
            lines.append("")
        elif content and content.get("error"):
            lines.append(f"**Content snapshot:** ERROR reading file: {content['error']}")
            lines.append("")
        else:
            lines.append("**Content snapshot:** HTML file not found locally")
            lines.append("")

        # Recommendations
        lines.append("**Recommended actions:**")
        lines.append("")
        for rec in recs:
            lines.append(f"- [ ] {rec}")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def post_to_linear(report_md, report_date, dry_run=False):
    """Create a Linear ticket with the review brief."""
    if dry_run:
        print("[DRY RUN] Would create Linear ticket: GSC page review - {report_date}")
        return None

    title = f"treestock: GSC page review - {report_date}"
    description = (
        f"Fortnightly page review generated by gsc_page_review.py.\n\n"
        f"Review the recommendations below and action the highest-priority items.\n\n"
        f"{report_md[:4000]}"  # Linear description has limits
    )

    try:
        result = subprocess.run(
            [
                sys.executable,
                LINEAR_SCRIPT,
                "create",
                title,
                "--description", description,
                "--labels", "SEO,Track B",
                "--priority", "3",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            ticket_id = result.stdout.strip().split()[-1] if result.stdout else "unknown"
            print(f"Created Linear ticket: {ticket_id}")
            return ticket_id
        else:
            print(f"WARNING: Linear create failed: {result.stderr[:200]}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"WARNING: Could not create Linear ticket: {e}", file=sys.stderr)
        return None


def run_review(pages=5, days=28, dry_run=False):
    today = datetime.utcnow().date()
    end_date = today - timedelta(days=3)  # 3-day GSC lag
    start_date = end_date - timedelta(days=days - 1)
    start_str, end_str = str(start_date), str(end_date)

    print(f"=== GSC Page Review: treestock.com.au ===")
    print(f"Date: {today} | GSC period: {start_str} to {end_str} ({days} days)")
    print(f"Selecting top-{pages} pages (prioritising never-reviewed)")
    print()

    # Load GSC report (use cached if < 1 day old, otherwise re-query)
    gsc_data = None
    if os.path.exists(GSC_REPORT_PATH):
        with open(GSC_REPORT_PATH) as f:
            gsc_data = json.load(f)
        age_hours = (datetime.utcnow() - datetime.fromisoformat(
            gsc_data.get("generated_at", "2000-01-01")
        )).total_seconds() / 3600
        if age_hours > 25:
            print(f"  Cached GSC report is {age_hours:.0f}h old, will use it (live re-query not needed for page list)")

    if not gsc_data:
        print("ERROR: No GSC report found at", GSC_REPORT_PATH)
        print("Run gsc_analysis.py first.")
        sys.exit(1)

    all_pages = gsc_data.get("top_pages_by_impressions", [])
    if not all_pages:
        print("ERROR: No page data in GSC report.")
        sys.exit(1)

    print(f"Found {len(all_pages)} pages in GSC report.")

    # Load review log
    review_log = load_review_log()
    print(f"Review log: {len(review_log['pages'])} pages tracked. Last run: {review_log.get('last_run', 'never')}")
    print()

    # Sort pages by priority
    candidates = []
    for row in all_pages:
        url = normalise_url(row["page"])
        score = score_page(url, row["impressions"], review_log)
        candidates.append((score, row))

    candidates.sort(key=lambda x: x[0])
    selected = [row for _, row in candidates[:pages]]

    print(f"Selected {len(selected)} pages for review:")
    for row in selected:
        url = normalise_url(row["page"])
        last = review_log["pages"].get(url, {}).get("last_reviewed", "NEVER")
        print(f"  {url.replace(SITE_BASE, '')} | {row['impressions']} impr | last reviewed: {last}")
    print()

    # Get live GSC service for per-page query lookups
    try:
        service = get_service()
    except Exception as e:
        print(f"ERROR: Could not authenticate with GSC: {e}")
        sys.exit(1)

    # Build review data for each page
    pages_data = []
    for i, row in enumerate(selected):
        url = normalise_url(row["page"])
        path = url.replace(SITE_BASE, "") or "/"
        print(f"[{i+1}/{len(selected)}] Analysing {path} ...")

        gsc_metrics = {
            "clicks": row["clicks"],
            "impressions": row["impressions"],
            "ctr": row["ctr"],
            "position": row["position"],
        }

        # Per-page query breakdown from GSC
        print(f"  Fetching per-page queries from GSC ...")
        page_queries = query_page_queries(service, url, start_str, end_str)
        opportunity_queries = [
            q for q in page_queries
            if 10 < q.get("position", 999) <= 30 and q.get("impressions", 0) >= 3
        ]
        opportunity_queries.sort(key=lambda r: r["impressions"], reverse=True)
        print(f"  {len(page_queries)} queries, {len(opportunity_queries)} opportunities")

        # Content extraction
        local_path = url_to_local_path(url)
        content = extract_page_content(local_path)
        if content and not content.get("error"):
            print(f"  Content: ~{content['word_count']} words, {content['internal_links']} internal links")
        else:
            print(f"  Content: not found at {local_path}")

        # Recommendations
        recs = build_recommendations(gsc_metrics, page_queries, content)

        last_reviewed = review_log["pages"].get(url, {}).get("last_reviewed", "Never")

        pages_data.append({
            "url": url,
            "gsc_metrics": gsc_metrics,
            "top_queries": page_queries[:10],
            "opportunity_queries": opportunity_queries[:5],
            "content": content,
            "recommendations": recs,
            "last_reviewed": last_reviewed,
        })

        # Throttle to avoid GSC quota
        if i < len(selected) - 1:
            time.sleep(0.5)

    print()

    # Generate markdown report
    review_date = str(today)
    report_md = format_review_brief(pages_data, review_date)

    # Save to disk
    if not dry_run:
        os.makedirs(REVIEW_OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(REVIEW_OUTPUT_DIR, f"{review_date}.md")
        with open(output_path, "w") as f:
            f.write(report_md)
        print(f"Report saved: {output_path}")
    else:
        print("=== REPORT (dry run) ===")
        print(report_md)
        return

    # Update review log
    for pd in pages_data:
        url = pd["url"]
        if url not in review_log["pages"]:
            review_log["pages"][url] = {}
        review_log["pages"][url]["last_reviewed"] = review_date
        review_log["pages"][url]["review_count"] = review_log["pages"][url].get("review_count", 0) + 1
        review_log["pages"][url]["last_impressions"] = pd["gsc_metrics"].get("impressions", 0)

    review_log["last_run"] = datetime.utcnow().isoformat()
    save_review_log(review_log)
    print(f"Review log updated: {REVIEW_LOG_PATH}")

    # Post to Linear
    ticket_id = post_to_linear(report_md, review_date, dry_run=dry_run)

    print()
    print(f"=== Done: {len(pages_data)} pages reviewed ===")
    if ticket_id:
        print(f"Linear ticket: {ticket_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fortnightly GSC page review generator")
    parser.add_argument("--pages", type=int, default=5, help="Number of pages to review (default: 5)")
    parser.add_argument("--days", type=int, default=28, help="Days of GSC data to analyse (default: 28)")
    parser.add_argument("--dry-run", action="store_true", help="Print report to stdout, do not save or post to Linear")
    args = parser.parse_args()

    run_review(pages=args.pages, days=args.days, dry_run=args.dry_run)
