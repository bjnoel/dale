"""
Typed domain model for nursery stock snapshots, and a validator.

Until now the product/variant schema was implicit -- defined only by whatever a
scraper happened to emit, documented nowhere, so a malformed product surfaced
only as a broken page days later. This module makes the shape explicit and
machine-checkable:

- Product / Variant / Snapshot dataclasses (the canonical shape).
- normalize_product(): reconciles the two scraper dialects into one shape:
    * variant-based (Daleys, Shopify, WooCommerce): a `variants` list plus
      precomputed `min_price` / `max_price` / `any_available`.
    * flat (Ecwid): a single product-level `price` / `available`, no variants.
  Flat products get a synthesised "Default" variant so downstream code can
  always iterate `variants` uniformly.
- validate_snapshot(): returns a list of human-readable problems ([] == valid).
- validate_and_warn(): validate + log problems to stderr, warn-only (never
  raises), for use at the scraper write boundary.

Stdlib only (dataclasses), matching the project's stdlib-tests convention; no
third-party dependency. validate_snapshot is a pure function, unit-tested in
tests/test_model.py.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Variant:
    title: str = "Default"
    price: float | None = None
    sku: str | None = None
    id: str | None = None
    available: bool = False
    stock_count: int | None = None


@dataclass
class Product:
    title: str
    url: str
    nursery: str
    available: bool
    min_price: float | None = None
    max_price: float | None = None
    currency: str = "AUD"
    category_raw: str = ""          # the nursery's own category/type string, verbatim
    on_sale: bool = False
    variants: list[Variant] = field(default_factory=list)


@dataclass
class Snapshot:
    nursery: str
    nursery_name: str
    scraped_at: str
    products: list[Product] = field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict) -> "Snapshot":
        nursery = raw.get("nursery", "")
        return cls(
            nursery=nursery,
            nursery_name=raw.get("nursery_name", ""),
            scraped_at=raw.get("scraped_at", ""),
            products=[normalize_product(p, nursery) for p in raw.get("products", []) or []],
        )


def normalize_product(raw: dict, nursery: str | None = None) -> Product:
    """Turn a raw scraped product dict (either dialect) into a canonical Product."""
    variants = [
        Variant(
            title=v.get("title", "Default"),
            price=_as_float(v.get("price")),
            sku=v.get("sku"),
            id=(str(v["id"]) if v.get("id") is not None else None),
            available=bool(v.get("available", False)),
            stock_count=v.get("stock_count"),
        )
        for v in (raw.get("variants") or [])
    ]
    # Flat dialect (Ecwid): synthesise one variant so callers can always iterate.
    if not variants:
        flat_price = _as_float(raw.get("price"))
        if flat_price is not None or "available" in raw:
            variants = [Variant(
                title="Default",
                price=flat_price,
                sku=raw.get("sku") or None,
                available=bool(raw.get("available", False)),
            )]

    if "any_available" in raw:
        available = bool(raw["any_available"])
    elif "available" in raw:
        available = bool(raw["available"])
    else:
        available = any(v.available for v in variants)

    variant_prices = [v.price for v in variants if v.price is not None]
    min_price = _as_float(raw.get("min_price"))
    if min_price is None:
        min_price = min(variant_prices) if variant_prices else _as_float(raw.get("price"))
    max_price = _as_float(raw.get("max_price"))
    if max_price is None:
        max_price = max(variant_prices) if variant_prices else _as_float(raw.get("price"))

    return Product(
        title=(raw.get("title") or "").strip(),
        url=raw.get("url", ""),
        nursery=nursery or raw.get("nursery", ""),
        available=available,
        min_price=min_price,
        max_price=max_price,
        currency=raw.get("currency", "AUD") or "AUD",
        category_raw=(raw.get("category") or raw.get("product_type") or ""),
        on_sale=bool(raw.get("on_sale", False)),
        variants=variants,
    )


def validate_snapshot(raw: dict) -> list[str]:
    """Return a list of problems with a raw snapshot dict. Empty list == valid.

    Pure function: no I/O, no raising. Catches the silent-malformed-scraper-output
    failure mode (missing title/url, no availability signal, bad price).
    """
    problems: list[str] = []
    if not raw.get("nursery"):
        problems.append("missing 'nursery' key")
    if "products" not in raw:
        problems.append("missing 'products' key")
        return problems
    if not isinstance(raw["products"], list):
        problems.append("'products' is not a list")
        return problems

    for i, p in enumerate(raw["products"]):
        label = (p.get("title") or p.get("url") or f"index {i}")
        if not p.get("title"):
            problems.append(f"product[{i}] missing title")
        if not p.get("url"):
            problems.append(f"product '{label}' missing url")
        has_availability = ("any_available" in p) or ("available" in p) or bool(p.get("variants"))
        if not has_availability:
            problems.append(f"product '{label}' has no availability signal")
        price = p.get("min_price", p.get("price"))
        if price is not None and (not isinstance(price, (int, float)) or price < 0):
            problems.append(f"product '{label}' has invalid price {price!r}")
    return problems


def validate_and_warn(raw: dict, source: str = "", stream=sys.stderr) -> list[str]:
    """Validate a snapshot and print any problems to stderr. Warn-only; never raises.

    Call this at the scraper write boundary so a malformed snapshot is logged
    (and visible in the cron log) without failing the pipeline.
    """
    problems = validate_snapshot(raw)
    tag = source or raw.get("nursery", "?")
    for p in problems:
        print(f"WARN[{tag}]: snapshot {p}", file=stream)
    return problems
