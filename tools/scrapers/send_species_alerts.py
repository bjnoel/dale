#!/usr/bin/env python3
"""
Send species restock alerts to subscribers who are watching specific species.

Compares today's data against yesterday's to detect when a species goes from
0 in-stock to >0 in-stock. Sends a targeted email to subscribers watching
that species.

Runs after each daily scrape, after build_species_pages.py.

Usage:
    python3 send_species_alerts.py <data-dir>
    python3 send_species_alerts.py <data-dir> --dry-run
    python3 send_species_alerts.py <data-dir> --date 2026-03-14
    python3 send_species_alerts.py <data-dir> --redirect-to me@example.com

--redirect-to sends every alert to the given address (with the original
recipient noted in the subject and a banner injected into the body) and
does NOT update the sends log. Useful for previewing.

Australian Spam Act compliance:
    - Every email includes a working unsubscribe link
    - Unsubscribe requests are honoured via subscribe_server.py
"""

import hashlib
import hmac
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
DASHBOARD_DIR = Path("/opt/dale/dashboard")
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
ALERT_SENDS_LOG = DATA_DIR / "species_alert_sends.json"
RESEND_ENV = SECRETS_DIR / "resend.env"
APP_ENV = SECRETS_DIR / "app.env"
SPECIES_FILE = Path(__file__).parent / "fruit_species.json"

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
    "ornamental",  # ornamental trees/shrubs are not fruit trees
    "asparagus",   # vegetable, not a fruit tree
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


def load_subscribers() -> list:
    if not SUBSCRIBERS_FILE.exists():
        return []
    with open(SUBSCRIBERS_FILE) as f:
        return json.load(f)


def load_sends_log() -> dict:
    if not ALERT_SENDS_LOG.exists():
        return {}
    with open(ALERT_SENDS_LOG) as f:
        return json.load(f)


def save_sends_log(log: dict):
    ALERT_SENDS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERT_SENDS_LOG, "w") as f:
        json.dump(log, f, indent=2)


def load_species_lookup() -> dict:
    """Build lowercase name → species entry lookup."""
    if not SPECIES_FILE.exists():
        return {}
    with open(SPECIES_FILE) as f:
        species_list = json.load(f)
    lookup = {}
    for s in species_list:
        key = s["common_name"].lower()
        lookup[key] = s
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = s
    return lookup


def match_title(title: str, lookup: dict) -> dict | None:
    title_lower = title.lower()
    words = re.split(r'[\s\-–—]+', title_lower)
    for n in range(min(len(words), 5), 0, -1):
        candidate = " ".join(words[:n])
        if candidate in lookup:
            return lookup[candidate]
    return None


def load_nursery_data(data_dir: Path, target_date: str) -> list[dict]:
    """Load products from a specific date's snapshots (or latest.json if today)."""
    products = []
    today = date.today().isoformat()
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        # Try dated file first, fall back to latest.json for today
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


def count_in_stock_by_species(products: list[dict], lookup: dict) -> dict[str, list[dict]]:
    """Group in-stock products by species slug. Returns {slug: [products]}."""
    by_species: dict[str, list[dict]] = {}
    for p in products:
        if not p["available"]:
            continue
        species = match_title(p["title"], lookup)
        if not species:
            continue
        slug = species["slug"]
        by_species.setdefault(slug, []).append(p)
    return by_species


