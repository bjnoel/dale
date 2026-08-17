#!/usr/bin/env python3
"""
Turn queued curation decisions into a commit against variety_overrides.json.

The other half of plan section 5. Alias and deny are configuration, not
operational state: `canonical_cultivar` applies them, so the builders, the alert
gate and the alert sender all inherit them, and `deploy.sh` rsyncs the file, so
a browser writing it on the server is overwritten within the hour. Layering a
second server-side copy over the git one would work and would create a second
place curation lives, which this codebase has consistently refused.

So the browser queues and this promotes. Benedict decides in the UI, Dale does
the mechanical half, git stays the single source of truth, and the decision is
reviewable as a diff with his name in the commit message.

    python3 promote_curation.py                 # dry run, prints the diff
    python3 promote_curation.py --execute       # write, test, commit
    python3 promote_curation.py --execute --push

The suite runs before the commit, not after. An alias that breaks
`canonical_cultivar` would otherwise be committed and deployed before anything
noticed, and the symptom (a variety page quietly moving) is the kind that shows
up in Search Console two months later.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stocklib import admin_decisions as ad

# Skip reasons meaning "the file already says this", as opposed to "this row is
# malformed". A satisfied row is DONE and must leave the queue: leaving it there
# is what made a failed push strand it forever, showing "folded into X" in the
# review UI with no run able to clear it.
ALREADY_ALIASED = "already aliased there"
ALREADY_DENIED = "already denied"
SATISFIED = (ALREADY_ALIASED, ALREADY_DENIED)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OVERRIDES = Path(__file__).resolve().parent / "variety_overrides.json"
DEFAULT_DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", "/opt/dale/data"))


def load_overrides(path: Path) -> dict:
    """The whole file, not the two keys this script edits.

    It used to return exactly {"deny": ..., "alias": ...}, and `render` dumps
    whatever it is handed, so the first promotion would have deleted the 29-line
    `_readme` block: the description of how alias and deny interact, the warning
    to check watch counts before aliasing, and "Do NOT run
    migrate_variety_watch_slugs.py", which is the one instruction in this repo
    that protects live subscribers' alerts from being moved onto pages that do
    not exist. Silently, in a commit whose message says it added four aliases.

    Nothing had caught it because the alias map was empty: promotion had never
    run in production, so the destructive path had never executed.
    """
    if not path.exists():
        return {"deny": [], "alias": {}}
    raw = json.loads(path.read_text())
    raw["deny"] = list(raw.get("deny") or [])
    raw["alias"] = dict(raw.get("alias") or {})
    return raw


def merge(overrides: dict, pending: list) -> tuple[dict, list, list]:
    """Apply the queue to a copy of the overrides. Returns (new, applied, skipped).

    A row that asks for something already true is skipped rather than applied:
    promoting it would produce an empty diff and an empty commit, and a commit
    that changes nothing is a commit nobody can review.
    """
    # Copy the whole file, then edit the two keys this script owns. Building a
    # fresh two-key dict is what dropped `_readme`.
    new = dict(overrides)
    new["deny"] = sorted(set(overrides["deny"]))
    new["alias"] = dict(overrides["alias"])
    applied, skipped = [], []
    for row in pending:
        kind, slug = row.get("kind"), row.get("from")
        if not slug:
            skipped.append((row, "no slug"))
            continue
        if kind == ad.ALIAS:
            target = row.get("to")
            if not target:
                skipped.append((row, "no target"))
                continue
            if new["alias"].get(slug) == target:
                skipped.append((row, ALREADY_ALIASED))
                continue
            # canonical_cultivar applies the map once with no chain resolution,
            # so A -> B where B -> C leaves A at B. Refuse rather than write a
            # map that quietly does half of what it looks like it does.
            if target in new["alias"]:
                skipped.append((row, f"target {target} is itself aliased to "
                                     f"{new['alias'][target]}"))
                continue
            if slug in new["alias"].values():
                skipped.append((row, "other aliases point AT this slug"))
                continue
            new["alias"][slug] = target
            applied.append(row)
        elif kind == ad.DENY:
            if slug in new["deny"]:
                skipped.append((row, ALREADY_DENIED))
                continue
            new["deny"] = sorted(set(new["deny"]) | {slug})
            applied.append(row)
        else:
            skipped.append((row, f"unknown kind {kind!r}"))
    new["alias"] = dict(sorted(new["alias"].items()))
    return new, applied, skipped


def render(overrides: dict) -> str:
    return json.dumps(overrides, indent=2, sort_keys=True) + "\n"


def commit_message(applied: list) -> str:
    who = sorted({r.get("by") for r in applied if r.get("by")})
    aliases = [r for r in applied if r.get("kind") == ad.ALIAS]
    denies = [r for r in applied if r.get("kind") == ad.DENY]
    bits = []
    if aliases:
        bits.append(f"{len(aliases)} alias{'es' if len(aliases) != 1 else ''}")
    if denies:
        bits.append(f"{len(denies)} deny")
    head = f"chore: curation from /admin/varieties/review ({', '.join(bits)})"
    lines = [head, ""]
    for r in aliases[:40]:
        lines.append(f"  {r['from']} -> {r['to']}")
    if len(aliases) > 40:
        lines.append(f"  ... and {len(aliases) - 40} more")
    for r in denies[:20]:
        lines.append(f"  deny {r['from']}")
    lines += ["",
              "Queued in the browser, promoted by promote_curation.py. The map is",
              "applied inside canonical_cultivar, so the products move under the",
              "target on the next build and the lifecycle emits the redirect two",
              "nights later on its own."]
    if who:
        lines += ["", f"Approved-by: {', '.join(who)}"]
    return "\n".join(lines)


def clear_queue(path: Path, slugs: set) -> int:
    """Drop promoted or already-satisfied rows. Re-reads first, so anything
    queued while the suite was running survives."""
    if not slugs:
        return 0
    fresh = ad.load_decisions(path)
    fresh["curation_pending"] = [r for r in (fresh.get("curation_pending") or [])
                                 if r.get("from") not in slugs]
    ad.save_decisions(path, fresh)
    return len(slugs)


def run(cmd: list, cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--overrides", type=Path, default=OVERRIDES)
    ap.add_argument("--execute", action="store_true",
                    help="write, run the suite, and commit. Without it, print "
                         "what would happen and change nothing")
    ap.add_argument("--push", action="store_true",
                    help="push after committing (implies --execute)")
    ap.add_argument("--skip-tests", action="store_true",
                    help="do not run the suite. For a rerun where it just passed, "
                         "never for the first run of a batch")
    args = ap.parse_args()
    if args.push:
        args.execute = True

    path = ad.decisions_path(args.data_dir)
    store = ad.load_decisions(path)
    pending = store.get("curation_pending") or []
    if not pending:
        print("Nothing queued.")
        return 0

    current = load_overrides(args.overrides)
    new, applied, skipped = merge(current, pending)

    print(f"{len(pending)} queued, {len(applied)} to apply, {len(skipped)} skipped")
    for row in applied:
        arrow = f" -> {row['to']}" if row.get("kind") == ad.ALIAS else ""
        print(f"  {row['kind']:<6} {row['from']}{arrow}   ({row.get('by', '?')})")
    for row, why in skipped:
        print(f"  SKIP   {row.get('from')}: {why}")

    satisfied = {r.get("from") for r, why in skipped if why in SATISFIED}
    if not applied:
        print("Nothing to write.")
        # Every row asks for something the file already says. That is a finished
        # decision, not a pending one, and the previous version returned here
        # without clearing it. A push that failed after the commit left exactly
        # this state, and no later run could ever get out of it.
        if satisfied and args.execute:
            print(f"Cleared {clear_queue(path, satisfied)} already-applied "
                  f"row(s) from the queue.")
        return 0
    if not args.execute:
        print("\nDry run. Re-run with --execute to write, test and commit.")
        return 0

    args.overrides.write_text(render(new))
    print(f"Wrote {args.overrides}")

    if not args.skip_tests:
        print("Running the suite...")
        code, out = run([sys.executable, "-m", "unittest", "discover", "tests/"],
                        REPO_ROOT)
        if code != 0:
            # Put the file back. A half-promoted curation file on disk is worse
            # than an unpromoted queue: the next deploy would ship it.
            args.overrides.write_text(render(current))
            print(out[-4000:])
            print("\nTESTS FAILED. Reverted the override file, queue left intact.")
            return 1
        print("Suite green.")

    rel = str(args.overrides.relative_to(REPO_ROOT))
    for cmd in ([["git", "add", rel],
                 ["git", "commit", "-m", commit_message(applied)]]):
        code, out = run(cmd, REPO_ROOT)
        if code != 0:
            print(out)
            print("Commit failed, override file left written and queue intact.")
            return 1
    print("Committed.")

    if args.push:
        code, out = run(["git", "push"], REPO_ROOT)
        print(out.strip() or "Pushed.")
        if code != 0:
            return 1

    # Only now is the queue safe to clear: the decision is in git.
    done = {r["from"] for r in applied} | satisfied
    print(f"Cleared {clear_queue(path, done)} promoted row(s) from the queue.")
    print("\nNOT live yet: this needs a deploy to reach the server, and then the "
          "next build to move the products.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
