#!/usr/bin/env python3
"""One-off: backfill /admin/digest from the Resend send history.

The daily digest was email-only until 2026-08-10, so the archive would otherwise
start empty and fill one day at a time. Resend keeps the sent HTML and will hand
it back per message, which is exactly the fragment build_digest_html produced,
so the history up to Resend's retention horizon can be recovered verbatim.

Run on the server (needs /opt/dale/secrets/resend-readonly.env):

    python3 backfill-digest-archive.py --dry-run
    python3 backfill-digest-archive.py

Idempotent: skips days already archived unless --force. Safe to re-run as the
retention window slides; it simply finds fewer.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
SCRAPERS_DIR = Path("/opt/dale/scrapers")

# api.resend.com sits behind Cloudflare, which 403s (error 1010) on the default
# Python-urllib User-Agent. Same reason resend_engagement.py sets one.
UA = "dale-digest-backfill/1.0"

SUBJECT_RE = re.compile(r"Dale Daily Digest\s*(?:--|—|&mdash;)\s*(\d{4}-\d{2}-\d{2})")

# Read-throttle. Resend's documented limit is 2 requests/second.
SLEEP_BETWEEN_CALLS = 0.6


def load_api_key() -> str:
    path = SECRETS_DIR / "resend-readonly.env"
    for line in path.read_text().splitlines():
        if line.startswith("RESEND_FULL_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"RESEND_FULL_API_KEY not found in {path}")


def api_get(url: str, key: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {key}", "User-Agent": UA}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else str(e)
        raise SystemExit(f"Resend API error ({e.code}) on {url}: {body[:300]}")


def list_digest_emails(key: str, max_pages: int = 200) -> list:
    """Every "Dale Daily Digest" send, newest first, following the cursor.

    Pagination matters: a single page is 100 sends, which at treestock's volume
    is only a few days. Refuse to report a partial history rather than backfill
    a silently truncated one.
    """
    found, cursor = [], None
    for _ in range(max_pages):
        url = "https://api.resend.com/emails?limit=100"
        if cursor:
            url += f"&after={cursor}"
        payload = api_get(url, key)
        rows = payload.get("data") or []
        found += [e for e in rows if SUBJECT_RE.search(e.get("subject") or "")]
        if not payload.get("has_more") or not rows:
            return found
        cursor = rows[-1]["id"]
        time.sleep(SLEEP_BETWEEN_CALLS)
    raise SystemExit(f"Resend pagination exceeded {max_pages} pages; aborting.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="List what would be written, write nothing.")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite days already archived.")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--scrapers-dir", default=str(SCRAPERS_DIR),
                    help="Where digest_archive.py lives.")
    args = ap.parse_args()

    sys.path.insert(0, args.scrapers_dir)
    import digest_archive

    key = load_api_key()
    emails = list_digest_emails(key)
    print(f"Found {len(emails)} digest sends in the Resend history.")

    existing = set(digest_archive.list_digest_days(args.data_dir))
    print(f"Already archived: {len(existing)}")

    # Newest first, so the first sighting of a day is the one to keep if a day
    # was ever sent twice (a retry would otherwise overwrite with the earlier body).
    seen, written, skipped = set(), 0, 0
    for e in emails:
        m = SUBJECT_RE.search(e.get("subject") or "")
        day = m.group(1)
        if day in seen:
            continue
        seen.add(day)

        if day in existing and not args.force:
            skipped += 1
            continue

        detail = api_get(f"https://api.resend.com/emails/{e['id']}", key)
        html = detail.get("html")
        if not html:
            print(f"  {day}: no HTML stored, skipping")
            continue

        if args.dry_run:
            print(f"  {day}: would write {len(html)} bytes")
        else:
            path = digest_archive.save_digest(args.data_dir, day, html)
            print(f"  {day}: wrote {len(html)} bytes -> {path}")
        written += 1
        time.sleep(SLEEP_BETWEEN_CALLS)

    verb = "would write" if args.dry_run else "wrote"
    print(f"\n{verb} {written}, skipped {skipped} already archived.")
    if not args.dry_run:
        days = digest_archive.list_digest_days(args.data_dir)
        print(f"Archive now holds {len(days)} digests "
              f"({days[-1]} to {days[0]})." if days else "Archive is empty.")


if __name__ == "__main__":
    main()
