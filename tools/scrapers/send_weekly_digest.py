#!/usr/bin/env python3
"""
Send weekly nursery stock digest to email subscribers via Resend.

Compares today's snapshot against 7 days ago to produce a curated weekly
summary: biggest price drops, notable restocks, interesting new arrivals.

Runs Sundays at 23:00 UTC (= Monday 7am AWST).

Usage:
    python3 send_weekly_digest.py                    # Send to all subscribers
    python3 send_weekly_digest.py --dry-run          # Preview without sending
    python3 send_weekly_digest.py --test EMAIL       # Send to one address only
    python3 send_weekly_digest.py --date 2026-04-06  # Use specific end date

Australian Spam Act compliance:
    - Every email includes a working unsubscribe link
    - From address is clearly identified
    - Unsubscribe requests are honoured immediately via subscribe_server.py
"""

import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daily_digest import load_snapshot, compare_snapshots, NURSERY_NAMES, ALL_CATEGORIES, filter_changes_by_plant_categories
from send_digest import get_subscriber_categories, get_subscriber_frequency, get_subscriber_state, get_subscriber_plant_categories
from shipping import SHIPPING_MAP, nursery_ships_to
from stocklib.email_footer import inject_footer, inject_text_footer
from stocklib.utm import outbound

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
NURSERY_STOCK_DIR = DATA_DIR / "nursery-stock"
WEEKLY_SENDS_LOG = DATA_DIR / "weekly_digest_sends.json"


from stocklib.mailer import (get_resend_api_key, get_unsubscribe_secret,
                             make_unsubscribe_token, load_subscribers,
                             load_sends_log, save_sends_log)
import functools
from stocklib.mailer import send_email as _send_email
send_email = functools.partial(_send_email, user_agent="treestock-weekly/1.0")
SITE_URL = "https://treestock.com.au"

# Caps to keep emails scannable
MAX_PRICE_DROPS = 8
MAX_RESTOCKS = 8
MAX_NEW_ARRIVALS = 8


def load_weekly_changes(end_date: str, state_filter: str = "") -> dict:
    """
    Compare snapshot from 7 days ago vs end_date snapshot for all nurseries.

    Returns dict of {nursery_key: changes} where changes has price_drops,
    back_in_stock, new_products. Items are enriched with significance scores.
    """
    end = date.fromisoformat(end_date)
    start = end - timedelta(days=7)
    start_date = start.isoformat()

    all_changes = {}

    for nursery_dir in sorted(NURSERY_STOCK_DIR.iterdir()):
        if not nursery_dir.is_dir():
            continue
        nursery_key = nursery_dir.name

        if state_filter and not nursery_ships_to(nursery_key, state_filter):
            continue

        # Try to find the best "start" snapshot within the window
        # (may not have data from exactly 7 days ago, try 6-8 days back)
        prev = {}
        for delta in [7, 6, 8, 5, 9]:
            try_date = (end - timedelta(days=delta)).isoformat()
            prev = load_snapshot(nursery_dir, try_date)
            if prev:
                break

        curr = load_snapshot(nursery_dir, end_date)
        if not prev or not curr:
            continue

        changes = compare_snapshots(prev, curr)

        # Score price drops by % discount descending
        for item in changes["price_drops"]:
            old = item["old_price"]
            new = item["new_price"]
            item["pct_drop"] = round((old - new) / old * 100, 1) if old > 0 else 0
        changes["price_drops"].sort(key=lambda x: -x.get("pct_drop", 0))

        # New arrivals: sort by price ascending (value items first)
        changes["new_products"].sort(
            key=lambda x: x.get("price") or 999999
        )

        all_changes[nursery_key] = changes

    return all_changes


