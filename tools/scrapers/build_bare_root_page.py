#!/usr/bin/env python3
"""
Build the bare-root season page (/bare-root.html) for treestock.com.au (DAL-185).

Bare-root season (June to September) is the peak buying window for deciduous
fruit trees in Australia. This page targets 'buy bare root fruit trees
australia', 'bare root apple trees', 'bare root stone fruit' and similar
seasonal queries, and shows what is actually in stock right now across the
tracked nurseries: something no static guide can do.

The page regenerates nightly and is season-aware:
  - open:   in season (June 1 to September 30) with enough live stock,
            renders the full in-stock table
  - sparse: in season but under SPARSE_MIN items in stock, renders
            per-nursery counts instead of a thin table
  - closed: October to May, curated content stays live and indexable,
            the live table swaps for a next-season subscribe panel

The filename is evergreen (bare-root.html) so rankings compound year over
year; only the title/H1 carry the season year, derived from the build date.

Usage:
    python3 build_bare_root_page.py /path/to/data/nursery-stock /path/to/output/ [--today YYYY-MM-DD]
"""

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer, render_treesmith_promo

from stocklib.citations import inline_cite
from stocklib.classify import is_real_product
from stocklib.utm import outbound
from stocklib.registry import NURSERY_NAMES, delivery_label, restriction_warning
from stocklib.snapshots import iter_nursery_snapshots, variant_min_price, withdraw_if_dormant
from stocklib.taxonomy import enabled_species

from cultivar_parsing import _RE_BARE_ROOTED, _RE_BEAR_ROOTED
from build_when_to_plant import SPECIES, build_cta, SUBSCRIBE_SCRIPT

SEASON_START_MONTH = 6   # June 1
SEASON_END_MONTH = 9     # through September 30
SPARSE_MIN = 5           # fewer in-stock items than this = sparse state
MAX_TABLE_ROWS = 150

# Sources drawn from the verified when-to-plant research pass (all resolved
# HTTP 200, June 2026), reused here because the claims overlap.
SOURCES = [
    {"name": "Sustainable Gardening Australia: bare-root fruit trees", "url": "https://www.sgaonline.org.au/bare-root-fruit-trees/"},
    {"name": "ABC Gardening Australia: bare-rooted plants", "url": "https://www.gardeningaustraliamag.com.au/bare-rooted-plants/"},
    {"name": "Daleys Fruit Tree Nursery: chill factor guide", "url": "https://www.daleysfruit.com.au/fruit%20pages/chillfactor.htm"},
]

CITE_SGA = ("SGA bare-root guide", "https://www.sgaonline.org.au/bare-root-fruit-trees/")
CITE_ABC = ("ABC Gardening Australia", "https://www.gardeningaustraliamag.com.au/bare-rooted-plants/")
CITE_DALEYS = ("Daleys chill guide", "https://www.daleysfruit.com.au/fruit%20pages/chillfactor.htm")

FAQS = [
    (
        "What does bare root mean?",
        "A bare-root tree is a deciduous tree that's dug up while it's dormant in winter and sold with the soil shaken off its roots, usually wrapped in damp sawdust or coir instead of a pot. With no pot or potting mix and much less weight to freight, bare-root trees usually cost less than the same variety in a pot, and nurseries can offer a much wider range.",
    ),
    (
        "When is bare-root season in Australia?",
        "Roughly June to September. Nurseries start lifting and releasing dormant stock in early June, availability peaks in July, and most stop shipping by mid September as the trees wake up. Popular varieties often sell out within days of release, so order early.",
    ),
    (
        "Which fruit trees are sold bare-root?",
        "Deciduous species: apples, pears, plums, peaches, nectarines, apricots, cherries, figs, mulberries, grapes, pecans, jujubes, pomegranates and cool-climate blueberries, plus quince, persimmon and many multi-graft combinations. Evergreens like citrus, avocado and mango aren't sold bare-root. You can only buy them potted.",
    ),
    (
        "How do I plant a bare-root tree?",
        "Plant as soon as you can after it arrives. Soak the roots in a bucket of water for a few hours, dig a hole wide enough to spread the roots without bending them, plant at the same depth the tree grew at (look for the soil mark on the trunk, and keep the graft union above ground), backfill with the soil you dug out, water in well, and mulch. Don't add fertiliser to the planting hole. If you can't plant straight away, heel the tree into damp soil or potting mix and keep the roots moist.",
    ),
    (
        "Are bare-root trees cheaper than potted trees?",
        "Usually, yes. The nursery saves on the pot, the potting mix and the freight, and you see that in the price. Bare-root trees also establish quickly when planted in winter, because the roots grow into your soil before the tree leafs out in spring.",
    ),
    (
        "Can I buy bare-root trees in WA, NT or TAS?",
        "Sometimes, but check with the nursery first. WA, NT and TAS have strict plant quarantine, and a lot of eastern-states nurseries don't ship there at all. The nursery list on this page shows each seller's restrictions. WA buyers can also get bare-root trees in season from local growers, with no border paperwork.",
    ),
]


