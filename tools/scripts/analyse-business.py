#!/usr/bin/env python3
"""
Business Online Presence Analyser

Given a business URL, performs automated analysis of:
- Website quality (mobile, speed, SEO basics)
- Google Business Profile presence
- Social media presence
- Review analysis
- Technology stack detection

Outputs a JSON file that can feed into the report generator.

Usage: python3 analyse-business.py https://example.com "Business Name"
"""

import json
import sys
import subprocess
import re
from urllib.parse import urlparse
from datetime import date


def check_dependency(cmd, name):
    """Check if a command-line tool is available."""
    try:
        subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print(f"Warning: {name} not found. Some checks will be skipped.")
        return False


def fetch_page(url, timeout=15):
    """Fetch a page and return (status_code, headers, body)."""
    try:
        result = subprocess.run(
            ["curl", "-sL", "-o", "-", "-w", "\n%{http_code}", "-m", str(timeout),
             "-H", "User-Agent: Mozilla/5.0 (compatible; WalkthroughBot/1.0; +https://walkthrough.au)",
             url],
            capture_output=True, text=True, timeout=timeout + 5
        )
        lines = result.stdout.rsplit("\n", 1)
        body = lines[0] if len(lines) > 1 else result.stdout
        status = int(lines[-1]) if len(lines) > 1 else 0
        return status, body
    except Exception as e:
        return 0, str(e)


def analyse_html(html):
    """Basic HTML analysis without external dependencies."""
    findings = {}

    # Title tag
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    findings["has_title"] = bool(title_match)
    findings["title"] = title_match.group(1).strip() if title_match else None
    findings["title_length"] = len(findings["title"]) if findings["title"] else 0

    # Meta description
    desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', html, re.IGNORECASE)
    if not desc_match:
        desc_match = re.search(r'<meta[^>]*content=["\'](.*?)["\'][^>]*name=["\']description["\']', html, re.IGNORECASE)
    findings["has_meta_description"] = bool(desc_match)
    findings["meta_description_length"] = len(desc_match.group(1)) if desc_match else 0

    # Mobile viewport
    findings["has_viewport"] = bool(re.search(r'<meta[^>]*name=["\']viewport["\']', html, re.IGNORECASE))

    # HTTPS
    findings["uses_https"] = False  # set by caller

    # Common platforms
    platforms = []
    if "shopify" in html.lower() or "cdn.shopify" in html.lower():
        platforms.append("Shopify")
    if "woocommerce" in html.lower() or "wp-content" in html.lower():
        platforms.append("WordPress/WooCommerce")
    if "squarespace" in html.lower():
        platforms.append("Squarespace")
    if "wix.com" in html.lower():
        platforms.append("Wix")
    if "square" in html.lower() and "squareup" in html.lower():
        platforms.append("Square Online")
    findings["platforms_detected"] = platforms

    # Social links
    socials = {
        "facebook": bool(re.search(r'facebook\.com/', html, re.IGNORECASE)),
        "instagram": bool(re.search(r'instagram\.com/', html, re.IGNORECASE)),
        "twitter": bool(re.search(r'(twitter|x)\.com/', html, re.IGNORECASE)),
        "linkedin": bool(re.search(r'linkedin\.com/', html, re.IGNORECASE)),
        "tiktok": bool(re.search(r'tiktok\.com/', html, re.IGNORECASE)),
    }
    findings["social_links"] = socials

    # Schema/structured data
    findings["has_schema"] = bool(re.search(r'application/ld\+json', html, re.IGNORECASE))

    # Images without alt text (rough check)
    all_imgs = re.findall(r'<img[^>]*>', html, re.IGNORECASE)
    imgs_without_alt = [img for img in all_imgs if 'alt=' not in img.lower() or 'alt=""' in img.lower()]
    findings["total_images"] = len(all_imgs)
    findings["images_missing_alt"] = len(imgs_without_alt)

    # Page size
    findings["page_size_kb"] = round(len(html) / 1024, 1)

    return findings


def check_google_business(business_name, location="Perth"):
    """Check for Google Business presence (basic search check)."""
    # We can't reliably scrape Google, but we can note this needs manual checking
    return {
        "note": f"Manual check needed: search Google for '{business_name} {location}' and check the business panel",
        "checklist": [
            "Is there a Google Business listing?",
            "Are hours listed and current?",
            "Are there recent photos?",
            "How many reviews? What's the average rating?",
            "Are reviews being responded to?",
            "Is the business description filled in?",
            "Are services/products listed?"
        ]
    }


