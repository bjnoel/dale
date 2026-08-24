#!/usr/bin/env python3
"""Rebuild the compare ledger's `first_seen` / `live_days` from snapshot history.

`build_compare_pages.seed_from_disk` can only read a file's mtime. For a page
the builder rewrites every night that mtime is last night, so seeding on
2026-08-20 gave all 116 live compare pages `first_seen 2026-08-20` and
`live_days 0`, leaving every one of them below `ENTRY_GUARD_LIVE_DAYS` for its
first week. A page orphaned inside that window is held rather than redirected,
and because `live_days` only advances on a night the page is written, it stays
held forever: the exact defect the ledger was added to fix (DEC-309, DAL-288).

`PageLedger.seed` was always meant to backdate from availability history rather
than from the filesystem. This does that. A compare page qualifies on a night
when at least MIN_NURSERIES distinct nurseries list the species at all, in
stock or not, which is the gate in build_compare_pages.py, so it can be
replayed exactly over the per-day snapshots in data/nursery-stock/.

Method check: replaying it reconstructs chinese-bayberry's first qualifying day
as 2026-06-18, the same date that was worked out by hand from the primal-fruits
listing when that page was reseeded.

Read-only without `--apply`. Only `live` entries are touched; a redirect or
tombstone is terminal and no guard reads its dates any more.
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stocklib.classify import is_real_product
from stocklib.species_match import build_species_lookup, match_title
from stocklib.taxonomy import enabled_species

MIN_NURSERIES = 3


def reconstruct(data_dir: Path) -> dict[str, dict]:
    """slug -> {first, last, days} over every daily snapshot on disk."""
    lookup = build_species_lookup(enabled_species())
    cache: dict[str, str | None] = {}

    def species_of(title: str) -> str | None:
        if title not in cache:
            sp = match_title(title, lookup) if is_real_product(title) else None
            cache[title] = sp["slug"] if sp else None
        return cache[title]

    by_day: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        for snap in sorted(nursery_dir.glob("20*.json")):
            try:
                products = json.loads(snap.read_text()).get("products", [])
            except (OSError, ValueError) as exc:
                print(f"  skipped {snap}: {exc}", file=sys.stderr)
                continue
            for p in products:
                slug = species_of(p.get("title", ""))
                if slug:
                    by_day[snap.stem][slug].add(nursery_dir.name)

    qualified: dict[str, list[str]] = defaultdict(list)
    for day in sorted(by_day):
        for slug, nurseries in by_day[day].items():
            if len(nurseries) >= MIN_NURSERIES:
                qualified[slug].append(day)
    return {s: {"first": d[0], "last": d[-1], "days": len(d)}
            for s, d in qualified.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=Path("/opt/dale/data/nursery-stock"))
    ap.add_argument("--ledger", type=Path,
                    default=Path("/opt/dale/data/page-ledger/compare.json"))
    ap.add_argument("--apply", action="store_true",
                    help="write the ledger (default is to report only)")
    args = ap.parse_args()

    hist = reconstruct(args.data_dir)
    print(f"Species that ever qualified: {len(hist)}")

    ledger = json.loads(args.ledger.read_text())
    pages = ledger["pages"]
    changes = []
    for slug, entry in sorted(pages.items()):
        if entry.get("state") != "live":
            continue
        h = hist.get(slug)
        if not h:
            print(f"  no history for live page {slug}, left alone")
            continue
        if (entry.get("first_seen"), entry.get("live_days")) != (h["first"], h["days"]):
            changes.append((slug, entry.get("first_seen"), h["first"],
                            entry.get("live_days"), h["days"]))

    for slug, of, nf, od, nd in changes:
        print(f"  {slug}: first_seen {of} -> {nf}, live_days {od} -> {nd}")
    print(f"{len(changes)} live page(s) to correct")

    if not args.apply:
        print("Report only. Pass --apply to write.")
        return 0

    for slug, _, nf, _, nd in changes:
        pages[slug]["first_seen"] = nf
        pages[slug]["live_days"] = nd
    ledger["review"].append({
        "date": date.today().isoformat(),
        "slug": "*",
        "reason": (f"reseed_compare_ledger.py corrected first_seen and live_days "
                   f"on {len(changes)} live page(s) from snapshot history"),
    })
    args.ledger.with_name(args.ledger.name + ".prev").write_bytes(args.ledger.read_bytes())
    args.ledger.write_text(json.dumps(ledger, indent=1, sort_keys=True))
    print(f"Wrote {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