def season_state(today: date, in_stock_count: int) -> str:
    """Return 'open', 'sparse' or 'closed' for the given date and live count."""
    if SEASON_START_MONTH <= today.month <= SEASON_END_MONTH:
        return "open" if in_stock_count >= SPARSE_MIN else "sparse"
    return "closed"


def season_year(today: date) -> int:
    """The year of the season this page is about: the current season while it
    runs (and in the months leading up to it), next year's from October."""
    return today.year + 1 if today.month > SEASON_END_MONTH else today.year


def _product_price(p: dict):
    """Minimum price for a product across both snapshot dialects."""
    if p.get("min_price") is not None:
        try:
            return float(p["min_price"])
        except (TypeError, ValueError):
            pass
    price = variant_min_price(p, prefer_available=True)
    if price is not None:
        return price
    try:
        return float(p["price"]) if p.get("price") is not None else None
    except (TypeError, ValueError):
        return None


def _product_available(p: dict) -> bool:
    if "any_available" in p:
        return bool(p["any_available"])
    variants = p.get("variants") or []
    if variants:
        return any(v.get("available") for v in variants)
    return bool(p.get("available"))


def _fmt_price(price: float) -> str:
    s = f"${price:,.2f}"
    return s[:-3] if s.endswith(".00") else s


def _is_bare_root(p: dict) -> bool:
    text = (p.get("title") or "") + " " + " ".join(p.get("tags") or [])
    return bool(_RE_BARE_ROOTED.search(text) or _RE_BEAR_ROOTED.search(text))


def _shipping_cell(nursery_key: str) -> str:
    """Shipping/delivery note for a nursery, styled by meaning.

    Local nurseries (Guildford, Primal Fruits, the Melbourne yards) show their
    delivery area in neutral grey: that is how you buy from them, not a warning.
    Interstate shippers that skip a quarantine state show an amber caution
    (No WA/NT/TAS). Full-nationwide shippers read a plain 'All states'. Keeping
    the two apart stops a WA buyer reading a page full of amber and concluding
    nothing is available locally when Guildford stocks it."""
    local = delivery_label(nursery_key)
    if local:
        return f'<span class="text-xs text-gray-500">{local}</span>'
    restrict = restriction_warning(nursery_key)
    if restrict:
        return f'<span class="text-xs text-amber-700">{restrict}</span>'
    return '<span class="text-xs text-gray-400">All states</span>'


def collect_bare_root(data_dir, today: str | None = None) -> list[dict]:
    """All bare-root products across today's snapshots, as flat row dicts."""
    rows = []
    # `today` here is the page's season date (--today pins it for the golden
    # test); whether a nursery has gone quiet is a fact about the data against
    # the real clock, so withdrawal is judged separately. Identical in cron,
    # where no --today is passed.
    for nursery_key, snap in iter_nursery_snapshots(data_dir, today, withdraw_dormant=False):
        snap = withdraw_if_dormant(nursery_key, snap)
        for p in snap.get("products", []):
            if not is_real_product(p.get("title", "")):
                continue
            if not _is_bare_root(p):
                continue
            rows.append({
                "title": p.get("title", ""),
                "url": outbound(p.get("url", ""), "bare-root"),
                "nursery_key": nursery_key,
                "nursery": NURSERY_NAMES.get(nursery_key, snap.get("nursery_name", nursery_key)),
                "price": _product_price(p),
                "available": _product_available(p),
            })
    return rows


# ----- Section builders -----

