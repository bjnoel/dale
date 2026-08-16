#!/usr/bin/env python3
"""
Send per-variety alerts to subscribers watching specific cultivars.

Two triggers, compared against yesterday's data:

  restock     the variety had 0 in-stock listings anywhere yesterday and has
              at least one today. Deliberately measured at VARIETY level across
              all nurseries, not per variant: a collector cares that the thing
              is buyable somewhere, not that one nursery's Large flipped while
              its Small was available the whole time.

  price drop  a single variant of a watched variety fell by at least
              MIN_DROP_PCT and MIN_DROP_ABS while staying in stock. Measured at
              VARIANT level via stocklib.changes, which is mandatory: comparing
              product-level min_price across variants reports a different pot
              size as a price change (treestock rule 3).

At most one email per person per variety per day. If both fire, RESTOCK WINS,
and the restock email carries the old price as context, so a price drop never
costs a second send.

Repeat alerts are suppressed for COOLDOWN_DAYS. Before that existed, stock
flickering 0 -> >0 -> 0 -> >0 re-alerted every time (tamarillo-red went out 8
times to the same two people).

Runs after each daily scrape, after send_species_alerts.py.

Usage:
    python3 send_variety_alerts.py <data-dir>
    python3 send_variety_alerts.py <data-dir> --dry-run
    python3 send_variety_alerts.py <data-dir> --date 2026-03-14
    python3 send_variety_alerts.py <data-dir> --redirect-to me@example.com

--redirect-to sends every alert to the given address (with the original
recipient noted in the subject and a banner injected into the body) and
does NOT record sends, so a real run later can still fire normally. Useful
for previewing what would have gone out.

Australian Spam Act compliance:
    - Every email includes a working unsubscribe link
    - Unsubscribe requests are honoured via subscribe_server.py
"""

import hashlib
import hmac
import html as _html
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
VARIETY_WATCHES_DB = DATA_DIR / "variety_watches.db"

# Don't re-alert the same person about the same variety and trigger inside this
# window. Stock that flickers in and out otherwise re-fires indefinitely.
COOLDOWN_DAYS = 30

# A price drop has to clear BOTH floors to be worth an email. Percent alone
# fires on cheap seedlings moving a couple of dollars; dollars alone fires on
# a $200 tree moving 2%.
MIN_DROP_PCT = 10.0
MIN_DROP_ABS = 5.00

RESTOCK = "restock"
PRICE_DROP = "price_drop"


from stocklib.mailer import (get_resend_api_key, get_unsubscribe_secret,
                             make_unsubscribe_token)
import functools
from stocklib.mailer import send_email as _send_email
send_email = functools.partial(_send_email, user_agent="treestock-variety-alerts/1.0")
SITE_URL = "https://treestock.com.au"
UNSUBSCRIBE_BASE = f"{SITE_URL}/unsubscribe.html"

# Treesmith cross-promo, shown above the unsubscribe footer. Inline styles for
# email clients. No em dashes (treestock copy rule).
TREESMITH_PROMO = (
    '<div style="margin:24px 0 0;padding:16px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px">'
    '<p style="margin:0 0 6px;color:#14532d;font-weight:600;font-size:0.95em">Track your collection with Treesmith</p>'
    '<p style="margin:0 0 10px;color:#166534;font-size:0.85em">'
    'Treesmith is a mobile app for plant collectors. Catalog every tree, log grafts and harvests, '
    'and capture growth photos over time. Built by the same person behind treestock.'
    '</p>'
    f'<a href="{SITE_URL}/treesmith.html?utm_source=treestock&utm_medium=email&utm_campaign=variety-alert" '
    'style="display:inline-block;background:#15803d;color:white;padding:8px 16px;border-radius:6px;'
    'text-decoration:none;font-size:0.85em;font-weight:500">See Treesmith</a>'
    '</div>'
)

from stocklib.classify import is_real_product
from stocklib.snapshots import snapshot_path_for_date
from stocklib.utm import outbound
from stocklib import changes as _changes
from stocklib.fruit_filters import digest_product_filter
from stocklib.variety_index import DEFAULT_INDEX_PATH, get_variety_index


from cultivar_parsing import slugify, parse_cultivar, product_variety_slug  # noqa: E402


