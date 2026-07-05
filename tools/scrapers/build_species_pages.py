#!/usr/bin/env python3
"""
Build static species pages for SEO.

Generates one HTML page per fruit species showing:
- Current stock across all nurseries
- Price range
- Which nurseries carry it + shipping states
- Variety breakdown

Target keywords: "buy [species] tree online Australia", "[species] tree price Australia"

Usage:
    python3 build_species_pages.py /path/to/nursery-stock /path/to/output/
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone

from shipping import SHIPPING_MAP, LOCAL_DELIVERY, delivery_label
from stocklib.templates import render as render_template
from stocklib.structured_data import product_offer_jsonld
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer, render_treesmith_promo
import growing_guides
from stocklib.variety_descriptions import has_description, render_excerpt
from build_species_trends import build_species_trends, make_sparkline, trend_direction

# How many described in-stock varieties a species page surfaces as excerpts.
NOTABLE_VARIETIES_MAX = 5


from cultivar_parsing import (  # noqa: E402
    product_variety_slug as _variety_slug,
    group_by_cultivar, GRANDFATHERED_VARIETY_SLUGS,
)


def _no_dash(text: str) -> str:
    """Strip en and em dashes from external strings (nursery product titles and
    names) so passthrough data never breaks the treestock copy rule on the page.
    Mirrors build_species_state_pages._no_dash; raw titles are kept for matching
    and slugs, this is applied only where the value is rendered into HTML."""
    return text.replace("—", "-").replace("–", "-")

# Related species groups for cross-linking — people who buy one often compare others in the group.
# Ordered by popularity within each group (most popular first).
RELATED_GROUPS = {
    "tropical": ["mango", "lychee", "longan", "jackfruit", "banana", "dragon-fruit", "papaya", "rambutan", "starfruit"],
    "citrus": ["lemon", "lime", "orange", "mandarin", "grapefruit", "pomelo", "finger-lime"],
    "stone_fruit": ["peach", "nectarine", "apricot", "plum", "cherry"],
    "pome": ["apple", "pear"],
    "subtropical": ["avocado", "guava", "feijoa", "passionfruit", "loquat", "jaboticaba", "sapodilla", "custard-apple", "white-sapote", "black-sapote", "wax-jambu", "grumichama"],
    "exotic_tropical": ["jackfruit", "cacao", "rollinia", "rambutan", "wax-jambu", "miracle-fruit"],
    "berries": ["blueberry", "raspberry", "mulberry", "lilly-pilly", "grumichama", "jaboticaba"],
    "figs": ["fig", "mulberry"],
    "nuts": ["macadamia", "pecan"],
    "vines": ["grape", "passionfruit"],
    "mediterranean": ["olive", "fig", "pomegranate", "loquat", "grape"],
}

# Build reverse lookup: slug -> list of related slugs (from same group, excluding self)
def build_related_lookup() -> dict[str, list[str]]:
    related: dict[str, list[str]] = {}
    for group_members in RELATED_GROUPS.values():
        for slug in group_members:
            others = [s for s in group_members if s != slug]
            if slug not in related:
                related[slug] = []
            for other in others:
                if other not in related[slug]:
                    related[slug].append(other)
    return related

RELATED_LOOKUP = build_related_lookup()

# Hardcoded non-plant keywords to skip (same as build-dashboard.py)
from stocklib.classify import NON_PLANT_KEYWORDS
from stocklib.taxonomy import enabled_species
from stocklib.category_ui import category_badges_html, CATEGORY_FILTER_CSS


def load_species() -> list[dict]:
    records = enabled_species()
    if not records:
        print("ERROR: no enabled species records found", file=sys.stderr)
        sys.exit(1)
    return records


def build_species_lookup(species_list: list[dict]) -> dict:
    """Build a lowercase name → species entry lookup."""
    lookup = {}
    for s in species_list:
        key = s["common_name"].lower()
        lookup[key] = s
        for syn in s.get("synonyms", []):
            if syn:
                lookup[syn.lower()] = s
    return lookup


def match_title(title: str, lookup: dict) -> dict | None:
    """Match a product title against the species lookup."""
    title_lower = title.lower()
    # Try progressively shorter prefixes
    words = re.split(r'[\s\-–—]+', title_lower)
    for n in range(min(len(words), 5), 0, -1):
        candidate = " ".join(words[:n])
        if candidate in lookup:
            return lookup[candidate]
    return None


def load_nursery_products(data_dir: Path) -> list[dict]:
    """Load all products from latest.json files."""
    products = []
    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        latest = nursery_dir / "latest.json"
        if not latest.exists():
            continue
        with open(latest) as f:
            data = json.load(f)
        nursery_key = nursery_dir.name
        nursery_name = data.get("nursery_name", nursery_key)
        for p in data.get("products", []):
            title = p.get("title", "")
            title_lower = title.lower()
            if any(kw in title_lower for kw in NON_PLANT_KEYWORDS):
                continue
            if re.search(r'\bseeds?\b', title_lower) and 'seedling' not in title_lower and 'seedless' not in title_lower:
                continue
            if title_lower in {"gift card", "gift voucher", "gift certificate"}:
                continue
            # Get best price
            variants = p.get("variants", [])
            min_price = p.get("min_price")
            if min_price is None and variants:
                avail_prices = [float(v["price"]) for v in variants if v.get("price") and v.get("available", True)]
                all_prices = [float(v["price"]) for v in variants if v.get("price")]
                min_price = min(avail_prices) if avail_prices else (min(all_prices) if all_prices else None)
            elif min_price is None:
                min_price = p.get("price")

            available = p.get("any_available", p.get("available", False))
            products.append({
                "title": title,
                "url": p.get("url", ""),
                "nursery_key": nursery_key,
                "nursery_name": nursery_name,
                "price": round(float(min_price), 2) if min_price else None,
                "available": bool(available),
            })
    return products


def compute_rarity_scores(data_dir: Path, by_species: dict, lookup: dict) -> dict[str, dict]:
    """Compute rarity scores for each species using availability history.

    Score formula (0 = common, 100 = extremely rare):
      60% weight: nursery scarcity (fewer nurseries carry it = rarer)
      40% weight: availability scarcity (out-of-stock more often = rarer)

    Returns dict of {slug: {"score", "hard_to_find", "avg_availability", "nursery_count"}}
    """
    total_nurseries = len(SHIPPING_MAP)

    # Aggregate availability per species: list of (in_stock_days, total_days)
    species_avail: dict[str, list] = defaultdict(list)

    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        avail_file = nursery_dir / "availability.json"
        if not avail_file.exists():
            continue
        try:
            with open(avail_file) as f:
                avail_data = json.load(f)
        except Exception:
            continue

        for prod_data in avail_data.get("products", {}).values():
            title = prod_data.get("title", "")
            if not title:
                continue
            species = match_title(title, lookup)
            if not species:
                continue
            days = prod_data.get("days", {})
            if not days:
                continue
            in_stock_days = sum(1 for d in days.values() if d.get("a", False))
            species_avail[species["slug"]].append((in_stock_days, len(days)))

    scores = {}
    for slug, entry in by_species.items():
        prods = entry["products"]
        nursery_count = len({p["nursery_key"] for p in prods})

        # Average availability from historical data
        if species_avail.get(slug):
            total_in = sum(x[0] for x in species_avail[slug])
            total_days = sum(x[1] for x in species_avail[slug])
            avg_avail = total_in / total_days if total_days > 0 else 0.5
        else:
            # No history — fall back to current stock ratio
            in_stock = sum(1 for p in prods if p["available"])
            avg_avail = in_stock / len(prods) if prods else 0.5

        nursery_score = 1.0 - min(nursery_count / total_nurseries, 1.0)
        avail_score = 1.0 - avg_avail
        rarity_score = round((nursery_score * 0.6 + avail_score * 0.4) * 100, 1)

        scores[slug] = {
            "score": rarity_score,
            "hard_to_find": rarity_score >= 65,
            "avg_availability": round(avg_avail, 3),
            "nursery_count": nursery_count,
        }
    return scores


def group_by_species(products: list[dict], lookup: dict) -> dict:
    """Group products by matched species slug."""
    by_species = {}
    for p in products:
        species = match_title(p["title"], lookup)
        if not species:
            continue
        slug = species["slug"]
        if slug not in by_species:
            by_species[slug] = {"species": species, "products": []}
        by_species[slug]["products"].append(p)
    return by_species


def build_species_description(species: dict) -> str:
    """Render the growing-guide section for a species page.

    When a cited growing guide exists (growing_guides/<slug>.json), render its
    state-invariant core (scannable, cited sections plus FAQ and Sources) instead
    of the generic fruit_species.json blurb. Falls back to the blurb otherwise.

    The returned HTML is curated, first-party content (no untrusted scraped data),
    so the template renders it through the {{ description_html|safe }} slot.
    """
    name = species["common_name"]
    slug = species.get("slug", "")
    if slug and growing_guides.has_guide(slug):
        return f"""  <!-- Growing Guide (cited) -->
  <section class="mb-8" id="growing">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Growing {name} in Australia</h3>
{growing_guides.render_species_guide(slug)}
  </section>"""
    description = species.get("description", "")
    if not description:
        return ""
    paragraphs = [p.strip() for p in description.strip().split("\n\n") if p.strip()]
    paras_html = "\n".join(f'      <p class="text-gray-700 text-sm leading-relaxed mb-3">{p}</p>' for p in paragraphs)
    return f"""  <!-- Growing Guide -->
  <section class="mb-8">
    <h3 class="text-lg font-semibold text-gray-800 mb-3">Growing {name} in Australia</h3>
    <div class="prose prose-sm max-w-none">
{paras_html}
    </div>
  </section>"""


def build_related_species_html(slug: str, slug_to_name: dict[str, str], max_links: int = 5) -> str:
    """Render a 'Related species' section with links to up to max_links related species that have data."""
    related_slugs = RELATED_LOOKUP.get(slug, [])
    # Only link species we actually have pages for (i.e. in slug_to_name)
    available = [(s, slug_to_name[s]) for s in related_slugs if s in slug_to_name][:max_links]
    if not available:
        return ""
    links = "".join(
        f'<a href="/species/{s}.html" class="inline-block text-sm text-green-700 hover:underline mr-4 mb-1">{name} &rarr;</a>'
        for s, name in available
    )
    return f"""  <!-- Related species -->
  <section class="mb-6">
    <h3 class="text-base font-semibold text-gray-700 mb-2">Related species</h3>
    <div class="flex flex-wrap gap-y-1">{links}</div>
  </section>
