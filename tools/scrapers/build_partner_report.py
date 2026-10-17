#!/usr/bin/env python3
"""
Monthly partner report for one nursery: the traffic treestock sent them, and
what our dataset says about the stock behind it.

This is the recruitment artefact DEC-248's affiliate plan called for (first
sketched by hand for Ross Creek on 2026-08-31). It is not
build_nursery_report.py, which pitches the cancelled $49 sponsored listing and
never reads Plausible.

Three joins, each something the nursery cannot build from its own analytics:

  1. Clicks we sent, by month, verifiable on utm_source=treestock.
  2. Clicks that landed on a sold-out page. Each click is judged against
     availability ON THE DAY OF THE CLICK (availability.json), not against one
     snapshot: the 2026-08-31 sample used a single snapshot and counted a
     mid-month restock as a lost sale.
  3. Varieties they list that treestock users are watching, set against every
     other nursery we track. Watchers in a state the nursery cannot ship to
     are dropped where we know the state (feedback: never quote demand a
     nursery cannot serve).

No price-positioning section. Title-token matching produced junk in the
August sample and the variety-slug matcher has not been wired to it.

Usage (on the server, needs Plausible secrets and the watch DB):
    python3 build_partner_report.py ross-creek --month 2026-09 \\
        --out /opt/dale/dashboard/reports/<unguessable-name>.html
"""
import argparse
import calendar
import collections
import json
import re
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
# plausible_stats lives with the autonomous tools: tools/autonomous locally,
# /opt/dale/autonomous on the server. Both are ../autonomous from here.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "autonomous"))

from build_variety_pages import slug_for_title  # noqa: E402
from stocklib.registry import NURSERY_NAMES, SHIPPING_MAP  # noqa: E402
from stocklib.snapshots import iter_nursery_snapshots  # noqa: E402
from stocklib.templates import render as render_template  # noqa: E402

DATA_DIR = Path("/opt/dale/data/nursery-stock")
WATCH_DB = Path("/opt/dale/data/variety_watches.db")
SITE_ID = "treestock.com.au"
OUTBOUND_GOAL = "Outbound Link: Click"

# A per-product restriction the nursery states in the title. These clicks are
# not lost sales: the line was never sellable outside Queensland. Bare root is
# deliberately NOT here: Ross Creek sells "Bare Root Potted" nationally, and
# the August sample wrongly set those aside.
RESTRICTED_RE = re.compile(r"\b(?:qld|queensland)\s+only\b", re.I)
RESTRICTED_STATE = "QLD"

AU_REGIONS = ("NSW", "VIC", "QLD", "WA", "SA", "ACT", "TAS", "NT")


# ---------------------------------------------------------------------------
# Pure helpers (tested in tests/test_partner_report.py)
# ---------------------------------------------------------------------------

def norm_url(url: str) -> str:
    """Product URL without scheme, www, query or trailing slash, lowercased.

    Click URLs carry utm params and availability keys carry "|sku:..."; both
    reduce to this.
    """
    url = url.split("|", 1)[0]
    p = urlparse(url if "//" in url else "https://" + url)
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host + p.path.rstrip("/").lower()


def availability_by_url(avail: dict) -> dict:
    """{norm_url: {"title": str, "days": {YYYY-MM-DD: bool}}}.

    availability.json is keyed per variant. A product is available on a day if
    ANY of its variants was.
    """
    out: dict = {}
    for key, rec in (avail.get("products") or {}).items():
        u = norm_url(key)
        entry = out.setdefault(u, {"title": rec.get("title", ""), "days": {}})
        for day, d in (rec.get("days") or {}).items():
            entry["days"][day] = entry["days"].get(day, False) or bool(d.get("a"))
    return out