def load_nursery_data(data_dir: Path, target_date: str) -> list[dict]:
    """Load products from a specific date's snapshots."""
    products = []
    today = date.today().isoformat()
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        # A missing snapshot means the nursery did not report, not that it sold
        # out. Skipping it here made every watched variety on the other side of
        # the comparison look like a restock (DEC-293).
        source = snapshot_path_for_date(nursery_dir, target_date, today)
        if source is None:
            continue
        try:
            with open(source) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        nursery_key = nursery_dir.name
        nursery_name = data.get("nursery_name", nursery_key)
        for p in data.get("products", []):
            title = p.get("title", "")
            title_lower = title.lower()
            if not is_real_product(title):
                continue
            available = p.get("any_available", p.get("available", False))
            variants = p.get("variants", [])
            min_price = p.get("min_price")
            if min_price is None and variants:
                avail_prices = [float(v["price"]) for v in variants if v.get("price") and v.get("available", True)]
                all_prices = [float(v["price"]) for v in variants if v.get("price")]
                min_price = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)
            elif min_price is None:
                min_price = p.get("price")
            products.append({
                "title": title,
                "url": p.get("url", ""),
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "price": round(float(min_price), 2) if min_price else None,
                "available": bool(available),
            })
    return products


def in_stock_by_variety_slug(products: list[dict]) -> dict[str, list[dict]]:
    """Return {variety_slug: [in-stock products]} for all cultivar-named products."""
    by_slug: dict[str, list[dict]] = {}
    for p in products:
        if not p["available"]:
            continue
        v_slug = product_variety_slug(p["title"])
        if not v_slug:
            continue
        by_slug.setdefault(v_slug, []).append(p)
    return by_slug


