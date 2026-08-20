#!/usr/bin/env python3
"""Append-only keyword rank series for Treesmith (DAL-257).

`appstore_rank.py` and `playstore_rank.py` both measure well and neither
remembers anything. Every comparison to date has been a hand-run two-file diff,
and the 2026-08-13 pre-rename baseline nearly went to waste because there was no
series for it to be the start of. This module is that series: one CSV, one row
per capture x store x country x term, appended to and never rewritten.

The one thing flattening to CSV forces, which the JSON did not:

    Both readers enforce DEC-249 *structurally*. An errored row carries `error`
    and omits `rank`, `result_count`, `truncated` and `top3` entirely, so an
    absence of measurement cannot be mistaken for a measured zero -- the key is
    simply not there. A CSV cell cannot be absent, only empty, so the states
    have to be named instead:

        ranked                 we are at that position
        absent                 DEC-255: absence PROVEN, the store ran out of
                               results before the cap
        absent_window_capped   DEC-255: absence NOT proven, we could be at 31
        error                  DEC-249: nothing was measured. Not a zero.

    `truncated` is kept alongside as the raw boolean it was derived from.

Apple has no truncation concept, but leaving its column blank would let a future
capped iOS window read as proven absence, so it is derived from
`appstore_rank.LIMIT`. Observed iOS counts are 37-193, so it is false everywhere
today and only becomes true if Apple starts capping us.

Usage:
    python3 rank_history.py captures
    python3 rank_history.py backfill            # dry run
    python3 rank_history.py backfill --write
    python3 rank_history.py diff
    python3 rank_history.py diff --store play --against 2026-08-13T01:56:00Z
"""

import argparse
import csv
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from appstore_rank import LIMIT, TERMS  # noqa: E402  the shared term set
from playstore_rank import OUR_PACKAGE, saturated  # noqa: E402  Play's window rule, not re-derived

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CSV = os.path.join(REPO_ROOT, "data", "treesmith-rank-history.csv")

APPSTORE = "appstore"
PLAY = "play"
STORES = (APPSTORE, PLAY)

# The four states a measurement can be in. See the module docstring.
RANKED = "ranked"
ABSENT = "absent"
ABSENT_CAPPED = "absent_window_capped"
ERROR = "error"

# The header, and the single source of truth for column order. Append-only: a
# reader that has already parsed older rows must keep working, so columns are
# added at the end or not at all.
CSV_COLUMNS = [
    "captured_at",
    "store",
    "country",
    "group",
    "term",
    "rank",
    "result_count",
    "truncated",
    "status",
    "name_match_top5",
    "top3_1",
    "top3_2",
    "top3_3",
    "error",
]

# Columns that carry a value or nothing at all. Everything else is a string,
# empty when it has no value, so "" and None never both mean "missing".
_INT_COLUMNS = ("rank", "result_count")
_BOOL_COLUMNS = ("truncated",)
_FLOAT_COLUMNS = ("name_match_top5",)

# Group and term ordering, imported rather than restated so the series cannot
# drift from what the readers measure.
_TERM_ORDER = {
    term: (gi, ti)
    for gi, (group, terms) in enumerate(TERMS.items())
    for ti, term in enumerate(terms)
}

# The three captures that existed before this series did. None of the files
# carries a timestamp -- provenance is filename, mtime and the decision log --
# and mtimes do not survive a clone, so the map is hardcoded. Two of the three
# are the same store on the same date, which is why the key is a full timestamp
# and not a date: a date-only key would let day 0 overwrite the baseline and
# destroy the most informative pair in the dataset.
BACKFILL = (
    # (path relative to repo root, store, captured_at, why this timestamp)
    ("data/treesmith-play-rank-baseline.json", PLAY, "2026-08-13T01:56:00Z",
     "mtime 09:56 AWST; commit 'feat: Play rank reader' 10:04 AWST"),
    ("data/treesmith-appstore-rank-baseline.json", APPSTORE, "2026-08-13T02:01:00Z",
     "mtime 10:01 AWST; same commit"),
    ("data/treesmith-play-rank-day0-postchange.json", PLAY, "2026-08-13T02:55:00Z",
     "mtime 10:55 AWST; commit 'data: Play rename is live' 10:56 AWST"),
)


