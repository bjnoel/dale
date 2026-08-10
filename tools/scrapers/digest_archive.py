#!/usr/bin/env python3
"""Browsable archive of the Dale daily digest, served at /admin/digest.

The digest was email-only: daily-digest.py built the HTML, handed it to Resend
and dropped it, so "what did Dale say needed doing on the 3rd" meant searching a
mail client. daily-digest.py now writes each day's HTML here first, and this
module lists and renders them behind the same Cloudflare Access gate as /admin.

What is stored is the email *fragment* (the `<h2>Dale Daily Digest ...` body),
not a full document, so the admin chrome can change without rewriting history.

The path convention is defined here and mirrored by write_digest_archive() in
tools/autonomous/daily-digest.py, which cannot import this module (different
deploy tree: /opt/dale/autonomous vs /opt/dale/scrapers). The digest cron must
not be able to fail on a cross-tree import, so the two agree by convention and
tests/test_digest_archive.py asserts they still do.
"""

import os
import re
from datetime import datetime
from pathlib import Path

import admin_view

DATA_DIR = Path("/opt/dale/data")

# Both halves of the convention. daily-digest.py repeats these two literals.
DIGESTS_DIRNAME = "digests"
DIGEST_FILENAME = "{day}.html"

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MONTH_LABEL = "%B %Y"

EXTRA_CSS = """
  .digest { background:#fff; border:1px solid #e5e7eb; border-radius:10px;
    padding:4px 20px 20px; }
  .digest h2:first-child { margin-top:16px; font-size:1.05rem; color:#065f46; }
  .digest h3 { font-size:0.92rem; color:#065f46; margin:20px 0 8px;
    border-top:1px solid #f3f4f6; padding-top:14px; }
  .digest ul { padding-left:20px; font-size:0.88rem; line-height:1.5; }
  .digest li { margin-bottom:6px; }
  .digest p { font-size:0.88rem; line-height:1.5; }
  .digest table { font-size:0.82rem; margin:8px 0; }
  .digest a { color:#065f46; }
  .pager { display:flex; align-items:center; gap:12px; flex-wrap:wrap;
    margin:0 0 18px; font-size:0.85rem; }
  .pager .spacer { flex:1; }
  .pager a, .pager span.off { display:inline-block; padding:6px 12px;
    border:1px solid #e5e7eb; border-radius:8px; background:#fff; }
  .pager a { color:#065f46; text-decoration:none; font-weight:600; }
  .pager span.off { color:#d1d5db; }
  .archive ul { list-style:none; margin:0; padding:0; display:grid;
    grid-template-columns:repeat(auto-fill,minmax(120px,1fr)); gap:6px; }
  .archive li a { display:block; padding:6px 10px; background:#fff;
    border:1px solid #e5e7eb; border-radius:6px; font-size:0.82rem;
    color:#065f46; text-decoration:none; }
  .archive li a.here { background:#065f46; color:#fff; border-color:#065f46; }
  .archive details { margin-top:12px; }
  .archive summary { cursor:pointer; font-size:0.85rem; color:#6b7280;
    margin-bottom:8px; }
"""


def digests_dir(data_dir=None) -> Path:
    return Path(data_dir or DATA_DIR) / DIGESTS_DIRNAME


def is_valid_day(day: str) -> bool:
    """Strict YYYY-MM-DD. This is the path-traversal guard, not a formality:
    the day comes straight off the URL."""
    if not day or not DAY_RE.match(day):
        return False
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def digest_path(data_dir, day: str) -> Path:
    if not is_valid_day(day):
        raise ValueError(f"not a YYYY-MM-DD day: {day!r}")
    return digests_dir(data_dir) / DIGEST_FILENAME.format(day=day)


