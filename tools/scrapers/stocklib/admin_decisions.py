"""
Decisions a human made in the browser, for the nightly to apply.

The admin UI does not edit the ledger, and that is the whole design. Both
builders load the ledger, mutate it and write the entire file back
(`PageLedger.save`), so a web write landing at 00:00:30 is gone by 00:05 with
nothing to show it ever happened. The UI writes *intent* here instead, and the
nightly adopts it the same way `--seed-reviewed` adopts the R1 proposals:
re-testing every condition against tonight's build rather than trusting the file.

That indirection buys the safety property the confirmation dialogs advertise.
Nothing a click does reaches the site until the 00:00 UTC build, so every
decision has a whole day in which changing your mind costs an edit rather than
an incident.

Three sections, because there are three genuinely different kinds of decision:

  redirects         operational state. Where a dead URL points, or whether it is
                    a redirect or a tombstone. Affects one URL, nothing derives
                    from it, the server owns it outright. (DAL-284)
  siblings          "I looked at this pair and they are different plants."
                    Suppression, not configuration: it changes what the queue
                    shows, never what the parser does. (DAL-285)
  curation_pending  alias and deny, queued for `promote_curation.py` to turn
                    into a commit against `variety_overrides.json`. These are
                    configuration: `canonical_cultivar` applies them, so every
                    surface inherits them, and `deploy.sh` rsyncs the file, so a
                    browser writing it on the server is overwritten within the
                    hour. Queue-and-promote is the answer to that, not a second
                    copy of the file. (DAL-285, plan section 5)

Nothing here deletes anything. Every action is a state a later night can move
back, which is what makes a browser button an acceptable place to make it from.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .page_ledger import atomic_write

SCHEMA = 1

DECISIONS_FILENAME = "variety-decisions.json"

# What a `redirects` entry may ask for. Deliberately not "delete": the ledger's
# own delete paths sit behind `--allow-delete` on the nightly and stay there.
RETARGET = "retarget"      # redirect -> a different target
TO_TOMBSTONE = "tombstone"  # redirect (or retired) -> tombstone, target dropped
TO_REDIRECT = "redirect"   # tombstone (or retired) -> redirect at a target
REDIRECT_ACTIONS = (RETARGET, TO_TOMBSTONE, TO_REDIRECT)

# What a `curation_pending` row may ask for. Mirrors the two keys
# variety_overrides.json actually has.
ALIAS = "alias"
DENY = "deny"
CURATION_KINDS = (ALIAS, DENY)

DISTINCT = "distinct"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def decisions_path(data_dir: Path | str) -> Path:
    return Path(data_dir) / DECISIONS_FILENAME


def sibling_key(a: str, b: str) -> str:
    """Order-independent key for a pair.

    Sorted, so dismissing (hass, hass-lamb) also dismisses (hass-lamb, hass).
    The queue renders base-first and a future change to that ordering must not
    silently un-dismiss 400 pairs.
    """
    return "|".join(sorted((a, b)))


def empty() -> dict:
    return {"schema": SCHEMA, "updated": None,
            "redirects": {}, "siblings": {}, "curation_pending": []}


def load_decisions(path: Path | str) -> dict:
    """Read the file, defensively. A missing or corrupt file is an empty set of
    decisions, never an exception: the nightly must not die because a UI wrote
    something malformed, and the admin page must still render."""
    path = Path(path)
    data = empty()
    if not path.exists():
        return data
    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError("not an object")
    except (OSError, ValueError) as e:
        print(f"WARNING: unreadable decisions file {path}: {e}")
        return data
    if isinstance(raw.get("redirects"), dict):
        data["redirects"] = {k: v for k, v in raw["redirects"].items()
                             if isinstance(v, dict)}
    if isinstance(raw.get("siblings"), dict):
        data["siblings"] = {k: v for k, v in raw["siblings"].items()
                            if isinstance(v, dict)}
    if isinstance(raw.get("curation_pending"), list):
        data["curation_pending"] = [r for r in raw["curation_pending"]
                                    if isinstance(r, dict)]
    data["updated"] = raw.get("updated")
    return data


def save_decisions(path: Path | str, data: dict, now: str = None) -> Path:
    """Write atomically. A half-written decisions file would be read as "no
    decisions" on exactly the night the decisions mattered."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["schema"] = SCHEMA
    payload["updated"] = now or utc_now()
    atomic_write(path, json.dumps(payload, indent=1, sort_keys=True).encode())
    return path


def record_redirect(data: dict, slug: str, action: str, target: str = "",
                    by: str = "", now: str = None) -> dict:
    """Queue a redirect/tombstone change for tonight.

    One entry per slug: deciding twice before the build runs means the second
    decision wins, which is what a reviewer correcting themselves expects. The
    superseded one is not history worth keeping in a file the nightly reads.
    """
    if action not in REDIRECT_ACTIONS:
        raise ValueError(f"unknown redirect action {action!r}")
    if action in (RETARGET, TO_REDIRECT) and not target:
        raise ValueError(f"{action} needs a target")
    entry = {"action": action, "by": by, "at": now or utc_now()}
    if action != TO_TOMBSTONE:
        entry["target"] = target
    data.setdefault("redirects", {})[slug] = entry
    return entry


def dismiss_sibling(data: dict, base: str, other: str, by: str = "",
                    now: str = None) -> dict:
    """Record that a pair is two different plants.

    The single change that turns the sibling queue from a wall into a backlog:
    319 groups regenerate identically every night, and without somewhere to put
    "I looked", opening it twice is the same work twice.
    """
    entry = {"decision": DISTINCT, "by": by, "at": now or utc_now()}
    data.setdefault("siblings", {})[sibling_key(base, other)] = entry
    return entry


def restore_sibling(data: dict, base: str, other: str) -> bool:
    """Undo a dismissal. Dismissing is a judgement and judgements are wrong
    sometimes; a decision you cannot take back is one people stop making."""
    return data.setdefault("siblings", {}).pop(sibling_key(base, other),
                                               None) is not None


def queue_curation(data: dict, kind: str, slug: str, target: str = "",
                   by: str = "", now: str = None) -> dict:
    """Queue an alias or a deny for promote_curation.py to commit.

    NOT applied here and not applied by the nightly. `variety_overrides.json` is
    git-tracked and `deploy.sh` rsyncs it, so the only way a curation call
    survives is as a commit.
    """
    if kind not in CURATION_KINDS:
        raise ValueError(f"unknown curation kind {kind!r}")
    if kind == ALIAS and not target:
        raise ValueError("an alias needs a target")
    if kind == ALIAS and target == slug:
        raise ValueError("an alias to itself is a cycle")
    pending = data.setdefault("curation_pending", [])
    row = {"kind": kind, "from": slug, "by": by, "at": now or utc_now()}
    if kind == ALIAS:
        row["to"] = target
    # Re-queueing the same slug replaces the earlier row rather than stacking a
    # second one: promote would otherwise write two lines for one key and the
    # later would silently win.
    pending[:] = [r for r in pending if r.get("from") != slug]
    pending.append(row)
    return row


def drop_curation(data: dict, slug: str) -> bool:
    pending = data.setdefault("curation_pending", [])
    before = len(pending)
    pending[:] = [r for r in pending if r.get("from") != slug]
    return len(pending) != before


def dismissed_pairs(data: dict) -> set:
    """Every pair marked distinct, as sibling_key strings."""
    return {k for k, v in (data.get("siblings") or {}).items()
            if v.get("decision") == DISTINCT}