"""


def build_when_to_buy_html(name: str, trend_summary: dict) -> str:
    """Render a 'When to buy' signal box for a species page.

    trend_summary keys:
        stock_series: list[int|None]  -- daily in-stock count, oldest first
        availability_pct: int         -- % days tracked with any stock
        stock_direction: up|down|flat
        price_direction: up|down|flat
        in_stock_now: int
        min_price_now: float|None
        days_tracked: int
    """
    days_tracked = trend_summary.get("days_tracked", 0)
    if days_tracked < 7:
        return ""

    avail_pct = trend_summary.get("availability_pct", 0)
    stock_dir = trend_summary.get("stock_direction", "flat")
    price_dir = trend_summary.get("price_direction", "flat")
    in_stock_now = trend_summary.get("in_stock_now", 0)
    min_price_now = trend_summary.get("min_price_now")
    stock_series = trend_summary.get("stock_series", [])

    # Determine buying signal
    if in_stock_now > 0 and avail_pct < 25:
        bg = "bg-amber-50 border-amber-200"
        icon = "&#9889;"  # lightning bolt
        title = f"Rarely in stock - buy now if you can"
        body = (
            f"Available only {avail_pct}% of days tracked. "
            f"When {name} appears, it often sells out quickly."
        )
    elif in_stock_now > 0 and stock_dir == "down":
        bg = "bg-amber-50 border-amber-200"
        icon = "&#8595;"  # down arrow
        title = f"Stock is falling - consider buying soon"
        body = (
            f"Stock levels have dropped over the last week "
            f"(available {avail_pct}% of days tracked overall)."
        )
    elif in_stock_now > 0 and avail_pct >= 60 and price_dir in ("down", "flat"):
        bg = "bg-green-50 border-green-200"
        icon = "&#10003;"  # check mark
        title = f"Good time to buy"
        body = (
            f"Consistently available ({avail_pct}% of days) with stable supply. "
            + ("Prices have been steady." if price_dir == "flat" else "Prices have been easing.")
        )
    elif in_stock_now > 0 and stock_dir == "up":
        bg = "bg-green-50 border-green-200"
        icon = "&#8593;"  # up arrow
        title = f"Stock is rising"
        body = f"More {name} varieties have been appearing recently. Available {avail_pct}% of days."
    elif in_stock_now > 0:
        bg = "bg-green-50 border-green-200"
        icon = "&#10003;"
        title = f"Currently in stock"
        body = f"Available {avail_pct}% of days we've tracked."
    elif avail_pct == 0:
        bg = "bg-gray-50 border-gray-200"
        icon = "&#63;"  # question mark
        title = f"Stock history building"
        body = f"No stock recorded yet in our {days_tracked}-day tracking window."
    elif avail_pct < 15:
        bg = "bg-red-50 border-red-200"
        icon = "&#128269;"  # magnifier
        title = f"Very hard to find"
        body = (
            f"In stock only {avail_pct}% of tracked days. "
            f"Set an alert below to be notified when {name} returns."
        )
    elif stock_dir == "up":
        bg = "bg-amber-50 border-amber-200"
        icon = "&#8593;"
        title = f"May restock soon"
        body = (
            f"Currently out of stock, but stock was trending upward before selling out "
            f"(available {avail_pct}% of tracked days)."
        )
    else:
        bg = "bg-gray-50 border-gray-200"
        icon = "&#9203;"  # hourglass
        title = f"Currently out of stock"
        body = f"Available {avail_pct}% of days. Set an alert below to be notified when it returns."

    price_note = f" Prices from ${min_price_now:.0f} AUD." if min_price_now else ""
    dir_label = {"up": "rising", "down": "falling", "flat": "stable"}
    trend_note = f"Stock {dir_label[stock_dir]} over the last 7 days. Based on {days_tracked} days of data."

    spark = make_sparkline(stock_series, width=120, height=28, color="#16a34a")

    return f"""  <!-- When to Buy -->
  <section class="mb-6 p-4 {bg} border rounded-lg">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div class="min-w-0">
        <h3 class="text-base font-semibold text-gray-800 mb-1">{icon} {title}</h3>
        <p class="text-sm text-gray-600">{body}{price_note}</p>
        <p class="text-xs text-gray-400 mt-1">{trend_note}</p>
      </div>
      <div class="shrink-0 flex flex-col items-end gap-1">
        <span class="text-xs text-gray-400 whitespace-nowrap">30-day stock trend</span>
        {spark}
      </div>
    </div>
  </section>
