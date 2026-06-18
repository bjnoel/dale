# Scraper coverage audit (Shopify + BigCommerce follow-up to DEC-207)

**Status:** not started. Follow-up from DEC-207 (2026-06-18).
**Goal:** confirm the Shopify and BigCommerce scrapers are not silently dropping
real fruit/nut/berry stock the way the WooCommerce scrapers were, and fix any
that are.

Read this whole file first, then execute. It is self-contained: a fresh session
needs no prior context beyond what is here plus the linked files.

---

## 1. Background: the bug class

DEC-207 found that `tools/scrapers/woocommerce_scraper.py` was silently dropping
real fruit trees at three nurseries. The cause was an **include-filter that was
too narrow**: it kept a product only if the product's own category slugs matched
the nursery's configured allow-list. When a nursery tagged a tree with only a
leaf category (e.g. Guildford filed "Fig - Peter Good" under just `fig-tree`,
with no `fruits-nuts` parent), the filter dropped it. The scraper still ran fine
and returned hundreds of products, so the gap was invisible. Guildford went from
611 to 838 captured products once fixed; Engall's 55 to 70; Yalca 188 to 198.

The same *shape* of risk (a narrow include-filter that can drop mistagged fruit)
exists in two other scrapers that use different mechanisms. Neither is confirmed
broken. This audit checks them.

The key insight to carry in: **"the scraper returns plenty of products" does not
mean "it returns all of them."** Always compare captured-vs-ground-truth, not
captured-vs-zero.

See `decisions/decision-log.md` DEC-207 and memory
`project_scraper_leaf_category_gap.md` for the full write-up.

---

## 2. Scope: exactly which nurseries are at risk

Only nurseries that apply an **include-filter** can drop fruit. Nurseries with no
filter capture everything (the downstream `stocklib.classify` junk filter is an
*exclude* list, so it cannot drop fruit, with one caveat noted below).

### Shopify (`tools/scrapers/shopify_scraper.py`)
Pulls the full catalog from `/products.json?limit=250&page=N`, then optionally
filters. Three nurseries filter; the rest keep everything.

| Nursery key | Filter | Config value | Risk |
|---|---|---|---|
| `garden-world` | `product_types` (exact, lowercased) | `["FOOD PLANTS"]` | Fruit with a different/empty `product_type` is dropped. Exact match, so higher risk than substring. |
| `diggers` | `fruit_tags` (tag membership) | `["all fruit & nuts", "all fruit &amp; nuts", "all berries", "fruit trees", "nuts"]` | Fruit lacking one of these tags is dropped. |
| `forever-seeds` | `fruit_tags` | `["Fruit", "edible", "citrus"]` | Fruit lacking these tags is dropped. Note: seeds, not live plants. |

No-filter Shopify nurseries (not at risk of dropping fruit): `ross-creek`,
`ladybird`, `fruitopia`, `fruit-salad-trees`, `all-season-plants-wa`,
`ausnurseries`, `fruit-tree-cottage`, `perth-mobile-nursery`. Sanity-skim them
only if time permits (secondary caveat below).

### BigCommerce (`tools/scrapers/bigcommerce_scraper.py`)
One nursery: `heritage-fruit-trees`. HTML-scraped. It only walks these category
slugs:
```
CATEGORIES = ["fruit-trees", "nut-trees", "berries-and-vine-fruit"]
```
Risk: a fruit product in a category not covered by those three (directly or as a
child). Note `SKIP_SLUGS` already lists `blueberries`, `kiwi-fruit`,
`all-grape-varieties` as "skip" pages. **Check whether those (and any citrus/fig
category) are standalone categories whose products do NOT also appear under the
three scraped categories.** If so, they are being missed.

### Out of scope (different mechanism, low risk; name but do not deep-dive)
- `ecwid_scraper.py` (one nursery): discovers product URLs and *excludes*
  system/category pages. Exclude-based, so it does not drop fruit by include-gap.
- `daleys_scraper.py`: parses a broad product export with category fields;
  captures broadly (~425 products). No narrow include-filter.

### Secondary caveat (all scrapers)
`stocklib.classify.NON_PLANT_KEYWORDS` is an *exclude* filter applied downstream.
It can in theory false-positive and drop a real fruit whose title contains a junk
keyword. Low priority, but if a specific expected product is missing and is NOT
explained by the include-filter, check it against `NON_PLANT_KEYWORDS` and
`is_real_product` in `stocklib/classify.py`.

---

## 3. Environment and gotchas (read before running anything)

- **Run audits from the server, not locally.** These stores 403 a local/residential
  IP. SSH in: `ssh dale-server`. Use the scraper's real User-Agent:
  `WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)`.
