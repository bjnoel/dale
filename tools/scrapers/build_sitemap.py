#!/usr/bin/env python3
"""
Build a sitemap index + per-section sitemaps for treestock.com.au.

Layout:
    sitemap.xml                  -- sitemap index referencing the sub-sitemaps
    sitemaps/static.xml          -- homepage, guides, section index pages
    sitemaps/species.xml         -- species/*.html
    sitemaps/nursery.xml         -- nursery/*.html
    sitemaps/compare.xml         -- compare/*.html
    sitemaps/locations.xml       -- buy-*-trees-*.html (state + species/state combos)
    sitemaps/variety.xml         -- variety/*.html (the bulk of the URLs)

Per-URL <lastmod> is derived from the HTML file's mtime, so Google sees a
real freshness signal rather than a blanket "today" stamp.

Usage:
    python3 build_sitemap.py <species-dir> <output-dir>
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape


BASE_URL = "https://treestock.com.au"


# Static / hand-curated pages. (path, changefreq, priority).
# Path is relative to the site root; "" means the homepage.
STATIC_PAGES = [
    ("", "daily", "1.0"),
    ("digest.html", "daily", "0.8"),
    ("history.html", "daily", "0.7"),
    ("species/", "weekly", "0.8"),
    ("nursery/", "weekly", "0.8"),
    ("compare/", "weekly", "0.8"),
    ("variety/", "weekly", "0.7"),
    ("rare.html", "daily", "0.8"),
    ("sample-digest.html", "daily", "0.6"),
    ("guide.html", "monthly", "0.7"),
    ("finger-lime-guide.html", "monthly", "0.8"),
    ("when-to-plant.html", "monthly", "0.8"),
    ("companion-planting-guide.html", "monthly", "0.8"),
    ("wa-rare-fruit-guide.html", "monthly", "0.8"),
    ("advertise.html", "monthly", "0.4"),
]

# State landing pages live in their own section so the locations sub-sitemap
# is self-contained.
STATE_LANDING_PAGES = [
    ("buy-fruit-trees-wa.html", "daily", "0.7"),
    ("buy-fruit-trees-qld.html", "daily", "0.7"),
    ("buy-fruit-trees-nsw.html", "daily", "0.7"),
    ("buy-fruit-trees-vic.html", "daily", "0.7"),
]

COMBO_PATTERN = re.compile(r"^buy-.+-trees-.+\.html$")
LOCATION_PAGE_PATTERN = re.compile(r"^buy-fruit-trees-(wa|qld|nsw|vic)\.html$")


# ---------------------------------------------------------------------------
# Helpers

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _file_lastmod(path: Path, fallback: str) -> str:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return fallback
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _resolve_static_file(output_dir: Path, species_dir: Path, rel_path: str) -> Path:
    """Map a STATIC_PAGES path to the HTML file that backs it (for mtime)."""
    if rel_path == "":
        return output_dir / "index.html"
    if rel_path == "species/":
        return species_dir / "index.html"
    if rel_path.endswith("/"):
        return output_dir / rel_path / "index.html"
    return output_dir / rel_path


def _url_xml(loc: str, lastmod: str, changefreq: str, priority: str) -> str:
    return (
        "  <url>\n"
        f"    <loc>{escape(loc)}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        "  </url>"
    )


def _write_urlset(path: Path, entries: list[tuple[str, str, str, str]]) -> str:
    """Write an urlset sitemap. Returns the max lastmod across entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    body += "\n".join(_url_xml(*e) for e in entries)
    body += "\n</urlset>\n"
    path.write_text(body)
    return max((e[1] for e in entries), default=_today())


def _write_index(path: Path, sections: list[tuple[str, str]]) -> None:
    """sections: list of (sitemap_loc, lastmod)."""
    body = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body += '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, lastmod in sections:
        body += (
            "  <sitemap>\n"
            f"    <loc>{escape(loc)}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            "  </sitemap>\n"
        )
    body += "</sitemapindex>\n"
    path.write_text(body)


