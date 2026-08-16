# Page lifecycle: stop deleting URLs that still mean something

Branch: `dale/page-lifecycle`. Scope agreed with Benedict 2026-08-16: the nightly lifecycle
only. The slug merge already landed separately (see "What already landed"); the 2,512-URL
backfill is deliberately deferred until this has proven itself over a week of nightlies.

---

## 1. The problem

Both page families decide whether they exist from what is in stock tonight, and they fail in
opposite directions.

- **Variety pages delete themselves.** `build_variety_pages.py:381-391` unlinks any page whose
  slug is not in tonight's set. The comment says it exists for the case where "parse_cultivar
  tightens up and a slug stops being generated", so it was written for **renames**.
- **Combo pages freeze.** `build_species_state_pages.py:613-655` only writes, never deletes, so
  a `buy-<species>-trees-<state>.html` that falls below `MIN_PRODUCTS = 3` serves a stale
  in-stock table forever. 10 such orphans as of 2026-08-16, including feijoa WA (889
  impressions/yr) and tamarillo WA (676).

One root cause: **the builders have no memory of what they built last night**, so they cannot
tell a delisting from a rename from a page that should still exist but is empty today. The
deletion does the right thing for the case it was designed for and the wrong thing for the two
that dominate in practice.

### Measured cost

165 days of snapshots replayed through the real builder logic; deletion counts reconcile with
`scraper.log` exactly, so these are behaviours, not estimates.

| | |
|---|---|
| Delete/recreate events in 165 days | **1,546** |
| ...of which a page vanishing for exactly one night | **1,312 (85%)** |
| Variety slugs ever generated / dead as of 2026-08-16 | 3,013 / 288 |
| Worst night (Heritage bare-root season ending, 375 products to 181) | 62 pages |

GSC, 365 days to 2026-08-13: Google knows 4,658 `/variety/` URLs, **2,512 now 404**, carrying
**13,662 impressions (30% of variety impressions) and 472 clicks (34%)**. **1,066 of the dead
URLs still rank in the top 10.** Plausible independently shows **330 visitors in 30 days**
landing on 404ing variety URLs, a fifth of all variety traffic. The sources agree rather than
conflict: Caddy rewrites to `/404.html` without redirecting, so Plausible logs a pageview on the
original path and GSC logs a click.

Two cases that make it concrete:

- `Pecan - Mahan (B)`: Daleys listed it 5 Mar to 1 May, delisted, relisted 11 Aug. The page
  404'd for **101 days** and then rebuilt itself.
- `dwarf-lychee-salathiel` (296 impressions, position 7.7) and `semi-dwarf-lychee-salathiel`
  (180, position 6.4) were **not dead varieties**. Both renamed to `lychee-salathiel`, which is
  live. "Dwarf" became a type-label pill, the slug changed, the old files were unlinked with
  nothing left behind.

### Why this is backwards for this business

Per-variety alerts became the product on 2026-08-15 (DEC-294). Unavailability is when the
signup is worth most, and it is exactly when we delete the page.

We already do the right thing in the adjacent case: a product that is listed but out of stock
renders "0 in stock", the last nursery rows, and a prominent notify-me form. Roughly 1,220 of
the live variety pages are in that state. The only difference from a deleted page is whether the
nursery kept the listing up, which to a collector is the same event.

---

## 2. What already landed, and the debt it left

`2cff70c` (2026-08-16) fixed the parser so one cultivar gets one slug, measured against all
14,021 live titles, and `11e83c0` added `variety_overrides.json` with `deny` and `alias`
curation. That is the merge. It was validated better than the version originally planned here:
running both parsers over live data showed `seedless`, `thornless`, `male`/`female` and
`seedling` were unsafe to strip (Crimson Seedless and Chester Thornless are cultivar names;
kiwifruit and pistachio sexes are separate products), and all four are excluded with tests.

