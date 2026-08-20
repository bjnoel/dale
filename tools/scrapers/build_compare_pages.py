#!/usr/bin/env python3
"""
Build price comparison pages for top fruit species.

Each page answers: "Which nursery has the cheapest [species] tree in Australia?"
Target keywords: "[species] tree price australia", "cheapest [species] tree",
                 "compare [species] tree prices", "where to buy [species] tree"

Generates /compare/[species]-prices.html for top species with multi-nursery coverage.

Usage:
    python3 build_compare_pages.py /path/to/nursery-stock /path/to/output/
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

from shipping import SHIPPING_MAP, NURSERY_NAMES, LOCAL_DELIVERY, delivery_label
from stocklib.flags import DIGEST_SIGNUP_ENABLED
from stocklib.snapshots import iter_nursery_snapshots, variant_min_price
from stocklib.structured_data import product_offer_jsonld
from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer, SITE_URL


from stocklib.classify import is_real_product
from stocklib.taxonomy import enabled_species
from stocklib.utm import outbound
from stocklib.category_ui import category_badges_html, is_bush_tucker, CATEGORY_FILTER_CSS
from stocklib.page_ledger import (
    FAMILY_COMPARE, LIVE, REDIRECT, PageLedger, decide_night, write_page,
)
from stocklib.scrape_health import untrusted_nurseries
from stocklib.tombstone import render_stub, stub_head_extras

# Minimum nurseries for a compare page to be useful
MIN_NURSERIES = 3


def load_species() -> list[dict]:
    return enabled_species()


from stocklib.species_match import build_species_lookup, match_title


def load_all_products(data_dir: Path) -> list[dict]:
    """Load all products from today's snapshot (or latest.json fallback)."""
    products = []
    for nursery_key, data in iter_nursery_snapshots(data_dir):
        nursery_name = data.get("nursery_name") or NURSERY_NAMES.get(nursery_key, nursery_key)
        for p in data.get("products", []):
            title = p.get("title", "")
            if not is_real_product(title):
                continue
            min_price = p.get("min_price")
            if min_price is None:
                min_price = variant_min_price(p, prefer_available=True)
            available = p.get("any_available", p.get("available", False))
            url = p.get("url", "")
            products.append({
                "title": title,
                "url": url,
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "price": round(float(min_price), 2) if min_price else None,
                "available": bool(available),
            })
    return products


def group_by_species(products: list[dict], lookup: dict) -> dict:
    by_species = defaultdict(list)
    for p in products:
        sp = match_title(p["title"], lookup)
        if sp:
            by_species[sp["slug"]].append((sp, p))
    # Return dict of slug -> (species_meta, [products])
    result = {}
    for slug, items in by_species.items():
        sp_meta = items[0][0]
        prods = [i[1] for i in items]
        result[slug] = {"species": sp_meta, "products": prods}
    return result


