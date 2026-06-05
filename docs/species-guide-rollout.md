# Species growing-guide rollout

Plan for building a comprehensive, per-state, cited growing guide for every tracked species on
treestock.com.au, one species per fresh Claude Code session. Olive shipped first (DEC-126 / DEC-127)
as the reference implementation; this doc tracks the rest.

How it works:
- The content layer is `tools/scrapers/growing_guides/<slug>.json` (state-invariant `core` plus
  per-state overlays). See the `project_growing_guides` and `reference_owned_content_archives`
  memories, and `olive.json` as the gold standard.
- Rendering boundary (read this, it changed): `growing_guides.py` turns the JSON into a
  pre-rendered HTML fragment using Python string-building (NOT a Jinja2 template). The page
  builders then inject that fragment into the autoescaping Jinja2 page templates through a `|safe`
  slot (`stocklib/templates/species_state_combo.html.j2` `{{ guide_body|safe }}`,
  `species_page.html.j2` `{{ description_html|safe }}`); the FAQ JSON-LD goes to the head via
  `growing_guides.faq_jsonld()`. Because the block is `|safe`, your JSON strings are emitted
  VERBATIM (not escaped), which means: inline HTML in a `body`/`intro` is intentional and works
  (e.g. internal `<a href="/species/longan.html" class="text-green-700 hover:underline">longan</a>`
  links), but any literal `&`, `<`, `>` in prose MUST be hand-escaped (`&amp;`, `&lt;`, `&gt;`),
  and the no-dash rule still applies. Adding a species is still just one JSON file: no template
  or code change.
- Run the prompt below in a fresh session, changing only the species, and work down the priority
  order. Each run opens a PR; merge + deploy stays a human gate.
- Re-check traffic periodically (the priority order is a snapshot, not fixed).

## The prompt (substitute one line per run)

