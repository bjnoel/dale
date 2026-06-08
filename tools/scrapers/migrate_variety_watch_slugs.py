#!/usr/bin/env python3
"""
One-shot migration: re-slug variety watches after the 2026-06-08 cultivar
parsing cleanup (DEC-176).

parse_cultivar now strips listing noise (pot sizes, "(grafted)", "QLD ONLY",
"Super Dwarf", the "bear rooted" typo, ...) from cultivar names so size and
rootstock variants of one cultivar collapse to a single variety slug. Existing
watches keyed to the OLD fragmented slugs ("sapodilla-grafted-krasuey",
"feijoa-mammoth-5l", "dwarf-cumquat-meiwa-qld-only", ...) would otherwise never
match live stock again, silently breaking those restock alerts.

For each watch this recomputes the slug from its stored variety_title with the
NEW parser; where it changed, it updates variety_slug + species_slug, dedupes
against any existing watch the same email already holds for the new slug, and
remaps the sends-history table with the same old->new map so restock dedupe
keeps working.

Idempotent: rerunning after migration is a no-op (titles already map to their
current slugs). DRY RUN by default; pass --apply to write (after backing up).

Run ON THE SERVER, AFTER deploying the new cultivar_parsing.py:
    python3 migrate_variety_watch_slugs.py            # dry run
    python3 migrate_variety_watch_slugs.py --apply
"""
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cultivar_parsing import parse_cultivar, product_variety_slug, slugify  # noqa: E402

DB = Path("/opt/dale/data/variety_watches.db")


def recompute(title: str) -> tuple[str | None, str | None]:
    """(new_variety_slug, new_species_slug) from a stored variety_title, or
    (None, None) if the title no longer parses as a cultivar (leave it alone)."""
    parsed = parse_cultivar(title or "")
    if not parsed:
        return None, None
    species, _ = parsed
    return product_variety_slug(title), slugify(species)


def main() -> None:
    apply = "--apply" in sys.argv
    if not DB.exists():
        print(f"No DB at {DB}; nothing to do.")
        return

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    watches = con.execute(
        "SELECT id, email, variety_slug, species_slug, variety_title FROM watches"
    ).fetchall()

    slug_map: dict[str, str] = {}                  # old -> new (for the sends table)
    plan: list[tuple[int, str, str, str, str]] = []  # id, email, old, new_v, new_sp
    for w in watches:
        new_v, new_sp = recompute(w["variety_title"])
        if not new_v or new_v == w["variety_slug"]:
            continue
        plan.append((w["id"], w["email"], w["variety_slug"], new_v, new_sp))
        slug_map[w["variety_slug"]] = new_v

    print(f"{len(watches)} watches; {len(plan)} need re-slugging:")
    for _id, email, old, new_v, _new_sp in plan:
        print(f"  [{email}] {old}  ->  {new_v}")

    if not apply:
        print("\nDRY RUN. Re-run with --apply to write.")
        return

    backup = DB.with_name(DB.name + ".pre-reslug.bak")
    shutil.copy2(DB, backup)
    print(f"Backed up DB to {backup}")

    existing = {(w["email"], w["variety_slug"]) for w in watches}
    updated = deduped = 0
    for wid, email, _old, new_v, new_sp in plan:
        if (email, new_v) in existing:
            # This email already watches the merged slug -> drop the duplicate.
            con.execute("DELETE FROM watches WHERE id = ?", (wid,))
            deduped += 1
        else:
            con.execute(
                "UPDATE watches SET variety_slug = ?, species_slug = ? WHERE id = ?",
                (new_v, new_sp, wid),
            )
            existing.add((email, new_v))
            updated += 1

    sends_remapped = 0
    for old, new_v in slug_map.items():
        cur = con.execute(
            "UPDATE OR IGNORE sends SET variety_slug = ? WHERE variety_slug = ?",
            (new_v, old),
        )
        sends_remapped += cur.rowcount
    con.commit()
    print(f"watches: {updated} updated, {deduped} deduped; sends: {sends_remapped} remapped")


if __name__ == "__main__":
    main()
