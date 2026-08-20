#!/usr/bin/env python3
"""Where App Store traffic comes from: search vs browse, as a weekly series.

`appstore_rank.py` and `rank_history.py` can now tell us that TreeSmith moved
from #26 to #1 for a term. Neither can tell us whether anybody was looking.
A rank is a position in a list; it is not an audience. The app was renamed
"TreeSmith: Plant Graft Tracker" -> "TreeSmith: Fruit Tree Tracker" (Play
2026-08-13, iOS 1.0.10 live 2026-08-19 13:13 UTC) on the theory that the name
is the field that ranks (DEC-247), and the rank series measures the theory's
first half. This module measures the second half: did the movement produce
impressions, and what share of them arrive through App Store search rather
than browse.

That share is the number the whole ASO programme is scored against. If browse
supplies most of our impressions, keyword rank is not our lever no matter how
well we rank, and we should say so.

Five things this deliberately does NOT do
-----------------------------------------

1. **It does not look for a per-search-term report, because there is not one.**
   A ONE_TIME_SNAPSHOT request exposes 156 report types and the whole
   APP_STORE_ENGAGEMENT category is exactly five: Discovery and Engagement
   (Standard and Detailed), Web Preview Engagement (Standard and Detailed),
   and Retention Messaging. Enumerated against the live API on 2026-08-20 and
   re-confirmed by this module's own `--list-reports`. Third-party claims that
   Apple's July 2026 per-search-term metrics are API-exportable refer to the
   App Store Connect web UI. `Source Type` is as close as the API gets.

2. **It does not read an empty instances list as zero traffic.** Apple takes
   roughly 24 to 48 hours to generate a snapshot, so "not ready yet" is the
   normal state of a fresh request, and a ONE_TIME_SNAPSHOT stops producing
   instances once it has produced them. Both are reported as NOT READY.
   DEC-249: an absence of measurement and a measured zero must not look alike,
   and here the wrong reading would say the rename killed our impressions.

3. **It does not present the incomplete tail as a decline.** Apple states the
   completeness lag twice and not identically: the Analytics Reports API help
   page says a day is complete two days after the reporting date, while this
   report's own page says "Completeness: Within three days". We drop three
   (`INCOMPLETE_TAIL_DAYS`), which satisfies both, and name the dates dropped
   rather than quietly trimming them.

4. **It does not carry Territory**, though the report has it. Territory would
   multiply every day by ~20 rows forever to answer a question we are not
   asking weekly, and the source data is re-fetchable: Apple holds history back
   to 2024-01-01, so a territory question is answered by re-pulling the report,
   not by hoarding rows against the day somebody asks. Same reasoning drops
   Page Title, Source Info, Campaign, Device and Platform Version.

5. **It does not hardcode the report id.** Report ids are scoped to the request
   that created them (`r15-<request-uuid>`), so the id changes the moment a new
   request exists. Config carries the REQUEST id and the report NAME, and the
   id is rediscovered on every run.

A note on Standard vs Detailed
------------------------------
`Source Type` appears in BOTH the Standard and Detailed reports; the fields
unique to Detailed are Page Title, Source Info and Campaign, none of which we
read. Apple's own guidance is "Download the standard report unless you need to
analyze the unique fields in the detailed report", because Detailed carries
extra privacy measures, and at TreeSmith's volume those could suppress rows we
need. Detailed is the default here because that is the report the existing
request was built around; switching is one line in appstoreconnect.env, and
`--list-reports` prints the ids to switch to.

Config, all from the environment. No credential appears in this file.
--------------------------------------------------------------------
Reads /opt/dale/secrets/appstoreconnect.env (house convention, see
posthog.env / revenuecat.env / lodgify.env); real environment variables win
over the file, so a local run needs no secrets directory.

    ASC_KEY_ID            the App Store Connect API key id
    ASC_ISSUER_ID         the issuer id (per team)
    ASC_PRIVATE_KEY_PATH  path to the PKCS#8 .p8 private key, mode 600
    ASC_REQUEST_ID        the analyticsReportRequests record to read
    ASC_REPORT_NAME       optional, defaults to the Detailed report
    ASC_GRANULARITY       optional, DAILY (default) / WEEKLY / MONTHLY
    ASC_SERIES_PATH       optional, overrides where the series is written

Usage:
    python3 appstore_sources.py                 # pull, append, print
    python3 appstore_sources.py --dry-run       # pull and print, write nothing
    python3 appstore_sources.py --list-reports  # rediscover report ids
    python3 appstore_sources.py --json

Schedule (VPS crontab, Sundays 22:40 UTC): see docs/appstore-source-series.md.
The series lives in /opt/dale/data (weekly_backup.sh territory), NOT in the
repo, because unlike the rank series it is a cache of something Apple will hand
us again on request. Committing it would dirty /opt/dale/repo's working tree
every week for no recovery benefit.
"""