def build_status_box(state: str, rows: list[dict], today: date) -> str:
    in_stock = [r for r in rows if r["available"]]
    nurseries = {r["nursery_key"] for r in in_stock}
    yr = season_year(today)
    if state == "closed":
        return f"""
<div class="bg-gray-50 border border-gray-300 rounded-lg p-4 mb-8" id="season-status">
  <p class="font-semibold text-gray-800 mb-1">Season closed. Bare-root runs June to September.</p>
  <p class="text-sm text-gray-700">Nurseries lift and ship dormant trees through winter. Live listings for the {yr} season start showing here on 1 June.</p>
</div>
"""
    if state == "sparse":
        return f"""
<div class="bg-amber-50 border border-amber-300 rounded-lg p-4 mb-8" id="season-status">
  <p class="font-semibold text-amber-800 mb-1">Bare-root season is on (June to September).</p>
  <p class="text-sm text-amber-900">Not much is listed right now. New releases sell out within days, and nurseries list the next batch as they lift it. This page updates every night.</p>
</div>
"""
    return f"""
<div class="bg-green-50 border border-green-300 rounded-lg p-4 mb-8" id="season-status">
  <p class="font-semibold text-green-900 mb-1">Bare-root season is on. {len(in_stock)} trees in stock across {len(nurseries)} nurseries.</p>
  <p class="text-sm text-green-900">From last night's check of every nursery we track. The best varieties sell out within days of release, so if you see the one you want, don't wait.</p>
</div>
"""


def build_what_is_section() -> str:
    return f"""
<section class="mb-10" id="what-is-bare-root">
  <h2 class="text-xl font-bold text-green-900 mb-3">What Bare Root Means (and Why It's the Cheapest Way to Buy)</h2>
  <p class="text-sm text-gray-600 mb-3">Deciduous fruit trees go fully dormant in winter. Nurseries dig them out of the field, shake the soil off, and sell them with the roots wrapped in damp packing instead of a pot. With no pot or potting mix and much less weight to freight, the same grafted variety usually costs a fair bit less bare-root than potted. Nurseries can also offer far more varieties than they could ever keep in pots.{inline_cite(*CITE_SGA)}</p>
  <p class="text-sm text-gray-600 mb-3">Plant it while it's dormant and a bare-root tree starts pushing new roots into your soil weeks before the top wakes up, so it establishes at least as well as a potted tree planted in spring. The catch is timing. Nurseries can only lift and ship them while the trees are dormant, roughly June to September, and the popular varieties go early.{inline_cite(*CITE_ABC)}</p>
  <p class="text-sm text-gray-600">Check chill hours before you buy. Most bare-root species need a certain amount of winter cold to fruit properly, and high-chill cherries or apples won't do well in Brisbane or coastal Perth. There are low-chill varieties of most species, so pick the variety for your climate as well as the species.{inline_cite(*CITE_DALEYS)}</p>
</section>
"""


def _bare_root_months_text(months: list[int]) -> str:
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return ", ".join(names[m - 1] for m in months)


def build_species_section(valid_slugs: set) -> str:
    items = []
    for s in SPECIES:
        if not s.get("bareRoot"):
            continue
        if s.get("slug") and s["slug"] in valid_slugs:
            name = f'<a href="/species/{s["slug"]}.html" class="text-green-700 font-semibold hover:underline">{s["name"]}</a>'
        else:
            name = f'<span class="font-semibold text-gray-800">{s["name"]}</span>'
        items.append(
            f'<li class="mb-1">{name} <span class="text-xs text-gray-500">({_bare_root_months_text(s["bareRoot"])})</span></li>'
        )
    items_html = "".join(items)
    return f"""
<section class="mb-10" id="species">
  <h2 class="text-xl font-bold text-green-900 mb-3">Which Fruit Trees Come Bare-Root</h2>
  <p class="text-sm text-gray-600 mb-3">Only deciduous species are sold bare-root. Evergreens (citrus, avocado, mango and the tropicals) are always sold potted. Each species links to its stock page, with prices from every nursery we track.</p>
  <ul class="text-sm columns-2 sm:columns-3 list-none">
    {items_html}
  </ul>
</section>
"""