def build_compare_page(species: dict, products: list[dict]) -> str:
    name = species["common_name"]
    latin = species["latin_name"]
    slug = species["slug"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    in_stock = [p for p in products if p["available"] and p["price"]]
    all_priced = [p for p in products if p["price"]]

    # Per-nursery best price
    nursery_best = {}
    for p in products:
        nk = p["nursery_key"]
        if nk not in nursery_best:
            nursery_best[nk] = {
                "name": p["nursery_name"],
                "best_price": None,
                "best_title": None,
                "best_url": None,
                "in_stock_count": 0,
                "total": 0,
                "ships_to": SHIPPING_MAP.get(nk, []),
            }
        nursery_best[nk]["total"] += 1
        if p["available"]:
            nursery_best[nk]["in_stock_count"] += 1
        if p["available"] and p["price"]:
            if nursery_best[nk]["best_price"] is None or p["price"] < nursery_best[nk]["best_price"]:
                nursery_best[nk]["best_price"] = p["price"]
                nursery_best[nk]["best_title"] = p["title"]
                nursery_best[nk]["best_url"] = p["url"]

    # Sort nurseries by best price (in-stock first, then by price)
    sorted_nurseries = sorted(
        nursery_best.items(),
        key=lambda x: (
            x[1]["best_price"] is None or x[1]["in_stock_count"] == 0,
            x[1]["best_price"] or 9999
        )
    )

    # Price stats
    in_stock_prices = [p["price"] for p in in_stock]
    min_price = min(in_stock_prices) if in_stock_prices else None
    max_price = max(in_stock_prices) if in_stock_prices else None

    price_range_str = ""
    if min_price:
        if min_price == max_price:
            price_range_str = f"${min_price:.2f}"
        else:
            price_range_str = f"${min_price:.2f} – ${max_price:.2f}"

    nursery_count = len([nk for nk, n in nursery_best.items() if n["in_stock_count"] > 0])
    total_nurseries = len(nursery_best)

    # Per-nursery comparison rows as view-data. The template autoescapes the
    # scraped title and the utm URL (which carries the & that f-strings left raw).
    nursery_view = []
    for nk, n in sorted_nurseries:
        in_stock_row = bool(n["best_price"] and n["in_stock_count"] > 0)
        utm_url = outbound(n["best_url"], "compare") if in_stock_row else ""
        local_lbl = delivery_label(nk)
        ships = local_lbl if local_lbl else (", ".join(n["ships_to"]) if n["ships_to"] else "Local only")
        nursery_view.append({
            "name": n["name"],
            "in_stock_row": in_stock_row,
            "best_price": n["best_price"],
            "best_title": n["best_title"],
            "utm_url": utm_url,
            "in_stock_count": n["in_stock_count"],
            "ships": ships,
        })

    # Full product listing (in-stock first, then price-sorted) as view-data.
    sorted_products = sorted(products, key=lambda x: (not x["available"], x["price"] or 9999, x["title"]))
    product_view = []
    for p in sorted_products:
        utm_url = outbound(p["url"], "compare")
        product_view.append({
            "url": p["url"],
            "utm_url": utm_url,
            "title": p["title"],
            "nursery_name": p["nursery_name"],
            "price": p["price"],
            "available": p["available"],
        })

    cheapest = None
    if sorted_nurseries and sorted_nurseries[0][1]["best_price"] and sorted_nurseries[0][1]["in_stock_count"] > 0:
        cheapest_n = sorted_nurseries[0][1]
        cheapest = {"name": cheapest_n["name"], "best_price": cheapest_n["best_price"]}

    seo_nurseries = [n["name"] for _, n in sorted_nurseries]

    head = render_head(
        title=f"{name} Tree Price Comparison Australia | treestock.com.au",
        description=f"Compare {name} ({latin}) tree prices across {total_nurseries} Australian nurseries. {len(in_stock)} varieties in stock. {'Prices from ' + price_range_str + ' AUD.' if price_range_str else ''} Updated daily.",
        canonical_url=f"{SITE_URL}/compare/{slug}-prices.html",
        og_title=f"{name} Tree Prices Compared Across {total_nurseries} Australian Nurseries",
        og_description=f"{'From ' + price_range_str if price_range_str else str(len(in_stock)) + ' varieties in stock'} across {nursery_count} nurseries. Compare prices and availability at treestock.com.au",
        jsonld=product_offer_jsonld(
            # Distinct from the species page's Product entity, which is the plain
            # "<Name> Tree". Both pages used to emit that same name against two URLs,
            # which is a duplicate-entity signal on top of the title collision. This
            # node describes what THIS page is: the cross-nursery price comparison.
            name=f"{name} Tree Price Comparison",
            url=f"{SITE_URL}/compare/{slug}-prices.html",
            products=products,
            description=f"Compare {name} ({latin}) tree prices across {total_nurseries} Australian nurseries.",
            include_offers=False,  # compare aggregates a whole species: summary only
        ),
    )
    header = render_header(active_path="/compare/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Compare Prices", "/compare/"), (name, "")])
    footer = render_footer()

    return render_template(
        "compare_page.html.j2",
        digest_signup=DIGEST_SIGNUP_ENABLED,
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        name=name, latin=latin, slug=slug, now=now,
        total_nurseries=total_nurseries, in_stock_count=len(in_stock),
        price_range_str=price_range_str, cheapest=cheapest,
        nursery_view=nursery_view, product_view=product_view,
        seo_nurseries=seo_nurseries,
    )


def build_compare_index(entries: list[dict]) -> str:
    """Build /compare/index.html listing all compare pages."""
    entries_view = []
    for e in sorted(entries, key=lambda x: -x["nursery_count"]):
        sp = e["species"]
        entries_view.append({
            "slug": sp["slug"],
            "common_name": sp["common_name"],
            "latin_name": sp["latin_name"],
            "nursery_count": e["nursery_count"],
            "in_stock": e["in_stock"],
            "min_price": e["min_price"],
            "category": sp.get("category", "fruit"),
            "is_bush_tucker": is_bush_tucker(sp),
            "category_badges_html": category_badges_html(sp),
        })

    head = render_head(
        title="Fruit Tree and Bush Tucker Price Comparisons Across Australian Nurseries | treestock.com.au",
        description=f"Compare fruit tree and Australian bush tucker prices across nurseries. Find the cheapest mango, fig, avocado, lemon, finger lime and more. Updated daily from {len(entries)} species.",
        canonical_url=f"{SITE_URL}/compare/",
        extra_style=CATEGORY_FILTER_CSS,
    )
    header = render_header(active_path="/compare/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Compare Prices", "")])
    footer = render_footer()

    return render_template(
        "compare_index.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        entry_count=len(entries), entries_view=entries_view,
        nursery_count=len(SHIPPING_MAP),
    )


