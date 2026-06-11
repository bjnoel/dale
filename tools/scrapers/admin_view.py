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
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from stocklib.scrape_health import HEALTH_DIRNAME, read_records

DATA_DIR = Path("/opt/dale/data")
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
PENDING_FILE = DATA_DIR / "pending_subscribers.json"
VARIETY_WATCHES_DB = DATA_DIR / "variety_watches.db"

HEALTH_DAYS = 14
MAX_RECENT_ERRORS = 15

SITE_URL = "https://treestock.com.au"

VALID_CATEGORIES = ("new_products", "price_drops", "back_in_stock")
VALID_FREQUENCIES = ("daily", "weekly", "off")
STATES = ("ALL", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT")

CATEGORY_SHORT = {
    "new_products": "new",
    "price_drops": "drops",
    "back_in_stock": "restock",
}


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
    return model


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


def render_admin_html(model: dict, generated_at: str = None) -> str:
    """Standalone, view-only HTML page. No public site chrome, noindex."""
    if generated_at is None:
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

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
        _health_section(model.get("health")),
        _needs_review_section(model.get("needs_review")),
    ]
    content = "\n".join(parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>treestock admin — subscribers</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    margin:0; background:#f9fafb; color:#111827; }}
  header {{ background:#065f46; color:#fff; padding:16px 24px; }}
  header h1 {{ margin:0; font-size:1.1rem; }}
  header .ts {{ font-size:0.8rem; opacity:0.85; }}
  main {{ max-width:1100px; margin:0 auto; padding:24px 16px 64px; }}
  .cards {{ display:flex; flex-wrap:wrap; gap:12px; margin:0 0 24px; }}
  .card {{ flex:1 1 150px; background:#fff; border:1px solid #e5e7eb;
    border-radius:10px; padding:16px; text-align:center; }}
  .card-num {{ font-size:1.8rem; font-weight:700; color:#065f46; }}
  .card-label {{ font-size:0.8rem; color:#6b7280; margin-top:4px; }}
  section {{ margin:0 0 28px; }}
  h2 {{ font-size:1rem; color:#374151; margin:0 0 10px; }}
  table {{ width:100%; border-collapse:collapse; background:#fff;
    border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; font-size:0.85rem; }}
  th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid #f3f4f6;
    vertical-align:top; }}
  th {{ background:#f3f4f6; color:#374151; font-weight:600; }}
  td.num, th.num {{ text-align:right; }}
  tr:last-child td {{ border-bottom:none; }}
  .mini {{ max-width:100%; }}
  .muted {{ color:#9ca3af; }}
  .grid3 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; }}
  .grid2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
  .grid3 section, .grid2 section {{ margin:0; }}
  h3 {{ font-size:0.9rem; color:#374151; margin:14px 0 8px; }}
  table.health th.hday {{ font-size:0.7rem; text-align:center; padding:6px 2px; }}
  td.hcell {{ width:18px; padding:0; }}
  span.hcell {{ display:inline-block; width:12px; height:12px; border-radius:2px;
    vertical-align:-2px; }}
  .hcell.ok {{ background:#34d399; }}
  .hcell.fail {{ background:#ef4444; }}
  .hcell.zero {{ background:#fbbf24; }}
  .hcell.none {{ background:#e5e7eb; }}
  .legend {{ font-size:0.8rem; margin:0 0 10px; }}
</style>
</head>
<body>
<header>
  <h1>treestock admin · subscribers</h1>
  <div class="ts">View only · generated {_esc(generated_at)}</div>
</header>
<main>
{content}
</main>
</body>
</html>"""


if __name__ == "__main__":
    # Local smoke test: render from whatever data dir is passed (or the default).
    import sys
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR
    print(render_admin_html(load_admin_data(data_dir)))
