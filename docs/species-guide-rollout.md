# Species growing-guide rollout

Plan for building a comprehensive, per-state, cited growing guide for every tracked species on
treestock.com.au, one species per fresh Claude Code session. Olive shipped first (DEC-126 / DEC-127)
as the reference implementation; this doc tracks the rest.

How it works:
- The content layer is `tools/scrapers/growing_guides/<slug>.json` (state-invariant `core` plus
  per-state overlays), rendered by `growing_guides.py` into the combo and species pages. See the
  `project_growing_guides` and `reference_owned_content_archives` memories, and `olive.json` as the
  gold standard.
- Run the prompt below in a fresh session, changing only the species, and work down the priority
  order. Each run opens a PR; merge + deploy stays a human gate.
- Re-check traffic periodically (the priority order is a snapshot, not fixed).

## The prompt (substitute one line per run)

```text
SPECIES = mango        # <-- change ONLY this line each run (use the common name as in fruit_species.json)

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
  - `tools/scrapers/growing_guides.py`  (has_guide, render_combo_guide, render_further_reading merge)
  - `tools/scrapers/build_species_state_pages.py`  (core/overlay, SPECIES_CLIMATE_CATEGORY, STATE_CLIMATE_NOTES)
  - `tools/scrapers/build_species_pages.py`, `tools/scrapers/build_archive_index.py`
  - `tests/test_species_state_pages.py`  (the bar to keep green)
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
  planting & soil, water & feeding, harvest, post-harvest/ripening or eating, buying tips.
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

## 4. Refresh the RFCA index + climate category
- Run `python3 tools/scrapers/build_archive_index.py`; confirm {{SLUG}} now has entries in
  `growing_guides/archive_links.json`. Its printed "WANATCA candidates" are your curation shortlist
  for step 3's further_reading.
- If {{SPECIES}} has special climate needs (as olive/grape use "mediterranean"), add/adjust its entry
  in `SPECIES_CLIMATE_CATEGORY` and the matching `STATE_CLIMATE_NOTES` per state (no dashes).

## 5. Test + build locally
- Keep `python3 -m unittest discover tests/` green (extend tests if the species needs it; reuse the
  uniqueness / no-dash / FAQ-JSON-LD / sources / further-reading guards).
- Build against real stock into a tmp dir and open the {{SLUG}} pages: per-state-unique, cited,
  dash-free, with FAQ JSON-LD, article OG, Sources, and Further reading (RFCA merged + curated).
  Confirm /species/{{SLUG}}.html. curl every cited + further-reading URL -> 200.

## 6. Ship (do NOT merge unilaterally)
- You are already in the `dale/{{SLUG}}-guide` worktree from step 0. Commit; push; open a PR. Ask
  Benedict to review; on his go-ahead, merge + deploy: ssh dale-server, `git pull`,
  `tools/deploy.sh`, run `build_species_state_pages.py` + `build_species_pages.py` into
  /opt/dale/dashboard, rebuild purged Tailwind, verify live (200, fresh mtime, dash-free,
  per-state-unique). NEVER scp.
- Log a DEC entry and a public-ledger note.

Definition of done: a guide as thorough and accurate as olive.json, each state genuinely unique,
first-party archives preferenced (RFC archives > WANATCA > RFCWA), every URL resolving, no dashes,
full test suite green, PR open.
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
- [ ] fig
- [ ] lychee
- [ ] guava
- [ ] mango
- [ ] avocado
- [ ] sapodilla
- [ ] longan
- [ ] custard-apple
- [ ] jaboticaba
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