def save_digest(data_dir, day: str, html: str) -> Path:
    """Write one day's digest fragment. Raises on a bad day or unwritable dir;
    callers on the cron path are expected to swallow that (the email matters
    more than the archive)."""
    path = digest_path(data_dir, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def list_digest_days(data_dir=None) -> list:
    """Every archived day, newest first. Ignores anything not named YYYY-MM-DD."""
    d = digests_dir(data_dir)
    try:
        names = os.listdir(d)
    except OSError:
        return []
    days = []
    for name in names:
        if not name.endswith(".html"):
            continue
        stem = name[: -len(".html")]
        if is_valid_day(stem):
            days.append(stem)
    return sorted(days, reverse=True)


def load_digest(data_dir, day: str):
    """The stored fragment, or None if there is no such day."""
    try:
        path = digest_path(data_dir, day)
    except ValueError:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _pager(day: str, days: list) -> str:
    """Older/newer links plus position. `days` is newest-first."""
    i = days.index(day)
    older = days[i + 1] if i + 1 < len(days) else None
    newer = days[i - 1] if i > 0 else None

    def link(target, label):
        if not target:
            return f'<span class="off">{label}</span>'
        return f'<a href="/admin/digest/{target}">{label}</a>'

    position = f"{i + 1} of {len(days)}"
    latest = "" if i == 0 else ' · <a href="/admin/digest">latest</a>'
    return (
        '<div class="pager">'
        + link(newer, "&larr; Newer")
        + link(older, "Older &rarr;")
        + '<span class="spacer"></span>'
        + f'<span class="muted small">{position}{latest}</span>'
        + "</div>"
    )


def _archive_list(current: str, days: list) -> str:
    """All archived days, grouped by month. The current month is open; older
    months collapse, so a year of digests does not bury the one being read."""
    by_month = {}
    for day in days:
        by_month.setdefault(day[:7], []).append(day)

    def month_block(month, month_days):
        items = []
        for d in month_days:
            cls = ' class="here"' if d == current else ""
            items.append(f'<li><a href="/admin/digest/{d}"{cls}>{d}</a></li>')
        return "<ul>" + "".join(items) + "</ul>"

    months = sorted(by_month, reverse=True)
    parts = ['<section class="archive"><h2>Archive</h2>']
    for n, month in enumerate(months):
        label = datetime.strptime(month, "%Y-%m").strftime(MONTH_LABEL)
        body = month_block(month, by_month[month])
        count = len(by_month[month])
        if n == 0:
            parts.append(f"<h3>{label}</h3>{body}")
        else:
            parts.append(
                f"<details><summary>{label} ({count})</summary>{body}</details>"
            )
    parts.append("</section>")
    return "".join(parts)


def _shell(subtitle: str, content: str) -> str:
    return admin_view.render_page(
        title="treestock admin — daily digest",
        heading="treestock admin · daily digest",
        subtitle=subtitle,
        content=content,
        extra_css=EXTRA_CSS,
        nav=admin_view.render_nav("/admin/digest"),
    )


def render_digest_page(data_dir=None, day: str = None):
    """(status, html) for /admin/digest and /admin/digest/<day>.

    day=None means the newest archived digest.
    """
    days = list_digest_days(data_dir)

    if not days:
        return 200, _shell(
            "View only",
            '<section><h2>No digests archived yet</h2>'
            '<p class="muted">The first one lands after the next daily digest '
            "run (22:00 UTC / 6am AWST).</p></section>",
        )

    if day is None:
        day = days[0]
    elif day not in days:
        # Either a malformed day or one we never archived. Same answer: offer
        # the list rather than a bare 404, since the likely cause is a guessed URL.
        label = admin_view._esc(day)
        return 404, _shell(
            f"{len(days)} archived",
            f'<section><h2>No digest for {label}</h2>'
            '<p class="muted">Nothing archived for that date. Pick one below.</p>'
            "</section>" + _archive_list("", days),
        )

    body = load_digest(data_dir, day)
    if body is None:
        return 404, _shell(
            f"{len(days)} archived",
            "<section><h2>Could not read that digest</h2></section>",
        )

    content = (
        _pager(day, days)
        + f'<div class="digest">{body}</div>'
        + _archive_list(day, days)
    )
    return 200, _shell(f"{days[-1]} to {days[0]} · {len(days)} archived", content)


if __name__ == "__main__":
    import sys

    d = sys.argv[1] if len(sys.argv) > 1 else None
    target = sys.argv[2] if len(sys.argv) > 2 else None
    status, page = render_digest_page(d, target)
    print(f"<!-- status {status} -->")
    print(page)
