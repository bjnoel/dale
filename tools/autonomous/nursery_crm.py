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
VALID_STATUSES = {"not_contacted", "contacted", "warm", "courtesy", "personal"}
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


def outbound_clicks(period="30d"):
    """Clicks per destination domain from Plausible.

    Paginates: the breakdown is by full URL and there are ~1,000 distinct
    product URLs per month, so a single unpaginated page silently undercounts.
    Returns {} if Plausible is unreachable, so a report still renders.
    """
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
        if not res or not res.get("results"):
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
    clicks = outbound_clicks(args.period)
    rows = []
    for n in reg["nurseries"]:
        c = clicks.get(n["domain"], {})
        rows.append((c.get("clicks", 0), c.get("visitors", 0), n))
    rows.sort(key=lambda r: (-r[0], r[2]["name"]))

    total = sum(r[0] for r in rows)
    uncontacted = sum(r[0] for r in rows if r[2]["status"] == "not_contacted")
    print(f"# Nursery relationship register ({args.period} referrals)\n")
    print(f"{len(rows)} nurseries. {total} outbound clicks sent in the last "
          f"{args.period}. {uncontacted} of those ({pct(uncontacted, total)}) went to "
          f"nurseries we have never spoken to.\n")
    print("| Nursery | Clicks | Buyers | Status | Last touch | Contact | Outstanding |")
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
    n.setdefault("touches", []).append(touch)
    n["touches"].sort(key=lambda t: t["date"])
    if args.direction == "in" and n["status"] == "contacted":
        n["status"] = "warm"
    elif args.direction == "out" and n["status"] == "not_contacted":
        n["status"] = "contacted"
    if args.clear_action:
        n["open_action"] = None
    save_register(reg)
    print(f"Logged {args.direction} touch for {n['name']} on {args.date}. "
          f"Status now {n['status']}.")
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
        if not touches and n["status"] in {"contacted", "warm", "courtesy"}:
            problems.append(w + f"status {n['status']} but no recorded touches")
        act = n.get("open_action")
        if act and act.get("owner") not in {"dale", "benedict"}:
            problems.append(w + f"action owner {act.get('owner')!r} is not dale or benedict")
    return problems


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
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("validate")
    p.set_defaults(fn=cmd_validate)

    args = ap.parse_args(argv)
    return args.fn(load_register(), args)


if __name__ == "__main__":
    sys.exit(main())
