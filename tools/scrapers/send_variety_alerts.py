#!/usr/bin/env python3
"""
Send per-variety restock alerts to subscribers watching specific cultivars.

Compares today's data against yesterday's to detect when a watched variety
goes from 0-in-stock to >0-in-stock. Sends a targeted email to watchers.

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
RESEND_ENV = SECRETS_DIR / "resend.env"
APP_ENV = SECRETS_DIR / "app.env"

FROM_EMAIL = "alerts@mail.treestock.com.au"
FROM_NAME = "treestock.com.au"
SITE_URL = "https://treestock.com.au"
UNSUBSCRIBE_BASE = f"{SITE_URL}/unsubscribe.html"

NON_PLANT_KEYWORDS = [
    "fertilizer", "fertiliser", "potting mix", "soil mix", "seaweed solution",
    "fish emulsion", "worm castings", "secateurs", "pruning", "garden gloves",
    "plant label", "grafting tape", "grafting knife", "budding tape",
    "grow bag", "terracotta", "saucer", "pest spray", "insecticide", "fungicide",
    "neem oil", "insect killer", "insect control", "white oil", "weed killer",
    "herbicide", "concentrate spray", "shipping", "postage", "freight",
    "delivery charge", "gift card", "gift voucher", "gift certificate",
    "sharp shooter", "searles liquid", "ecofend",
    "ornamental",
    "asparagus",
]


def get_resend_api_key() -> str:
    with open(RESEND_ENV) as f:
        for line in f:
            line = line.strip()
            if line.startswith("RESEND_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise ValueError("RESEND_API_KEY not found in resend.env")


def get_unsubscribe_secret() -> str:
    if APP_ENV.exists():
        with open(APP_ENV) as f:
            for line in f:
                line = line.strip()
                if line.startswith("UNSUBSCRIBE_SECRET="):
                    return line.split("=", 1)[1].strip()
    return ""


def make_unsubscribe_token(email: str, secret: str) -> str:
    return hmac.new(
        secret.encode(),
        email.lower().encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


from cultivar_parsing import slugify, parse_cultivar, product_variety_slug  # noqa: E402


def load_nursery_data(data_dir: Path, target_date: str) -> list[dict]:
    """Load products from a specific date's snapshots."""
    products = []
    today = date.today().isoformat()
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        dated_file = nursery_dir / f"{target_date}.json"
        latest_file = nursery_dir / "latest.json"
        if dated_file.exists():
            source = dated_file
        elif target_date == today and latest_file.exists():
            source = latest_file
        else:
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
            if any(kw in title_lower for kw in NON_PLANT_KEYWORDS):
                continue
            if re.search(r'\bseeds?\b', title_lower) and 'seedling' not in title_lower and 'seedless' not in title_lower:
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


def already_sent_today(target_date: str) -> set[tuple[str, str]]:
    """Return set of (email, variety_slug) already sent on target_date."""
    if not VARIETY_WATCHES_DB.exists():
        return set()
    con = sqlite3.connect(VARIETY_WATCHES_DB)
    rows = con.execute(
        "SELECT email, variety_slug FROM sends WHERE sent_at = ?",
        (target_date,),
    ).fetchall()
    con.close()
    return {(r[0], r[1]) for r in rows}


def record_send(email: str, variety_slug: str, target_date: str):
    """Record a send in the SQLite sends table."""
    con = sqlite3.connect(VARIETY_WATCHES_DB)
    con.execute(
        "INSERT OR IGNORE INTO sends (email, variety_slug, sent_at) VALUES (?, ?, ?)",
        (email, variety_slug, target_date),
    )
    con.commit()
    con.close()