- **Server data path:** `/opt/dale/data/nursery-stock/<key>/` (`latest.json`,
  dated `YYYY-MM-DD.json`, `availability.json`). `DALE_DATA_DIR=/opt/dale/data`.
- **Repo on server:** `/opt/dale/repo` (git). Deployed scrapers run from
  `/opt/dale/scrapers/` and are synced from the repo by `tools/deploy.sh`.
- **Long server commands get auto-backgrounded by the harness.** Pull-the-whole-
  store scripts take 1-3 min. Run with `run_in_background: true` and poll the
  output file, or write results to a temp file on the server and read it back.
- **Never run `run-all-scrapers.sh` ad hoc** - it scrapes AND emails subscribers.
  Running a single scraper (`woocommerce_scraper.py <key>`, `shopify_scraper.py
  <key>`, `bigcommerce_scraper.py`) only scrapes + saves; it sends no emails.
- Tests: `python3 -m unittest discover tests/` from repo root (1633 tests as of
  DEC-207). Existing filter regression tests: `tests/test_woocommerce_filter.py`.

---

## 4. Method: ground-truth diff, per platform

For each target nursery: get the **full** product set independently, see what the
current filter keeps, and inspect what it drops. Judge whether the dropped items
are real fruit/nut/berry or correctly-excluded junk.

### 4a. Shopify (garden-world, diggers, forever-seeds)

Ground truth is easy: `/products.json` returns the entire catalog with
`product_type` and `tags`. Run this on the server (adjust the per-nursery filter
block). Template:

```python
# ssh dale-server, then: python3 << 'EOF'
import urllib.request, json, time
UA="WalkthroughBot/1.0 (+https://treestock.com.au; stock-monitoring)"
def pull(domain):
    out=[]; page=1
    while True:
        req=urllib.request.Request("https://%s/products.json?limit=250&page=%d"%(domain,page),
                                   headers={"User-Agent":UA,"Accept":"application/json"})
        d=json.load(urllib.request.urlopen(req,timeout=30)).get("products",[])
        if not d: break
        out.extend(d); page+=1; time.sleep(1)
    return out

# --- garden-world: product_type exact match ---
gw=pull("gardenworld.au")
wanted={"food plants"}
kept=[p for p in gw if (p.get("product_type") or "").lower() in wanted]
dropped=[p for p in gw if p not in kept]
from collections import Counter
print("garden-world: total=%d kept=%d dropped=%d"%(len(gw),len(kept),len(dropped)))
print("product_types being DROPPED (count):")
for t,n in Counter((p.get("product_type") or "(empty)") for p in dropped).most_common():
    print("   %4d  %s"%(n,t))
# eyeball: any dropped product_type that is clearly fruit? print samples:
for p in dropped[:40]:
    print("   -", p.get("title"), "| type=", repr(p.get("product_type")))
EOF
```

For `diggers` and `forever-seeds`, replace the filter with the tag check (mirror
`scrape_shopify`): a product is kept if any configured tag (lowercased) is in its
lowercased tags list. Then print the DROPPED products and their tags, and judge
whether any are fruit/nut/berry (or, for forever-seeds, edible plant seeds in
scope). Watch for fruit with empty tags or an unexpected tag spelling.

**What counts as a real miss:** a dropped product that is a fruit/nut/berry tree,
vine, or (for forever-seeds) an in-scope edible. **Not a miss:** ornamentals,
tools, pots, gift cards, bulbs, vegetables/herbs that are out of the fruit
taxonomy. When unsure whether a species is in scope, check
`stocklib/taxonomy.py` / `fruit_species.json` and `ENABLED_CATEGORIES`.

### 4b. BigCommerce (heritage-fruit-trees)

Ground truth = the store's full product list. Two ways, use whichever resolves:
1. **Sitemap:** fetch `https://www.heritagefruittrees.com.au/sitemap.xml` (may be
   an index pointing to a products sitemap, e.g. `/xmlsitemap.php?type=products`).
   Collect every `/product-or-slug/` URL. That is ground truth.
2. **Category enumeration:** fetch the store nav / each `product-category`-style
   page to list ALL category slugs, then compare to `CATEGORIES`. For each
   candidate fruit category not in `CATEGORIES` (especially `blueberries`,
   `kiwi-fruit`, `all-grape-varieties`, and any `citrus`/`figs`/`olives` cat),
   collect its product URLs.