def format_weekly_html(all_changes: dict, end_date: str, state_filter: str = "", categories=None) -> str:
    """Build a curated weekly digest HTML email."""
    enabled = frozenset(c for c in (categories or ALL_CATEGORIES) if c in ALL_CATEGORIES)
    start = (date.fromisoformat(end_date) - timedelta(days=7)).strftime("%-d %b")
    end_fmt = date.fromisoformat(end_date).strftime("%-d %b %Y")
    date_range = f"{start} — {end_fmt}"

    # Collect top items across all nurseries
    top_price_drops = []
    top_restocks = []
    top_new_arrivals = []

    for nursery_key, changes in sorted(all_changes.items()):
        name = NURSERY_NAMES.get(nursery_key, nursery_key)

        if "price_drops" in enabled:
            for item in changes["price_drops"]:
                top_price_drops.append({**item, "nursery": name, "nursery_key": nursery_key})

        if "back_in_stock" in enabled:
            for item in changes["back_in_stock"]:
                top_restocks.append({**item, "nursery": name, "nursery_key": nursery_key})

        if "new_products" in enabled:
            for item in changes["new_products"]:
                top_new_arrivals.append({**item, "nursery": name, "nursery_key": nursery_key})

    # Sort globally and cap
    top_price_drops.sort(key=lambda x: -x.get("pct_drop", 0))
    top_price_drops = top_price_drops[:MAX_PRICE_DROPS]

    top_new_arrivals.sort(key=lambda x: x.get("price") or 999999)
    top_new_arrivals = top_new_arrivals[:MAX_NEW_ARRIVALS]

    top_restocks = top_restocks[:MAX_RESTOCKS]

    has_any = top_price_drops or top_restocks or top_new_arrivals

    # Build content sections
    sections = []

    def utm(url):
        return outbound(url, "email", campaign="weekly")

    if top_price_drops:
        rows = []
        for item in top_price_drops:
            url = utm(item.get("url", ""))
            link = (
                f'<a href="{url}" style="color:#065f46;text-decoration:none">{item["title"]}</a>'
                if url else item["title"]
            )
            pct = f' <span style="color:#059669;font-size:0.85em">(-{item["pct_drop"]}%)</span>' if item.get("pct_drop") else ""
            rows.append(
                f'<tr>'
                f'<td style="padding:8px 0;border-bottom:1px solid #f3f4f6">'
                f'{link}<br>'
                f'<span style="font-size:0.85em;color:#6b7280">{item["nursery"]}</span>'
                f'</td>'
                f'<td style="padding:8px 0 8px 16px;border-bottom:1px solid #f3f4f6;text-align:right;white-space:nowrap">'
                f'<span style="text-decoration:line-through;color:#9ca3af">${item["old_price"]:.2f}</span>'
                f' <strong style="color:#059669">${item["new_price"]:.2f}</strong>{pct}'
                f'</td>'
                f'</tr>'
            )
        sections.append(
            f'<h3 style="color:#065f46;margin:24px 0 8px;font-size:1rem">📉 Price drops</h3>'
            f'<table style="width:100%;border-collapse:collapse">{"".join(rows)}</table>'
        )

    if top_restocks:
        rows = []
        for item in top_restocks:
            url = utm(item.get("url", ""))
            link = (
                f'<a href="{url}" style="color:#065f46;text-decoration:none">{item["title"]}</a>'
                if url else item["title"]
            )
            price_str = f' — <strong>${item["price"]:.2f}</strong>' if item.get("price") else ""
            rows.append(
                f'<li style="padding:6px 0;border-bottom:1px solid #f3f4f6">'
                f'{link}{price_str}'
                f'<br><span style="font-size:0.85em;color:#6b7280">{item["nursery"]}</span>'
                f'</li>'
            )
        sections.append(
            f'<h3 style="color:#065f46;margin:24px 0 8px;font-size:1rem">✅ Back in stock</h3>'
            f'<ul style="list-style:none;padding:0;margin:0">{"".join(rows)}</ul>'
        )

    if top_new_arrivals:
        rows = []
        for item in top_new_arrivals:
            url = utm(item.get("url", ""))
            link = (
                f'<a href="{url}" style="color:#065f46;text-decoration:none">{item["title"]}</a>'
                if url else item["title"]
            )
            price_str = f' — <strong>${item["price"]:.2f}</strong>' if item.get("price") else ""
            rows.append(
                f'<li style="padding:6px 0;border-bottom:1px solid #f3f4f6">'
                f'{link}{price_str}'
                f'<br><span style="font-size:0.85em;color:#6b7280">{item["nursery"]}</span>'
                f'</li>'
            )
        sections.append(
            f'<h3 style="color:#065f46;margin:24px 0 8px;font-size:1rem">🆕 New this week</h3>'
            f'<ul style="list-style:none;padding:0;margin:0">{"".join(rows)}</ul>'
        )

    if not has_any:
        sections.append('<p style="color:#6b7280">All quiet this week — no notable changes across the nurseries.</p>')

    # Stats line
    total_drops = sum(len(c["price_drops"]) for c in all_changes.values())
    total_restocks = sum(len(c["back_in_stock"]) for c in all_changes.values())
    total_new = sum(len(c["new_products"]) for c in all_changes.values())
    nursery_count = len(SHIPPING_MAP)

    stats_parts = []
    if total_drops:
        stats_parts.append(f"{total_drops} price drop{'s' if total_drops != 1 else ''}")
    if total_restocks:
        stats_parts.append(f"{total_restocks} restock{'s' if total_restocks != 1 else ''}")
    if total_new:
        stats_parts.append(f"{total_new} new listing{'s' if total_new != 1 else ''}")
    stats_str = ", ".join(stats_parts) if stats_parts else "no changes"

    state_note = f" (filtered to {state_filter})" if state_filter else ""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:560px;margin:0 auto;padding:24px 16px;">
