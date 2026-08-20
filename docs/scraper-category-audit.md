# treestock: scraper and curation architecture audit

## Context

treestock monitors 27 nurseries and holds 15,339 live product records. Benedict expects
to expand past fruit trees soon, into bush tucker, seeds, ornamentals and whatever else
the stock supports. Before that happens we need to know what the current pipeline is
quietly throwing away, where the category decision actually gets made, and what it would
cost to add a category.

The audit was run against live server data on 2026-08-20, not against the local repo
(local `data/nursery-stock/` is stale for most nurseries).

The headline: **the category decision happens last, downstream of four filters that
already assumed the answer was "fruit".** That inversion is the whole problem. A product
cannot be categorised as an ornamental after it has been deleted for not being a fruit.

There is a second finding that changes the order of work. Of the 1,176 unclassified
product titles live right now, **roughly 55% are fruit**, not a new category at all. The
fruit-only site is under-delivering on its own remit before expansion is even considered.

---

## 1. What the numbers say

### The filter stack, measured

```
27 nurseries                                     15,339 products in latest.json
  |
  |-- scraper include-filters (per platform, at scrape time)
  |      product_types / fruit_tags / fruit_handles / CATEGORIES / category slugs
  |      DROPPED HERE IS INVISIBLE: never written to a snapshot, unrecoverable
  v
  |-- classify.is_real_product()  (TRUE_JUNK + derived non-plant + seed regex)
  |                                                  -705
  v
  |-- fruit_filters.is_fruit_product()  (per-nursery, 12 of 27 nurseries configured)
  |                                                  -5,563
  v
  |-- build-dashboard.py's OWN inline cascade (:449-487), applied after the above:
  |      is_fruit_product -> skip_titles -> non_plant_types -> DASHBOARD_JUNK_KEYWORDS
  |      -> a SECOND is_seed_packet call (:478) -> a pot regex
  |      Five more filters that exist nowhere else and are not shared
  v
9,071 products reach the categorize ladder
  |
  |-- rung 1 species registry -> rung 2 nursery_categories.json (3 rules total)
  |   -> rung 3 CATEGORY_KEYWORDS (29 entries) -> unclassified
  v
1,280 unclassified (14.1%), 1,176 unique titles
```

### What the 1,176 unclassified titles actually are

| Bucket | Count | Share | Note |
|---|---:|---:|---|
| Fruit species we already have, parser missed | 150 | 13% | upper bound, see the anomaly below |
| Fruit with no species record | ~500 | 43% | Tayberry, Boysenberry, Achacha, Breadfruit, Kwai Muk, Longan |
| Herb / spice | 268 | 23% | largest genuinely new category |
| Ornamental / native | 134 | 11% | small here, enormous upstream (see Ladybird) |
| Vegetable | 112 | 10% | |
| Non-product | 12 | 1% | "Preorder Request", "Quarantine Inspection Certificate" |

**~55% of the backlog is fruit.** Only ~34% is a category we do not support.

Worst offenders by rate: all-rare-herbs 54%, primal-fruits 44%, st-clements-citrus 25%,
heaven-on-earth 23%, ladybird 20%.

### Registry and switches

- `fruit_species.json`: 110 records. 90 have **no `category` field at all** and rely on
  `DEFAULT_CATEGORY`; 20 are `bush_tucker`; 8 are cross-tagged.
- `taxonomy.ENABLED_CATEGORIES` is `("fruit", "bush_tucker")`. `KNOWN_CATEGORIES` also
  lists `native`, `ornamental`, `vegetable`. **`CLAUDE.md` still documents this as
  `("fruit",)` and has been wrong since June.**
- `nursery_categories.json` holds **3 rules across 27 nurseries**, all pointing at
  `bush_tucker`.
- `stocklib/categorize.py` is only ever called from `build-dashboard.py`.

---

## 2. Worked examples, from live data

### 2a. Ladybird: the nursery already told us the category and we delete it

Ladybird sends 7,200 products with a complete hierarchical store taxonomy. After
`is_real_product` and the `include_tags: ["Fruit Trees & Edibles"]` filter, 1,892 survive.
The 5,308 discarded carry exactly the labels a category expansion needs:

```
3340  Flowering Plants        1006  Indoor Plants          214  Roses
1119  Natives                  981  Feature Trees          195  Cacti & Succulents
1078  Bird & Bee attracting    539  Groundcovers           137  Rare Plants
 530  Hedge & Screening        517  Palms & Tropical       121  Proteas
```

This is thrown away nightly and never recorded. Note the shape of the fix: this is not a
classification problem, it is a **retention** problem.

### 2b. The same filter is dropping 13 real fruit and nut trees today