def classify_clicks(daily_clicks: dict, avail: dict, titles: dict) -> dict:
    """Judge every product-page click against stock on the day it happened.

    daily_clicks: {day: {norm_url: n}}. avail: availability_by_url output.
    titles: {norm_url: title} for restriction checks (falls back to avail).

    Returns counts plus per-URL tallies for the lost and restricted buckets.
    'unknown' covers product URLs with no history for that day (new listing,
    missed scrape); they are reported, not guessed.
    """
    res = {"product": 0, "other": 0, "in_stock": 0, "sold_out": 0,
           "restricted": 0, "unknown": 0,
           "lost_by_url": collections.Counter(),
           "restricted_by_url": collections.Counter(),
           "clicks_by_url": collections.Counter()}
    for day, urls in daily_clicks.items():
        for u, n in urls.items():
            if "/products/" not in u and u not in avail:
                res["other"] += n
                continue
            res["product"] += n
            res["clicks_by_url"][u] += n
            title = titles.get(u) or avail.get(u, {}).get("title", "")
            if RESTRICTED_RE.search(title):
                res["restricted"] += n
                res["restricted_by_url"][u] += n
                continue
            status = avail.get(u, {}).get("days", {}).get(day)
            if status is None:
                res["unknown"] += n
            elif status:
                res["in_stock"] += n
            else:
                res["sold_out"] += n
                res["lost_by_url"][u] += n
    return res


def catalogue_sold_out_share(avail: dict, days: list[str]) -> float | None:
    """Mean share of listed products that were sold out, across `days`.

    The baseline for the lost-clicks figure: if we sent traffic at random,
    this is the share that would hit a sold-out page.
    """
    shares = []
    for day in days:
        states = [e["days"][day] for e in avail.values() if day in e["days"]]
        if states:
            shares.append(sum(1 for s in states if not s) / len(states))
    return sum(shares) / len(shares) if shares else None


def servable_watchers(watchers: list[tuple[str, str | None]], ships_to) -> list[str]:
    """Emails that could actually buy from this nursery.

    watchers: [(email, state_or_None)]. None or 'ALL' means we do not know
    their state, so they are kept: the report says so rather than guessing.
    """
    ok = set(ships_to)
    return [e for e, st in watchers if st in (None, "ALL") or st in ok]


def region_summary(region_clicks: dict, total: int, ships_to,
                   restricted: set) -> dict:
    """Where this month's clicks came from, against where the nursery ships.

    region_clicks: {"NSW": {norm_url: n}, ...} for Australian states only.
    restricted: norm_urls of lines sold only in RESTRICTED_STATE.
    Clicks with no Australian region (overseas, or no geo) are 'elsewhere'.
    """
    ok = set(ships_to)
    rows = []
    for st in AU_REGIONS:
        n = sum((region_clicks.get(st) or {}).values())
        if n:
            rows.append({"state": st, "clicks": n, "ships": st in ok})
    rows.sort(key=lambda r: -r["clicks"])
    located = sum(r["clicks"] for r in rows)
    r_home = sum(n for u, n in (region_clicks.get(RESTRICTED_STATE) or {}).items()
                 if u in restricted)
    r_away = sum(n for st, urls in region_clicks.items() if st != RESTRICTED_STATE
                 for u, n in urls.items() if u in restricted)
    per_line = collections.defaultdict(lambda: {"home": 0, "away": 0})
    for st, urls in region_clicks.items():
        for u, n in urls.items():
            if u in restricted:
                per_line[u]["home" if st == RESTRICTED_STATE else "away"] += n
    return {"rows": rows, "elsewhere": max(total - located, 0),
            "unshippable": sum(r["clicks"] for r in rows if not r["ships"]),
            "restricted_home": r_home, "restricted_away": r_away,
            "restricted_per_line": dict(per_line)}


def classify_variety(mine: list[dict], others: list[dict]) -> str:
    """'only_you' | 'nobody' | 'you_and_others' | 'others_only'."""
    you = any(l["available"] for l in mine)
    them = any(l["available"] for l in others)
    if you and not them:
        return "only_you"
    if not you and not them:
        return "nobody"
    return "you_and_others" if you else "others_only"


