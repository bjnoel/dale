#!/usr/bin/env python3
"""Apple's own install and purchase counts, as a nightly series.

`appstore_sources.py` reads one report out of the ongoing analytics request:
App Store Discovery and Engagement, which counts impressions, page views and
taps. It cannot see a download and it cannot see a sale. This module reads the
two COMMERCE reports that can:

  r3   App Downloads Standard        -> first-time downloads, redownloads, updates
  r12  App Store Purchases Standard  -> purchases, proceeds, sales, paying users

Why Apple's number and not one we already have
----------------------------------------------

RevenueCat is not an install count. It opens a customer record per SDK init,
and DEC-321 measured the consequence against Apple: 51 lifetime first-time iOS
downloads where RevenueCat held 134 iOS customers, a 2.5x inflation (Android
~6x). Every install-denominated rate we quote -- conversion, cost per install,
the AU/US share -- was computed on the inflated number. r3 is the only exact
one, and until this module existed nothing read it, so Apple's count was frozen
at the 2026-08-20 hand pull that produced DEC-321.

r12 is a third independent reading of revenue, alongside RevenueCat (the money
source of truth, DEC-260) and PostHog (which undercounts, DEC-282, because a
completed sale can be recorded as a dismissal). Having three is what caught
both of those.

What this deliberately does NOT do
----------------------------------

1. **It does not read an empty instance list as zero.** `list_instances`
   raises NotReady, and this module prints it. That matters more here than for
   engagement: App Store Purchases has NO instances at all on the ongoing
   request today, and "no instances" and "no sales" would render identically.
   A month of silence must not be reported as a month of measured zero.

2. **It does not sum overlapping instances.** Apple's DAILY instances are a
   ROLLING WINDOW (DEC-332). For r3 the window is even shorter than the
   engagement report's three days: each instance carries exactly the TWO days
   ending the day before its processing date, measured across all nine
   instances Apple held on 2026-09-17. Miss two nights and a day falls out of
   the window permanently. So every instance is read oldest-first and a newer
   one REPLACES an older one for any day the two share.

3. **It does not treat the ONGOING request as the whole history.** The ongoing
   window starts 2026-09-06. Everything before that came out of the frozen
   ONE_TIME_SNAPSHOT request, backfilled once with `--request-id`. The gap
   between them (2026-08-21..2026-09-05) is lost the same way the discovery
   series lost 2026-08-21..09-04, and is printed as missing rather than
   averaged over.

4. **It does not aggregate away territory or download type.** Those are the two
   dimensions every question we have ever asked of this data needs (AU vs US
   conversion, first-time vs update). Device, app version and platform version
   ARE aggregated away: nothing reads them and they multiply the row count.

Verification
------------

The snapshot backfill reproduces DEC-321 exactly, which is the check that says
the reader is right rather than merely plausible:

  51 first-time downloads · 4 redownloads · 3 purchases · US$77.30 sales

Usage
-----

  python3 appstore_downloads.py                  # pull both, append, render
  python3 appstore_downloads.py --report downloads --dry-run
  python3 appstore_downloads.py --request-id <snapshot-uuid> --pulled-at ...
  python3 appstore_downloads.py --json
"""

import argparse
import datetime
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import appstore_sources as src  # noqa: E402 - sibling module, path set above

COMMERCE_CATEGORY = "COMMERCE"

DOWNLOADS_REPORT = "App Downloads Standard"
PURCHASES_REPORT = "App Store Purchases Standard"

DOWNLOADS_CSV = "treesmith-appstore-downloads.csv"
PURCHASES_CSV = "treesmith-appstore-purchases.csv"

# Apple's Download Type values. An unrecognised one is carried into the series
# as-is and named in the render, never folded into a total it does not belong
# to. `Redownload` and `Restore` are different things and both have been seen.
DOWNLOAD_FIRST_TIME = "First-time download"
DOWNLOAD_REDOWNLOAD = "Redownload"
DOWNLOAD_RESTORE = "Restore"
DOWNLOAD_AUTO_UPDATE = "Auto-update"
DOWNLOAD_MANUAL_UPDATE = "Manual update"
KNOWN_DOWNLOAD_TYPES = (
    DOWNLOAD_FIRST_TIME,
    DOWNLOAD_REDOWNLOAD,
    DOWNLOAD_RESTORE,
    DOWNLOAD_AUTO_UPDATE,
    DOWNLOAD_MANUAL_UPDATE,
)

