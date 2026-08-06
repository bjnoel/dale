#!/usr/bin/env python3
"""App Store keyword rank measurement for Treesmith.

Reads the iTunes Search API (no credentials, no cost) and reports where our app
appears for a fixed set of terms, on any storefront.

Why this exists: DEC-247 measured 36 terms by hand on the AU store and concluded
the app NAME is the field that ranks. DEC-256 then found 61% of installs are US
and DEC-261 found iOS is 100% of revenue, so the AU-only measurement was scored
on the wrong store. DAL-257 has to re-measure after the rename, and a hand pass
is not comparable to another hand pass.

Two things this deliberately does NOT do:

  * It does not truncate. `limit=200` is Apple's maximum and Apple returns fewer
    than 200 for most terms, so the result count doubles as the size of the whole
    result set. "absent from n=191" is then a finding, not a truncation (DEC-255).
  * It does not silently drop a storefront that returned nothing. A term that
    errors is reported as an error, never as "not ranked" (DEC-249: an absence of
    measurement and a zero must not look alike).

Usage:
    python3 appstore_rank.py                    # AU and US, table to stdout
    python3 appstore_rank.py --country US
    python3 appstore_rank.py --json
"""

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

OUR_TRACK_ID = 6761506742
SEARCH_URL = "https://itunes.apple.com/search"
LIMIT = 200
PAUSE_S = 0.35

# The DEC-247 term set. Grouped so the report can say something about the shape
# of the result rather than just listing 36 numbers.
TERMS = {
    # <niche> tracker compounds: held by 0-rating apps, the winnable ground
    "niche_tracker": [
        "fruit tree tracker",
        "orchard tracker",
        "tree tracker",
        "graft tracker",
        "grafting tracker",
        "bonsai tracker",
        "citrus tracker",
        "propagation tracker",
        "seedling tracker",
        "harvest tracker",
    ],
    # broad plant/garden terms: held by PictureThis/Planta, not winnable at 0 ratings
    "broad": [
        "plant tracker",
        "garden journal",
        "garden planner",
        "plant log",
        "garden diary",
        "garden log",
        "plant inventory",
        "plant collection",
        "plant catalogue",
        "plant database",
        "garden mapping",
        "plant care",
    ],
    # subject terms with buying intent but no app-category shape
    "subject": [
        "fruit tree",
        "fruit tree journal",
        "fruit tree care",
        "rare fruit",
        "grafting",
        "scion wood",
        "rootstock",
        "orchard management",
        "orchard map",
        "home orchard",
        "backyard orchard",
        "permaculture",
    ],
    # brand
    "brand": [
        "treesmith",
        "tree smith",
    ],
}


def all_terms():
    out = []
    for group, terms in TERMS.items():
        for t in terms:
            out.append((group, t))
    return out


def search(term, country, timeout=20):
    """Return the ordered list of results for a term, or raise."""
    qs = urllib.parse.urlencode(
        {
            "term": term,
            "country": country,
            "media": "software",
            "entity": "software",
            "limit": LIMIT,
        }
    )
    req = urllib.request.Request(
        f"{SEARCH_URL}?{qs}", headers={"User-Agent": "treestock-aso/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
    data = json.loads(body)
    return data.get("results", [])


def rank_of(results, track_id=OUR_TRACK_ID):
    """1-based rank of our app in the result list, or None if absent."""
    for i, app in enumerate(results):
        if app.get("trackId") == track_id:
            return i + 1
    return None


def name_match_share(results, term, top_n=5):
    """Share of the top N results carrying every query token in the app NAME.

    This is DEC-247's supporting evidence, recomputed rather than assumed.
    """
    tokens = [t for t in term.lower().split() if t]
    if not tokens or not results:
        return None
    window = results[:top_n]
    hits = 0
    for app in window:
        name = (app.get("trackName") or "").lower()
        if all(tok in name for tok in tokens):
            hits += 1
    return hits / len(window)


def measure(country, terms=None, pause=PAUSE_S, searcher=search):
    """Measure every term on one storefront. Errors are recorded, not swallowed."""
    rows = []
    for group, term in terms if terms is not None else all_terms():
        row = {"group": group, "term": term, "country": country}
        try:
            results = searcher(term, country)
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
            continue
        row["result_count"] = len(results)
        row["rank"] = rank_of(results)
        row["name_match_top5"] = name_match_share(results, term)
        row["top3"] = [
            {
                "name": a.get("trackName"),
                "ratings": a.get("userRatingCount", 0),
            }
            for a in results[:3]
        ]
        rows.append(row)
        if pause:
            time.sleep(pause)
    return rows


def render(rows_by_country):
    """Render the comparison. Returns plain text."""
    countries = list(rows_by_country.keys())
    lines = []
    lines.append("Treesmith App Store keyword rank")
    lines.append("=" * 72)
    lines.append("")

    # index rows by (country, term)
    idx = {}
    for c, rows in rows_by_country.items():
        for r in rows:
            idx[(c, r["term"])] = r

    header = f"{'term':<24}" + "".join(f"{c:>12}" for c in countries)
    lines.append(header)
    lines.append("-" * len(header))

    errors = []
    moves = []
    for group, terms in TERMS.items():
        lines.append(f"  [{group}]")
        for term in terms:
            cells = []
            ranks = {}
            for c in countries:
                r = idx.get((c, term))
                if r is None:
                    cells.append("--")
                elif "error" in r:
                    cells.append("ERR")
                    errors.append(f"{c} {term}: {r['error']}")
                elif r["rank"] is None:
                    cells.append(f"none/{r['result_count']}")
                else:
                    cells.append(f"#{r['rank']}/{r['result_count']}")
                    ranks[c] = r["rank"]
            lines.append(f"{term:<24}" + "".join(f"{c:>12}" for c in cells))
            if len(ranks) == 2 and len(countries) == 2:
                a, b = countries
                if a in ranks and b in ranks and ranks[a] != ranks[b]:
                    moves.append((term, ranks[a], ranks[b]))
        lines.append("")

    lines.append(
        "Rank is our position; the denominator is how many results Apple returned"
    )
    lines.append(
        "in total for that term, so 'none/191' means genuinely absent, not truncated."
    )

    if len(countries) == 2:
        a, b = countries
        both = [
            t
            for t in [r["term"] for r in rows_by_country[a]]
            if idx.get((a, t), {}).get("rank") and idx.get((b, t), {}).get("rank")
        ]
        only_a = [
            t
            for t in [r["term"] for r in rows_by_country[a]]
            if idx.get((a, t), {}).get("rank") and not idx.get((b, t), {}).get("rank")
        ]
        only_b = [
            t
            for t in [r["term"] for r in rows_by_country[b]]
            if idx.get((b, t), {}).get("rank") and not idx.get((a, t), {}).get("rank")
        ]
        lines.append("")
        lines.append(f"Ranked on both stores : {len(both)}")
        lines.append(f"Ranked on {a} only     : {len(only_a)}" + (f"  ({', '.join(only_a)})" if only_a else ""))
        lines.append(f"Ranked on {b} only     : {len(only_b)}" + (f"  ({', '.join(only_b)})" if only_b else ""))

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
