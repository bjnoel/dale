#!/usr/bin/env python3
"""
Build /fruit-tree-shipping-by-state.html: which fruit trees can actually be
shipped to each Australian state, measured daily since 2026-03-05.

Why this page exists (DAL-254, DEC-245, DEC-246): every other page on treestock
is a live stock table. Useful, but nothing anyone cites. This one publishes a
measurement nobody else in Australia can make, because making it needs a daily
per-nursery availability history joined to each nursery's published shipping
policy, and we are the only people keeping one.

The claim it exists to support: national rarity is largely a myth (nearly every
species is in stock somewhere on nearly every day) and the real constraint is
STATE REACHABILITY. Tasmania cannot buy most of them at all.

Method, deliberately conservative:

  - Roll up to NURSERY-day, not listing-day. compute_rarity_scores in
    build_species_pages.py averages over listings, so a nursery with 20 variety
    SKUs of one species outvotes four nurseries with one each. That is fine for
    an internal ranking signal and wrong for a published number (DEC-246).
  - "Reachable in state S on day D" means: at least one nursery whose published
    policy covers S had at least one listing of that species in stock on D.
  - Shipping is each nursery's STATED policy, not a test order.
  - Absence of a day entry is not "out of stock", it is "not listed", so days
    are only counted where the availability history actually has an entry.

Usage:
    python3 build_shipping_reachability.py /path/to/nursery-stock /path/to/output/
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from stocklib.registry import NURSERY_NAMES, SHIPPING_MAP, nursery_location, nursery_ships_to
from stocklib.species_match import build_species_lookup, match_title
from stocklib.taxonomy import enabled_species
from treestock_layout import (
    CONTENT_MAX_WIDTH,
    render_breadcrumb,
    render_footer,
    render_head,
    render_header,
    render_treesmith_promo,
)

PAGE_SLUG = "fruit-tree-shipping-by-state.html"
DATA_SLUG = "shipping-reachability.json"
PAGE_URL = f"https://treestock.com.au/{PAGE_SLUG}"
DATA_URL = f"https://treestock.com.au/{DATA_SLUG}"

#: Ordered worst-reachable last, because that is the finding.
STATES = [
    ("VIC", "Victoria"),
    ("NSW", "New South Wales"),
    ("ACT", "Australian Capital Territory"),
    ("QLD", "Queensland"),
    ("SA", "South Australia"),
    ("WA", "Western Australia"),
    ("NT", "Northern Territory"),
    ("TAS", "Tasmania"),
]


def load_stock_history(data_dir: Path, lookup: dict) -> tuple[dict, list[str], dict]:
    """Return ({species_slug: {day: {nursery_key, ...}}}, sorted days, {day: n_nurseries}).

    The inner value is a SET OF NURSERIES, which is the whole point: it is what
    makes the published numbers nursery-day rollups rather than listing counts.

    The third return value is the size of the measuring instrument on each day,
    and it is not optional. The panel started at a handful of nurseries and grew
    to the full set, so a whole-window average understates every state. The page
    has to be able to say so, and to say so from the data rather than from a
    number somebody wrote down once.
    """
    stock: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    reporting: dict[str, set] = defaultdict(set)
    days: set[str] = set()

    for nursery_dir in sorted(data_dir.iterdir()):
        if not nursery_dir.is_dir():
            continue
        avail_file = nursery_dir / "availability.json"
        if not avail_file.exists():
            continue
        try:
            with open(avail_file) as f:
                avail = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        key = avail.get("nursery") or nursery_dir.name
        if key not in SHIPPING_MAP:
            # A nursery we no longer track (removed at their request, or
            # retired) must not keep contributing to a published number.
            continue
        for product in avail.get("products", {}).values():
            title = product.get("title", "")
            if not title:
                continue
            species = match_title(title, lookup)
            if not species:
                continue
            slug = species["slug"]
            for day, record in product.get("days", {}).items():
                days.add(day)
                reporting[day].add(key)
                if record.get("a"):
                    stock[slug][day].add(key)

    return stock, sorted(days), {d: len(v) for d, v in reporting.items()}


#: Days at the end of the window over which the headline average is taken. The
#: whole-window average is also published, but the panel was a third of its
#: current size in March, so it is the conservative figure and not the current
#: one. Both are shown; neither is hidden.
RECENT_DAYS = 30

#: A day counts only if at least this share of the largest panel seen so far
#: actually reported. On a day the scrapers failed, "nothing was in stock
#: anywhere in Australia" is not a fact about Australian nurseries, it is a fact
#: about our cron, and averaging it in silently understates every state.
#:
#: The number is measured, not chosen (DEC-323). Ranked by share-of-running-max
#: over 176 days, the observed values are: six days at 0.04 (a total outage, one
#: nursery reporting), one at 0.56, one at 0.60, then the healthy floor at 0.89
#: and everything else at 0.92 or above. 0.75 sits in the empty band between the
#: worst partial day and the worst healthy one, so it catches every outage and
#: no ordinary day.
PANEL_COMPLETENESS = 0.75


def complete_days(days: list[str], reporting: dict) -> tuple[list[str], list[str]]:
    """Split days into (measurable, excluded-as-incomplete).

    Completeness is judged against the largest panel seen UP TO that day, not
    against the final panel, because the panel legitimately grew from 8 to 25
    nurseries and March must not be excluded for being March.
    """
    kept, dropped, running_max = [], [], 0
    for day in days:
        count = reporting.get(day, 0)
        running_max = max(running_max, count)
        if running_max and count / running_max >= PANEL_COMPLETENESS:
            kept.append(day)
        else:
            dropped.append(day)
    return kept, dropped


def compute(stock: dict, all_days: list[str], reporting: dict, species: list[dict]) -> dict:
    """Compute the whole dataset: per-state, per-species and national scarcity."""
    names = {s["slug"]: s["common_name"] for s in species}
    days, excluded = complete_days(all_days, reporting)
    latest = days[-1]
    recent = days[-RECENT_DAYS:]

    per_state = {}
    for code, full_name in STATES:
        shippers = sorted(k for k in SHIPPING_MAP if nursery_ships_to(k, code))
        shipper_set = set(shippers)
        ever = set()
        per_day = {}
        for day in days:
            count = 0
            for slug, by_day in stock.items():
                if by_day.get(day, ()) and (by_day[day] & shipper_set):
                    count += 1
                    ever.add(slug)
            per_day[day] = count
        recent_counts = [per_day[d] for d in recent]
        all_counts = list(per_day.values())
        per_state[code] = {
            "name": full_name,
            "nurseries": len(shippers),
            "nursery_keys": shippers,
            "species_ever_reachable": len(ever),
            "species_never_reachable": sorted(
                names[s] for s in stock if s not in ever and s in names
            ),
            "avg_species_in_stock_per_day": round(sum(recent_counts) / len(recent_counts), 1),
            "avg_species_in_stock_per_day_whole_window": round(sum(all_counts) / len(all_counts), 1),
            "species_in_stock_latest_day": per_day[latest],
            "ever_slugs": sorted(ever),
        }

    # National scarcity: days on which a species was in stock at NO tracked
    # nursery. This is the "genuinely rare" list, and it is short.
    national = {}
    for slug, by_day in stock.items():
        if slug not in names:
            continue
        stocked_days = sum(1 for day in days if by_day.get(day))
        nurseries_ever = len(set().union(*by_day.values())) if by_day else 0
        national[slug] = {
            "name": names[slug],
            "days_in_stock_somewhere": stocked_days,
            "days_tracked": len(days),
            "pct_of_days": round(100 * stocked_days / len(days), 1) if days else 0,
            "nurseries_ever_stocking": nurseries_ever,
            "in_stock_today": bool(by_day.get(latest)) if latest else False,
        }

    return {
        "generated": date.today().isoformat(),
        "window": {
            "first_day": days[0],
            "last_day": latest,
            "days": len(days),
            "recent_days": len(recent),
            "recent_first_day": recent[0],
            "days_excluded_incomplete": len(excluded),
            "excluded_days": excluded,
        },
        "panel": {
            "nurseries_first_day": reporting.get(days[0], 0),
            "nurseries_last_day": reporting.get(latest, 0),
            "completeness_threshold": PANEL_COMPLETENESS,
        },
        "nurseries_tracked": len(SHIPPING_MAP),
        "species_tracked": len(species),
        "species_with_any_stock": len(national),
        "method": (
            "A species counts as reachable in a state on a day when at least one nursery whose "
            "published shipping policy covers that state had at least one listing of it in stock "
            "that day. Rolled up to nursery-day, never listing-day. Shipping is stated policy, "
            "not a test order."
        ),
        "licence": "CC BY 4.0. Attribution: treestock.com.au",
        "source_url": PAGE_URL,
        "states": per_state,
        "species": dict(sorted(national.items(), key=lambda kv: kv[1]["pct_of_days"])),
    }


# ----- Rendering -----


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_headline(result: dict) -> str:
    window = result["window"]
    tas = result["states"]["TAS"]
    vic = result["states"]["VIC"]
    never_tas = len(tas["species_never_reachable"])
    return f"""
