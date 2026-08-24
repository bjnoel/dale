"""
Shared snapshot-loading mechanics for the page builders.

Every builder that reads the daily nursery snapshots repeated the same three
steps: walk the nursery subdirectories in sorted order, pick today's dated file
(else fall back to latest.json), and json.load it. That mechanical part is
centralised here as iter_nursery_snapshots(). Each builder keeps its own
per-product filtering and dict-shaping, because those legitimately differ (e.g.
variety pages carry shipping fields; compare pages round prices and prefer the
snapshot's own nursery_name). Forcing one output shape would change pages.

variant_min_price() captures the other repeated snippet: deriving a product's
minimum price from its variants when the snapshot has no explicit min_price.

This module works in raw dicts (what the builders consume) and is deliberately
independent of the typed stocklib.model -- model.py serves the scraper write
boundary and future typed consumers; this serves the existing builders.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def snapshot_path(nursery_dir: Path, today: str | None = None) -> Path | None:
    """Return today's snapshot path for a nursery dir, else latest.json, else None."""
    today = today or _today_utc()
    snap = nursery_dir / f"{today}.json"
    if snap.exists():
        return snap
    fallback = nursery_dir / "latest.json"
    return fallback if fallback.exists() else None


def snapshot_path_for_date(nursery_dir: Path, target_date: str,
                           today: str | None = None, *,
                           distrusted=None) -> Path | None:
    """How a nursery looked on `target_date`, for day-to-day comparisons.

    Exact dated snapshot if we have one. For today, latest.json is at least as
    fresh, so it wins when today's dated file is not written yet. Otherwise the
    most recent snapshot at or before the target date: a nursery whose scrape
    failed has not emptied its shelves, it only failed to report.

    That last fallback is the point of this function. Callers used to skip the
    nursery entirely when a dated file was missing, which silently claimed it
    had *no stock* that day. On 2026-08-13, with Heritage Fruit Trees missing
    two snapshots (their site was 503ing) and Ladybird missing one, that made
    10 watched varieties look like fresh 0 -> in-stock restocks against 98 real
    subscriber watches. None of them had ever gone out of stock (DEC-293).

    Deliberately unbounded: comparing against the last state we actually
    observed is what "back in stock" means to a subscriber. A nursery returning
    after a long outage yields alerts for what genuinely changed since we last
    saw it, which is a real answer, where treating the gap as zero stock is a
    fabricated one. Returns None only when a nursery has no history at or
    before the date, where no claim about stock can honestly be made.

    `distrusted` is an optional callable (day -> bool) for this nursery. A day
    it rejects is treated exactly like a missing snapshot and skipped over, so
    the walk-back lands on the last state we actually believe. That covers the
    failure this function's original fix did not: a scrape that *succeeds* while
    reporting a catalogue we should not trust. On 2026-08-15 Heritage Fruit
    Trees came back from three days of 503s having republished only its
    available stock, 210 products where there had been 375, and every
    out-of-stock line simply deleted rather than marked. 48 kept products
    flipped out-of-stock to in-stock in one hop and one of them, Bramley's
    Seedling Apple, went out to a real subscriber as a restock. The nursery was
    already in untrusted_nurseries() that night. The ledger asked; this path did
    not. Pass stocklib.scrape_health.untrusted_nurseries through here so it does.
    """
    def trusted(day: str) -> bool:
        return distrusted is None or not distrusted(day)

    if trusted(target_date):
        snap = nursery_dir / f"{target_date}.json"
        if snap.exists():
            return snap

        today = today or _today_utc()
        if target_date == today:
            fallback = nursery_dir / "latest.json"
            if fallback.exists():
                return fallback

    prior = sorted(
        p for p in nursery_dir.glob("????-??-??.json") if p.stem <= target_date
    )
    for path in reversed(prior):
        if trusted(path.stem):
            return path
    return None


def iter_nursery_snapshots(data_dir, today: str | None = None) -> Iterator[tuple[str, dict]]:
    """Yield (nursery_key, snapshot_dict) for each nursery under data_dir.

    Nurseries are visited in sorted directory order. For each, today's dated
    snapshot is used if present, else latest.json; nurseries with neither are
    skipped. This is the exact directory-walk + fallback the page builders each
    used to inline, so swapping a builder onto it preserves behaviour.
    """
    today = today or _today_utc()
    for nursery_dir in sorted(Path(data_dir).iterdir()):
        if not nursery_dir.is_dir():
            continue
        path = snapshot_path(nursery_dir, today)
        if path is None:
            continue
        with open(path) as fp:
            yield nursery_dir.name, json.load(fp)


def variant_min_price(product: dict, *, prefer_available: bool = False) -> float | None:
    """Lowest variant price for a product, or None if no variant has a price.

    prefer_available=True: use the lowest *available* variant price when any
    available variant has a price, else fall back to the lowest of all priced
    variants (build_compare_pages' availability-aware behaviour).
    prefer_available=False: lowest of all priced variants (build_location_pages /
    build_species_state_pages behaviour).
    """
    variants = product.get("variants", []) or []
    if prefer_available:
        avail = [float(v["price"]) for v in variants
                 if v.get("price") and v.get("available", True)]
        if avail:
            return min(avail)
    prices = [float(v["price"]) for v in variants if v.get("price")]
    return min(prices) if prices else None


# A nursery is scraped nightly, so a snapshot this old means the scrape has been
# failing for days rather than having one bad night. Three days is deliberately
# short: the point is to stop a page claiming live stock it cannot vouch for,
# and being a day or two early about that costs nothing but a cautious label.
STALE_AFTER_DAYS = 3


def snapshot_age_days(scraped_at: str | None, today: str | None = None) -> int | None:
    """Whole days between a snapshot's `scraped_at` and `today`. None if unreadable.

    None means "cannot tell", and every caller must treat that as fresh rather
    than stale: a page that hides its stock because it could not parse a
    timestamp is worse than one that shows it.
    """
    if not scraped_at:
        return None
    try:
        stamp = datetime.fromisoformat(str(scraped_at).replace("Z", "+00:00")).date()
    except ValueError:
        return None
    today = today or _today_utc()
    try:
        return (date.fromisoformat(today) - stamp).days
    except ValueError:
        return None


def is_stale(scraped_at: str | None, today: str | None = None, *,
             after: int = STALE_AFTER_DAYS) -> bool:
    """True when a snapshot is old enough that its stock must not be called current."""
    age = snapshot_age_days(scraped_at, today)
    return age is not None and age >= after