def build_compare_redirect_stub(slug: str, entry: dict) -> str:
    """The stub for a compare page that no longer has enough nurseries to compare.

    A compare page is the only one of the three ledger families with a
    guaranteed-live parent: every enabled species has a /species/<slug>.html,
    so there is always somewhere honest to send the reader. That is why this
    family redirects where the others tombstone. The species page carries the
    same listings plus the varieties, the growing guide and today's prices, so
    the reader is strictly better off there than on a frozen table.

    The copy deliberately does not say "is now listed as", which is the variety
    rename wording: nothing was renamed here, we simply stopped comparing.
    """
    name = entry.get("species_name") or slug.replace("-", " ").title()
    target_href = f"/species/{slug}.html"
    target_url = f"{SITE_URL}{target_href}"
    head = render_head(
        title=f"{name} Trees for Sale Australia | treestock.com.au",
        description=f"{name} tree prices and availability across Australian nurseries.",
        canonical_url=target_url,
        extra_head=stub_head_extras(target_url),
    )
    return render_stub(
        head=head,
        header=render_header(active_path="/compare/"),
        footer=render_footer(),
        title=f"{name} Tree Prices",
        target_title=f"{name} Trees",
        target_href=target_href,
        heading=f"{name} price comparison has moved",
        lede=(f"Too few nurseries are listing {name} to compare prices across them. "
              f"The {name} species page has every current listing, with prices and "
              f"shipping."),
    )


def run_lifecycle(ledger: PageLedger, args, compare_dir: Path, output_dir: Path,
                  today: str, written_keys: set[str]) -> None:
    """Decide what happens to compare pages that were not generated tonight.

    Without this, build_compare_pages never removed a page it stopped writing.
    On 2026-08-20 that left /compare/chinese-bayberry-prices.html live and
    serving prices from 2026-08-11, ranking at position 9.5, with no internal
    link to it: the species had dropped below MIN_NURSERIES and the builder
    simply moved on. Same failure mode build_species_state_pages had before the
    ledger, and the same fix.

    decide_night stays family-agnostic, so it classifies these as tombstones.
    This converts them to redirects, which is the honest terminal state here,
    and only when the species page is really on disk. Nothing is ever deleted:
    decide_night is called without allow_delete, so the below-entry-guard branch
    holds rather than unlinking and plan.removals is always empty. That is
    deliberate for this family. A seeded page carries live_days 0, so running
    with --allow-delete on rollout would delete every orphan on its third night
    instead of redirecting it, and the orphan this was written for ranks at
    position 9.5.

    KNOWN LIMIT: a compare page orphaned before it has ENTRY_GUARD_LIVE_DAYS of
    ledger history is held, not redirected, and stays stale. For a page created
    and abandoned inside a week that is the entry guard working. For a page that
    predates the ledger it is merely conservative, and the fix is to seed it with
    its real dates rather than to loosen the guard.
    """
    untrusted = untrusted_nurseries(today, args.health_dir)
    if untrusted:
        print(f"  Untrusted nurseries tonight: {', '.join(sorted(untrusted))}")

    plan = decide_night(ledger, written_keys, today=today, untrusted=untrusted)

    # Tombstone -> redirect, but never to a page that is not there. A species
    # page missing from disk means something upstream failed tonight, and
    # pointing a live URL at a 404 is worse than leaving the stale table up.
    for slug in list(plan.tombstoned):
        entry = ledger.pages[slug]
        if not (output_dir / "species" / f"{slug}.html").exists():
            entry["state"] = LIVE
            entry["absent_nights"] = 0
            plan.held[slug] = "no species page to redirect to"
            plan.tombstoned.remove(slug)
            ledger.note(slug, "would redirect, but /species page is missing", today)
            continue
        entry["state"] = REDIRECT
        entry["since"] = today
        entry["redirect_to"] = slug
        plan.redirected[slug] = slug
        plan.tombstoned.remove(slug)

    # Printed after the substitution, not before: decide_night classifies these
    # as tombstones and this family turns them into redirects, so a summary
    # taken any earlier reports the opposite of what happens.
    print(f"Page lifecycle: {plan.summary()}")
    for key, reason in sorted(plan.held.items())[:10]:
        print(f"  Held {key}: {reason}")

    if args.dry_run:
        print("  DRY RUN: no ledger written, no stubs rendered")
        return

    rendered = 0
    for slug in ledger.slugs_in_state(REDIRECT):
        html = build_compare_redirect_stub(slug, ledger.pages[slug])
        if write_page(compare_dir / f"{slug}-prices.html", html):
            rendered += 1
    if rendered:
        print(f"  Wrote {rendered} redirect stub(s) "
              f"({len(ledger.slugs_in_state(REDIRECT))} total)")

    ledger.save(args.ledger, today)
    print(f"  Ledger: {len(ledger.pages)} pages, {ledger.live_count()} live")