"""


STATE_SLUGS = {
    "WA": "western-australia",
    "QLD": "queensland",
    "NSW": "new-south-wales",
    "VIC": "victoria",
}
STATE_FULL_NAMES = {
    "WA": "Western Australia",
    "QLD": "Queensland",
    "NSW": "New South Wales",
    "VIC": "Victoria",
}
MIN_COMBO_PRODUCTS = 3


def compute_state_links(species_slug: str, products: list[dict]) -> dict[str, str]:
    """Return state -> URL for states with enough in-stock products for this species."""
    links = {}
    for state, state_slug in STATE_SLUGS.items():
        state_nurseries = {k for k, v in SHIPPING_MAP.items() if state in v}
        count = sum(
            1 for p in products
            if p["available"] and p["nursery_key"] in state_nurseries
        )
        if count >= MIN_COMBO_PRODUCTS:
            links[state] = f"/buy-{species_slug}-trees-{state_slug}.html"
    return links


def build_species_page(species: dict, products: list[dict], slug_to_name: dict[str, str] | None = None,
                       rarity: dict | None = None, trend_summary: dict | None = None,
                       varieties: list[dict] | None = None) -> str:
    """Generate HTML for a single species page."""
    name = species["common_name"]
    latin = species["latin_name"]
    slug = species["slug"]
    region = species.get("region", "")
    if slug_to_name is None:
        slug_to_name = {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    in_stock = [p for p in products if p["available"]]
    out_of_stock = [p for p in products if not p["available"]]

    # Price stats (in-stock only)
    prices = [p["price"] for p in in_stock if p["price"]]
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None
    price_range = ""
    if min_price and max_price:
        if min_price == max_price:
            price_range = f"${min_price:.2f}"
        else:
            price_range = f"${min_price:.2f} to ${max_price:.2f}"

    # Which nurseries stock it
    nurseries_seen = {}
    for p in products:
        nk = p["nursery_key"]
        if nk not in nurseries_seen:
            nurseries_seen[nk] = {
                "name": p["nursery_name"],
                "in_stock": 0,
                "total": 0,
                "ships_to": SHIPPING_MAP.get(nk, []),
            }
        nurseries_seen[nk]["total"] += 1
        if p["available"]:
            nurseries_seen[nk]["in_stock"] += 1

    nursery_view = []
    for nk, n in sorted(nurseries_seen.items(), key=lambda x: -x[1]["in_stock"]):
        local_lbl = delivery_label(nk)
        ships = local_lbl if local_lbl else (", ".join(n["ships_to"]) if n["ships_to"] else "Local only")
        in_s = n["in_stock"]
        nursery_view.append({
            "key": nk,
            "name": _no_dash(n["name"]),
            "avail_text": f"{in_s} in stock" if in_s > 0 else "out of stock",
            "avail_color": "text-green-700 font-semibold" if in_s > 0 else "text-gray-400",
            "total": n["total"],
            "ships": ships,
        })

    # Product listing (in-stock first). Title links to the nursery (buy-now
    # intent). For named cultivars that have a treestock variety page, append
    # a small "Alerts" link to that page so users can set up restock alerts
    # for the specific cultivar.
    # Product row view-data. The template autoescapes the scraped title, the
    # utm URL (the & target) and the nursery name. alert_link is a prebuilt
    # fragment (a clean variety slug or the #subscribeBox anchor) -> |safe.
    product_view = []
    for p in sorted(products, key=lambda x: (not x["available"], x["price"] or 9999)):
        nursery_url = p["url"] + ("&" if "?" in p["url"] else "?") + "utm_source=treestock&utm_medium=referral" if p["url"] else ""
        # Alerts link only on OOS rows -- no value nudging someone to an
        # "alert me when it's back" page for something they can buy right now.
        # Named cultivars get a per-variety watch (the kept, low-noise feature)
        # via their variety page. OOS rows we can't parse into a cultivar (bare
        # species names) have no per-variety target, so they fall back to the
        # daily-digest subscribe box on this page (#subscribeBox); the digest
        # covers back-in-stock items.
        v_slug = _variety_slug(p["title"])
        if v_slug and not p["available"]:
            # #watchSection lands the click ON the variety page's restock-alert
            # form instead of the top of the page (Benedict, 2026-06-11).
            alert_link = (
                f' <a href="/variety/{v_slug}.html#watchSection" class="ml-1 text-xs text-green-700 hover:underline whitespace-nowrap" '
                f'title="Get restock alerts for this variety">&#128276; Alerts</a>'
            )
        elif not p["available"]:
            alert_link = (
                f' <a href="#subscribeBox" class="ml-1 text-xs text-green-700 hover:underline whitespace-nowrap" '
                f'title="Subscribe to the daily digest for back-in-stock alerts">&#128276; Alerts</a>'
            )
        else:
            alert_link = ''
        product_view.append({
            "has_url": bool(nursery_url),
            "nursery_url": nursery_url,
            "nursery_key": p["nursery_key"],
            "title": _no_dash(p["title"]),
            "alert_link": alert_link,
            "nursery_name": _no_dash(p["nursery_name"]),
            "price": p["price"],
            "available": p["available"],
        })

    in_stock_count = len(in_stock)
    total_count = len(products)
    nursery_count = len(nurseries_seen)
    total_nurseries = len(SHIPPING_MAP)

    # Daily-digest subscribe box. Shown on EVERY species page now (was an
    # OOS-only box). NOTE: species-level "watch" was deliberately removed
    # (commit 2b9e4d7: too noisy, overlaps the digest). We keep the two things
    # that survived that decision: the general/state-filtered daily digest
    # (this box) and per-variety watches (the bell links on cultivar rows ->
    # /variety/<slug>.html). So this box subscribes to the digest, which itself
    # flags back-in-stock items, price drops and new arrivals across nurseries.
    if in_stock_count == 0:
        sub_bg = "bg-amber-50 border-amber-200"
        # Keep the amber headline: the box sits under a Where-to-buy table whose
        # rows all read "out of stock", and this line turns that into an action.
        heading_p = (
            f'<p class="font-semibold text-amber-800 mb-1">&#9888; {name} trees are currently out of stock</p>\n    '
        )
        sub_body = (
            f"Subscribe to the free treestock daily digest. It flags back-in-stock items "
            f"(including {name}), price drops, and new arrivals across all {total_nurseries} "
            f"nurseries we monitor. Filter by state below."
        )
    else:
        sub_bg = "bg-green-50 border-green-200"
        # No headline on the in-stock variant; the body line says what it is.
        heading_p = ""
        sub_body = (
            f"Free daily email flagging back-in-stock items, price drops, and new arrivals "
            f"across all {total_nurseries} nurseries we monitor. Filter by state below."
        )

    watch_box_html = f"""  <!-- Daily-digest subscribe box (always shown) -->
  <div id="subscribeBox" class="p-4 {sub_bg} border rounded-lg text-sm mb-6">
    {heading_p}<p class="text-gray-600 mb-3">{sub_body}</p>
    <form id="subscribeForm" class="flex flex-col sm:flex-row gap-2 flex-wrap">
      <input type="email" id="subEmail" placeholder="your@email.com" required
        class="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500 flex-1 max-w-xs">
      <select id="subState" class="px-2 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-green-500">
        <option value="ALL">All states</option>
        <option value="NSW">NSW</option><option value="VIC">VIC</option>
        <option value="QLD">QLD</option><option value="WA">WA</option>
        <option value="SA">SA</option><option value="TAS">TAS</option>
        <option value="NT">NT</option><option value="ACT">ACT</option>
      </select>
      <button type="submit"
        class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium whitespace-nowrap">
        Subscribe free
      </button>
    </form>
    <div id="subMessage" class="mt-2 text-sm hidden"></div>
  </div>"""

    # Self-contained handler for the subscribe form. Species pages do not load
    # the dashboard search bundle, so the form is wired up here. Posts the
    # general double-opt-in subscribe contract (action:'subscribe' + state),
    # the same one the variety pages use. No species-level watch (removed).
    watch_script = r"""
