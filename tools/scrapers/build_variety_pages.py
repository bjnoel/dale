#!/usr/bin/env python3
"""
Build cultivar/variety-level pages for treestock.com.au.

Each page answers: "Where can I buy [Cultivar Name] in Australia?"
Targets high-intent searches like "buy Hass avocado tree australia",
"Grimal jaboticaba for sale", "R2E2 mango tree price australia".

Generates /variety/[slug].html for all cultivar-level products
(products with "Species - Variety" or "Species – Variety" format).

Also generates /variety/index.html listing all cultivar pages.

Usage:
    python3 build_variety_pages.py <data_dir> <output_dir> [--ledger PATH]

Without --ledger the builder is stateless and never deletes: it writes tonight's
pages and leaves everything else alone. With one, it keeps a lifecycle record
(stocklib/page_ledger.py) and a slug that stops being generated becomes a
tombstone or a redirect stub instead of a 404. See docs/page-lifecycle-plan.md.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

from shipping import SHIPPING_MAP, NURSERY_NAMES, restriction_warning, delivery_label
from stocklib.flags import DIGEST_SIGNUP_ENABLED
from stocklib.page_ledger import (
    FAMILY_VARIETY, LIVE, REDIRECT, TOMBSTONE, PageLedger, decide_night,
    page_state_meta, write_page,
)
from stocklib.scrape_health import untrusted_nurseries
from stocklib.snapshots import iter_nursery_snapshots
from stocklib.structured_data import product_offer_jsonld
from stocklib.templates import render as render_template
from stocklib.tombstone import render_stub, render_tombstone, stub_head_extras
from stocklib.variety_descriptions import has_description, render_blurb
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer, render_treesmith_promo, SITE_URL

NURSERY_URLS = {
    "daleys": "https://www.daleysfruit.com.au",
    "ross-creek": "https://www.rosscreektropicals.com.au",
    "ladybird": "https://ladybird.com.au",
    "fruitopia": "https://fruitopia.com.au",
    "primal-fruits": "https://primalfruits.com.au",
    "guildford": "https://guildfordgardencentre.com.au",
    "fruit-salad-trees": "https://www.fruitsaladtrees.com.au",
    "diggers": "https://www.diggers.com.au",
    "all-season-plants-wa": "https://allseasonplantswa.com.au",
    "ausnurseries": "https://www.ausnurseries.com",
    "fruit-tree-cottage": "https://www.fruittreecottage.com.au",
}

from stocklib.classify import NON_PLANT_KEYWORDS, is_real_product


from cultivar_parsing import (  # noqa: E402
    slugify, parse_cultivar, extract_type_label, canonical_cultivar,
    group_by_cultivar, GRANDFATHERED_VARIETY_SLUGS,
)
from stocklib.taxonomy import load_species
from stocklib.category_ui import category_badges_html, is_bush_tucker, CATEGORY_FILTER_CSS
from stocklib.utm import outbound
from stocklib.variety_index import DEFAULT_INDEX_PATH, write_variety_index

# Canonical species name -> the /species/ page slug from the taxonomy record
# (slugify("Davidson's Plum") gives davidson-s-plum; the record says
# davidsons-plum, which is the file build_species_pages actually writes).
_SPECIES_PAGE_SLUG = {r["common_name"]: r["slug"] for r in load_species()}

# Canonical species name -> full taxonomy record (for the category badge/filter).
_SPECIES_BY_NAME = {r["common_name"]: r for r in load_species()}


def species_page_slug(name: str) -> str:
    return _SPECIES_PAGE_SLUG.get(name) or slugify(name)


def visible_type_label(type_label: str, variety: str) -> str:
    """Drop pill parts whose text already appears in the variety name, so the
    banana 'Dwarf Cavendish' page shows no redundant Dwarf pill (DEC-177)."""
    if not type_label:
        return ""
    vlow = variety.lower()
    parts = [
        p for p in (s.strip() for s in type_label.split(","))
        if p and p.lower() not in vlow
    ]
    return ", ".join(parts)


def load_all_products(data_dir: Path) -> list[dict]:
    """Load all products from today's or latest snapshot."""
    products = []
    for nursery_key, data in iter_nursery_snapshots(data_dir):
        nursery_name = NURSERY_NAMES.get(nursery_key, nursery_key)
        restrict = "" if delivery_label(nursery_key) else restriction_warning(nursery_key)

        raw_products = data.get("products", [])
        for p in raw_products:
            title = p.get("title", "").strip()
            title_lower = title.lower()
            # Skip non-plant items and seed packets
            if not is_real_product(title):
                continue
            products.append({
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "title": title,
                "type_label": extract_type_label(title),
                "url": p.get("url", ""),
                "price": p.get("min_price") or 0,
                "available": p.get("any_available", False),
                "restrict": restrict,
                "ships_states": SHIPPING_MAP.get(nursery_key, []),
            })
    return products


