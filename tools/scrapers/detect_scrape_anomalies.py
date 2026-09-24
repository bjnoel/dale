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
  - most of the panel did not run at all (DAL-292, see PANEL_COVERAGE_FLOOR)

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

from stocklib.registry import NURSERIES
from stocklib.scrape_health import is_dormant, latest_by_nursery, read_records

STREAK_DAYS = 3

# PANEL COVERAGE (DAL-292). Every other rule in this file loops over the
# nurseries that WROTE a health record, so a nursery that never ran is not
# examined by any of them. Backtested over 99 nights of records, the six total
# outages of 2026-06-24..07-03 (DEC-324) each produced ONE OR TWO anomalies,
# because only 2 of 27 nurseries got far enough to report anything. A routine
# night produces one to three. So the worst nights in the dataset sent a
# SMALLER email than the ordinary ones, and six complete collapses read as
# quiet. An absence and a zero looked identical again (DEC-339).
#
# Coverage is measured against the nurseries we actually expected to run:
# registered, not dormant (DEC-330 already owns "shut, stop scraping nightly"),
# and seen at least once recently, so a newly added nursery grace-periods in
# rather than firing this on its first night.
#
# The floor is measured, not chosen. Over those 99 nights coverage is bimodal:
# every healthy night sits at 0.81 or above (0.81 is the June era when five
# nurseries had not been instrumented yet; from 2026-06-21 on it is 0.93+),
# and every outage night sits at 0.07. Anything from 0.60 to 0.80 scores
# identically: 6 of 6 outages caught, nothing else. 0.75 sits in the middle of
# that dead zone, one clear step below the worst healthy night, same discipline
# as DEC-323's subscriber thresholds.
PANEL_COVERAGE_FLOOR = 0.75
PANEL_RECENT_DAYS = 14

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
    "panel_coverage": "Most of the panel did not run",
}


def expected_panel(day, days, health_dir=None):
    """The nurseries that should have written a health record on `day`.

    Registered, not dormant, and seen at least once in the recent window. The
    recency test is what stops a newly added nursery (or a newly instrumented
    one) reading as a missing one. It looks back PANEL_RECENT_DAYS rather than
    a night or two so that a multi-night outage cannot quietly redefine the
    panel down to whoever survived it, which is the shape that let a closed
    store reset the dormancy backoff in DEC-330.
    """
    seen = set()
    for n in range(1, PANEL_RECENT_DAYS + 1):
        prior = (date.fromisoformat(day) - timedelta(days=n)).isoformat()
        seen.update(latest_by_nursery(read_records(prior, health_dir)))
    seen.update(latest_by_nursery(days[0] if days else []))
    return [
        n.key for n in NURSERIES
        if n.key in seen and not is_dormant(n.key, day, health_dir)
    ]


def detect_panel_coverage(day, days, health_dir=None):
    """A run-level anomaly: most of the panel never reported. None when fine."""
    expected = expected_panel(day, days, health_dir)
    if not expected:
        return None
    ran = latest_by_nursery(days[0] if days else [])
    present = [k for k in expected if k in ran]
    coverage = len(present) / len(expected)
    if coverage >= PANEL_COVERAGE_FLOOR:
        return None
    missing = sorted(set(expected) - set(present))
    return {
        "nursery": "(whole panel)",
        "type": "panel_coverage",
        "detail": f"only {len(present)} of {len(expected)} nurseries ran "
                  f"({coverage:.0%}); {len(missing)} never reported",
        "coverage": coverage,
        "missing": missing,
    }


def _is_restoration(nursery, today_count, per_day):
    """True when today's count returns to the level of the night before last.

    "Within the swing band of two nights ago" deliberately reuses
    COUNT_SWING_RATIO rather than picking a second number by eye: the thing
    being asked is whether today and the pre-dip day would have counted as the
    same level under this alarm's own definition of a level.
    """
    if len(per_day) < 3:
        return False
    before = per_day[2].get(nursery)
    if not before or not before.get("ok", False):
        return False
    prior2 = before.get("products", 0)
    if prior2 <= 0:
        return False
    back = today_count / prior2
    return 1 / COUNT_SWING_RATIO < back < COUNT_SWING_RATIO


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

        # Zero products is only news when the run SUCCEEDED and still came back
        # empty. A failed run has no products by definition, so firing this
        # alongside "failed" is a second row saying the same thing about the
        # same nursery. Backtested over 99 nights (DAL-292): all 36 of these
        # ever raised were on a nursery already reported failed the same night,
        # and it has never once fired independently. The rule is kept for the
        # ok-but-empty case it was written for, which stays uncovered otherwise.
        y = yesterday_latest.get(nursery)
        if not failed and rec.get("products", 0) == 0 and y and y.get("products", 0) > 0:
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
                # A swing that puts the count back where it was the night
                # BEFORE last is a recovery, not an event. Backtested over 99
                # nights (DAL-292), 8 of the 9 count swings ever raised were
                # four V-shaped pairs: ladybird 7022 -> 750 -> 7035,
                # garden-world 220 -> 25 -> 220, ladybird 7059 -> 1250 -> 7071,
                # fruitopia 638 -> 250 -> 638. Each truncated run was worth an
                # email; none of the four "it is back" rows was. The one
                # structural swing in the whole record, daleys 647 -> 1998 on
                # 2026-08-20, is not a restoration and survives this.
                swung = ratio >= COUNT_SWING_RATIO or ratio <= 1 / COUNT_SWING_RATIO
                if swung and not _is_restoration(nursery, today_count, per_day):
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


