#!/usr/bin/env python3
"""Detect scraper anomalies from the scrape-health records (DAL-193 P0.2).

Reads data/scraper-health/YYYY-MM-DD.jsonl (written by every scraper via
stocklib.scrape_health) and alerts Benedict when something needs a look:

  - a scraper run failed (ok=false)
  - a nursery returned 0 products where yesterday it had some
  - any 403/429 (we are being blocked or rate-limited)
  - a nursery has failed 3 days running
  - a nursery changed data SOURCE overnight (DEC-207 follow-up, see below)
  - a nursery's product count more than doubled or halved in one night

Runs in run-all-scrapers.sh after the smoke test. Idempotent: a send marker
prevents duplicate emails when the pipeline is re-run on the same day (same
pattern as detect_stock_surges.py).

Usage:
    python3 detect_scrape_anomalies.py [health_dir] [--dry-run] [--force]

--dry-run prints the email it would send without sending or marking sent.
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from stocklib.scrape_health import latest_by_nursery, read_records

STREAK_DAYS = 3

# A source change means the scraper feeding a nursery was swapped: Daleys went
# from the HTML plant_list scraper (647 products) to a CSV supplier feed (1,998)
# on 2026-08-20, out of band, three hours after the nightly had already written
# a snapshot and sent the day's digest and alerts against the old numbers.
# Nothing noticed. The swap also tripled the catalogue and re-minted variety
# pages, so it is worth an email on its own.
#
# COUNT_SWING_RATIO is deliberately blunt (a doubling or a halving) rather than
# matched to detect_stock_surges.py's +/-20%. That job already owns ordinary
# stock movement and emails on it; a second alarm at the same sensitivity would
# double-send on every seasonal restock, which is exactly the noise that trains
# an alarm to be ignored. This one is for structural events: a source swap, a
# truncated run, a catalogue that vanished. The Daleys swap was +209%.
COUNT_SWING_RATIO = 2.0

# A nursery can be scraped perfectly and still stop yielding prices. PlantNet
# reported price "0" on 79 of its 110 SKUs and nothing anywhere noticed: the
# snapshot validated (0.0 is a non-negative price), the product count was
# normal, and the only symptom was a blank cell on the homepage that Benedict
# happened to see. So the share of products carrying a usable price is now
# recorded per run and a collapse in it is an anomaly.
#
# HONEST LIMIT: this is a day-over-day rule, so it catches a nursery that LOSES
# its prices. It would NOT have caught PlantNet, which has been mostly priceless
# since the day it was added. There is no delta to see in a birth defect. What
# closes that gap is the priced figure being visible per nursery in the health
# grid, not another alarm: an absolute threshold would fire nightly and forever
# for a nursery that is legitimately POA, which is how an alarm gets ignored.
PRICED_SHARE_DROP = 0.5
MIN_PRODUCTS_FOR_PRICED_CHECK = 20

SENDS_LOG_FILE = Path(os.environ.get("DALE_DATA_DIR", "/opt/dale/data")) / "scrape_anomaly_sends.json"

from stocklib.mailer import load_sends_log, save_sends_log

CONDITION_LABELS = {
    "failed": "Scraper failed",
    "zero_products": "Zero products",
    "blocked": "Blocked (403/429)",
    "failure_streak": f"Failed {STREAK_DAYS} days running",
    "source_change": "Data source changed",
    "count_swing": "Product count swing",
    "priced_collapse": "Prices stopped being read",
}


def detect_anomalies(days):
    """Find anomalies in health records. `days` is a list of per-day record
    lists, newest first: days[0] = today, days[1] = yesterday, ... At least
    STREAK_DAYS entries are needed for streak detection; missing/short days
    are tolerated (no records = no streak evidence)."""
    per_day = [latest_by_nursery(d) for d in days]
    today_latest = per_day[0] if per_day else {}
    yesterday_latest = per_day[1] if len(per_day) > 1 else {}

    anomalies = []
    for nursery in sorted(today_latest):
        rec = today_latest[nursery]
        failed = not rec.get("ok", False)

        if failed:
            anomalies.append({
                "nursery": nursery,
                "type": "failed",
                "detail": rec.get("error") or "no error message recorded",
            })

        y = yesterday_latest.get(nursery)
        if rec.get("products", 0) == 0 and y and y.get("products", 0) > 0:
            anomalies.append({
                "nursery": nursery,
                "type": "zero_products",
                "detail": f"0 products today, {y['products']} yesterday",
            })

        n403 = rec.get("http_403", 0)
        n429 = rec.get("http_429", 0)
        if n403 or n429:
            anomalies.append({
                "nursery": nursery,
                "type": "blocked",
                "detail": f"{n403}x HTTP 403, {n429}x HTTP 429",
            })

        # Source swap and structural count swings. Both compare against
        # yesterday's LAST record for the nursery, and both are skipped when
        # today's run failed: a failed run already has its own anomaly and its
        # product count is not evidence of anything.
        if y and not failed:
            today_source = rec.get("source")
            prior_source = y.get("source")
            if today_source and prior_source and today_source != prior_source:
                anomalies.append({
                    "nursery": nursery,
                    "type": "source_change",
                    "detail": f"{prior_source} -> {today_source} "
                              f"({y.get('products', 0)} -> {rec.get('products', 0)} products)",
                })

            # Priced share collapse. Guarded on both days carrying the field
            # (it is optional, and old records predate it) and on a catalogue
            # big enough for a share to mean anything.
            t_n, y_n = rec.get("products", 0), y.get("products", 0)
            t_priced, y_priced = rec.get("priced"), y.get("priced")
            if (t_priced is not None and y_priced is not None
                    and t_n >= MIN_PRODUCTS_FOR_PRICED_CHECK
                    and y_n >= MIN_PRODUCTS_FOR_PRICED_CHECK):
                t_share, y_share = t_priced / t_n, y_priced / y_n
                if y_share > 0 and t_share <= y_share * PRICED_SHARE_DROP:
                    anomalies.append({
                        "nursery": nursery,
                        "type": "priced_collapse",
                        "detail": f"{y_share:.0%} -> {t_share:.0%} of products priced "
                                  f"({y_priced}/{y_n} -> {t_priced}/{t_n})",
                    })

            prior_count = y.get("products", 0)
            today_count = rec.get("products", 0)
            if prior_count > 0 and today_count > 0:
                ratio = today_count / prior_count
                if ratio >= COUNT_SWING_RATIO or ratio <= 1 / COUNT_SWING_RATIO:
                    anomalies.append({
                        "nursery": nursery,
                        "type": "count_swing",
                        "detail": f"{prior_count} -> {today_count} products "
                                  f"({(ratio - 1) * 100:+.0f}%)",
                    })

        if failed and len(per_day) >= STREAK_DAYS:
            prior = [per_day[n].get(nursery) for n in range(1, STREAK_DAYS)]
            if all(p is not None and not p.get("ok", False) for p in prior):
                anomalies.append({
                    "nursery": nursery,
                    "type": "failure_streak",
                    "detail": f"ok=false for the last {STREAK_DAYS} days",
                })

    return anomalies


def build_email(anomalies, today):
    """Build (subject, html, text) for the alert email."""
    rows_html = ""
    rows_text = []
    for a in anomalies:
        label = CONDITION_LABELS.get(a["type"], a["type"])
        rows_html += (
            f'<tr style="border-bottom:1px solid #eee">'
            f'<td style="padding:6px 10px">{a["nursery"]}</td>'
            f'<td style="padding:6px 10px;color:#c62828;font-weight:bold">{label}</td>'
            f'<td style="padding:6px 10px">{a["detail"]}</td>'
            f'</tr>'
        )
        rows_text.append(f"  {a['nursery']}: {label} - {a['detail']}")

    html = f"""<h2>Scrape Health Alert &mdash; {today}</h2>
