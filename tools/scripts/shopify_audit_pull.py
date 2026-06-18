#!/usr/bin/env python3
"""One-off: pull full Shopify catalogs for the three filtered nurseries and cache
the raw products to /tmp so the audit analysis can run offline (no re-fetching).
Run on the server (stores 403 residential IPs). DEC-207 follow-up audit."""
import urllib.request, json, time, sys

UA = "WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"
STORES = {
    "garden-world": "gardenworld.au",
    "diggers": "www.diggers.com.au",
    "forever-seeds": "forever-seeds.myshopify.com",
}

def pull(domain):
    out, page = [], 1
    while True:
        req = urllib.request.Request(
            "https://%s/products.json?limit=250&page=%d" % (domain, page),
            headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            d = json.load(urllib.request.urlopen(req, timeout=30)).get("products", [])
        except Exception as e:
            print("  ERROR page %d: %s" % (page, e)); break
        if not d:
            break
        out.extend(d); page += 1; time.sleep(1)
    return out

for key, domain in STORES.items():
    print("Pulling %s (%s)..." % (key, domain), flush=True)
    prods = pull(domain)
    # keep only the fields we need for the audit
    slim = [{"title": p.get("title"), "product_type": p.get("product_type"),
             "tags": p.get("tags"), "handle": p.get("handle")} for p in prods]
    with open("/tmp/%s_catalog.json" % key, "w") as f:
        json.dump(slim, f)
    print("  %s: %d products cached" % (key, len(slim)), flush=True)
print("DONE")