def build_variety_alert_email(variety_title: str, variety_slug: str, products: list[dict]) -> str:
    """Build HTML email body for a per-variety restock alert."""
    rows = ""
    for p in sorted(products, key=lambda x: x["price"] or 9999):
        price_str = f"${p['price']:.2f}" if p["price"] else "POA"
        utm_url = p["url"] + ("&" if "?" in p["url"] else "?") + "utm_source=treestock&utm_medium=email&utm_campaign=variety-alert" if p["url"] else ""
        rows += f"""
      <tr>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6">
          <a href="{utm_url}" style="color:#15803d;text-decoration:none">{p['title']}</a>
        </td>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;color:#6b7280;font-size:0.875em">{p['nursery_name']}</td>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;font-weight:600">{price_str}</td>
      </tr>"""

    variety_url = f"{SITE_URL}/variety/{variety_slug}.html"

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
      {variety_title} is now available!
    </h2>
    <p style="color:#6b7280;margin:0 0 20px;font-size:0.9em">
      The specific variety you were watching has come back into stock.
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
        View {variety_title} on treestock.com.au
      </a>
    </div>

    <p style="margin-top:16px;font-size:0.8em;color:#9ca3af">
      Prices and availability updated daily. Act fast — nursery stock can sell out quickly.
    </p>
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


def inject_unsubscribe(html: str, email: str, token: str) -> str:
    unsubscribe_url = f"{UNSUBSCRIBE_BASE}?email={urllib.parse.quote(email)}&token={token}"
    manage_url = f"{SITE_URL}/api/preferences?email={urllib.parse.quote(email)}&token={token}"
    footer = f"""
<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.75em;color:#9ca3af;text-align:center">
  You're receiving this because you requested restock alerts at <a href="{SITE_URL}" style="color:#6b7280">{SITE_URL}</a>.<br>
  <a href="{manage_url}" style="color:#6b7280">Manage your alerts</a> &middot;
  <a href="{unsubscribe_url}" style="color:#6b7280">Unsubscribe</a>
</p>
"""
    if "</body>" in html:
        return html.replace("</body>", footer + "</body>", 1)
    return html + footer


def send_email(api_key: str, to_email: str, subject: str, html_body: str) -> bool:
    payload = {
        "from": f"{FROM_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "treestock-variety-alerts/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"  Sent to {to_email}: {result.get('id', 'ok')}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        print(f"  FAILED {to_email} ({e.code}): {error_body}", file=sys.stderr)
        return False


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

    # Find restocks: variety going from 0 -> >0
    restocked = []
    for slug in watched_slugs:
        today_count = len(today_by_variety.get(slug, []))
        yesterday_count = len(yesterday_by_variety.get(slug, []))
        if today_count > 0 and yesterday_count == 0:
            # Use the variety_title from the first watcher record
            variety_title = watchers[slug][0]["variety_title"]
            restocked.append({
                "slug": slug,
                "variety_title": variety_title,
                "products": today_by_variety[slug],
                "watchers": watchers[slug],
            })
            print(f"  RESTOCK: {variety_title} -- {today_count} listing(s) now in stock (was 0)")

    if not restocked:
        print("No variety restocks detected. No alerts to send.")
        return

    # Load already-sent set
    sent_today = already_sent_today(target_date)

    if dry_run:
        for r in restocked:
            print(f"\n  Would send '{r['variety_title']}' alert to:")
            for w in r["watchers"]:
                already = (w["email"], r["slug"]) in sent_today
                print(f"    {'[SKIP already sent] ' if already else ''}{w['email']}")
        return

    api_key = get_resend_api_key()
    secret = get_unsubscribe_secret()
    total_sent = 0
    total_failed = 0

    for r in restocked:
        slug = r["slug"]
        variety_title = r["variety_title"]
        products = r["products"]

        recipients = [w for w in r["watchers"] if (w["email"], slug) not in sent_today]
        if not recipients:
            print(f"  {variety_title}: all watchers already alerted today")
            continue

        subject = f"{variety_title} is now available -- treestock.com.au"
        email_html = build_variety_alert_email(variety_title, slug, products)

        print(f"\n  Sending '{variety_title}' alert to {len(recipients)} watcher(s)...")
        for w in recipients:
            email = w["email"]
            token = make_unsubscribe_token(email, secret)
            personalised = inject_unsubscribe(email_html, email, token)
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
                    record_send(email, slug, target_date)
                total_sent += 1
            else:
                total_failed += 1

    print(f"\nDone: {total_sent} variety alert(s) sent, {total_failed} failed")
    if total_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
