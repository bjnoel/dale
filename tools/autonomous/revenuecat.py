#!/usr/bin/env python3
"""RevenueCat reader: receipt-grade Treesmith revenue (DAL-265, DEC-260).

Why this exists
---------------
Every revenue figure this business has ever quoted came from PostHog's
`purchase_succeeded`, which is client-side telemetry fired by our own app.
That is a claim, not a receipt. It was wrong in both directions:

* It did not exist before 2026-07-01, so the production sale on 2026-06-26
  is absent from it entirely. PostHog knows about 2 sales; there are 3.
* It records the sticker price the user saw, not the money we receive.
  A$39.99 of Pro is US$27.74 gross and US$17.66 in proceeds once the store
  commission and tax come out: 64% of the number we were reporting.

RevenueCat sits between the app and the stores and holds the validated
receipt, including `environment` (so sandbox cannot be mistaken for real
money) and a `revenue_in_usd` breakdown of gross, commission, tax and
proceeds. Proceeds is what lands in the bank and is the only figure that
should ever be called revenue.

Method notes
------------
There is no project-wide purchase listing in the v2 API (`/purchases`
requires a `store_purchase_identifier`), so the authoritative sweep walks
every customer. `/metrics/overview` costs one call and reports 28-day GROSS,
which is used here purely as an independent cross-check of the sweep, per
DEC-259: a number nobody can recompute is a number nobody can falsify.

Every list read follows `next_page` to exhaustion (DEC-255 / DAL-261).
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_ROOT = "https://api.revenuecat.com/v2"
SECRETS_DIR = "/opt/dale/secrets"
PAGE_LIMIT = 100
MAX_WORKERS = 8


# ── Credentials ────────────────────────────────────────────────────────────

def load_revenuecat_credentials(secrets_dir=SECRETS_DIR):
    """Return (project_id, api_key) from secrets/revenuecat.env.

    The key is a project-scoped v2 secret key and is read-only (confirmed by
    Benedict in the RevenueCat dashboard, DAL-267). It is NOT valid for the
    v1 API, which rejects it with code 7723; use v2 endpoints only.
    """
    path = os.path.join(secrets_dir, "revenuecat.env")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No RevenueCat credentials at {path}. The key is Benedict's to "
            "create; it cannot be recovered from the app mirror because both "
            "RevenueCat keys there are String.fromEnvironment at build time."
        )
    project_id = api_key = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("REVENUECAT_PROJECT_ID="):
                project_id = line.split("=", 1)[1].strip()
            elif line.startswith("REVENUECAT_API_KEY="):
                api_key = line.split("=", 1)[1].strip()
    if not project_id or not api_key:
        raise ValueError(
            "revenuecat.env must set REVENUECAT_PROJECT_ID and "
            "REVENUECAT_API_KEY"
        )
    return project_id, api_key


# ── Transport ──────────────────────────────────────────────────────────────

def _open(url, api_key):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "dale-revenuecat/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def rc_get(path, api_key, project_id=None, _opener=None):
    """GET one v2 URL. `path` may be absolute (as `next_page` returns)."""
    opener = _opener or _open
    if path.startswith("http"):
        url = path
    else:
        url = f"{API_ROOT}/projects/{project_id}{path}"
    return opener(url, api_key)


def paginate(path, api_key, project_id=None, _opener=None):
    """Follow `next_page` to exhaustion and return every item.

    DEC-255: a saturated first page and a complete small result set look
    identical at the call site. Stopping after one request is the defect that
    produced five wrong numbers in five days, so this never returns a partial
    list; it either reads everything or raises.
    """
    items = []
    url = path
    seen = set()
    while url:
        payload = rc_get(url, api_key, project_id, _opener=_opener)
        items.extend(payload.get("items", []))
        nxt = payload.get("next_page")
        if nxt and nxt in seen:
            raise RuntimeError(f"RevenueCat pagination loop at {nxt}")
        if nxt:
            seen.add(nxt)
        url = nxt
    return items


# ── Fetchers ───────────────────────────────────────────────────────────────

def fetch_customers(project_id, api_key, _opener=None):
    return paginate(f"/customers?limit={PAGE_LIMIT}", api_key, project_id,
                    _opener=_opener)


def fetch_purchases(project_id, api_key, customers=None, _opener=None,
                    max_workers=MAX_WORKERS):
    """Every purchase record across every customer.

    There is no project-wide purchase list in the v2 API, so this is O(number
    of customers) requests. That is ~420 today and grows with installs, which
    is acceptable weekly and would not be acceptable hourly.
    """
    if customers is None:
        customers = fetch_customers(project_id, api_key, _opener=_opener)

    def one(customer):
        cid = urllib.parse.quote(customer["id"], safe="")
        return paginate(f"/customers/{cid}/purchases?limit={PAGE_LIMIT}",
                        api_key, project_id, _opener=_opener)

    purchases = []
    if max_workers and max_workers > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for got in pool.map(one, customers):
                purchases.extend(got)
    else:
        for customer in customers:
            purchases.extend(one(customer))
    return purchases


def fetch_overview(project_id, api_key, _opener=None):
    """The dashboard's headline metrics. One call, used as a cross-check.

    `revenue` here is 28-day GROSS in USD, not proceeds, and not all-time.
    Do not report it as revenue on its own.
    """
    payload = rc_get("/metrics/overview", api_key, project_id, _opener=_opener)
    return {m["id"]: m.get("value") for m in payload.get("metrics", [])}


# ── Summary ────────────────────────────────────────────────────────────────

def _month(purchase):
    import datetime
    ts = purchase.get("purchased_at") or 0
    return datetime.datetime.fromtimestamp(
        ts / 1000, datetime.timezone.utc).strftime("%Y-%m")


def summarise(purchases):
    """Split purchases by environment and total the money we actually receive.

    `environment` is never inferred. RevenueCat always sets it, so unlike
    PostHog's `purchase_succeeded` (where 13 launch-era events are untagged
    and DEC-253 had to invent an 'untagged' bucket) anything that is not
    literally "production" is excluded from revenue rather than assumed real.
    """
    by_env = {}
    for p in purchases:
        env = p.get("environment") or "unknown"
        rev = p.get("revenue_in_usd") or {}
        bucket = by_env.setdefault(env, {
            "n": 0, "gross": 0.0, "proceeds": 0.0,
            "commission": 0.0, "tax": 0.0,
        })
        bucket["n"] += 1
        for field in ("gross", "proceeds", "commission", "tax"):
            bucket[field] += rev.get(field) or 0.0
    for bucket in by_env.values():
        for field in ("gross", "proceeds", "commission", "tax"):
            bucket[field] = round(bucket[field], 2)

    production = [p for p in purchases if p.get("environment") == "production"]
    by_month = {}
    for p in production:
        rev = p.get("revenue_in_usd") or {}
        m = by_month.setdefault(_month(p), {"n": 0, "proceeds": 0.0})
        m["n"] += 1
        m["proceeds"] += rev.get("proceeds") or 0.0
    for m in by_month.values():
        m["proceeds"] = round(m["proceeds"], 2)

    prod = by_env.get("production", {"n": 0, "gross": 0.0, "proceeds": 0.0,
                                     "commission": 0.0, "tax": 0.0})
    return {
        "by_env": by_env,
        "by_month": dict(sorted(by_month.items())),
        "production_n": prod["n"],
        "production_gross_usd": prod["gross"],
        "production_proceeds_usd": prod["proceeds"],
        "countries": sorted({p.get("country") or "?" for p in production}),
        "stores": sorted({p.get("store") or "?" for p in production}),
    }


def collect(project_id=None, api_key=None, _opener=None):
    """One call site for everything: customers, purchases, summary, overview."""
    if project_id is None or api_key is None:
        project_id, api_key = load_revenuecat_credentials()
    customers = fetch_customers(project_id, api_key, _opener=_opener)
    purchases = fetch_purchases(project_id, api_key, customers,
                                _opener=_opener)
    summary = summarise(purchases)
    summary["customers"] = len(customers)
    try:
        summary["overview"] = fetch_overview(project_id, api_key,
                                             _opener=_opener)
    except Exception as e:  # noqa: BLE001 - the cross-check is optional
        summary["overview"] = {"error": str(e)[:120]}
    summary["purchases"] = purchases
    return summary


# ── CLI ────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read validated Treesmith revenue from RevenueCat.")
    parser.add_argument("--json", action="store_true",
                        help="emit the full summary as JSON")
    args = parser.parse_args(argv)

    summary = collect()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    import datetime
    print(f"Customers: {summary['customers']}")
    print(f"Purchase records: {len(summary['purchases'])}\n")
    header = (f"{'purchased (UTC)':<17} {'environment':<11} {'store':<11} "
              f"{'cc':<3} {'gross':>8} {'proceeds':>9}")
    print(header)
    print("-" * len(header))
    for p in sorted(summary["purchases"],
                    key=lambda r: r.get("purchased_at") or 0):
        rev = p.get("revenue_in_usd") or {}
        when = datetime.datetime.fromtimestamp(
            (p.get("purchased_at") or 0) / 1000,
            datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
        print(f"{when:<17} {p.get('environment',''):<11} "
              f"{p.get('store',''):<11} {p.get('country') or '?':<3} "
              f"{rev.get('gross', 0):>8.2f} {rev.get('proceeds', 0):>9.2f}")

    print()
    for env, b in sorted(summary["by_env"].items()):
        label = "REVENUE" if env == "production" else "excluded"
        print(f"{env:<11} {b['n']:>2} purchases  gross US${b['gross']:>7.2f}  "
              f"proceeds US${b['proceeds']:>7.2f}  [{label}]")
    print(f"\nProduction proceeds all time: "
          f"US${summary['production_proceeds_usd']:.2f} "
          f"from {summary['production_n']} purchases "
          f"({', '.join(summary['countries']) or 'none'})")
    for month, m in summary["by_month"].items():
        print(f"  {month}  {m['n']} purchase(s)  US${m['proceeds']:.2f}")

    ov = summary.get("overview") or {}
    if "revenue" in ov:
        print(f"\nCross-check, RevenueCat overview 28d gross: "
              f"US${ov['revenue']} (active subs {ov.get('active_subscriptions')}, "
              f"MRR US${ov.get('mrr')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