# The only download types that mean "a new person now has the app". An update
# is the same person; a redownload or restore is the same person returning.
# Quoting "downloads" without this distinction is how a 93-update month reads
# as growth.
NEW_USER_TYPES = (DOWNLOAD_FIRST_TIME,)

DOWNLOAD_COLUMNS = [
    "pulled_at",
    "date",
    "download_type",
    "territory",
    "source_type",
    "page_type",
    "counts",
    "complete",
    "report",
]
DOWNLOAD_SERIES = src.SeriesSchema(
    columns=DOWNLOAD_COLUMNS,
    key_columns=("date", "download_type", "territory", "source_type", "page_type"),
    metric_columns=("counts",),
    int_columns=("counts",),
)

PURCHASE_COLUMNS = [
    "pulled_at",
    "date",
    "purchase_type",
    "content_name",
    "territory",
    "source_type",
    "page_type",
    "purchases",
    "paying_users",
    "proceeds_usd",
    "sales_usd",
    "complete",
    "report",
]
PURCHASE_SERIES = src.SeriesSchema(
    columns=PURCHASE_COLUMNS,
    key_columns=("date", "purchase_type", "content_name", "territory",
                 "source_type", "page_type"),
    metric_columns=("purchases", "paying_users", "proceeds_usd", "sales_usd"),
    int_columns=("purchases", "paying_users"),
    float_columns=("proceeds_usd", "sales_usd"),
)

# Apple's headers for the two reports, from the live files (2026-09-17).
DL_REQUIRED = ("Date", "Download Type", "Source Type", "Page Type",
               "Territory", "Counts")
PU_REQUIRED = ("Date", "Purchase Type", "Content Name", "Source Type",
               "Page Type", "Territory", "Purchases", "Proceeds in USD",
               "Sales in USD", "Paying Users")


# ── Parsing (pure) ───────────────────────────────────────────────────────────

def _cell(cells, columns, name):
    return cells[columns[name]].strip()


def _to_float(cell):
    text = (cell or "").strip().replace(",", "").replace("$", "")
    if not text or text == "-":
        return 0.0
    return float(text)


def aggregate_downloads(columns, rows):
    """Sum a parsed r3 segment to {(date, type, territory, source, page): counts}.

    Device, app version and platform version are summed away here rather than
    stored. Returns `(totals, anomalies)`; an unrecognised Download Type is
    counted, kept, and named, because a download type we have never seen is
    exactly the thing that would make a total wrong.
    """
    totals = {}
    unknown_types = {}
    unknown_sources = {}
    for cells in rows:
        date = _cell(cells, columns, "Date")
        dtype = _cell(cells, columns, "Download Type") or "Unavailable"
        territory = _cell(cells, columns, "Territory") or "Unavailable"
        source = _cell(cells, columns, "Source Type") or "Unavailable"
        page = _cell(cells, columns, "Page Type") or "No page"
        count = src._to_int(_cell(cells, columns, "Counts"))

        if dtype not in KNOWN_DOWNLOAD_TYPES:
            unknown_types[dtype] = unknown_types.get(dtype, 0) + 1
        if source not in src.KNOWN_SOURCES:
            unknown_sources[source] = unknown_sources.get(source, 0) + 1

        key = (date, dtype, territory, source, page)
        totals[key] = totals.get(key, 0) + count
    return totals, {"unknown_download_types": unknown_types,
                    "unknown_sources": unknown_sources}