`FRUIT_FILTERS["ladybird"]["include_tags"]` lists only `Fruit Trees & Edibles`. Ladybird
files nuts under a separate top-level tag, `Nut Trees`, which is not in the list:

```
Walnut 'English'                     Pecan Wichita (B) (PICK UP ONLY)
Pecan Tejas (B) SP                   Advanced Almond Self Pollinating
Pecan Mohawk (B) SP                  Hazelnut Seedling (Corylus avellana)
Pecan Apache (B)                     Corkscrew Hazel Contorta (Corylus avellana)
Pecan Nut PABST (grafted)            Sour Cherry Morello (Prunus cerasus)
Pecan Kiowa (B)                      Kaffir Plum
Pecan Riverside                      Diploglottis australis - Large Leaved Tamarind
```

This is DEC-207's bug class exactly: a narrow include-filter silently dropping in-scope
stock. The June 2026 coverage audit (`docs/scraper-coverage-audit.md`) checked
**scrape-time** include-filters and passed Ladybird as "no filter". It never looked at
`stocklib/fruit_filters.py`, which is a second include-filter at **build** time. Same bug
class, different layer, missed because the audit's scope was defined by file rather than
by function.

### 2c. The case that goes wrong: the 150 "parser misses" is an upper bound

My own measurement over-counts, and the over-count is instructive. Matching a taxonomy
name anywhere in a title flags these as recoverable fruit:

```
Chilli 'Lemon Drop'          -> Lemon        WRONG, it is a chilli
Chilli 'Aji Pineapple'       -> Pineapple    WRONG
Chilli 'Red Hot Cherry'      -> Cherry       WRONG
Berzelia 'Strawberry Jelly'  -> Strawberry   WRONG, a South African shrub
Brunia albiflora 'Lime'      -> Lime         WRONG
Crab Apples Charlottae (Flowering tree) -> Apple   WRONG, ornamental crabapple
```

These are **correctly** unclassified today, but not for the reason you would assume, and
the real reason is a landmine.

The unclassified list comes from the categorize ladder, whose rung 1 is
`stocklib/species_match.py`, **not** `cultivar_parsing.py`. The DEC-195 guards
(`_NON_FRUIT_FORM_WORDS`, `_ornamental_conflict`) are not what rejects these: those guard
`/variety/`, a different consumer. Measured against the live registry:

```
Chilli Lemon Drop        -> Lemon      species_match MATCHES it
Chilli 'Lemon Drop'      -> None       the same title, quoted, does not
```

`match_species` matches a species mid-title or trailing quite happily. The only thing
stopping us filing every Ladybird chilli as a lemon cultivar is **the quote characters**,
and only in the fallback (non-leading) position:

```
Blueberry 'Biloxi'   -> Blueberry, cv Biloxi   quoted LEADING already works
Biloxi 'Blueberry'   -> None                   quoted FALLBACK does not
```

So the protection is incidental, not principled. Anyone who later extends quote handling to
the fallback path will mis-file the entire chilli range in the same commit, silently.

**And one of these is already broken.** The ornamental crabapple escapes only on its
plural:

```
Crab Apples Charlottae (Flowering tree)  -> None    escapes, by luck
Crab Apple Charlottae (Flowering tree)   -> Apple   ALREADY MIS-FILED today
```

`crab apple` is not a lookup key and there is no ornamental guard on this path, so any
singular crabapple title is counted as an Apple right now. That is a live defect, and it
is directly in the way of 1.6.

The genuine misses, by contrast, are narrow and safe. Measured:

```
Biloxi Blueberry     -> Blueberry    matches
Biloxi Blueberries   -> None         fails on the PLURAL alone
Finger Lime <cv>     -> Finger Lime  matches in any position
Fingerlime           -> None         "fingerlime" is not a lookup key
Coffee Arabica       -> Coffee       matches; "Coffee, Arabica" is the comma form
```

So the recoverable figure is below 150, the fix is per-form rather than positional, and
Phase 1.6 must not loosen matching to get there.

### 2d. Seeds are not a missing category, they are an actively deleted one

`classify.is_seed_packet` is `\bseeds?\b`, minus `seedling` and `seedless`. It feeds
`is_real_product`, which every builder calls. So seeds are destroyed, not categorised.
And the regex is blunt enough to eat real trees:

```
Lychee Lin San Sue (Small Seed)   dropped.  Small-seed is a prized lychee trait
Seed Grown Mango                  dropped.  A mango tree
Seed of Heaven                    dropped.  A plant name
```

`forever-seeds` is a whole nursery, 82 products, of which 40 survive `is_real_product`.

### 2e. Junk keywords match as substrings, with the predictable result

`is_junk_keyword` does a substring test. Live casualties right now:

```
Grevillea 'Ellabella' - Large            dropped, "ellabella" contains "label"
Grevillea 'Sea Spray'                    dropped, contains "spray"
Wire Vine (Muehlenbeckia complexa)       dropped, contains "wire"
Blood Orange Fruit Tree Cara Cara (Already Fruiting) QLD POSTAGE ONLY
                                         dropped, contains "postage". A real orange tree.
```

The precedent is in memory: bare `tool` was removed once because it ate Toolangi
strawberry. The same fix was never generalised.

### 2f. Daleys changed data source today and tripled

```
2026-08-17.json   665 products   source=plant_list   (HTML scraper)
2026-08-18.json   660 products   source=plant_list
2026-08-19.json   647 products   source=plant_list
2026-08-20.json  1998 products   source=feed         (CSV supplier feed)
```

Two health records exist for daleys on 08-20: 646 products at 00:04:42 and 1,998 at
03:19:16. The nightly wrote one snapshot and an out-of-band run replaced it in place three
hours later. Nothing alarms on a 209% single-night jump, the snapshot envelope carries no
`source` field at the top level (only per-product), and the day's digest and alerts had
already gone out against the old 647. The mass-restock alert was dodged by timing rather
than by design.

This also explains three of the five misfiled variety pages found on 2026-08-19: they were
minted by the new feed the same day.

### 2g. What is already good, and should not be rewritten

The fault-tolerance layer works. garden-express has been failing since 08-18 (`HTTP 400`
on the old WooCommerce endpoint after the store migrated to Shopify) and the system
behaved correctly on all three nights:

```
08-18  garden-express: failed + zero_products      -> anomaly alert sent
08-19  garden-express: failed                      -> anomaly alert sent
08-20  garden-express: failure_streak, 3 days      -> anomaly alert sent
       Untrusted nurseries tonight: garden-express -> page ledger froze its pages
```

The fix is committed (`124ab16`) and deployed, and will run at the next 00:00 UTC.
Do not treat this as a hole. `detect_scrape_anomalies.py`, `stocklib/scrape_health.py`,
the 3-of-6 failure floor and the ledger's health gate are all doing their job.

Equally sound and out of scope for change: `stocklib/page_ledger.py` (guards are measured,
not guessed), `stocklib/model.py` validation at the write boundary, the anti-truncation
guards in each scraper, and the CSRF/JWT model on `/admin`.

---

## 3. The plan

Benedict's calls, taken as given:
1. **Fruit first, then machinery.**
2. **Pick the next category by search demand, before building for it.**
3. The first category is whatever that research names.

Phase 2 is research and depends on nothing in Phase 1, so **run it in parallel**. It does
not delay the code work.

---

### Phase 1: recover the fruit already in scope

Target: the ~650 fruit products currently invisible. Each step is a bugfix with a
failing-then-passing test, per `feedback_regression_tests_on_bugfix`.

**1.1 Fix the Ladybird include-filter.** Add `Nut Trees` to
`FRUIT_FILTERS["ladybird"]["include_tags"]` in `tools/scrapers/stocklib/fruit_filters.py`.
Recovers the 13 trees in 2b. Test home is the existing
`tests/test_fruit_filters.py`, not `test_woocommerce_filter.py`.

Note the counter-case while doing this: Ladybird files `Sour Cherry Morello` under
`Nut Trees`. Store taxonomy is a strong signal, not an authoritative one, which is the
argument for keeping the ladder's rung ordering rather than trusting `category_raw`
outright.

**1.2 Audit every `FRUIT_FILTERS` entry the same way.** 2b is one instance of a class. For
each of the 12 configured nurseries, diff the store's own top-level category vocabulary
against the include list, exactly as `docs/scraper-coverage-audit.md` section 4 does, but
at build time rather than scrape time. The 15 unconfigured nurseries default to open and
are not at risk of dropping fruit.

**1.2 findings, measured 2026-08-20.** Only **three** of the twelve configured
entries are restrictive at all: `ladybird` (tags), `daleys` (categories) and
`forever-seeds` (title_include). The other nine are `mode: "all"` and cannot drop
anything, and the 15 unconfigured nurseries default open. So the audit surface was three
nurseries, not twelve.

`daleys`, 1,998 live products, 785 dropped:

```
X  602  ''                            no category at all  -> see below, this is 1.5
X   76  'Ornamental Native & Exotic'  correctly out of scope
X   45  'Gardening Accessories'       correctly junk
X   36  'Rainforest Trees'            deliberately left out, see the Fig landmine
X   20  'Farm and Forestry Trees'     correctly out of scope
X    5  'Specials'                    FIXED, a real fruit tree was hiding here
X    1  'Trees and Plants/.../Palm Trees'
```

