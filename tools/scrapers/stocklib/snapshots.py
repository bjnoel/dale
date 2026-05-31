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
from datetime import datetime, timezone
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
