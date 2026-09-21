#!/usr/bin/env python3
"""Split state/business-state.json into a metrics file plus state/findings/ (DEC-349).

One-off, but committed and re-runnable against the pre-split file so the result is
re-derivable rather than a thing that happened once (DEC-313). It is idempotent in
the only sense that matters: it refuses to run against an already-split file rather
than doing half a job.

Usage:
    python3 tools/state/split_business_state.py --check    # report, write nothing
    python3 tools/state/split_business_state.py --execute
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from findings_manifest import (  # noqa: E402
    EMPTY_CONTAINERS,
    METRIC_KEYS,
    MOVES,
    SEO_METRIC_KEYS,
)

REPO = Path(__file__).resolve().parent.parent.parent
STATE = REPO / "state" / "business-state.json"
FINDINGS = REPO / "state" / "findings"


def dig(state, path):
    """Pop the value at tracks.<path> and return it, or None if it is not there."""
    node = state["tracks"]
    for part in path[:-1]:
        if part not in node:
            return None
        node = node[part]
    return node.pop(path[-1], None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not (args.execute or args.check):
        ap.error("pass --check or --execute")

    state = json.loads(STATE.read_text())
    before = len(json.dumps(state))

    # Deepest paths first, so a nested finding is lifted out before its parent moves.
    moves = sorted(MOVES, key=lambda m: -len(m[0]))

    written, missing = [], []
    for path, slug, date, claim in moves:
        track = path[0]
        body = dig(state, path)
        if body is None:
            missing.append(".".join(path))
            continue
        # tracks.b.seo keeps its current GSC numbers; only the findings move.
        if path == ("b", "seo"):
            kept = {k: body.pop(k) for k in SEO_METRIC_KEYS if k in body}
            state["tracks"]["b"]["seo"] = kept
        written.append({
            "path": FINDINGS / track / f"{slug}.json",
            "doc": {
                "claim": claim,
                "date": date,
                "track": track,
                "was": "tracks." + ".".join(path),
                "body": body,
            },
        })

    if missing:
        print(f"REFUSING: {len(missing)} manifest paths are not in the state file:")
        for m in missing:
            print(f"  {m}")
        print("The file may already be split. Nothing written.")
        return 1

    for track, key in EMPTY_CONTAINERS:
        leftover = state["tracks"].get(track, {}).get(key)
        if leftover:
            print(f"REFUSING: tracks.{track}.{key} was declared an empty container "
                  f"but still holds {sorted(leftover)}")
            return 1
        state["tracks"].get(track, {}).pop(key, None)

    # Nothing may be left behind that was not declared a metric. A finding that
    # silently stays in the state file is the failure this whole change is about.
    stray = []
    for track, keys in METRIC_KEYS.items():
        allowed = set(keys)
        for k in state["tracks"].get(track, {}):
            if k not in allowed:
                stray.append(f"tracks.{track}.{k}")
    if stray:
        print(f"REFUSING: {len(stray)} track keys are neither a declared metric nor a move:")
        for s in stray:
            print(f"  {s}")
        return 1

    after = len(json.dumps(state, indent=2))
    print(f"business-state.json  {before:,}B -> {after:,}B")
    print(f"findings             {len(written)} files")
    if args.check:
        print("(--check: nothing written)")
        return 0

    for item in written:
        item["path"].parent.mkdir(parents=True, exist_ok=True)
        item["path"].write_text(json.dumps(item["doc"], indent=2, ensure_ascii=False) + "\n")
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {FINDINGS}/ and {STATE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