```text
SPECIES = lychee

You are building a comprehensive, evidence-backed, per-state growing guide for {{SPECIES}} on
treestock.com.au, matching the olive implementation we already shipped, and shipping it via PR.

## 0. Start from an up-to-date tree, THEN orient (do this FIRST)
- The olive infrastructure (growing_guides.py, growing_guides/olive.json, build_species_state_pages.py,
  build_archive_index.py, the tests) is ALREADY MERGED to origin/main. The local `main` checkout may be
  STALE (dozens of commits behind), so do NOT trust the current working copy. First fetch and create
  your worktree off origin/main, then do EVERYTHING inside it:
    `git -C <repo> fetch origin`
    `git -C <repo> worktree add ../dale-{{SLUG}}-guide -b dale/{{SLUG}}-guide origin/main`  then cd there
  Sanity check: `tools/scrapers/growing_guides/olive.json` MUST exist in your worktree. If it does not,
  you are not on origin/main - fix that before continuing (the infra is merged; your checkout is behind).
- CLAUDE.md - obey the treestock rules: NO em or en dashes in copy; search results stay above the
  fold; variant-level price comparison only.
- Memory: `project_growing_guides` and `reference_owned_content_archives` (the content layer + the
  three archive sites and how to use them).
- Mirror these reference files exactly (structure, depth, tone):
  - `tools/scrapers/growing_guides/olive.json`  (gold-standard schema + writing quality)
  - `tools/scrapers/growing_guides.py`  (has_guide, render_combo_guide, render_further_reading merge;
    string-built fragment, injected `|safe` into the templates below)
  - `tools/scrapers/stocklib/templates/{species_page,species_state_combo}.html.j2` and
    `tools/scrapers/stocklib/templates.py` (the autoescape Jinja2 env; invariants pinned by
    `tests/test_templates.py`) - you do NOT edit these to add a species, but understand the boundary
  - `tools/scrapers/build_species_state_pages.py`  (core/overlay, SPECIES_CLIMATE_CATEGORY, STATE_CLIMATE_NOTES)
  - `tools/scrapers/build_species_pages.py`, `tools/scrapers/build_archive_index.py`
  - Tests are split so parallel runs do not collide: `tests/test_guide_<slug>.py` (one file per
    species, the per-species bar), `tests/guide_helpers.py` (shared setup), and
    `tests/test_species_state_pages.py` (cross-cutting guards: climate mapping, the unenriched
    fallback, the archive index, the growing_guides module API, and the FAQ-overlap guard over every
    guide). Add your species as a NEW `tests/test_guide_<slug>.py` (copy an existing one); keep the
    full suite green.
- Resolve the slug: find {{SPECIES}} in `tools/scrapers/fruit_species.json` and use its `slug`
  (call it {{SLUG}}). If {{SPECIES}} is not there, stop and ask before proceeding.

## 1. Pick the flagship state (data-driven)
- Find which state earns the most traffic for this species: run `tools/scrapers/gsc_analysis.py`
  (GSC) and/or Plausible (data.bjnoel.com, `tools/autonomous/plausible_stats.py`) and look at the
  `buy-{{SLUG}}-trees-<state>.html` and `/species/{{SLUG}}.html` entrances. Combine with climate
  reality (e.g. mango -> QLD tropical; olive -> WA Mediterranean). Research the flagship state
  deepest, but EVERY generated state still gets a genuine, unique overlay.
- Determine which states actually generate a page (WA = all species with 3+ in stock; QLD/NSW/VIC =
  top 20) by checking live stock or running the builder.

## 2. Research - fan out, adversarially verified, archives first
Split the work:
- State-INVARIANT (research once -> `core`): variety/cultivar choice, pollination/self-fertility,
  planting & soil, water & feeding (research this to the DEPTH CHECKLIST in step 3, with cited
  fertiliser specifics, not a generic "feed in spring" line), harvest, post-harvest/ripening or
  eating, buying tips.
- State-VARIANT (research per state -> `states.<ST>`): climate fit, named growing regions, harvest
  window, pests & diseases, and for WA the quarantine/shipping context.

Source PREFERENCE ORDER - strongly prefer Benedict's OWNED sites first (first-party authority,
citable URLs, keeps authority/traffic in-network):
  1. RFC archives - rfcarchives.org.au  (`/Next/Fruits/<Species>/`). Richest rare-fruit source.
     Read the articles for ground truth (local mirror: /Users/bjnoel/Projects/rfcarchive.org.au,
     or fetch live). OWNED -> cite and use as followed "Further reading".
  2. WANATCA - wanatca.org.au  (yearbooks, Quandong, ACOTANC). Search the local
     /Users/bjnoel/Projects/wanatca-hugo for {{SPECIES}}: `content/wanatca yearbook/YearbookIndex.md`,
     `content/Quandong/keyword-index.md`, `content/ACOTANC/papers/*`. Yearbook PDFs are citable at
     `https://wanatca.org.au/yearbooks/Y<N>all.pdf` (use #page if useful). OWNED -> cite + followed.
  3. RFCWA - rarefruitclub.au/wp/fruit-trees/ (WA Rare Fruit Club). Benedict does NOT host this, so
     it is THIRD-PARTY: cite with `"nofollow": true`; do NOT use it as a followed Further-reading link.
  Then fill gaps with authoritative third parties (nofollow): state ag departments (.gov.au - DPIRD
  WA, Business Queensland/DAF, NSW DPI, Agriculture Victoria), AgriFutures/RIRDC, BOM, the relevant
  industry body. Down-weight forums and retail blogs.

Rules: correctness is the top priority - wrong variety/climate/pest/harvest advice wastes a grower's
years. For every cited claim, open the URL and confirm it returns HTTP 200 AND supports the claim;
adversarially cross-check the key claims against a second source. Tie variety recommendations to
varieties actually in the live stock table.

## 3. Author tools/scrapers/growing_guides/{{SLUG}}.json
- Mirror olive.json exactly: `slug`, `common_name`, `sources[]` ({id,name,short,url}), `core`
  (intro + subheaded cited `sections` + `faqs`), `states` {WA,QLD,NSW,VIC} (each intro + sections +
  faqs), and `further_reading[]` ({title,url,source[,nofollow]}).
- Per-state overlays must be genuinely unique (different regions, harvest windows, pests) so region
  tokens never leak across states. NO em/en dashes anywhere. Internal /species/ links must be real slugs.
- `further_reading`: hand-curate the best WANATCA yearbook articles + optionally one rarefruitclub.au
  link with `"nofollow": true`. (RFCA links auto-merge from the index in step 4 - don't list them all.)

### 3a. FAQs: every question must be NET-NEW (do not recap the body)
The body sections already tell the full agronomic story. The FAQ is NOT a summary of it. Each FAQ
must answer a question the body does NOT already headline, so the page covers MORE long-tail queries
in its FAQPage rich result and a reader never re-reads a fact they just read. (The old guides failed
this: nearly half the FAQs restated a section, e.g. "Do I need two trees to get fruit?" duplicating a
"Pollination" section, or "When do you harvest in <state>?" duplicating a "Harvest window in <state>"
overlay section. An automated guard now fails the build on this; see step 5.)

- HARD RULE: never pose an FAQ whose answer is the subject of a body-section heading. If a section is
  "Pollination: do you need two trees?", do NOT also add a "Do I need two trees?" FAQ. Likewise drop
  the per-state "When do you harvest in <state>?" and "Where are <species> grown in <state>?" and
  "Why won't nurseries post to WA?" FAQs when an overlay section already covers them.
- Instead, draw FAQs from these NET-NEW archetypes (pick the ~4-6 core + 1-2 per state that a real
  buyer of THIS species would still ask):
  - Commerce / sizing: "How much does a <species> tree cost?" (point at the live table), "Can I grow
    it in a pot / a small garden / a courtyard?", "How big does it get and can I keep it small?"
  - Decision / disambiguation: "Which variety is best for <fresh eating vs drying vs cold districts vs
    containers>?", "What is the difference between <X> and <Y>?", "Grafted vs seedling, does it matter?"
  - Troubleshooting / expectations: "Why is it flowering but not setting fruit?", "Why is it dropping
    fruit?", "How long until it fruits?" (ONLY if no body section already leads with this), "Does it
    need winter chill / frost protection?", a species-specific quirk (e.g. lychee "chicken tongue"
    seed, mango sap burn, fig roots and pipes).
  - State FAQs stay genuinely state-specific but must NOT echo an overlay section: prefer a buying or
    siting angle ("Can I bring a tree into WA myself?", "Which local nurseries stock it?") over a
    harvest-timing recap.
- Keep roughly 4-6 core + 1-2 per state for the JSON-LD, but every one must earn its place.

### 3b. Water and feeding: the DEPTH CHECKLIST (keep it ONE "Water and feeding" section, but deepen it)
The old guides were generic here ("apply nitrogen in spring", "a balanced fertiliser"). tamarillo is
the model to beat ("a complete fruit fertiliser, around NPK 5:6:6, in spring and again in summer ...
up to a kilogram for a mature plant"). The "Water and feeding" core section (and any state water note)
must cover, WHERE SOURCES SUPPORT IT:
- Water: need by growth stage (establishing vs bearing); the critical water-stress window for THIS
  species (e.g. flowering to fruit-swell drop; mango's pre-flowering dry period); rainfall vs
  irrigation; mulch; waterlogging/drainage sensitivity; a quantified water->yield figure when one is
  cited (model: olive WA "irrigated trees yield roughly twice as much").
- Feeding: name the fertiliser TYPE (complete/balanced, citrus or fruit-and-flower formulations,
  organic options like blood and bone / well-rotted manure / compost, sulphate of potash for fruit,
  trace elements where the species is deficiency-prone, e.g. iron or zinc chlorosis on alkaline soil);
  NPK DIRECTION (e.g. higher K than N for fruiting, low N to avoid leafy growth at the expense of
  fruit) and an approximate RATIO only when cited; a RATE per tree scaled by age when cited; the
  FREQUENCY and TIMING (split feeds across the warm season; what to ease off and when, e.g. cut
  nitrogen in late summer/autumn so wood hardens); soil pH where it drives nutrition.
- CORRECTNESS RULE (this is where wrong advice harms growers): do NOT invent NPK ratios, rates or
  frequencies. State a number ONLY when a cited authority (DPIRD WA, Business Queensland, NSW DPI,
  Agriculture Victoria, AgriFutures, the industry body, or a peer-reviewed / university-extension
  source) gives it, and cross-check it against a second source. If no source gives a number, stay
  specific-but-qualitative ("a complete fertiliser higher in potassium than nitrogen, fed little and
  often through the warm season") and still name the TYPE and TIMING. Wire each new claim to a
  `cites` id and add the source to `sources[]`.

## 4. Refresh the RFCA index + climate category
- Run `python3 tools/scrapers/build_archive_index.py`; confirm {{SLUG}} now has entries in
  `growing_guides/archive_links.json`. Its printed "WANATCA candidates" are your curation shortlist
  for step 3's further_reading. In a parallel batch, run it locally for the candidate list but do NOT
  commit the regenerated `archive_links.json` in your branch (it is regenerated once at close-out;
  see step 6).
- If {{SPECIES}} has special climate needs (as olive/grape use "mediterranean"), add/adjust its entry
  in `SPECIES_CLIMATE_CATEGORY` and the matching `STATE_CLIMATE_NOTES` per state (no dashes).

## 5. Test + build locally
- Keep `python3 -m unittest discover tests/` green (extend tests if the species needs it; reuse the
  uniqueness / no-dash / FAQ-JSON-LD / sources / further-reading guards).
- The FAQ-overlap guard (`FaqBodyOverlapTests` in `tests/test_species_state_pages.py`) runs over
  every `growing_guides/*.json` and FAILS if an FAQ answer substantially restates a section body, or
  an FAQ question restates a section heading. If it fails on your species, your FAQs are recapping the
  body: rewrite them per step 3a, do not raise the threshold.
- Golden gate: `tests/test_golden.py` runs `build_species_pages` and `build_species_state_pages`
  against the committed fixture and diffs the output. If your species is present in
  `tests/golden/fixture/` (today that is fig, lychee and mango; most species are NOT), enriching it
  changes the rendered page and the golden test will fail. That is EXPECTED: review the diff, confirm
  it is only your intended content change, then regenerate with
  `GOLDEN_UPDATE=1 python3 -m unittest tests.test_golden` and re-run the suite green. Commit the
  regenerated `tests/golden/expected/...` files with your change.
- Build against real stock into a tmp dir and open the {{SLUG}} pages: per-state-unique, cited,
  dash-free, with FAQ JSON-LD, article OG, Sources, and Further reading (RFCA merged + curated).
  Confirm /species/{{SLUG}}.html. curl every cited + further-reading URL -> 200.

## 6. Ship (do NOT merge unilaterally)
- You are already in the `dale/{{SLUG}}-guide` worktree from step 0. Commit; push; open a PR. Ask
  Benedict to review; on his go-ahead, merge + deploy: ssh dale-server, `git pull`,
  `tools/deploy.sh`, run `build_species_state_pages.py` + `build_species_pages.py` into
  /opt/dale/dashboard, rebuild purged Tailwind, verify live (200, fresh mtime, dash-free,
  per-state-unique). NEVER scp.

### Logging in a PARALLEL batch (this is what stops the end-of-run merge pile-up)
Guide runs are usually several agents at once, so do NOT, in your branch, touch any file that every
run edits at the same place: that is exactly what makes the second and later branches conflict on
merge. Specifically, in your branch:
- Decision: write ONE fragment `decisions/pending/{{DATE}}-{{SLUG}}-guide.md` (a `# title` line then
  the body, same shape as a log entry; see `decisions/pending/README.md`). Do NOT edit
  `decisions/decision-log.md`, and do NOT choose a DEC number (two agents would pick the same one).
- Public ledger: write a per-entry file `public-ledger/{{DATE}}-{{SLUG}}-guide.md`, NOT the shared
  daily `public-ledger/{{DATE}}.md`.
- Do NOT tick the Progress list in this doc, and do NOT commit a regenerated
  `growing_guides/archive_links.json` (both are shared-edit conflict points; your guide's curated
  `further_reading` carries it until close-out).
- Keep species-specific tests out of the shared file where you can: the generic `FaqBodyOverlapTests`
  already guards FAQ overlap for every guide, so you rarely need to edit
  `tests/test_species_state_pages.py`; if you do add bespoke assertions, a new
  `tests/test_guide_{{SLUG}}.py` will not collide with other branches.
These artifacts are uniquely named, so any number of guide branches merge cleanly.

### Close-out (ONE serialized step, AFTER the batch has merged)
Run once for the whole batch (Benedict, or a single coordinating session):
- `python3 tools/fold_pending_decisions.py` folds every `decisions/pending/*.md` into the log with
  fresh sequential DEC numbers and deletes the fragments (use `--dry-run` to preview).
- `python3 tools/scrapers/build_archive_index.py` regenerates the archive index once.
- Tick the Progress list below for the species that landed.

Definition of done: a guide as thorough and accurate as olive.json, each state genuinely unique,
first-party archives preferenced (RFC archives > WANATCA > RFCWA), every URL resolving, no dashes,
FAQs all net-new (the overlap guard is green, no FAQ recaps a body section), the Water-and-feeding
section meets the step-3b depth checklist with cited fertiliser specifics, goldens regenerated if the
species is in the fixture, full test suite green, PR open.
```

## Priority order (data-driven)

Ranked by Google Search Console clicks (28 days to 2026-06-02, 2,302 page rows), with Plausible
views (30d, supplementary) and archive depth. Aggregated per species across its `buy-*-trees-*` and
`/species/*` pages. `topState` is the highest-impressions state (a hint for flagship, not gospel;
weigh clicks + climate too).

| Species | GSC clicks | GSC impr | PL views | topState | Archive depth |
|---------|-----------:|---------:|---------:|----------|---------------|
| olive (done) | 37 | 2187 | 95 | VIC | done |
| fig | 17 | 954 | 53 | QLD | RFCA + WANATCA |
| lychee | 13 | 547 | 28 | WA | RFCA rich |
| tamarillo | 13 | 318 | 40 | WA | thin (confirm slug) |
| plum | 12 | 507 | 31 | WA | web / WANATCA |
| guava | 11 | 655 | 33 | WA | RFCA rich |
| peach | 9 | 483 | 20 | WA | web |
| sapodilla | 9 | 198 | 27 | species pg | RFCA rich |
| mango | 8 | 634 | 24 | WA (real: QLD) | RFCA very rich |
| avocado | 8 | 589 | 40 | NSW | RFCA rich |
| mandarin | 8 | 546 | 28 | WA | web / citrus |
| lime | 7 | 522 | 20 | NSW | web / citrus |
| apple | 7 | 419 | 33 | WA | web / WANATCA |
| longan | 7 | 229 | 17 | WA | RFCA rich |
| wax-jambu | 7 | 169 | 19 | WA | RFCA |
| orange | 6 | 308 | 16 | WA | web / citrus |

Tail (1 to 5 clicks, still worth doing): nectarine, rambutan, mulberry, cherry, lemon, finger-lime,
apricot, pecan, custard-apple, banana, dragon-fruit, papaya, macadamia, grape, pear, jackfruit,
pomegranate, passionfruit, feijoa, jaboticaba. Indexed but ~0 clicks yet: blueberry, jujube,
black-sapote, loquat, starfruit, rollinia, miracle-fruit. (50 species have some traffic.)

### Suggested run order (traffic x archive depth)

1. fig
2. lychee, guava, mango, avocado, sapodilla  (high traffic AND RFCA-rich; the rare-fruit moat)
3. longan, custard-apple, jaboticaba, dragon-fruit, jackfruit, papaya, banana  (RFCA-rich)
4. plum, peach, mandarin, lime, apple, lemon, orange  (high traffic, temperate/citrus, lean on
   .gov.au + WANATCA + web rather than RFCA)
5. everything else, working down the clicks column

## Progress

- [x] olive (DEC-126 per-state guide; DEC-127 archive citations + Further reading)
- [x] fig (per-state guide; flagship WA on climate, QLD highest impressions)
- [x] lychee (DEC-128, flagship QLD by climate, WA strongest overlay)
- [x] guava (QLD flagship)
- [x] mango (QLD flagship)
- [x] peach (temperate, reuses the existing chill note; no RFCA Further reading)
- [x] plum (WA flagship)
- [x] tamarillo (DEC-129, NSW flagship, frost-tender subtropical)
- All eight above were retrofitted to the step-3a FAQ rule + step-3b feeding depth in the
  guide-rollout-v2 PR (the FAQ-overlap guard was added in the same change).
- [x] avocado (DEC-132)
- [x] sapodilla (DEC-140, QLD flagship)
- [x] longan (DEC-138, QLD flagship)
- [x] custard-apple (DEC-134, QLD flagship, atemoya-led)
- [x] jaboticaba (DEC-136, subtropical, own climate category)
- [x] dragon-fruit (DEC-135, QLD flagship)
- [x] papaya (DEC-139, QLD flagship)
- [x] jackfruit (DEC-137, QLD flagship)
- [x] banana (DEC-133, QLD flagship, biosecurity-accurate, own climate category)
- The nine above shipped as a parallel batch, all merged 2026-06-04 (PRs #37 to #45).
- [x] apple (DEC-141, WA flagship, Pink Lady plus codling-moth-free WA story; golden fixture regenerated)
- [x] lemon (DEC-142, citrus)
- [x] lime (DEC-143, NSW flagship, citrus, warmer overlays than orange)
- [x] mandarin (DEC-144, QLD flagship, citrus, all four states live)
- [x] orange (DEC-145, NSW flagship, first citrus guide; mixed-genus RFCA Citrus folder hand-curated)
- The five above (the citrus quartet plus apple) shipped as a parallel batch, all merged 2026-06-04 (PRs #47 to #51).
- [x] apricot (DEC-146, WA flagship, self-fertile and summer-pruning correctness pinned)
- [x] cherry (DEC-147, NSW/VIC flagship, its own high-chill climate category)
- [x] finger-lime (DEC-148, native rainforest citrus, archives-first)
- [x] mulberry (DEC-149, WA flagship, its own climate-flexible category)
- [x] nectarine (DEC-150, VIC flagship, smooth-skin stone-fruit agronomy)
- [x] pear (DEC-151, VIC flagship, the pick-firm-ripen-off-tree pome story)
- [x] rambutan (DEC-152, archives-first, pollination story corrected)
- [x] wax-jambu (DEC-153, QLD flagship, standout WA overlay)
- [x] feijoa (WA flagship, its own cool-climate category: cold-hardy and chill-needing, not frost-tender subtropical; DEC assigned at fold)
- The eight above shipped as a parallel batch, all merged 2026-06-05 (PRs #53 to #60). cherry and
  mulberry each added their own climate category to build_species_state_pages.py; pear and apricot
  were normalised to the pending-fragment convention at merge (they had edited decision-log.md directly).
- [ ] (continue down the priority order)

## Notes

- The GSC ranking is authoritative (full 2,302 rows). Plausible hit its 1,000-page return cap, so
  its view counts are supplementary.
- `topState` is by impressions; the real flagship can differ (mango's is QLD on climate even though
  WA shows impressions; olive's was WA even though VIC shows most impressions).
- Some species (sapodilla, rambutan, white-sapote) earn traffic mainly on the `/species/` page (few
  or no state combo pages because of low stock); a guide still benefits the species page.
- Confirm tamarillo is in `fruit_species.json` before attempting it (it may not have a slug yet).
- RFCA = rfcarchives.org.au (owned), WANATCA = wanatca.org.au (owned), RFCWA = rarefruitclub.au
  (third-party, nofollow). Re-run `build_archive_index.py` after the RFCA mirror changes.
