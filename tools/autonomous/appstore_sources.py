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

Standard, not Detailed, and that is a measurement not a preference
------------------------------------------------------------------
The first live run pulled Detailed and reported 517 impressions, 100% of them
from App Store search, no browse at all and not one tap. Pulling Standard for
the same request on the same day returned 2,225 impressions, 22 of them browse,
and 85 tap rows including 50 `Get`. Detailed was showing 23% of our traffic and
none of our downloads.

Apple's guidance says "download the standard report unless you need to analyze
the unique fields in the detailed report". Those fields are Page Title, Source
Info and Campaign, and this module reads none of them. Detailed's extra privacy
measures are applied per row; at 43 MAU there are not enough rows to survive
them. `--list-reports` prints the ids if this ever needs switching back.

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
ONGOING_ACCESS = "ONGOING"
ONE_TIME_ACCESS = "ONE_TIME_SNAPSHOT"
SECRETS_DIR = "/opt/dale/secrets"
SECRETS_FILE = "appstoreconnect.env"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Standard, not Detailed, and this was measured rather than assumed (2026-08-23).
# Apple's guidance is "download the standard report unless you need to analyze the
# unique fields in the detailed report", and at TreeSmith's volume the difference is
# not cosmetic. Same request, same day, same 3.5 months:
#
#              rows  impressions  browse  Tap rows  territories
#   Detailed     60          517       0         0            7
#   Standard  1,569        2,225      22        85          110
#
# Detailed showed 23% of our impressions, no App Store browse at all, and none of the
# 50 `Get` taps -- the download button, the one engagement that matters. Its extra
# privacy measures are applied per row, and at our row counts they take nearly
# everything. The fields unique to Detailed (Page Title, Source Info, Campaign) are
# ones this module never reads.
DEFAULT_REPORT_NAME = "App Store Discovery and Engagement Standard"
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

# The pre-rename window runs back to the app's first impression, and its early
# months are near-silent: the full 108-day pre-rename mean is 19.1 impressions a
# day, while the last 28 days before the rename average 45. Reporting the
# lifetime rate next to a post-rename rate overstates any change by more than
# double, purely because of what the old window contains. So a trailing window
# is carried alongside it as the comparable baseline.
RECENT_BASELINE_DAYS = 28

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
    # Which report the row came from. Appended 2026-08-23 after the Detailed ->
    # Standard switch, because without it the switch was silent and permanent:
    # `new_rows` skips any day already marked complete, so every historical day
    # would have kept its understated Detailed figures forever while new days
    # came from Standard, and the series would have rendered one trend out of
    # two incompatible sources.
    "report",
]
_INT_COLUMNS = ("impressions", "impressions_unique", "page_views",
                "page_views_unique", "taps", "taps_unique")
_BOOL_COLUMNS = ("complete",)
_METRIC_COLUMNS = _INT_COLUMNS


class SeriesSchema:
    """The column layout and typing of one report's CSV series.

    Exists so that a second report (App Downloads, App Store Purchases) can
    reuse the restatement rule in `new_rows` rather than growing a second copy
    of it. That rule is the subtle part of this file and the part DEC-332 was
    paid for: which rows supersede which, and which days may never be
    re-recorded. Two implementations of it would drift.

    `key_columns` is what makes a row the SAME OBSERVATION as an earlier one.
    For the engagement report that is (date, source type); a downloads row is
    further split by territory and download type, so its key is longer. Getting
    this wrong does not error, it silently merges or duplicates days, so it is
    named per report rather than inferred.
    """

    def __init__(self, columns, key_columns, metric_columns,
                 int_columns=(), float_columns=(), bool_columns=("complete",)):
        self.columns = list(columns)
        self.key_columns = tuple(key_columns)
        self.metric_columns = tuple(metric_columns)
        self.int_columns = tuple(int_columns)
        self.float_columns = tuple(float_columns)
        self.bool_columns = tuple(bool_columns)
        unknown = [c for c in self.key_columns + self.metric_columns
                   if c not in self.columns]
        if unknown:
            raise ValueError(f"schema names columns it does not carry: {unknown}")

    def key(self, record):
        return tuple(record.get(name) for name in self.key_columns)


