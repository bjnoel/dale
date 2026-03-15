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
    ("nursery/", "weekly", "0.8"),
    ("buy-fruit-trees-wa.html", "daily", "0.7"),
    ("buy-fruit-trees-qld.html", "daily", "0.7"),
    ("buy-fruit-trees-nsw.html", "daily", "0.7"),
    ("buy-fruit-trees-vic.html", "daily", "0.7"),
    ("compare/", "weekly", "0.8"),
    ("rare.html", "daily", "0.8"),
    ("variety/", "weekly", "0.7"),
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

    # Nursery profile pages (dynamically scanned)
    nursery_dir = output_dir / "nursery"
    if nursery_dir.exists():
        for html_file in sorted(nursery_dir.glob("*.html")):
            if html_file.name == "index.html":
                continue  # already in static pages as nursery/
            loc = f"{BASE_URL}/nursery/{html_file.name}"
            urls.append(f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.7</priority>
  </url>""")

    # Compare pages (price comparison, dynamically scanned)
    compare_dir = output_dir / "compare"
    if compare_dir.exists():
        for html_file in sorted(compare_dir.glob("*.html")):
            if html_file.name == "index.html":
                continue  # already in static pages as compare/
            loc = f"{BASE_URL}/compare/{html_file.name}"
            urls.append(f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.7</priority>
  </url>""")

    # Variety pages (cultivar-level, dynamically scanned)
    variety_dir = output_dir / "variety"
    if variety_dir.exists():
        for html_file in sorted(variety_dir.glob("*.html")):
            if html_file.name == "index.html":
                continue  # already in static pages as variety/
            loc = f"{BASE_URL}/variety/{html_file.name}"
            urls.append(f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.6</priority>
  </url>""")

    # Species pages
    if species_dir.exists():
        for html_file in sorted(species_dir.glob("*.html")):
            if html_file.name == "index.html":
                continue  # already in static pages as species/
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
