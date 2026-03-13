#!/usr/bin/env python3
"""
Build sitemap.xml for treestock.com.au.

Generates a sitemap covering the main pages and all species pages.

Usage:
    python3 build_sitemap.py <species-dir> <output-dir>
"""

import sys
from datetime import datetime, timezone
from pathlib import Path


BASE_URL = "https://treestock.com.au"

STATIC_PAGES = [
    ("", "daily", "1.0"),        # Homepage
    ("digest.html", "daily", "0.8"),
    ("history.html", "daily", "0.7"),
    ("species/", "weekly", "0.8"),
]


def build_sitemap(species_dir: Path, output_dir: Path) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urls = []

    # Static pages
    for path, changefreq, priority in STATIC_PAGES:
        loc = f"{BASE_URL}/{path}" if path else BASE_URL + "/"
        urls.append(f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>""")

    # Species pages
    if species_dir.exists():
        for html_file in sorted(species_dir.glob("*.html")):
            if html_file.name == "index.html":
                continue  # already in static pages as species/
            slug = html_file.stem
            loc = f"{BASE_URL}/species/{html_file.name}"
            urls.append(f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.6</priority>
  </url>""")

    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
    sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "\n".join(urls)
    sitemap += "\n</urlset>\n"

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "sitemap.xml"
    out_file.write_text(sitemap)
    print(f"Sitemap written: {out_file} ({len(urls)} URLs)")


def main():
    if len(sys.argv) < 3:
        print("Usage: build_sitemap.py <species-dir> <output-dir>")
        sys.exit(1)

    species_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    build_sitemap(species_dir, output_dir)


if __name__ == "__main__":
    main()