def build_variety_page(slug: str, data: dict, valid_species_slugs: set[str],
                       state_meta: str = "") -> str:
    """Build HTML for a single cultivar page.

    `state_meta` is the page-state declaration the sitemap reads. It is empty
    unless a ledger is in play: without one this builder has no page states, and
    declaring `live` would be declaring something it does not know.
    """
    title = data["title"]
    species = data["species"]
    variety = data["variety"]
    products = data["products"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Sort: in-stock first, then by price
    in_stock = [p for p in products if p["available"] and p["price"]]
    out_stock = [p for p in products if not p["available"] or not p["price"]]
    in_stock.sort(key=lambda p: p["price"])

    cheapest = in_stock[0] if in_stock else None

    # Build product rows
    # Row view-data. The template autoescapes the scraped nursery name, the
    # product URL and the ships-to states; restrict_div is a prebuilt fragment
    # over the curated restriction warning (|safe).
    product_view = []
    for p in in_stock + out_stock:
        local_lbl = delivery_label(p["nursery_key"])
        states = local_lbl if local_lbl else (", ".join(p["ships_states"]) if p["ships_states"] else "—")
        nursery_url = NURSERY_URLS.get(p["nursery_key"], "#")
        restrict_div = (
            f'<div class="text-xs"><span class="text-xs text-red-600">{p["restrict"]}</span></div>'
            if p["restrict"] else ""
        )
        product_view.append({
            "product_link": outbound(p["url"] or (nursery_url if nursery_url != "#" else ""), "variety-page") or "#",
            "nursery_name": p["nursery_name"],
            "type_label": visible_type_label(p["type_label"], variety),
            "restrict_div": restrict_div,
            "price_str": f"${p['price']:.2f}" if p["price"] else "—",
            "available": p["available"],
            "states": states,
        })

    # Summary callouts
    summary_parts = []
    if cheapest:
        summary_parts.append(
            f'<span class="font-medium">Cheapest:</span> '
            f'{cheapest["nursery_name"]} at ${cheapest["price"]:.2f}'
        )

    summary_html = " &nbsp;·&nbsp; ".join(summary_parts) if summary_parts else ""
    summary_callout = (
        "<div class='bg-green-50 border border-green-200 rounded-lg px-4 py-3 mb-6 text-sm text-green-900'>"
        + summary_html + "</div>"
    ) if summary_html else ""

    in_stock_count = len(in_stock)
    nursery_count = len(set(p["nursery_key"] for p in products))
    species_slug = species_page_slug(species)
    # Optional verified "what's unique about this variety" blurb, rendered under the
    # meta line and above the price table. Empty string for un-enriched varieties.
    blurb_html = render_blurb(slug, species_slug) if has_description(slug, species_slug) else ""
    variety_title = f"{species} - {variety}"
    # Escape single quotes for safe embedding in JS string literals
    variety_title_js = variety_title.replace("'", "\\'")
    slug_js = slug.replace("'", "\\'")
    species_slug_js = species_slug.replace("'", "\\'")

    meta_desc = (
        f"Find {title} trees for sale in Australia. "
        f"Compare prices across {nursery_count} nurseries. "
        f"{in_stock_count} nurseries currently in stock. Updated daily."
    )

    head = render_head(
        title=f"Buy {title} Trees in Australia, Prices & Availability | treestock.com.au",
        description=meta_desc,
        canonical_url=f"https://treestock.com.au/variety/{slug}.html",
        og_title=f"Buy {title} Trees in Australia",
        og_description=meta_desc,
        og_type="product",
        jsonld=product_offer_jsonld(
            name=title,
            url=f"https://treestock.com.au/variety/{slug}.html",
            products=products,
            description=meta_desc,
        ),
        extra_head=state_meta,
    )
    header = render_header(active_path="/variety/")
    species_href = f"/species/{species_slug}.html" if species_slug in valid_species_slugs else ""
    breadcrumb = render_breadcrumb([
        ("Home", "/"), ("Varieties", "/variety/"),
        (species, species_href), (variety, ""),
    ])
    footer = render_footer()

    other_varieties_html = (f'''<p class="mt-2">
      Looking for other {species} varieties?
      <a href="/species/{species_slug}.html" class="underline text-green-700">See all {species} options &rarr;</a>
    </p>''' if species_slug in valid_species_slugs else "")

    return render_template(
        "variety_page.html.j2",
        digest_signup=DIGEST_SIGNUP_ENABLED,
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        treesmith_promo=render_treesmith_promo("variety"),
        title=title, today=today, nursery_count=nursery_count, in_stock_count=in_stock_count,
        blurb_html=blurb_html,
        summary_callout=summary_callout, product_view=product_view,
        # One watch fires on BOTH triggers, so say so on both sides of the
        # in-stock split. The old copy promised only a restock, which was the
        # wrong promise in the in-stock case (where a price drop is the alert
        # you actually want) and an incomplete one everywhere else.
        watch_heading=(f"Alert me about {variety} {species}" if in_stock
                       else f"Get notified when {variety} {species} comes back"),
        watch_body=(f"{variety} {species} is in stock now. Set an alert and we'll email you "
                    f"if the price drops, or next time it sells out and returns."
                    if in_stock else
                    f"{variety} {species} is currently out of stock. Enter your email and we'll "
                    f"tell you the moment it's available again, or if it comes back cheaper."),
        other_varieties_html=other_varieties_html,
        slug_js=slug_js, species_slug_js=species_slug_js, variety_title_js=variety_title_js,
    )


def build_tombstone_page(slug: str, entry: dict, valid_species_slugs: set[str],
                         siblings: list[dict]) -> str:
    """Build the page for a variety no nursery is listing any more.

    The same template as a live page, with three differences: no "Updated" line
    (its facts stopped changing), the tombstone block below the blurb, and the
    last-known rows linking to the nursery rather than to a dead product URL.

    No Product JSON-LD. A tombstone that advertises a price nobody can pay is
    both a lie and a structured-data violation, and it is exactly what would
    happen if someone later fed the stored `price` into the offer builder.

    The watch form below is unchanged and still posts to /api/watch-variety.
    That is the entire point of keeping the URL: unavailability is when the
    signup is worth most (DEC-294).
    """
    title = entry.get("title") or slug
    species = entry.get("species") or ""
    variety = entry.get("variety") or title
    species_slug = entry.get("species_slug") or species_page_slug(species)
    rows = entry.get("rows") or []

    # Last known listings. The nursery name links to our own nursery page: the
    # product URL is dead by definition, and sending a reader to a 404 on
    # someone else's site is worse than not linking at all.
    product_view = [
        {
            "product_link": f"/nursery/{r.get('nursery_key', '')}.html",
            "nursery_name": r.get("nursery_name") or r.get("nursery_key") or "",
            "type_label": visible_type_label(r.get("type_label", ""), variety),
            "restrict_div": "",
            "price_str": f"${float(r['price']):.2f}" if r.get("price") else "—",
            "available": False,
            "states": r.get("states") or "—",
        }
        for r in rows
    ]

    in_stock_siblings = [s for s in siblings if s.get("in_stock")]
    cta_html = ""
    if in_stock_siblings:
        links = ", ".join(
            f'<a href="/variety/{s["slug"]}.html" class="underline text-green-800">'
            f'{s["variety"]}</a>'
            for s in in_stock_siblings[:8]
        )
        cta_html = f"<p>Other {species} varieties in stock now: {links}</p>"

    blurb_html = render_blurb(slug, species_slug) if has_description(slug, species_slug) else ""

    meta_desc = (
        f"{title} is not currently listed by any Australian nursery we track. "
        f"See its last known price and availability, and get an alert when it "
        f"comes back into stock."
    )
    head = render_head(
        title=f"Buy {title} Trees in Australia, Prices & Availability | treestock.com.au",
        description=meta_desc,
        canonical_url=f"https://treestock.com.au/variety/{slug}.html",
        og_title=f"Buy {title} Trees in Australia",
        og_description=meta_desc,
        og_type="product",
        extra_head=page_state_meta(TOMBSTONE),
    )
    species_href = f"/species/{species_slug}.html" if species_slug in valid_species_slugs else ""
    other_varieties_html = (f'''<p class="mt-2">
      Looking for other {species} varieties?
      <a href="/species/{species_slug}.html" class="underline text-green-700">See all {species} options &rarr;</a>
    </p>''' if species_slug in valid_species_slugs else "")

    return render_template(
        "variety_page.html.j2",
        digest_signup=DIGEST_SIGNUP_ENABLED,
        head=head,
        header=render_header(active_path="/variety/"),
        breadcrumb=render_breadcrumb([
            ("Home", "/"), ("Varieties", "/variety/"),
            (species, species_href), (variety, ""),
        ]),
        footer=render_footer(),
        treesmith_promo=render_treesmith_promo("variety"),
        title=title, today="", nursery_count=0, in_stock_count=0,
        blurb_html=blurb_html,
        summary_callout="",
        # "Mahan (B) Pecan", not the canonical "Pecan - Mahan (B)": the callout
        # is a sentence, and the same reading the watch copy below already uses.
        tombstone_html=render_tombstone(
            f"{variety} {species}".strip() or title, entry, cta_html=cta_html),
        product_view=product_view,
        watch_heading=f"Tell me when {variety} {species} is back",
        watch_body=(
            f"No nursery we track is listing {variety} {species} at the moment. "
            f"Enter your email and we'll tell you the moment one does."),
        other_varieties_html=other_varieties_html,
        slug_js=slug.replace("'", "\\'"),
        species_slug_js=species_slug.replace("'", "\\'"),
        variety_title_js=title.replace("'", "\\'"),
    )


def build_redirect_stub(slug: str, entry: dict, target_slug: str,
                        target_title: str) -> str:
    """Build the stub for a slug whose products now live under another one."""
    title = entry.get("title") or slug
    target_url = f"https://treestock.com.au/variety/{target_slug}.html"
    head = render_head(
        title=f"{title} is now listed as {target_title} | treestock.com.au",
        description=f"{title} is now tracked as {target_title}.",
        canonical_url=target_url,
        extra_head=stub_head_extras(target_url),
    )
    return render_stub(
        head=head,
        header=render_header(active_path="/variety/"),
        footer=render_footer(),
        title=title,
        target_title=target_title,
        target_href=f"/variety/{target_slug}.html",
    )


def build_variety_index(entries: list[dict], valid_species_slugs: set[str]) -> str:
    """Build /variety/index.html listing all cultivar pages.

    valid_species_slugs is the set of species slugs that have a real
    /species/<slug>.html page; anything else renders as plain text rather
    than a broken link (e.g. "Sapodilla Grafted" — parse_cultivar can't
    distinguish a propagation-method prefix from the canonical species name).
    """
    # Group by species for easier browsing
    by_species = defaultdict(list)
    for e in entries:
        by_species[e["species"]].append(e)

    # Per-species section view-data. The template autoescapes the scraped
    # variety and species names in both the visible links and the data-var /
    # data-sp filter attributes (the manual &quot; escaping is gone -- autoescape
    # now covers ", & and < in those attributes).
    species_view = []
    for sp in sorted(by_species.keys()):
        varieties = sorted(by_species[sp], key=lambda x: x["variety"])
        sp_slug = species_page_slug(sp)
        row_view = [
            {
                "var_lower": v["variety"].lower(),
                "slug": v["slug"],
                "variety": v["variety"],
                "n_count": v["nursery_count"],
                "in_s": v["in_stock"],
                "price": f'${v["min_price"]:.2f}' if v["min_price"] else "—",
                "states": " ".join(v.get("states", [])),
            }
            for v in varieties
        ]
        sp_heading = (
            f'<a href="/species/{sp_slug}.html" class="hover:underline">{sp}</a>'
            if sp_slug in valid_species_slugs else sp
        )
        record = _SPECIES_BY_NAME.get(sp, {})
        species_view.append({
            "sp_heading": sp_heading,
            "sp_slug": sp_slug,
            "sp_lower": sp.lower(),
            "variety_count": len(varieties),
            "in_stock_count": sum(v["in_stock"] for v in varieties),
            "rows": row_view,
            "category": record.get("category", "fruit"),
            "is_bush_tucker": is_bush_tucker(record),
            "badges_html": category_badges_html(record),
        })

    total_varieties = len(entries)
    total_in_stock = sum(e["in_stock"] for e in entries)

    head = render_head(
        title="Fruit Tree and Bush Tucker Varieties for Sale in Australia | treestock.com.au",
        description=f"Browse {total_varieties} named fruit tree and Australian bush tucker varieties from nurseries. Find Hass avocado, R2E2 mango, Grimal jaboticaba, Brown Turkey fig and more. Compare prices and check availability. Updated daily.",
        canonical_url=f"{SITE_URL}/variety/",
        extra_style=CATEGORY_FILTER_CSS,
    )
    header = render_header(active_path="/variety/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Varieties", "")])
    footer = render_footer()

    return render_template(
        "variety_index.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        total_varieties=total_varieties, total_in_stock=total_in_stock,
        species_count=len(by_species), species_view=species_view,
    )