<div class="bg-green-50 border border-green-200 rounded-lg p-5 mb-8">
  <p class="text-gray-800 mb-3">Across <strong>{window['days']} consecutive days</strong>
  ({window['first_day']} to {window['last_day']}), treestock recorded whether each of
  <strong>{result['species_with_any_stock']} fruit and bush tucker species</strong> was in stock at each of up to
  <strong>{result['nurseries_tracked']} Australian nurseries</strong> (the panel grew from
  {result['panel']['nurseries_first_day']} on the first day to {result['panel']['nurseries_last_day']} now),
  then joined that to each nursery's published shipping policy.</p>
  <p class="text-gray-800 mb-0">The finding: national rarity is mostly resolved, and the real constraint is
  <strong>which state you live in</strong>. Over the last {window['recent_days']} days a Victorian buyer could
  reach an average of <strong>{vic['avg_species_in_stock_per_day']} species on any given day</strong>. A
  Tasmanian buyer could reach <strong>{tas['avg_species_in_stock_per_day']}</strong>, and
  <strong>{never_tas} of the {result['species_with_any_stock']} species were never once buyable in Tasmania</strong>
  on any day in the window.</p>
</div>
"""


def render_state_table(result: dict) -> str:
    rows = []
    best = max(s["avg_species_in_stock_per_day"] for s in result["states"].values())
    order = sorted(
        result["states"].items(),
        key=lambda kv: kv[1]["avg_species_in_stock_per_day"],
        reverse=True,
    )
    for code, s in order:
        pct = round(100 * s["avg_species_in_stock_per_day"] / best) if best else 0
        bar_class = "bg-green-500" if pct >= 80 else ("bg-amber-500" if pct >= 50 else "bg-red-500")
        rows.append(f"""
    <tr class="border-b border-gray-100">
      <td class="py-2 pr-3 font-medium text-gray-900">{_esc(s['name'])} <span class="text-gray-400">({code})</span></td>
      <td class="py-2 px-3 text-right tabular-nums">{s['nurseries']}</td>
      <td class="py-2 px-3 text-right tabular-nums">{s['species_ever_reachable']}</td>
      <td class="py-2 px-3 text-right tabular-nums font-semibold">{s['avg_species_in_stock_per_day']}</td>
      <td class="py-2 px-3 text-right tabular-nums text-gray-500">{s['avg_species_in_stock_per_day_whole_window']}</td>
      <td class="py-2 pl-3 w-40">
        <div class="flex items-center gap-2">
          <div class="flex-1 bg-gray-100 rounded h-2"><div class="{bar_class} h-2 rounded" style="width:{pct}%"></div></div>
          <span class="text-xs text-gray-500 tabular-nums w-10 text-right">{pct}%</span>
        </div>
      </td>
    </tr>""")

    return f"""