def generate_analysis(url, business_name):
    """Run full analysis and return structured data."""
    parsed = urlparse(url)
    domain = parsed.hostname

    print(f"Analysing {business_name} ({url})...")

    analysis = {
        "business_name": business_name,
        "url": url,
        "domain": domain,
        "analysis_date": date.today().isoformat(),
        "website": {},
        "google_business": {},
        "issues": [],
        "opportunities": []
    }

    # Fetch main page
    print("  Fetching main page...")
    status, html = fetch_page(url)
    analysis["website"]["status_code"] = status
    analysis["website"]["reachable"] = status == 200

    if status != 200:
        analysis["issues"].append({
            "severity": "critical",
            "area": "website",
            "issue": f"Website returned HTTP {status} — may be down or misconfigured"
        })
        return analysis

    # HTML analysis
    print("  Analysing HTML...")
    html_findings = analyse_html(html)
    html_findings["uses_https"] = parsed.scheme == "https"
    analysis["website"].update(html_findings)

    # Generate issues from findings
    if not html_findings["uses_https"]:
        analysis["issues"].append({
            "severity": "high",
            "area": "security",
            "issue": "Website not using HTTPS — browsers show 'Not Secure' warning"
        })

    if not html_findings["has_viewport"]:
        analysis["issues"].append({
            "severity": "high",
            "area": "mobile",
            "issue": "No mobile viewport meta tag — site likely broken on phones"
        })

    if not html_findings["has_title"] or html_findings["title_length"] < 10:
        analysis["issues"].append({
            "severity": "medium",
            "area": "seo",
            "issue": "Missing or very short page title — hurts search rankings"
        })

    if not html_findings["has_meta_description"]:
        analysis["issues"].append({
            "severity": "medium",
            "area": "seo",
            "issue": "No meta description — Google will use random page text in search results"
        })

    if html_findings["images_missing_alt"] > 0:
        pct = round(html_findings["images_missing_alt"] / max(html_findings["total_images"], 1) * 100)
        analysis["issues"].append({
            "severity": "low",
            "area": "accessibility",
            "issue": f"{html_findings['images_missing_alt']} of {html_findings['total_images']} images missing alt text ({pct}%)"
        })

    if not html_findings["has_schema"]:
        analysis["opportunities"].append({
            "area": "seo",
            "opportunity": "Add structured data (Schema.org) to improve Google search appearance"
        })

    active_socials = [k for k, v in html_findings["social_links"].items() if v]
    missing_socials = [k for k, v in html_findings["social_links"].items() if not v]
    if missing_socials:
        analysis["opportunities"].append({
            "area": "social",
            "opportunity": f"Missing social links: {', '.join(missing_socials)}. Active: {', '.join(active_socials) or 'none'}"
        })

    # Google Business check
    analysis["google_business"] = check_google_business(business_name)

    # Check robots.txt
    print("  Checking robots.txt...")
    robots_status, robots_body = fetch_page(f"{parsed.scheme}://{domain}/robots.txt")
    analysis["website"]["has_robots_txt"] = robots_status == 200

    # Check sitemap
    print("  Checking sitemap...")
    sitemap_status, _ = fetch_page(f"{parsed.scheme}://{domain}/sitemap.xml")
    analysis["website"]["has_sitemap"] = sitemap_status == 200
    if not analysis["website"]["has_sitemap"]:
        analysis["opportunities"].append({
            "area": "seo",
            "opportunity": "No sitemap.xml found — add one to help Google index your pages"
        })

    return analysis


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 analyse-business.py <url> <business_name>")
        print("Example: python3 analyse-business.py https://example.com.au 'Joe\\'s Coffee'")
        sys.exit(1)

    url = sys.argv[1]
    business_name = sys.argv[2]

    if not url.startswith("http"):
        url = f"https://{url}"

    analysis = generate_analysis(url, business_name)

    # Output
    output_file = f"data/analyses/{urlparse(url).hostname}-{date.today().isoformat()}.json"
    import os
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(analysis, f, indent=2)

    print(f"\nAnalysis saved to: {output_file}")
    print(f"\nSummary:")
    print(f"  Issues found: {len(analysis['issues'])}")
    print(f"  Opportunities: {len(analysis['opportunities'])}")
    if analysis["issues"]:
        print(f"\n  Top issues:")
        for issue in sorted(analysis["issues"], key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}[x["severity"]]):
            print(f"    [{issue['severity'].upper()}] {issue['issue']}")


if __name__ == "__main__":
    main()
