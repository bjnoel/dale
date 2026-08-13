#!/usr/bin/env python3
"""Google Play keyword rank measurement for Treesmith.

The Play-side twin of `appstore_rank.py`, sharing its term set rather than
copying it. Reads the public Play search page (no credentials, no cost) and
reports where our app appears for the same DEC-247 terms.

Why this exists: DAL-279 renames the app on both stores. On Apple the rename
rides a version submission that ALSO carries the en-US localisation deletion,
so the Apple measurement is confounded by construction. A Play listing change
needs no build and lands alone, which makes Play the cleaner test of the
name-field theory -- but only if a baseline exists before the rename. This
script is that baseline.

The one thing Play does differently, and it matters:

    Apple returns up to 200 results and usually fewer, so a result count below
    the limit proves the set was exhausted and "absent from n=191" is a finding
    (DEC-255). Play's search page serves ~30 results before it lazy-loads more.
    So a count of exactly WINDOW means the set was TRUNCATED and absence is not
    proven, while a count below WINDOW means it was exhausted and absence is.

    Those two cases are reported differently and must never be collapsed. That
    is DEC-249's rule (an absence of measurement and a measured zero must not
    look alike) applied to a store that truncates where Apple did not.

Usage:
    python3 playstore_rank.py                     # AU and US, table to stdout
    python3 playstore_rank.py --country AU
    python3 playstore_rank.py --json
    python3 playstore_rank.py --save data/treesmith-play-rank-baseline.json
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from appstore_rank import TERMS, all_terms  # noqa: E402  the shared term set

OUR_PACKAGE = "app.treesmith"
SEARCH_URL = "https://play.google.com/store/search"
PAUSE_S = 1.0

# How many results Play's search page serves before it lazy-loads. A measured
# count equal to this is a truncated window, not an exhausted result set.
WINDOW = 30

# Play renders a desktop layout only for a browser UA; the mobile/bot layout
# returns a different and much shorter result list.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

DETAIL_LINK_RE = re.compile(r"/store/apps/details\?id=([A-Za-z0-9_.]+)")


def fetch(term, country, timeout=25):
    """Return the raw search page HTML for a term, or raise."""
    qs = urllib.parse.urlencode(
        {
            "q": term,
            "c": "apps",
            "hl": f"en_{country}",
            "gl": country,
        }
    )
    req = urllib.request.Request(
        f"{SEARCH_URL}?{qs}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def packages_in_order(html):
    """Ordered, de-duplicated package ids as they appear in the results.

    Play repeats a package in several link slots per card, so first appearance
    is the ranking position.
    """
    seen = []
    for pkg in DETAIL_LINK_RE.findall(html):
        if pkg not in seen:
            seen.append(pkg)
    return seen


def rank_of(packages, package=OUR_PACKAGE):
    """1-based rank of our app, or None if absent from the measured window."""
    for i, pkg in enumerate(packages):
        if pkg == package:
            return i + 1
    return None


def saturated(count, window=WINDOW):
    """True when the result set was cut off by the window rather than exhausted.

    A saturated window cannot prove absence: our app may sit at rank 31. An
    unsaturated one can, because Play ran out of results before the cap.
    """
    return count >= window


def measure(country, terms=None, pause=PAUSE_S, fetcher=fetch):
    """Measure every term on one storefront. Errors are recorded, not swallowed."""
    rows = []
    for group, term in terms if terms is not None else all_terms():
        row = {"group": group, "term": term, "country": country}
        try:
            html = fetcher(term, country)
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            continue
        packages = packages_in_order(html)
        row["result_count"] = len(packages)
        row["truncated"] = saturated(len(packages))
        row["rank"] = rank_of(packages)
        row["top3"] = packages[:3]
        rows.append(row)
        if pause:
            time.sleep(pause)
    return rows


def cell(row):
    """One table cell, keeping proven and unproven absence distinguishable."""
    if row is None:
        return "--"
    if "error" in row:
        return "ERR"
    n = row.get("result_count", 0)
    if row.get("rank") is not None:
        return f"#{row['rank']}/{n}"
    # Absent. Whether that is a finding depends on the window.
    return f"none/{n}+" if row.get("truncated") else f"none/{n}"


def render(rows_by_country):
    """Render the comparison. Returns plain text."""
    countries = list(rows_by_country.keys())
    lines = []
    lines.append("Treesmith Google Play keyword rank")
    lines.append("=" * 72)
    lines.append("")

    idx = {}
    for c, rows in rows_by_country.items():
        for r in rows:
            idx[(c, r["term"])] = r

    header = f"{'term':<24}" + "".join(f"{c:>12}" for c in countries)
    lines.append(header)
    lines.append("-" * len(header))

    errors = []
    for group, terms in TERMS.items():
        lines.append(f"  [{group}]")
        for term in terms:
            cells = [cell(idx.get((c, term))) for c in countries]
            for c in countries:
                r = idx.get((c, term))
                if r is not None and "error" in r:
                    errors.append(f"{c} {term}: {r['error']}")
            lines.append(f"{term:<24}" + "".join(f"{x:>12}" for x in cells))
        lines.append("")

    lines.append(
        f"Play serves ~{WINDOW} results before lazy-loading, so the denominator is"
    )
    lines.append("the measured window, NOT the whole result set:")
    lines.append(
        f"  none/{WINDOW}+  absent from the window, which is capped. NOT proof of absence."
    )
    lines.append(
        "  none/12   absent from all 12 results Play had. That IS proof of absence."
    )
    lines.append("Apple's 200-result limit makes its denominators exhaustive; Play's is not.")

    if errors:
        lines.append("")
        lines.append("!! ERRORS (these are NOT 'not ranked'):")
        for e in errors:
            lines.append(f"   {e}")

    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--country",
        action="append",
        help="storefront code, repeatable (default: AU and US)",
    )
    ap.add_argument("--json", action="store_true", help="emit raw rows as JSON")
    ap.add_argument("--term", action="append", help="measure only these terms")
    ap.add_argument("--save", help="also write raw rows as JSON to this path")
    args = ap.parse_args(argv)

    countries = args.country or ["AU", "US"]
    terms = None
    if args.term:
        wanted = set(args.term)
        terms = [(g, t) for g, t in all_terms() if t in wanted]
        if not terms:
            terms = [("adhoc", t) for t in args.term]

    rows_by_country = {c: measure(c, terms=terms) for c in countries}

    if args.json:
        print(json.dumps(rows_by_country, indent=2))
    else:
        print(render(rows_by_country))

    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            json.dump(rows_by_country, fh, indent=2)
        print(f"\nSaved raw rows to {args.save}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