def slug_for_title(title: str) -> str | None:
    """The variety slug a raw nursery title maps to, or None if it maps to no
    page (species-only listing, or out of the /variety/ taxonomy)."""
    parsed = parse_cultivar(title)
    if not parsed:
        return None
    canon = canonical_cultivar(*parsed, title)
    return canon[2] if canon else None


def retired_check(slug: str, entry: dict) -> str | None:
    """Has this variety left the taxonomy, rather than merely gone out of stock?

    Asks the current parser about the raw product titles we stored, which is why
    rows carry them. Deliberately not asked of the canonical title: that string
    is the parser's own output, and feeding output back through the parser to
    decide whether to delete a URL is a circular test with an irreversible
    result.

    No stored titles means no evidence, and no evidence means no deletion. The
    caller tombstones instead, which is the reversible outcome.
    """
    titles = [r.get("title") for r in (entry.get("rows") or []) if r.get("title")]
    if not titles:
        return None
    if any(slug_for_title(t) is not None for t in titles):
        return None
    return "no longer resolves to a variety page (taxonomy gate or a deny)"


def seed_from_availability(ledger: PageLedger, data_dir: Path, today: str) -> int:
    """Backdate ledger entries from the per-nursery availability history.

    Night one with an empty ledger would otherwise hold every page below the
    entry guard for a week, and a page that has been live since March would look
    exactly like one built for the first time tonight. availability.json records
    per-product, per-day in-stock history keyed by product URL, carrying the
    scraped title on each record, so the dates are real rather than
    reconstructed.

    Good archaeology, and still the wrong primary source: the only identity it
    holds is that scraped title, so it re-derives the slug under the current
    parser, which is the bug class this whole change exists to fix. Used once,
    at bootstrap.
    """
    history: dict[str, dict] = {}
    for nursery_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        avail_file = nursery_dir / "availability.json"
        if not avail_file.exists():
            continue
        try:
            with open(avail_file) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"  WARNING: unreadable {avail_file}: {e}")
            continue
        # Keyed by product URL, or `<url>|sku:…` / `|id:…` / `|v:…` per variant
        # (availability_tracker.py builds them). The scraped title is a field of
        # the record, so several variant keys can carry the same title and
        # aggregate into one slug below.
        for record in (data.get("products") or {}).values():
            slug = slug_for_title(record.get("title") or "")
            if not slug:
                continue
            agg = history.setdefault(slug, {"days": set(), "in_stock": set()})
            for day, entry in (record.get("days") or {}).items():
                agg["days"].add(day)
                if entry.get("a"):
                    agg["in_stock"].add(day)

    seeded = 0
    for slug, agg in history.items():
        entry = ledger.pages.get(slug)
        # Only bootstrap: an entry with real history of its own is the better
        # record, and overwriting it with re-parsed archaeology would lose the
        # identity the ledger exists to hold.
        if entry and not (entry.get("first_seen") == today or entry.get("seeded")):
            continue
        days = sorted(agg["days"])
        in_stock = sorted(agg["in_stock"])
        if not days:
            continue
        ledger.seed(
            slug, today=today,
            first_seen=days[0],
            last_seen=max(days[-1], today if entry else days[-1]),
            live_days=len(days),
            in_stock_days=len(in_stock),
            last_in_stock=in_stock[-1] if in_stock else None,
        )
        seeded += 1
    return seeded