<div style="background:white;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

  <!-- Header -->
  <div style="background:#065f46;padding:24px;text-align:center;">
    <h1 style="margin:0;color:white;font-size:1.3rem;font-weight:700;">treestock.com.au</h1>
    <p style="margin:6px 0 0;color:#a7f3d0;font-size:0.85rem;">Weekly Stock Digest</p>
  </div>

  <!-- Body -->
  <div style="padding:24px;">
    <h2 style="margin:0 0 4px;color:#065f46;font-size:1.1rem;">This week{state_note}</h2>
    <p style="margin:0 0 20px;color:#6b7280;font-size:0.85rem;">{date_range} across {nursery_count} nurseries — {stats_str}</p>

    {"".join(sections)}

    <div style="margin-top:24px;text-align:center;">
      <a href="{SITE_URL}?utm_source=treestock&utm_medium=email&utm_campaign=weekly"
         style="display:inline-block;background:#065f46;color:white;text-decoration:none;padding:10px 24px;border-radius:8px;font-weight:600;font-size:0.95rem;">
        Browse all current stock &rarr;
      </a>
    </div>

    <p style="margin-top:24px;font-size:0.85rem;color:#6b7280;text-align:center;">
      Know a fellow fruit grower who would love this? Forward this email to them.
    </p>

    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:14px 16px;margin-top:20px;">
      <p style="margin:0 0 6px;font-weight:600;color:#065f46;font-size:0.9rem;">Track your collection with Treesmith</p>
      <p style="margin:0;color:#374151;font-size:0.875rem;line-height:1.5;">
        treestock tells you what's in stock. <strong>Treesmith</strong>, our companion app, helps you
        catalog every tree, log grafts and harvests, and capture growth photos over time.
        <a href="{SITE_URL}/treesmith.html?utm_source=treestock&amp;utm_medium=email&amp;utm_campaign=weekly_digest" style="color:#065f46;">Learn more &rarr;</a>
      </p>
    </div>

  </div>

