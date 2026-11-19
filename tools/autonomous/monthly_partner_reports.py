#!/usr/bin/env python3
"""
Build last month's partner report for every nursery we have an established
relationship with, then email Benedict one list of links to send by hand.

Runs from cron on the first Tuesday of the month, 06:00 Perth (Monday 22:00
UTC; cron cannot say "first Tuesday", so the script checks the date itself).
Nothing is sent to a nursery: Benedict sends each link through that nursery's
own channel (WhatsApp, Instagram, email), as he did for Sept and Oct 2026.

Who gets one: register status warm (replied), courtesy (replied, not a
prospect) or personal (Benedict knows them). Never contacted, contacted with
no reply, cold (decided not to chase) and unreachable are left out. A nursery
we don't scrape (no stock data) can't have a report and is skipped.

What they get: the full report if they already pay us (stocklib.utm
AFFILIATES), otherwise --traffic-only, the split used for October 2026.

A rerun for the same month rebuilds into the same file, so a link Benedict has
already sent never changes or dies.

Usage:
    python3 monthly_partner_reports.py                  # cron: date-guarded
    python3 monthly_partner_reports.py --force --dry-run
    python3 monthly_partner_reports.py --force --month 2026-10
"""
import argparse
import html
import json
import secrets
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PERTH = ZoneInfo("Australia/Perth")
CONTACTS = Path("/opt/dale/data/nursery-contacts.json")
STOCK_DIR = Path("/opt/dale/data/nursery-stock")
SCRAPERS = Path("/opt/dale/scrapers")
REPORTS_DIR = Path("/opt/dale/dashboard/reports")
BASE_URL = "https://treestock.com.au/reports/"

ESTABLISHED = ("warm", "courtesy", "personal")


def is_first_tuesday(d: date) -> bool:
    return d.weekday() == 1 and d.day <= 7


def previous_month(d: date) -> str:
    last = d.replace(day=1) - timedelta(days=1)
    return f"{last.year}-{last.month:02d}"


def select_nurseries(register: dict, has_stock) -> tuple[list[dict], list[tuple[dict, str]]]:
    """(chosen, skipped-with-reason). Skipped only lists established nurseries
    we could not build for, so the email explains a gap Benedict would notice."""
    chosen, skipped = [], []
    for n in register["nurseries"]:
        if n.get("status") not in ESTABLISHED:
            continue
        if not has_stock(n["key"]):
            skipped.append((n, "no stock data (not scraped)"))
            continue
        chosen.append(n)
    return chosen, skipped


def report_path(reports_dir: Path, key: str, month: str) -> Path:
    """Reuse an existing report for this nursery and month, so the link is stable."""
    existing = sorted(reports_dir.glob(f"{key}-{month}-*.html"))
    if existing:
        return existing[0]
    return reports_dir / f"{key}-{month}-{secrets.token_hex(5)}.html"


def contact_line(n: dict) -> str:
    name = n.get("contact_name") or "no contact name on file"
    channel = n.get("preferred_channel") or "no channel on file"
    detail = n.get("email") or n.get("phone") or n.get("contact_form") or ""
    return f"{name}, via {channel}" + (f" ({detail})" if detail and channel == "email" else "")


def build_one(n: dict, month: str, out: Path) -> dict:
    cmd = [sys.executable, str(SCRAPERS / "build_partner_report.py"), n["key"],
           "--month", month, "--out", str(out)]
    if n.get("contact_name"):
        cmd += ["--contact", n["contact_name"].split()[0]]
    is_partner = _is_partner(n["key"])
    if not is_partner:
        cmd.append("--traffic-only")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=SCRAPERS)
    if res.returncode != 0:
        tail = (res.stderr or res.stdout).strip().splitlines()
        raise RuntimeError(tail[-1] if tail else f"exit {res.returncode}")
    summary = json.loads(res.stdout)
    return {"people": summary["this"]["people"], "prev": summary["prev"]["people"],
            "full": is_partner}


def _is_partner(key: str) -> bool:
    sys.path.insert(0, str(SCRAPERS))
    from stocklib.utm import AFFILIATES
    return any(a.nursery_key == key for a in AFFILIATES.values())


def render_email(month_label: str, rows: list[dict], failed: list[tuple[dict, str]],
                 skipped: list[tuple[dict, str]]) -> tuple[str, str]:
    e = html.escape
    lines = [f"<p>{len(rows)} nursery reports for {e(month_label)} are ready. "
             "Nothing has been sent to the nurseries.</p>", "<ul>"]
    text = [f"{len(rows)} nursery reports for {month_label} are ready. "
            "Nothing has been sent to the nurseries.", ""]
    for r in rows:
        n = r["nursery"]
        change = f"{r['people']} people (was {r['prev']})"
        kind = "full report" if r["full"] else "traffic only"
        lines.append(f"<li><b>{e(n['name'])}</b>: {e(contact_line(n))}<br>"
                     f"{e(change)}, {kind}<br><a href=\"{e(r['url'])}\">{e(r['url'])}</a></li>")
        text += [f"{n['name']}: {contact_line(n)}", f"  {change}, {kind}", f"  {r['url']}", ""]
    lines.append("</ul>")
    if failed:
        lines.append("<p><b>Failed to build:</b></p><ul>")
        lines += [f"<li>{e(n['name'])}: {e(why)}</li>" for n, why in failed]
        lines.append("</ul>")
        text += ["Failed to build:"] + [f"  {n['name']}: {why}" for n, why in failed] + [""]
    if skipped:
        lines.append("<p>Skipped:</p><ul>")
        lines += [f"<li>{e(n['name'])}: {e(why)}</li>" for n, why in skipped]
        lines.append("</ul>")
        text += ["Skipped:"] + [f"  {n['name']}: {why}" for n, why in skipped]
    return "\n".join(lines), "\n".join(text)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--month", help="YYYY-MM (default: last month)")
    ap.add_argument("--force", action="store_true", help="ignore the first-Tuesday guard")
    ap.add_argument("--dry-run", action="store_true", help="list who would get one, build nothing")
    args = ap.parse_args(argv)

    today = datetime.now(PERTH).date()
    if not (args.force or is_first_tuesday(today)):
        return 0
    month = args.month or previous_month(today)
    month_label = datetime.strptime(month, "%Y-%m").strftime("%B %Y")

    register = json.loads(CONTACTS.read_text())
    chosen, skipped = select_nurseries(register, lambda k: (STOCK_DIR / k).is_dir())
    if args.dry_run:
        for n in chosen:
            print(f"{n['key']}: {contact_line(n)} -> {report_path(REPORTS_DIR, n['key'], month)}")
        for n, why in skipped:
            print(f"skip {n['key']}: {why}")
        return 0

    rows, failed = [], []
    for n in chosen:
        out = report_path(REPORTS_DIR, n["key"], month)
        try:
            r = build_one(n, month, out)
        except Exception as exc:  # one nursery's failure must not cost the rest
            failed.append((n, str(exc)[:200]))
            continue
        rows.append({"nursery": n, "url": BASE_URL + out.name, **r})
        print(f"built {out.name}", flush=True)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from notify import send_email
    body_html, body_text = render_email(month_label, rows, failed, skipped)
    send_email(f"Nursery reports for {month_label} ready to send ({len(rows)})",
               body_html, body_text)
    print(f"emailed {len(rows)} links, {len(failed)} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