import argparse
import csv
import datetime
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_ROOT = "https://api.appstoreconnect.apple.com/v1"
SECRETS_DIR = "/opt/dale/secrets"
SECRETS_FILE = "appstoreconnect.env"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_REPORT_NAME = "App Store Discovery and Engagement Detailed"
DEFAULT_GRANULARITY = "DAILY"
ENGAGEMENT_CATEGORY = "APP_STORE_ENGAGEMENT"

CSV_NAME = "treesmith-appstore-sources.csv"

# Apple's JWTs are capped at 20 minutes for most endpoints. Ten is plenty for a
# run and short enough that a leaked token in a log is worthless by the time
# anybody reads the log.
TOKEN_TTL_S = 600
AUDIENCE = "appstoreconnect-v1"

# The day the iOS listing changed. Play changed on 2026-08-13 but this report
# is App Store only, so the Play date is not a boundary in this data.
#
# 1.0.10 went live 13:13 UTC, so 2026-08-19 is PART pre-rename and PART post,
# and belongs to neither window. It is reported on its own line rather than
# being quietly assigned to whichever side flatters the result.
RENAME_DATE = "2026-08-19"

# How many trailing days are treated as incomplete and excluded from every
# total. Apple says this twice and not identically:
#
#   "Data for a given day is considered complete two days after the reporting
#    date."                    -- Analytics reports API help page
#   "Completeness: Within three days."
#                              -- the App Store Discovery and Engagement page
#
# Three satisfies both. It also matches the observed consequence: the first
# complete post-rename day (2026-08-20) becomes readable on 2026-08-23, which
# is when a post-rename window first exists at all.
INCOMPLETE_TAIL_DAYS = 3

# Apple's Event values for this report. Everything else is counted into
# `unknown_events` and reported, never silently dropped.
EVENT_IMPRESSION = "Impression"
EVENT_PAGE_VIEW = "Page view"
EVENT_TAP = "Tap"
KNOWN_EVENTS = (EVENT_IMPRESSION, EVENT_PAGE_VIEW, EVENT_TAP)

# Apple's Source Type values. Used for ordering and for the search/browse
# split; an unrecognised value is still carried into the series, because the
# thing we would most want to know about is a source type we have not seen.
SOURCE_SEARCH = "App Store search"
SOURCE_BROWSE = "App Store browse"
KNOWN_SOURCES = (
    SOURCE_SEARCH,
    SOURCE_BROWSE,
    "App referrer",
    "Web referrer",
    "App Clip",
    "Notification",
    "Unavailable",
)

# The report's column headers, from Apple's field table. Matched leniently by
# `resolve_columns` so a cosmetic change to a header does not silently zero a
# metric, but never guessed at: an unresolvable header is an error naming the
# header we actually got.
COL_DATE = "Date"
COL_EVENT = "Event"
COL_SOURCE = "Source Type"
COL_COUNTS = "Counts"
COL_UNIQUE = "Unique Counts"
REQUIRED_COLUMNS = (COL_DATE, COL_EVENT, COL_SOURCE, COL_COUNTS)

# One row per pull x day x source type.
CSV_COLUMNS = [
    "pulled_at",
    "date",
    "source_type",
    "impressions",
    "impressions_unique",
    "page_views",
    "page_views_unique",
    "taps",
    "taps_unique",
    "complete",
]
_INT_COLUMNS = ("impressions", "impressions_unique", "page_views",
                "page_views_unique", "taps", "taps_unique")
_BOOL_COLUMNS = ("complete",)
_METRIC_COLUMNS = _INT_COLUMNS


class NotReady(Exception):
    """The report exists but Apple has not generated an instance yet.

    A distinct type because this is the ONE failure that must never be reported
    as a number. Everything else can degrade to an error line; this one would
    degrade to "zero impressions", which is a different claim entirely.
    """


class ReportSchemaError(Exception):
    """The TSV did not carry the columns we aggregate on.

    Raised rather than defaulting a missing column to zero. A report whose
    `Counts` column has been renamed would otherwise produce a clean-looking
    series of zeroes.
    """


# ── Credentials ──────────────────────────────────────────────────────────────