def load_watches() -> list[dict]:
    """Load all watches from SQLite DB."""
    if not VARIETY_WATCHES_DB.exists():
        return []
    con = sqlite3.connect(VARIETY_WATCHES_DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT email, variety_slug, species_slug, variety_title FROM watches").fetchall()
    con.close()
    return [dict(r) for r in rows]


# Canonical slug -> title map, written by build_variety_pages.py. Loaded on
# first use; tests replace it directly.
_VARIETY_INDEX = None


def variety_index():
    global _VARIETY_INDEX
    if _VARIETY_INDEX is None:
        _VARIETY_INDEX = get_variety_index(DEFAULT_INDEX_PATH)
    return _VARIETY_INDEX


def display_title(slug: str, watchers: dict) -> str:
    """The name to put in front of a watcher for `slug`.

    Canonical title from the index. This used to be
    `watchers[slug][0]["variety_title"]`, i.e. whatever string the FIRST person
    to watch this slug happened to POST, interpolated into the subject and body
    of mail sent to everyone else watching it.

    The stored title is still the fallback, because ~12 watched slugs have
    dropped out of live stock and so have no page and no index entry, and those
    people should keep getting a recognisable name rather than nothing. That
    fallback is exactly why every render site escapes.
    """
    stored = ""
    rows = watchers.get(slug) or []
    if rows:
        stored = rows[0].get("variety_title") or ""
    return variety_index().display_title(slug, stored)


def subject_safe(title: str) -> str:
    """Flatten a title for use in a subject line.

    Resend takes the subject as a JSON field, so a newline cannot inject a
    header, but it can still produce a subject that renders as junk. Collapse
    whitespace and drop control characters.
    """
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", title or "")).strip()


def ensure_schema(con: sqlite3.Connection) -> None:
    """Add the alert_type column to `sends` if this DB predates price alerts.

    Named alert_type and not `trigger`: TRIGGER is a SQLite keyword and would
    need quoting at every use site. Existing rows are all restocks, which is
    what the DEFAULT backfills them to.
    """
    cols = {r[1] for r in con.execute("PRAGMA table_info(sends)")}
    if "alert_type" not in cols:
        con.execute(
            f"ALTER TABLE sends ADD COLUMN alert_type TEXT NOT NULL DEFAULT '{RESTOCK}'"
        )
        con.commit()


def last_sent_map() -> dict[tuple[str, str, str], str]:
    """Return {(email, variety_slug, alert_type): most recent sent_at}.

    Replaces the old already-sent-today lookup, which only ever suppressed a
    duplicate within a single day and so let flickering stock re-alert forever.
    """
    if not VARIETY_WATCHES_DB.exists():
        return {}
    con = sqlite3.connect(VARIETY_WATCHES_DB)
    ensure_schema(con)
    rows = con.execute(
        "SELECT email, variety_slug, alert_type, MAX(sent_at) FROM sends "
        "GROUP BY email, variety_slug, alert_type"
    ).fetchall()
    con.close()
    return {(r[0], r[1], r[2]): r[3] for r in rows}


def in_cooldown(last_sent: dict, email: str, variety_slug: str,
                alert_type: str, target_date: str) -> bool:
    """True if this exact alert went out within COOLDOWN_DAYS of target_date."""
    previous = last_sent.get((email, variety_slug, alert_type))
    if not previous:
        return False
    try:
        gap = date.fromisoformat(target_date) - date.fromisoformat(previous[:10])
    except ValueError:
        return False
    return gap.days < COOLDOWN_DAYS


def sent_same_day(last_sent: dict, email: str, variety_slug: str,
                  target_date: str) -> bool:
    """True if this person already got ANY alert about this variety today.
    One email per person per variety per day, whichever trigger won."""
    return any(
        last_sent.get((email, variety_slug, t)) == target_date
        for t in (RESTOCK, PRICE_DROP)
    )


def record_send(email: str, variety_slug: str, target_date: str,
                alert_type: str = RESTOCK):
    """Record a send in the SQLite sends table."""
    con = sqlite3.connect(VARIETY_WATCHES_DB)
    ensure_schema(con)
    con.execute(
        "INSERT OR IGNORE INTO sends (email, variety_slug, sent_at, alert_type) "
        "VALUES (?, ?, ?, ?)",
        (email, variety_slug, target_date, alert_type),
    )
    con.commit()
    con.close()


def qualifying_drop(old_price, new_price) -> bool:
    """True if a variant's price fell far enough to be worth an email.

    Both floors must clear. MIN_DROP_PCT alone would fire on a $12 seedling
    losing $1.50; MIN_DROP_ABS alone would fire on a $200 tree losing 2.5%.
    """
    try:
        old_price = float(old_price)
        new_price = float(new_price)
    except (TypeError, ValueError):
        return False
    if old_price <= 0 or new_price >= old_price:
        return False
    drop = old_price - new_price
    return drop >= MIN_DROP_ABS and (drop / old_price) * 100 >= MIN_DROP_PCT


def price_drops_by_variety(data_dir: Path, target_date: str,
                           watched_slugs: set[str]) -> dict[str, list[dict]]:
    """Return {variety_slug: [dropped variant records]} for watched varieties.

    Runs the shared variant-level comparison engine (stocklib.changes) over
    every nursery, then maps each dropped variant back to its cultivar. The
    comparison MUST stay at variant level (treestock rule 3); it is only the
    grouping afterwards that is per-variety.

    Slugs from the raw product_title rather than the variant display title,
    because the display title carries a size suffix that can change the slug.
    """
    all_changes, _ = _changes.load_all_changes(
        data_dir, target_date, product_filter=digest_product_filter)

    nursery_names = {}
    by_variety: dict[str, list[dict]] = {}
    for nursery_key, changes in all_changes.items():
        for item in changes.get("price_drops", []):
            if not qualifying_drop(item.get("old_price"), item.get("new_price")):
                continue
            source_title = item.get("product_title") or item.get("title", "")
            v_slug = product_variety_slug(source_title)
            if not v_slug or v_slug not in watched_slugs:
                continue
            if nursery_key not in nursery_names:
                nursery_names[nursery_key] = _nursery_display_name(data_dir, nursery_key)
            by_variety.setdefault(v_slug, []).append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "nursery_key": nursery_key,
                "nursery_name": nursery_names[nursery_key],
                "price": round(float(item["new_price"]), 2),
                "old_price": round(float(item["old_price"]), 2),
                "available": True,
            })
    return by_variety


def _nursery_display_name(data_dir: Path, nursery_key: str) -> str:
    """Read the nursery's own display name from any snapshot it has."""
    nursery_dir = Path(data_dir) / nursery_key
    try:
        for snap in sorted(nursery_dir.glob("*.json"), reverse=True):
            with open(snap) as f:
                name = json.load(f).get("nursery_name")
            if name:
                return name
            break
    except (OSError, json.JSONDecodeError):
        pass
    return nursery_key


