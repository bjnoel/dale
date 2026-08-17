#!/usr/bin/env python3
"""Read-only admin view of treestock.com.au subscribers.

Aggregates the server-side subscriber data into an at-a-glance HTML dashboard:
who is subscribed, what they're subscribed to, pending confirmations, and
aggregate demand (top watched varieties, species wishlist).

Three layers, kept separate so the data-shaping is unit-testable without I/O:
  - build_admin_model(...)  pure aggregation over already-loaded rows
  - load_admin_data(...)    reads subscribers.json / pending_subscribers.json /
                            variety_watches.db, then calls build_admin_model
  - render_admin_html(...)  turns the model into a standalone HTML page

Rendered by subscribe_server.py at GET /admin, behind Cloudflare Access. The
page is view-only: it never writes anything.
"""

import html
import json
import re
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from stocklib.page_ledger import (FAMILY_VARIETY, LEDGER_DIRNAME, LIVE,
                                  REDIRECT, RETIRED, TOMBSTONE, ledger_path)
from stocklib.scrape_health import HEALTH_DIRNAME, read_records

DATA_DIR = Path("/opt/dale/data")
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
PENDING_FILE = DATA_DIR / "pending_subscribers.json"
VARIETY_WATCHES_DB = DATA_DIR / "variety_watches.db"
NURSERY_CONTACTS_FILE = DATA_DIR / "nursery-contacts.json"
BUSINESS_SNAPSHOT_FILE = DATA_DIR / "business-snapshot.json"

HEALTH_DAYS = 14
MAX_RECENT_ERRORS = 15

# Past this, a ticket waiting on Benedict is flagged. Matches STALE_DAYS in
# daily-digest.py, which writes the snapshot this reads.
WAITING_STALE_DAYS = 30
SNAPSHOT_STALE_HOURS = 36  # digest runs daily; older than this and the page says so

SITE_URL = "https://treestock.com.au"