def load_config(secrets_dir=SECRETS_DIR, environ=None):
    """Return the config dict, environment first, secrets file second.

    Nothing here has a default that could stand in for a credential: a missing
    key id is an error, not an empty string that produces a 401 forty lines
    later.
    """
    environ = os.environ if environ is None else environ
    values = {}

    path = os.path.join(secrets_dir, SECRETS_FILE)
    if os.path.exists(path):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                values[name.strip()] = value.strip().strip('"').strip("'")

    # A real environment variable beats the file, so a local run or a one-off
    # `ASC_REQUEST_ID=... python3 appstore_sources.py` needs no file at all.
    for name in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_PRIVATE_KEY_PATH",
                 "ASC_REQUEST_ID", "ASC_REPORT_NAME", "ASC_GRANULARITY",
                 "ASC_SERIES_PATH"):
        if environ.get(name):
            values[name] = environ[name]

    missing = [n for n in ("ASC_KEY_ID", "ASC_ISSUER_ID", "ASC_PRIVATE_KEY_PATH",
                           "ASC_REQUEST_ID") if not values.get(n)]
    if missing:
        raise ValueError(
            f"missing {', '.join(missing)}. Set them in {path} or in the "
            f"environment. See this module's docstring for the full list."
        )

    key_path = os.path.expanduser(values["ASC_PRIVATE_KEY_PATH"])
    if not os.path.exists(key_path):
        raise FileNotFoundError(
            f"no private key at {key_path}. The .p8 is Benedict's to install; "
            f"it cannot be re-downloaded from Apple once created."
        )
    values["ASC_PRIVATE_KEY_PATH"] = key_path
    values.setdefault("ASC_REPORT_NAME", DEFAULT_REPORT_NAME)
    values.setdefault("ASC_GRANULARITY", DEFAULT_GRANULARITY)
    return values


def mint_token(key_id, issuer_id, private_key_path, ttl=TOKEN_TTL_S, now=None):
    """Mint the ES256 JWT App Store Connect wants.

    PyJWT is imported here rather than at module scope on purpose: every pure
    function in this file has to be testable, and the digest reads the series
    without ever minting a token. A top-level import would make both depend on
    a package neither needs.
    """
    try:
        import jwt  # noqa: PLC0415 - deferred so the module imports without it
    except ImportError as exc:  # pragma: no cover - environment, not logic
        raise ImportError(
            "PyJWT is not installed for this interpreter. On the VPS install "
            "with apt, not pip: the environment is externally managed (PEP 668) "
            "and cron runs /usr/bin/python3. "
            "sudo apt install python3-jwt python3-cryptography"
        ) from exc

    with open(private_key_path, "rb") as fh:
        private_key = fh.read()

    issued = int(now if now is not None else time.time())
    payload = {
        "iss": issuer_id,
        "iat": issued,
        "exp": issued + ttl,
        "aud": AUDIENCE,
    }
    return jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers={"kid": key_id, "typ": "JWT"},
    )


# ── Transport ────────────────────────────────────────────────────────────────

def api_get(path, token, timeout=60):
    """One authenticated GET against the App Store Connect API."""
    url = path if path.startswith("http") else f"{API_ROOT}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "dale-appstore-sources/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def api_get_all(path, token, getter=api_get):
    """Follow `links.next` to exhaustion and return every `data` element.

    Paginated for the same reason every other list read in this repo is
    (DEC-255 / DAL-261): a first page that happens to fill is indistinguishable
    from a complete answer, and here a truncated instances list would silently
    drop the most recent day.
    """
    out = []
    url = path
    while url:
        payload = getter(url, token)
        out.extend(payload.get("data", []))
        url = (payload.get("links") or {}).get("next")
    return out