def build_variety_alert_email(variety_title: str, variety_slug: str,
                              products: list[dict],
                              alert_type: str = RESTOCK) -> str:
    """Build HTML email body for a per-variety restock or price-drop alert.

    Everything interpolated into the HTML here is escaped. The variety title is
    the one that mattered (it used to be caller-supplied and reached every
    watcher of the slug), but nursery listing titles get the same treatment:
    an unescaped `&` or `<` in a product name is a rendering bug even when
    nobody is being hostile.
    """
    safe_title = _html.escape(variety_title)
    rows = ""
    for p in sorted(products, key=lambda x: x["price"] or 9999):
        price_str = f"${p['price']:.2f}" if p["price"] else "POA"
        # Show the old price whenever we have one. On a restock this is the
        # free context compare_snapshots already worked out; on a price drop it
        # is the whole point of the email.
        old = p.get("old_price")
        if old and p["price"] and old > p["price"]:
            price_str += (
                f' <span style="color:#9ca3af;font-weight:400;text-decoration:line-through">'
                f'${old:.2f}</span>'
            )
        utm_url = outbound(p["url"], "email", campaign="variety-alert")
        rows += f"""
      <tr>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6">
          <a href="{_html.escape(utm_url, quote=True)}" style="color:#15803d;text-decoration:none">{_html.escape(p['title'])}</a>
        </td>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;color:#6b7280;font-size:0.875em">{_html.escape(p['nursery_name'])}</td>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;font-weight:600">{price_str}</td>
      </tr>"""

    if alert_type == PRICE_DROP:
        heading = f"{safe_title} just dropped in price"
        subhead = "A variety you're watching is cheaper than it was yesterday."
    else:
        heading = f"{safe_title} is now available!"
        subhead = "The specific variety you were watching has come back into stock."

    variety_url = f"{SITE_URL}/variety/{urllib.parse.quote(variety_slug)}.html"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;margin:0;padding:24px">
<div style="max-width:600px;margin:0 auto;background:white;border-radius:8px;overflow:hidden;border:1px solid #e5e7eb">

  <div style="background:#14532d;padding:20px 24px">
    <h1 style="color:white;margin:0;font-size:1.1em;font-weight:600">treestock.com.au</h1>
    <p style="color:#86efac;margin:4px 0 0;font-size:0.85em">Australian Nursery Stock Tracker</p>
  </div>

  <div style="padding:24px">
    <h2 style="margin:0 0 8px;color:#14532d;font-size:1.25em">
      {heading}
    </h2>
    <p style="color:#6b7280;margin:0 0 20px;font-size:0.9em">
      {subhead}
    </p>

    <table style="width:100%;border-collapse:collapse;font-size:0.9em">
      <thead>
        <tr style="background:#f9fafb">
          <th style="padding:8px 12px;text-align:left;font-size:0.75em;text-transform:uppercase;color:#9ca3af;font-weight:600;border-bottom:2px solid #e5e7eb">Listing</th>
          <th style="padding:8px 12px;text-align:left;font-size:0.75em;text-transform:uppercase;color:#9ca3af;font-weight:600;border-bottom:2px solid #e5e7eb">Nursery</th>
          <th style="padding:8px 12px;text-align:left;font-size:0.75em;text-transform:uppercase;color:#9ca3af;font-weight:600;border-bottom:2px solid #e5e7eb">Price</th>
        </tr>
      </thead>
      <tbody>{rows}
      </tbody>
    </table>

    <div style="margin-top:20px">
      <a href="{variety_url}" style="display:inline-block;background:#15803d;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:0.9em;font-weight:500">
        View {safe_title} on treestock.com.au
      </a>
    </div>

    <p style="margin-top:16px;font-size:0.8em;color:#9ca3af">
      Prices and availability updated daily. Act fast, nursery stock can sell out quickly.
    </p>

    {TREESMITH_PROMO}
  </div>