def build_live_table(state: str, rows: list[dict], today: date) -> str:
    if state == "closed":
        yr = season_year(today)
        return f"""
<section class="mb-10" id="in-stock">
  <h2 class="text-xl font-bold text-green-900 mb-3">Bare-Root Trees in Stock</h2>
  <div class="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
    <p class="text-sm text-gray-700 mb-1 font-medium">The bare-root season is over for this year.</p>
    <p class="text-sm text-gray-600">Nurseries start listing {yr} season stock from late autumn, and the live listings come back here on 1 June.</p>
  </div>
</section>
"""
    in_stock = sorted(
        (r for r in rows if r["available"]),
        key=lambda r: (r["price"] is None, r["price"] if r["price"] is not None else 0, r["title"]),
    )
    if state == "sparse" or not in_stock:
        by_nursery: dict[str, int] = {}
        for r in rows:
            by_nursery[r["nursery_key"]] = by_nursery.get(r["nursery_key"], 0) + 1
        counts = "".join(
            f'<li><a href="/nursery/{k}.html" class="text-green-700 hover:underline">{NURSERY_NAMES.get(k, k)}</a>: {n} bare-root listings</li>'
            for k, n in sorted(by_nursery.items(), key=lambda kv: -kv[1])
        )
        listing_note = f'<ul class="text-sm space-y-1 list-disc pl-5 mt-3">{counts}</ul>' if counts else ""
        return f"""
<section class="mb-10" id="in-stock">
  <h2 class="text-xl font-bold text-green-900 mb-3">Bare-Root Trees in Stock Now</h2>
  <p class="text-sm text-gray-600">Very little bare-root stock is in stock right now. That usually means one batch has sold out and the next one isn't listed yet. These nurseries sell bare-root:</p>
  {listing_note}
</section>
"""
    shown = in_stock[:MAX_TABLE_ROWS]
    rows_html = []
    for r in shown:
        price = _fmt_price(r["price"]) if r["price"] is not None else "POA"
        ship_html = _shipping_cell(r["nursery_key"])
        rows_html.append(
            f"""        <tr>
          <td><a href="{r['url']}" rel="noopener nofollow" target="_blank" class="text-green-700 hover:underline">{r['title']}</a></td>
          <td><a href="/nursery/{r['nursery_key']}.html" class="text-gray-700 hover:underline">{r['nursery']}</a></td>
          <td class="whitespace-nowrap">{price}</td>
          <td>{ship_html}</td>
        </tr>"""
        )
    cap_note = ""
    if len(in_stock) > MAX_TABLE_ROWS:
        cap_note = f'<p class="text-xs text-gray-500 mt-2">Showing the {MAX_TABLE_ROWS} cheapest of {len(in_stock)} in-stock bare-root listings. Use the <a href="/" class="text-green-700 hover:underline">main search</a> to filter by species and state.</p>'
    body = "\n".join(rows_html)
    return f"""
<section class="mb-10" id="in-stock">
  <h2 class="text-xl font-bold text-green-900 mb-3">Bare-Root Trees in Stock Now ({len(in_stock)})</h2>
  <p class="text-sm text-gray-600 mb-3">Every bare-root tree in stock at the nurseries we track, cheapest first. Prices are what each nursery is listing today. Click through for details and shipping costs. The shipping column shows quarantine limits (No WA/NT/TAS), or the delivery area for local nurseries.</p>
  <div style="overflow-x:auto;">
    <table class="br-table">
      <thead>
        <tr><th>Tree</th><th>Nursery</th><th>Price</th><th>Shipping</th></tr>
      </thead>
      <tbody>
{body}
      </tbody>
    </table>
  </div>
  {cap_note}
</section>
"""


def build_nursery_section(rows: list[dict]) -> str:
    by_nursery: dict[str, dict] = {}
    for r in rows:
        entry = by_nursery.setdefault(r["nursery_key"], {"total": 0, "in_stock": 0})
        entry["total"] += 1
        if r["available"]:
            entry["in_stock"] += 1
    if not by_nursery:
        return ""
    items = []
    for key, entry in sorted(by_nursery.items(), key=lambda kv: (-kv[1]["in_stock"], -kv[1]["total"])):
        ship = " " + _shipping_cell(key)
        items.append(
            f'<li class="mb-1"><a href="/nursery/{key}.html" class="text-green-700 font-semibold hover:underline">{NURSERY_NAMES.get(key, key)}</a>'
            f' <span class="text-xs text-gray-500">({entry["in_stock"]} in stock of {entry["total"]} bare-root listings)</span>{ship}</li>'
        )
    items_html = "".join(items)
    return f"""
<section class="mb-10" id="nurseries">
  <h2 class="text-xl font-bold text-green-900 mb-3">Which Nurseries Sell Bare-Root</h2>
  <p class="text-sm text-gray-600 mb-3">Nurseries we track that have bare-root trees in their current catalogue. Many eastern nurseries don't ship to WA, NT or TAS because of quarantine rules, so check the restriction next to each one.</p>
  <ul class="text-sm list-none">
    {items_html}
  </ul>
</section>
"""


def build_faq_section() -> str:
    items = "".join(
        f"""  <div class="mb-5">
    <h3 class="font-semibold text-gray-800 mb-1">{q}</h3>
    <p class="text-sm text-gray-600">{a}</p>
  </div>"""
        for q, a in FAQS
    )
    return f"""
<section class="mb-10" id="faq">
  <h2 class="text-xl font-bold text-green-900 mb-4">Frequently Asked Questions</h2>
  {items}
</section>
"""