def fetch_segment(url, timeout=120, opener=None):
    """Download one pre-signed segment URL and return its text.

    No Authorization header: these are pre-signed and adding one makes the CDN
    reject the request. Gzip is detected by magic bytes rather than assumed,
    because a plain-text segment decoded as gzip fails in a way that reads like
    a network error.
    """
    if opener is None:
        req = urllib.request.Request(
            url, headers={"User-Agent": "dale-appstore-sources/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    else:
        raw = opener(url)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


# ── Discovery ────────────────────────────────────────────────────────────────

def list_reports(token, request_id, category=ENGAGEMENT_CATEGORY, getter=api_get):
    """Every report in a request, optionally filtered to one category.

    There is no read-only way to enumerate report types: a request record has
    to exist first. This reads the one that does.
    """
    qs = "?limit=200"
    if category:
        qs += f"&filter[category]={urllib.parse.quote(category)}"
    data = api_get_all(f"/analyticsReportRequests/{request_id}/reports{qs}",
                       token, getter=getter)
    return [
        {
            "id": d["id"],
            "name": (d.get("attributes") or {}).get("name"),
            "category": (d.get("attributes") or {}).get("category"),
        }
        for d in data
    ]


def find_report(token, request_id, name=DEFAULT_REPORT_NAME, getter=api_get):
    """Resolve a report NAME to its request-scoped id, every run.

    Never cached and never hardcoded: `r15-<request-uuid>` is only valid for
    the request that produced it, so a hardcoded id survives right up until
    somebody creates a second request, and then reads a report that no longer
    exists rather than failing.
    """
    reports = list_reports(token, request_id, getter=getter)
    for report in reports:
        if report["name"] == name:
            return report["id"]
    raise LookupError(
        f"no report named {name!r} in request {request_id}. Available: "
        + ", ".join(sorted(r["name"] or "?" for r in reports))
    )


def list_instances(token, report_id, granularity=DEFAULT_GRANULARITY,
                   getter=api_get):
    """Instances of one report, newest processing date first.

    An empty list raises NotReady rather than returning []. Every caller of
    this function is about to sum something, and an empty sum is zero.
    """
    qs = f"?limit=200&filter[granularity]={urllib.parse.quote(granularity)}"
    data = api_get_all(f"/analyticsReports/{report_id}/instances{qs}",
                       token, getter=getter)
    if not data:
        raise NotReady(
            f"no {granularity} instances for report {report_id} yet. Apple "
            f"takes roughly 24-48h to generate a snapshot; a ONE_TIME_SNAPSHOT "
            f"then stops producing new ones. This is not zero traffic."
        )
    instances = [
        {
            "id": d["id"],
            "granularity": (d.get("attributes") or {}).get("granularity"),
            "processing_date": (d.get("attributes") or {}).get("processingDate"),
        }
        for d in data
    ]
    instances.sort(key=lambda i: i["processing_date"] or "", reverse=True)
    return instances


def segment_urls(token, instance_id, getter=api_get):
    """Pre-signed download URLs for one instance.

    An instance can hold several segments, and Apple splits late-arriving
    events and corrections into extra batches, so every segment is fetched and
    concatenated. Taking only the first would silently drop corrections.
    """
    data = api_get_all(f"/analyticsReportInstances/{instance_id}/segments?limit=200",
                       token, getter=getter)
    return [(d.get("attributes") or {}).get("url") for d in data
            if (d.get("attributes") or {}).get("url")]


# ── Parsing (pure) ───────────────────────────────────────────────────────────

def _normalise(header):
    return "".join(ch for ch in header.lower() if ch.isalnum())


def resolve_columns(header, required=REQUIRED_COLUMNS, optional=(COL_UNIQUE,)):
    """Map our logical column names onto the header the file actually carries.

    Lenient about case, spaces and underscores, and strict about absence. The
    alternative -- `row.get("Counts", 0)` -- turns a renamed column into a
    plausible series of zeroes, which is the failure this repo has already
    shipped once with a renamed PostHog event.
    """
    index = {}
    for position, name in enumerate(header):
        index.setdefault(_normalise(name), position)

    resolved = {}
    missing = []
    for wanted in required:
        position = index.get(_normalise(wanted))
        if position is None:
            missing.append(wanted)
        else:
            resolved[wanted] = position
    if missing:
        raise ReportSchemaError(
            f"report is missing {', '.join(missing)}. Header was: "
            f"{' | '.join(header)}"
        )
    for wanted in optional:
        position = index.get(_normalise(wanted))
        if position is not None:
            resolved[wanted] = position
    return resolved


def parse_tsv(text):
    """Parse one report segment into (columns, rows).

    Pure, so the aggregation below is testable without a network, a credential
    or a live snapshot. `rows` are lists of cells; `columns` maps our logical
    names to positions. Ragged rows raise rather than being padded: a short row
    means the file is not what we think it is, and padding it invents a zero.
    """
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if not lines:
        raise ReportSchemaError("empty report segment: no header row")

    header = lines[0].split("\t")
    columns = resolve_columns(header)

    rows = []
    for number, line in enumerate(lines[1:], start=2):
        cells = line.split("\t")
        if len(cells) != len(header):
            raise ReportSchemaError(
                f"line {number}: {len(cells)} fields, header has {len(header)}"
            )
        rows.append(cells)
    return columns, rows


def _to_int(cell):
    """Apple writes plain integers; empty and '-' both mean no value."""
    text = (cell or "").strip().replace(",", "")
    if not text or text == "-":
        return 0
    return int(float(text))


def aggregate_sources(columns, rows):
    """Sum a parsed segment to {(date, source_type): metrics}.

    Returns `(totals, anomalies)`. Anomalies carries the Event and Source Type
    values we did not recognise, with their row counts, so a new Apple
    dimension shows up as a line in the digest instead of as a quiet shortfall
    in the totals.
    """
    totals = {}
    unknown_events = {}
    unknown_sources = {}

    has_unique = COL_UNIQUE in columns
    for cells in rows:
        date = cells[columns[COL_DATE]].strip()
        event = cells[columns[COL_EVENT]].strip()
        source = cells[columns[COL_SOURCE]].strip() or "Unavailable"
        count = _to_int(cells[columns[COL_COUNTS]])
        unique = _to_int(cells[columns[COL_UNIQUE]]) if has_unique else 0

        if source not in KNOWN_SOURCES:
            unknown_sources[source] = unknown_sources.get(source, 0) + 1
        if event not in KNOWN_EVENTS:
            # Counted and named, not dropped: an Event value we do not know
            # about is exactly the thing that would make the totals wrong.
            unknown_events[event] = unknown_events.get(event, 0) + 1
            continue

        bucket = totals.setdefault(
            (date, source),
            {name: 0 for name in _METRIC_COLUMNS},
        )
        if event == EVENT_IMPRESSION:
            bucket["impressions"] += count
            bucket["impressions_unique"] += unique
        elif event == EVENT_PAGE_VIEW:
            bucket["page_views"] += count
            bucket["page_views_unique"] += unique
        else:
            bucket["taps"] += count
            bucket["taps_unique"] += unique

    anomalies = {"unknown_events": unknown_events,
                 "unknown_sources": unknown_sources}
    return totals, anomalies


# ── Completeness (pure) ──────────────────────────────────────────────────────

def _as_date(value):
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


def last_complete_date(pulled_at, tail=INCOMPLETE_TAIL_DAYS):
    """The newest date whose data Apple considers final.

    Everything after this is excluded from every total. It is not rounded down
    to zero and it is not shown as a drop; see the module docstring for the two
    different lags Apple publishes and why we take the longer one.
    """
    return _as_date(pulled_at) - datetime.timedelta(days=tail)


def is_complete(date, pulled_at, tail=INCOMPLETE_TAIL_DAYS):
    return _as_date(date) <= last_complete_date(pulled_at, tail)


def to_records(totals, pulled_at, tail=INCOMPLETE_TAIL_DAYS):
    """Turn an aggregate into series records, stamping completeness per day."""
    stamp = normalise_pulled_at(pulled_at)
    cutoff = last_complete_date(stamp, tail)
    records = []
    for (date, source), metrics in totals.items():
        record = {
            "pulled_at": stamp,
            "date": date,
            "source_type": source,
            "complete": _as_date(date) <= cutoff,
        }
        record.update({name: metrics.get(name, 0) for name in _METRIC_COLUMNS})
        records.append(record)
    records.sort(key=_sort_key)
    return records


def _source_order(source):
    try:
        return KNOWN_SOURCES.index(source)
    except ValueError:
        return len(KNOWN_SOURCES)


def _sort_key(record):
    return (record["pulled_at"], record["date"],
            _source_order(record["source_type"]), record["source_type"])


# ── Series (CSV) ─────────────────────────────────────────────────────────────

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalise_pulled_at(value):
    """Canonicalise a timestamp to `YYYY-MM-DDTHH:MM:SSZ`, or raise."""
    text = str(value).strip()
    iso = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsed = datetime.datetime.fromisoformat(iso)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def series_path(environ=None):
    """Where the series lives.

    /opt/dale/data on the box (weekly_backup.sh covers it), the repo's data/
    directory locally. Deliberately NOT committed: unlike the rank series,
    which no API will ever hand back, this is a cache of something Apple keeps
    for us back to 2024-01-01. Writing it into /opt/dale/repo would leave that
    working tree dirty every week and break the next autonomous pull.
    """
    environ = os.environ if environ is None else environ
    override = environ.get("ASC_SERIES_PATH")
    if override:
        return override
    server = os.path.join(environ.get("DALE_DATA", "/opt/dale/data"), CSV_NAME)
    local = os.path.join(REPO_ROOT, "data", CSV_NAME)
    for candidate in (server, local):
        if os.path.exists(candidate):
            return candidate
    return server if os.path.isdir(os.path.dirname(server)) else local


def _encode(record):
    out = {}
    for column in CSV_COLUMNS:
        value = record.get(column)
        if value is None:
            out[column] = ""
        elif column in _BOOL_COLUMNS:
            out[column] = "true" if value else "false"
        else:
            out[column] = str(value)
    return out


def _decode(row):
    record = {}
    for column in CSV_COLUMNS:
        raw = (row.get(column) or "").strip()
        if column in _INT_COLUMNS:
            record[column] = int(raw) if raw else 0
        elif column in _BOOL_COLUMNS:
            record[column] = raw == "true"
        else:
            record[column] = raw
    return record


def append(path, records):
    """Append records, writing the header only when creating the file."""
    if not records:
        return 0
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fresh = (not os.path.exists(path)) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        if fresh:
            writer.writeheader()
        for record in records:
            writer.writerow(_encode(record))
    return len(records)


def read(path):
    """Parse the series back to typed records. A missing file is empty."""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return []
        if list(reader.fieldnames) != CSV_COLUMNS:
            raise ValueError(
                f"{path}: unexpected header {reader.fieldnames!r}; "
                f"expected {CSV_COLUMNS!r}"
            )
        return [_decode(row) for row in reader]


def latest_view(records):
    """Newest observation of each (date, source_type).

    Apple restates incomplete days, so the same day legitimately appears more
    than once with different numbers. The newest pull wins; the older rows stay
    in the file as the record of what we believed at the time.
    """
    view = {}
    for record in records:
        key = (record["date"], record["source_type"])
        held = view.get(key)
        if held is None or record["pulled_at"] > held["pulled_at"]:
            view[key] = record
    return view


def new_rows(existing, candidates):
    """The subset of `candidates` worth appending.

    Two rows are skipped: a day already recorded as complete (Apple will not
    restate it, so re-pulling it every week would add ~600 identical rows a
    year), and a re-observation whose numbers and completeness are unchanged.
    A genuine restatement always lands.
    """
    view = latest_view(existing)
    out = []
    for record in candidates:
        held = view.get((record["date"], record["source_type"]))
        if held is None:
            out.append(record)
            continue
        if held["complete"]:
            continue
        same = all(held.get(name) == record.get(name) for name in _METRIC_COLUMNS)
        if same and held["complete"] == record["complete"]:
            continue
        out.append(record)
    return out


# ── The split (pure) ─────────────────────────────────────────────────────────

def _blank_window():
    return {name: 0 for name in _METRIC_COLUMNS}


def _search_share(window):
    """Search impressions as a share of all impressions, or None.

    None rather than 0 when there are no impressions at all: a share of nothing
    is undefined, and 0% would read as "search sends us nobody".
    """
    total = window["impressions"]
    if not total:
        return None
    return round(window["by_source"].get(SOURCE_SEARCH, {}).get("impressions", 0)
                 / total * 100, 1)


def _accumulate(records):
    window = _blank_window()
    window["by_source"] = {}
    window["days"] = set()
    for record in records:
        window["days"].add(record["date"])
        bucket = window["by_source"].setdefault(
            record["source_type"], {name: 0 for name in _METRIC_COLUMNS}
        )
        for name in _METRIC_COLUMNS:
            window[name] += record[name]
            bucket[name] += record[name]
    window["days"] = sorted(window["days"])
    window["day_count"] = len(window["days"])
    window["search_share"] = _search_share(window)
    return window


def split_on_rename(records, rename_date=RENAME_DATE, pulled_at=None,
                    tail=INCOMPLETE_TAIL_DAYS):
    """Split the series into pre-rename, post-rename and the boundary day.

    The three rules this function exists to enforce, all of which would
    otherwise be a comparison that reads as a result when it is not one:

      * The trailing `tail` days are excluded from both windows and named.
      * The rename day itself belongs to neither window. 1.0.10 went live at
        13:13 UTC, so 2026-08-19 is part one listing and part the other.
      * When no complete day follows the rename, `has_post_window` is False and
        the caller must present the pre-rename figures as a BASELINE. Rendering
        a two-day post window against ten months of pre would be a lopsided
        comparison that reads as a finding.
    """
    view = latest_view(records)
    if pulled_at is None:
        pulled_at = max((r["pulled_at"] for r in records), default=now_iso())
    stamp = normalise_pulled_at(pulled_at)
    cutoff = last_complete_date(stamp, tail)
    boundary = _as_date(rename_date)

    pre, post, boundary_rows = [], [], []
    excluded = set()
    for record in view.values():
        date = _as_date(record["date"])
        if date > cutoff:
            excluded.add(record["date"])
            continue
        if date < boundary:
            pre.append(record)
        elif date == boundary:
            boundary_rows.append(record)
        else:
            post.append(record)

    result = {
        "pulled_at": stamp,
        "rename_date": rename_date,
        "last_complete_date": cutoff.isoformat(),
        "excluded_incomplete": sorted(excluded),
        "pre": _accumulate(pre),
        "post": _accumulate(post),
        "boundary": _accumulate(boundary_rows),
        "has_post_window": bool(post),
        "latest_date": max((r["date"] for r in view.values()), default=None),
    }
    return result


def series_age_days(records, now=None):
    """Whole days since the newest pull. Tells a stopped job from a quiet week."""
    if not records:
        return None
    newest = max(r["pulled_at"] for r in records)
    then = datetime.datetime.strptime(newest, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc
    )
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return (now - then).days


# ── The pull ─────────────────────────────────────────────────────────────────

def pull(config, token=None, getter=api_get, fetcher=fetch_segment):
    """Fetch every segment of the newest instance and aggregate it.

    Returns `(totals, anomalies, meta)`. Raises NotReady when Apple has not
    generated an instance, which is the caller's cue to say "not ready", not
    to write zeroes.
    """
    if token is None:
        token = mint_token(config["ASC_KEY_ID"], config["ASC_ISSUER_ID"],
                           config["ASC_PRIVATE_KEY_PATH"])
    report_id = find_report(token, config["ASC_REQUEST_ID"],
                            config["ASC_REPORT_NAME"], getter=getter)
    instances = list_instances(token, report_id, config["ASC_GRANULARITY"],
                               getter=getter)

    # The newest instance carries the report; older ones are earlier renderings
    # of the same request. Segments WITHIN the instance are all read, because
    # that is where Apple puts corrections and late-arriving events.
    instance = instances[0]
    urls = segment_urls(token, instance["id"], getter=getter)
    if not urls:
        raise NotReady(
            f"instance {instance['id']} has no segments yet "
            f"(processing date {instance['processing_date']}). Not zero traffic."
        )

    totals = {}
    anomalies = {"unknown_events": {}, "unknown_sources": {}}
    rows_read = 0
    for url in urls:
        columns, rows = parse_tsv(fetcher(url))
        rows_read += len(rows)
        part, part_anomalies = aggregate_sources(columns, rows)
        for key, metrics in part.items():
            bucket = totals.setdefault(key, {name: 0 for name in _METRIC_COLUMNS})
            for name in _METRIC_COLUMNS:
                bucket[name] += metrics[name]
        for kind in anomalies:
            for name, count in part_anomalies[kind].items():
                anomalies[kind][name] = anomalies[kind].get(name, 0) + count

    meta = {
        "report_id": report_id,
        "report_name": config["ASC_REPORT_NAME"],
        "granularity": config["ASC_GRANULARITY"],
        "instance_id": instance["id"],
        "processing_date": instance["processing_date"],
        "instances_available": len(instances),
        "segments": len(urls),
        "rows_read": rows_read,
    }
    return totals, anomalies, meta


# ── Rendering ────────────────────────────────────────────────────────────────

def _pct(value):
    return "n/a" if value is None else f"{value}%"


def render(split, meta=None, anomalies=None):
    """Plain text for a terminal or a cron log."""
    lines = []
    lines.append("TreeSmith App Store discovery: search vs browse")
    lines.append("=" * 62)
    lines.append("")
    lines.append(f"Pulled          : {split['pulled_at']}")
    lines.append(f"Data through    : {split['last_complete_date']}  "
                 f"(last {INCOMPLETE_TAIL_DAYS} days excluded as incomplete)")
    if split["excluded_incomplete"]:
        lines.append(f"  excluded      : {', '.join(split['excluded_incomplete'])}")
    if meta:
        lines.append(f"Report          : {meta['report_name']} "
                     f"({meta['granularity']}, {meta['rows_read']} rows, "
                     f"{meta['segments']} segment(s))")
    lines.append("")

    def window(title, data):
        lines.append(title)
        lines.append("-" * len(title))
        if not data["day_count"]:
            lines.append("  no complete days in this window")
            lines.append("")
            return
        lines.append(f"  {data['day_count']} days "
                     f"({data['days'][0]} to {data['days'][-1]})")
        lines.append(f"  {'source':<20}{'impressions':>13}{'page views':>13}"
                     f"{'taps':>9}{'share':>8}")
        total = data["impressions"]
        ordered = sorted(data["by_source"].items(),
                         key=lambda kv: (-kv[1]["impressions"], kv[0]))
        for source, metrics in ordered:
            share = (f"{metrics['impressions'] / total * 100:.1f}%"
                     if total else "n/a")
            lines.append(f"  {source:<20}{metrics['impressions']:>13,}"
                         f"{metrics['page_views']:>13,}{metrics['taps']:>9,}"
                         f"{share:>8}")
        lines.append(f"  {'TOTAL':<20}{data['impressions']:>13,}"
                     f"{data['page_views']:>13,}{data['taps']:>9,}")
        lines.append(f"  search share of impressions: {_pct(data['search_share'])}")
        lines.append("")

    if not split["has_post_window"]:
        # The whole point of the section in this state. Anything that looked
        # like a comparison here would be a comparison against nothing.
        lines.append("NO POST-RENAME WINDOW YET.")
        lines.append(f"The iOS listing changed on {split['rename_date']}, and no day "
                     f"after it is complete yet.")
        lines.append("The figures below are the PRE-RENAME BASELINE, not a result.")
        lines.append("")
        window("Pre-rename baseline", split["pre"])
    else:
        window("Pre-rename", split["pre"])
        window("Post-rename", split["post"])
        pre_share = split["pre"]["search_share"]
        post_share = split["post"]["search_share"]
        if pre_share is not None and post_share is not None:
            lines.append(f"Search share {pre_share}% -> {post_share}% "
                         f"({post_share - pre_share:+.1f} points) across "
                         f"{split['post']['day_count']} complete post-rename days")
            lines.append("")

    if split["boundary"]["day_count"]:
        b = split["boundary"]
        lines.append(f"Boundary day {split['rename_date']} (part one listing, part "
                     f"the other, counted in neither window):")
        lines.append(f"  {b['impressions']:,} impressions, "
                     f"search share {_pct(b['search_share'])}")
        lines.append("")

    if anomalies and (anomalies.get("unknown_events")
                      or anomalies.get("unknown_sources")):
        lines.append("!! Values Apple sent that we do not recognise:")
        for name, count in sorted(anomalies.get("unknown_events", {}).items()):
            lines.append(f"   Event {name!r}: {count} rows, NOT counted")
        for name, count in sorted(anomalies.get("unknown_sources", {}).items()):
            lines.append(f"   Source Type {name!r}: {count} rows, counted as-is")
        lines.append("")

    lines.append("Source Type is as close as the API gets to a search term; the")
    lines.append("APP_STORE_ENGAGEMENT category has no per-term report.")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="pull and print, write nothing")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--csv", help="series path (default: see series_path)")
    parser.add_argument("--pulled-at", help="ISO8601 stamp, for backfills")
    parser.add_argument("--list-reports", action="store_true",
                        help="print the report ids in the configured request")
    parser.add_argument("--rename-date", default=RENAME_DATE,
                        help=f"listing change date (default {RENAME_DATE})")
    args = parser.parse_args(argv)

    try:
        config = load_config()
    except (ValueError, FileNotFoundError) as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 2

    token = mint_token(config["ASC_KEY_ID"], config["ASC_ISSUER_ID"],
                       config["ASC_PRIVATE_KEY_PATH"])

    if args.list_reports:
        for report in list_reports(token, config["ASC_REQUEST_ID"]):
            print(f"{report['id']}\t{report['name']}")
        return 0

    path = args.csv or series_path()
    try:
        totals, anomalies, meta = pull(config, token=token)
    except NotReady as exc:
        # Exit 0. This is the expected state for the first 24-48h after a
        # request is created, and a non-zero exit would page somebody about
        # Apple working normally.
        print(f"NOT READY: {exc}")
        print("Nothing written. This is not zero traffic.")
        return 0
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"App Store Connect API failed: {exc}", file=sys.stderr)
        return 1

    pulled_at = normalise_pulled_at(args.pulled_at) if args.pulled_at else now_iso()
    candidates = to_records(totals, pulled_at)
    existing = read(path)
    fresh = new_rows(existing, candidates)

    if not args.dry_run:
        append(path, fresh)

    combined = existing + fresh
    split = split_on_rename(combined, rename_date=args.rename_date,
                            pulled_at=pulled_at)

    if args.json:
        print(json.dumps({"meta": meta, "anomalies": anomalies,
                          "appended": len(fresh), "path": path,
                          "split": split}, indent=2, default=list))
    else:
        print(render(split, meta=meta, anomalies=anomalies))
        print("")
        verb = "would append" if args.dry_run else "appended"
        print(f"{verb} {len(fresh)} of {len(candidates)} rows to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