VALID_CATEGORIES = ("new_products", "price_drops", "back_in_stock")
VALID_FREQUENCIES = ("daily", "weekly", "off")
STATES = ("ALL", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT")

CATEGORY_SHORT = {
    "new_products": "new",
    "price_drops": "drops",
    "back_in_stock": "restock",
}

# Listing noise that should never have reached a slug. Every token is one
# cultivar_parsing._strip_listing_noise removes from a product title, or one
# _NOISE_PAREN_WORDS drops from a bracketed category label, so a slug still
# carrying one means the parser missed it rather than that a grower named the
# plant that way. Kept as a literal set rather than imported: pulling
# cultivar_parsing into admin_view would put a heavy import on the server and
# add a module to deploy.sh's restart fingerprint (test_variety_overrides
# enforces that). The cost is that this list has to be re-read against
# _NOISE_RES when that changes, which is what the reference above is for.
NOISE_SLUG_TOKENS = frozenset({
    "grafted", "potted", "pot", "pots",
    "bare", "bareroot", "root", "rooted", "cutting", "grown",
    "tree", "trees", "seedling", "seedlings", "plant", "plants",
    "fruit", "nut", "nuts", "pome", "stone",
    "tm", "dwf", "pbr", "dwarf",
})

# Bananas keep dwarf: Dwarf Cavendish is a cultivar, not a pot size. Exactly the
# `keep_dwarf` exception _strip_listing_noise already makes, mirrored here so the
# two cannot disagree about the same 8 slugs.
DWARF_KEEPING_SPECIES = frozenset({"banana"})

# "1 years old", "5-year-old". Age is a listing attribute, never a cultivar.
_AGE_IN_SLUG_RE = re.compile(r"\d+-years?-old")
_AGE_TOKENS = frozenset({"year", "years", "old"})

_SLUGIFY_RE = re.compile(r"[^a-z0-9]+")


# These three mirror the normalisation helpers in send_digest.py. Inlined so this
# module imports standalone (send_digest pulls in daily_digest + stocklib). The
# logic must stay in sync with send_digest.get_subscriber_{state,categories,frequency}.
def _sub_state(sub: dict) -> str:
    if "state" in sub:
        return sub["state"]
    if sub.get("wa_only"):
        return "WA"
    return "ALL"


def _sub_categories(sub: dict) -> list:
    raw = sub.get("categories")
    if raw is None:
        return list(VALID_CATEGORIES)
    return [c for c in raw if c in VALID_CATEGORIES]


def _sub_frequency(sub: dict) -> str:
    freq = sub.get("frequency", "daily")
    return freq if freq in VALID_FREQUENCIES else "daily"


def _short_date(value: str) -> str:
    """ISO timestamp -> YYYY-MM-DD, defensively (returns input on parse failure)."""
    if not value:
        return ""
    return str(value)[:10]


def build_admin_model(subscribers, pending, watches_rows) -> dict:
    """Pure aggregation. No I/O.

    watches_rows: iterable of (email, variety_slug, variety_title, species_slug, added_at)
    """
    subscribers = subscribers or []
    pending = pending or []
    watches_rows = list(watches_rows or [])

    # Map email -> list of watched varieties as (title, slug), preserving order.
    # The slug lets the renderer link each watch to its /variety/<slug>.html page.
    watches_by_email = {}
    for row in watches_rows:
        email = (row[0] or "").lower()
        slug = row[1] or ""
        title = row[2] or slug or ""
        watches_by_email.setdefault(email, []).append((title, slug))

    sub_emails = {(s.get("email") or "").lower() for s in subscribers}

    # Per-subscriber rows (the "who + what"), newest signups first.
    sub_rows = []
    for s in subscribers:
        email = (s.get("email") or "").lower()
        sub_rows.append({
            "email": email,
            "state": _sub_state(s),
            "frequency": _sub_frequency(s),
            "categories": _sub_categories(s),
            "subscribed_at": _short_date(s.get("subscribed_at", "")),
            "watches": watches_by_email.get(email, []),
        })
    sub_rows.sort(key=lambda r: r["subscribed_at"], reverse=True)

    # Watchers who aren't in subscribers.json (set a variety watch without subscribing).
    watch_only = [
        {"email": email, "watches": watches}
        for email, watches in sorted(watches_by_email.items())
        if email not in sub_emails
    ]

    pending_rows = [
        {
            "email": (p.get("email") or "").lower(),
            "state": (p.get("state") or "ALL"),
            "requested_at": _short_date(p.get("requested_at", "")),
        }
        for p in pending
    ]
    pending_rows.sort(key=lambda r: r["requested_at"], reverse=True)

    # Breakdowns.
    state_counts = Counter(_sub_state(s) for s in subscribers)
    freq_counts = Counter(_sub_frequency(s) for s in subscribers)
    cat_counts = Counter()
    for s in subscribers:
        for c in _sub_categories(s):
            cat_counts[c] += 1

    by_state = [(st, state_counts.get(st, 0)) for st in STATES if state_counts.get(st, 0)]
    by_frequency = [(f, freq_counts.get(f, 0)) for f in VALID_FREQUENCIES]
    by_category = [(c, cat_counts.get(c, 0)) for c in VALID_CATEGORIES]

    # Most-watched varieties, aggregated by slug (with a representative title) so
    # the renderer can link each to its /variety/<slug>.html page.
    slug_counts = Counter()
    slug_title = {}
    for row in watches_rows:
        slug = row[1] or ""
        title = row[2] or slug or ""
        slug_counts[slug] += 1
        slug_title.setdefault(slug, title)
    top_varieties = [
        (slug, slug_title.get(slug, slug), n) for slug, n in slug_counts.most_common()
    ]

    distinct_watchers = len({(r[0] or "").lower() for r in watches_rows})

    return {
        "totals": {
            "subscribers": len(subscribers),
            "pending": len(pending),
            "watches": len(watches_rows),
            "watchers": distinct_watchers,
        },
        "by_state": by_state,
        "by_frequency": by_frequency,
        "by_category": by_category,
        "subscribers": sub_rows,
        "watch_only": watch_only,
        "pending": pending_rows,
        "top_varieties": top_varieties,
    }


def build_health_model(day_records) -> dict:
    """Pure aggregation of scrape-health records into the /admin grid model.

    day_records: list of (YYYY-MM-DD, records) pairs, NEWEST first (today at
    index 0). Re-runs append, so only the last record per nursery per day
    counts. Per day a nursery is "ok", "fail" (ok=false), "zero" (ok but 0
    products), or absent (no record, rendered as a gap).
    """
    day_records = list(day_records or [])
    # Oldest -> newest so the grid reads left to right.
    days = [d for d, _ in reversed(day_records)]
    latest_per_day = []  # aligned with days
    for _, records in reversed(day_records):
        latest = {}
        for rec in records:
            if rec.get("nursery"):
                latest[rec["nursery"]] = rec
        latest_per_day.append(latest)

    nurseries = sorted({n for day in latest_per_day for n in day})

    rows = []
    total_records = sum(len(r) for _, r in day_records)
    for nursery in nurseries:
        cells = []
        counts = []
        last_success = None
        latest_products = None
        for day, latest in zip(days, latest_per_day):
            rec = latest.get(nursery)
            if rec is None:
                cells.append(None)
                counts.append(None)
                continue
            products = rec.get("products", 0)
            if not rec.get("ok", False):
                cells.append("fail")
            elif products == 0:
                cells.append("zero")
            else:
                cells.append("ok")
                last_success = rec.get("ts") or day
            counts.append(products)
            latest_products = products
        rows.append({
            "nursery": nursery,
            "cells": cells,
            "counts": counts,
            "latest_products": latest_products,
            "last_success": last_success,
        })

    # Recent errors, newest first.
    recent_errors = []
    for day, latest in zip(reversed(days), reversed(latest_per_day)):
        for nursery in sorted(latest):
            rec = latest[nursery]
            if rec.get("error"):
                recent_errors.append({
                    "day": day,
                    "nursery": nursery,
                    "error": rec["error"],
                })
    recent_errors = recent_errors[:MAX_RECENT_ERRORS]

    return {
        "days": days,
        "rows": rows,
        "recent_errors": recent_errors,
        "total_records": total_records,
    }


def load_health_data(data_dir: Path = DATA_DIR, today: date = None) -> dict:
    """Read the last HEALTH_DAYS of scrape-health records and build the model."""
    today = today or date.today()
    health_dir = Path(data_dir) / HEALTH_DIRNAME
    day_records = []
    for n in range(HEALTH_DAYS):
        day = (today - timedelta(days=n)).isoformat()
        day_records.append((day, read_records(day, health_dir)))
    return build_health_model(day_records)


def load_needs_review(data_dir: Path = DATA_DIR) -> dict | None:
    """The categorize ladder's needs-review report (written nightly by
    build-dashboard --needs-review-out). None when it doesn't exist yet."""
    path = Path(data_dir) / "needs-review.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def build_nursery_model(register, today: date = None) -> dict:
    """Pure aggregation of the nursery relationship register (DAL-80) into the
    /admin view model. No I/O, and no referral figures: those come from
    Plausible at call time in nursery_crm.py and are deliberately not duplicated
    here, so this page cannot show a stale copy of them.

    Rows are ordered by how overdue they are: nurseries with an open action
    first (oldest first), then never-contacted, then everything else by name.
    """
    today = today or date.today()
    register = register or {}
    nurseries = register.get("nurseries") or []

    rows = []
    for n in nurseries:
        touches = sorted(n.get("touches") or [], key=lambda t: t.get("date") or "")
        last = touches[-1]["date"] if touches else None
        open_action = n.get("open_action") or None
        rows.append({
            "key": n.get("key", ""),
            "name": n.get("name", ""),
            "status": n.get("status", "unknown"),
            "contact_name": n.get("contact_name") or "",
            "route": contact_route_label(n),
            "last_touch": last,
            "days_since": days_between(last, today),
            "touches": touches,
            "open_owner": (open_action or {}).get("owner") or "",
            "open_what": (open_action or {}).get("what") or "",
            "open_since": (open_action or {}).get("since") or "",
            "notes": n.get("notes") or "",
        })

    def sort_key(r):
        if r["open_what"]:
            # An action with no "since" date has an unknown age, so it sorts
            # after the ones we can actually date rather than ahead of them.
            return (0, r["open_since"] or "9999", r["name"])
        if r["status"] == "not_contacted":
            return (1, "", r["name"])
        return (2, "", r["name"])

    rows.sort(key=sort_key)

    status_counts = Counter(r["status"] for r in rows)
    return {
        "rows": rows,
        "updated": register.get("updated", ""),
        "totals": {
            "nurseries": len(rows),
            "open_actions": sum(1 for r in rows if r["open_what"]),
            "never_contacted": sum(1 for r in rows if not r["last_touch"]),
        },
        "by_status": sorted(status_counts.items(), key=lambda kv: -kv[1]),
    }


def contact_route_label(n: dict) -> str:
    """How we can reach this nursery: email, else contact form, else phone."""
    if n.get("email"):
        return n["email"]
    if n.get("contact_form"):
        return "web form"
    if n.get("phone"):
        return str(n["phone"])
    return "no route found"


def days_between(iso_day: str, today: date) -> int | None:
    if not iso_day:
        return None
    try:
        return (today - date.fromisoformat(str(iso_day)[:10])).days
    except ValueError:
        return None


def load_nursery_data(data_dir: Path = DATA_DIR, today: date = None) -> dict | None:
    """Read the deployed copy of the register. None when it is not there yet
    (deploy.sh copies it out of the repo, where git history is the audit log)."""
    path = Path(data_dir) / NURSERY_CONTACTS_FILE.name
    if not path.exists():
        return None
    try:
        register = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return build_nursery_model(register, today)


def load_business_data(data_dir: Path = DATA_DIR, now: datetime = None) -> dict | None:
    """Read the business snapshot the daily digest writes.

    None when it has not been written yet, which is the state on any server
    that has not run a digest since this shipped. The page degrades to a note
    rather than an error.
    """
    path = Path(data_dir) / BUSINESS_SNAPSHOT_FILE.name
    if not path.exists():
        return None
    try:
        snapshot = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    # A snapshot that quietly stops updating is worse than none: the page would
    # keep showing confident numbers from a dead cron. Age it explicitly.
    now = now or datetime.now()
    stale = None
    generated = snapshot.get("generated_at")
    if generated:
        try:
            ts = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
            age_h = (now.astimezone(ts.tzinfo) - ts).total_seconds() / 3600
            stale = age_h > SNAPSHOT_STALE_HOURS
            snapshot["age_hours"] = round(age_h, 1)
        except (ValueError, TypeError):
            pass
    snapshot["stale"] = stale
    return snapshot


def load_admin_data(data_dir: Path = DATA_DIR) -> dict:
    """Read the live data files + DB and build the model."""
    data_dir = Path(data_dir)
    subs_file = data_dir / "subscribers.json"
    pending_file = data_dir / "pending_subscribers.json"
    watches_db = data_dir / "variety_watches.db"

    subscribers = []
    if subs_file.exists():
        try:
            subscribers = json.loads(subs_file.read_text())
        except (json.JSONDecodeError, OSError):
            subscribers = []

    pending = []
    if pending_file.exists():
        try:
            pending = json.loads(pending_file.read_text())
        except (json.JSONDecodeError, OSError):
            pending = []

    watches_rows = []
    if watches_db.exists():
        try:
            con = sqlite3.connect(f"file:{watches_db}?mode=ro", uri=True)
            watches_rows = con.execute(
                "SELECT email, variety_slug, variety_title, species_slug, added_at "
                "FROM watches ORDER BY added_at"
            ).fetchall()
            con.close()
        except sqlite3.Error:
            watches_rows = []

    model = build_admin_model(subscribers, pending, watches_rows)
    model["health"] = load_health_data(data_dir)
    model["needs_review"] = load_needs_review(data_dir)
    model["nurseries"] = load_nursery_data(data_dir)
    model["business"] = load_business_data(data_dir)
    model["varieties"] = load_variety_curation(data_dir, watches_rows)
    watch_counts = Counter(row[1] for row in watches_rows if row[1])
    model["inventory"] = load_variety_inventory(data_dir, watch_counts)
    return model


def load_variety_curation(data_dir: Path, watches_rows) -> dict:
    """The variety review queue, built WITHOUT importing cultivar_parsing.

    That import is deliberately kept out of the server (it is heavy, and it
    would join deploy.sh's restart fingerprint list). Everything here is string
    work over two files the server already has: the canonical index the builder
    writes, and the curated override file that rsyncs with the scrapers.

    Sibling detection is prefix matching, and prefix matching is exactly what
    must NOT be applied automatically: avocado-hass-lamb is Lamb Hass, a
    different cultivar. That is the point of surfacing pairs for a human rather
    than folding them.
    """
    data_dir = Path(data_dir)
    index = {}
    index_file = data_dir / "variety-index.json"
    if index_file.exists():
        try:
            loaded = json.loads(index_file.read_text())
            if isinstance(loaded, dict):
                index = {k: v for k, v in loaded.items()
                         if isinstance(k, str) and isinstance(v, str)}
        except (json.JSONDecodeError, OSError):
            index = {}

    overrides = {"deny": [], "alias": {}, "error": ""}
    ov_file = Path(__file__).parent / "variety_overrides.json"
    if ov_file.exists():
        try:
            raw = json.loads(ov_file.read_text())
            overrides["deny"] = sorted(raw.get("deny") or [])
            overrides["alias"] = dict(raw.get("alias") or {})
        except (json.JSONDecodeError, OSError) as e:
            overrides["error"] = str(e)

    watch_counts = {}
    for row in watches_rows:
        watch_counts[row[1]] = watch_counts.get(row[1], 0) + 1

    slugs = sorted(index)
    siblings = []
    for base in slugs:
        longer = [s for s in slugs if s != base and s.startswith(base + "-")]
        if longer:
            siblings.append({
                "base": base,
                "base_watchers": watch_counts.get(base, 0),
                "siblings": [{"slug": s, "watchers": watch_counts.get(s, 0)}
                             for s in sorted(longer)],
            })

    # Watched slugs with no page. The rollout tracks this number and requires
    # it not to grow: each one is an alert whose link 404s.
    orphan_watches = sorted(
        ({"slug": s, "watchers": n} for s, n in watch_counts.items() if s not in index),
        key=lambda d: (-d["watchers"], d["slug"]))

    # Should always be empty. A denied slug someone watches means a curation
    # call silently switched off a live alert.
    denied_but_watched = sorted(
        s for s in overrides["deny"] if watch_counts.get(s))

    return {
        "index_size": len(index),
        "overrides": overrides,
        "siblings": siblings,
        "orphan_watches": orphan_watches,
        "denied_but_watched": denied_but_watched,
    }


# ---------------------------------------------------------------------------
# Catalogue inventory: what the variety pages ARE (DAL-283)
#
# load_variety_curation above knows only slug strings, because the two files it
# reads carry nothing else. The page ledger sitting next to it has the whole
# history of every page (state, first seen, days in stock, last known nurseries
# and prices, and why each state changed) and until now nothing read it. That is
# the whole change: state counts, a species drill-down, and the attention queues
# all fall out of a file the nightly already writes.
#
# Read only, deliberately. Approving anything is DAL-284 and needs the CSRF work
# in docs/admin-varieties-plan.md section 6 first.
# ---------------------------------------------------------------------------

def _slugify(value: str) -> str:
    return _SLUGIFY_RE.sub("-", (value or "").lower()).strip("-")


def noisy_slug_tokens(slug: str, species: str = "") -> list:
    """Listing-noise tokens left in `slug`, ignoring its species prefix.

    The species prefix has to come off first or the check fires on correct
    slugs: Dragon Fruit, Bunya Nut and Grapefruit are species names, so
    `dragon-fruit-asunta` carries no noise at all while `grape-fruit-wheeny`
    (species Grape) carries one.
    """
    slug = slug or ""
    prefix = _slugify(species)
    rest = slug[len(prefix) + 1:] if prefix and slug.startswith(prefix + "-") else slug
    tokens = set(rest.split("-"))
    if prefix in DWARF_KEEPING_SPECIES:
        tokens.discard("dwarf")
    found = sorted(tokens & NOISE_SLUG_TOKENS)
    if _AGE_IN_SLUG_RE.search(rest):
        found.append("<age>")
    return found


def clean_twin(slug: str, noise, live_slugs) -> str:
    """The slug this one would be with its listing noise stripped, IF that page
    already exists as a live page of its own.

    62 of the 120 noisy slugs have one: two live pages for the same cultivar,
    competing for the same search term, and nothing has ever shown that. Stated
    as a fact and nothing more. Folding one into the other is an alias, an alias
    is configuration, configuration is git, and that is DAL-284 and section 5 of
    docs/admin-varieties-plan.md rather than anything this page may do.
    """
    if not noise:
        return ""
    drop = {t for t in noise if t != "<age>"} | _AGE_TOKENS
    parts = [p for p in slug.split("-") if p not in drop and not p.isdigit()]
    candidate = "-".join(parts)
    return candidate if candidate != slug and candidate in live_slugs else ""


def _entry_facts(slug: str, entry: dict, watchers: int = 0) -> dict:
    """One ledger entry flattened to the handful of facts the page shows."""
    rows = entry.get("rows") or []
    nurseries = {r.get("nursery_key") for r in rows if r.get("nursery_key")}
    species = entry.get("species") or ""
    state = entry.get("state") or LIVE
    noise = noisy_slug_tokens(slug, species)
    return {
        "slug": slug,
        "species": species,
        "state": state,
        "title": entry.get("title") or "",
        "nurseries": len(nurseries),
        "products": len(rows),
        "in_stock": any(r.get("available") for r in rows),
        "in_stock_days": int(entry.get("in_stock_days") or 0),
        "live_days": int(entry.get("live_days") or 0),
        "first_seen": entry.get("first_seen") or "",
        "last_in_stock": entry.get("last_in_stock") or "",
        "absent_nights": int(entry.get("absent_nights") or 0),
        "redirect_to": entry.get("redirect_to") or "",
        "see_also": list(entry.get("see_also") or []),
        "retired_reason": entry.get("retired_reason") or "",
        "since": entry.get("since") or "",
        "watchers": watchers,
        "noise": noise,
    }


# Flag key -> (tile label, the one-line explanation under it). Order is the
# order they appear. Every one is a filter the browser can apply to the payload,
# so a count is never a dead end: clicking it lists the pages it counted.
ATTENTION_QUEUES = (
    ("absent", "absent tonight",
     "Not generated tonight. Tombstoned after 2 nights."),
    ("never", "never in stock",
     "Live page, no buyable product has ever appeared on it."),
    ("oos", "out of stock now",
     "Has sold before, nothing available today."),
    ("single", "single-product",
     "One product at one nursery. The page is that nursery's listing."),
    ("noisy", "noisy slug",
     "Slug still carries listing noise the parser should have stripped."),
    ("lonely", "only variety",
     "The sole live page for its species."),
)


def build_variety_inventory(pages: dict, watch_counts: dict = None) -> dict:
    """Pure aggregation over the ledger's `pages` object. No I/O.

    Returns state counts, per-species rows, the attention-queue counts, and the
    flattened per-variety facts. The renderer sends the species rows to HTML and
    the per-variety facts to a compact JSON payload; both come from here so they
    cannot disagree about a number.
    """
    pages = pages or {}
    watch_counts = watch_counts or {}

    facts = [_entry_facts(slug, entry, watch_counts.get(slug, 0))
             for slug, entry in sorted(pages.items())
             if isinstance(entry, dict)]

    counts = Counter(f["state"] for f in facts)

    # Only live pages have a species that means anything for a count: a redirect
    # or tombstone is shown against its species too, but it is not a page the
    # catalogue offers, so it never counts toward "varieties".
    live_per_species = Counter(f["species"] for f in facts if f["state"] == LIVE)
    lonely_species = {s for s, n in live_per_species.items() if n == 1}

    for f in facts:
        live = f["state"] == LIVE
        f["flags"] = {
            "absent": live and f["absent_nights"] > 0,
            "never": live and f["in_stock_days"] == 0,
            "oos": live and not f["in_stock"] and f["in_stock_days"] > 0,
            "single": live and f["products"] == 1 and f["nurseries"] == 1,
            "noisy": live and bool(f["noise"]),
            "lonely": live and f["species"] in lonely_species,
        }

    live_slugs = {f["slug"] for f in facts if f["state"] == LIVE}
    for f in facts:
        f["clean_twin"] = (clean_twin(f["slug"], f["noise"], live_slugs)
                           if f["flags"]["noisy"] else "")
    shadowing = sum(1 for f in facts if f["clean_twin"])

    attention = []
    for key, label, note in ATTENTION_QUEUES:
        if key == "noisy" and shadowing:
            note = f"{note} {shadowing} shadow a clean page that already exists."
        attention.append({
            "key": key, "label": label, "note": note,
            "count": sum(1 for f in facts if f["flags"][key]),
        })

    species_rows = []
    for name in sorted(live_per_species):
        mine = [f for f in facts if f["species"] == name]
        live_rows = [f for f in mine if f["state"] == LIVE]
        species_rows.append({
            "name": name,
            "slug": _slugify(name),
            "varieties": len(live_rows),
            "in_stock": sum(1 for f in live_rows if f["in_stock"]),
            "single": sum(1 for f in live_rows if f["flags"]["single"]),
            "never": sum(1 for f in live_rows if f["flags"]["never"]),
            "noisy": sum(1 for f in live_rows if f["flags"]["noisy"]),
            "redirect": sum(1 for f in mine if f["state"] == REDIRECT),
            "tombstone": sum(1 for f in mine if f["state"] == TOMBSTONE),
        })
    species_rows.sort(key=lambda r: (-r["varieties"], r["name"]))

    # Species with no live page at all still deserve a row: a species whose only
    # pages are redirects is exactly the kind of thing this page exists to show.
    for name in sorted({f["species"] for f in facts} - set(live_per_species)):
        mine = [f for f in facts if f["species"] == name]
        species_rows.append({
            "name": name, "slug": _slugify(name), "varieties": 0,
            "in_stock": 0, "single": 0, "never": 0, "noisy": 0,
            "redirect": sum(1 for f in mine if f["state"] == REDIRECT),
            "tombstone": sum(1 for f in mine if f["state"] == TOMBSTONE),
        })

    return {
        "total": len(facts),
        "counts": {
            LIVE: counts.get(LIVE, 0),
            REDIRECT: counts.get(REDIRECT, 0),
            TOMBSTONE: counts.get(TOMBSTONE, 0),
            RETIRED: counts.get(RETIRED, 0),
        },
        "species": species_rows,
        "species_count": len(live_per_species),
        "attention": attention,
        "shadowing": shadowing,
        "facts": facts,
    }


def load_variety_inventory(data_dir: Path = DATA_DIR, watch_counts: dict = None) -> dict:
    """Read the variety page ledger and aggregate it.

    A missing or unreadable ledger is reported on the page rather than raised:
    the admin view is the thing you open when something is wrong, so it must
    still render when the file it wants is the thing that broke.
    """
    path = ledger_path(FAMILY_VARIETY, Path(data_dir) / LEDGER_DIRNAME)
    if not path.exists():
        return {"present": False, "path": str(path), "error": "",
                **build_variety_inventory({}, watch_counts)}
    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict) or not isinstance(raw.get("pages"), dict):
            raise ValueError("no pages object")
    except (OSError, ValueError) as e:
        return {"present": False, "path": str(path), "error": str(e),
                **build_variety_inventory({}, watch_counts)}

    model = build_variety_inventory(raw["pages"], watch_counts)
    model.update({
        "present": True,
        "path": str(path),
        "error": "",
        "updated": raw.get("updated") or "",
        "skipped_nights": int(raw.get("skipped_nights") or 0),
    })
    return model


