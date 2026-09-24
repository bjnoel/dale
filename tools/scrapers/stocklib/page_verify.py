"""Confirm "in stock" against the product page when a store's API cannot say.

Guildford Garden Centre runs a plugin that blanks a product page with "we are
unable to supply this product and it cannot be placed on backorder", removes
the price and cart button, and hides the product from category listings. The
WooCommerce Store API knows nothing about it: the product, and its only
variation, still report in stock and purchasable at full price. Compared field
by field against buyable Guildford products (2026-09-24), nothing differs. So
the page is the only place the truth lives: 5 of 276 "in stock" products.

Loading every in-stock page nightly would cost ~12 minutes (Guildford serves a
page in ~2.7s), so checks are rationed:

  must     a product that is in stock now but was not in stock in the last
           published snapshot, or has never been checked. This is the "back in
           stock" case, the one that reaches subscribers as an alert, so it is
           checked the same night (up to MUST_CAP).
  rolling  the ROLLING in-stock products checked longest ago, so a product that
           becomes unavailable while staying "in stock" in the API is caught
           within about len(in_stock) / ROLLING nights.

A verdict is remembered per URL in page-checks.json next to the snapshots. A
page that fails to load keeps its previous verdict; a fetch problem is never
evidence either way. Pure apart from the injected `fetch`; no network here.
"""
from __future__ import annotations

import json
from pathlib import Path

from stocklib.jsonio import atomic_write_json

CHECKS_FILE = "page-checks.json"
MUST_CAP = 60
ROLLING = 30


def load_checks(nursery_dir) -> dict:
    path = Path(nursery_dir) / CHECKS_FILE
    try:
        with open(path) as f:
            return json.load(f).get("checks", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def previous_in_stock(nursery_dir) -> set:
    """URLs published as available in the last latest.json (after verification)."""
    try:
        with open(Path(nursery_dir) / "latest.json") as f:
            return {p.get("url") for p in json.load(f).get("products", [])
                    if p.get("any_available")}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def select_urls(products, prev_in_stock, checks, *, must_cap=MUST_CAP, rolling=ROLLING):
    """(must, rolling) URL lists to load tonight."""
    in_stock = [p["url"] for p in products if p.get("any_available") and p.get("url")]
    must = [u for u in in_stock if u not in prev_in_stock or u not in checks][:must_cap]
    chosen = set(must)
    rest = sorted((u for u in in_stock if u not in chosen),
                  key=lambda u: checks.get(u, {}).get("checked", ""))
    return must, rest[:rolling]


def apply_verdicts(products, checks) -> list:
    """Withdraw products whose page says unavailable. Mutates `products`.
    Returns the withdrawn products."""
    withdrawn = []
    for p in products:
        if p.get("any_available") and checks.get(p.get("url"), {}).get("unavailable"):
            p["any_available"] = False
            p["page_unavailable"] = True
            for v in p.get("variants") or []:
                v["available"] = False
            withdrawn.append(p)
    return withdrawn


def verify(products, nursery_dir, marker, fetch, today, *, sleep=None,
           delay=1.5, must_cap=MUST_CAP, rolling=ROLLING) -> dict:
    """Check tonight's pages, persist verdicts, withdraw unavailable products.

    `fetch(url) -> str | None`. Returns stats for the log."""
    nursery_dir = Path(nursery_dir)
    checks = load_checks(nursery_dir)
    must, roll = select_urls(products, previous_in_stock(nursery_dir), checks,
                             must_cap=must_cap, rolling=rolling)
    failed = 0
    for i, url in enumerate(must + roll):
        if i and sleep:
            sleep(delay)
        page = fetch(url)
        if page is None:
            failed += 1
            continue
        checks[url] = {"checked": today, "unavailable": marker in page}

    live = {p.get("url") for p in products}
    checks = {u: c for u, c in checks.items() if u in live}
    atomic_write_json(nursery_dir / CHECKS_FILE, {"marker": marker, "checks": checks})

    withdrawn = apply_verdicts(products, checks)
    return {"must": len(must), "rolling": len(roll), "failed": failed,
            "withdrawn": [p.get("title", p.get("url")) for p in withdrawn]}