# ---------------------------------------------------------------------------
# Section collectors

def _collect_static(output_dir: Path, species_dir: Path) -> list:
    today = _today()
    out = []
    for rel, changefreq, priority in STATIC_PAGES:
        loc = f"{BASE_URL}/{rel}" if rel else f"{BASE_URL}/"
        backing = _resolve_static_file(output_dir, species_dir, rel)
        out.append((loc, _file_lastmod(backing, today), changefreq, priority))
    return out


def _collect_dir(output_dir: Path, subdir: str, changefreq: str, priority: str) -> list:
    """Generic collector for a flat directory of *.html (excluding index.html)."""
    today = _today()
    d = output_dir / subdir
    if not d.exists():
        return []
    out = []
    for html_file in sorted(d.glob("*.html")):
        if html_file.name == "index.html":
            continue
        loc = f"{BASE_URL}/{subdir}/{html_file.name}"
        out.append((loc, _file_lastmod(html_file, today), changefreq, priority))
    return out


def _collect_species(species_dir: Path) -> list:
    today = _today()
    if not species_dir.exists():
        return []
    out = []
    for html_file in sorted(species_dir.glob("*.html")):
        if html_file.name == "index.html":
            continue
        loc = f"{BASE_URL}/species/{html_file.name}"
        out.append((loc, _file_lastmod(html_file, today), "weekly", "0.6"))
    return out


def _collect_locations(output_dir: Path) -> list:
    """State landing pages + species/state combo pages."""
    today = _today()
    out = []
    # State landing pages (always included; mtime if present).
    for filename, changefreq, priority in STATE_LANDING_PAGES:
        backing = output_dir / filename
        loc = f"{BASE_URL}/{filename}"
        out.append((loc, _file_lastmod(backing, today), changefreq, priority))
    # Species/state combo pages (everything matching buy-*-trees-*.html that
    # isn't a state landing page). This includes the combo index page
    # buy-fruit-trees-by-species-state.html.
    for html_file in sorted(output_dir.glob("buy-*-trees-*.html")):
        if LOCATION_PAGE_PATTERN.match(html_file.name):
            continue
        if not COMBO_PATTERN.match(html_file.name):
            continue
        loc = f"{BASE_URL}/{html_file.name}"
        out.append((loc, _file_lastmod(html_file, today), "weekly", "0.7"))
    return out


# ---------------------------------------------------------------------------
# Orchestration

def build_sitemap(species_dir: Path, output_dir: Path) -> None:
    sitemaps_dir = output_dir / "sitemaps"
    sitemaps_dir.mkdir(parents=True, exist_ok=True)

    sections = [
        ("static",    _collect_static(output_dir, species_dir)),
        ("species",   _collect_species(species_dir)),
        ("nursery",   _collect_dir(output_dir, "nursery", "weekly", "0.7")),
        ("compare",   _collect_dir(output_dir, "compare", "weekly", "0.7")),
        ("locations", _collect_locations(output_dir)),
        ("variety",   _collect_dir(output_dir, "variety", "weekly", "0.6")),
    ]

    index_entries = []
    total_urls = 0
    for name, entries in sections:
        if not entries:
            continue
        sub_path = sitemaps_dir / f"{name}.xml"
        max_lastmod = _write_urlset(sub_path, entries)
        index_entries.append((f"{BASE_URL}/sitemaps/{name}.xml", max_lastmod))
        total_urls += len(entries)
        print(f"  sitemaps/{name}.xml: {len(entries)} URLs (lastmod {max_lastmod})")

    _write_index(output_dir / "sitemap.xml", index_entries)
    print(f"Sitemap index written: {output_dir / 'sitemap.xml'} "
          f"({len(index_entries)} sub-sitemaps, {total_urls} URLs total)")


def main():
    if len(sys.argv) < 3:
        print("Usage: build_sitemap.py <species-dir> <output-dir>")
        sys.exit(1)

    species_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    build_sitemap(species_dir, output_dir)


if __name__ == "__main__":
    main()