def watch_growth(added_ats: list[str], month: str, n: int = 4,
                 today: date | None = None) -> dict:
    """New alerts set per month for the n months ending at `month`, plus the
    partial month after it so far. The partial month is reported as a count and
    a day span, never drawn as a bar: half a month next to whole ones reads as
    a drop. Counts are alerts still live (a cancelled alert leaves the table);
    on 2026-10-15 the id gaps showed deletions spread 1-18 a month, so they do
    not bend the curve."""
    per = collections.Counter(a[:7] for a in added_ats)
    months = prev_months(month, n)
    rows = [{"label": date(*map(int, m.split("-")), 1).strftime("%B"), "n": per.get(m, 0)}
            for m in months]
    y, m = map(int, month.split("-"))
    nxt = f"{y + (m == 12):04d}-{m % 12 + 1:02d}"
    after = {"label": date(*map(int, nxt.split("-")), 1).strftime("%B"),
             "n": per.get(nxt, 0), "days": 0}
    if today and today.strftime("%Y-%m") == nxt:
        after["days"] = today.day
    return {"rows": rows, "max": max(r["n"] for r in rows) or 1, "after": after}


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def month_bounds(month: str) -> tuple[date, date]:
    y, m = map(int, month.split("-"))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def prev_months(month: str, n: int) -> list[str]:
    y, m = map(int, month.split("-"))
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def _plausible():
    from plausible_stats import api_get, load_plausible_config
    token, base = load_plausible_config()
    return lambda params, endpoint="breakdown": api_get(
        base, token, f"/api/v1/stats/{endpoint}", params)


def outbound_by_url(get, date_param: str, period: str = "custom",
                    extra_filter: str = "") -> dict:
    """{raw_url: clicks}, paginated. Raises on an API error rather than
    returning zero (DEC-250: a failed request is not a quiet month)."""
    agg: dict = collections.Counter()
    for page in range(1, 41):
        res = get({"site_id": SITE_ID, "period": period, "date": date_param,
                   "property": "event:props:url",
                   "filters": f"event:name=={OUTBOUND_GOAL}" + (f";{extra_filter}" if extra_filter else ""),
                   "metrics": "events", "limit": 1000, "page": page})
        if res is None:
            raise RuntimeError(f"Plausible error for {period} {date_param} page {page}")
        rows = res.get("results") or []
        for r in rows:
            agg[r["url"]] += r.get("events", 0)
        if len(rows) < 1000:
            return agg
    raise RuntimeError(f"Plausible pagination cap hit for {date_param}")


def outbound_people(get, date_param: str, domain: str) -> int:
    """Unique people who clicked through to `domain`. This, not the click
    count, is what a nursery's Shopify shows as sessions: someone comparing two
    plants clicks twice but arrives once. Ross Creek's Shopify read 316 for
    September 2026 against our 460 clicks from 321 people, and the 460 alone
    looked like a 31% discrepancy to them."""
    res = get({"site_id": SITE_ID, "period": "custom", "date": date_param,
               "metrics": "visitors",
               "filters": f"event:goal=={OUTBOUND_GOAL};event:props:url==*{domain}*"},
              "aggregate")
    if res is None:
        raise RuntimeError(f"Plausible error for people {date_param}")
    return res["results"]["visitors"]["value"]


def domain_of(url: str) -> str:
    return norm_url(url).split("/", 1)[0]


