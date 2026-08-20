#!/usr/bin/env python3
"""Turn a Search Console "Not found (404)" export into redirect proposals.

`recover_merged_slugs.py` recovers the URLs a PARSER CHANGE killed, by diffing
two builds off nursery snapshots. It can only see slugs that existed in the
build it diffs against. This tool starts from the other end: Google's list of
URLs it crawled and got a 404 from, which reaches back further than any snapshot
we keep and includes cohorts that predate the page ledger entirely.

The two are complements, not alternatives. Task R1 recovered 194 URLs on
2026-08-17 from the snapshot side and left this cohort untouched, because the
slugs died before the ledger existed and no build we can reach still generates
them.

## What a recoverable 404 looks like

    /variety/loquat-champagne-5l.html          404, no ledger entry
    /variety/loquat-champagne.html             live, 3 nurseries

`5l` is a pot size. One plant, two URLs, and the one Google has is the dead one.
That is a redirect we never wrote, not a page that went away, and every one of
them is link equity on the floor.

## What it refuses to propose

The tail has to be listing noise ALL the way down. A tail carrying a real word
is a different plant until a person says otherwise:

    pear-nashi-tropical-sunshu -> pear-nashi        "sunshu" is a cultivar
    apricot-storeys-early-moorpark -> apricot-storeys   "Early Moorpark" is one

Those come out in `--report` for a human and are never approved by this tool.

Dwarf is the interesting exception and it runs both ways. The site's own
vocabulary calls `dwarf` listing noise for every species except banana
(`DWARF_KEEPING_SPECIES`), so `apricot-moorpark-dwarf -> apricot-moorpark` is
consistent with how every other page on the site is named. But if a `-dwarf-`
page ALSO exists live, the dead slug is ambiguous no matter what the vocabulary
says: `banana-red-dacca-dwarf-90mm-qld-only` sits between a live
`banana-red-dacca` and a live `banana-dwarf-red-dacca`, and picking the shorter
prefix would file a dwarf plant under the standard one.

Nothing here writes a page. It emits rows in the schema
`build_variety_pages.seed_reviewed` reads, and that function re-tests every
condition against the night it runs: a target that stopped being a page, or an
old slug the parser started generating again, is skipped there rather than
trusted from here.

Usage:
    python3 recover_gsc_404s.py Table.csv --report
    python3 recover_gsc_404s.py Table.csv --merge-into \\
        /opt/dale/data/variety-redirect-proposals.json --approve b@bjnoel.com
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Imported, never copied: `tests/test_no_forking.py` enforces that, and the two
# lists disagreeing is exactly how a redirect gets proposed for a slug the rest
# of the site considers meaningful. admin_view is a light import with no
# cultivar_parsing dependency, which is why it is safe to pull in here.
from admin_view import DWARF_KEEPING_SPECIES, NOISE_SLUG_TOKENS

DEFAULT_DASHBOARD = Path("/opt/dale/dashboard")
DEFAULT_LEDGER = Path("/opt/dale/data/page-ledger/variety.json")
DEFAULT_INDEX = Path("/opt/dale/data/variety-index.json")

VARIETY_PREFIX = "/variety/"

# Tokens that are listing noise in a SLUG but that `cultivar_parsing._NOISE_RES`
# does not strip from a TITLE. That is not an inconsistency to fix in one place:
# these slugs were minted by older parsers, or by titles the current one would
# still not fully clean, and the products behind them have since moved or gone.
# The vocabulary here is therefore historical, and widening it changes what gets
# proposed for review rather than what the site generates tonight.
_EXTRA_NOISE = frozenset({
    # where it ships, never what it is
    "qld", "nsw", "vic", "wa", "sa", "tas", "nt", "only", "restricted", "to",
    "s", "e",                                   # "S E QLD only"
    # how it was grown or sold
    "pickup", "pick", "up", "tube", "stock", "tubestock", "organic",
    "advanced", "large", "small", "medium", "seed", "bear",
    # trademark and cultivar-rights markers that reached the slug as words
    "amp", "reg", "cv",
})

# "5l", "180mm", "14cm", "165ml", "60". A bare number is a size here because a
# variety whose name is a number is rejected upstream (`cultivar_parsing`
# refuses a leading-digit variety), so a trailing bare number in a tail is a
# pot, never a cultivar.
_SIZE_RE = re.compile(r"^\d+(mm|cm|l|lt|ltr|litre|liter|ml|inch)?$")

_DWARF_TOKENS = frozenset({"dwarf", "dwf", "semi"})


def is_noise_token(token: str) -> bool:
    return (token in NOISE_SLUG_TOKENS or token in _EXTRA_NOISE
            or bool(_SIZE_RE.match(token)))


def read_export(path: Path) -> list[dict]:
    """The GSC coverage drilldown CSV, as rows of {url, crawled}.

    Both hostnames appear in these exports because www.treestock.com.au serves
    the site rather than redirecting to the apex, so the same dead path arrives
    twice. Deduplicated on the PATH for that reason: proposing the same slug
    twice would have `seed_reviewed` seed the same ledger entry twice.
    """
    rows, seen = [], set()
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            url = (row.get("URL") or "").strip()
            if "treestock.com.au" not in url:
                continue
            path_only = url.split("treestock.com.au", 1)[1]
            if path_only in seen:
                continue
            seen.add(path_only)
            rows.append({"path": path_only,
                         "crawled": (row.get("Last crawled") or "").strip()})
    return rows


def longest_live_prefix(slug: str, live: set) -> str:
    """The longest token-prefix of `slug` that is itself a live page, or "".

    Token-wise, never character-wise: `apple-gala-dwarf` must be allowed to find
    `apple-gala`, and `apple-galaxy` must not.

    Stops at two tokens because a one-token prefix is the bare species, and
    every variety slug starts with its species. Allowing it would propose
    `mango-something-unknown -> mango` for anything with an unrecognised
    cultivar, which is a redirect to an index page dressed up as a recovery.
    """
    parts = slug.split("-")
    for i in range(len(parts) - 1, 1, -1):
        candidate = "-".join(parts[:i])
        if candidate in live:
            return candidate
    return ""


def better_target(target: str, tail: list, live: set) -> str:
    """A live slug that keeps a tail token the plain prefix would throw away.

    `pear-nashi-tropical-sunshu` prefix-matches `pear-nashi`, and `pear-nashi`
    is live, so the naive answer is to fold a named cultivar onto the generic
    nashi page. But `pear-nashi-sunshu` is ALSO live, and it is obviously the
    real successor. Reported, never proposed: the tool can see that a better
    target exists without being able to prove it is the right one.
    """
    for token in tail:
        if is_noise_token(token):
            continue
        candidate = f"{target}-{token}"
        if candidate in live:
            return candidate
    return ""


def dwarf_ambiguity(target: str, tail: list, live: set) -> str:
    """The live `-dwarf-` sibling that makes a dwarf tail ambiguous, or "".

    Only fires when the dead slug says dwarf AND a dwarf page exists to be
    confused with. `apricot-moorpark-dwarf` has no `apricot-dwarf-moorpark`, so
    it is unambiguous and the site's own vocabulary settles it. Banana is where
    this bites, because banana is the one species whose dwarf really is a
    cultivar name.
    """
    if not any(t in _DWARF_TOKENS for t in tail):
        return ""
    parts = target.split("-")
    species = parts[0]
    for marker in ("dwarf", "dwf"):
        sibling = "-".join([species, marker] + parts[1:])
        if sibling in live and sibling != target:
            return sibling
    # Banana keeps dwarf as a cultivar word, so a dwarf tail there is a claim
    # about the plant even when no sibling page happens to exist tonight.
    return "banana keeps dwarf" if species in DWARF_KEEPING_SPECIES else ""


def classify(rows, live: set, ledger: dict, dashboard: Path) -> dict:
    """Every export row sorted into what can be done about it."""
    out = {"recoverable": [], "needs_human": [], "correct": [], "serving": [],
           "not_variety": []}
    for row in rows:
        path = row["path"]
        if (dashboard / path.lstrip("/")).exists():
            out["serving"].append(dict(row))
            continue
        if not (path.startswith(VARIETY_PREFIX) and path.endswith(".html")):
            out["not_variety"].append(dict(row))
            continue
        slug = path[len(VARIETY_PREFIX):-len(".html")]
        if slug in ledger:
            # Already a redirect or tombstone in the ledger, so it serves 200
            # and the export row is stale. Not ours to touch.
            out["serving"].append(dict(row, slug=slug))
            continue

        target = longest_live_prefix(slug, live)
        if not target:
            out["correct"].append(dict(row, slug=slug))
            continue

        tail = slug[len(target) + 1:].split("-")
        entry = dict(row, slug=slug, target=target, tail="-".join(tail))
        better = better_target(target, tail, live)
        dwarf = dwarf_ambiguity(target, tail, live)
        if better:
            entry["why"] = f"a longer live page exists: {better}"
            out["needs_human"].append(entry)
        elif dwarf:
            entry["why"] = f"dwarf is ambiguous here ({dwarf})"
            out["needs_human"].append(entry)
        elif all(is_noise_token(t) for t in tail):
            out["recoverable"].append(entry)
        else:
            real = [t for t in tail if not is_noise_token(t)]
            entry["why"] = f"tail carries {', '.join(real)}"
            out["needs_human"].append(entry)
    return out


def titleise(slug: str) -> str:
    return " ".join(p.capitalize() for p in slug.split("-"))


def to_proposal(entry: dict, approve: str = "", now: str = "") -> dict:
    """One row in the schema `build_variety_pages.seed_reviewed` reads.

    `verdict` is always "rename": every row here HAS a live successor, which is
    the entire test for getting into this list. A tombstone is what the other
    tool emits for slugs that never had one, and proposing one from a 404 export
    would be asserting a plant is gone on the evidence that Google could not
    fetch a URL.
    """
    slug, target = entry["slug"], entry["target"]
    species = slug.split("-")[0]
    row = {
        "slug": slug,
        "title": titleise(slug),
        "species": species.capitalize(),
        "variety": titleise(slug[len(species) + 1:]) if "-" in slug else "",
        "verdict": "rename",
        "target": target,
        "target_live": True,
        "source": "gsc-404-export",
        "last_crawled": entry.get("crawled", ""),
        "dropped": entry.get("tail", ""),
    }
    if approve:
        row["approved"] = True
        row["approved_by"] = approve
        row["approved_at"] = now
    return row


def merge_into(path: Path, proposals: list) -> tuple[int, int]:
    """Add rows to the file the nightly already reads, keyed on slug.

    `run-all-scrapers.sh` passes ONE `--seed-reviewed` path, so a second file
    would need a change to the nightly to be read at all, and a proposal nothing
    reads is the failure mode task R1 shipped with the first time. Existing rows
    are never rewritten: an approval already recorded against a slug is a
    decision, and this tool does not get to revise it.
    """
    doc = json.loads(path.read_text())
    existing = {p.get("slug") for p in doc.get("proposals") or []}
    fresh = [p for p in proposals if p["slug"] not in existing]
    doc.setdefault("proposals", []).extend(fresh)
    summary = doc.setdefault("summary", {})
    summary["total"] = len(doc["proposals"])
    summary["gsc_recovered"] = summary.get("gsc_recovered", 0) + len(fresh)
    path.write_text(json.dumps(doc, indent=1) + "\n")
    return len(fresh), len(proposals) - len(fresh)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", type=Path, help="GSC coverage drilldown Table.csv")
    ap.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    ap.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    ap.add_argument("--report", action="store_true",
                    help="print the buckets and the rows a human has to settle")
    ap.add_argument("--merge-into", type=Path, default=None,
                    help="proposals file the nightly reads")
    ap.add_argument("--approve", default="",
                    help="stamp approval on the pure-noise rows, as this email. "
                         "Never applied to the --report rows.")
    args = ap.parse_args(argv)

    live = set(json.loads(args.index.read_text()))
    ledger = json.loads(args.ledger.read_text()).get("pages") or {}
    rows = read_export(args.export)
    buckets = classify(rows, live, ledger, args.dashboard)

    print(f"{len(rows)} unique paths in {args.export.name}")
    for name, label in (("recoverable", "recoverable (clean live page exists)"),
                        ("needs_human", "need a human"),
                        ("correct", "correct 404 (nothing to point at)"),
                        ("not_variety", "not a /variety/ page"),
                        ("serving", "already serving 200")):
        print(f"  {len(buckets[name]):5}  {label}")

    if args.report:
        print("\n-- need a human --")
        for e in sorted(buckets["needs_human"], key=lambda e: e["slug"]):
            print(f"  {e['slug']}\n      -> {e['target']}   ({e['why']})")

    if args.merge_into:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        proposals = [to_proposal(e, args.approve, now)
                     for e in sorted(buckets["recoverable"],
                                     key=lambda e: e["slug"])]
        added, skipped = merge_into(args.merge_into, proposals)
        state = f"approved by {args.approve}" if args.approve else "UNAPPROVED"
        print(f"\n{added} rows added to {args.merge_into} ({state})"
              f"{f', {skipped} already there' if skipped else ''}")
        if not args.approve:
            print("Nothing will apply until a reviewer sets approved=true.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