# ── Timestamps ───────────────────────────────────────────────────────────────

def now_iso():
    """Current UTC time in the series' canonical form."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalise_captured_at(value):
    """Canonicalise an ISO8601 timestamp to `YYYY-MM-DDTHH:MM:SSZ`, or raise.

    Validated at the door rather than trusted: a malformed timestamp reaching
    the CSV would split one capture into two and there is no way to tell that
    apart from a real pair afterwards.
    """
    text = str(value).strip()
    iso = text[:-1] + "+00:00" if text.endswith("Z") else text
    dt = datetime.datetime.fromisoformat(iso)  # raises ValueError on junk
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Records ──────────────────────────────────────────────────────────────────

def _top3_ids(top3):
    """Three identifier columns from a store-shaped top3.

    Apple gives `{name, ratings}` dicts, Play gives bare package strings. Three
    flat columns holding the identifier avoids separator escaping and is what
    the diff joins on. Apple's rating counts are dropped: they are already in
    the render path and are not what movement is computed from.
    """
    out = []
    for item in top3 or []:
        if isinstance(item, dict):
            out.append(item.get("name") or "")
        else:
            out.append(str(item))
    return (out + ["", "", ""])[:3]


def _truncated_for(store, result_count):
    """Whether the result set was capped rather than exhausted.

    Play's rule is `saturated()`, imported rather than re-derived: it is `>=`
    WINDOW, not `==`, because real AU data carries `result_count: 50` still
    flagged truncated.
    """
    if store == PLAY:
        return saturated(result_count)
    return result_count >= LIMIT


def to_records(store, rows_by_country, captured_at):
    """Normalise one `measure()` result to series records.

    Returns the same typed shape `read()` returns, so a round trip through the
    CSV is an equality check rather than a conversion.
    """
    if store not in STORES:
        raise ValueError(f"unknown store {store!r}; expected one of {STORES}")
    stamp = normalise_captured_at(captured_at)

    records = []
    for country, rows in rows_by_country.items():
        for row in rows:
            rec = {
                "captured_at": stamp,
                "store": store,
                "country": row.get("country") or country,
                "group": row.get("group", ""),
                "term": row.get("term", ""),
                "rank": None,
                "result_count": None,
                "truncated": None,
                "status": ERROR,
                "name_match_top5": None,
                "top3_1": "",
                "top3_2": "",
                "top3_3": "",
                "error": "",
            }
            if "error" in row:
                # DEC-249: nothing was measured. rank, result_count and
                # truncated stay empty, which is not the same as a zero.
                rec["error"] = str(row["error"])
                records.append(rec)
                continue

            count = row.get("result_count") or 0
            truncated = _truncated_for(store, count)
            rec["result_count"] = count
            rec["truncated"] = truncated
            rec["rank"] = row.get("rank")
            rec["name_match_top5"] = row.get("name_match_top5")
            rec["top3_1"], rec["top3_2"], rec["top3_3"] = _top3_ids(row.get("top3"))
            if rec["rank"] is not None:
                rec["status"] = RANKED
            else:
                rec["status"] = ABSENT_CAPPED if truncated else ABSENT
            records.append(rec)

    records.sort(key=_sort_key)
    return records


def _sort_key(rec):
    order = _TERM_ORDER.get(rec["term"], (len(TERMS), rec["term"]))
    return (rec["captured_at"], rec["store"], rec["country"], order, rec["term"])


# ── CSV ──────────────────────────────────────────────────────────────────────

def _encode(rec):
    out = {}
    for col in CSV_COLUMNS:
        value = rec.get(col)
        if value is None:
            out[col] = ""
        elif col in _BOOL_COLUMNS:
            out[col] = "true" if value else "false"
        else:
            out[col] = str(value)
    return out


def _decode(row):
    rec = {}
    for col in CSV_COLUMNS:
        raw = (row.get(col) or "").strip()
        if col in _INT_COLUMNS:
            rec[col] = int(raw) if raw else None
        elif col in _BOOL_COLUMNS:
            rec[col] = (raw == "true") if raw else None
        elif col in _FLOAT_COLUMNS:
            rec[col] = float(raw) if raw else None
        else:
            rec[col] = raw
    return rec


def append(path, records):
    """Append records, writing the header only when creating the file.

    Append-only by construction: the file is opened in append mode and existing
    rows are never read, rewritten or reordered.
    """
    if not records:
        return 0
    fresh = (not os.path.exists(path)) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        if fresh:
            writer.writeheader()
        for rec in records:
            writer.writerow(_encode(rec))
    return len(records)


def read(path):
    """Parse the series back to typed records. A missing file is an empty series."""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return []
        if list(reader.fieldnames) != CSV_COLUMNS:
            # The header is a contract with the published artefact and with the
            # admin worker that fetches it. A changed one is a bug, not a row.
            raise ValueError(
                f"{path}: unexpected header {reader.fieldnames!r}; "
                f"expected {CSV_COLUMNS!r}"
            )
        return [_decode(row) for row in reader]


def record_run(path, store, rows_by_country, captured_at=None):
    """Append one reader run to the series. The entry point both readers call.

    Returns `(captured_at, rows_written)`. Kept here rather than in each reader
    so the two stores cannot drift on how a run becomes a row.
    """
    stamp = normalise_captured_at(captured_at) if captured_at else now_iso()
    return stamp, append(path, to_records(store, rows_by_country, stamp))


def captures(records, store=None):
    """Distinct capture timestamps, newest first, optionally for one store."""
    stamps = {r["captured_at"] for r in records
              if store is None or r["store"] == store}
    return sorted(stamps, reverse=True)


# ── Diff ─────────────────────────────────────────────────────────────────────

NOISE = 3  # positions. Two runs 20 minutes apart already disagreed by one, and
           # the 2026-08-06 ledger measured 8 positions of drift in 7 days with
           # the listing untouched. Anything inside the band is not movement.

ABSENT_STATUSES = (ABSENT, ABSENT_CAPPED)

VACATED = "vacated"
DISPLACED = "displaced"
TURNED_OVER = "turned over"


def is_ours(identifier):
    """Whether a top3 identifier is us.

    Apple's identifier is the app NAME, and the app name is the thing that just
    changed. Without this, "TreeSmith: Plant Graft Tracker" leaving the top 3 and
    "TreeSmith: Fruit Tree Tracker" arriving reads as a competitor displacing us
    with ourselves. Play's identifier is the package id and is stable.
    """
    ident = (identifier or "").strip().lower()
    return ident == OUR_PACKAGE or ident.startswith("treesmith")


def _top3(rec):
    return [v for v in (rec["top3_1"], rec["top3_2"], rec["top3_3"]) if v]


def attribute(prev, curr):
    """Why we lost ground: did somebody take the slot, or did we leave it?

    This is what the top3 columns exist for, and the two cases are different
    business facts. iOS AU `graft tracker` fell 1 -> 11 and the two apps that
    moved up behind us are a peptide tracker and a blood-sugar tracker; nobody
    beat us, we simply stopped matching the term. A real competitor arriving
    (Grove, DEC-237) would be a different finding entirely.

    Read positionally rather than as a set difference. When we drop out of a
    3-slot window, whatever was at rank 4 backfills slot 3, so a newcomer always
    appears -- a bare `curr_top3 - prev_top3` would call every vacancy a
    displacement. What separates the two is WHERE the newcomer landed:

        vacated      every newcomer sits below every survivor: the field shifted
                     up into the slot we left and the tail backfilled
        displaced    a newcomer landed above a survivor: it jumped the queue
        turned over  no survivor at all: the result set re-indexed wholesale and
                     neither reading is about us

    Returns `(kind, names)`.
    """
    before = [a for a in _top3(prev) if not is_ours(a)]
    after = [a for a in _top3(curr) if not is_ours(a)]

    survivors = [a for a in after if a in before]
    newcomers = [a for a in after if a not in before]

    if not survivors:
        return TURNED_OVER, newcomers
    if not newcomers:
        return VACATED, []

    last_survivor = max(after.index(a) for a in survivors)
    jumpers = [a for a in newcomers if after.index(a) < last_survivor]
    if jumpers:
        return DISPLACED, jumpers
    return VACATED, []


def _movement(prev, curr, kind):
    """One row of a bucket, carrying enough to render without the records."""
    item = {
        "store": curr["store"],
        "country": curr["country"],
        "group": curr["group"],
        "term": curr["term"],
        "prev_rank": prev["rank"],
        "curr_rank": curr["rank"],
        "prev_status": prev["status"],
        "curr_status": curr["status"],
        "delta": None,
        "attribution": None,
        "attributed_to": [],
        # DEC-255: an absence Play could not prove is not the same finding as
        # one it could, and the difference has to survive into the report.
        "absence_proven": None,
    }
    if prev["rank"] is not None and curr["rank"] is not None:
        # Positive is worse: a bigger number is a lower position.
        item["delta"] = curr["rank"] - prev["rank"]
    if kind == "dropped":
        item["absence_proven"] = curr["status"] == ABSENT
    elif kind == "entered":
        item["absence_proven"] = prev["status"] == ABSENT
    if kind == "dropped" or (item["delta"] or 0) > 0:
        item["attribution"], item["attributed_to"] = attribute(prev, curr)
    return item


def diff_captures(prev_records, curr_records, noise=NOISE):
    """Compare two captures. The function the digest imports.

    Joins on (store, country, term). Deliberately not on `group`: the group is
    our own label from TERMS, not a store fact, so moving a term between groups
    would otherwise render as that term dropping off the store and a new one
    arriving. A term measured in only one of the two captures is `unmeasured`,
    never a drop -- a partial re-run must not read as 36 apps falling off.
    """
    def index(records):
        return {(r["store"], r["country"], r["term"]): r for r in records}

    prev_idx, curr_idx = index(prev_records), index(curr_records)

    out = {
        "moved": [],
        "entered": [],
        "dropped": [],
        "flat_n": 0,
        "still_absent_n": 0,
        "unmeasured": [],
    }

    for key in sorted(set(prev_idx) | set(curr_idx)):
        prev, curr = prev_idx.get(key), curr_idx.get(key)
        store, country, term = key

        if prev is None or curr is None:
            side = "the older capture" if prev is None else "the newer capture"
            known = prev or curr
            out["unmeasured"].append({
                "store": store, "country": country, "group": known["group"],
                "term": term, "reason": f"not measured in {side}",
            })
            continue

        # DEC-249: a term that failed to fetch has not moved. It is never folded
        # into a bucket, because a zero and an absence of measurement must not
        # look alike -- and here the absence would render as a drop.
        if prev["status"] == ERROR or curr["status"] == ERROR:
            which = [n for n, r in (("older", prev), ("newer", curr))
                     if r["status"] == ERROR]
            out["unmeasured"].append({
                "store": store, "country": country, "group": curr["group"],
                "term": term,
                "reason": f"error in the {' and '.join(which)} capture",
                "error": (curr if curr["status"] == ERROR else prev)["error"],
            })
            continue

        prev_ranked = prev["status"] == RANKED
        curr_ranked = curr["status"] == RANKED

        if prev_ranked and curr_ranked:
            item = _movement(prev, curr, "moved")
            if abs(item["delta"]) > noise:
                out["moved"].append(item)
            else:
                out["flat_n"] += 1
        elif not prev_ranked and curr_ranked:
            out["entered"].append(_movement(prev, curr, "entered"))
        elif prev_ranked and not curr_ranked:
            out["dropped"].append(_movement(prev, curr, "dropped"))
        else:
            # Absent both times. Not movement, but counted so the buckets and
            # the term count reconcile and nothing goes missing in silence.
            out["still_absent_n"] += 1

    # Biggest first in each bucket: the top of a list is what gets read.
    out["moved"].sort(key=lambda i: (-abs(i["delta"]), i["country"], i["term"]))
    out["entered"].sort(key=lambda i: (i["curr_rank"], i["country"], i["term"]))
    out["dropped"].sort(key=lambda i: (i["prev_rank"], i["country"], i["term"]))
    out["unmeasured"].sort(key=lambda i: (i["country"], i["term"]))
    return out


def diff(records, store, against=None, noise=NOISE):
    """Diff the two most recent captures FOR ONE STORE.

    Per store, not globally: iOS and Play were baselined five minutes apart and
    Play carries an extra day-0 capture, so a global "last two" would compare
    Apple against Play and report the difference between two shops as movement.
    """
    stamps = captures(records, store)
    if not stamps:
        return None
    curr_stamp = stamps[0]
    prev_stamp = against or (stamps[1] if len(stamps) > 1 else None)
    if prev_stamp is None:
        return {"store": store, "prev": None, "curr": curr_stamp,
                "moved": [], "entered": [], "dropped": [], "flat_n": 0,
                "still_absent_n": 0, "unmeasured": []}
    if prev_stamp not in stamps:
        raise ValueError(
            f"no {store} capture at {prev_stamp}; have {', '.join(stamps)}"
        )

    def rows(stamp):
        return [r for r in records
                if r["store"] == store and r["captured_at"] == stamp]

    result = diff_captures(rows(prev_stamp), rows(curr_stamp), noise=noise)
    result["store"] = store
    result["prev"] = prev_stamp
    result["curr"] = curr_stamp
    return result


def describe(item):
    """One human-readable line for a movement. Shared by the CLI and the digest."""
    where = f"{item['country']} {item['term']}"
    if item["curr_rank"] is None:
        proven = "absent" if item["absence_proven"] else "outside a capped window"
        tail = "" if item["absence_proven"] else ", absence not proven"
        note = ""
        if item["attribution"] == VACATED:
            note = "  vacated, nobody took the slot"
        elif item["attribution"] == DISPLACED:
            note = f"  displaced by {', '.join(item['attributed_to'])}"
        elif item["attribution"] == TURNED_OVER:
            note = "  result set turned over"
        return f"{where}: {item['prev_rank']} -> {proven}{tail}{note}"
    if item["prev_rank"] is None:
        prior = ("absent" if item["absence_proven"]
                 else "previously outside a capped window, absence was never proven")
        return f"{where}: entered at {item['curr_rank']} from {prior}"
    direction = "down" if item["delta"] > 0 else "up"
    note = ""
    if item["attribution"] == DISPLACED:
        note = f"  displaced by {', '.join(item['attributed_to'])}"
    elif item["attribution"] == VACATED:
        note = "  vacated, nobody took the slot"
    elif item["attribution"] == TURNED_OVER:
        note = "  result set turned over"
    return (f"{where}: {item['prev_rank']} -> {item['curr_rank']} "
            f"({direction} {abs(item['delta'])}){note}")


def render_diff(result, noise=NOISE):
    """Plain-text diff for the CLI."""
    if result is None:
        return "No captures."
    lines = [f"{result['store']}: {result['prev'] or '(no earlier capture)'}"
             f" -> {result['curr']}", "=" * 72]
    if result["prev"] is None:
        lines.append("Only one capture for this store; nothing to compare yet.")
        return "\n".join(lines)
    for title, key in (("Moved", "moved"), ("Entered", "entered"),
                       ("Dropped", "dropped")):
        items = result[key]
        lines.append("")
        lines.append(f"{title} ({len(items)})")
        if not items:
            lines.append("  none")
        for item in items:
            lines.append(f"  {describe(item)}")
    lines.append("")
    lines.append(f"Flat within +/-{noise}: {result['flat_n']}   "
                 f"still absent: {result['still_absent_n']}")
    if result["unmeasured"]:
        lines.append("")
        lines.append(f"!! NOT MEASURED ({len(result['unmeasured'])}) "
                     "- these have not moved, they were never read:")
        for item in result["unmeasured"]:
            lines.append(f"   {item['country']} {item['term']}: {item['reason']}")
    return "\n".join(lines)


# ── Backfill ─────────────────────────────────────────────────────────────────

def backfill_records(root=REPO_ROOT):
    """Records for the three pre-series captures, in timestamp order."""
    out = []
    for rel, store, stamp, _why in BACKFILL:
        path = os.path.join(root, rel)
        with open(path, encoding="utf-8") as fh:
            rows_by_country = json.load(fh)
        out.extend(to_records(store, rows_by_country, stamp))
    return out


def backfill(path, root=REPO_ROOT, write=False):
    """Add any missing pre-series captures. Idempotent.

    Skips every `(captured_at, store)` already present, so a re-run cannot
    double the series -- which matters because there is no delete path.
    """
    existing = {(r["captured_at"], r["store"]) for r in read(path)}
    pending = [r for r in backfill_records(root)
               if (r["captured_at"], r["store"]) not in existing]
    if write and pending:
        append(path, pending)
    return pending


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_captures(args):
    records = read(args.csv)
    if not records:
        print(f"No series at {args.csv}", file=sys.stderr)
        return 1
    for store in STORES:
        stamps = captures(records, store)
        print(f"{store}:")
        for stamp in stamps:
            n = sum(1 for r in records
                    if r["captured_at"] == stamp and r["store"] == store)
            print(f"  {stamp}  {n} rows")
    print(f"\n{len(records)} rows total in {args.csv}")
    return 0


def _cmd_diff(args):
    records = read(args.csv)
    if not records:
        print(f"No series at {args.csv}", file=sys.stderr)
        return 1
    stores = [args.store] if args.store else list(STORES)
    for i, store in enumerate(stores):
        try:
            result = diff(records, store, against=args.against, noise=args.noise)
        except ValueError as exc:
            # A mistyped --against is a typo, not a stack trace.
            print(str(exc), file=sys.stderr)
            return 1
        if result is None:
            print(f"{store}: no captures", file=sys.stderr)
            continue
        if i:
            print()
        print(render_diff(result, noise=args.noise))
    return 0


def _cmd_backfill(args):
    pending = backfill(args.csv, write=args.write)
    if not pending:
        print("Nothing to backfill; all three captures are already in the series.")
        return 0
    grouped = {}
    for rec in pending:
        grouped.setdefault((rec["captured_at"], rec["store"]), 0)
        grouped[(rec["captured_at"], rec["store"])] += 1
    verb = "Appended" if args.write else "Would append"
    for (stamp, store), n in sorted(grouped.items()):
        print(f"{verb} {n:>4} rows  {store:<8} {stamp}")
    if not args.write:
        print("\nDry run. Re-run with --write to append.")
    return 0


def main(argv=None):
    # --csv hangs off each subcommand rather than the top-level parser: a
    # top-level option has to be typed before the subcommand, and every caller
    # here (wrapper script, tests, Benedict) writes it after.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--csv", default=DEFAULT_CSV, help="series path")

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("captures", parents=[common],
                   help="list capture timestamps per store")

    bf = sub.add_parser("backfill", parents=[common],
                        help="add the three pre-series 2026-08-13 captures")
    bf.add_argument("--write", action="store_true", help="actually append (default: dry run)")

    df = sub.add_parser("diff", parents=[common],
                        help="compare the two most recent captures, per store")
    df.add_argument("--store", choices=STORES, help="one store (default: both)")
    df.add_argument("--against", help="compare against this captured_at instead "
                                      "of the second-newest")
    df.add_argument("--noise", type=int, default=NOISE,
                    help=f"positions of drift to treat as flat (default {NOISE})")

    args = ap.parse_args(argv)
    if args.cmd == "captures":
        return _cmd_captures(args)
    if args.cmd == "backfill":
        return _cmd_backfill(args)
    if args.cmd == "diff":
        return _cmd_diff(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