- **`Specials` is a merchandising bucket, not a taxonomy one, and it replaces the
  product's real category rather than adding to it.** A fruit tree put on special
  therefore dropped off treestock entirely, which is backwards: a discounted rare fruit
  tree is the most interesting event we have, and it is what feeds the price-drop alerts.
  Live it held `Papaya - Broad Leaf` (resolves to Papaya) alongside a gift voucher, an
  End Stop Terminator and a River Red Gum. The junk gate already drops all three, so the
  bucket is safe to include and leans on the gate downstream by design. Fixed.

- **`Rainforest Trees` is deliberately NOT included, and the reason is 1.6a's bug class
  wearing a different hat.** The bucket looks in scope: Blue Quandong, Candle Nut, Native
  Ginger, Brown Tamarind. It also holds `Fig - Small Leaved` and `Fig - White`, which are
  rainforest shade figs (*Ficus obliqua*, *Ficus virens*), and `match_title` resolves both
  to **Fig**. Including the bucket mints them as edible-fig cultivars on `/variety/fig`.
  Revisit only behind an ornamental guard on the `species_match` path.

- **The 602 empty-category rows are a registry gap, not a filter gap, and this reorders
  the value of 1.5.** The CSV feed carries no category column, so
  `csv_feed_scraper.CategoryResolver` falls back to the frozen url map the HTML scraper
  left behind, then to our own species taxonomy, then gives up. 514 of the 602 survive
  `is_real_product`, and among them are `Achacha`, `Ambarella`, `Amla`, `Bael`,
  `African Breadfruit` and `Alupag`, all of which `match_title` returns `None` for. So
  **1.5 is a retention lever for daleys, not only a classification one**: each registry
  record added makes the resolver return `Fruit and Nut Trees` and the product appears.
  Admitting `""` here instead would let in Agapanthus, Aspen, African daisy and nine gift
  vouchers.

`forever-seeds`, 82 live products, 36 pass. Everything it drops that is also a real
product is a herb (spearmint, oregano, patchouli, Mexican sawtooth coriander). Out of
scope for a fruit site and Phase 2's question, not Phase 1's. Note the inconsistency
recorded rather than fixed: `daleys` includes `Herbs, Spices & Perennial Vegetables`
while `forever-seeds` excludes herbs. Phase 2 should settle which is right.

**1.3 Make junk matching word-aware, in both places that do it.** Token boundaries rather
than substrings. Keep the multi-word entries (`gift card`, `potting mix`) as phrase
matches. Two call sites, and fixing one is not enough:

1. `stocklib/classify.py:is_junk_keyword`, whose docstring already says "(substring
   match)", so the behaviour is intended and simply wrong. This covers the variety,
   species and compare surfaces.
2. **`build-dashboard.py:474` never calls `is_real_product` at all.** It inlines its own
   `any(kw in title_lower for kw in DASHBOARD_JUNK_KEYWORDS)`, and
   `DASHBOARD_JUNK_KEYWORDS` is built from `TRUE_JUNK`, which contains all four of
   `label`, `postage`, `spray`, `wire`. So the homepage keeps dropping the 2e casualties
   until this line uses the shared helper too.

Extract one word-aware predicate in `classify.py` and have both sites call it. Pin the
2e casualties in `tests/test_classify.py`, and pin at least one of them through the
dashboard path so site 2 cannot regress independently.

**1.4 Stop deleting seeds; mark them instead.** Two call sites, not one:

1. `classify.is_real_product` (`stocklib/classify.py:135`) bundles the seed test. Split it
   out so `is_seed_packet` stays a classifier and the product is retained and annotated.
2. **`build-dashboard.py:478` calls `is_seed_packet` a second time, independently**, after
   the fruit filter. Fixing only (1) leaves seeds still dropped on the homepage.

Tighten `_SEED_RE` so `(Small Seed)` and `Seed Grown` do not match.

**Widening risk, and it points the opposite way to the rest of Phase 1.** Retaining seeds
globally would push seed rows into every surface that trusts the shared gate, which is a
scope change nobody asked for. **Thirteen modules call `is_real_product`:**

```
build_variety_pages.py     build_species_pages.py      build_compare_pages.py
build_location_pages.py    build_species_state_pages.py  build_species_trends.py
build_nursery_pages.py     build_bare_root_page.py     daily_digest.py
send_variety_alerts.py     send_species_alerts.py      csv_feed_scraper.py
recover_merged_slugs.py
```

The seed flag must therefore be *carried* on the product and *honoured* by each consumer,
not simply removed from the shared gate. Do this step after 1.1 to 1.3, not before, and
pin each surface with a test asserting seeds stay out of it.