def seed_from_disk(ledger: PageLedger, compare_dir: Path, today: str) -> int:
    """Create ledger entries for compare pages already on disk.

    Enumerating the filesystem rather than tonight's output is the whole point:
    the page that most needs an entry is the orphan the current stock no longer
    produces. Seeded entries carry no history, so the entry guard holds them for
    a week before anything can happen to them. That is the guard working.
    """
    seeded = 0
    for path in sorted(compare_dir.glob("*-prices.html")):
        slug = path.name[: -len("-prices.html")]
        if slug in ledger.pages:
            continue
        # The file's mtime is the one real fact available about a page the
        # ledger has never seen: the last night the builder wrote it. For a page
        # still being generated that is today, and tonight's observe() takes it
        # from there. For an orphan it is the night it stopped, which is exactly
        # what we want recorded. No history is invented beyond that.
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        last_written = mtime.strftime("%Y-%m-%d")
        ledger.seed(slug, today=today,
                    first_seen=last_written, last_seen=last_written,
                    species_name=slug.replace("-", " ").title())
        seeded += 1
    return seeded


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--ledger", type=Path, default=None,
                        help="page lifecycle ledger. Without it this builder is "
                             "stateless and never retires a page it stops writing")
    parser.add_argument("--dry-run", action="store_true",
                        help="classify and report, but write no ledger and no stubs")
    parser.add_argument("--seed", action="store_true",
                        help="create ledger entries for compare pages already on "
                             "disk. For bootstrapping an empty ledger")
    parser.add_argument("--health-dir", type=Path, default=None,
                        help="scraper health records, for the untrusted-nursery gate")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    data_dir = args.data_dir
    output_dir = args.output_dir
    compare_dir = output_dir / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Opt-in by flag: with no --ledger this builder constructs nothing, retires
    # nothing and behaves exactly as it did before, which is what keeps the
    # golden cases byte-identical.
    ledger = PageLedger.load(args.ledger, FAMILY_COMPARE) if args.ledger else None
    if ledger is not None and args.seed:
        seeded = seed_from_disk(ledger, compare_dir, today)
        print(f"Seeded {seeded} compare page(s) from disk")

    species_list = load_species()
    lookup = build_species_lookup(species_list)
    products = load_all_products(data_dir)

    print(f"Loaded {len(products)} products across all nurseries")

    by_species = group_by_species(products, lookup)

    index_entries = []
    pages_written = 0
    written_keys: set[str] = set()

    for slug, data in by_species.items():
        sp = data["species"]
        prods = data["products"]

        # Count how many unique nurseries have in-stock items
        in_stock_nurseries = set(p["nursery_key"] for p in prods if p["available"])
        all_nurseries = set(p["nursery_key"] for p in prods)

        if len(all_nurseries) < MIN_NURSERIES:
            continue

        in_stock_prods = [p for p in prods if p["available"] and p["price"]]
        min_price = min((p["price"] for p in in_stock_prods), default=None)

        html = build_compare_page(sp, prods)
        out_path = compare_dir / f"{slug}-prices.html"
        with open(out_path, "w") as f:
            f.write(html)

        index_entries.append({
            "species": sp,
            "nursery_count": len(all_nurseries),
            "in_stock": len(in_stock_prods),
            "min_price": min_price,
        })
        pages_written += 1
        written_keys.add(slug)
        if ledger is not None:
            ledger.observe(
                slug, today=today, in_stock=bool(in_stock_prods),
                rows=[{"nursery_key": p["nursery_key"],
                       "nursery_name": p["nursery_name"],
                       "title": p["title"], "price": p["price"],
                       "available": p["available"], "url": p["url"]}
                      for p in prods],
                species_name=sp["common_name"],
            )

    # Write index
    index_html = build_compare_index(index_entries)
    with open(compare_dir / "index.html", "w") as f:
        f.write(index_html)

    print(f"Written {pages_written} compare pages + index to {compare_dir}/")

    if ledger is not None:
        run_lifecycle(ledger, args, compare_dir, output_dir, today, written_keys)


if __name__ == "__main__":
    main()
