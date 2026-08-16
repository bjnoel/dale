#!/usr/bin/env python3
"""
One-shot backfill: replace client-supplied watch titles with canonical ones.

Every row in `watches` predating server-owned titles carries whatever
`variety_title` the caller POSTed. From the homepage that was the raw nursery
listing title ("Advanced Lemon 'Eureka Seedless' 400mm/45Ltr Pot (PICK UP
ONLY)"); from anywhere else it was whatever the caller felt like sending, and
`send_variety_alerts.py` put the first watcher's copy of it in the subject line
and body of mail to every other watcher of that slug.

The builder now writes a canonical {slug: title} index; this rewrites the
stored titles from it.

Rows whose slug is NOT in the index are left exactly as they are. Roughly a
dozen watched slugs have dropped out of live stock and so have no page and no
index entry; blanking their titles would take a recognisable name off a real
person's alert to fix a problem the escaping already fixed.

Idempotent: rerunning changes nothing once titles match the index.
DRY RUN by default; pass --apply to write (a backup is taken first).

Run ON THE SERVER, AFTER build_variety_pages.py has written the index:
    python3 backfill_variety_titles.py            # dry run
    python3 backfill_variety_titles.py --apply
"""
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stocklib.variety_index import DEFAULT_INDEX_PATH, get_variety_index  # noqa: E402

DB = Path("/opt/dale/data/variety_watches.db")
INDEX = DEFAULT_INDEX_PATH


def main() -> None:
    apply = "--apply" in sys.argv
    if not DB.exists():
        print(f"No DB at {DB}; nothing to do.")
        return

    index = get_variety_index(INDEX)
    if not index.available:
        # Failing loudly matters: a silent no-op here looks identical to
        # "everything was already canonical".
        print(f"ERROR: no variety index at {INDEX}. Run build_variety_pages.py "
              f"first.", file=sys.stderr)
        sys.exit(1)
    print(f"{len(index)} canonical titles in {INDEX}")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    watches = con.execute(
        "SELECT id, email, variety_slug, variety_title FROM watches"
    ).fetchall()

    plan = []      # (id, slug, old_title, new_title)
    unknown = []   # slugs with no index entry, left alone
    for w in watches:
        canonical = index.title(w["variety_slug"])
        if canonical is None:
            unknown.append(w["variety_slug"])
            continue
        if canonical != w["variety_title"]:
            plan.append((w["id"], w["variety_slug"], w["variety_title"], canonical))

    print(f"{len(watches)} watches; {len(plan)} titles to rewrite; "
          f"{len(set(unknown))} slug(s) not in the index (left alone):")
    for _id, slug, old, new in plan:
        print(f"  [{slug}] {old!r}  ->  {new!r}")
    for slug in sorted(set(unknown)):
        print(f"  [{slug}] not in index, keeping stored title")

    if not plan:
        print("\nNothing to do.")
        return

    if not apply:
        print("\nDRY RUN. Re-run with --apply to write.")
        return

    backup = DB.with_name(DB.name + ".pre-title-backfill.bak")
    shutil.copy2(DB, backup)
    print(f"Backed up DB to {backup}")

    for wid, _slug, _old, new in plan:
        con.execute("UPDATE watches SET variety_title = ? WHERE id = ?", (new, wid))
    con.commit()
    print(f"watches: {len(plan)} titles rewritten")


if __name__ == "__main__":
    main()
