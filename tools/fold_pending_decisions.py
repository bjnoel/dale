#!/usr/bin/env python3
"""
Fold pending decision fragments into the decision log, assigning sequential DEC numbers.

Why this exists: when several guide-building agents run in parallel (see
docs/species-guide-rollout.md), each one editing decisions/decision-log.md at the same
spot, and each guessing the same next DEC number, produces a merge conflict every time
the second and later branches land. So a parallel run writes a uniquely-named fragment
to decisions/pending/ instead (those never collide), and this script folds them into the
log in one serialized, conflict-free step after the batch has merged.

Fragment format (decisions/pending/YYYY-MM-DD-<slug>.md):

    # One-line title (becomes the DEC header)

    <body markdown: Decided by / Context / Decision / Why / Actions / Status / To revert>

Run from the repo root after merging a batch:

    python3 tools/fold_pending_decisions.py            # fold, then delete the fragments
    python3 tools/fold_pending_decisions.py --dry-run  # show what would happen, change nothing

The script only PREPENDS new entries (it never edits past ones), matching the log's
"append-only, newest at top" convention.
"""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LOG = REPO / "decisions" / "decision-log.md"
DEFAULT_PENDING = REPO / "decisions" / "pending"

DEC_RE = re.compile(r"^##\s*DEC-(\d+)\b", re.M)
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
# Match the existing header style, e.g. "## DEC-130 — 2026-06-02 — Guava ...".
EM_DASH = "—"


def max_dec(log_text: str) -> int:
    nums = [int(m) for m in DEC_RE.findall(log_text)]
    return max(nums) if nums else 0


def parse_fragment(path: Path):
    text = path.read_text(encoding="utf-8").strip()
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        title = lines[0].lstrip("#").strip()
        body = "\n".join(lines[1:]).strip()
    else:
        title = path.stem
        body = text
    m = DATE_RE.match(path.name)
    return title, (m.group(1) if m else ""), body


def fold(log_path: Path, pending_dir: Path, dry_run: bool = False) -> int:
    if not pending_dir.exists():
        print(f"No pending directory at {pending_dir}; nothing to fold.")
        return 0
    frags = sorted(p for p in pending_dir.glob("*.md") if p.name.lower() != "readme.md")
    if not frags:
        print("No pending decision fragments to fold.")
        return 0

    log_text = log_path.read_text(encoding="utf-8")
    n = max_dec(log_text)
    blocks = []  # (dec_num, fragment_path, formatted_block)
    for frag in frags:
        n += 1
        title, date, body = parse_fragment(frag)
        head = f"## DEC-{n} {EM_DASH} {date} {EM_DASH} {title}" if date else f"## DEC-{n} {EM_DASH} {title}"
        blocks.append((n, frag, f"{head}\n\n{body}\n"))
        print(f"  DEC-{n}  <-  {frag.name}  ({title})")

    # Newest (highest number) sits at the top, matching the existing convention.
    new_section = "\n".join(b for _, _, b in reversed(blocks)) + "\n"
    parts = log_text.split("\n---\n", 1)
    if len(parts) == 2:
        updated = parts[0] + "\n---\n\n" + new_section + parts[1].lstrip("\n")
    else:  # no divider found; just prepend
        updated = new_section + log_text

    if dry_run:
        print(f"\n[dry-run] would assign {len(blocks)} DEC number(s), prepend them to "
              f"{log_path.name}, and delete the fragments. No changes made.")
        return 0

    log_path.write_text(updated, encoding="utf-8")
    for _, frag, _ in blocks:
        frag.unlink()
    print(f"\nFolded {len(blocks)} decision(s) into {log_path.name} and removed the fragments.")
    print("Close-out reminders: regenerate the archive index "
          "(python3 tools/scrapers/build_archive_index.py) and tick the Progress list in "
          "docs/species-guide-rollout.md for the species that landed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", type=Path, default=DEFAULT_LOG, help="path to decision-log.md")
    ap.add_argument("--pending", type=Path, default=DEFAULT_PENDING, help="path to the pending/ fragment dir")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    args = ap.parse_args()
    return fold(args.log, args.pending, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
