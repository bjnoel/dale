#!/usr/bin/env python3
"""
Assert every watched variety slug still resolves to something.

This is the check that catches a missed slug migration BEFORE a subscriber
does. A watch whose slug has no page is an alert whose "View X on
treestock.com.au" link 404s, and nothing else in the pipeline complains:
build_variety_pages.py deletes orphan pages silently, and send_variety_alerts.py
happily sends an alert for a slug with no page behind it.

A slug is considered resolved when it has a generated /variety/ page, or is in
GRANDFATHERED_VARIETY_SLUGS (which exists precisely to keep those alerts alive).

Some slugs are legitimately unresolved: a variety can simply leave every
nursery's catalogue. That is why this reports a COUNT and compares it to a
baseline rather than failing on any unresolved slug at all. What must not
happen is the number growing across a deploy, because that means the change
moved slugs out from under live watchers.

Usage, on the server, AFTER build_variety_pages.py has run:
    python3 check_watched_slugs.py                      # report
    python3 check_watched_slugs.py --baseline 12        # exit 1 if it grew

Run it BEFORE the change too, to establish the baseline honestly.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cultivar_parsing import GRANDFATHERED_VARIETY_SLUGS  # noqa: E402
from stocklib.variety_index import DEFAULT_INDEX_PATH, get_variety_index  # noqa: E402

DB = Path("/opt/dale/data/variety_watches.db")


def unresolved_slugs(watch_counts: dict, pages, grandfathered=None) -> list:
    """[(slug, watcher_count)] for watches that point at nothing, worst first.

    `pages` is anything supporting `in`: the variety index, or a set of slugs.
    """
    if grandfathered is None:
        grandfathered = GRANDFATHERED_VARIETY_SLUGS
    return sorted(
        ((slug, n) for slug, n in watch_counts.items()
         if slug not in pages and slug not in grandfathered),
        key=lambda r: (-r[1], r[0]))


def main() -> None:
    baseline = None
    if "--baseline" in sys.argv:
        baseline = int(sys.argv[sys.argv.index("--baseline") + 1])

    if not DB.exists():
        print(f"No DB at {DB}; nothing to check.")
        return

    index = get_variety_index(DEFAULT_INDEX_PATH)
    if not index.available:
        # Failing loudly matters: an empty index would make EVERY watch look
        # unresolved, and a check that cries wolf gets ignored.
        print(f"ERROR: no variety index at {DEFAULT_INDEX_PATH}. "
              f"Run build_variety_pages.py first.", file=sys.stderr)
        sys.exit(2)

    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT variety_slug, COUNT(*) FROM watches GROUP BY variety_slug"
    ).fetchall()
    con.close()

    unresolved = unresolved_slugs(dict(rows), index)

    total_watches = sum(n for _, n in rows)
    print(f"{len(rows)} distinct watched slugs, {total_watches} watches; "
          f"{len(index)} pages in the index")
    if unresolved:
        print(f"\n{len(unresolved)} watched slug(s) resolve to NOTHING "
              f"({sum(n for _, n in unresolved)} watches affected):")
        for slug, n in unresolved:
            print(f"  {slug}  ({n} watcher(s))")
    else:
        print("\nEvery watched slug resolves.")

    if baseline is not None:
        if len(unresolved) > baseline:
            print(f"\nFAIL: unresolved went {baseline} -> {len(unresolved)}. "
                  f"This change moved slugs out from under live watchers. "
                  f"Check migrate_variety_watch_slugs.py ran, and that nothing "
                  f"in variety_overrides.json denies a watched slug.",
                  file=sys.stderr)
            sys.exit(1)
        print(f"\nOK: unresolved {len(unresolved)} <= baseline {baseline}.")


if __name__ == "__main__":
    main()
