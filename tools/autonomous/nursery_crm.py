#!/usr/bin/env python3
"""Nursery relationship register (DAL-80).

Benedict asked for a touchlist outside Linear: something that records who we
have contacted, when, and what is outstanding, that he can read and Dale can
read and write programmatically.

This is that, as a git-tracked JSON file plus this CLI. Git history is the
audit log. Referral click counts are deliberately NOT stored in the file: they
are pulled live from Plausible so a report can never show a stale number.

Usage:
  nursery_crm.py report [--period 30d]   Markdown table, newest referral data
  nursery_crm.py due                     Nurseries with an outstanding action
  nursery_crm.py log KEY --date D --direction out|in --channel C --by WHO
                       --summary TEXT [--evidence TEXT]
  nursery_crm.py set KEY --status S | --email E | --contact-name N | --note TEXT
  nursery_crm.py validate                Schema and cross-reference checks
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from urllib.parse import urlparse

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTER_PATH = os.path.join(REPO, "data", "nursery-contacts.json")
SITE_ID = "treestock.com.au"
OUTBOUND_GOAL = "Outbound Link: Click"
VALID_STATUSES = {"not_contacted", "contacted", "unreachable", "warm",
                  "courtesy", "personal"}
VALID_DIRECTIONS = {"out", "in"}


def load_register(path=REGISTER_PATH):
    with open(path) as f:
        return json.load(f)


def save_register(reg, path=REGISTER_PATH):
    reg["updated"] = date.today().isoformat()
    with open(path, "w") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
        f.write("\n")


def find(reg, key):
    for n in reg["nurseries"]:
        if n["key"] == key:
            return n
    raise KeyError(f"unknown nursery key: {key}")


def normalise_domain(url_or_host):
    host = urlparse(url_or_host).netloc if "//" in url_or_host else url_or_host
    host = host.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


# Plausible's v1 stats API only accepts these. It 400s on anything else,
# including the plausible-looking "90d", and api_get turns a 400 into None.
PLAUSIBLE_PERIODS = ("day", "7d", "30d", "month", "6mo", "12mo")


class PlausibleUnavailable(RuntimeError):
    """The API refused or could not be reached. NOT the same as zero clicks."""


def outbound_clicks(period="30d"):
    """Clicks per destination domain from Plausible.

    Paginates: the breakdown is by full URL and there are ~1,000 distinct
    product URLs per month, so a single unpaginated page silently undercounts.
    Returns {} if Plausible is not configured, so a report still renders.

    Raises PlausibleUnavailable if the API answers with an error. A failed
    request and a genuine zero are indistinguishable in the returned dict, and
    rendering "0 outbound clicks" from a 400 is a confident false statement
    about the only revenue-adjacent metric treestock has (DEC-250, DEC-253).
    """
    if period not in PLAUSIBLE_PERIODS:
        raise PlausibleUnavailable(
            f"invalid period {period!r}; Plausible accepts "
            f"{', '.join(PLAUSIBLE_PERIODS)}")

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from plausible_stats import load_plausible_config, api_get

    try:
        token, base = load_plausible_config()
    except (OSError, ValueError) as e:
        print(f"warning: no Plausible config ({e}), referral columns will be blank",
              file=sys.stderr)
        return {}

    agg = {}
    max_pages = 40
    complete = False
    for page in range(1, max_pages + 1):
        res = api_get(base, token, "/api/v1/stats/breakdown", {
            "site_id": SITE_ID, "period": period, "property": "event:props:url",
            "filters": f"event:name=={OUTBOUND_GOAL}",
            "metrics": "events,visitors", "limit": 1000, "page": page,
        })
        if res is None:
            raise PlausibleUnavailable(
                f"Plausible returned an error for period {period!r} on page {page}; "
                "refusing to report zero clicks from a failed request")
        if not res.get("results"):
            complete = True
            break
        for row in res["results"]:
            dom = normalise_domain(row["url"])
            cur = agg.setdefault(dom, {"clicks": 0, "visitors": 0})
            cur["clicks"] += row.get("events", 0)
            cur["visitors"] += row.get("visitors", 0)
        if len(res["results"]) < 1000:
            complete = True
            break
    if not complete:
        # Running off the end of the loop with a full final page means there is
        # more data we did not read. Say so out loud: a silently capped total is
        # exactly the failure behind DEC-250 and DEC-253.
        print(f"warning: Plausible outbound breakdown hit the {max_pages}-page cap; "
              "referral click totals are PARTIAL and understated.", file=sys.stderr)
    return agg


def last_touch(n):
    dates = [t["date"] for t in n.get("touches", [])]
    return max(dates) if dates else None


def days_since(iso, today=None):
    if not iso:
        return None
    today = today or date.today()
    return (today - datetime.strptime(iso, "%Y-%m-%d").date()).days


def contact_route(n):
    if n.get("email"):
        return n["email"]
    if n.get("contact_form"):
        return "form"
    if n.get("phone"):
        return f"phone {n['phone']}"
    return "NONE"


def cmd_report(reg, args):
    try:
        clicks = outbound_clicks(args.period)
    except PlausibleUnavailable as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    rows = []
    for n in reg["nurseries"]:
        c = clicks.get(n["domain"], {})
        rows.append((c.get("clicks", 0), c.get("visitors", 0), n))
    rows.sort(key=lambda r: (-r[0], r[2]["name"]))

    total = sum(r[0] for r in rows)
    # `unreachable` counts as never spoken to, because it is: the message
    # bounced or there was no route to send one. Excluding it would shrink the
    # headline by hiding the nurseries hardest to reach.
    no_relationship = {"not_contacted", "unreachable"}
    uncontacted = sum(r[0] for r in rows if r[2]["status"] in no_relationship)
    print(f"# Nursery relationship register ({args.period} referrals)\n")
    print(f"{len(rows)} nurseries. {total} outbound clicks sent in the last "
          f"{args.period}. {uncontacted} of those ({pct(uncontacted, total)}) went to "
          f"nurseries we have never spoken to.\n")
    # "People", not "Buyers". This column is Plausible `visitors` on the
    # outbound-click goal: how many distinct people clicked through, not how
    # many bought anything. Daleys reads 324 here against the 4 actual sales
    # Correy reported for the same window.
    print("| Nursery | Clicks | People | Status | Last touch | Contact | Outstanding |")
    print("|---|---:|---:|---|---|---|---|")
    for cl, vis, n in rows:
        lt = last_touch(n)
        ds = days_since(lt)
        touch = f"{lt} ({ds}d)" if lt else "never"
        act = n.get("open_action")
        out = f"**{act['owner']}**: {act['what'][:70]}" if act else ""
        print(f"| {n['name']} | {cl} | {vis} | {n['status']} | {touch} | "
              f"{contact_route(n)} | {out} |")
    return 0


def pct(part, whole):
    return f"{round(100 * part / whole)}%" if whole else "n/a"


def cmd_due(reg, args):
    found = 0
    for n in reg["nurseries"]:
        act = n.get("open_action")
        if not act:
            continue
        found += 1
        ds = days_since(act.get("since"))
        age = f", waiting {ds} days" if ds is not None else ""
        print(f"[{act['owner']}] {n['name']}{age}\n    {act['what']}")
    if not found:
        print("Nothing outstanding.")
    return 0


def cmd_log(reg, args):
    n = find(reg, args.key)
    touch = {
        "date": args.date, "direction": args.direction, "channel": args.channel,
        "by": args.by, "summary": args.summary,
    }
    if args.evidence:
        touch["evidence"] = args.evidence
    had = (n.get("open_action") or {}).get("what")
    if not apply_touch(n, touch):
        print(f"{n['name']} already has a touch with evidence "
              f"{touch['evidence']}. Nothing to do.")
        return 0
    if args.clear_action:
        n["open_action"] = None
    save_register(reg)
    print(f"Logged {args.direction} touch for {n['name']} on {args.date}. "
          f"Status now {n['status']}.")
    if had and not n.get("open_action"):
        print(f"  Cleared open action: {had}")
    return 0


INBOUND_LOG = "/opt/dale/data/nursery-inbound.jsonl"


def apply_touch(n, touch):
    """Append a touch to a nursery and advance its status. Shared by `log` and
    `merge-inbound` so a hand-logged touch and a BCC'd one behave identically.

    Returns False when this evidence id is already on the nursery, which is what
    makes the merge idempotent: Resend retries webhooks, and the merge may run
    before a previous run's commit has landed.
    """
    evidence = touch.get("evidence")
    if evidence and any(t.get("evidence") == evidence
                        for t in n.get("touches", [])):
        return False

    n.setdefault("touches", []).append(touch)
    n["touches"].sort(key=lambda t: t["date"])
    if touch["direction"] == "in" and n["status"] == "contacted":
        n["status"] = "warm"
    elif touch["direction"] == "out" and n["status"] == "not_contacted":
        n["status"] = "contacted"
    # `unreachable` deliberately does NOT auto-promote on an outbound touch,
    # and it is the one status that requires an explicit `set --status` to
    # leave. The reason is that a bounce IS an outbound touch: Fruitopia's
    # 2026-03-31 record is one. Promoting on direction alone would relabel
    # every bounce as `contacted`, which is the exact lie this status exists to
    # prevent. Whether a channel actually worked is a judgement the tool cannot
    # make from the touch, so it stays with whoever sent it. Benedict's
    # 2026-08-27 Instagram DM landed, so Fruitopia was moved by hand.

    # An outbound touch discharges the open action, because in every case so far
    # the action IS the outbound touch ("send touch 1.5 to Correy"). Without
    # this the loop never closed: Benedict sent the email, the BCC logged it,
    # and the digest kept asking him to send it. Fruit Tree Lane asked for 134
    # days. Git history keeps the cleared text, so nothing is lost.
    #
    # Inbound is excluded: them replying is not us doing our half.
    # `keep_open` is the escape hatch for an action an email cannot discharge,
    # such as Primal Fruits' "sign up to the affiliate program". Emailing Cyrus
    # about anything else must not silently tick that off.
    if touch["direction"] == "out":
        action = n.get("open_action") or {}
        if action.get("what") and not action.get("keep_open"):
            n["open_action"] = None
    return True


def cmd_merge_inbound(reg, args):
    """Fold BCC'd touches from the inbound log into the register (DAL-273).

    The webhook cannot write the register itself: `deploy.sh` copies the repo
    copy over `/opt/dale/data/nursery-contacts.json` on every deploy, and
    dale-runner deploys hourly, so anything written there is gone within the
    hour. The webhook appends to a JSONL nothing overwrites; this folds it into
    the repo copy, where git history stays the audit log.

    **This is stateless: it reads the log and never writes it.** Every record is
    replayed on every run, and `apply_touch` drops the ones the register already
    has by evidence id, so the whole thing is idempotent by construction.

    It used to stamp `merged: true` onto each record instead. That marked a
    touch consumed before the register write was durable, so any path that
    reverted the register lost the touch twice over: absent from the register,
    and flagged consumed in the log, therefore never retried. It happened for
    real on 2026-08-10, when a concurrent session left the shared repo
    mid-rebase, the commit failed, and the merge had already flipped the flags.
    Replaying costs one pass over a file that grows by a few lines a week, and
    it means a failure anywhere downstream, a failed commit, a reverted file, a
    clobbered deploy, heals itself on the next run instead of persisting.
    """
    path = args.log or INBOUND_LOG
    try:
        with open(path) as f:
            lines = [ln for ln in (l.strip() for l in f) if ln]
    except OSError:
        print(f"No inbound log at {path}, nothing to merge.")
        return 0

    records, malformed = [], 0
    for ln in lines:
        try:
            records.append(json.loads(ln))
        except json.JSONDecodeError:
            malformed += 1

    merged, skipped, unknown, cleared, unusable = 0, 0, [], [], []
    for rec in records:
        # No evidence id means `apply_touch` cannot dedupe, so replaying would
        # append the same touch every hour forever. Refuse it and say so.
        if not rec.get("evidence"):
            unusable.append(rec.get("nursery"))
            continue
        try:
            n = find(reg, rec["nursery"])
        except KeyError:
            # The register lost a nursery between logging and merging. Say so
            # and move on; the next run retries it for free.
            unknown.append(rec.get("nursery"))
            continue
        touch = {k: rec[k] for k in ("date", "direction", "channel", "by",
                                     "summary") if k in rec}
        touch["evidence"] = rec["evidence"]
        had = (n.get("open_action") or {}).get("what")
        if apply_touch(n, touch):
            merged += 1
            if had and not n.get("open_action"):
                cleared.append(f"{n['name']}: {had}")
        else:
            skipped += 1

    if args.dry_run:
        print(f"(dry run) would merge {merged}, skip {skipped} already present")
        for c in cleared:
            print(f"  would clear open action, {c}")
        if unknown:
            print(f"  unknown nursery keys, retried next run: {sorted(set(unknown))}")
        if unusable:
            print(f"  records with no evidence id, refused: {sorted(set(unusable))}")
        return 0

    if merged:
        save_register(reg)

    print(f"Merged {merged} touch(es), {skipped} already present.")
    for c in cleared:
        print(f"  Cleared open action, {c}")
    if malformed:
        print(f"  warning: {malformed} malformed line(s) skipped")
    if unknown:
        print(f"  warning: unknown nursery keys, retried next run: {sorted(set(unknown))}")
    if unusable:
        print(f"  warning: {len(unusable)} record(s) with no evidence id refused, "
              f"they cannot be deduped: {sorted(set(unusable))}")
    return 0


def cmd_set(reg, args):
    n = find(reg, args.key)
    if args.status:
        n["status"] = args.status
    for field in ("email", "phone", "contact_form", "contact_name",
                  "preferred_channel"):
        val = getattr(args, field.replace("-", "_"), None)
        if val:
            n[field] = val
    if args.note:
        n["notes"] = args.note
    if args.action:
        n["open_action"] = {"owner": args.action_owner, "what": args.action,
                            "since": date.today().isoformat()}
        if args.keep_open:
            n["open_action"]["keep_open"] = True
    elif args.keep_open and n.get("open_action"):
        n["open_action"]["keep_open"] = True
    if args.clear_action:
        n["open_action"] = None
    save_register(reg)
    print(f"Updated {n['name']}.")
    return 0


def validate(reg):
    """Return a list of problems. Empty list means valid."""
    problems = []
    keys = [n["key"] for n in reg["nurseries"]]
    if len(keys) != len(set(keys)):
        problems.append("duplicate nursery keys")
    for n in reg["nurseries"]:
        w = f"{n['key']}: "
        if n["status"] not in VALID_STATUSES:
            problems.append(w + f"invalid status {n['status']!r}")
        if not n.get("domain"):
            problems.append(w + "no domain, cannot be matched to referral data")
        elif n["domain"] != normalise_domain(n["domain"]):
            problems.append(w + f"domain {n['domain']!r} is not normalised")
        touches = n.get("touches", [])
        for t in touches:
            if t["direction"] not in VALID_DIRECTIONS:
                problems.append(w + f"invalid direction {t['direction']!r}")
            try:
                datetime.strptime(t["date"], "%Y-%m-%d")
            except (ValueError, KeyError):
                problems.append(w + f"unparseable touch date {t.get('date')!r}")
        if touches and n["status"] == "not_contacted":
            problems.append(w + "has touches but status is not_contacted")
        # `unreachable` is deliberately allowed both with and without touches.
        # Fruitopia has one (a bounce); Garden World has none, because there was
        # never an address to try. Both are "email is not a channel here".
        if not touches and n["status"] in {"contacted", "warm", "courtesy"}:
            problems.append(w + f"status {n['status']} but no recorded touches")
        act = n.get("open_action")
        if act and act.get("owner") not in {"dale", "benedict"}:
            problems.append(w + f"action owner {act.get('owner')!r} is not dale or benedict")
        if act and "keep_open" in act and not isinstance(act["keep_open"], bool):
            problems.append(w + f"keep_open {act['keep_open']!r} is not a bool")
        for path in unfollowable_paths(act.get("what", "") if act else ""):
            problems.append(w + f"action points at {path!r}, which does not exist")
    return problems


# Deliverables live in Linear, not git (CLAUDE.md), so an action telling
# somebody to open a repo file is usually telling them to open nothing. This
# fired for real: the Daleys action read "send the drafted reply
# (deliverables/daleys-reply-2026-08-27.txt)" and that file was never written,
# which stalled the top of Benedict's queue and blocked DAL-248 behind it.
#
# Scoped to open_action only. Historical touch evidence legitimately names
# artefacts since superseded or deleted, and failing on those would make
# `validate` noisy enough to get ignored.
ACTION_PATH_PREFIXES = ("deliverables/", "docs/", "state/", "data/", "tools/")


def unfollowable_paths(text, repo=REPO):
    """Repo-relative paths named by an action that are not on disk."""
    missing = []
    for token in str(text).replace("(", " ").replace(")", " ").split():
        token = token.strip(".,;:'\"`")
        if "/" not in token or not token.startswith(ACTION_PATH_PREFIXES):
            continue
        if not os.path.exists(os.path.join(repo, token)):
            missing.append(token)
    return missing


def cmd_validate(reg, args):
    problems = validate(reg)
    for p in problems:
        print(f"FAIL {p}")
    if not problems:
        print(f"OK: {len(reg['nurseries'])} nurseries, register valid.")
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("report")
    p.add_argument("--period", default="30d")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("due")
    p.set_defaults(fn=cmd_due)

    p = sub.add_parser("log")
    p.add_argument("key")
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--direction", choices=sorted(VALID_DIRECTIONS), required=True)
    p.add_argument("--channel", default="email")
    p.add_argument("--by", default="benedict")
    p.add_argument("--summary", required=True)
    p.add_argument("--evidence")
    p.add_argument("--clear-action", action="store_true")
    p.set_defaults(fn=cmd_log)

    p = sub.add_parser("set")
    p.add_argument("key")
    p.add_argument("--status", choices=sorted(VALID_STATUSES))
    p.add_argument("--email")
    p.add_argument("--phone")
    p.add_argument("--contact-form", dest="contact_form")
    p.add_argument("--contact-name", dest="contact_name")
    p.add_argument("--preferred-channel", dest="preferred_channel")
    p.add_argument("--note")
    p.add_argument("--action")
    p.add_argument("--action-owner", default="benedict",
                   choices=["benedict", "dale"])
    p.add_argument("--clear-action", action="store_true")
    p.add_argument("--keep-open", dest="keep_open", action="store_true",
                   help="an outbound touch must NOT auto-clear this action, "
                        "for actions an email cannot discharge")
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("merge-inbound",
                       help="fold BCC'd touches from the Resend inbound log "
                            "into the register (DAL-273)")
    p.add_argument("--log", help=f"inbound JSONL (default {INBOUND_LOG})")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_merge_inbound)

    p = sub.add_parser("validate")
    p.set_defaults(fn=cmd_validate)

    args = ap.parse_args(argv)
    return args.fn(load_register(), args)


if __name__ == "__main__":
    sys.exit(main())