<section id="by-state" class="mb-10">
  <h2 class="text-xl font-bold text-green-900 mb-2">Reachability by state</h2>
  <p class="text-gray-700 text-sm mb-4">"Species ever reachable" counts a species once if it was in stock at
  least once, on any day, at any nursery that ships to that state. "Average in stock per day" is the honest
  day-to-day figure: how many species a buyer in that state could actually have bought on a typical day. It is
  shown over the last {result['window']['recent_days']} days and over the whole window; the whole-window figure
  is lower everywhere because we were tracking fewer nurseries in March.</p>
  <div class="overflow-x-auto">
  <table class="w-full text-sm">
    <thead>
      <tr class="border-b-2 border-gray-200 text-left text-gray-600">
        <th class="py-2 pr-3 font-semibold">State</th>
        <th class="py-2 px-3 text-right font-semibold">Nurseries<br>shipping there</th>
        <th class="py-2 px-3 text-right font-semibold">Species ever<br>reachable</th>
        <th class="py-2 px-3 text-right font-semibold">Avg in stock/day<br>(last {result['window']['recent_days']} days)</th>
        <th class="py-2 px-3 text-right font-semibold">Avg in stock/day<br>(whole window)</th>
        <th class="py-2 pl-3 font-semibold">Share of best state</th>
      </tr>
    </thead>
    <tbody>{''.join(rows)}
    </tbody>
  </table>
  </div>
