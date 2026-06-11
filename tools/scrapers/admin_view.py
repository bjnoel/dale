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
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("/opt/dale/data")
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
PENDING_FILE = DATA_DIR / "pending_subscribers.json"
VARIETY_WATCHES_DB = DATA_DIR / "variety_watches.db"

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

    return build_admin_model(subscribers, pending, watches_rows)


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