ENGAGEMENT_SERIES = SeriesSchema(
    columns=CSV_COLUMNS,
    key_columns=("date", "source_type"),
    metric_columns=_METRIC_COLUMNS,
    int_columns=_INT_COLUMNS,
)


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


def api_post(path, token, payload, timeout=60):
    """One authenticated POST against the App Store Connect API.

    Separate from [api_get] rather than a flag on it because everything else
    in this module is a read. A write wants its own name at the call site.
    """
    url = path if path.startswith("http") else f"{API_ROOT}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "dale-appstore-sources/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise _with_apple_detail(exc) from exc


def _with_apple_detail(exc):
    """Re-raise an HTTPError with Apple's own explanation attached.

    `HTTP Error 403: Forbidden` is not actionable. The body says which
    operation the resource actually allows, which is the whole answer.
    """
    try:
        body = json.loads(exc.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - a body we cannot parse is not the story
        return exc
    detail = "; ".join(
        f"{e.get('title', '')}: {e.get('detail', '')}".strip(": ")
        for e in body.get("errors", [])
    )
    if not detail:
        return exc
    return urllib.error.HTTPError(exc.url, exc.code,
                                  f"{exc.reason} ({detail})", exc.hdrs, None)


def find_request(token, app_id, access=ONGOING_ACCESS, getter=api_get):
    """Return the app's newest request of `access` type, or None.

    Apple allows one ONGOING request per app, so creating a second returns a
    409. Checking first turns "already done" into a normal outcome instead of
    an error somebody has to interpret.

    ONE_TIME_SNAPSHOT is different: several may coexist, and a new one is how
    history that fell out of the ongoing report's rolling window is recovered
    (DEC-339). Newest wins, because an older snapshot is by definition the one
    that stops sooner.

    Read through the app relationship, not `/analyticsReportRequests?filter`.
    Apple answers a collection GET on that resource with a 403 naming the
    allowed operations as CREATE, DELETE and GET_INSTANCE only, so the filter
    form fails in a way that looks like a credential problem rather than a
    wrong URL.
    """
    matches = [req for req in
               api_get_all(f"/apps/{app_id}/analyticsReportRequests?limit=200",
                           token, getter=getter)
               if (req.get("attributes") or {}).get("accessType") == access]
    if not matches:
        return None
    return matches[-1]


def find_ongoing_request(token, app_id, getter=api_get):
    """Return the app's existing ONGOING request, or None."""
    return find_request(token, app_id, access=ONGOING_ACCESS, getter=getter)


def create_request(token, app_id, access=ONGOING_ACCESS, poster=api_post,
                   getter=api_get, reuse_existing=True):
    """Create an analytics report request of `access` type for `app_id`.

    Returns (request, created). `created` is False when an existing one was
    reused, because re-running this must be safe: the ONE_TIME_SNAPSHOT this
    replaced (DEC-321) went unnoticed for weeks precisely because nobody could
    re-run the setup step to check it.

    `reuse_existing` is the whole difference between the two access types. An
    ONGOING request is a singleton and re-creating it is an error, so reuse is
    right. A ONE_TIME_SNAPSHOT is a *dated dump*: reusing the old one is the
    failure mode, not the safe path, since the reason to ask for another is
    always that the first one stops before the days you need.

    Apple takes 24-48h to produce the first instance. Until then `pull` raises
    NotReady, which main() already reports as normal rather than as failure.
    """
    if reuse_existing:
        existing = find_request(token, app_id, access=access, getter=getter)
        if existing:
            return existing, False
    payload = {
        "data": {
            "type": "analyticsReportRequests",
            "attributes": {"accessType": access},
            "relationships": {
                "app": {"data": {"type": "apps", "id": str(app_id)}},
            },
        },
    }
    return poster("/analyticsReportRequests", token, payload)["data"], True


def create_ongoing_request(token, app_id, poster=api_post, getter=api_get):
    """Create the app's singleton ONGOING analytics report request."""
    return create_request(token, app_id, access=ONGOING_ACCESS, poster=poster,
                          getter=getter, reuse_existing=True)


def create_snapshot_request(token, app_id, poster=api_post, getter=api_get):
    """Create a fresh ONE_TIME_SNAPSHOT request covering history to today.

    This is the only way to reach a day that has fallen out of the ongoing
    report's rolling window (2 days for r3, 3 for r14). Always creates a new
    one; see `create_request` for why reuse would defeat the purpose.
    """
    return create_request(token, app_id, access=ONE_TIME_ACCESS, poster=poster,
                          getter=getter, reuse_existing=False)


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


def find_report(token, request_id, name=DEFAULT_REPORT_NAME, getter=api_get,
                category=ENGAGEMENT_CATEGORY):
    """Resolve a report NAME to its request-scoped id, every run.

    Never cached and never hardcoded: `r15-<request-uuid>` is only valid for
    the request that produced it, so a hardcoded id survives right up until
    somebody creates a second request, and then reads a report that no longer
    exists rather than failing.
    """
    reports = list_reports(token, request_id, category=category, getter=getter)
    for report in reports:
        if report["name"] == name:
            return report["id"]
    raise LookupError(
        f"no report named {name!r} in request {request_id} category "
        f"{category}. Available: "
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


def request_liveness(token, request_id, category=ENGAGEMENT_CATEGORY,
                     granularity=DEFAULT_GRANULARITY, getter=api_get):
    """Instance counts and date spans for every report in one request.

    This exists to answer the question an empty instance list cannot answer on
    its own (DEC-339). `list_instances` correctly refuses to read zero
    instances as zero events, but "Apple is not producing this report" and
    "nothing happened worth reporting" are then indistinguishable, and they
    have opposite consequences.

    The siblings settle it. Every report lives in the same request, under the
    same credential, with the same generation schedule, so a sibling carrying
    instances proves the request is alive and dates the window Apple has
    actually covered. Only the events differ.

    Returns a list of {name, report_id, instances, first, last}, most
    instances first. Never raises NotReady: emptiness is the finding here.
    """
    out = []
    for report in list_reports(token, request_id, category=category,
                               getter=getter):
        try:
            instances = list_instances(token, report["id"],
                                       granularity=granularity, getter=getter)
        except NotReady:
            instances = []
        dates = sorted(i["processing_date"] for i in instances
                       if i["processing_date"])
        out.append({
            "name": report["name"],
            "report_id": report["id"],
            "instances": len(instances),
            "first": dates[0] if dates else None,
            "last": dates[-1] if dates else None,
        })
    out.sort(key=lambda r: (-r["instances"], r["name"]))
    return out


def explain_silence(report_name, liveness):
    """Turn an empty instance list into a statement about which fact it is.

    `liveness` is `request_liveness` output for the same request. Three
    outcomes, and the difference between them is the whole point:

      * no sibling has instances  -> the request is not producing anything.
        Not ready, stopped, or misconfigured. Nothing is known about any day.
      * siblings have instances   -> the request is alive over a dated window,
        and this report is empty because no event of its kind occurred inside
        that window. Still says nothing about days outside it.
      * the report is not present -> it was never granted, which is a
        different failure from being empty and must not read the same.
    """
    live = [r for r in liveness if r["instances"]]
    named = [r for r in liveness if r["name"] == report_name]
    if not named:
        return (f"{report_name!r} is not among the reports in this request. "
                f"That is a missing grant, not an empty report.")
    if not live:
        return ("No report in this request has any instance, so the request "
                "itself is not producing. Nothing is known about any day.")
    witness = live[0]
    return (f"The request is alive: {witness['name']!r} has "
            f"{witness['instances']} instance(s) covering "
            f"{witness['first']}..{witness['last']}. So {report_name!r} is "
            f"empty because no such event occurred in that window, NOT "
            f"because Apple stopped. This says nothing about days outside it.")


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


def parse_tsv(text, required=REQUIRED_COLUMNS, optional=(COL_UNIQUE,)):
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
    columns = resolve_columns(header, required=required, optional=optional)

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


def to_records(totals, pulled_at, tail=INCOMPLETE_TAIL_DAYS,
               report=DEFAULT_REPORT_NAME):
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
            "report": report,
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


def _encode(record, schema=ENGAGEMENT_SERIES):
    out = {}
    for column in schema.columns:
        value = record.get(column)
        if value is None:
            out[column] = ""
        elif column in schema.bool_columns:
            out[column] = "true" if value else "false"
        elif column in schema.float_columns:
            out[column] = f"{float(value):.2f}"
        else:
            out[column] = str(value)
    return out


def _decode(row, schema=ENGAGEMENT_SERIES):
    record = {}
    for column in schema.columns:
        raw = (row.get(column) or "").strip()
        if column in schema.int_columns:
            record[column] = int(raw) if raw else 0
        elif column in schema.float_columns:
            record[column] = float(raw) if raw else 0.0
        elif column in schema.bool_columns:
            record[column] = raw == "true"
        else:
            record[column] = raw
    return record


def append(path, records, schema=ENGAGEMENT_SERIES):
    """Append records, writing the header only when creating the file."""
    if not records:
        return 0
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    fresh = (not os.path.exists(path)) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=schema.columns)
        if fresh:
            writer.writeheader()
        for record in records:
            writer.writerow(_encode(record, schema))
    return len(records)


def read(path, schema=ENGAGEMENT_SERIES):
    """Parse the series back to typed records. A missing file is empty."""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return []
        if list(reader.fieldnames) != schema.columns:
            raise ValueError(
                f"{path}: unexpected header {reader.fieldnames!r}; "
                f"expected {schema.columns!r}"
            )
        return [_decode(row, schema) for row in reader]


def latest_view(records, schema=ENGAGEMENT_SERIES):
    """Newest observation of each keyed row.

    Apple restates incomplete days, so the same day legitimately appears more
    than once with different numbers. The newest pull wins; the older rows stay
    in the file as the record of what we believed at the time.
    """
    view = {}
    for record in records:
        key = schema.key(record)
        held = view.get(key)
        if held is None or record["pulled_at"] > held["pulled_at"]:
            view[key] = record
    return view


def new_rows(existing, candidates, schema=ENGAGEMENT_SERIES):
    """The subset of `candidates` worth appending.

    Two rows are skipped: a day already recorded as complete (Apple will not
    restate it, so re-pulling it every week would add ~600 identical rows a
    year), and a re-observation whose numbers and completeness are unchanged.
    A genuine restatement always lands.
    """
    view = latest_view(existing, schema)
    out = []
    for record in candidates:
        held = view.get(schema.key(record))
        if held is None:
            out.append(record)
            continue
        if held.get("report") != record.get("report"):
            # Different report, so different numbers for the same day. This is
            # the one case where a "complete" day must be re-recorded.
            out.append(record)
            continue
        if held["complete"]:
            continue
        same = all(held.get(name) == record.get(name)
                   for name in schema.metric_columns)
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
    # Per DAY, not per window. Windows either side of the rename are never the
    # same length -- on the first readable day it is 108 against 1 -- so the
    # totals are not comparable and only the rate is.
    window["per_day"] = (round(window["impressions"] / window["day_count"], 1)
                         if window["day_count"] else None)
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

    pre, post, boundary_rows, pre_recent = [], [], [], []
    excluded = set()
    recent_from = boundary - datetime.timedelta(days=RECENT_BASELINE_DAYS)
    for record in view.values():
        date = _as_date(record["date"])
        if date > cutoff:
            excluded.add(record["date"])
            continue
        if date < boundary:
            pre.append(record)
            if date >= recent_from:
                pre_recent.append(record)
        elif date == boundary:
            boundary_rows.append(record)
        else:
            post.append(record)

    # Days inside the post-rename span that the series simply does not hold.
    # A hole and a day of no traffic render identically once the rows are
    # summed, and this window is the one the rename is judged on, so name it.
    # Counted from our first post-rename day, not from the rename itself, so a
    # window we have not started observing yet does not read as loss.
    held = {_as_date(r["date"]) for r in post}
    missing = []
    if held:
        day = min(held)
        while day <= cutoff:
            if day not in held:
                missing.append(day.isoformat())
            day += datetime.timedelta(days=1)

    result = {
        "pulled_at": stamp,
        "rename_date": rename_date,
        "last_complete_date": cutoff.isoformat(),
        "excluded_incomplete": sorted(excluded),
        "post_missing_days": missing,
        "pre": _accumulate(pre),
        "pre_recent": _accumulate(pre_recent),
        "post": _accumulate(post),
        "boundary": _accumulate(boundary_rows),
        "has_post_window": bool(post),
        "recent_baseline_days": RECENT_BASELINE_DAYS,
        "latest_date": max((r["date"] for r in view.values()), default=None),
    }
    return result


def newest_complete_date(records):
    """The newest day the series can actually report on, or None.

    Deliberately not `max(date)`: the trailing incomplete days are excluded
    from every window, so a series whose only new rows are incomplete has not
    grown in any way a reader of those windows can see.
    """
    dates = [r["date"] for r in records if r.get("complete")]
    return max(dates) if dates else None


def data_age_days(records, now=None):
    """Whole days since the newest COMPLETE day in the series.

    `series_age_days` answers "did the job run". This answers "did the job
    bring anything back", and 2026-08-30 is why both are needed. That pull ran,
    succeeded, printed "Data through 2026-08-27" and appended 0 of 161 rows:
    Apple's ONE_TIME_SNAPSHOT had stopped producing instances, so every
    candidate was a re-observation of a day already recorded as complete and
    `new_rows` correctly dropped all of them.

    The newest day we actually held stayed at 2026-08-20. The post-rename
    window therefore sat at one single day for eleven days while the digest
    presented its search share as that week's result, and the pull-age check
    said nothing, because `pulled_at` only advances when a row lands.

    That near-miss is the point: had even one restatement row landed, pull age
    would have reset to 0 and a permanently frozen series would never have been
    reported at all.
    """
    newest = newest_complete_date(records)
    if newest is None:
        return None
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return (now.date() - _as_date(newest)).days


def series_age_days(records, now=None):
    """Whole days since the newest pull. Tells a stopped job from a quiet week.

    Says nothing about whether the pull brought back new days; see
    `data_age_days` for that.
    """
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
    """Fetch every instance Apple still holds and aggregate them.

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

    # Apple's instances are a ROLLING WINDOW, not successive renderings of one
    # report. Each DAILY instance covers the three days ending the day before
    # its processing date, so consecutive instances overlap by two days and the
    # span advances daily. Reading only the newest one therefore tolerates
    # missing at most two nights: miss a third and those days fall out of the
    # window, nothing will ever hand them back, and the series keeps a hole
    # that is indistinguishable from days with no traffic. So read every
    # instance Apple still holds, oldest first, and let a newer instance
    # REPLACE an older one for any day the two share. Replace, not sum: the
    # overlap is the same day observed twice, and summing would treble it.
    totals = {}
    anomalies = {"unknown_events": {}, "unknown_sources": {}}
    rows_read = 0
    segments_read = 0
    instances_read = 0
    newest_read = None
    for instance in sorted(instances, key=lambda i: i["processing_date"] or ""):
        urls = segment_urls(token, instance["id"], getter=getter)
        if not urls:
            # An instance whose segments have not landed yet. Skipping it is
            # only safe because we raise below when NONE of them produced any.
            continue
        # Segments WITHIN an instance are all read and summed, because that is
        # where Apple puts corrections and late-arriving events.
        instance_totals = {}
        for url in urls:
            columns, rows = parse_tsv(fetcher(url))
            rows_read += len(rows)
            part, part_anomalies = aggregate_sources(columns, rows)
            for key, metrics in part.items():
                bucket = instance_totals.setdefault(
                    key, {name: 0 for name in _METRIC_COLUMNS})
                for name in _METRIC_COLUMNS:
                    bucket[name] += metrics[name]
            for kind in anomalies:
                for name, count in part_anomalies[kind].items():
                    anomalies[kind][name] = anomalies[kind].get(name, 0) + count
        segments_read += len(urls)
        instances_read += 1
        newest_read = instance
        covered = {date for date, _source in instance_totals}
        totals = {key: value for key, value in totals.items()
                  if key[0] not in covered}
        totals.update(instance_totals)

    if not instances_read:
        raise NotReady(
            f"none of the {len(instances)} instance(s) of report {report_id} "
            f"have segments yet (newest processing date "
            f"{instances[0]['processing_date']}). Not zero traffic."
        )

    meta = {
        "report_id": report_id,
        "report_name": config["ASC_REPORT_NAME"],
        "granularity": config["ASC_GRANULARITY"],
        "instance_id": newest_read["id"],
        "processing_date": newest_read["processing_date"],
        "instances_available": len(instances),
        "instances_read": instances_read,
        "segments": segments_read,
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
        # Rates, and BOTH pre-rename rates. The lifetime one is the honest
        # denominator for "how big is this app"; the trailing one is the only
        # fair thing to compare a handful of post-rename days against.
        recent = split["pre_recent"]
        lines.append(
            f"Impressions/day  {split['pre']['per_day']} lifetime "
            f"({split['pre']['day_count']}d)  ·  {recent['per_day']} over the "
            f"{split['recent_baseline_days']}d before the rename  ->  "
            f"{split['post']['per_day']} ({split['post']['day_count']}d)")
        if split["post"]["day_count"] < 7:
            lines.append(f"  {split['post']['day_count']} post-rename day(s) is "
                         f"not a trend. Daily impressions in the 28 days before "
                         f"the rename already ranged widely; wait for a full week.")
        missing = split.get("post_missing_days") or []
        if missing:
            lines.append(f"  {len(missing)} day(s) inside the post-rename span are "
                         f"MISSING from the series, not zero: {missing[0]} to "
                         f"{missing[-1]}. The rate above is over the days we hold.")
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
    parser.add_argument("--create-ongoing-request", metavar="APP_ID",
                        help="create the app's ONGOING analytics report "
                             "request and print the id to put in "
                             "ASC_REQUEST_ID. Safe to re-run.")
    parser.add_argument("--create-snapshot-request", metavar="APP_ID",
                        help="create a NEW ONE_TIME_SNAPSHOT request covering "
                             "history up to today, to recover days that fell "
                             "out of the ongoing rolling window. Creates one "
                             "every time it is run.")
    args = parser.parse_args(argv)

    try:
        config = load_config()
    except (ValueError, FileNotFoundError) as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 2

    token = mint_token(config["ASC_KEY_ID"], config["ASC_ISSUER_ID"],
                       config["ASC_PRIVATE_KEY_PATH"])

    if args.create_ongoing_request or args.create_snapshot_request:
        snapshot = bool(args.create_snapshot_request)
        app_id = args.create_snapshot_request or args.create_ongoing_request
        maker = create_snapshot_request if snapshot else create_ongoing_request
        try:
            request, created = maker(token, app_id)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            print(f"could not create the request: {exc}", file=sys.stderr)
            return 1
        verb = "created" if created else "already exists"
        print(f"{verb}: {request['id']}")
        print(f"attributes: {request.get('attributes')}")
        if created and snapshot:
            print("")
            print("Do NOT put a snapshot id in ASC_REQUEST_ID. Read it once "
                  "with:")
            print(f"  appstore_downloads.py --request-id {request['id']} "
                  f"--final")
            print("Apple takes 24-48h to produce the instance; until then the "
                  "pull reports NOT READY, which is normal.")
        elif created:
            print("")
            print("Set ASC_REQUEST_ID to that id in "
                  "/opt/dale/secrets/appstoreconnect.env.")
            print("Apple takes 24-48h to produce the first instance; until "
                  "then the pull reports NOT READY, which is normal.")
        return 0

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
    candidates = to_records(totals, pulled_at, report=config["ASC_REPORT_NAME"])
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