Two notes that shrink the work: `send_species_alerts.py` has been unwired from the
pipeline since 2026-04-19, and `recover_merged_slugs.py` is an offline proposal generator.
Both still need the decision, neither is on the nightly path.

**1.5 Grow the species registry.** ~500 titles are fruit with no record. This is DAL-192's
scope, which is no longer in the backlog. Batch by count: berries first (Tayberry,
Boysenberry, Youngberry, Loganberry, Lawtonberry all appear), then rare tropicals
(Achacha, Grumichama, Kwai Muk, Garcinia, Bignay, Nam Nam, Lau Lau, Breadfruit).

Adding a record improves the parser as a side effect (memory:
`project_variety_taxonomy_gate`, Persimmon went 14 to 45 varieties just by existing), so
**check active watches before and after each batch** and run
`check_watched_slugs.py --baseline 2`.

**1.6 Fix the formatting misses in `species_match`, per form, never positionally.** The
target is `stocklib/species_match.py`, not `cultivar_parsing.py` (see 2c).

Do **not** loosen positional or quote matching to raise the hit rate. The chilli range is
rejected only by the quote characters in fallback position, so extending quote handling
there files Ladybird's chillies as lemon, cherry and pineapple cultivars.

**Order matters here, because the obvious fix makes an existing bug worse.**

1. **Fix the crabapple first.** `Crab Apple Charlottae (Flowering tree)` already resolves
   to Apple (2c). Add `crab apple` / `crabapple` as an explicit non-fruit exclusion on
   this path before touching anything else, and pin it.
2. **Then one-word compounds** (`fingerlime`). Narrow and safe: an explicit extra lookup
   key per affected registry name.
3. **Then plurals, as explicit keys and NOT a stemmer.** A blanket plural stemmer would
   make `Crab Apples Charlottae` match Apple too, which is the exact case that currently
   escapes by luck. Derive plural keys from registry common names and synonyms, so the
   vocabulary stays a closed set someone can read.

Pin **both directions** in `tests/test_categorize.py` or a `species_match` test:
`Biloxi Blueberries` must resolve; `Chilli 'Lemon Drop'`, `Chilli 'Red Hot Cherry'`,
`Berzelia 'Strawberry Jelly'` and **both** crabapple forms must return None. The second
half is the half that matters, because most of it currently passes by accident.

**1.7 Give the snapshot envelope a `source` field** and alarm on a source change or a
single-night product-count swing beyond a threshold. 2f went unremarked; the next one
should not. Correcting the target:

- `stocklib/model.py` is **pure validation and writes nothing** (`validate_snapshot`
  returns a list of problems). It can require the field, not emit it.
- Each scraper writes its own envelope, so the field goes in all six:
  `shopify_scraper.py`, `woocommerce_scraper.py`, `bigcommerce_scraper.py`,
  `ecwid_scraper.py`, `wix_scraper.py`.
- **`csv_feed_scraper.py:282` already writes a top-level `"source": "feed"`.** It is the
  reference implementation; the other five copy it.
- `detect_scrape_anomalies.py` does not mention `source` at all today. The source-change
  check is new code there.

---

### Phase 2: pick the category on evidence (runs in parallel)

Bush tucker is the calibration, and it is the reason this phase exists. It shipped in June
with 388 products across 15 nurseries, indexed fine (impressions grew 95 to 140 to 311 per
fortnight), and still produced **~1 organic click per fortnight against a 30/week
threshold**. Coverage was never the constraint. Demand was.

Produce a written go/no-go per candidate, same shape as DAL-202:

1. **Mine GSC for non-fruit intent we already receive.** 12 months of queries via
   `gsc_analysis.py`, bucketed against category vocabulary. We rank for a lot; the question
   is what people ask for that we do not serve.
2. **Size the stock per candidate**, which is largely done: herbs 268, ornamentals 134
   in the unclassified set but 5,308 at Ladybird alone once retention is fixed,
   vegetables 112, seeds a whole nursery plus scattered lines.
3. **Check the competition.** Track B's moat is that nobody aggregates Australian rare
   fruit stock. That is emphatically not true of ornamentals or seeds. Verify per
   candidate before assuming the moat transfers.
4. **Apply the bush tucker floor.** Any candidate must plausibly beat ~1 click/fortnight
   at comparable coverage, or it repeats DEC-227.

Deliverable: one decision doc naming the winner and the criteria it met, logged as a DEC.

---

### Phase 3: make a category cheap to add

Built for the winner, but generically. Target: a new category is a config plus data
change, not an engineering project.

**3.1 Retain what we currently discard, in a sibling file.** The single highest-value
change, and the one most easily done wrong.