def aggregate_purchases(columns, rows):
    """Sum a parsed r12 segment, keyed by day, product and territory."""
    totals = {}
    unknown_sources = {}
    for cells in rows:
        date = _cell(cells, columns, "Date")
        ptype = _cell(cells, columns, "Purchase Type") or "Unavailable"
        content = _cell(cells, columns, "Content Name")
        territory = _cell(cells, columns, "Territory") or "Unavailable"
        source = _cell(cells, columns, "Source Type") or "Unavailable"
        page = _cell(cells, columns, "Page Type") or "No page"

        if source not in src.KNOWN_SOURCES:
            unknown_sources[source] = unknown_sources.get(source, 0) + 1

        key = (date, ptype, content, territory, source, page)
        bucket = totals.setdefault(key, {"purchases": 0, "paying_users": 0,
                                         "proceeds_usd": 0.0, "sales_usd": 0.0})
        bucket["purchases"] += src._to_int(_cell(cells, columns, "Purchases"))
        bucket["paying_users"] += src._to_int(_cell(cells, columns, "Paying Users"))
        bucket["proceeds_usd"] += _to_float(_cell(cells, columns, "Proceeds in USD"))
        bucket["sales_usd"] += _to_float(_cell(cells, columns, "Sales in USD"))
    return totals, {"unknown_sources": unknown_sources}


def _cutoff(stamp, tail, final):
    """The newest date to mark complete.

    Normally Apple's three-day rule. `final` overrides it to "everything in
    this pull", and is ONLY correct for the frozen ONE_TIME_SNAPSHOT request:
    that request stopped producing instances on 2026-08-20, so its last three
    days are provisional by Apple's rule and will never be restated, because
    the ongoing request's rolling window does not reach back that far. Leaving
    them incomplete would drop downloads Apple did measure, from every total,
    permanently. Taking them risks a small undercount instead, which is the
    lesser error and is recorded on the ticket rather than hidden.
    """
    if final:
        return datetime.date.max
    return src.last_complete_date(stamp, tail)


def download_records(totals, pulled_at, tail=src.INCOMPLETE_TAIL_DAYS,
                     report=DOWNLOADS_REPORT, final=False):
    stamp = src.normalise_pulled_at(pulled_at)
    cutoff = _cutoff(stamp, tail, final)
    out = []
    for (date, dtype, territory, source, page), count in totals.items():
        out.append({
            "pulled_at": stamp, "date": date, "download_type": dtype,
            "territory": territory, "source_type": source, "page_type": page,
            "counts": count,
            "complete": src._as_date(date) <= cutoff,
            "report": report,
        })
    out.sort(key=lambda r: (r["date"], r["download_type"], r["territory"],
                            r["source_type"], r["page_type"]))
    return out


def purchase_records(totals, pulled_at, tail=src.INCOMPLETE_TAIL_DAYS,
                     report=PURCHASES_REPORT, final=False):
    stamp = src.normalise_pulled_at(pulled_at)
    cutoff = _cutoff(stamp, tail, final)
    out = []
    for (date, ptype, content, territory, source, page), metrics in totals.items():
        record = {
            "pulled_at": stamp, "date": date, "purchase_type": ptype,
            "content_name": content, "territory": territory,
            "source_type": source, "page_type": page,
            "complete": src._as_date(date) <= cutoff,
            "report": report,
        }
        record.update(metrics)
        out.append(record)
    out.sort(key=lambda r: (r["date"], r["content_name"], r["territory"]))
    return out


# ── Reading (network) ────────────────────────────────────────────────────────