</section>
"""


def render_tasmania(result: dict) -> str:
    tas = result["states"]["TAS"]
    nt = result["states"]["NT"]
    wa = result["states"]["WA"]
    tas_nurseries = ", ".join(
        f"{NURSERY_NAMES.get(k, k)} ({nursery_location(k)})" for k in tas["nursery_keys"]
    )
    never = tas["species_never_reachable"]
    chips = "".join(
        f'<span class="inline-block bg-white border border-red-200 text-red-900 rounded px-2 py-0.5 text-xs mr-1 mb-1">{_esc(n)}</span>'
        for n in never
    )
    return f"""
<section id="tasmania" class="mb-10">
  <h2 class="text-xl font-bold text-green-900 mb-3">Tasmania, not Western Australia, is the cut-off state</h2>
  <p class="text-gray-700 mb-3">Quarantine rules on plant material into Western Australia, the Northern Territory
  and Tasmania are what shape this, and they do not bite evenly. Only <strong>{tas['nurseries']} of the
  {result['nurseries_tracked']} nurseries we track will send a plant to Tasmania</strong>
  ({_esc(tas_nurseries)}). The Northern Territory has {nt['nurseries']}. Western Australia, the state everyone
  worries about, has {wa['nurseries']}.</p>
  <p class="text-gray-700 mb-3">This is worth stating plainly because the rare fruit community in Western
  Australia generally assumes WA is the state that misses out. It is not.
  <strong>{wa['species_ever_reachable']} of {result['species_with_any_stock']} species reached a WA address</strong>
  at some point in the window, and WA buyers averaged {wa['avg_species_in_stock_per_day']} species in stock per
  day against Victoria's {result['states']['VIC']['avg_species_in_stock_per_day']}. Quarantine costs WA breadth,
  but not much of it. Tasmania has the problem WA thinks it has.</p>
  <details class="bg-red-50 border border-red-200 rounded-lg p-4">
    <summary class="cursor-pointer font-medium text-red-900">The {len(never)} species never once buyable in Tasmania in {result['window']['days']} days</summary>
    <div class="mt-3">{chips}</div>
    <p class="text-xs text-red-800 mt-3 mb-0">Never once in stock at any of the {tas['nurseries']} nurseries
    that ship to Tasmania, on any of the {result['window']['days']} days measured. Some of these are
    genuinely prohibited entry; most are simply not carried by a nursery that ships there.</p>
  </details>
</section>
"""


def render_national_scarcity(result: dict, top: int = 15) -> str:
    """The short list of species that are scarce nationally, not just locally."""
    scarce = [v for v in result["species"].values() if v["pct_of_days"] < 100][:top]
    saturated = sum(1 for v in result["species"].values() if v["pct_of_days"] == 100)
    if not scarce:
        return ""
    rows = "".join(f"""
    <tr class="border-b border-gray-100">
      <td class="py-2 pr-3 text-gray-900">{_esc(v['name'])}</td>
      <td class="py-2 px-3 text-right tabular-nums">{v['nurseries_ever_stocking']}</td>
      <td class="py-2 px-3 text-right tabular-nums">{v['days_in_stock_somewhere']}</td>
      <td class="py-2 pl-3 text-right tabular-nums font-semibold">{v['pct_of_days']}%</td>
    </tr>""" for v in scarce)
    return f"""