This is not a new idea. It is already the newest scraper's stated design, in
`csv_feed_scraper.py:245`:

> Deliberately no is_real_product / category filtering here. Every gate is a render-time
> decision (...) because the feed is a live view with no history: a row we decline to
> record today cannot be recovered later.

Phase 3.1 generalises that to the other six scrapers.

**Retention is NOT isolated from rendering, and the naive version sends email.** Four jobs
read the raw product list or the envelope counts with no scope filter:

| Consumer | What raw retention would do |
|---|---|
| `availability_tracker.py:66` | 5,308 ornamentals enter Ladybird's availability history |
| `build_nursery_compare.py:59` | public nursery product counts jump |
| `build_location_pages.py:196` | public location counts jump |
| **`detect_stock_surges.py:40`** | **reads `product_count` from the envelope and emails Benedict on a swing. Every nursery would surge at once** |

**Decision (Benedict, this review): write discarded products to a sibling file**, e.g.
`data/nursery-stock/<key>/out-of-scope.json`, next to `latest.json`. `latest.json` keeps
exactly the products it has today, so all four consumers are untouched, no public count
moves, and the surge detector never sees the change. Nothing reads the new file until
Phase 3 needs it.

The accepted cost is two files per nursery and an eventual convergence onto one list with
a scope field. That convergence is a later decision, taken when a category actually
launches and the consumers have to be scope-aware anyway.

Carry the store's own taxonomy into the sibling file verbatim (`tags`, `product_type`,
`category_raw`). That is the raw material for rung 2 of the ladder in 3.5, and it is the
part that cannot be reconstructed later.

**Retention can only keep what was fetched, and three nurseries never fetch it.** The
sibling file solves the downstream problem, not the upstream one. `woocommerce_scraper.py`
has a `category_api` mode (`_scrape_by_category`, `:263`) that iterates **only the
configured `fruit_categories`**, so out-of-scope products are never in memory to write.
It is on for `all-rare-herbs`, `diacos` and `plantnet`.

Those three need a fetch-path change, and it is not simply "turn the filter off":
`all-rare-herbs` uses `category_api` because it is **required**, not as an optimisation.
Plain pagination hides roughly 55 of its 98 products (comment at `woocommerce_scraper.py:140`).
Retaining there means enumerating **all** category slugs from the store, not just the
fruit ones. Treat it as its own task, and do not let it block the other 24 nurseries.

**3.2 Turn scope from a boolean into a category.** `is_fruit_product` answers yes/no and
its name encodes the assumption. It becomes a function returning a category or set of
categories per nursery rule. Rename `FRUIT_FILTERS` to match.

The full migration surface, which is wider than "the callers":

| Site | What it does |
|---|---|
| `build-dashboard.py:96,450` | imports `FRUIT_FILTERS` + `is_fruit_product` directly |
| `daily_digest.py:30` | imports all three |
| `build_nursery_pages.py:18,245` | `digest_product_filter` |
| `send_variety_alerts.py:353` | `digest_product_filter` |
| **`send_variety_alerts.py:149`** | **a second path in the same file using only `is_real_product`.** Two scope rules, one module. Reconcile it or category scope stays inconsistent in the alert inputs |
| `stocklib/changes.py:60` | takes `product_filter` as a parameter; the conduit both the digest and alerts run through |
| `csv_feed_scraper.py` + `daleys_category_map.json` | a frozen 1,998-entry url to category map exists **solely** so Daleys still passes `is_fruit_product` after the feed switch, because the feed has no category column. Changing the contract has to keep this working, or every Daleys product "silently fails is_fruit_product and vanishes from the site with no alarm" (its own comment) |

**3.3 Separate "junk" from "out of scope".** `NON_PLANT_KEYWORDS` currently contains
`acacia`, `banksia`, `eucalyptus`, `melaleuca`, `wattle`, `callistemon`, `lomandra`,
`sheoak`, `kurrajong`, `cordyline`. Those are plants, in a category we have not enabled.
The derivation via `derived_non_plant_keywords(ENABLED_CATEGORIES)` is already correct in
shape and will drop them automatically when a category is enabled. The **name** is the
liability, and the vocabulary is thin: 26 native, 2 ornamental, 1 vegetable, against a
backlog naming protea, leucadendron, dogwood, maple, jacaranda, ginkgo and more.

**3.4 Make `category` explicit in the registry.** 90 of 110 records have no `category`
field and lean on `DEFAULT_CATEGORY`. An implicit default is fine with one category and a
trap with five. Backfill it, then make the schema test require it.