def build(key: str, month: str) -> dict:
    get = _plausible()
    start, end = month_bounds(month)

    snaps = dict(iter_nursery_snapshots(DATA_DIR))
    mine_snap = snaps[key]
    domain = domain_of(mine_snap["products"][0]["url"])
    nursery_domains = {}
    for k, s in snaps.items():
        if s.get("products"):
            nursery_domains[domain_of(s["products"][0]["url"])] = k

    # 1. Monthly clicks, and this month's rank among nurseries.
    monthly = []
    for m in prev_months(month, 4):
        a, b = month_bounds(m)
        by_url = outbound_by_url(get, f"{a},{b}")
        mine = sum(n for u, n in by_url.items() if domain_of(u) == domain)
        tagged = sum(n for u, n in by_url.items()
                     if domain_of(u) == domain and "utm_source=treestock" in u)
        monthly.append({"month": m, "label": a.strftime("%B"), "clicks": mine,
                        "tagged": tagged,
                        "people": outbound_people(get, f"{a},{b}", domain)})
        if m == month:
            per_nursery = collections.Counter()
            for u, n in by_url.items():
                d = domain_of(u)
                if d in nursery_domains:
                    per_nursery[d] += n
            total_nursery = sum(per_nursery.values())
            rank = [d for d, _ in per_nursery.most_common()].index(domain) + 1
            n_nurseries = len(per_nursery)

    this = monthly[-1]
    prev = monthly[-2]

    # 2. Daily clicks against daily availability.
    avail = availability_by_url(json.load(open(DATA_DIR / key / "availability.json")))
    current = {norm_url(p["url"]): p for p in mine_snap["products"]}
    titles = {u: p.get("title", "") for u, p in current.items()}
    daily: dict = {}
    days = []
    d = start
    while d <= end:
        ds = d.isoformat()
        days.append(ds)
        by_url = outbound_by_url(get, ds, period="day")
        daily[ds] = collections.Counter()
        for u, n in by_url.items():
            if domain_of(u) == domain:
                daily[ds][norm_url(u)] += n
        d = date.fromordinal(d.toordinal() + 1)
    cls = classify_clicks(daily, avail, titles)
    baseline = catalogue_sold_out_share(avail, days)

    restricted_urls = {u for u, t in titles.items() if RESTRICTED_RE.search(t)}
    region_clicks = {}
    for st in AU_REGIONS:
        by_url = outbound_by_url(get, f"{start},{end}", extra_filter=f"visit:region==AU-{st}")
        region_clicks[st] = collections.Counter()
        for u, n in by_url.items():
            if domain_of(u) == domain:
                region_clicks[st][norm_url(u)] += n
    regions = region_summary(region_clicks, this["clicks"], SHIPPING_MAP.get(key, []),
                             restricted_urls)

    def product_row(u, n):
        p = current.get(u)
        title = (p or {}).get("title") or avail.get(u, {}).get("title") or u
        return {"title": title, "url": (p or {}).get("url") or "https://" + u,
                "price": (p or {}).get("min_price"), "clicks": n,
                "now": None if p is None else bool(p.get("any_available")),
                "days_out": sum(1 for ds in days if avail.get(u, {}).get("days", {}).get(ds) is False)}

    top_clicked = [product_row(u, n) for u, n in cls["clicks_by_url"].most_common(10)]
    lost = [product_row(u, n) for u, n in cls["lost_by_url"].most_common()]
    restricted = [dict(product_row(u, n), **regions["restricted_per_line"].get(u, {"home": 0, "away": 0}))
                  for u, n in cls["restricted_by_url"].most_common()]

    # 3. Watched varieties.
    con = sqlite3.connect(f"file:{WATCH_DB}?mode=ro", uri=True)
    watch_rows = con.execute(
        "SELECT w.variety_slug, w.variety_title, w.email, p.state, w.added_at "
        "FROM watches w LEFT JOIN watcher_prefs p ON p.email = w.email").fetchall()
    by_slug = collections.defaultdict(list)
    vtitle = {}
    for slug, vt, email, state, _ in watch_rows:
        by_slug[slug].append((email, state))
        vtitle[slug] = vt
    all_watchers = {e for _, _, e, _, _ in watch_rows}
    state_known = {e for _, _, e, st, _ in watch_rows if st not in (None, "ALL")}

    listings = collections.defaultdict(list)
    for k, s in snaps.items():
        for p in s.get("products") or []:
            slug = slug_for_title(p.get("title", ""))
            if slug and slug in by_slug:
                listings[slug].append({"nursery": k, "title": p["title"],
                                       "price": p.get("min_price"),
                                       "available": bool(p.get("any_available"))})
    ships_to = SHIPPING_MAP.get(key, [])
    watched = []
    dropped_unshippable = set()
    rc_watchers = set()
    for slug, ls in listings.items():
        mine = [l for l in ls if l["nursery"] == key]
        if not mine:
            continue
        others = [l for l in ls if l["nursery"] != key]
        ok = servable_watchers(by_slug[slug], ships_to)
        dropped_unshippable |= {e for e, _ in by_slug[slug]} - set(ok)
        if not ok:
            continue
        rc_watchers |= set(ok)
        other_names = sorted({NURSERY_NAMES.get(l["nursery"], l["nursery"]) for l in others})
        watched.append({
            "slug": slug, "title": vtitle.get(slug) or slug,
            "waiting": len(set(ok)), "kind": classify_variety(mine, others),
            "mine_in": any(l["available"] for l in mine),
            "mine_prices": sorted({l["price"] for l in mine if l["price"]}),
            "mine_in_prices": sorted({l["price"] for l in mine if l["price"] and l["available"]}),
            "mine_restricted": all(RESTRICTED_RE.search(l["title"]) for l in mine),
            "others_n": len({l["nursery"] for l in others}),
            "others_in": len({l["nursery"] for l in others if l["available"]}),
            "other_names": other_names,
        })
    watched.sort(key=lambda r: (-r["waiting"], r["title"]))

    top_watched = collections.Counter({s: len({e for e, _ in v}) for s, v in by_slug.items()}).most_common(1)[0]

    return {
        "key": key, "name": NURSERY_NAMES.get(key, key), "domain": domain,
        "month": month, "month_label": start.strftime("%B %Y"),
        "month_name": start.strftime("%B"),
        "generated": datetime.now(timezone.utc).strftime("%-d %B %Y"),
        "scraped_at": mine_snap.get("scraped_at", ""),
        "monthly": monthly, "this": this, "prev": prev,
        "max_monthly": max(m["people"] for m in monthly) or 1,
        "rank": rank, "n_nurseries": n_nurseries,
        "share": this["clicks"] / total_nursery if total_nursery else 0,
        "tagged_share": this["tagged"] / this["clicks"] if this["clicks"] else 0,
        "cls": {k: v for k, v in cls.items() if not isinstance(v, collections.Counter)},
        "lost_products": len(lost), "baseline": baseline,
        "top_clicked": top_clicked, "lost": lost, "restricted": restricted,
        "watched": watched,
        "only_you": [w for w in watched if w["kind"] == "only_you"],
        "nobody": [w for w in watched if w["kind"] == "nobody"],
        "n_watchers": len(all_watchers), "n_state_known": len(state_known),
        "n_dropped": len(dropped_unshippable), "n_watching_yours": len(rc_watchers),
        "n_varieties_yours": len(watched),
        "growth": watch_growth([a for *_, a in watch_rows], month,
                               today=datetime.now(timezone.utc).date()),
        "top_watched": {"title": vtitle[top_watched[0]], "n": top_watched[1],
                        "yours": any(w["slug"] == top_watched[0] for w in watched)},
        "ships_to": ships_to, "regions": regions,
        "n_days": len(days),
        "no_ship": [s for s in AU_REGIONS if s not in ships_to],
        "listed": len(current),
        "sold_out_now": sum(1 for p in current.values() if not p.get("any_available")),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("nursery")
    ap.add_argument("--month", required=True, help="YYYY-MM, a complete month")
    ap.add_argument("--out", required=True)
    ap.add_argument("--contact", default="", help="first name for the dek line")
    args = ap.parse_args(argv)

    ctx = build(args.nursery, args.month)
    ctx["contact"] = args.contact
    html = render_template("partner_report.html.j2", **ctx)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    summary = {k: ctx[k] for k in ("this", "prev", "rank", "n_nurseries", "share",
                                   "tagged_share", "cls", "lost_products", "baseline",
                                   "n_watchers", "n_state_known", "n_dropped",
                                   "n_watching_yours", "n_varieties_yours", "top_watched",
                                   "listed", "sold_out_now")}
    summary["regions"] = {k: v for k, v in ctx["regions"].items() if k != "restricted_per_line"}
    summary["growth"] = ctx["growth"]
    summary["monthly"] = [(m["label"], m["people"], m["clicks"]) for m in ctx["monthly"]]
    summary["only_you"] = [(w["title"], w["waiting"]) for w in ctx["only_you"]]
    summary["nobody"] = [(w["title"], w["waiting"], w["others_n"]) for w in ctx["nobody"]][:12]
    summary["lost_top"] = [(r["title"], r["clicks"], r["now"]) for r in ctx["lost"][:12]]
    summary["restricted"] = [(r["title"], r["clicks"]) for r in ctx["restricted"]]
    summary["top_clicked"] = [(r["title"], r["clicks"], r["now"]) for r in ctx["top_clicked"]]
    print(json.dumps(summary, indent=1, default=str))
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