<section id="national" class="mb-10">
  <h2 class="text-xl font-bold text-green-900 mb-2">What is actually rare nationally</h2>
  <p class="text-gray-700 text-sm mb-4"><strong>{saturated} of {result['species_with_any_stock']} species were in
  stock somewhere in Australia on every single one of the {result['window']['days']} days.</strong> "Rare fruit"
  is, for the most part, a description of how few people grow something rather than how hard it is to buy.
  These are the exceptions: species that were unbuyable anywhere in the country for a meaningful share of the
  window. Bare-root seasonality is not scarcity, so read a winter-deciduous species here with that in mind.</p>
  <div class="overflow-x-auto">
  <table class="w-full text-sm">
    <thead>
      <tr class="border-b-2 border-gray-200 text-left text-gray-600">
        <th class="py-2 pr-3 font-semibold">Species</th>
        <th class="py-2 px-3 text-right font-semibold">Nurseries that<br>ever stocked it</th>
        <th class="py-2 px-3 text-right font-semibold">Days in stock<br>somewhere</th>
        <th class="py-2 pl-3 text-right font-semibold">Share of days</th>
      </tr>
    </thead>
    <tbody>{rows}
    </tbody>
  </table>
  </div>
</section>
"""


def render_matrix(result: dict) -> str:
    """Full species x state matrix. This is the part somebody would cite a row of."""
    codes = [c for c, _ in STATES]
    ever = {c: set(result["states"][c]["ever_slugs"]) for c in codes}
    header = "".join(
        f'<th class="py-2 px-1 text-center font-semibold w-10">{c}</th>' for c in codes
    )
    rows = []
    for slug, v in sorted(result["species"].items(), key=lambda kv: kv[1]["name"].lower()):
        cells = []
        for c in codes:
            if slug in ever[c]:
                cells.append('<td class="py-1.5 px-1 text-center text-green-600" title="reachable">&#10003;</td>')
            else:
                cells.append('<td class="py-1.5 px-1 text-center text-red-400" title="never reachable">&#8212;</td>')
        rows.append(f"""
    <tr class="border-b border-gray-100">
      <td class="py-1.5 pr-3 text-gray-900 whitespace-nowrap"><a href="/species/{_esc(slug)}.html" class="hover:underline">{_esc(v['name'])}</a></td>
      <td class="py-1.5 px-2 text-right tabular-nums text-gray-500">{v['pct_of_days']}%</td>
      {''.join(cells)}
    </tr>""")
    return f"""
<section id="matrix" class="mb-10">
  <h2 class="text-xl font-bold text-green-900 mb-2">Every species, every state</h2>
  <p class="text-gray-700 text-sm mb-4">A tick means the species was in stock at least once, on at least one day
  in the window, at a nursery that ships to that state. It does not mean it is in stock now. The percentage is
  the share of days it was in stock somewhere in Australia.</p>
  <div class="overflow-x-auto border border-gray-200 rounded-lg">
  <table class="w-full text-sm">
    <thead class="bg-gray-50">
      <tr class="border-b-2 border-gray-200 text-left text-gray-600">
        <th class="py-2 pl-3 pr-3 font-semibold">Species</th>
        <th class="py-2 px-2 text-right font-semibold">Days in<br>stock</th>
        {header}
      </tr>
    </thead>
    <tbody>{''.join(rows)}
    </tbody>
  </table>
  </div>
</section>
"""


def render_method(result: dict) -> str:
    window = result["window"]
    return f"""