</div>
</body>
</html>"""


def inject_preview_banner(html: str, original_email: str) -> str:
    banner = (
        '<div style="background:#fef3c7;border:1px solid #fbbf24;padding:12px 16px;'
        'margin:0 0 16px;border-radius:6px;font-size:0.875em;color:#78350f">'
        f'<strong>PREVIEW</strong> -- this email would have been sent to '
        f'<code>{original_email}</code>. Sends were not recorded.'
        '</div>'
    )
    body_open = html.find("<body")
    if body_open == -1:
        return banner + html
    body_close = html.find(">", body_open)
    return html[:body_close + 1] + banner + html[body_close + 1:]


def inject_unsubscribe(html: str, email: str, token: str,
                       variety_slug: str = "", variety_title: str = "") -> str:
    """Footer with a working opt-out.

    This used to point at /api/unsubscribe and /api/preferences, both of which
    only know about subscribers.json. Almost everyone receiving a variety alert
    is watch-only (83 of 89 at the time of writing), so "Unsubscribe" told them
    "Not found" and kept sending, and "Manage your alerts" 404'd. The links now
    go to the watch system that is actually sending the email.

    /stop-watching.html is a confirm page, not a delete-on-GET link, so a mail
    scanner prefetching the URL cannot silently remove someone's alerts.
    """
    q = urllib.parse.quote
    stop_one = (f"{SITE_URL}/stop-watching.html?email={q(email)}&token={token}"
                f"&variety={q(variety_slug)}&title={q(variety_title)}")
    stop_all = f"{SITE_URL}/stop-watching.html?email={q(email)}&token={token}"
    manage_url = f"{SITE_URL}/api/preferences?email={q(email)}&token={token}"
    one_line = (
        f'<a href="{_html.escape(stop_one, quote=True)}" style="color:#6b7280">'
        f'Stop watching {_html.escape(variety_title)}</a> &middot;\n  '
        if variety_slug else ""
    )
    footer = f"""
<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.75em;color:#9ca3af;text-align:center">
  You're receiving this because you asked to be told about this variety at <a href="{SITE_URL}" style="color:#6b7280">{SITE_URL}</a>.<br>
  {one_line}<a href="{manage_url}" style="color:#6b7280">Manage your alerts</a> &middot;
  <a href="{stop_all}" style="color:#6b7280">Stop all my treestock alerts</a>