def pull_report(config, report_name, required, aggregator, token=None,
                getter=src.api_get, fetcher=src.fetch_segment, request_id=None):
    """Fetch every instance Apple still holds of one COMMERCE report.

    The instance merge is the DEC-332 rule and is not optional: oldest first,
    a newer instance replacing an older one on any shared day. Replace, not
    sum. r3's rolling window is two days wide, so an instance overlaps its
    predecessor on one day and summing would double it.
    """
    if token is None:
        token = src.mint_token(config["ASC_KEY_ID"], config["ASC_ISSUER_ID"],
                               config["ASC_PRIVATE_KEY_PATH"])
    request_id = request_id or config["ASC_REQUEST_ID"]
    report_id = src.find_report(token, request_id, report_name, getter=getter,
                                category=COMMERCE_CATEGORY)
    instances = src.list_instances(token, report_id, config["ASC_GRANULARITY"],
                                   getter=getter)

    totals = {}
    anomalies = {}
    rows_read = segments_read = instances_read = 0
    newest = None
    for instance in sorted(instances, key=lambda i: i["processing_date"] or ""):
        urls = src.segment_urls(token, instance["id"], getter=getter)
        if not urls:
            continue
        instance_totals = {}
        for url in urls:
            columns, rows = src.parse_tsv(fetcher(url), required=required,
                                          optional=())
            rows_read += len(rows)
            part, part_anomalies = aggregator(columns, rows)
            for key, value in part.items():
                held = instance_totals.get(key)
                if held is None:
                    instance_totals[key] = value
                elif isinstance(value, dict):
                    for name, amount in value.items():
                        held[name] += amount
                else:
                    instance_totals[key] = held + value
            for kind, counts in part_anomalies.items():
                target = anomalies.setdefault(kind, {})
                for name, count in counts.items():
                    target[name] = target.get(name, 0) + count
        segments_read += len(urls)
        instances_read += 1
        newest = instance
        covered = {key[0] for key in instance_totals}
        totals = {k: v for k, v in totals.items() if k[0] not in covered}
        totals.update(instance_totals)

    if not instances_read:
        raise src.NotReady(
            f"none of the {len(instances)} instance(s) of {report_name} have "
            f"segments yet (newest processing date "
            f"{instances[0]['processing_date']}). Not zero."
        )

    meta = {
        "report_id": report_id, "report_name": report_name,
        "granularity": config["ASC_GRANULARITY"],
        "request_id": request_id,
        "processing_date": newest["processing_date"],
        "instances_available": len(instances), "instances_read": instances_read,
        "segments": segments_read, "rows_read": rows_read,
    }
    return totals, anomalies, meta


# ── Summarising (pure) ───────────────────────────────────────────────────────

def series_file(name, environ=None):
    """Same placement rule as the engagement series: /opt/dale/data on the box."""
    environ = os.environ if environ is None else environ
    server = os.path.join(environ.get("DALE_DATA", "/opt/dale/data"), name)
    local = os.path.join(src.REPO_ROOT, "data", name)
    for candidate in (server, local):
        if os.path.exists(candidate):
            return candidate
    return server if os.path.isdir(os.path.dirname(server)) else local


def complete_only(records, schema):
    return [r for r in src.latest_view(records, schema).values() if r["complete"]]


def no_row_days(dates):
    """Calendar days between the first and last we hold that carry no row.

    NOT the same as missing days, and the difference is the whole point. At 1.8
    first-time downloads a day, a day with none is completely ordinary and
    produces no row at all, so 47 of the 66 days in the snapshot backfill have
    no row while every one of them was observed. Calling those "missing" would
    manufacture a data-loss scare out of a quiet app.

    A no-row day is only unobserved if we also failed to pull while it was
    inside Apple's rolling window. That is what `pull_gaps` measures, and the
    two are reported separately rather than conflated.
    """
    if not dates:
        return []
    days = sorted({src._as_date(d) for d in dates})
    held = set(days)
    span = (days[-1] - days[0]).days + 1
    return [(days[0] + datetime.timedelta(days=i)).isoformat()
            for i in range(span)
            if (days[0] + datetime.timedelta(days=i)) not in held]


# Apple's r3 DAILY instance carries the two days ending the day before its
# processing date, measured across all nine instances held on 2026-09-17. So a
# pull sees the previous two days and no more: go three days without pulling
# and a day leaves the window with nobody having read it, exactly the way the
# discovery series lost 2026-08-21..09-04 (DEC-332).
ROLLING_WINDOW_DAYS = 2


def pull_gaps(records, window=ROLLING_WINDOW_DAYS):
    """Stretches where we did not pull for longer than the window survives.

    Returned as (after, before) pairs of pull dates. Any no-row day inside such
    a stretch is genuinely unobserved and is NOT a measured zero.
    """
    pulls = sorted({src._as_date(r["pulled_at"]) for r in records})
    gaps = []
    for earlier, later in zip(pulls, pulls[1:]):
        if (later - earlier).days > window:
            gaps.append((earlier.isoformat(), later.isoformat()))
    return gaps