**3.5 Fill in rung 2 of the ladder.** `nursery_categories.json` has 3 rules for 27
nurseries. Ladybird's tags and Daleys' `product_type` values are ready-made and would
carry most of the load. Note that `FRUIT_FILTERS["daleys"]` already admits
`"Herbs, Spices & Perennial Vegetables"` and `"Bush Food Plants"` through a filter called
fruit, so herbs are half in the system already and currently land as unclassified.

**3.6 Reuse the existing surface pattern, and close the gap between it and "config only".**
The landing page really is one `LANDING_PAGES` entry plus one `NAV_ITEMS` line plus
enabling the category. **But "a new category is config plus data" is not true today**, and
Phase 3 is not done until it is. What a new category also needs right now:

- `stocklib/category_ui.py:13` `CATEGORY_BADGES` is a hardcoded two-entry dict, and
  `category_keys` ends `[c for c in cats if c in CATEGORY_BADGES]`. A species in a
  category with no badge entry gets **zero** badges and silently drops out of every
  badge and filter surface. Its own docstring already tells you to add a line.
- `CATEGORY_FILTER_CSS` needs a colour pair per category.
- `build-dashboard.py:834` hardcodes the homepage `<select>` options as Fruit and
  Bush Tucker.
- `daily_digest.py:39+` carries the per-subscriber `plant_categories` logic.

Make these derive from `ENABLED_CATEGORIES` plus a per-category presentation record, so
the switch really is one place. The species index filter and the `plant_categories`
opt-in do generalise as built; the badge and select vocabularies do not.

**Keep out of Phase 3:** the DEC-195 `/variety/` taxonomy gate stays fruit-scoped. Variety
pages and restock alerts are the product's sharp end and the gate is what keeps 548
ornamental species groups out of them. A new category earns a landing page and species
pages first; variety pages are a separate decision.

---

### Phase 4: admin and curation tooling

Smaller, and independent of the above.

**4.1 `deny` has no button.** `apply_decisions` accepts it, `queue_curation` stores it,
`_pending_section` renders it, `promote_curation.merge` commits it, and nothing on
`/admin/varieties/review` can produce one. The deny half of curation is reachable only by
hand-editing `variety_overrides.json` in git. `undistinct` is in the same position.
Given the session on 2026-08-19 turned on exactly this file, this is the gap most likely
to be hit next.

**4.2 `promote_curation` can strand a queue row permanently.** `clear_queue` removes only
`applied | satisfied`. A row skipped for a chain, a missing target or an unknown kind stays
in `curation_pending` forever, rendering as "Queued for tonight" with no run able to clear
it except the manual unqueue button.

**4.3 Optimistic concurrency is redirect-only.** `row_stamp` hashes `state|redirect_to`.
Alias, deny and sibling decisions have no staleness check.

**4.4 `NOISE_SLUG_TOKENS` is an unenforced mirror.** `admin_view.py` keeps a literal copy
of the parser's noise vocabulary, deliberately, to stay off `deploy.sh`'s restart
fingerprint. The reason is sound and documented at `admin_view.py:66`. Nothing tests that
the copy still matches `cultivar_parsing._NOISE_RES`. Add that test.

**4.5 `migrate_variety_watch_slugs.py` has zero tests and must never run.** Its protection
is three prose warnings, one of which `promote_curation.render` nearly deleted. Either add
a test that asserts it refuses to run, or delete the script.

**4.6 Housekeeping.** `daleys_scraper.py` (605 lines) and `run-all-scrapers-server.sh` are
dead and still reference each other. `bigcommerce_scraper.py:32` computes `DATA_DIR` one
level shallower than every other scraper. `woocommerce_scraper.py` and
`bigcommerce_scraper.py` do not use `stocklib.retry` despite being the two most 503-prone.
`CLAUDE.md` documents `ENABLED_CATEGORIES` wrongly.

---

## 4. Critical files