**The debt.** That change took variety pages from 2,764 to 2,633 slugs, and it deployed and
rebuilt at 03:12 on 2026-08-16 with the unlink loop still in place and no redirect mechanism.
Live pages went 2,726 to 2,582. `check_watched_slugs.py` correctly guarantees no *watched* slug
moved, and its own docstring notes that "build_variety_pages.py deletes orphan pages silently".
The unwatched folded slugs had no such guard and are now 404.

**Nothing is unrecoverable.** Both parser versions are in git and the snapshots are on disk, so
the exact old-to-new mapping regenerates by running each parser over the same titles. Task R1
below does that, and it is the highest-value early task on this branch because those redirects
are deterministic rather than reconstructed by archaeology.

---

## 3. Constraints. Violating one is a defect, not a tradeoff.

- **No email capture on a combo tombstone.** Species-level watches were removed deliberately
  (`3f89a09`). DEC-294 found a "watch this species" banner POSTing `action:'watch'` to
  `/api/subscribe`, an action the server never had, silently enrolling people in the digest
  while telling them they were watching a species. `DIGEST_SIGNUP_ENABLED = False`, so no digest
  box either. Shared callout and CTA **slot**: variety fills it with the working
  `/api/watch-variety` form, combo fills it with links to that species' `/variety/` pages.
- **Never tombstone a page that has stock to show.** Combo thresholds split three ways: create
  at >= 3 (`MIN_PRODUCTS` unchanged), retain and render live at >= 1 however thin, tombstone
  only at 0.
- **A page cannot be born a tombstone.** Creation still requires stock; the tombstone state is
  reachable only from `live`. Demand without stock belongs in the existing species `wishlist`.
- **No `noindex` on variety pages.** DEC-266 tested exactly this and refuted it.
- **Tombstones live indefinitely**, no expiry sweep. Measured: 84% of combos that hit zero stock
  are back within 30 days. Any window under a year deletes precisely the pages that were coming
  back.
- **No em dashes in user-facing copy.**

---

## 4. The ledger

New `tools/scrapers/stocklib/page_ledger.py`. Files at `/opt/dale/data/page-ledger/`
(`variety.json`, `species-state.json`, plus one-deep `.prev` backups). Data dir, not the output
dir, because `/opt/dale/dashboard` is the web root and is globbed by the sitemap.

```json
{"schema": 1, "family": "variety", "updated": "2026-08-16", "skipped_nights": 0,
 "pages": {
   "pecan-mahan-b": {
     "state": "live",                      // live | tombstone | redirect | retired
     "first_seen": "2026-03-05", "last_seen": "2026-05-01",
     "live_days": 58, "in_stock_days": 44, "last_in_stock": "2026-05-01",
     "since": "2026-05-02", "seeded": false,
     "title": "Pecan - Mahan (B)", "species": "Pecan",
     "species_slug": "pecan", "variety": "Mahan (B)",
     "rows": [{"nursery_key": "daleys", "nursery_name": "Daleys", "price": 49.0,
               "available": true, "url": "https://...", "states": "NSW, QLD, VIC",
               "type_label": ""}],
     "rows_as_of": "2026-05-01",
     "redirect_to": null, "retired_reason": null}}}
```