<script>
(function() {
  var subForm = document.getElementById('subscribeForm');
  if (!subForm) return;
  var msg = document.getElementById('subMessage');
  subForm.addEventListener('submit', function(e) {
    e.preventDefault();
    var email = document.getElementById('subEmail').value.trim();
    var stateEl = document.getElementById('subState');
    var state = stateEl ? stateEl.value : 'ALL';
    fetch('/api/subscribe', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email: email, state: state, action: 'subscribe'})
    })
    .then(function(r) { return r.json().then(function(d) { return {status: r.status, data: d}; }); })
    .then(function(res) {
      if (res.status === 202) {
        msg.textContent = '✓ Check your email. We sent you a confirmation link.';
      } else if (res.data && res.data.message === 'Already subscribed') {
        msg.textContent = 'You are already subscribed.';
      } else {
        msg.textContent = '✓ Subscribed. You will get the daily digest.';
      }
      msg.className = 'mt-2 text-sm text-green-700';
      msg.style.display = 'block';
      subForm.style.display = 'none';
    })
    .catch(function() {
      msg.textContent = 'Something went wrong. Please try again.';
      msg.className = 'mt-2 text-sm text-red-600';
      msg.style.display = 'block';
    });
  });
})();
</script>"""

    # Rarity badge
    rarity_badge_html = ""
    if rarity and rarity.get("hard_to_find"):
        rarity_badge_html = (
            '<span class="px-3 py-1 bg-amber-50 text-amber-800 rounded-full font-medium '
            'border border-amber-200 text-sm" title="Found at fewer nurseries and often out of stock">'
            '&#11088; Hard to find</span>'
        )

    # State combo links (buy-[species]-trees-[state].html)
    state_links = compute_state_links(slug, products)
    state_links_html = ""
    if state_links:
        link_items = "".join(
            f'<a href="{url}" class="inline-block text-sm text-green-700 hover:underline mr-4 mb-1">'
            f'Buy {name} trees in {STATE_FULL_NAMES[state]} &rarr;</a>'
            for state, url in state_links.items()
        )
        state_links_html = f"""
  <!-- State combo links -->
  <section class="mb-6">
    <h3 class="text-base font-semibold text-gray-700 mb-2">Buy {name} trees by state</h3>
    <div class="flex flex-wrap gap-y-1">{link_items}</div>
  </section>