Then run the live scraper to get the captured set and diff:
```bash
ssh dale-server
cd /opt/dale/scrapers && export DALE_DATA_DIR=/opt/dale/data
python3 bigcommerce_scraper.py 2>&1 | tail -5   # writes today's snapshot, no emails
python3 -c "import json;d=json.load(open('/opt/dale/data/nursery-stock/heritage-fruit-trees/latest.json'));print(d['product_count']);[print(' ',p['title']) for p in d['products'][:50]]"
```
Diff ground-truth URLs/titles against captured titles. Any fruit product on the
store but not captured, and whose category is one of the three scraped or a child
of them, is a parser bug; if it lives only in an unscraped category, it is a
coverage gap (the thing this audit is looking for).

---

## 5. If a gap is found: fix + email-safe rollout

Mirror DEC-207 exactly.

1. **Fix the config** in the repo (`tools/scrapers/<scraper>.py`):
   - Shopify product_types/tags: broaden the list to include the missing
     type/tag. If the dropped fruit has an empty/garbage product_type and cannot
     be caught by type, consider switching that nursery to `fruit_tags`, or (last
     resort) removing the filter and leaning on the downstream classify filter.
     The Shopify filter is inline in `scrape_shopify`; if you broaden it, consider
     extracting a small pure predicate so it can be unit-tested (the way
     `category_matches` was extracted for WooCommerce).
   - BigCommerce: add the missing category slug(s) to `CATEGORIES` and remove
     them from `SKIP_SLUGS` if present.
2. **Add a regression test** pinning the exact products that were being dropped
   (failing-then-passing). Put WooCommerce-style cases in
   `tests/test_woocommerce_filter.py`; for Shopify/BigCommerce add a sibling test
   file. This is required by `feedback_regression_tests_on_bugfix`.
3. **Run** `python3 -m unittest discover tests/` - must stay green.
4. **Commit + push** (`main`), then on the server:
   ```bash
   ssh dale-server
   cd /opt/dale/repo && git pull --ff-only
   cd /opt/dale/repo/tools && bash deploy.sh
   ```
5. **Write a baseline snapshot per fixed nursery** so tonight's diff does not fire
   false restock alerts (the new products would otherwise look like a mass
   restock):
   ```bash
   cd /opt/dale/scrapers && export DALE_DATA_DIR=/opt/dale/data
   python3 shopify_scraper.py <key>      # or bigcommerce_scraper.py
   ```
   (Scraper alone sends no emails. This overwrites today's snapshot with the
   corrected set, so tonight's nightly run compares like-for-like.)
6. **Rebuild the product pages** (email-safe). Reuse the one-off rebuild approach
   from DEC-207: run the product-listing builders + tailwind + cache purge, and
   SKIP `daily_digest`/`build_history` (or the public /digest.html shows the
   added items as false "new listings"), and SKIP all `send_*`/`detect_stock_surges`
   email steps. The builder list and exact commands are in
   `reference_treestock_rebuild_no_emails` and were used in DEC-207
   (build-dashboard, nursery, species-before-variety, compare, rare_finds,
   location, species_state, then tailwind, then `purge_cloudflare.sh`).
7. **Verify live:** grep the rebuilt `/opt/dale/dashboard/data.js` for a couple of
   the previously-missing product titles; confirm they are present.
8. **Log it:** append to the DEC-207 thread or a new DEC, and update memory
   `project_scraper_leaf_category_gap.md` (mark Shopify/BigCommerce audited).

---

## 6. Definition of done

For each of `garden-world`, `diggers`, `forever-seeds`, `heritage-fruit-trees`:
either
- **confirmed clean**, with the captured-vs-total numbers recorded (e.g.
  "garden-world: 312 of 318 FOOD PLANTS kept, the 6 dropped are pots/tools"), or
- **fixed**, deployed, baseline-scraped, pages rebuilt, verified live, logged.

Record the outcome in the decision log and flip the status line at the top of
this file to "done (YYYY-MM-DD)".

---

## 7. References

- `decisions/decision-log.md` -> DEC-207 (the WooCommerce fix this follows up).
- `tools/scrapers/woocommerce_scraper.py` -> `category_matches()` + the fixed
  Guildford/Engall's/Yalca configs (worked example of the fix shape).
- `tests/test_woocommerce_filter.py` -> regression test pattern to copy.
- `tools/scrapers/shopify_scraper.py` (`scrape_shopify`, NURSERIES) and
  `tools/scrapers/bigcommerce_scraper.py` (`CATEGORIES`, `SKIP_SLUGS`).
- Memory: `project_scraper_leaf_category_gap.md` (audit method + email-safe
  rollout), `reference_treestock_rebuild_no_emails` (builder list),
  `feedback_treestock_deploy`, `feedback_regression_tests_on_bugfix`.