def build_faq_jsonld() -> str:
    entities = [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
        for q, a in FAQS
    ]
    data = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities}
    return '<script type="application/ld+json">\n' + json.dumps(data, indent=2) + "\n</script>"


def build_references() -> str:
    items = "".join(
        f'<li><a href="{s["url"].replace("&", "&amp;")}" rel="noopener nofollow" target="_blank" class="text-green-700 hover:underline">{s["name"]}</a></li>'
        for s in SOURCES
    )
    return f"""
<section class="mb-10" id="references">
  <h2 class="text-xl font-bold text-green-900 mb-3">Sources</h2>
  <p class="text-gray-600 text-sm mb-3">The bare-root advice here comes from Sustainable Gardening Australia, ABC Gardening Australia and Daleys. Stock and prices come from our nightly check of each nursery's website.</p>
  <ul class="text-sm space-y-1 list-disc pl-5">
    {items}
  </ul>
</section>
"""


def build_related_guides() -> str:
    return """
<section class="mb-10" id="related">
  <h2 class="text-xl font-bold text-green-900 mb-3">Related Guides</h2>
  <ul class="text-sm space-y-1 list-disc pl-5">
    <li><a href="/when-to-plant.html" class="text-green-700 hover:underline">When to plant fruit trees in Australia</a> (full planting calendar for 50 species)</li>
    <li><a href="/companion-planting-guide.html" class="text-green-700 hover:underline">Companion planting guide for fruit trees</a> (what to grow alongside)</li>
    <li><a href="/rootstock.html" class="text-green-700 hover:underline">Fruit tree rootstock guide</a> (rootstock types, suppliers, grow your own)</li>
    <li><a href="/species/" class="text-green-700 hover:underline">Browse all tracked species</a> (in-stock counts, prices, restock alerts)</li>
  </ul>
</section>
"""


EXTRA_STYLE = """\
  .br-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  .br-table th { background: #f3f4f6; color: #374151; font-weight: 600; padding: 9px 11px; text-align: left; border-bottom: 2px solid #e5e7eb; white-space: nowrap; }
  .br-table td { padding: 8px 11px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }"""


def build_page(data_dir, today: date) -> str:
    valid_slugs = {s["slug"] for s in enabled_species() if s.get("slug")}
    rows = collect_bare_root(data_dir, today.isoformat())
    in_stock_count = sum(1 for r in rows if r["available"])
    state = season_state(today, in_stock_count)
    yr = season_year(today)

    head = render_head(
        title=f"Bare Root Fruit Trees Australia {yr}: Season Guide and Live Stock - treestock.com.au",
        description=f"Bare root fruit tree season in Australia runs June to September. What bare root means, which species and nurseries sell it, and live {yr} in-stock listings with prices, updated daily.",
        canonical_url="https://treestock.com.au/bare-root.html",
        extra_head=build_faq_jsonld(),
        extra_style=EXTRA_STYLE,
        og_title=f"Bare Root Fruit Trees in Australia ({yr} Season)",
        og_description="Which fruit trees come bare-root, which nurseries sell them, and what is in stock right now across Australian nurseries. Updated daily.",
        og_image="https://treestock.com.au/og-image.png",
        og_type="article",
    )
    header = render_header(active_path="/bare-root.html")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Bare Root Season", "")])
    footer = render_footer()

    return render_template(
        "bare_root_page.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        season_year=yr,
        today=today.isoformat(),
        status_box=build_status_box(state, rows, today),
        what_is_section=build_what_is_section(),
        species_section=build_species_section(valid_slugs),
        live_table=build_live_table(state, rows, today),
        nursery_section=build_nursery_section(rows),
        cta=build_cta(),
        faq_section=build_faq_section(),
        references=build_references(),
        related_guides=build_related_guides(),
        treesmith_promo=render_treesmith_promo("species"),
        subscribe_script=SUBSCRIBE_SCRIPT,
    )


def main():
    parser = argparse.ArgumentParser(description="Build the bare-root season page")
    parser.add_argument("data_dir", help="Path to data/nursery-stock")
    parser.add_argument("out_dir", help="Output directory")
    parser.add_argument("--today", help="Build date YYYY-MM-DD (for deterministic tests)")
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    html = build_page(args.data_dir, today)
    out_file = out_dir / "bare-root.html"
    out_file.write_text(html)
    print(f"Written: {out_file} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