</div>
</div>
</body>
</html>"""


def has_any_weekly_changes(all_changes: dict, categories=None) -> bool:
    """True if at least one item survives the category filter."""
    enabled = frozenset(c for c in (categories or ALL_CATEGORIES) if c in ALL_CATEGORIES)
    for changes in all_changes.values():
        for cat in enabled:
            if changes.get(cat):
                return True
    return False


def format_weekly_text(all_changes: dict, end_date: str, state_filter: str = "", categories=None) -> str:
    """Build a plain-text version of the weekly digest (fallback for non-HTML clients)."""
    enabled = frozenset(c for c in (categories or ALL_CATEGORIES) if c in ALL_CATEGORIES)
    start = (date.fromisoformat(end_date) - timedelta(days=7)).strftime("%-d %b")
    end_fmt = date.fromisoformat(end_date).strftime("%-d %b %Y")
    date_range = f"{start} to {end_fmt}"
    nursery_count = len(SHIPPING_MAP)
    state_note = f" (filtered to {state_filter})" if state_filter else ""

    top_price_drops = []
    top_restocks = []
    top_new_arrivals = []

    for nursery_key, changes in sorted(all_changes.items()):
        name = NURSERY_NAMES.get(nursery_key, nursery_key)
        if "price_drops" in enabled:
            for item in changes["price_drops"]:
                top_price_drops.append({**item, "nursery": name})
        if "back_in_stock" in enabled:
            for item in changes["back_in_stock"]:
                top_restocks.append({**item, "nursery": name})
        if "new_products" in enabled:
            for item in changes["new_products"]:
                top_new_arrivals.append({**item, "nursery": name})

    top_price_drops.sort(key=lambda x: -x.get("pct_drop", 0))
    top_price_drops = top_price_drops[:MAX_PRICE_DROPS]
    top_new_arrivals.sort(key=lambda x: x.get("price") or 999999)
    top_new_arrivals = top_new_arrivals[:MAX_NEW_ARRIVALS]
    top_restocks = top_restocks[:MAX_RESTOCKS]

    total_drops = sum(len(c["price_drops"]) for c in all_changes.values())
    total_restocks = sum(len(c["back_in_stock"]) for c in all_changes.values())
    total_new = sum(len(c["new_products"]) for c in all_changes.values())

    stats_parts = []
    if total_drops:
        stats_parts.append(f"{total_drops} price drop{'s' if total_drops != 1 else ''}")
    if total_restocks:
        stats_parts.append(f"{total_restocks} restock{'s' if total_restocks != 1 else ''}")
    if total_new:
        stats_parts.append(f"{total_new} new listing{'s' if total_new != 1 else ''}")
    stats_str = ", ".join(stats_parts) if stats_parts else "no changes"

    lines = [
        "treestock.com.au — Weekly Stock Digest",
        "=" * 40,
        f"Week of {date_range}{state_note}",
        f"{nursery_count} nurseries tracked — {stats_str}",
        "",
    ]

    if top_price_drops:
        lines.append("PRICE DROPS")
        lines.append("-" * 30)
        for item in top_price_drops:
            pct = f" (-{item['pct_drop']}%)" if item.get("pct_drop") else ""
            lines.append(f"  {item['title']}")
            lines.append(f"  ${item['old_price']:.2f} -> ${item['new_price']:.2f}{pct}")
            lines.append(f"  {item['nursery']}")
            if item.get("url"):
                lines.append(f"  {item['url']}")
            lines.append("")

    if top_restocks:
        lines.append("BACK IN STOCK")
        lines.append("-" * 30)
        for item in top_restocks:
            price_str = f" — ${item['price']:.2f}" if item.get("price") else ""
            lines.append(f"  {item['title']}{price_str}")
            lines.append(f"  {item['nursery']}")
            if item.get("url"):
                lines.append(f"  {item['url']}")
            lines.append("")

    if top_new_arrivals:
        lines.append("NEW THIS WEEK")
        lines.append("-" * 30)
        for item in top_new_arrivals:
            price_str = f" — ${item['price']:.2f}" if item.get("price") else ""
            lines.append(f"  {item['title']}{price_str}")
            lines.append(f"  {item['nursery']}")
            if item.get("url"):
                lines.append(f"  {item['url']}")
            lines.append("")

    if not (top_price_drops or top_restocks or top_new_arrivals):
        lines.append("All quiet this week — no notable changes across the nurseries.")
        lines.append("")

    lines.append(f"Browse all current stock: {SITE_URL}")
    lines.append("")
    lines.append("Know a fellow fruit grower who would love this? Forward this email to them.")
    lines.append("")
    lines.append("---")
    lines.append("Track your collection with Treesmith")
    lines.append(f"treestock tells you what's in stock. Treesmith, our companion app, helps you catalog every tree, log grafts and harvests, and capture growth photos over time.")
    lines.append(f"{SITE_URL}/treesmith.html?utm_source=treestock&utm_medium=email&utm_campaign=weekly_digest")
    return "\n".join(lines)


def main():
    dry_run = "--dry-run" in sys.argv
    test_email = None
    end_date = date.today().isoformat()
    week_key = f"week-{end_date}"

    if "--test" in sys.argv:
        idx = sys.argv.index("--test")
        test_email = sys.argv[idx + 1]

    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        end_date = sys.argv[idx + 1]
        week_key = f"week-{end_date}"

    print(f"send_weekly_digest.py — week ending {end_date}{' [DRY RUN]' if dry_run else ''}")

    # Load subscribers — only those who opted into weekly cadence
    all_subscribers = load_subscribers()
    if test_email:
        existing = next((s for s in all_subscribers if s["email"] == test_email.lower()), None)
        if existing:
            subscribers = [existing]
        else:
            subscribers = [{"email": test_email, "state": "ALL"}]
        ts = get_subscriber_state(subscribers[0])
        tc = sorted(get_subscriber_categories(subscribers[0]))
        print(f"TEST MODE: Sending only to {test_email} (state={ts}, categories={','.join(tc)})")
    else:
        subscribers = [s for s in all_subscribers if get_subscriber_frequency(s) == "weekly"]

    if not subscribers:
        print("No subscribers.")
        return

    # Idempotency
    sends_log = load_sends_log(WEEKLY_SENDS_LOG)
    already_sent = set() if test_email else set(sends_log.get(week_key, []))
    to_send = [s for s in subscribers if s["email"] not in already_sent]
    skipped = len(subscribers) - len(to_send)

    print(f"Subscribers: {len(subscribers)} weekly, {len(to_send)} to send, {skipped} already sent this week")

    if not to_send:
        print("All subscribers already received this week's digest.")
        return

    # Group by (state, change-categories, plant-categories) — same combo reuses HTML.
    by_bucket: dict[tuple, list] = {}
    for s in to_send:
        state = get_subscriber_state(s)
        cats = get_subscriber_categories(s)
        pcats = get_subscriber_plant_categories(s)
        by_bucket.setdefault((state, cats, pcats), []).append(s)

    bucket_summary = ", ".join(
        f"{st}/{','.join(sorted(cs)) or '(none)'}/{','.join(sorted(pc)) or '(none)'}({len(subs)})"
        for (st, cs, pc), subs in sorted(by_bucket.items(),
                                         key=lambda kv: (kv[0][0], sorted(kv[0][1]), sorted(kv[0][2])))
    )
    print(f"Buckets: {bucket_summary}")

    if dry_run:
        for s in to_send:
            state = get_subscriber_state(s)
            cats = ",".join(sorted(get_subscriber_categories(s))) or "(none)"
            pcats = ",".join(sorted(get_subscriber_plant_categories(s))) or "(none)"
            print(f"  Would send to: {s['email']} (state={state}, categories={cats}, plant={pcats})")
        all_changes = load_weekly_changes(end_date)
        total_drops = sum(len(c["price_drops"]) for c in all_changes.values())
        total_restocks = sum(len(c["back_in_stock"]) for c in all_changes.values())
        total_new = sum(len(c["new_products"]) for c in all_changes.values())
        print(f"  Changes found: {total_drops} price drops, {total_restocks} restocks, {total_new} new arrivals")
        return

    api_key = get_resend_api_key()
    secret = get_unsubscribe_secret()
    start_fmt = (date.fromisoformat(end_date) - timedelta(days=7)).strftime("%-d %b")
    end_fmt = date.fromisoformat(end_date).strftime("%-d %b %Y")
    subject = f"Weekly Nursery Digest — {start_fmt} to {end_fmt}"

    # Cache weekly change data per state (network-of-snapshots load is the expensive bit).
    state_changes_cache: dict[str, dict] = {}
    # Cache rendered HTML/text per (state, categories).
    html_cache: dict[tuple, str] = {}
    text_cache: dict[tuple, str] = {}

    sent_emails = list(already_sent)
    failed = 0
    empty_skipped = 0

    for (state, cats, pcats), bucket_subscribers in sorted(
        by_bucket.items(), key=lambda kv: (kv[0][0], sorted(kv[0][1]), sorted(kv[0][2]))
    ):
        filter_state = "" if state == "ALL" else state

        # Mute-all opt-out: keep variety alerts but skip the weekly digest.
        if not cats or not pcats:
            empty_skipped += len(bucket_subscribers)
            print(f"  Skipping {len(bucket_subscribers)} subscribers with no categories enabled")
            continue

        if state not in state_changes_cache:
            state_changes_cache[state] = load_weekly_changes(end_date, state_filter=filter_state)
        # Scope to the subscriber's plant categories (DAL-199); the weekly has no
        # separate labelled section, so we filter the items in place.
        all_changes = filter_changes_by_plant_categories(
            state_changes_cache[state], pcats)

        if not has_any_weekly_changes(all_changes, categories=cats):
            empty_skipped += len(bucket_subscribers)
            print(f"  Skipping {len(bucket_subscribers)} subscribers — no matching changes for {state}/{','.join(sorted(cats))}/{','.join(sorted(pcats))}")
            continue

        cache_key = (state, cats, pcats)
        if cache_key not in html_cache:
            html_cache[cache_key] = format_weekly_html(
                all_changes, end_date, state_filter=filter_state, categories=cats
            )
            text_cache[cache_key] = format_weekly_text(
                all_changes, end_date, state_filter=filter_state, categories=cats
            )

        digest_html = html_cache[cache_key]
        digest_text = text_cache[cache_key]

        for subscriber in bucket_subscribers:
            email = subscriber["email"]
            token = make_unsubscribe_token(email, secret)
            personalised_html = inject_footer(digest_html, email, token, state)
            personalised_text = inject_text_footer(digest_text, email, token, state)
            success = send_email(api_key, email, subject, personalised_html, personalised_text)
            if success:
                sent_emails.append(email)
            else:
                failed += 1

    if not test_email:
        sends_log[week_key] = sent_emails
        save_sends_log(WEEKLY_SENDS_LOG, sends_log)

    sent_count = len(sent_emails) - len(already_sent)
    print(f"Done: {sent_count} sent, {empty_skipped} skipped (empty/muted), {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