`rows` capped at 12 (60 for combos, matching that page's own render cap). `live_days` counts
nights generated, not a streak. The combo family keys on the filename, because there the URL is
the identity.

**Why purpose-built rather than derived from `availability.json`.** That file is keyed
`url|sku`, carries no variety slug, and a Shopify handle change mints a new row with a new
`first_seen`. More fundamentally, deriving identity from titles re-derives it nightly under the
current parser, which is the bug class being fixed. It is good archaeology for seeding and
backfill, and the wrong primary.

### 4.1 Opt-in by flag, which is what makes the tests trustworthy

Both builders gain `--ledger PATH`. **Without the flag the builder is stateless: no ledger read
or write, no tombstones, and no deletes.** `tests/golden_runner.py` runs builders with no extra
args, so **all 19 golden cases must be byte-identical after this change.** If a golden moves,
the change is not as inert as claimed and work stops until we know why. `run-all-scrapers.sh`
and `tools/scripts/rebuild_pages_email_safe.sh` both pass `--ledger`.

Both builders currently read `sys.argv` positionally. Convert to `argparse` with the existing
positionals plus `--ledger`, `--allow-delete`, `--dry-run`, `--seed`. Keep
`build_species_state_pages.py`'s trailing `print(json.dumps(pages))` as the last stdout line
(`run-all-scrapers.sh:317` pipes to `tail -3`).

### 4.2 Degradation. No path leads to a mass unlink.

| condition | behaviour |
|---|---|
| no `--ledger` | today's behaviour minus the delete |
| file missing | seed from tonight's output, tombstone nothing, log `LEDGER MISSING, seeding` |
| file corrupt | as above, plus a loud `ERROR`, and do not overwrite `.prev` |
| tonight's slug count < 85% of ledger `live` count | write ledger, `skipped_nights += 1`, change no page states |

The only `unlink` calls in the design sit behind `--allow-delete`, which a manual run never
passes.

---

## 5. The nightly decision

Runs inside each builder after pages are written, over `set(ledger.pages) - tonight_slugs`.

**Resurrection first.** Any slug generated tonight that is `tombstone`, `redirect` or `retired`
returns to `live`, keeps its `first_seen`, and clears `redirect_to`. The real page overwrites
the stub or tombstone at the same path, so there is no deletion path to get wrong and no race.
A generated slug always wins.

Then, for each disappeared slug, in order:

1. **Scrape-health gate.** Read `data/scraper-health/<today>.jsonl` via
   `stocklib.scrape_health`. A nursery is UNTRUSTED if `ok=false` or its product count is below
   60% of its 7-day median. Any slug whose last-known rows were **entirely** at untrusted
   nurseries stays `live`, HTML untouched. Highest-value safety mechanism, and it reuses a feed
   already written nightly.
2. **Exit guard, N=2.** If this is the first night absent, record it and stop. Measured: this
   suppresses **1,312 of 1,546 variety events (85%)** and 45% of combo events, for one day of
   latency. Both families land on the same knee, so one constant.
3. **Entry guard.** Require `live_days >= 7` **and** `last_seen - first_seen >= 7 days`. The
   span condition matters: a pure consecutive-days rule breaks on the pipeline's own missed
   nights, of which there were two in the last month. Below the guard, delete (behind
   `--allow-delete`).
4. **Rename (variety only).** If the stored rows' product URLs reappear tonight under a single
   different slug accounting for >= 50% of them, write a redirect stub. Combo keys come from
   taxonomy rather than parsed titles, so combos skip this branch.
5. **Retired.** If every stored title now returns `None` from `canonical_cultivar`, the variety
   left the taxonomy (DEC-195 gate, or a `variety_overrides.json` deny). Delete, record
   `retired_reason`. The only case where a URL is allowed to die.
6. **Otherwise, tombstone.**

**Ambiguity resolved toward honesty.** A split (rows moving to two different slugs) tombstones
with "now listed as X and Y" links rather than redirecting, because a redirect asserts a single
successor. Overlap below the majority threshold tombstones with a "see also" link. Every
non-obvious classification appends to a `review` list in the ledger.

**Chained renames.** A to B, later B to C. Re-resolve all `redirect` entries nightly and rewrite
any stub whose terminal target moved. Depth cap 8, cycle-safe.

---

## 6. Rendering

### 6.1 Redirect stubs: generated HTML, not Caddy config

`infrastructure/README.md` states in bold that those files are recordings, not deploy sources.
A generated Caddy snippet needs a nightly root-privileged config write plus a reload, and the
blast radius of a malformed one is every domain in the file. It would also make
`snapshot-server-config.sh` email config drift every Monday, training us to ignore drift alerts.
Disproportionate for a page-lifecycle change.

The stub carries an instant `<meta http-equiv="refresh">`, `<link rel="canonical">` to the
target, a state meta tag (section 8), and **a visible link**, because a stub returns 200 and
anyone with meta refresh disabled sees only what is on the page.

Two rules:

- **No `noindex` on a stub.** A noindexed page that also canonicals elsewhere is a conflicting
  signal, and DEC-266 settled that variety URLs are not noindexed.
- **No watch form on a stub.** A watch on a dead slug is inert (`send_variety_alerts.py` uses
  `.get(slug, [])`), so a form there enrols people against a slug that can never fire. That is
  the DEC-294 shape exactly: a control that looks like it works and does not.

Honest downsides: a meta refresh consolidates more slowly than a 301, and because a stub is a
200, monitoring that asks "is this a 404" now says fine. If GSC still shows old URLs ranking
after 60 days, escalate to real 301s. Follow-up, not prerequisite.

### 6.2 Tombstones

New `stocklib/tombstone.py` renders **only the callout, the date sentence and the CTA slot**.
Each family renders its own table: a variety tombstone's rows are listings of one cultivar, a
combo's are up to 60 products spanning many cultivars. Sharing more would grow a `mode=`
parameter within a month, which is what `stocklib` exists to prevent.

**Variety needs no new template.** Reuse `variety_page.html.j2` with empty `product_view`, a new
`tombstone_html` variable, and a third branch on the existing `watch_heading`/`watch_body`. The
`#watchSection` form already renders unconditionally and posts to the working endpoint, so the
variety CTA needs zero new code. Suppress the table when there are no rows (today it would
render bare headers).

Copy, no em dashes:

> **Buy Mahan (B) Pecan Trees in Australia** *(H1 unchanged)*
> *(blurb, if one exists)*
> No nursery we track is currently listing Mahan (B) Pecan. It was last in stock on 1 May 2026
> at Daleys for $49.00. We tracked it at 1 nursery between 5 March and 1 May 2026, in stock on
> 44 of those 58 days.
> *(last known rows, nursery names linking to `/nursery/<key>.html`, not to dead product URLs)*
> *(watch form)*
> Other Pecan varieties in stock now: Wichita, Pawnee, Elliot.

**Combo CTA** is a capped list of `/variety/` links for that species, in-stock first, plus the
species page and the other states' combo pages. No form, no email input, no `/api/` call. The
slot can be empty (feijoa WA tombstones precisely because it has no feijoa), so degrade to the
species page, then the state hub. Never render an empty box.

### 6.3 Soft-404 risk, the sharpest risk here

A tombstone with no unique content is a soft 404, which is no worse than today's hard 404 but
wastes the work. Only 34 of the 2,512 dead URLs have a written blurb (1,153 of the live
varieties do), so most tombstones need substance from elsewhere. In descending value:

1. **Do not lead with the negative.** H1 stays "Buy X Trees in Australia" and the callout sits
   below the blurb. A page whose first 200 words are a variety description is not a soft 404 to
   any classifier.
2. **The date and price-history sentence** is unique, factual and per-page, and exists for every
   tombstone. This is what `first_seen` / `in_stock_days` / `last_in_stock` are for.
3. **Other varieties of that species in stock now.** Real content, and the highest-value thing
   to put in front of someone who wanted this cultivar.
4. Growing guide and species links where they exist.
5. **No Product JSON-LD.** Already true by construction, but pin it with a test: if someone
   later feeds last-known prices into the row data, the page starts advertising a purchasable
   product that cannot be bought.

Blurb coverage for tombstoned slugs carrying impressions is the real lever, and it is content
work via the existing `variety-rollout` skill, not template work.

Stated plainly: some tombstones will still be soft-404'd. Acceptable, not worse than the 404,
and it self-heals when stock returns.

### 6.4 Combo threshold split

`MIN_PRODUCTS = 3` stays as the **create** threshold; add `RETAIN_MIN_PRODUCTS = 1`. The subtle
part is the cap: a retained thin combo must not consume a `MAX_COMBOS_PER_STATE` slot nor be
dropped for sorting below it, so compute the new set with the existing cap and guided-tail logic
(DEC-295) and then **union** the retained set. `ComboSelectionTests` needs new cases, and
`test_cap_still_bounds_the_guideless` needs its docstring restated: the cap bounds *new*
guideless pages, not the live set.

The 10 current orphans are on disk but in no ledger, so seeding must enumerate
`buy-*-trees-*.html` from the filesystem, not just from snapshots.

### 6.5 Atomic write-if-changed, and `<lastmod>` becoming true

Neither builder writes atomically today (`write_text`, `open().write()`). A crash mid-write
leaves a truncated file that the sitemap submits; today that self-heals next night, but once
files are permanent so is the truncation. Route both through `page_ledger.write_page()`: write
temp, `os.replace`, and skip the write entirely when bytes are unchanged.

That also fixes two things at once. Tombstones are re-rendered nightly from fixed ledger data,
so a nav or footer change reaches them (otherwise `rebuild_pages_email_safe.sh` would skip every
tombstone forever), while their mtime stops churning. Drop the `Updated {{ today }}` line from
tombstones, which is a lie on a tombstone anyway, and their sitemap `<lastmod>` says something
true for the first time.

---

## 7. Recovering the slugs the merge already deleted (task R1)

Highest-value early task, because both ends of the mapping are deterministic rather than
reconstructed.

1. Check out `cultivar_parsing.py` at `75df8b7` (pre-merge) and at `HEAD`.
2. Run both over the same live snapshot titles.
3. For each old slug absent from the new set, take its product titles and compute the new slug.
   A single consistent target is a **rename**; `None` for all titles is **retired** (a deny in
   `variety_overrides.json`, or the taxonomy gate); anything else goes to review.
4. Seed the ledger with those entries so the first nightly run emits the stubs through the
   normal path. Do not write HTML by hand: one renderer, one code path.

Expect roughly 144 URLs, most of them renames onto slugs that exist today.

---

## 8. Sitemap

Every generated page gets `<meta name="treestock-page-state" content="live|tombstone|
redirect-stub">`, and `build_sitemap.py:_collect_dir` reads the first 1KB and excludes by state.
Rejected alternatives: reading the ledger from the sitemap builder (couples it to a file it does
not own and breaks the hand-built test fixture), and a sidecar exclusion list.

| state | in sitemap |
|---|---|
| live | yes |
| **tombstone** | **yes** |
| redirect stub | no |
| retired | file removed |

Tombstones belong in the sitemap: they are 200s with unique content and we want Google to
recrawl and learn they are not 404s. Carrying the state as a *value* rather than a bare marker
is also what makes rollback lever 2 a one-line change.

Tombstoned varieties are **excluded from `/variety/index.html`**, which is exactly the
`GRANDFATHERED_VARIETY_SLUGS` precedent: a page that exists, is not browsable, and survives the
sweep.

**Fix the ordering hazard while here.** `build_sitemap.py` runs at `run-all-scrapers.sh:277` but
`build_location_pages.py` at 312 and `build_species_state_pages.py` at 317, so tonight's sitemap
describes last night's combo files. Harmless today, wrong once state changes matter. Move both
page builders above the sitemap step; nothing between those lines feeds either.

---

## 9. Rollout order

| # | Step | Gate before proceeding |
|---|---|---|
| 1 | `stocklib/page_ledger.py` + tests | new tests green, no builder touched |
| 2 | `stocklib/tombstone.py`, templates, no-forking guards | full suite green, **all 19 goldens unchanged** |
| 3 | `build_variety_pages.py`: argparse, ledger, resurrection, classify, tombstone, `write_page`, index exclusion, delete behind `--allow-delete` | `variety` golden **unchanged** |
| 4 | `build_sitemap.py` state exclusion + `run-all-scrapers.sh` reorder | sitemap and pipeline tests green |
| 5 | `build_species_state_pages.py`: retain threshold, tombstone, ledger | `species_state` golden **unchanged**; DEC-294 guard green |
| 6 | New golden case `variety_tombstone` with a committed fixture ledger | reviewed by hand |
| 7 | Deploy, seed both ledgers, dry run, **let it run 7 nights** | night 8: first tombstones, plausible count, the 10 combo orphans tombstoned |
| 8 | Task R1: recover the ~144 slugs the merge deleted | stub count matches; spot-check 5 in a browser |

**Deploy rule: commit, then `tools/deploy.sh`. Never scp.** This deploy will bounce
`subscribe-server`, because the new `stocklib/*.py` files fall under the module checksum.
Expected, but confirm the restart in the deploy log rather than assuming (DEC-264).

`tools/deploy.sh` does not purge Cloudflare, so a code deploy changes nothing users see until
the next nightly rebuild and purge. "Deployed" and "live" are up to 24 hours apart.

Deferred to a separate piece of work: the backfill of the 2,512 historically dead URLs. Method
is task R1 generalised, with snapshot archaeology instead of a known parser pair, and a reviewed
proposal file before it writes roughly 1,900 pages. Roughly two thirds of those URLs should stay
404, being out-of-taxonomy plants and URLs predating our snapshot history, so it is not a
mechanical apply.

---

## 10. Risks and rollback

**Night one with an empty ledger.** Nothing to classify, so nothing is tombstoned, deleted or
redirected, and **no page can be tombstoned until night 8**. That is the guard working, not a
bug. Seeding sets `first_seen`, `in_stock_days` and `last_in_stock` from `availability.json` and
marks `seeded: true`, so genuinely old pages satisfy the guard on night one and new ones do not.

**Partial scrape mass-tombstoning.** Highest-severity risk; Ladybird alone is 6,529 of about
10,000 products. Four layers, all required: the existing `latest.json` fallback (a *failed*
scrape keeps yesterday's data, so the danger is a scrape that *succeeds* truncated); the
per-nursery health gate; the 85% global circuit breaker; and `MAX_TOMBSTONES_PER_NIGHT = 150`,
which bounds a bug in the first three to one constant.

The asymmetry that makes this safe: **tombstoning is reversible**, since the page returns the
moment the slug is generated again. Only `retired` and the sub-7-day delete are irreversible,
and both sit behind `--allow-delete`.

**If Google reacts badly**, defined up front so the trigger is pullable: variety clicks down
more than 30% over 14 days versus the prior 14, or site-wide impressions down more than 15%,
neither explained by a core update. Ladder: (1) stop creating new tombstones; (2) add
`tombstone` to the sitemap's excluded states, one line, pages still serve 200 for humans; (3)
purge tombstones from disk, restoring today's behaviour while keeping the ledger; (4) revert.
**Do not use `noindex` as a rollback**; DEC-266 settled it and a noindex-then-remove cycle is a
worse signal than either state.

**Cloudflare.** The nightly `purge_everything` helps, since a new tombstone or stub is live at
the edge immediately rather than sitting behind a cached 404. It hurts in one way: the purge
runs before `smoke_test.py`, so the smoke test re-warms the edge from origin and a broken
tombstone gets cached for an hour by the check meant to catch it. Add a night-over-night check
that the variety sitemap URL count has not dropped more than 10%, rather than pinning a specific
tombstone URL, since any tombstone can legitimately come back in stock.

---

## 11. Open item

`tools/scrapers/CLAUDE.md` is **untracked in git** and still describes the pre-`41b3260` world
where the parsing helpers are duplicated across three builders. They are not; they live in
`cultivar_parsing.py` and `tests/test_parsing.py:248` enforces it. That file auto-loads for
anyone working in that directory, so it misinforms every session. Awaiting Benedict's call on
whether to correct it and track it as part of this work.