# The compact payload the browser filters. Positional rather than keyed: the
# same 2,767 rows are 148KB as arrays and 258KB as objects, and the browser has
# to parse and hold whichever it gets. `cols` makes the format self-describing
# so the saving does not cost a reader their bearings.
PAYLOAD_COLS = ("slug", "species", "state", "nurseries", "in_stock",
                "first_seen", "watchers", "flags", "target", "twin")

PAYLOAD_STATES = (LIVE, REDIRECT, TOMBSTONE, RETIRED)

# Bit per attention queue, in ATTENTION_QUEUES order.
PAYLOAD_FLAGS = tuple(key for key, _, _ in ATTENTION_QUEUES)


def build_varieties_payload(model: dict) -> dict:
    """The per-variety rows, compacted for the browser.

    Species are interned to an index, states and flags to small integers, and
    the year is dropped from `first_seen` (every page is 20xx). None of that is
    cleverness for its own sake: the ledger is 3.1MB and /variety/index.html is
    already 1.4MB, so the one rule this page has is that it does not inline the
    catalogue.
    """
    facts = model.get("facts") or []
    species = sorted({f["species"] for f in facts})
    species_idx = {name: i for i, name in enumerate(species)}
    state_idx = {name: i for i, name in enumerate(PAYLOAD_STATES)}

    rows = []
    for f in facts:
        bits = 0
        for i, key in enumerate(PAYLOAD_FLAGS):
            if f["flags"].get(key):
                bits |= 1 << i
        rows.append([
            f["slug"],
            species_idx[f["species"]],
            state_idx.get(f["state"], 0),
            f["nurseries"],
            1 if f["in_stock"] else 0,
            (f["first_seen"] or "")[2:],
            f["watchers"],
            bits,
            f["redirect_to"],
            f.get("clean_twin", ""),
        ])

    return {
        "cols": list(PAYLOAD_COLS),
        "species": species,
        "states": list(PAYLOAD_STATES),
        "flags": list(PAYLOAD_FLAGS),
        "flagLabels": [label for _, label, _ in ATTENTION_QUEUES],
        "updated": model.get("updated", ""),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _variety_link(title: str, slug: str) -> str:
    """Link a variety to its page on the main site (opens in a new tab)."""
    if not slug:
        return _esc(title)
    return (
        f'<a href="{SITE_URL}/variety/{_esc(slug)}.html" target="_blank" '
        f'rel="noopener">{_esc(title)}</a>'
    )


def _watch_links(watches) -> str:
    """Render a list of (title, slug) watches as comma-separated links."""
    if not watches:
        return '<span class="muted">—</span>'
    return ", ".join(_variety_link(t, s) for t, s in watches)


def _cards(totals: dict) -> str:
    cards = [
        ("Subscribers", totals["subscribers"]),
        ("Pending", totals["pending"]),
        ("Variety watches", totals["watches"]),
        ("Watchers", totals["watchers"]),
    ]
    items = "".join(
        f'<div class="card"><div class="card-num">{n}</div>'
        f'<div class="card-label">{_esc(label)}</div></div>'
        for label, n in cards
    )
    return f'<div class="cards">{items}</div>'


def _count_table(title: str, rows, label_fn=lambda x: x) -> str:
    if not rows:
        body = '<tr><td colspan="2" class="muted">None</td></tr>'
    else:
        body = "".join(
            f"<tr><td>{_esc(label_fn(label))}</td><td class='num'>{n}</td></tr>"
            for label, n in rows
        )
    return (
        f'<section><h2>{_esc(title)}</h2>'
        f'<table class="mini"><tbody>{body}</tbody></table></section>'
    )


def _categories_label(cats) -> str:
    if not cats:
        return "(muted)"
    return ", ".join(CATEGORY_SHORT.get(c, c) for c in cats)


def _subscriber_table(rows) -> str:
    if not rows:
        return '<section><h2>Subscribers</h2><p class="muted">No subscribers yet.</p></section>'
    body = []
    for r in rows:
        body.append(
            "<tr>"
            f"<td>{_esc(r['email'])}</td>"
            f"<td>{_esc(r['state'])}</td>"
            f"<td>{_esc(r['frequency'])}</td>"
            f"<td>{_esc(_categories_label(r['categories']))}</td>"
            f"<td>{_esc(r['subscribed_at'])}</td>"
            f"<td>{_watch_links(r['watches'])}</td>"
            "</tr>"
        )
    return (
        f'<section><h2>Subscribers ({len(rows)})</h2>'
        '<table><thead><tr>'
        '<th>Email</th><th>State</th><th>Freq</th><th>Categories</th>'
        '<th>Joined</th><th>Variety watches</th>'
        '</tr></thead><tbody>' + "".join(body) + '</tbody></table></section>'
    )


def _watch_only_table(rows) -> str:
    if not rows:
        return ""
    body = "".join(
        "<tr>"
        f"<td>{_esc(r['email'])}</td>"
        f"<td>{_watch_links(r['watches'])}</td>"
        "</tr>"
        for r in rows
    )
    return (
        f'<section><h2>Variety watchers, not subscribed ({len(rows)})</h2>'
        '<p class="muted">Set a variety alert without joining the digest list.</p>'
        '<table><thead><tr><th>Email</th><th>Variety watches</th></tr></thead>'
        f'<tbody>{body}</tbody></table></section>'
    )


def _top_varieties_table(rows) -> str:
    """rows: list of (slug, title, count). Each variety links to the main site."""
    if not rows:
        body = '<tr><td colspan="2" class="muted">None</td></tr>'
    else:
        body = "".join(
            f"<tr><td>{_variety_link(title, slug)}</td><td class='num'>{n}</td></tr>"
            for slug, title, n in rows
        )
    return (
        '<section><h2>Top watched varieties</h2>'
        f'<table class="mini"><tbody>{body}</tbody></table></section>'
    )


_CELL_LABELS = {
    "ok": ("ok", "OK"),
    "fail": ("fail", "FAILED"),
    "zero": ("zero", "zero products"),
    None: ("none", "no record"),
}


def _health_grid(health: dict) -> str:
    days = health["days"]
    # Column headers: day-of-month, full date in the tooltip.
    head_cells = "".join(
        f'<th class="hday" title="{_esc(d)}">{_esc(d[8:10])}</th>' for d in days
    )
    body = []
    for row in health["rows"]:
        cells = []
        for day, status, count in zip(days, row["cells"], row["counts"]):
            cls, label = _CELL_LABELS[status]
            detail = f"{day}: {label}"
            if count is not None:
                detail += f", {count} products"
            cells.append(f'<td class="hcell {cls}" title="{_esc(detail)}"></td>')
        last = _short_date(row["last_success"]) if row["last_success"] else "never"
        products = row["latest_products"]
        body.append(
            "<tr>"
            f"<td>{_esc(row['nursery'])}</td>"
            + "".join(cells) +
            f"<td class='num'>{products if products is not None else '—'}</td>"
            f"<td>{_esc(last)}</td>"
            "</tr>"
        )
    return (
        '<table class="health"><thead><tr>'
        f'<th>Nursery</th>{head_cells}<th class="num">Products</th><th>Last success</th>'
        '</tr></thead><tbody>' + "".join(body) + "</tbody></table>"
    )


def _health_errors(errors) -> str:
    if not errors:
        return ""
    body = "".join(
        "<tr>"
        f"<td>{_esc(e['day'])}</td>"
        f"<td>{_esc(e['nursery'])}</td>"
        f"<td>{_esc(e['error'])}</td>"
        "</tr>"
        for e in errors
    )
    return (
        f'<h3>Recent errors</h3>'
        '<table><thead><tr><th>Day</th><th>Nursery</th><th>Error</th></tr></thead>'
        f'<tbody>{body}</tbody></table>'
    )


def _health_section(health) -> str:
    if not health or not health["rows"]:
        return (
            f'<section><h2>Scraper health ({HEALTH_DAYS} days)</h2>'
            '<p class="muted">No scrape-health records yet. They appear after the '
            'next nightly scrape.</p></section>'
        )
    legend = (
        '<p class="muted legend">'
        '<span class="hcell ok"></span> ok &nbsp;'
        '<span class="hcell zero"></span> zero products &nbsp;'
        '<span class="hcell fail"></span> failed &nbsp;'
        '<span class="hcell none"></span> no record</p>'
    )
    return (
        f'<section><h2>Scraper health ({HEALTH_DAYS} days)</h2>'
        + legend + _health_grid(health) + _health_errors(health["recent_errors"])
        + "</section>"
    )


def _needs_review_section(report) -> str:
    """Per-nursery unclassified counts from the categorize ladder (DEC-200).
    The correction loop: a high count means the nursery needs a species record
    or a nursery_categories.json mapping line, not hand-tuned keywords."""
    if not report or not report.get("nurseries"):
        return (
            '<section><h2>Needs review (unclassified products)</h2>'
            '<p class="muted">No needs-review report yet. It appears after the '
            'next nightly dashboard build.</p></section>'
        )
    rows = sorted(report["nurseries"].items(),
                  key=lambda kv: -kv[1].get("unclassified", 0))
    body = []
    for nursery, entry in rows:
        total = entry.get("total", 0)
        unclassified = entry.get("unclassified", 0)
        pct = f"{unclassified / total * 100:.0f}%" if total else "0%"
        examples = ", ".join(entry.get("examples", [])[:3])
        body.append(
            "<tr>"
            f"<td>{_esc(nursery)}</td>"
            f"<td class='num'>{unclassified}</td>"
            f"<td class='num'>{total}</td>"
            f"<td class='num'>{_esc(pct)}</td>"
            f"<td>{_esc(examples)}</td>"
            "</tr>"
        )
    generated = _short_date(report.get("generated_at", ""))
    return (
        f'<section><h2>Needs review (unclassified products)</h2>'
        f'<p class="muted">From the categorize ladder, generated {_esc(generated)}. '
        'Fix by adding a species record or a nursery_categories.json mapping.</p>'
        '<table><thead><tr><th>Nursery</th><th class="num">Unclassified</th>'
        '<th class="num">Total</th><th class="num">Rate</th><th>Examples</th>'
        '</tr></thead><tbody>' + "".join(body) + '</tbody></table></section>'
    )


_STATUS_CLASS = {
    "warm": "st-warm",
    "personal": "st-warm",
    "courtesy": "st-mid",
    "contacted": "st-mid",
    "not_contacted": "st-cold",
}


def _touch_history(touches) -> str:
    """Full contact history for one nursery, oldest first."""
    if not touches:
        return '<span class="muted">Never contacted.</span>'
    items = []
    for t in touches:
        arrow = "&rarr; out" if t.get("direction") == "out" else "&larr; in"
        by = t.get("by") or ""
        channel = t.get("channel") or ""
        meta = " · ".join(x for x in (arrow, _esc(by), _esc(channel)) if x)
        items.append(
            f'<li><span class="tdate">{_esc(_short_date(t.get("date", "")))}</span> '
            f'<span class="muted">{meta}</span><br>{_esc(t.get("summary", ""))}</li>'
        )
    return f'<ul class="touches">{"".join(items)}</ul>'


def _nursery_section(model) -> str:
    """The nursery relationship register (DAL-80): who we have spoken to, when,
    and whose move it is next. Ordered by what is overdue, not alphabetically."""
    if not model:
        return (
            '<section><h2>Nursery relationships</h2>'
            '<p class="muted">No register deployed yet. It is copied out of the '
            'repo by deploy.sh (data/nursery-contacts.json).</p></section>'
        )

    t = model["totals"]
    status_line = ", ".join(f"{_esc(s)} {n}" for s, n in model["by_status"])

    # Split, don't sort: build_nursery_model already orders open-action-first,
    # so partitioning preserves its ordering. Of 27 nurseries, 22 have never
    # been contacted and have no touches, and rendering all of them as full
    # rows is what made this section 55 rows and the top of the page.
    actionable = [r for r in model["rows"] if r["open_what"]]
    rest = [r for r in model["rows"] if not r["open_what"]]

    head = (
        '<table><thead><tr>'
        '<th>Nursery</th><th>Status</th><th>Last touch</th><th>Next action</th>'
        '</tr></thead><tbody>'
    )
    tables = _nursery_table(actionable, head) if actionable else (
        '<p class="muted">No open actions.</p>')
    if rest:
        tables += (
            f'<details><summary>{len(rest)} more '
            f'{"nursery" if len(rest) == 1 else "nurseries"}, nothing outstanding'
            f'</summary>{_nursery_table(rest, head)}</details>'
        )

    return (
        '<section><h2>Nursery relationships</h2>'
        f'<p class="muted">{t["nurseries"]} nurseries · '
        f'<strong>{t["open_actions"]} open actions</strong> · '
        f'{t["never_contacted"]} never contacted · {status_line}. '
        f'Register updated {_esc(model["updated"])}. '
        'Open actions are also listed under '
        '<a href="/admin">Business state</a>, alongside the Linear tickets '
        'waiting on you. '
        'Referral click counts are deliberately not shown here: they are read live '
        'from Plausible by <code>nursery_crm.py report</code> so they cannot go stale '
        'on a cached page.</p>'
        + tables + '</section>'
    )


def _nursery_table(rows, head: str) -> str:
    """One nursery table body. Split out so the open-action rows and the
    collapsed remainder render identically."""
    body = []
    for r in rows:
        since = f' <span class="muted">({r["days_since"]}d ago)</span>' if r["days_since"] is not None else ""
        last = f'{_esc(r["last_touch"])}{since}' if r["last_touch"] else '<span class="muted">never</span>'
        if r["open_what"]:
            owner = _esc(r["open_owner"] or "unassigned")
            action = (
                f'<div class="action"><strong>{owner}:</strong> {_esc(r["open_what"])}'
                f' <span class="muted">(since {_esc(r["open_since"])})</span></div>'
            )
        else:
            action = '<span class="muted">&mdash;</span>'
        name = _esc(r["name"])
        if r["contact_name"]:
            name += f' <span class="muted">({_esc(r["contact_name"])})</span>'
        cls = _STATUS_CLASS.get(r["status"], "st-cold")
        body.append(
            "<tr>"
            f"<td>{name}<br><span class='muted small'>{_esc(r['route'])}</span></td>"
            f"<td><span class='pill {cls}'>{_esc(r['status'])}</span></td>"
            f"<td>{last}</td>"
            f"<td>{action}</td>"
            "</tr>"
        )
        # Only emit the expander when there is something behind it, and label it
        # for what is actually there. It used to render for every nursery, so
        # the 22 never-contacted ones each got an empty "History (0)" row, and
        # the 14 of those carrying only a note said "History (0)" over a note.
        if r["touches"] or r["notes"]:
            label = f"History ({len(r['touches'])})" if r["touches"] else "Notes"
            body.append(
                "<tr class='histrow'><td colspan='4'>"
                f"<details><summary>{label}</summary>"
                f"{_touch_history(r['touches']) if r['touches'] else ''}"
                + (f"<p class='muted small'>{_esc(r['notes'])}</p>" if r["notes"] else "")
                + "</details></td></tr>"
            )

    return head + "".join(body) + "</tbody></table>"


def _pending_table(rows) -> str:
    if not rows:
        return '<section><h2>Pending confirmations</h2><p class="muted">None.</p></section>'
    body = "".join(
        "<tr>"
        f"<td>{_esc(r['email'])}</td>"
        f"<td>{_esc(r['state'])}</td>"
        f"<td>{_esc(r['requested_at'])}</td>"
        "</tr>"
        for r in rows
    )
    return (
        f'<section><h2>Pending confirmations ({len(rows)})</h2>'
        '<table><thead><tr><th>Email</th><th>State</th><th>Requested</th></tr></thead>'
        f'<tbody>{body}</tbody></table></section>'
    )


_VERDICT_CLASS = {
    "moved": ("moved", "v-good"),
    "declined": ("went the wrong way", "v-bad"),
    "flat": ("did not move", "v-flat"),
    "too-small": ("too small to call", "v-none"),
    "unmeasured": ("could not be measured", "v-none"),
}


def _waiting_table(waiting) -> str:
    if not waiting:
        return '<p class="muted">Nothing is blocked on Benedict.</p>'
    rows = []
    for w in waiting:
        days = w.get("days")
        stale = days is not None and days >= WAITING_STALE_DAYS
        # One class attribute, not two: a second `class` on the same tag is
        # ignored by every browser, which would have silently dropped the
        # over-30-days highlight that is the whole point of the column.
        cls = "num action" if stale else "num"
        if w.get("source") == "nursery":
            who = "nursery register"
        else:
            who = "assigned" if w.get("assigned") else "asked in ticket"
        rows.append(
            "<tr>"
            f"<td class='{cls}'><strong>{_esc(days if days is not None else '—')}</strong></td>"
            f"<td>{_esc(w.get('id'))}</td>"
            f"<td>{_esc(w.get('title'))}</td>"
            f"<td>{_esc(w.get('state'))}</td>"
            f"<td class='small muted'>{_esc(who)}</td>"
            "</tr>"
        )
    return (
        '<table><thead><tr><th class="num">Days</th><th>Item</th><th>What</th>'
        '<th>State</th><th>Source</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _verdict_table(verdicts, summary) -> str:
    parts = []
    if verdicts:
        rows = []
        for r in verdicts:
            v, base = r.get("verdict") or {}, r.get("baseline") or {}
            label, cls = _VERDICT_CLASS.get(v.get("call"), (v.get("call", "?"), "v-none"))
            pct = f" ({v['pct']:+.1f}%)" if v.get("pct") is not None else ""
            rows.append(
                "<tr>"
                f"<td>{_esc(r.get('ticket'))}</td>"
                f"<td class='small'>{_esc(r.get('metric'))}</td>"
                f"<td class='num'>{_esc(base.get('value'))} &rarr; {_esc(v.get('value'))}"
                f"<span class='muted small'>{_esc(pct)}</span></td>"
                f"<td><span class='pill {cls}'>{_esc(label)}</span></td>"
                "</tr>"
            )
        parts.append(
            '<table><thead><tr><th>Ticket</th><th>Metric</th>'
            '<th class="num">Before &rarr; after</th><th>Verdict</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
        )
    else:
        parts.append('<p class="muted">No verdicts settled recently.</p>')

    if summary:
        bits = [f"{summary.get('awaiting', 0)} awaiting a verdict"]
        if summary.get("next_due"):
            bits.append(f"next due {summary['next_due']}")
        if summary.get("ungraded"):
            bits.append(f"{summary['ungraded']} shipped without a readable metric")
        parts.append(f'<p class="small muted">{_esc(" · ".join(bits))}</p>')
    return "".join(parts)


def _traffic_row(traffic) -> str:
    sites = (traffic or {}).get("sites") or []
    if not sites:
        return ""
    rows = []
    for s in sites:
        def chg(v):
            if v is None:
                return '<span class="muted">—</span>'
            cls = "v-good" if v > 0 else ("v-bad" if v < 0 else "v-flat")
            return f'<span class="pill {cls}">{v:+d}%</span>'
        rows.append(
            "<tr>"
            f"<td>{_esc(s.get('site'))}</td>"
            f"<td class='num'>{_esc(s.get('month_visitors'))}</td>"
            f"<td class='num'>{chg(s.get('month_change'))}</td>"
            f"<td class='num'>{_esc(s.get('week_visitors'))}</td>"
            f"<td class='num'>{chg(s.get('week_change'))}</td>"
            "</tr>"
        )
    return (
        '<h3>Traffic</h3>'
        '<table><thead><tr><th>Site</th><th class="num">30d visitors</th>'
        '<th class="num">vs prev</th><th class="num">7d</th><th class="num">vs prev</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _business_section(snapshot) -> str:
    """State of the business: what is blocked on Benedict, what shipped work
    actually did, and the headline numbers. The daily email is a flow report;
    this is the thing to open when you want the current picture instead."""
    if not snapshot:
        return (
            '<section><h2>Business state</h2>'
            '<p class="muted">No snapshot yet. The daily digest writes one at '
            '22:00 UTC.</p></section>'
        )

    header = ""
    if snapshot.get("stale"):
        header = (
            f'<p class="action"><strong>Stale.</strong> Last written '
            f'{_esc(snapshot.get("age_hours"))}h ago, so the digest cron may have '
            f'stopped. Numbers below are from then, not now.</p>'
        )

    return (
        '<section><h2>Business state</h2>'
        + header
        + '<h3>Waiting on Benedict</h3>'
        + _waiting_table(snapshot.get("waiting_on_benedict") or [])
        + '<h3>Outcome verdicts</h3>'
        + _verdict_table(snapshot.get("verdicts_recent") or [],
                         snapshot.get("verdicts_summary") or {})
        + _traffic_row(snapshot.get("traffic"))
        + '</section>'
    )


# Page chrome, shared by /admin and /admin/digest (digest_archive.py). Kept as a
# plain string rather than inlined in the f-string below so a second page can use
# it without a second copy of the stylesheet drifting away from this one.
PAGE_CSS = """
  :root { color-scheme: light; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    margin:0; background:#f9fafb; color:#111827; }
  header { background:#065f46; color:#fff; padding:16px 24px; }
  header h1 { margin:0; font-size:1.1rem; }
  header .ts { font-size:0.8rem; opacity:0.85; }
  header a { color:#a7f3d0; }
  main { max-width:1100px; margin:0 auto; padding:24px 16px 64px; }
  .cards { display:flex; flex-wrap:wrap; gap:12px; margin:0 0 24px; }
  .card { flex:1 1 150px; background:#fff; border:1px solid #e5e7eb;
    border-radius:10px; padding:16px; text-align:center; }
  .card-num { font-size:1.8rem; font-weight:700; color:#065f46; }
  .card-label { font-size:0.8rem; color:#6b7280; margin-top:4px; }
  section { margin:0 0 28px; }
  h2 { font-size:1rem; color:#374151; margin:0 0 10px; }
  table { width:100%; border-collapse:collapse; background:#fff;
    border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; font-size:0.85rem; }
  th, td { text-align:left; padding:8px 10px; border-bottom:1px solid #f3f4f6;
    vertical-align:top; }
  th { background:#f3f4f6; color:#374151; font-weight:600; }
  td.num, th.num { text-align:right; }
  tr:last-child td { border-bottom:none; }
  .mini { max-width:100%; }
  .muted { color:#9ca3af; }
  .grid3 { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; }
  .grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }
  .grid3 section, .grid2 section { margin:0; }
  h3 { font-size:0.9rem; color:#374151; margin:14px 0 8px; }
  table.health th.hday { font-size:0.7rem; text-align:center; padding:6px 2px; }
  td.hcell { width:18px; padding:0; }
  span.hcell { display:inline-block; width:12px; height:12px; border-radius:2px;
    vertical-align:-2px; }
  .hcell.ok { background:#34d399; }
  .hcell.fail { background:#ef4444; }
  .hcell.zero { background:#fbbf24; }
  .hcell.none { background:#e5e7eb; }
  .legend { font-size:0.8rem; margin:0 0 10px; }
  .small { font-size:0.78rem; }
  .pill { display:inline-block; padding:2px 8px; border-radius:999px;
    font-size:0.72rem; font-weight:600; white-space:nowrap; }
  .st-warm { background:#d1fae5; color:#065f46; }
  .st-mid { background:#fef3c7; color:#92400e; }
  .st-cold { background:#f3f4f6; color:#6b7280; }
  .v-good { background:#d1fae5; color:#065f46; }
  .v-bad { background:#fee2e2; color:#991b1b; }
  .v-flat { background:#fef3c7; color:#92400e; }
  .v-none { background:#f3f4f6; color:#6b7280; }
  .action { color:#92400e; }
  tr.histrow td { padding:0 10px 8px; border-bottom:1px solid #e5e7eb; }
  tr.histrow summary { cursor:pointer; font-size:0.78rem; color:#6b7280; }
  ul.touches { margin:8px 0 0; padding-left:18px; font-size:0.8rem; }
  ul.touches li { margin-bottom:8px; }
  .tdate { font-weight:600; }
  nav.tabs { display:flex; gap:6px; flex-wrap:wrap; margin-top:12px; }
  nav.tabs a { padding:6px 12px; border-radius:999px; font-size:0.82rem;
    text-decoration:none; color:#d1fae5; background:rgba(255,255,255,0.14); }
  nav.tabs a.here { background:#fff; color:#065f46; font-weight:600; }
"""

# The admin surface, in the order the tabs appear. /admin is the landing page and
# holds the only thing that asks anything of the reader; the rest is reference.
# Splitting these out of one page was Benedict's call, 2026-08-10: as a single
# document it had become a wall of text you had to scroll past to find anything.
ADMIN_PAGES = (
    ("/admin", "Business state"),
    ("/admin/subscribers", "Subscribers"),
    ("/admin/nurseries", "Nurseries"),
    ("/admin/varieties", "Varieties"),
    ("/admin/varieties/review", "Variety review"),
    ("/admin/digest", "Daily digest"),
)


def render_nav(current_path: str) -> str:
    """Tab bar shared by every admin page. `current_path` is matched exactly."""
    links = []
    for path, label in ADMIN_PAGES:
        cls = ' class="here"' if path == current_path else ""
        links.append(f'<a href="{path}"{cls}>{_esc(label)}</a>')
    return '<nav class="tabs">' + "".join(links) + "</nav>"


def render_page(title: str, heading: str, subtitle: str, content: str,
                extra_css: str = "", nav: str = "") -> str:
    """The admin page shell: noindex, no public site chrome.

    `subtitle`, `content` and `nav` are trusted HTML the caller has already
    built and escaped. Shared by the three /admin pages and the digest archive.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>{_esc(title)}</title>
<style>{PAGE_CSS}{extra_css}</style>
</head>
<body>
<header>
  <h1>{_esc(heading)}</h1>
  <div class="ts">{subtitle}</div>
{nav}
</header>
<main>
{content}
</main>
</body>
</html>"""


def _subtitle(generated_at: str = None) -> tuple:
    if generated_at is None:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    return generated_at, f"View only · generated {_esc(generated_at)}"


def render_business_html(model: dict, generated_at: str = None) -> str:
    """/admin — the landing page, and the only one that asks anything of the
    reader: what is blocked on Benedict, how graded tickets turned out, traffic.

    Everything reference-shaped lives on the other tabs. The whole point of the
    split is that this page stays short enough to read in one screen.
    """
    _, subtitle = _subtitle(generated_at)
    return render_page(
        title="treestock admin — business state",
        heading="treestock admin · business state",
        subtitle=subtitle,
        content=_business_section(model.get("business")),
        nav=render_nav("/admin"),
    )


def render_subscribers_html(model: dict, generated_at: str = None) -> str:
    """/admin/subscribers — who is subscribed, to what, and what they watch."""
    _, subtitle = _subtitle(generated_at)
    parts = [
        _cards(model["totals"]),
        '<div class="grid3">',
        _count_table("By state", model["by_state"]),
        _count_table("By frequency", model["by_frequency"]),
        _count_table("By category", model["by_category"],
                     label_fn=lambda c: CATEGORY_SHORT.get(c, c)),
        "</div>",
        _subscriber_table(model["subscribers"]),
        _watch_only_table(model["watch_only"]),
        _pending_table(model["pending"]),
        _top_varieties_table(model["top_varieties"][:25]),
    ]
    return render_page(
        title="treestock admin — subscribers",
        heading="treestock admin · subscribers",
        subtitle=subtitle,
        content="\n".join(parts),
        nav=render_nav("/admin/subscribers"),
    )


def render_nurseries_html(model: dict, generated_at: str = None) -> str:
    """/admin/nurseries — the relationship register plus the scraper's view of
    the same nurseries: health grid and the unclassified-products report. They
    belong together; both answer "what is going on with nursery X".
    """
    _, subtitle = _subtitle(generated_at)
    parts = [
        _nursery_section(model.get("nurseries")),
        _health_section(model.get("health")),
        _needs_review_section(model.get("needs_review")),
    ]
    return render_page(
        title="treestock admin — nurseries",
        heading="treestock admin · nurseries",
        subtitle=subtitle,
        content="\n".join(parts),
        nav=render_nav("/admin/nurseries"),
    )


def _variety_alarm(model: dict) -> str:
    """The two things on this page that mean something is wrong right now."""
    parts = []
    denied = model.get("denied_but_watched") or []
    if denied:
        rows = ", ".join(_esc(s) for s in denied)
        parts.append(
            f'<section><h2>Denied but watched</h2>'
            f'<p class="warn">{len(denied)} slug(s) are on the deny list AND have '
            f'a live watcher: {rows}. A denied slug loses its page, so those '
            f'alerts now link to a 404. Remove the deny, or migrate the watch '
            f'first.</p></section>')
    orphans = model.get("orphan_watches") or []
    if orphans:
        body = "".join(
            f'<tr><td>{_esc(o["slug"])}</td><td class="num">{o["watchers"]}</td></tr>'
            for o in orphans)
        parts.append(
            f'<section><h2>Watched slugs with no page ({len(orphans)})</h2>'
            f'<p class="muted">Each one is an alert whose link 404s. This number '
            f'must not grow across a deploy: that is how a missed slug migration '
            f'shows up before a subscriber finds it.</p>'
            f'<table class="mini"><thead><tr><th>Slug</th><th class="num">Watchers</th>'
            f'</tr></thead><tbody>{body}</tbody></table></section>')
    return "\n".join(parts)


def _variety_overrides_section(overrides: dict) -> str:
    if overrides.get("error"):
        return (f'<section><h2>Override file</h2><p class="warn">'
                f'variety_overrides.json could not be read: '
                f'{_esc(overrides["error"])}. Curation is NOT being applied.'
                f'</p></section>')
    deny = overrides.get("deny") or []
    alias = overrides.get("alias") or {}
    deny_rows = "".join(f"<tr><td>{_esc(s)}</td></tr>" for s in deny) or \
        '<tr><td class="muted">None</td></tr>'
    alias_rows = "".join(
        f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>"
        for k, v in sorted(alias.items())) or \
        '<tr><td colspan="2" class="muted">None</td></tr>'
    return (
        f'<section><h2>Curation in force</h2>'
        f'<p class="muted">From tools/scrapers/variety_overrides.json. Edit it in '
        f'the repo and deploy; this page is read only, so no write endpoint has '
        f'to sit behind Cloudflare Access.</p>'
        f'<div class="grid3">'
        f'<div><h3>Denied ({len(deny)})</h3><table class="mini"><tbody>{deny_rows}'
        f'</tbody></table></div>'
        f'<div><h3>Aliased ({len(alias)})</h3><table class="mini"><thead><tr>'
        f'<th>From</th><th>To</th></tr></thead><tbody>{alias_rows}</tbody></table>'
        f'</div></div></section>')


def _sibling_review_section(siblings) -> str:
    """The queue that needs a person.

    Deliberately NOT auto-folded. avocado-hass-lamb is Lamb Hass, a different
    cultivar; guava-thai-pink, orange-valencia-delta and
    finger-lime-green-sapphire are all real. Prefix matching finds candidates;
    only someone who knows the plants can adjudicate them.
    """
    if not siblings:
        return ('<section><h2>Sibling review queue</h2>'
                '<p class="muted">Nothing to adjudicate.</p></section>')
    rows = []
    for group in siblings:
        kids = ", ".join(
            f'{_esc(s["slug"])}{" (" + str(s["watchers"]) + " watching)" if s["watchers"] else ""}'
            for s in group["siblings"])
        base_w = (f' ({group["base_watchers"]} watching)'
                  if group["base_watchers"] else "")
        rows.append(f'<tr><td>{_esc(group["base"])}{base_w}</td><td>{kids}</td></tr>')
    # Copy-pasteable starting point for the alias map. Every line is a
    # SUGGESTION to accept or delete, never something applied on its own.
    suggestion = ",\n".join(
        f'    {json.dumps(s["slug"])}: {json.dumps(group["base"])}'
        for group in siblings for s in group["siblings"])
    return (
        f'<section><h2>Sibling review queue ({len(siblings)} base slugs)</h2>'
        f'<p class="muted">Longer slugs sharing a base. Some are the same '
        f'cultivar fragmented across listings; some are genuinely different '
        f'plants (avocado-hass-lamb is Lamb Hass). A human decides, which is '
        f'why nothing here is applied automatically.</p>'
        f'<table class="mini"><thead><tr><th>Base</th><th>Longer siblings</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table>'
        f'<h3>Starting point for the alias map</h3>'
        f'<p class="muted">Paste into variety_overrides.json and DELETE every '
        f'line that names a different plant. Then run check_watched_slugs.py '
        f'--baseline 2: the number of watched slugs with no page must not grow, '
        f'which is how a folded slug with a live watcher shows up before a '
        f'subscriber finds a 404. Do NOT run migrate_variety_watch_slugs.py; it '
        f're-parses stored titles that are now canonical display titles and will '
        f'move a live watch onto a slug that has no page.</p>'
        f'<pre class="code">"alias": {{\n{_esc(suggestion)}\n}}</pre></section>')


def render_variety_review_html(model: dict, generated_at: str = None) -> str:
    """/admin/varieties/review — everything that needs a person.

    The three blocks that used to be /admin/varieties, moved here unchanged when
    that page became the inventory (DAL-283). Two different jobs: the inventory
    answers "what are my variety pages" and asks nothing, this one is the queue.
    """
    _, subtitle = _subtitle(generated_at)
    v = model.get("varieties") or {}
    parts = [
        f'<p class="muted">{v.get("index_size", 0)} variety pages in the '
        f'canonical index. <a href="/admin/varieties">Back to the inventory</a>.</p>',
        _variety_alarm(v),
        _variety_overrides_section(v.get("overrides") or {}),
        _sibling_review_section(v.get("siblings") or []),
    ]
    return render_page(
        title="treestock admin — variety review",
        heading="treestock admin · variety review",
        subtitle=subtitle,
        content="\n".join(p for p in parts if p),
        extra_css=(
            "  pre.code { background:#f8fafc; border:1px solid #e2e8f0; "
            "border-radius:6px; padding:12px; overflow-x:auto; font-size:0.78rem; }\n"
            "  .warn { color:#b91c1c; }\n"),
        nav=render_nav("/admin/varieties/review"),
    )


# -- the inventory page ------------------------------------------------------

_STATE_LABEL = {LIVE: "live", REDIRECT: "redirect",
                TOMBSTONE: "tombstone", RETIRED: "retired"}


def _inventory_states(inv: dict) -> str:
    """The state strip. Redirects and tombstones as first-class things.

    They are the point of reading the ledger at all: everywhere else on the site
    a redirected page shows up as an absence, which is indistinguishable from a
    page that was never built.
    """
    counts = inv.get("counts") or {}
    cells = []
    for state in (LIVE, REDIRECT, TOMBSTONE, RETIRED):
        n = counts.get(state, 0)
        if state == RETIRED and not n:
            continue  # only worth a slot once one exists
        cells.append(
            f'<div class="card"><div class="card-num st-{state}">{n:,}</div>'
            f'<div class="card-label">{_STATE_LABEL[state]}</div></div>')
    return f'<div class="cards">{"".join(cells)}</div>'


def _inventory_attention(inv: dict) -> str:
    """The six queues, each a filter rather than a number to admire."""
    tiles = []
    for q in inv.get("attention") or []:
        tiles.append(
            f'<button type="button" class="qtile" data-flag="{_esc(q["key"])}" '
            f'title="{_esc(q["note"])}">'
            f'<span class="qnum">{q["count"]:,}</span>'
            f'<span class="qlabel">{_esc(q["label"])}</span></button>')
    return (
        f'<section><h2>Attention</h2>'
        f'<div class="qtiles">{"".join(tiles)}</div>'
        f'<p class="small muted">Click a tile to list the pages it counted. '
        f'Nothing here is an error on its own: 59% of the catalogue being one '
        f'nursery selling one product is a fact about the market, not a bug.</p>'
        f'</section>')


def _inventory_controls(inv: dict) -> str:
    options = "".join(
        f'<option value="{_esc(r["name"])}">{_esc(r["name"])} ({r["varieties"]})</option>'
        for r in sorted(inv.get("species") or [], key=lambda r: r["name"]))
    states = "".join(
        f'<option value="{s}">{_STATE_LABEL[s]}</option>'
        for s in (LIVE, REDIRECT, TOMBSTONE, RETIRED))
    return (
        f'<section class="controls" hidden id="controls">'
        f'<input type="search" id="q" placeholder="Search slugs, e.g. hass" '
        f'autocomplete="off" spellcheck="false">'
        f'<select id="fspecies"><option value="">All species</option>{options}</select>'
        f'<select id="fstate"><option value="">Any state</option>{states}</select>'
        f'<button type="button" id="clear" hidden>Clear</button>'
        f'</section>')


def _inventory_species_table(inv: dict) -> str:
    """Server-rendered, so the page is useful before any JS runs.

    112 rows of aggregate, not 2,767 rows of detail: the detail arrives in the
    payload and expands in place.
    """
    rows = []
    for r in inv.get("species") or []:
        extra = []
        if r["redirect"]:
            extra.append(f'{r["redirect"]} redirect')
        if r["tombstone"]:
            extra.append(f'{r["tombstone"]} tombstone')
        rows.append(
            f'<tr class="sprow" data-species="{_esc(r["name"])}" tabindex="0">'
            f'<td class="sname">{_esc(r["name"])}</td>'
            f'<td class="num">{r["varieties"]}</td>'
            f'<td class="num">{r["in_stock"]}</td>'
            f'<td class="num">{r["single"] or ""}</td>'
            f'<td class="num">{r["never"] or ""}</td>'
            f'<td class="num">{r["noisy"] or ""}</td>'
            f'<td class="small muted">{_esc(", ".join(extra))}</td></tr>'
            f'<tr class="drill" hidden><td colspan="7"></td></tr>')
    if not rows:
        rows = ['<tr><td colspan="7" class="muted">No pages in the ledger.</td></tr>']
    return (
        f'<section id="species-section">'
        f'<h2>Species ({inv.get("species_count", 0)})</h2>'
        f'<div class="tscroll"><table id="species"><thead><tr><th>Species</th>'
        f'<th class="num">Varieties</th><th class="num">In stock</th>'
        f'<th class="num">Single</th><th class="num">Never</th>'
        f'<th class="num">Noisy</th><th>Other states</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        f'<p class="small muted"><noscript>Per-variety detail and search need '
        f'JavaScript; the counts above do not.</noscript></p></section>')


def _inventory_missing(inv: dict) -> str:
    reason = (f' It could not be read: {_esc(inv["error"])}.'
              if inv.get("error") else " It does not exist yet.")
    return (
        f'<section><h2>No page ledger</h2><p class="warn">Expected the variety '
        f'ledger at <code>{_esc(inv.get("path", ""))}</code>.{reason} Everything '
        f'on this page comes from that file, so there is nothing to show. The '
        f'nightly writes it; <a href="/admin/varieties/review">the review '
        f'queue</a> does not depend on it and still works.</p></section>')


INVENTORY_CSS = """
  /* Seven columns of counts do not fit a phone, and Benedict triages on one.
     The table scrolls inside its own box rather than pushing the page sideways. */
  .tscroll { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  .tscroll table { width:auto; min-width:100%; }
  .tscroll th, .tscroll td.num, .vt td:nth-child(2), .vt td:nth-child(5) {
    white-space:nowrap; }
  .qtiles { display:flex; flex-wrap:wrap; gap:10px; }
  .qtile { flex:1 1 150px; background:#fff; border:1px solid #e5e7eb;
    border-radius:10px; padding:12px 10px; text-align:center; cursor:pointer;
    font:inherit; color:inherit; }
  .qtile:hover, .qtile:focus { border-color:#065f46; }
  .qtile.on { border-color:#065f46; background:#ecfdf5; }
  .qnum { display:block; font-size:1.4rem; font-weight:700; color:#065f46; }
  .qlabel { display:block; font-size:0.75rem; color:#6b7280; margin-top:2px; }
  .card-num.st-redirect { color:#1d4ed8; }
  .card-num.st-tombstone { color:#6b7280; }
  .card-num.st-retired { color:#b91c1c; }
  .controls { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
  .controls input, .controls select, .controls button { font:inherit;
    font-size:0.85rem; padding:7px 10px; border:1px solid #d1d5db;
    border-radius:8px; background:#fff; color:#111827; }
  .controls input { flex:1 1 240px; }
  .controls button { cursor:pointer; }
  tr.sprow { cursor:pointer; }
  tr.sprow:hover td, tr.sprow:focus td { background:#f0fdf4; }
  tr.sprow.open td.sname { font-weight:700; }
  td.sname::before { content:"\\25B8 "; color:#9ca3af; }
  tr.sprow.open td.sname::before { content:"\\25BE "; }
  tr.drill > td { background:#f9fafb; padding:0 10px 10px; }
  table.vt { margin-top:6px; font-size:0.8rem; }
  .vstate { font-weight:600; }
  .vstate.redirect { color:#1d4ed8; }
  .vstate.tombstone { color:#6b7280; }
  .vstate.retired { color:#b91c1c; }
  .fl { display:inline-block; margin-left:4px; padding:1px 6px; border-radius:999px;
    font-size:0.68rem; background:#fef3c7; color:#92400e; }
  .twin { font-size:0.72rem; color:#92400e; margin-top:2px; }
  .warn { color:#b91c1c; }
  code { background:#f3f4f6; padding:1px 4px; border-radius:4px; }
"""

# Everything below runs only once the payload lands. The species counts are
# already on the page by then, which is the whole reason they are rendered
# server-side: a failed fetch costs the drill-down and the search, not the page.
INVENTORY_JS = """
(function () {
  var URL = '/admin/varieties.json';
  var data = null, open = null, filter = null;
  var q = document.getElementById('q');
  var fsp = document.getElementById('fspecies');
  var fst = document.getElementById('fstate');
  var clear = document.getElementById('clear');
  var controls = document.getElementById('controls');
  var sect = document.getElementById('species-section');
  var results = document.getElementById('results');

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c];
    });
  }

  function row(r) {
    return {
      slug: r[0], species: data.species[r[1]], state: data.states[r[2]],
      nurseries: r[3], inStock: !!r[4], firstSeen: r[5] ? '20' + r[5] : '',
      watchers: r[6], flags: r[7], target: r[8], twin: r[9]
    };
  }

  function hasFlag(r, key) {
    var i = data.flags.indexOf(key);
    return i >= 0 && (r[7] & (1 << i)) !== 0;
  }

  function flagPills(v, bits) {
    var out = '';
    data.flags.forEach(function (name, i) {
      if (name === 'oos' || name === 'lonely') return;   // shown by the columns
      if (bits & (1 << i)) out += '<span class="fl">' + esc(name) + '</span>';
    });
    return out;
  }

  function table(rows) {
    if (!rows.length) return '<p class="muted small">Nothing matches.</p>';
    var out = '<div class="tscroll"><table class="mini vt"><thead><tr><th>Slug</th><th>State</th>' +
      '<th class="num">Nurseries</th><th>In stock</th><th>First seen</th>' +
      '<th class="num">Watch</th></tr></thead><tbody>';
    rows.forEach(function (raw) {
      var v = row(raw);
      var state = v.state === 'redirect' && v.target
        ? 'redirect &rarr; ' + esc(v.target) : esc(v.state);
      var twin = v.twin
        ? '<div class="twin">shadows <a href="https://treestock.com.au/variety/' +
          encodeURIComponent(v.twin) + '.html" target="_blank" rel="noopener">' +
          esc(v.twin) + '</a></div>'
        : '';
      out += '<tr><td><a href="https://treestock.com.au/variety/' +
        encodeURIComponent(v.slug) + '.html" target="_blank" rel="noopener">' +
        esc(v.slug) + '</a>' + flagPills(v, v.flags) + twin + '</td>' +
        '<td class="vstate ' + esc(v.state) + '">' + state + '</td>' +
        '<td class="num">' + (v.nurseries || '') + '</td>' +
        '<td>' + (v.state === 'live' ? (v.inStock ? 'yes' : 'no') : '') + '</td>' +
        '<td>' + esc(v.firstSeen) + '</td>' +
        '<td class="num">' + (v.watchers || '\\u00b7') + '</td></tr>';
    });
    return out + '</tbody></table></div>';
  }

  function bySlug(a, b) { return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0; }

  function matching() {
    var term = (q.value || '').trim().toLowerCase();
    var sp = fsp.value, st = fst.value;
    return data.rows.filter(function (r) {
      if (filter && !hasFlag(r, filter)) return false;
      if (sp && data.species[r[1]] !== sp) return false;
      if (st && data.states[r[2]] !== st) return false;
      if (term && r[0].indexOf(term) === -1) return false;
      return true;
    }).sort(bySlug);
  }

  function searching() {
    return !!((q.value || '').trim() || fsp.value || fst.value || filter);
  }

  function heading(n) {
    var bits = [];
    if (filter) bits.push(data.flagLabels[data.flags.indexOf(filter)] || filter);
    if (fsp.value) bits.push(fsp.value);
    if (fst.value) bits.push(fst.value);
    var term = (q.value || '').trim();
    if (term) bits.push('"' + term + '"');
    return n.toLocaleString() + ' page' + (n === 1 ? '' : 's') +
      (bits.length ? ' \\u00b7 ' + esc(bits.join(' \\u00b7 ')) : '');
  }

  function render() {
    if (!searching()) {
      results.hidden = true;
      sect.hidden = false;
      clear.hidden = true;
      return;
    }
    var rows = matching();
    results.innerHTML = '<h2>' + heading(rows.length) + '</h2>' +
      table(rows.slice(0, 400)) +
      (rows.length > 400 ? '<p class="small muted">Showing the first 400 of ' +
        rows.length.toLocaleString() + '. Narrow the search to see the rest.</p>' : '');
    results.hidden = false;
    sect.hidden = true;
    clear.hidden = false;
  }

  function drill(tr) {
    var name = tr.getAttribute('data-species');
    var body = tr.nextElementSibling;
    if (open === tr) {
      open.classList.remove('open');
      body.hidden = true;
      open = null;
      return;
    }
    if (open) {
      open.classList.remove('open');
      open.nextElementSibling.hidden = true;
    }
    var rows = data.rows.filter(function (r) { return data.species[r[1]] === name; })
      .sort(bySlug);
    body.firstElementChild.innerHTML = table(rows);
    body.hidden = false;
    tr.classList.add('open');
    open = tr;
  }

  fetch(URL, {credentials: 'same-origin'})
    .then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function (payload) {
      data = payload;
      controls.hidden = false;
      [q, fsp, fst].forEach(function (el) {
        el.addEventListener('input', function () { render(); });
      });
      clear.addEventListener('click', function () {
        q.value = ''; fsp.value = ''; fst.value = ''; filter = null;
        Array.prototype.forEach.call(document.querySelectorAll('.qtile.on'),
          function (b) { b.classList.remove('on'); });
        render();
      });
      Array.prototype.forEach.call(document.querySelectorAll('.qtile'),
        function (b) {
          b.addEventListener('click', function () {
            var key = b.getAttribute('data-flag');
            filter = filter === key ? null : key;
            Array.prototype.forEach.call(document.querySelectorAll('.qtile'),
              function (o) { o.classList.toggle('on', o === b && filter); });
            render();
          });
        });
      Array.prototype.forEach.call(document.querySelectorAll('tr.sprow'),
        function (tr) {
          tr.addEventListener('click', function () { drill(tr); });
          tr.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); drill(tr); }
          });
        });
    })
    .catch(function (e) {
      results.innerHTML = '<p class="warn">Could not load the variety payload (' +
        esc(e.message) + '). The species counts above are still correct; ' +
        'search and drill-down need it.</p>';
      results.hidden = false;
    });
}());
"""


def render_varieties_html(model: dict, generated_at: str = None) -> str:
    """/admin/varieties — what the catalogue IS. No decisions on this page.

    Reads the page ledger, which until DAL-283 nothing did. Everything that
    needs a person moved to /admin/varieties/review.
    """
    _, subtitle = _subtitle(generated_at)
    inv = model.get("inventory") or {}
    v = model.get("varieties") or {}

    if not inv.get("present"):
        content = _inventory_missing(inv)
        return render_page(
            title="treestock admin — varieties",
            heading="treestock admin · varieties",
            subtitle=subtitle, content=content,
            extra_css=INVENTORY_CSS, nav=render_nav("/admin/varieties"))

    stale = ""
    updated = inv.get("updated") or ""
    if updated and updated < date.today().isoformat():
        stale = (f' <span class="warn">Ledger last written {_esc(updated)}, '
                 f'so tonight\'s build has not run yet.</span>')

    queue = len(v.get("siblings") or []) + len(v.get("orphan_watches") or [])
    parts = [
        _inventory_states(inv),
        f'<p class="small muted">{inv.get("total", 0):,} pages in the ledger, '
        f'{inv.get("species_count", 0)} species with a live page. '
        f'<a href="/admin/varieties/review">Review queue</a> ({queue}).{stale}</p>',
        _inventory_attention(inv),
        _inventory_controls(inv),
        '<section id="results" hidden></section>',
        _inventory_species_table(inv),
        f'<script>{INVENTORY_JS}</script>',
    ]
    return render_page(
        title="treestock admin — varieties",
        heading="treestock admin · varieties",
        subtitle=subtitle,
        content="\n".join(parts),
        extra_css=INVENTORY_CSS,
        nav=render_nav("/admin/varieties"),
    )


# path -> renderer, so subscribe_server routes without a chain of ifs.
ADMIN_RENDERERS = {
    "/admin": render_business_html,
    "/admin/subscribers": render_subscribers_html,
    "/admin/nurseries": render_nurseries_html,
    "/admin/varieties": render_varieties_html,
    "/admin/varieties/review": render_variety_review_html,
}

# path -> builder, for the admin surfaces that answer JSON rather than HTML.
# Same Cloudflare Access gate, same read-only posture; separate from
# ADMIN_RENDERERS so the server cannot send one as the other.
ADMIN_JSON = {
    "/admin/varieties.json": lambda model: build_varieties_payload(
        model.get("inventory") or {}),
}


if __name__ == "__main__":
    # Local smoke test, and the only way to see /admin at all: the live pages sit
    # behind Cloudflare Access, so curl gets a login redirect rather than the
    # page. Render it here instead.
    #   python3 admin_view.py [data_dir] [/admin/varieties|/admin/varieties.json|...]
    import sys
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR
    path = sys.argv[2] if len(sys.argv) > 2 else "/admin"
    if path in ADMIN_JSON:
        print(json.dumps(ADMIN_JSON[path](load_admin_data(data_dir)), indent=1))
        sys.exit(0)
    render = ADMIN_RENDERERS.get(path)
    if render is None:
        sys.exit(f"unknown admin page {path!r}; try one of "
                 f"{list(ADMIN_RENDERERS) + list(ADMIN_JSON)}")
    print(render(load_admin_data(data_dir)))