# Rows a human has already acted on. When a nursery's own site says it is shut
# and someone has written a dormant_note for it (stocklib.registry), "failed"
# and "failure streak" are the expected state, not news. Aus Nurseries went on
# holiday 2026-09-20 with a reopen date of 2026-10-20, and this alarm emailed
# about it every night: four identical mails in four days, with a month to go,
# under the same subject a real outage gets. An alarm that repeats a known fact
# nightly trains its reader to skip it.
#
# Deliberately NOT keyed on is_dormant() (five failed nights): that is the
# scraper's own inference, and a real outage nobody has looked at would go
# quiet on day six. Only a human-written note mutes. Every other anomaly type
# still fires for these nurseries, and a muted nursery is still named in the
# footer of any mail that does go out.
#
# And only a failure that CONTINUES a failure run is muted. A note can outlive
# its closure (Heritage's was still set on 2026-09-24 after a month of good
# scrapes), and the first failed night after a good one is always news.
EXPECTED_WHILE_CLOSED = {"failed", "failure_streak"}


def acknowledged_closures(yesterday_latest=None):
    """Nursery keys with a human-verified closure note whose previous run also
    failed. `yesterday_latest` is latest_by_nursery() for the day before."""
    from stocklib import registry
    note = getattr(registry, "dormant_note", None)
    if note is None:
        return set()
    yesterday_latest = yesterday_latest or {}
    return {n.key for n in registry.NURSERIES
            if note(n.key)
            and n.key in yesterday_latest
            and not yesterday_latest[n.key].get("ok", False)}


def split_acknowledged(anomalies, acknowledged):
    """(alertable, muted): muted rows are EXPECTED_WHILE_CLOSED rows for an
    acknowledged nursery."""
    alertable, muted = [], []
    for a in anomalies:
        if a.get("nursery") in acknowledged and a.get("type") in EXPECTED_WHILE_CLOSED:
            muted.append(a)
        else:
            alertable.append(a)
    return alertable, muted


def build_email(anomalies, today, muted=()):
    """Build (subject, html, text) for the alert email.

    A panel-coverage anomaly leads, in the subject line as well as the body.
    Counting rows cannot express severity here: the six worst nights on record
    raised one or two rows each because almost nothing ran, so "3 anomalies"
    and "2 anomalies" were the wrong way round (DAL-292).
    """
    panel = next((a for a in anomalies if a["type"] == "panel_coverage"), None)
    banner_html = banner_text = ""
    if panel:
        missing = ", ".join(panel["missing"][:12])
        if len(panel["missing"]) > 12:
            missing += f", +{len(panel['missing']) - 12} more"
        banner_html = (
            f'<p style="padding:10px;background:#c62828;color:#fff;font-weight:bold">'
            f'Panel outage: {panel["detail"]}.</p>'
            f'<p style="font-size:0.85em;color:#555">Did not report: {missing}</p>'
        )
        banner_text = (f"PANEL OUTAGE: {panel['detail']}.\n"
                       f"Did not report: {missing}\n\n")

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

    muted_names = sorted({a["nursery"] for a in muted})
    muted_html = muted_text = ""
    if muted_names:
        muted_html = (f'<p style="font-size:0.85em;color:#555">Known closures, not '
                      f'alerted: {", ".join(muted_names)}.</p>\n')
        muted_text = f"\n\nKnown closures, not alerted: {', '.join(muted_names)}."

    html = f"""<h2>Scrape Health Alert &mdash; {today}</h2>
{banner_html}
<p>{len(anomalies)} anomaly/ies in last night's scrape:</p>
<table style="font-family:monospace;font-size:13px;border-collapse:collapse;width:100%">
<tr style="border-bottom:2px solid #ddd;font-weight:bold">
<td style="padding:6px 10px">Nursery</td>
<td style="padding:6px 10px">Condition</td>
<td style="padding:6px 10px">Detail</td>
</tr>
{rows_html}
</table>
{muted_html}<p style="font-size:0.85em;color:#888;margin-top:16px">
Conditions: failed run, zero products where yesterday had stock, any 403/429,
{STREAK_DAYS}-day failure streak, data source change, product count swing beyond
{COUNT_SWING_RATIO:g}x. Health grid: treestock.com.au/admin.</p>"""

    text = (f"Scrape Health Alert -- {today}\n\n" + banner_text + "\n".join(rows_text)
            + muted_text)
    if panel:
        subject = (f"Scrape health: PANEL OUTAGE, {panel['coverage']:.0%} of "
                   f"nurseries ran -- {today}")
    else:
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
    panel = detect_panel_coverage(today.isoformat(), days, health_dir)
    if panel:
        anomalies.insert(0, panel)
    yesterday = latest_by_nursery(days[1]) if len(days) > 1 else {}
    anomalies, muted = split_acknowledged(anomalies, acknowledged_closures(yesterday))
    for a in muted:
        print(f"  {a['nursery']}: {a['type']} (known closure, not alerted)")
    if not anomalies:
        print(f"Scrape health: {len(latest_by_nursery(days[0]))} nurseries, no anomalies.")
        return 0

    for a in anomalies:
        print(f"  {a['nursery']}: {a['type']} - {a['detail']}")

    subject, html, text = build_email(anomalies, today.isoformat(), muted)

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