def summarise_downloads(records, since=None):
    """Totals by download type, territory and source over the complete rows."""
    gaps = pull_gaps(records)
    rows = complete_only(records, DOWNLOAD_SERIES)
    if since:
        rows = [r for r in rows if r["date"] >= since]
    by_type, by_territory, by_source = {}, {}, {}
    dates = set()
    for record in rows:
        count = record["counts"]
        dates.add(record["date"])
        by_type[record["download_type"]] = by_type.get(record["download_type"], 0) + count
        if record["download_type"] in NEW_USER_TYPES:
            by_territory[record["territory"]] = by_territory.get(record["territory"], 0) + count
            by_source[record["source_type"]] = by_source.get(record["source_type"], 0) + count
    days = sorted(dates)
    first_time = sum(by_type.get(t, 0) for t in NEW_USER_TYPES)
    return {
        "days": days,
        "day_count": len(days),
        "no_row_days": no_row_days(days),
        "pull_gaps": gaps,
        "first_time_downloads": first_time,
        "redownloads": by_type.get(DOWNLOAD_REDOWNLOAD, 0),
        "restores": by_type.get(DOWNLOAD_RESTORE, 0),
        "updates": (by_type.get(DOWNLOAD_AUTO_UPDATE, 0)
                    + by_type.get(DOWNLOAD_MANUAL_UPDATE, 0)),
        "by_type": by_type,
        "first_time_by_territory": by_territory,
        "first_time_by_source": by_source,
        "per_day": round(first_time / len(days), 2) if days else None,
    }


def summarise_purchases(records, since=None):
    rows = complete_only(records, PURCHASE_SERIES)
    if since:
        rows = [r for r in rows if r["date"] >= since]
    dates = set()
    purchases = paying = 0
    proceeds = sales = 0.0
    by_territory, by_content = {}, {}
    for record in rows:
        dates.add(record["date"])
        purchases += record["purchases"]
        paying += record["paying_users"]
        proceeds += record["proceeds_usd"]
        sales += record["sales_usd"]
        by_territory[record["territory"]] = by_territory.get(record["territory"], 0) + record["purchases"]
        by_content[record["content_name"]] = by_content.get(record["content_name"], 0) + record["purchases"]
    return {
        "days_with_a_sale": sorted(dates),
        "purchases": purchases,
        "paying_users": paying,
        "proceeds_usd": round(proceeds, 2),
        "sales_usd": round(sales, 2),
        "by_territory": by_territory,
        "by_content": by_content,
    }


def render(downloads=None, purchases=None, notes=()):
    lines = ["TreeSmith App Store downloads and purchases (Apple's own counts)",
             "=" * 66, ""]
    if downloads is not None:
        d = downloads
        lines.append("Downloads")
        lines.append("-" * 9)
        if not d["day_count"]:
            lines.append("  no complete days held")
        else:
            lines.append(f"  {d['day_count']} days held "
                         f"({d['days'][0]} to {d['days'][-1]})")
            if d["no_row_days"]:
                lines.append(f"  {len(d['no_row_days'])} day(s) in that span "
                             f"carried no download row (a measured zero, not a "
                             f"gap) unless listed under pull gaps below")
            for after, before in d["pull_gaps"]:
                lines.append(f"  !! PULL GAP {after} -> {before}: days between "
                             f"them left Apple's {ROLLING_WINDOW_DAYS}-day "
                             f"window unread and are UNOBSERVED, not zero")
            lines.append(f"  first-time downloads : {d['first_time_downloads']:,} "
                         f"({d['per_day']}/day over days held)")
            lines.append(f"  redownloads          : {d['redownloads']:,}")
            if d["restores"]:
                lines.append(f"  restores             : {d['restores']:,}")
            lines.append(f"  updates              : {d['updates']:,} "
                         f"(same people, not growth)")
            top = sorted(d["first_time_by_territory"].items(),
                         key=lambda kv: (-kv[1], kv[0]))[:6]
            if top:
                lines.append("  first-time by territory: "
                             + ", ".join(f"{k} {v}" for k, v in top))
            bysrc = sorted(d["first_time_by_source"].items(),
                           key=lambda kv: (-kv[1], kv[0]))
            if bysrc:
                lines.append("  first-time by source   : "
                             + ", ".join(f"{k} {v}" for k, v in bysrc))
        lines.append("")
    if purchases is not None:
        p = purchases
        lines.append("Purchases")
        lines.append("-" * 9)
        lines.append(f"  {p['purchases']} purchase(s), {p['paying_users']} paying "
                     f"user(s), US${p['sales_usd']:,.2f} sales, "
                     f"US${p['proceeds_usd']:,.2f} proceeds")
        if p["days_with_a_sale"]:
            lines.append("  days with a sale: "
                         + ", ".join(p["days_with_a_sale"]))
        if p["by_territory"]:
            lines.append("  by territory: " + ", ".join(
                f"{k} {v}" for k, v in sorted(p["by_territory"].items())))
        lines.append("")
    for note in notes:
        lines.append(note)
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

