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
"""

import argparse
import csv
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from appstore_rank import LIMIT, TERMS  # noqa: E402  the shared term set
from playstore_rank import saturated  # noqa: E402  Play's window rule, not re-derived

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

    args = ap.parse_args(argv)
    if args.cmd == "captures":
        return _cmd_captures(args)
    if args.cmd == "backfill":
        return _cmd_backfill(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