<section id="method" class="mb-10">
  <h2 class="text-xl font-bold text-green-900 mb-3">Method, and what this does not say</h2>
  <p class="text-gray-700 mb-3">Every day since {window['first_day']}, treestock reads the public catalogue of
  each tracked nursery and records, per listing, whether it is in stock. Listings are matched to a species and
  then <strong>rolled up to nursery-day</strong>: a nursery stocking twenty named varieties of one species
  counts once, the same as a nursery stocking one. Shipping is taken from each nursery's published policy.</p>
  <ul class="list-disc pl-5 text-gray-700 space-y-2 mb-3">
    <li><strong>Stated policy, not a test order.</strong> We have not attempted to send a plant to every state.
    A nursery that says it ships to Tasmania is counted as shipping to Tasmania.</li>
    <li><strong>The panel grew during the window.</strong> On {window['first_day']} we were reading
    {result['panel']['nurseries_first_day']} nurseries; on {window['last_day']} we were reading
    {result['panel']['nurseries_last_day']}. Early days therefore understate reachability everywhere, which is
    why the state table also shows a last-{result['window']['recent_days']}-day average, and why the
    "ever reachable" columns are the conservative reading rather than the generous one.</li>
    <li><strong>Seasonality is not scarcity.</strong> Bare-root deciduous stock (apple, pear, walnut, currant)
    is legitimately absent for months and then plentiful. Read the national scarcity table with that in mind.</li>
    <li><strong>A missing day is "not listed", not "out of stock".</strong> Days are only counted where the
    history has an entry for that listing, so a delisted product does not silently score as unavailable.</li>
    <li><strong>Days when our own collection failed are thrown away, not averaged in.</strong>
    {result['window']['days_excluded_incomplete']} days are excluded on that basis: on those days fewer than
    {int(result['panel']['completeness_threshold'] * 100)}% of the nurseries we were then tracking returned any
    data at all, and "nothing was in stock anywhere in Australia" would have been a fact about our scrapers
    rather than about Australian nurseries. The excluded dates are listed in the JSON so you can check the
    decision rather than take our word for it.</li>
    <li><strong>Some listings are seed, not trees.</strong> A handful of species are reachable only as seed at
    some nurseries, which is a different purchase from a grafted tree.</li>
    <li><strong>This is the nurseries we track, not every nursery in Australia.</strong> A species absent here
    may be available from a small grower, a club sale or a private seller.</li>
  </ul>
</section>
"""


def render_citation(result: dict) -> str:
    window = result["window"]
    return f"""
<section id="cite" class="mb-10">
  <h2 class="text-xl font-bold text-green-900 mb-3">Use it, cite it, download it</h2>
  <p class="text-gray-700 mb-4">This dataset is published under
  <a href="https://creativecommons.org/licenses/by/4.0/" class="text-green-700 hover:underline" rel="license">CC BY 4.0</a>.
  Reuse it anywhere, including commercially, as long as you credit treestock.com.au and link back. Journalists,
  clubs, nurseries and researchers are all welcome to it; if you want a cut we do not publish, ask.</p>
  <div class="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-4">
    <p class="text-xs uppercase tracking-wide text-gray-500 mb-2">Suggested citation</p>
    <p class="text-sm text-gray-800 font-mono mb-0">treestock.com.au, <em>Fruit tree shipping reachability by
    Australian state</em>, {window['first_day']} to {window['last_day']}
    ({window['days']} days, {result['nurseries_tracked']} nurseries). Retrieved {result['generated']}.
    <a href="{PAGE_URL}" class="text-green-700 hover:underline">{PAGE_URL}</a></p>
  </div>
  <p class="text-gray-700 mb-0">The full dataset behind this page, including the per-species and per-state
  breakdowns, is available as machine-readable JSON:
  <a href="/{DATA_SLUG}" class="text-green-700 hover:underline font-medium">{DATA_URL}</a>. It is rebuilt every
  night. Questions or corrections: <a href="mailto:ben@treestock.com.au" class="text-green-700 hover:underline">ben@treestock.com.au</a>.</p>
</section>
"""


def render_related() -> str:
    return """
<section class="mb-10">
  <h2 class="text-xl font-bold text-green-900 mb-3">Related</h2>
  <ul class="list-disc pl-5 text-gray-700 space-y-1">
    <li><a href="/wa-rare-fruit-guide.html" class="text-green-700 hover:underline">Buying rare fruit trees in Western Australia</a>, the nine nurseries that will actually send you one</li>
    <li><a href="/species/" class="text-green-700 hover:underline">Live stock by species</a> across every tracked nursery</li>
    <li><a href="/nursery/" class="text-green-700 hover:underline">Every nursery we track</a>, with its shipping restrictions</li>
    <li><a href="/bare-root.html" class="text-green-700 hover:underline">Bare-root season</a>, why deciduous stock disappears for half the year</li>
  </ul>
