# treestock category expansion: design doc

**Status:** Approved direction (DEC-200, 2026-06-11). Pilot category: bush tucker.
**Owner:** Dale (implementation), Benedict (promotion of tickets, copy review, go/no-go calls).
**Scope ceiling:** every plant category Australian nurseries sell. Non-plant supplies (pots, tools, fertiliser, gift cards) stay junk-filtered forever.

## 1. Goal

Expand treestock.com.au beyond rare fruit in stages: bush tucker first, natives next, eventually all plant categories. Three priorities, in order:

1. **Categorisation correctness at scale.** A new nursery's stock lands in the right category automatically or in a visible needs-review state. A rose must never appear under fruit trees.
2. **Site hierarchy that keeps the rare-fruit identity.** Fruit stays the default experience. The rare fruit community must never feel the site became a generic garden-centre aggregator.
3. **Scraper observability.** Per-nursery health (success, failures, zero-product anomalies, 403/429 blocks) recorded, surfaced in /admin, and alerting Benedict when something flatlines.

## 2. What the evidence changed (read this before assuming)

Two assumptions from earlier planning turned out wrong when checked against the code and data (2026-06-11):

1. **Scrape volume is mostly a non-issue.** Shopify, WooCommerce (non category-api) and Ecwid scrapers fetch entire stores and filter post-fetch; several nurseries (Ross Creek, Ladybird, Fruitopia, and more) have no filter at all. The bush tucker and natives products are largely already in our daily snapshots. Only Heritage (BigCommerce, category slugs in URLs) and the Woo category-api nurseries (Garden Express, Plantnet, Diacos) scope requests, and widening those adds a handful of category page fetches. The third workstream is therefore observability, not scaling.
2. **Flipping `ENABLED_CATEGORIES` does nothing by itself.** Roughly 15 builders read `fruit_species.json` directly; only `build-dashboard.py` uses `stocklib.taxonomy`, and `enabled_species()` has no production callers. The real work is a behaviour-preserving migration of every consumer onto the taxonomy module, then the one-line enable.

**Supply evidence** (local snapshots, some stale; re-census on the server before authoring records, see P2.1):

- **Bush tucker:** roughly 120 to 280 products across up to 9 nurseries (Ladybird, Daleys, Guildford, Ross Creek, Fruitopia lead). All pass today's junk filter; they sit in the dashboard as unmatched products. 8 species are already in the registry as fruit: Finger Lime, Lilly Pilly, Davidson's Plum, Kakadu Plum, Muntries, Midyim Berry, Desert Lime, Macadamia.
- **Natives:** roughly 750 products (Ladybird is the anchor, Daleys second). 311 are currently discarded by deliberate plant keywords in the junk filter (banksia, callistemon, melaleuca, eucalyptus, wattle, acacia, lomandra). About 186 grevilleas and 100+ other natives (kangaroo paw, westringia, leptospermum) already sit in the dashboard unmatched, because those genera were never in the junk list.
- **`category_raw`:** every snapshot product stores the source store's own category string (Daleys "Bush Food Plants", Guildford "Australian Native Food Plants", Ross Creek "Australian Native"). Nothing consumes it today. It is the cheap, high-precision classification signal.

## 3. Design

### 3.1 Taxonomy model

Species records in `tools/scrapers/fruit_species.json` gain:

- `category` (single, primary): drives which surfaces a species belongs to. Runtime default "fruit" already exists in `stocklib/taxonomy.py`.
- `tags` (list, optional): cross-listing without moving a species. The 8 bush-tucker-adjacent fruits keep `category: "fruit"` (zero change to their URLs, pages, watches) and gain `tags: ["bush_tucker"]`. New non-fruit species (lemon myrtle, saltbush, warrigal greens) get `category: "bush_tucker"`.

New taxonomy helpers: `KNOWN_CATEGORIES` frozenset ("fruit", "bush_tucker", "native", "ornamental", "vegetable"; the last three exist only as classification hints until enabled), and `landing_species(category)` returning records where the category matches OR the tag is present (what landing pages render). `ENABLED_CATEGORIES` remains the single switch.

Flat species + category scales to natives (a genus-level record like Grevillea is just a coarser species record). No beestock-style second taxonomy level is needed; beestock stays a design reference only.

### 3.2 Classification ladder (build time, snapshots stay raw facts)

Per product, first hit wins:

1. **Species-registry match** (existing `match_species` flow): category comes from the matched record. Highest confidence, gives species-page linkage.
2. **Per-nursery `category_raw` mapping** from a new committed config `tools/scrapers/nursery_categories.json`. Matchers applied exact, then prefix, then contains, against the verbatim `category_raw` string. Seed entries: Daleys exact "Bush Food Plants" -> bush_tucker; Guildford contains "Australian Native Food Plants" -> bush_tucker (Guildford strings are comma-joined and HTML-escaped, e.g. "Berries &amp; Vines", hence contains); Ross Creek exact "Australian Native" -> bush_tucker.
3. **`CATEGORY_KEYWORDS` hint** (see 3.3). Lowest confidence.
4. **Unclassified:** stays in dashboard search exactly as today, excluded from category surfaces, counted per nursery. Counts surface in /admin as the needs-review queue. The correction loop is: add a species record or a mapping line, and the next nightly build reclassifies. No human hand-tunes keywords per nursery.

Implementation: new `stocklib/categorize.py` (ladder + per-nursery unclassified counters), wired into `build-dashboard.py` behind a `--needs-review-out PATH` flag so golden tests never see it. The ladder consults ALL records (`load_species`), not just enabled ones: "category known but disabled" is useful needs-review information; surfaces filter by enabled-ness separately.

### 3.3 Junk-filter split (the NON_PLANT_KEYWORDS migration)

`stocklib/classify.py` currently mixes true junk with deliberately-filtered real plants. It splits into:

- `TRUE_JUNK` (about 73 keywords: fertiliser, gift cards, tools, books, chemicals, freight). Junk forever, all categories.
- `CATEGORY_KEYWORDS` dict, keyword -> category hint: banksia/callistemon/eucalyptus/melaleuca/wattle/acacia/lomandra/sheoak/kurrajong/etc -> "native"; ornamental/cordyline -> "ornamental"; asparagus -> "vegetable".

`NON_PLANT_KEYWORDS` becomes **derived**: `TRUE_JUNK` union the keywords of categories NOT in `ENABLED_CATEGORIES`. Enabling a category automatically stops junking its plants and routes them to classification instead. The public API (`NON_PLANT_KEYWORDS`, `is_junk_keyword`, `is_real_product`) is unchanged and the derived set is set-equal today, so behaviour and goldens hold. `tests/test_no_forking.py` gains guards for `TRUE_JUNK` and `CATEGORY_KEYWORDS`. Import direction is classify -> taxonomy (taxonomy imports stdlib only, no cycle).

Note: no bush tucker keywords exist in the junk list, so the pilot enable un-junks nothing. This machinery pays off at the natives enable (311 products return automatically).

### 3.4 Variety gate (DEC-195) and the myrtle conflict

`cultivar_parsing.py` reads the species file at three points (`_load_species_lookup`, `_canonical_species`, `_latin_noise_words`). All three route through a new `_species_records()` seam returning `taxonomy.enabled_species()`, so disabled records cannot perturb parsing.