<p>{len(anomalies)} anomaly/ies in last night's scrape:</p>
<table style="font-family:monospace;font-size:13px;border-collapse:collapse;width:100%">
<tr style="border-bottom:2px solid #ddd;font-weight:bold">
<td style="padding:6px 10px">Nursery</td>
<td style="padding:6px 10px">Condition</td>
<td style="padding:6px 10px">Detail</td>
</tr>
{rows_html}
</table>
<p style="font-size:0.85em;color:#888;margin-top:16px">
Conditions: failed run, zero products where yesterday had stock, any 403/429,
{STREAK_DAYS}-day failure streak, data source change, product count swing beyond
{COUNT_SWING_RATIO:g}x. Health grid: treestock.com.au/admin.</p>"""

    text = f"Scrape Health Alert -- {today}\n\n" + "\n".join(rows_text)
    subject = f"Scrape health: {len(anomalies)} anomalies -- {today}"
    return subject, html, text


def send_alert(subject, html, text):
    sys.path.insert(0, str(Path(__file__).parent.parent / "autonomous"))
    from notify import send_email
    send_email(subject, html, text)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    positional = [a for a in argv if not a.startswith("--")]
    health_dir = positional[0] if positional else None
    dry_run = "--dry-run" in argv
    force = "--force" in argv

    today = date.today()
    days = [
        read_records((today - timedelta(days=n)).isoformat(), health_dir)
        for n in range(STREAK_DAYS)
    ]

    if not days[0]:
        print(f"Scrape health: no records for {today.isoformat()}, nothing to check.")
        return 0

    anomalies = detect_anomalies(days)
    if not anomalies:
        print(f"Scrape health: {len(latest_by_nursery(days[0]))} nurseries, no anomalies.")
        return 0

    for a in anomalies:
        print(f"  {a['nursery']}: {a['type']} - {a['detail']}")

    subject, html, text = build_email(anomalies, today.isoformat())

    if dry_run:
        print(f"\n[DRY RUN] Would send:\nSubject: {subject}\n\n{text}")
        return 0

    sends_log = load_sends_log(SENDS_LOG_FILE)
    if sends_log.get("last_sent") == today.isoformat() and not force:
        print(f"Scrape anomaly alert already sent today ({today.isoformat()}), skipping.")
        return 0

    send_alert(subject, html, text)
    sends_log["last_sent"] = today.isoformat()
    save_sends_log(SENDS_LOG_FILE, sends_log)
    print(f"Scrape anomaly alert sent: {len(anomalies)} anomalies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