| File | Role in this plan |
|---|---|
| `tools/scrapers/stocklib/fruit_filters.py` | 1.1, 1.2, 3.2. The build-time scope gate. 12 of 27 nurseries |
| `tools/scrapers/stocklib/classify.py` | 1.3, 1.4, 3.3. Junk, seeds, and the category keyword hint |
| `tools/scrapers/stocklib/taxonomy.py` | 3.4. `ENABLED_CATEGORIES`, `KNOWN_CATEGORIES`, `DEFAULT_CATEGORY` |
| `tools/scrapers/fruit_species.json` | 1.5, 3.4. 110 records |
| `tools/scrapers/stocklib/categorize.py` | 3.5. The ladder. Sound as designed, starved of rules |
| `tools/scrapers/nursery_categories.json` | 3.5. 3 rules today |
| `tools/scrapers/stocklib/species_match.py` | **1.6.** Rung 1 of the ladder, and the real target for the formatting misses |
| `tools/scrapers/cultivar_parsing.py` | Reference only. The DEC-195 gate. Do not widen it, and note it is NOT what rejects the chilli titles |
| `tools/scrapers/stocklib/model.py` | 1.7. Validation only, writes nothing. Can require `source`, cannot emit it |
| the six scrapers | 1.7, 3.1. Each writes its own envelope. `csv_feed_scraper.py` is the reference for both `source` and retention |
| `tools/scrapers/detect_scrape_anomalies.py` | 1.7. The source-change alarm is new code here |
| `tools/scrapers/stocklib/category_ui.py` | 3.6. `CATEGORY_BADGES` is hardcoded and silently drops unknown categories |
| `tools/scrapers/build-dashboard.py` | 3.2, 3.6. Only caller of the ladder; five inline filters at :449-487; hardcoded category select at :834 |
| `availability_tracker.py`, `build_nursery_compare.py`, `build_location_pages.py`, `detect_stock_surges.py` | 3.1. Read raw products or envelope counts. The sibling-file design exists to avoid touching them |
| `tools/scrapers/admin_view.py` | 4.1, 4.3, 4.4 |
| `tools/scrapers/promote_curation.py` | 4.2 |
| `tools/scrapers/shopify_scraper.py` etc. | 3.1. Retention of out-of-scope products |

Reuse rather than rebuild: `stocklib/categorize.py` (the ladder), `stocklib/category_ui.py`
(badges and filter CSS), `stocklib/species_match.py` (title to species), `LANDING_PAGES` +
`filter_to_category` in `build-dashboard.py`, `stocklib/scrape_health.py`,
`stocklib/page_ledger.py`.

---

## 5. Verification

**Per change:** `.venv/bin/python -m unittest discover tests/` from the repo root, green
before commit. Bare `python3` fails on missing `requests`. Scraper changes are covered by
`tests/test_no_forking.py`, `tests/test_parsing.py`, `tests/test_golden.py`
(`GOLDEN_UPDATE=1` to regenerate).

**Phase 1 recovery, measured not assumed.** Re-run the audit probe before and after and
diff the counts:
- total products, per nursery
- `is_real_product` survivors
- `is_fruit_product` survivors
- unclassified count and rate from `data/needs-review.json`

Expect the unclassified count to fall and the kept count to rise. If kept rises and
unclassified rises with it, a filter was widened without the registry catching up.

**Watch safety, on any parser or registry change:** confirm zero watchers on affected slugs
via `/admin/varieties`, then `check_watched_slugs.py --baseline 2` after the next build.
The unresolved count must not grow. Never run `migrate_variety_watch_slugs.py`.

**Email safety.** Never run `run-all-scrapers.sh` ad hoc: it scrapes and emails
subscribers. Run individual scrapers to write a baseline snapshot before any coverage
widening, or the next nightly diff reads the recovered products as a mass restock and
alerts on it. Rebuild pages with the email-safe builder list in
`reference_treestock_rebuild_no_emails`, skipping `daily_digest`, `build_history` and every
`send_*`.

**Two specific email hazards in this plan.** Both send to Benedict, not to subscribers, but
both are noise that trains the alarm to be ignored:

- **1.1 and 1.2 widen coverage**, so the recovered products look like a restock. Write a
  baseline snapshot per fixed nursery before the next nightly.
- **`detect_stock_surges.py` reads `product_count` straight off the envelope** and fires at
  ±20% or 10+ items. The Daleys source switch in 2f was a 209% jump. Any step that changes
  what a snapshot contains must either be baselined first or be verified not to move
  `product_count`. Choosing the sibling-file design in 3.1 is what keeps this safe there.

**Ledger safety.** Ledger guards count builder runs, not calendar days
(`ENTRY_GUARD_LIVE_DAYS = 7`, `ENTRY_GUARD_SPAN_DAYS = 7`, `EXIT_GUARD_NIGHTS = 2`). An
ad-hoc build advances every page's counters. Do not force rebuilds to "check" a change.

**Deploy.** Commit, push, then `cd /opt/dale/repo && git pull --ff-only` and
`bash /opt/dale/repo/tools/deploy.sh`. Never scp. Check no autonomous session is running
before pushing to main.

---

## 6. Explicitly out of scope

- beestock, in any form. Hard-blocked in `state/ticket-blocklist.json`.
- walkthrough.au. Paused since 2026-04-27.
- Widening the DEC-195 `/variety/` gate beyond fruit.
- New bush tucker investment. DEC-227 stands; the pages stay live at zero marginal cost.
- Re-running the June scrape-time coverage audit. It was completed and its findings hold.
  Phase 1.2 is the build-time counterpart it never covered.