The conflict: `_ORNAMENTAL_WORDS` contains "myrtle", and `_ornamental_title()` runs before canonicalisation, so "Lemon Myrtle 'Mini'" would be rejected even with a registered Lemon Myrtle record. Fix: move the ornamental check after canonicalisation and make it **vocabulary-scoped**: an ornamental word in the title rejects the parse UNLESS that word belongs to the matched, enabled record's own common_name/synonyms. Verified behaviour-preserving today (no current record's vocabulary contains an ornamental word), and it preserves the pinned "Hibiscus Petite Orange" leak-guard ("hibiscus" is not in the Orange record's vocabulary). Latin names deliberately do NOT contribute to the cover vocabulary.

Authoring rule (enforced by a schema test): no record may use a bare ornamental or form word as a name or synonym ("Myrtle" alone would unlock crepe myrtles). Bush tucker species pass the gate automatically once registered and enabled; whether ornamentals ever get variety pages is decided at the natives phase (default no). The grandfathered `cinnamon-myrtle-mini` slug retires at enable time (it becomes organically in scope).

Related: DAL-192 (long-tail exotics dropped by the gate) benefits from the same seam; same registry-record pattern, different species list.

### 3.5 Information architecture (Benedict-approved 2026-06-11)

- **Homepage: untouched.** Fruit search results above the fold, nothing added above results, ever.
- New `/bush-tucker/` landing page: its own search + results, same layout components, built from `landing_species("bush_tucker")` plus the categorizer. Linked from the existing header nav and footer.
- `/species/<slug>.html` stays canonical for every species regardless of category. No URL migrations, no SEO risk to existing pages.
- Sitemap and structured data via existing `stocklib/structured_data.py` defaults. Shipping restriction warnings follow the existing rule ("No WA/NT/TAS" style, never "Ships to X" badges).
- State combo pages for new species render the existing guideless fallback (precedent: about 47 fruit species do this today). Growing guides for top bush tucker species follow as enrichment via the `docs/species-guide-rollout.md` batch pattern.
- Revisit a unified cross-category browse only at 3+ live categories.

### 3.6 Observability (independent of all the above; ships in parallel)

- **Records:** new `stocklib/scrape_health.py`. Every scraper (shopify, woocommerce, bigcommerce, ecwid, daleys) appends one JSONL line per nursery run to `data/scraper-health/YYYY-MM-DD.jsonl`: `{ts, nursery, ok, products, in_stock, duration_s, http_403, http_429, error}`. 403/429 captured in the fetch error handlers.
- **Detection + alerts:** new `detect_scrape_anomalies.py` in `run-all-scrapers.sh` after the smoke test. Conditions: scraper failed; products == 0 where yesterday > 0; any 403/429; 3-day failure streak. Emails Benedict via `tools/autonomous/notify.py:send_email` (same path as the surge detector), idempotent per day, with a dry-run flag.
- **Panel:** extend the existing Cloudflare-Access-gated /admin (`subscribe_server.py` + `admin_view.py`, three-layer pattern): per-nursery 14-day ok/fail/zero grid, last success time, product count trend, recent errors. Unclassified-per-nursery counts join the panel once the categorize ladder lands. Deploy needs a subscribe-server restart; the Caddy route already proxies /admin.

### 3.7 Subscriber emails (Benedict-approved 2026-06-11)

A clearly labelled "Bush tucker" section in the existing daily/weekly digest at enable time. Variant-level price comparison only (`_variant_key`), never product-level min_price. Variety watches are opt-in by nature and need no segmentation. No preference plumbing unless the digest section draws complaints. Dale drafts the copy, Benedict reviews before the first send.

## 4. Phased rollout and ticket specs

Phases 0 and 1 are independent and can run in parallel. Phase 2 is gated on Phase 1. Phase 3 is gated on the Phase 2 review.

**Backlog note (2026-06-11):** the Dale backlog sits near its 20-ticket cap, so only two umbrella tickets (P0, P1) are filed now; their descriptions point here. P2 tickets get filed when Phase 1 ships or slots free. P3 is a single placeholder filed with P2.

### Phase 0: Observability

- **P0.1 Scrape-health records.** `stocklib/scrape_health.py` + hooks in the 5 scrapers + 403/429 capture. AC: one JSONL record per nursery per run including failures; unit tests for the writer; pipeline behaviour otherwise unchanged.
- **P0.2 Anomaly detector + alerts.** `detect_scrape_anomalies.py` wired into `run-all-scrapers.sh`; notify.py reuse; idempotent per day; `--dry-run`. AC: fixture-based unit tests for each condition; a forced dry-run prints the email it would send.
- **P0.3 /admin scrape-health panel.** Extend admin_view with the health grid. AC: renders with zero records (empty state) and mixed records; no new public routes; CF Access still fails closed.

### Phase 1: Category plumbing (every step behaviour-preserving; byte-identical goldens are the acceptance test)

- **P1.1 Taxonomy.** `tags` default, `KNOWN_CATEGORIES`, `landing_species()`; schema tests (category in KNOWN_CATEGORIES, unique slugs, no bare ornamental-word names).
- **P1.2 Classify split.** `TRUE_JUNK` + `CATEGORY_KEYWORDS` + derived `NON_PLANT_KEYWORDS`; no-forking guards; partition tests (disjoint, union equals public set, enabling "native" un-junks its keywords).
- **P1.3 Cultivar gate.** `_species_records()` seam onto `enabled_species()` for all three readers; vocabulary-scoped ornamental rejection (dormant myrtle fix). Regression tests via injected records: registered Lemon Myrtle parses, "Hibiscus Petite Orange" still rejects, crepe myrtle still rejects, unregistered Lemon Myrtle still rejects.
- **P1.4 Builder migration.** Move all direct `fruit_species.json` readers onto `taxonomy.enabled_species()`, in leak-blast-radius order: cultivar_parsing/variety pages, then wishlist/llms/archive (enumerate-all-records builders), then species/state/compare/trends/location/dashboard (including the dashboard's second read around line 756), then senders and the dead `daily_digest.py` constant. Add a no-forking guard banning direct `fruit_species` reads outside `stocklib/taxonomy.py`.
- **P1.5 Dashboard junk de-fork.** Delete the local `non_plant_keywords` list (~line 522); filter with `TRUE_JUNK` plus ornamental/vegetable keywords, NOT native keywords (the ~12 live melaleuca/wattle dashboard rows must survive as unclassified). Upstream the 4 dashboard-only junk keywords (combo pack, starter kit, tree sealant, end stop terminator). Known prod diff: 8 live junk products drop (6 Guildford mushroom kits, 1 Ross Creek soil conditioner, 1 Ross Creek gift card); enumerate them in the PR. Dashboard golden is unaffected (verified against fixture).
- **P1.6 Categorize ladder.** `stocklib/categorize.py`, `nursery_categories.json` (seeded as in 3.2), `--needs-review-out` on build-dashboard, cron flag, counts into the P0.3 panel. Tests: ladder precedence, matcher modes, the `&amp;` case, unknown nursery, missing config.

### Phase 2: Bush tucker pilot (gated on Phase 1)

- **P2.1 Species records.** Re-run the census on the server (current snapshots), then author roughly 15 to 20 `bush_tucker` records (candidates: lemon myrtle, aniseed myrtle, cinnamon myrtle, mountain pepper, saltbush, warrigal greens, native ginger, native raspberry, native guava, native currant, native thyme, native mint, riberry, quandong if not present, sea celery; verified descriptions, latin_name required, no bare ornamental-word names) plus `tags: ["bush_tucker"]` on the 8 existing fruits. Still disabled; goldens unchanged.
- **P2.2 Golden fixture prep.** Add bush tucker products to the test fixture; intentional dashboard-golden diff (new unmatched rows) reviewed.
- **P2.3 Enable.** `ENABLED_CATEGORIES = ("fruit", "bush_tucker")`; pinned test flips (Lemon Myrtle OUT to IN); retire the cinnamon-myrtle-mini grandfather; `GOLDEN_UPDATE=1` regeneration, reviewing that the diff is exactly the new-category surfaces and zero changes to existing fruit pages; review per-nursery dashboard pre-filters (`FRUIT_FILTERS`) for the lead nurseries.
- **P2.4 Landing page.** `/bush-tucker/` builder + header/footer nav + sitemap + structured data; deploy + cache purge.
- **P2.5 Digest section.** Labelled bush tucker section, variant-level compares; Benedict reviews copy before first send.
- **P2.6 Scraper scope fast-follow (optional).** Widen configs where filters exclude bush food: Diggers fruit_tags, Garden World product_types, Forever Seeds tags, Garden Express/Plantnet/Diacos category slugs, Heritage categories. Health panel watches for fallout.
- **P2.7 Growing guides batch** for top bush tucker species (existing rollout pattern; unlocks state-combo uniqueness).
- **P2.8 Pilot review checkpoint** (~6 weeks post-enable): measure success criteria below; natives go/no-go. "Tell him he's dreaming" is a valid outcome.

### Phase 3: Natives (single design-review ticket, gated on P2.8)

Enabling "native" auto-un-junks the 311 filtered products via the keyword machinery. Work to scope then: genus-level records (grevillea, banksia, kangaroo paw, callistemon, melaleuca); the no-variety-pages decision for ornamentals; `bigcommerce_scraper.py` applies the junk list at scrape time, so snapshot contents change going forward; thin-content guard for combo pages; Ladybird as anchor nursery.

## 5. Pilot success criteria (judged at P2.8; thresholds Benedict-adjustable)

- Bush tucker surfaces indexed and earning at least 30 organic clicks/week combined by week 6 (GSC).
- At least 5 bush tucker variety watches or digest interactions.
- Unclassified rate under 10% for the lead nurseries.
- Zero regression in fruit engagement.
- Scrape health green throughout (no sustained red on the /admin grid).

## 6. Risks

- **Identity dilution.** Mitigated by IA: homepage untouched, fruit remains default, bush tucker is an adjacent collector interest rather than a generic category.
- **Thin content on new species/state pages.** Mitigated by the guideless fallback precedent and the P2.7 guides batch; natives phase adds an explicit guard.
- **Classification leaks (the cinnamon rose problem).** Mitigated by ladder precedence (registry first), the vocabulary-scoped gate, needs-review visibility in /admin, and golden coverage at every plumbing step.
- **Subscriber pushback on digest changes.** Mitigated by clear labelling, Benedict review, and the explicit fallback of building preference controls only if complaints arrive.
- **Block risk from scope widening.** Small by evidence (most data already fetched); P0 ships visibility before P2.6 widens anything.

## 7. Non-goals

- Non-plant supplies: junk forever.
- Homepage changes above results: never.
- Paid scraping infrastructure or proxies: not without block evidence.
- Subscriber preference plumbing: not in the pilot.
- Beestock de-fork: separate work (DAL-140).
- A second taxonomy hierarchy level: not needed; flat species + category + tags covers the ceiling.

## 8. References

- DEC-200 (this direction), DEC-195 (variety gate), DEC-104 (track structure), DEC-176/178 (variety page precedents).
- DAL-192 (long-tail exotics, same gate seam).
- `docs/species-guide-rollout.md` (the batch rollout pattern P2.1/P2.7 reuse).
- CLAUDE.md treestock rules (results above the fold, restriction warnings, variant-level compares, no em dashes).