</p>
"""
    if "</body>" in html:
        return html.replace("</body>", footer + "</body>", 1)
    return html + footer


def main():
    dry_run = "--dry-run" in sys.argv
    target_date = date.today().isoformat()
    redirect_to = None

    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        target_date = sys.argv[idx + 1]

    if "--redirect-to" in sys.argv:
        idx = sys.argv.index("--redirect-to")
        redirect_to = sys.argv[idx + 1]

    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("Usage: send_variety_alerts.py <data-dir> [--dry-run] [--date YYYY-MM-DD]")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    if not data_dir.exists():
        print(f"ERROR: {data_dir} does not exist", file=sys.stderr)
        sys.exit(1)
    idx_count = len(variety_index())
    if idx_count:
        print(f"Canonical variety titles loaded: {idx_count}")
    else:
        # Not fatal: every alert falls back to its stored title, which is what
        # shipped before the index existed. Loud because a missing index means
        # a variety page build has not run.
        print(f"WARNING: no variety index at {variety_index().path}; "
              f"falling back to stored watch titles", file=sys.stderr)

    mode_tag = ""
    if dry_run:
        mode_tag = " [DRY RUN]"
    elif redirect_to:
        mode_tag = f" [PREVIEW -> {redirect_to}]"
    print(f"send_variety_alerts.py -- {target_date}{mode_tag}")

    # Load all variety watches from SQLite
    watches = load_watches()
    if not watches:
        print("No variety watches found. Nothing to do.")
        return

    # Build {variety_slug: [emails]} lookup
    watchers: dict[str, list[dict]] = {}
    for w in watches:
        watchers.setdefault(w["variety_slug"], []).append(w)

    watched_slugs = set(watchers.keys())
    print(f"Watched varieties: {len(watched_slugs)} distinct slugs, {len(watches)} total watches")

    # Load today's and yesterday's data
    yesterday = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    print(f"Loading today's data ({target_date})...")
    today_products = load_nursery_data(data_dir, target_date)
    print(f"  {len(today_products)} products")
    print(f"Loading yesterday's data ({yesterday})...")
    yesterday_products = load_nursery_data(data_dir, yesterday)
    print(f"  {len(yesterday_products)} products")

    # Group in-stock products by variety slug
    today_by_variety = in_stock_by_variety_slug(today_products)
    yesterday_by_variety = in_stock_by_variety_slug(yesterday_products)

    # Find restocks: variety going from 0 -> >0 anywhere. Variety level on
    # purpose: see the module docstring.
    alerts = []
    restocked_slugs = set()
    for slug in watched_slugs:
        today_count = len(today_by_variety.get(slug, []))
        yesterday_count = len(yesterday_by_variety.get(slug, []))
        if today_count > 0 and yesterday_count == 0:
            variety_title = display_title(slug, watchers)
            restocked_slugs.add(slug)
            alerts.append({
                "slug": slug,
                "alert_type": RESTOCK,
                "variety_title": variety_title,
                "products": today_by_variety[slug],
                "watchers": watchers[slug],
            })
            print(f"  RESTOCK: {variety_title} -- {today_count} listing(s) now in stock (was 0)")

    # Find price drops on watched varieties, variant level (treestock rule 3).
    # A variety that just restocked is skipped: the restock email already
    # carries the old price, so a second email would be the same news twice.
    print("Checking watched varieties for price drops...")
    for slug, dropped in price_drops_by_variety(data_dir, target_date, watched_slugs).items():
        if slug in restocked_slugs:
            print(f"  (price drop on {slug} folded into its restock alert)")
            continue
        variety_title = display_title(slug, watchers)
        alerts.append({
            "slug": slug,
            "alert_type": PRICE_DROP,
            "variety_title": variety_title,
            "products": dropped,
            "watchers": watchers[slug],
        })
        cheapest = min(dropped, key=lambda d: d["price"])
        print(f"  PRICE DROP: {variety_title} -- ${cheapest['old_price']:.2f} "
              f"-> ${cheapest['price']:.2f} at {cheapest['nursery_name']}")

    if not alerts:
        print("No variety restocks or price drops detected. No alerts to send.")
        return

    last_sent = last_sent_map()

    def eligible(watcher_email: str, slug: str, alert_type: str) -> tuple[bool, str]:
        """(send?, why not). One email per person per variety per day, and no
        repeat of the same trigger inside the cooldown."""
        if sent_same_day(last_sent, watcher_email, slug, target_date):
            return False, "already alerted on this variety today"
        if in_cooldown(last_sent, watcher_email, slug, alert_type, target_date):
            return False, f"same alert within {COOLDOWN_DAYS}d"
        return True, ""

    if dry_run:
        for a in alerts:
            print(f"\n  Would send '{a['variety_title']}' {a['alert_type']} alert to:")
            for w in a["watchers"]:
                ok, why = eligible(w["email"], a["slug"], a["alert_type"])
                print(f"    {'' if ok else '[SKIP ' + why + '] '}{w['email']}")
        return

    api_key = get_resend_api_key()
    secret = get_unsubscribe_secret()
    total_sent = 0
    total_failed = 0

    for a in alerts:
        slug = a["slug"]
        alert_type = a["alert_type"]
        variety_title = a["variety_title"]
        products = a["products"]

        recipients = [w for w in a["watchers"]
                      if eligible(w["email"], slug, alert_type)[0]]
        if not recipients:
            print(f"  {variety_title} ({alert_type}): no eligible watchers")
            continue

        subject_title = subject_safe(variety_title)
        if alert_type == PRICE_DROP:
            subject = f"{subject_title} just dropped in price -- treestock.com.au"
        else:
            subject = f"{subject_title} is now available -- treestock.com.au"
        email_html = build_variety_alert_email(variety_title, slug, products, alert_type)

        print(f"\n  Sending '{variety_title}' {alert_type} alert to {len(recipients)} watcher(s)...")
        for w in recipients:
            email = w["email"]
            token = make_unsubscribe_token(email, secret)
            personalised = inject_unsubscribe(email_html, email, token,
                                              variety_slug=slug,
                                              variety_title=variety_title)
            if redirect_to:
                personalised = inject_preview_banner(personalised, email)
                actual_to = redirect_to
                actual_subject = f"[PREVIEW -> {email}] {subject}"
            else:
                actual_to = email
                actual_subject = subject
            success = send_email(api_key, actual_to, actual_subject, personalised)
            if success:
                if not redirect_to:
                    record_send(email, slug, target_date, alert_type)
                    # Keep the in-memory view current so a later alert in this
                    # same run cannot double up on the same person+variety.
                    last_sent[(email, slug, alert_type)] = target_date
                total_sent += 1
            else:
                total_failed += 1

    print(f"\nDone: {total_sent} variety alert(s) sent, {total_failed} failed")
    if total_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