</section>
"""


def build_jsonld(result: dict) -> str:
    window = result["window"]
    payload = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "Fruit tree shipping reachability by Australian state",
        "description": (
            f"Which fruit and bush tucker species could actually be bought and shipped to each Australian "
            f"state, measured daily across {window['days']} days and {result['nurseries_tracked']} nurseries."
        ),
        "url": PAGE_URL,
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "creator": {"@type": "Organization", "name": "treestock.com.au", "url": "https://treestock.com.au"},
        "temporalCoverage": f"{window['first_day']}/{window['last_day']}",
        "spatialCoverage": {"@type": "Place", "name": "Australia"},
        "dateModified": result["generated"],
        "isAccessibleForFree": True,
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": DATA_URL}
        ],
        "keywords": [
            "fruit trees", "Australia", "plant quarantine", "nursery stock",
            "shipping restrictions", "rare fruit", "bush tucker",
        ],
    }
    return f'<script type="application/ld+json">{json.dumps(payload)}</script>'


def build_page(result: dict) -> str:
    window = result["window"]
    tas = result["states"]["TAS"]
    never_tas = len(tas["species_never_reachable"])
    description = (
        f"{never_tas} of {result['species_with_any_stock']} fruit tree species were never once buyable in "
        f"Tasmania across {window['days']} days. A free, citable dataset of which species can actually be "
        f"shipped to each Australian state, from {result['nurseries_tracked']} nurseries."
    )
    head = render_head(
        title="Which Fruit Trees Can Be Shipped to Your State? (Australia)",
        description=description,
        canonical_url=PAGE_URL,
        og_title="Which fruit trees can actually be shipped to your state?",
        og_description=description,
        og_type="article",
        og_image="https://treestock.com.au/og-image.png",
        extra_head=build_jsonld(result),
    )
    header = render_header(active_path=f"/{PAGE_SLUG}")
    breadcrumb = render_breadcrumb([("Home", "/"), ("Shipping by state", "")])
    footer = render_footer()

    body = "\n".join([
        breadcrumb,
        '<h1 class="text-2xl font-bold text-green-900 mb-2">Which fruit trees can actually be shipped to your state?</h1>',
        f'<p class="text-gray-600 text-sm mb-6">A free, citable dataset measured daily across '
        f'{result["nurseries_tracked"]} Australian nurseries since {window["first_day"]}. '
        f'Updated {result["generated"]}.</p>',
        render_headline(result),
        render_state_table(result),
        render_tasmania(result),
        render_national_scarcity(result),
        render_matrix(result),
        render_method(result),
        render_citation(result),
        render_related(),
        render_treesmith_promo("species"),
    ])

    return f"""{head}
{header}

<main class="{CONTENT_MAX_WIDTH} mx-auto px-4 py-8">
{body}
</main>

{footer}
</body>
</html>"""


def main():
    if len(sys.argv) < 3:
        print("Usage: build_shipping_reachability.py /path/to/nursery-stock /path/to/output/")
        sys.exit(1)
    data_dir = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)

    species = enabled_species()
    lookup = build_species_lookup(species)
    stock, days, reporting = load_stock_history(data_dir, lookup)
    if not days:
        print("No availability history found; nothing to build.")
        sys.exit(1)

    result = compute(stock, days, reporting, species)

    page = output_dir / PAGE_SLUG
    page.write_text(build_page(result))
    print(f"Written: {page} ({page.stat().st_size} bytes)")

    # The JSON is the half a machine cites. Drop the internal ever_slugs lists,
    # which are a rendering detail and triple the file size.
    public = json.loads(json.dumps(result))
    for state in public["states"].values():
        state.pop("ever_slugs", None)
    data_file = output_dir / DATA_SLUG
    data_file.write_text(json.dumps(public, indent=2))
    print(f"Written: {data_file} ({data_file.stat().st_size} bytes)")

    tas = result["states"]["TAS"]
    print(
        f"  {result['window']['days']} days, {result['nurseries_tracked']} nurseries, "
        f"{result['species_with_any_stock']} species; "
        f"{len(tas['species_never_reachable'])} never reachable in TAS"
    )


if __name__ == "__main__":
    main()