def build_alert_email(species_name: str, slug: str, new_products: list[dict]) -> str:
    """Build HTML email body for a species restock alert."""
    rows = ""
    for p in sorted(new_products, key=lambda x: x["price"] or 9999):
        price_str = f"${p['price']:.2f}" if p["price"] else "POA"
        utm_url = p["url"] + ("&" if "?" in p["url"] else "?") + "utm_source=treestock&utm_medium=email&utm_campaign=alert" if p["url"] else ""
        rows += f"""
      <tr>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6">
          <a href="{utm_url}" style="color:#15803d;text-decoration:none">{p['title']}</a>
        </td>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;color:#6b7280;font-size:0.875em">{p['nursery_name']}</td>
        <td style="padding:8px 12px;border-bottom:1px solid #f3f4f6;font-weight:600">{price_str}</td>
      </tr>"""

    species_url = f"{SITE_URL}/species/{slug}.html"
    count = len(new_products)

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
      🌱 {species_name} trees are back in stock!
    </h2>
    <p style="color:#6b7280;margin:0 0 20px;font-size:0.9em">
      {count} {'variety' if count == 1 else 'varieties'} now available across our monitored nurseries.
    </p>

    <table style="width:100%;border-collapse:collapse;font-size:0.9em">
      <thead>
        <tr style="background:#f9fafb">
          <th style="padding:8px 12px;text-align:left;font-size:0.75em;text-transform:uppercase;color:#9ca3af;font-weight:600;border-bottom:2px solid #e5e7eb">Variety</th>
          <th style="padding:8px 12px;text-align:left;font-size:0.75em;text-transform:uppercase;color:#9ca3af;font-weight:600;border-bottom:2px solid #e5e7eb">Nursery</th>
          <th style="padding:8px 12px;text-align:left;font-size:0.75em;text-transform:uppercase;color:#9ca3af;font-weight:600;border-bottom:2px solid #e5e7eb">Price</th>
        </tr>
      </thead>
      <tbody>{rows}
      </tbody>
    </table>

    <div style="margin-top:20px">
      <a href="{species_url}" style="display:inline-block;background:#15803d;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:0.9em;font-weight:500">
        View all {species_name} varieties →
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
            "User-Agent": "treestock-alerts/1.0",
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
        print("Usage: send_species_alerts.py <data-dir> [--dry-run] [--date YYYY-MM-DD]")
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
    print(f"send_species_alerts.py — {target_date}{mode_tag}")

    # Find subscribers with watch_species
    all_subscribers = load_subscribers()
    watchers: dict[str, list[str]] = {}  # {species_slug: [emails]}
    for sub in all_subscribers:
        for slug in sub.get("watch_species", []):
            watchers.setdefault(slug, []).append(sub["email"])

    if not watchers:
        print("No species watchers found. Nothing to do.")
        return

    watched_slugs = set(watchers.keys())
    print(f"Watched species: {', '.join(sorted(watched_slugs))} ({len(watchers)} email/species pairs)")

    # Load species lookup
    lookup = load_species_lookup()
    if not lookup:
        print("ERROR: Could not load species taxonomy", file=sys.stderr)
        sys.exit(1)

    # Load today's and yesterday's data
    yesterday = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    print(f"Loading today's data ({target_date})...")
    today_products = load_nursery_data(data_dir, target_date)
    print(f"  {len(today_products)} products")
    print(f"Loading yesterday's data ({yesterday})...")
    yesterday_products = load_nursery_data(data_dir, yesterday)
    print(f"  {len(yesterday_products)} products")

    # Count in-stock by species
    today_by_species = count_in_stock_by_species(today_products, lookup)
    yesterday_by_species = count_in_stock_by_species(yesterday_products, lookup)

    # Find restocks: species going from 0 → >0 (or absent → present)
    restocked = []
    for slug in watched_slugs:
        today_count = len(today_by_species.get(slug, []))
        yesterday_count = len(yesterday_by_species.get(slug, []))
        if today_count > 0 and yesterday_count == 0:
            # Find the species common name
            species_entry = None
            for p in today_by_species[slug]:
                matched = match_title(p["title"], lookup)
                if matched and matched["slug"] == slug:
                    species_entry = matched
                    break
            if not species_entry:
                continue
            restocked.append({
                "slug": slug,
                "name": species_entry["common_name"],
                "products": today_by_species[slug],
                "emails": watchers[slug],
            })
            print(f"  RESTOCK: {species_entry['common_name']} — {today_count} varieties now in stock (was 0)")

    if not restocked:
        print("No species restocks detected. No alerts to send.")
        return

    # Load sends log
    sends_log = load_sends_log()
    today_log = sends_log.get(target_date, {})  # {species_slug: [emails_already_sent]}

    if dry_run:
        for r in restocked:
            print(f"\n  Would send '{r['name']}' alert to:")
            for email in r["emails"]:
                already = email in today_log.get(r["slug"], [])
                print(f"    {'[SKIP already sent]' if already else ''}{email}")
        return

    api_key = get_resend_api_key()
    secret = get_unsubscribe_secret()
    total_sent = 0
    total_failed = 0

    for r in restocked:
        slug = r["slug"]
        name = r["name"]
        products = r["products"]
        already_sent_to = set(today_log.get(slug, []))
        recipients = [e for e in r["emails"] if e not in already_sent_to]

        if not recipients:
            print(f"  {name}: all watchers already alerted today")
            continue

        subject = f"🌱 {name} trees are back in stock — treestock.com.au"
        email_html = build_alert_email(name, slug, products)

        print(f"\n  Sending {name} alert to {len(recipients)} subscriber(s)...")
        sent_to = list(already_sent_to)
        for email in recipients:
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
                    sent_to.append(email)
                total_sent += 1
            else:
                total_failed += 1

        today_log[slug] = sent_to

    if not redirect_to:
        sends_log[target_date] = today_log
        save_sends_log(sends_log)

    print(f"\nDone: {total_sent} alert(s) sent, {total_failed} failed")
    if total_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