def run_lifecycle(ledger: PageLedger, args, data_dir: Path, variety_dir: Path,
                  today: str, written_slugs: set[str],
                  url_to_slug: dict[str, str], valid_species_slugs: set[str],
                  siblings_by_species: dict[str, list[dict]],
                  canonical_titles: dict[str, str]) -> None:
    """Classify the slugs that were not generated tonight, then render them.

    Runs after the live pages are written, so a resurrected slug has already
    overwritten its own tombstone or stub at the same path. That ordering is
    what makes resurrection need no cleanup and have no race: a generated slug
    always wins.
    """
    if args.seed:
        print(f"Seeded {seed_from_availability(ledger, data_dir, today)} "
              f"ledger entries from availability history")

    untrusted = untrusted_nurseries(today, args.health_dir)
    if untrusted:
        print(f"Untrusted nurseries tonight: {', '.join(sorted(untrusted))}")

    plan = decide_night(
        ledger, written_slugs, today=today, untrusted=untrusted,
        url_to_slug=url_to_slug, retired_check=retired_check,
        allow_delete=args.allow_delete and not args.dry_run,
    )
    print(f"Page lifecycle: {plan.summary()}")
    if ledger.resurrected:
        print(f"  Resurrected {len(ledger.resurrected)}: "
              f"{', '.join(ledger.resurrected[:10])}")
    for slug, reason in sorted(plan.held.items())[:10]:
        print(f"  Held {slug}: {reason}")

    if args.dry_run:
        print("  DRY RUN: no ledger written, no tombstones rendered, "
              "nothing deleted")
        return

    # Every tombstone is re-rendered nightly, not just tonight's new ones.
    # Otherwise a nav or footer change would reach every page on the site except
    # the tombstones, forever. write_page skips the write when the bytes are
    # unchanged, so their mtimes stay still and their sitemap <lastmod> starts
    # telling the truth.
    rendered = 0
    for slug in ledger.slugs_in_state(TOMBSTONE):
        entry = ledger.pages[slug]
        siblings = siblings_by_species.get(entry.get("species") or "", [])
        html = build_tombstone_page(slug, entry, valid_species_slugs, siblings)
        if write_page(variety_dir / f"{slug}.html", html):
            rendered += 1
        # A tombstone keeps its working watch form, so its slug MUST stay in the
        # canonical title map: the subscribe server rejects a watch on a slug
        # the index does not know. Leaving it out would put a form on the page
        # that 404s on submit, which is the exact DEC-294 failure the tombstone
        # exists to avoid.
        canonical_titles[slug] = entry.get("title") or slug

    # Redirect stubs, re-resolved nightly so a chain A -> B -> C never leaves a
    # stub pointing at another stub.
    stubs = 0
    for slug, target in ledger.resolve_redirects(today).items():
        target_entry = ledger.pages.get(target) or {}
        target_title = target_entry.get("title") or canonical_titles.get(target) or target
        html = build_redirect_stub(slug, ledger.pages[slug], target, target_title)
        if write_page(variety_dir / f"{slug}.html", html):
            stubs += 1
    print(f"  Wrote {rendered} tombstone(s) and {stubs} stub(s) "
          f"({len(ledger.slugs_in_state(TOMBSTONE))} tombstones total)")

    for slug in plan.removals:
        (variety_dir / f"{slug}.html").unlink(missing_ok=True)
    if plan.removals:
        print(f"  Deleted {len(plan.removals)}: {', '.join(plan.removals[:10])}")

    ledger.save(args.ledger, today)
    print(f"  Ledger: {len(ledger.pages)} pages, {ledger.live_count()} live, "
          f"{ledger.skipped_nights} skipped night(s) recorded")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build /variety/<slug>.html pages for treestock.com.au")
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--index-out", type=Path, default=DEFAULT_INDEX_PATH,
                        help="where to write the canonical slug -> title map "
                             "the subscribe server reads")
    parser.add_argument("--ledger", type=Path, default=None,
                        help="page lifecycle ledger. Without it this builder is "
                             "stateless: no tombstones, no redirects, no deletes")
    parser.add_argument("--allow-delete", action="store_true",
                        help="permit the two irreversible outcomes (a retired "
                             "variety, and a page that never met the entry "
                             "guard). Everything else is reversible without it")
    parser.add_argument("--dry-run", action="store_true",
                        help="build pages as usual, report what the lifecycle "
                             "would do, but write no ledger, no tombstones and "
                             "delete nothing")
    parser.add_argument("--seed", action="store_true",
                        help="backdate ledger entries from availability.json. "
                             "For bootstrapping an empty ledger")
    parser.add_argument("--health-dir", type=Path, default=None,
                        help="scraper-health records, for the untrusted-nursery "
                             "gate (defaults to the DALE_DATA_DIR location)")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    index_out = args.index_out
    data_dir = args.data_dir
    output_dir = args.output_dir
    variety_dir = output_dir / "variety"
    variety_dir.mkdir(parents=True, exist_ok=True)

    # Species pages are built before variety pages by run-all-scrapers.sh.
    # Use the resulting filenames as the source of truth for which species
    # slugs are linkable (parse_cultivar's species portion can include
    # propagation prefixes like "Sapodilla Grafted" that have no species page).
    species_dir = output_dir / "species"
    valid_species_slugs = (
        {p.stem for p in species_dir.glob("*.html") if p.stem != "index"}
        if species_dir.exists() else set()
    )
    print(f"Loaded {len(valid_species_slugs)} valid species slugs from {species_dir}")

    products = load_all_products(data_dir)
    print(f"Loaded {len(products)} products")

    groups = group_by_cultivar(products)
    print(f"Found {len(groups)} distinct cultivar names")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ledger = (PageLedger.load(args.ledger, FAMILY_VARIETY)
              if args.ledger else None)
    state_meta = page_state_meta(LIVE) if ledger else ""

    index_entries = []
    # slug -> canonical title for EVERY page written, grandfathered ones
    # included. This is what the subscribe server and the alert sender read
    # instead of trusting a client-supplied title; a grandfathered slug is
    # excluded from the browsable index below but still has live watchers whose
    # alerts have to name the variety.
    canonical_titles: dict[str, str] = {}
    pages_written = 0
    written_slugs = set()
    # Tonight's product URL -> the slug carrying it. This is what turns "the
    # slug is gone" into "its products are listed over there" without the
    # ledger knowing anything about parsing.
    url_to_slug: dict[str, str] = {}
    siblings_by_species: dict[str, list[dict]] = defaultdict(list)

    for slug, data in groups.items():
        prods = data["products"]
        in_stock = [p for p in prods if p["available"] and p["price"]]
        all_nurseries = set(p["nursery_key"] for p in prods)
        min_price = min((p["price"] for p in in_stock), default=None)

        html = build_variety_page(slug, data, valid_species_slugs, state_meta)
        write_page(variety_dir / f"{slug}.html", html)
        written_slugs.add(slug)
        canonical_titles[slug] = data["title"]
        pages_written += 1

        if ledger:
            for p in prods:
                if p.get("url"):
                    url_to_slug[p["url"]] = slug
            siblings_by_species[data["species"]].append({
                "slug": slug, "variety": data["variety"],
                "in_stock": bool(in_stock),
            })
            # Rows carry the raw product title as well as the display fields:
            # the retired check asks the parser about those titles, and asking
            # it about our own canonical title instead would be circular.
            ledger.observe(
                slug, today=today,
                in_stock=bool(in_stock),
                rows=[{
                    "nursery_key": p["nursery_key"],
                    "nursery_name": p["nursery_name"],
                    "title": p["title"],
                    "price": p["price"],
                    "available": p["available"],
                    "url": p["url"],
                    "states": ", ".join(p["ships_states"]) if p["ships_states"] else "",
                    "type_label": p["type_label"],
                } for p in sorted(prods, key=lambda p: (not p["available"],
                                                        p["price"] or 0))],
                title=data["title"], species=data["species"],
                variety=data["variety"],
                species_slug=species_page_slug(data["species"]),
            )

        # Grandfathered non-fruit pages exist only to keep their subscribers'
        # restock alerts alive (DEC-195); they stay out of the browsable index.
        if slug in GRANDFATHERED_VARIETY_SLUGS:
            continue

        index_entries.append({
            "slug": slug,
            "title": data["title"],
            "species": data["species"],
            "variety": data["variety"],
            "nursery_count": len(all_nurseries),
            "in_stock": len(in_stock),
            "min_price": min_price,
            "states": sorted({st for p in prods for st in p["ships_states"]}),
        })

    # The unlink loop that used to live here is gone. It deleted any page whose
    # slug was not generated tonight, which is right for the case it was written
    # for (the parser tightens and a slug stops being emitted) and wrong for the
    # two that dominate: 1,546 delete/recreate events in 165 days, 1,312 of them
    # a page gone for exactly one night, and renames that left nothing behind.
    # Deletion now happens only through the ledger's plan, and only with
    # --allow-delete. Without --ledger this builder does not delete at all.
    if ledger:
        run_lifecycle(ledger, args, data_dir, variety_dir, today, written_slugs,
                      url_to_slug, valid_species_slugs, siblings_by_species,
                      canonical_titles)
    else:
        stale = [p for p in variety_dir.glob("*.html")
                 if p.stem != "index" and p.stem not in written_slugs]
        if stale:
            print(f"Left {len(stale)} page(s) in place that were not generated "
                  f"tonight (no --ledger, so no lifecycle decision to make)")

    # Write index
    index_html = build_variety_index(index_entries, valid_species_slugs)
    write_page(variety_dir / "index.html", index_html)

    print(f"Written {pages_written} variety pages + index to {variety_dir}/")

    # Canonical slug -> title map for the subscribe server and the alert
    # sender. Goes to the server's state dir, not the web root: it is state the
    # server reads, not a page anyone browses. Written last so a build that
    # dies partway leaves the previous (still valid) index in place rather than
    # a truncated one.
    if index_out.parent.is_dir():
        write_variety_index(index_out, canonical_titles)
        print(f"Written {len(canonical_titles)} canonical variety titles to {index_out}")
    else:
        # A dev box has no /opt/dale/data. Skipping is right there, and saying
        # so is what stops it being skipped unnoticed on the server.
        print(f"Skipped variety index: {index_out.parent} does not exist "
              f"(use --index-out to write elsewhere)")

    # Print summary stats
    multi = sum(1 for e in index_entries if e["nursery_count"] > 1)
    in_stock_count = sum(1 for e in index_entries if e["in_stock"] > 0)
    print(f"  Multi-nursery: {multi}, In-stock varieties: {in_stock_count}")


if __name__ == "__main__":
    main()