REPORT_PROFILES = {
    "downloads": {
        "name": DOWNLOADS_REPORT, "required": DL_REQUIRED,
        "aggregate": aggregate_downloads, "records": download_records,
        "schema": DOWNLOAD_SERIES, "csv": DOWNLOADS_CSV,
    },
    "purchases": {
        "name": PURCHASES_REPORT, "required": PU_REQUIRED,
        "aggregate": aggregate_purchases, "records": purchase_records,
        "schema": PURCHASE_SERIES, "csv": PURCHASES_CSV,
    },
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--report", choices=sorted(REPORT_PROFILES),
                        action="append",
                        help="which report(s) to read (default: both)")
    parser.add_argument("--dry-run", action="store_true",
                        help="pull and print, write nothing")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--pulled-at", help="ISO8601 stamp, for backfills")
    parser.add_argument("--request-id",
                        help="override ASC_REQUEST_ID, to backfill history "
                             "from the frozen ONE_TIME_SNAPSHOT request")
    parser.add_argument("--since", help="only summarise days on or after this")
    parser.add_argument("--final", action="store_true",
                        help="mark every day in this pull complete. Only for "
                             "the frozen snapshot request; see _cutoff.")
    args = parser.parse_args(argv)

    try:
        config = src.load_config()
    except (ValueError, FileNotFoundError) as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 2

    token = src.mint_token(config["ASC_KEY_ID"], config["ASC_ISSUER_ID"],
                           config["ASC_PRIVATE_KEY_PATH"])
    pulled_at = (src.normalise_pulled_at(args.pulled_at) if args.pulled_at
                 else src.now_iso())
    wanted = args.report or ["downloads", "purchases"]

    summaries, notes, metas, appended = {}, [], {}, {}
    for which in wanted:
        profile = REPORT_PROFILES[which]
        path = series_file(profile["csv"])
        try:
            totals, anomalies, meta = pull_report(
                config, profile["name"], profile["required"],
                profile["aggregate"], token=token, request_id=args.request_id)
        except src.NotReady as exc:
            # The one failure that must never render as a number.
            notes.append(f"{which.upper()}: NOT READY -- {exc}")
            notes.append(f"  Nothing written to {path}. This is NOT zero "
                         f"{which}.")
            continue
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            print(f"App Store Connect API failed on {which}: {exc}",
                  file=sys.stderr)
            return 1

        candidates = profile["records"](totals, pulled_at,
                                        report=profile["name"],
                                        final=args.final)
        existing = src.read(path, profile["schema"])
        fresh = src.new_rows(existing, candidates, profile["schema"])
        if not args.dry_run:
            src.append(path, fresh, profile["schema"])
        appended[which] = len(fresh)
        metas[which] = meta
        combined = existing + fresh
        summaries[which] = (summarise_downloads(combined, since=args.since)
                            if which == "downloads"
                            else summarise_purchases(combined, since=args.since))
        for kind, counts in (anomalies or {}).items():
            for name, count in sorted(counts.items()):
                notes.append(f"!! {which}: unrecognised {kind} {name!r} on "
                             f"{count} row(s), carried not dropped")

    if args.json:
        print(json.dumps({"meta": metas, "appended": appended,
                          "summaries": summaries, "notes": notes},
                         indent=2, default=str))
        return 0

    print(render(downloads=summaries.get("downloads"),
                 purchases=summaries.get("purchases"), notes=notes))
    print("")
    verb = "would append" if args.dry_run else "appended"
    for which in wanted:
        if which in appended:
            print(f"{verb} {appended[which]} rows to "
                  f"{series_file(REPORT_PROFILES[which]['csv'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