"""

    related_species_html = build_related_species_html(slug, slug_to_name)
    when_to_buy_html = build_when_to_buy_html(name, trend_summary) if trend_summary else ""

    price_desc = f" Prices from {price_range}." if price_range else ""
    head = render_head(
        title=f"{name} Trees for Sale Australia, Compare Prices | treestock.com.au",
        description=f"{in_stock_count} {name} varieties in stock across {nursery_count} Australian nurseries.{price_desc} Compare availability and shipping options. Updated daily.",
        canonical_url=f"https://treestock.com.au/species/{slug}.html",
        extra_head=growing_guides.faq_jsonld(slug) if growing_guides.has_guide(slug) else "",
        og_title=f"{name} Trees for Sale in Australia",
        og_description=f"{in_stock_count} {name} varieties in stock across {nursery_count} nurseries. From {price_range}.",
        jsonld=product_offer_jsonld(
            name=f"{name} Tree",
            url=f"https://treestock.com.au/species/{slug}.html",
            products=products,
            description=f"Compare {name} tree prices and availability across {nursery_count} Australian nurseries.",
            include_offers=False,  # species pages aggregate many cultivars: summary only
        ),
    )
    header = render_header(active_path="/species/")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Species", "/species/"), (name, "")])
    footer = render_footer()

    price_badge = (
        f'<span class="px-3 py-1 bg-gray-50 text-gray-600 rounded-full">{price_range} AUD</span>'
        if price_range else ''
    )
    description_html = build_species_description(species)
    treesmith_promo = render_treesmith_promo("species")
    variety_cta = (
        '<!-- Variety-watch suggestion CTA (shown below results when stock exists) -->\n'
        '  <div class="p-4 bg-green-50 rounded-lg text-sm mb-6">\n'
        f'    <p class="font-medium text-green-800 mb-1">Want alerts for a specific {name} variety?</p>\n'
        '    <p class="text-gray-600">Out-of-stock rows have a &#128276; Alerts link -- click it to get emailed when that exact variety restocks at any monitored nursery. In-stock rows link straight to the nursery for buy-now.</p>\n'
        '  </div>'
    ) if in_stock_count > 0 else ''

    # Variety chip cloud: in-stock varieties first, then alphabetical.
    variety_view = sorted(varieties or [], key=lambda v: (not v["in_stock"], v["name"].lower()))

    # Notable varieties: in-stock varieties that have a verified description,
    # surfaced as one-line excerpts. This is the only place species pages show
    # the variety_descriptions content; the full blurbs stay on /variety/ pages.
    notable_view = [
        {**v, "excerpt": render_excerpt(v["slug"], slug)}
        for v in variety_view
        if v["in_stock"] and has_description(v["slug"], slug)
    ][:NOTABLE_VARIETIES_MAX]

    return render_template(
        "species_page.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        name=name, latin=latin, region=region,
        in_stock_count=in_stock_count, nursery_count=nursery_count,
        total_count=total_count, price_badge=price_badge,
        rarity_badge_html=rarity_badge_html, watch_box_html=watch_box_html,
        when_to_buy_html=when_to_buy_html, description_html=description_html,
        state_links_html=state_links_html, related_species_html=related_species_html,
        variety_cta=variety_cta, treesmith_promo=treesmith_promo,
        watch_script=watch_script, nursery_view=nursery_view, product_view=product_view,
        variety_view=variety_view, notable_view=notable_view,
    )


def build_species_index(species_data: list[dict], trend_data: dict | None = None) -> str:
    """Build an index page listing all species with data."""
    # trend_data: {slug: [in_stock_count_per_day, ...]} (30 values, oldest first)
    index_view = []
    for entry in sorted(species_data, key=lambda x: x["in_stock_count"], reverse=True):
        s = entry["species"]
        in_s = entry["in_stock_count"]
        rarity = entry.get("rarity", {})
        rarity_cell = (
            '<span class="text-xs px-2 py-0.5 bg-amber-50 text-amber-700 rounded-full border border-amber-200 whitespace-nowrap">'
            '&#11088; Hard to find</span>'
            if rarity.get("hard_to_find", False) else ""
        )

        sparkline_cell = ""
        if trend_data and s["slug"] in trend_data:
            series = trend_data[s["slug"]]
            if len([v for v in series if v is not None]) >= 2:
                svg = make_sparkline(series, width=60, height=20, color="#16a34a")
                sparkline_cell = f'<span title="30-day availability trend">{svg}</span>'

        category = s.get("category", "fruit")
        is_bush_tucker = category == "bush_tucker" or "bush_tucker" in s.get("tags", [])

        index_view.append({
            "slug": s["slug"],
            "common_name": s["common_name"],
            "latin_name": s["latin_name"],
            "in_s": in_s,
            "in_s_class": "text-green-700 font-medium" if in_s > 0 else "text-gray-400",
            "total": entry["total_count"],
            "nurseries": entry["nursery_count"],
            "price_range": entry["price_range"],
            "sparkline_cell": sparkline_cell,
            "rarity_cell": rarity_cell,
            "category": category,
            "is_bush_tucker": is_bush_tucker,
            "category_badges_html": category_badges_html(s),
        })

    sparkline_th = '<th class="pb-2 pr-2">30d</th>' if trend_data else ""

    head = render_head(
        title="Browse Fruit Tree and Bush Tucker Species | treestock.com.au",
        description="Browse fruit trees and Australian bush tucker by species across nurseries. Track prices, availability, and shipping. Updated daily.",
        extra_style=CATEGORY_FILTER_CSS,
    )
    header = render_header(active_path="/species/")
    footer = render_footer()

    return render_template(
        "species_index.html.j2",
        head=head, header=header, footer=footer,
        sparkline_th=sparkline_th, index_view=index_view,
    )


def main():
    if len(sys.argv) < 3:
        print("Usage: build_species_pages.py <data-dir> <output-dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not data_dir.exists():
        print(f"Error: {data_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    print("Loading species taxonomy...")
    species_list = load_species()
    lookup = build_species_lookup(species_list)
    print(f"  {len(species_list)} species, {len(lookup)} lookup entries")

    print("Loading nursery products...")
    products = load_nursery_products(data_dir)
    print(f"  {len(products)} products loaded")

    print("Grouping by species...")
    by_species = group_by_species(products, lookup)
    print(f"  {len(by_species)} species matched")

    # Variety chip clouds: the SAME grouping build_variety_pages.py writes
    # /variety/<slug>.html pages from, so a chip can never link to a page that
    # does not exist. Grandfathered slugs are alert-only and stay off browsable
    # surfaces, matching the variety index (DEC-195/196).
    print("Grouping varieties for chip clouds...")
    variety_groups = group_by_cultivar(products)
    name_to_slug = {s["common_name"]: s["slug"] for s in species_list}
    varieties_by_species: dict[str, list[dict]] = defaultdict(list)
    for v_slug, g in variety_groups.items():
        if v_slug in GRANDFATHERED_VARIETY_SLUGS:
            continue
        sp_slug = name_to_slug.get(g["species"])
        if not sp_slug:
            continue
        varieties_by_species[sp_slug].append({
            "slug": v_slug,
            "name": _no_dash(g["variety"]),
            # available and price, matching the variety page's own in-stock count
            "in_stock": any(p["available"] and p["price"] for p in g["products"]),
        })
    print(f"  {sum(len(v) for v in varieties_by_species.values())} variety chips across {len(varieties_by_species)} species")

    print("Computing rarity scores...")
    rarity_scores = compute_rarity_scores(data_dir, by_species, lookup)
    hard_to_find_count = sum(1 for r in rarity_scores.values() if r["hard_to_find"])
    print(f"  {hard_to_find_count} species marked 'Hard to find'")

    # Save rarity scores for use by other build scripts (e.g. build_rare_finds.py)
    rarity_scores_file = data_dir.parent / "rarity_scores.json"
    with open(rarity_scores_file, "w") as f:
        json.dump(rarity_scores, f, indent=2)
    print(f"  Saved rarity scores to {rarity_scores_file}")

    # Build 30-day sparkline trend data for index + per-species 'When to buy' summaries
    print("Computing 30-day availability trends for sparklines and When to Buy signals...")
    try:
        all_dates, species_trend_raw = build_species_trends(data_dir)
        last_30 = all_dates[-30:]
        trend_data = {}
        trend_summaries: dict[str, dict] = {}
        for slug, date_map in species_trend_raw.items():
            stock_series = [date_map.get(d, {}).get("in_stock") for d in last_30]
            price_series = [date_map.get(d, {}).get("min_price") for d in last_30]
            if not any(v is not None for v in stock_series):
                continue
            trend_data[slug] = stock_series
            latest = next((date_map[d] for d in reversed(last_30) if d in date_map), None)
            in_stock_now = latest["in_stock"] if latest else 0
            min_price_now = latest["min_price"] if latest else None
            days_with_stock = sum(1 for v in stock_series if v is not None and v > 0)
            days_tracked = sum(1 for v in stock_series if v is not None)
            avail_pct = int(days_with_stock / days_tracked * 100) if days_tracked else 0
            trend_summaries[slug] = {
                "stock_series": stock_series,
                "price_series": price_series,
                "availability_pct": avail_pct,
                "stock_direction": trend_direction(stock_series),
                "price_direction": trend_direction(price_series),
                "in_stock_now": in_stock_now,
                "min_price_now": min_price_now,
                "days_tracked": days_tracked,
            }
        print(f"  Trend data for {len(trend_data)} species, {len(trend_summaries)} with When to Buy signal")
    except Exception as e:
        print(f"  WARNING: Could not compute trend data: {e}")
        trend_data = None
        trend_summaries = {}

    # Build slug->name map for species that have product data (used for related links)
    slug_to_name = {
        slug: entry["species"]["common_name"]
        for slug, entry in by_species.items()
    }

    species_dir = output_dir / "species"
    species_dir.mkdir(parents=True, exist_ok=True)

    index_data = []
    generated = 0
    for slug, entry in sorted(by_species.items()):
        species = entry["species"]
        prods = entry["products"]
        in_stock = [p for p in prods if p["available"]]
        prices = [p["price"] for p in in_stock if p["price"]]
        min_p = min(prices) if prices else None
        max_p = max(prices) if prices else None
        price_range = ""
        if min_p and max_p:
            price_range = f"${min_p:.2f}" if min_p == max_p else f"${min_p:.2f}-${max_p:.2f}"

        nurseries = {p["nursery_key"] for p in prods}
        rarity = rarity_scores.get(slug, {})
        index_data.append({
            "species": species,
            "in_stock_count": len(in_stock),
            "total_count": len(prods),
            "nursery_count": len(nurseries),
            "price_range": price_range,
            "rarity": rarity,
        })

        html = build_species_page(species, prods, slug_to_name, rarity=rarity,
                                  trend_summary=trend_summaries.get(slug),
                                  varieties=varieties_by_species.get(slug, []))
        out_file = species_dir / f"{slug}.html"
        out_file.write_text(html)
        generated += 1
        if generated <= 5 or generated % 10 == 0:
            htf = " [Hard to find]" if rarity.get("hard_to_find") else ""
            print(f"  {species['common_name']}: {len(in_stock)}/{len(prods)} in stock, {len(nurseries)} nurseries{htf}")

    # Build index
    index_html = build_species_index(index_data, trend_data=trend_data)
    index_file = species_dir / "index.html"
    index_file.write_text(index_html)

    print(f"\nGenerated {generated} species pages + index → {species_dir}")
    print(f"Index: {index_file}")


if __name__ == "__main__":
    main()
