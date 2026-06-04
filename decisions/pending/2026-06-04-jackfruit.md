# Jackfruit per-state growing guide shipped to treestock (flagship QLD)

**Decided by:** Dale (parallel guide run)

**Context:** Per-species growing-guide rollout (see [[project_growing_guides]]). Jackfruit was
next in the tropical/rare-fruit set. It was already mapped as "tropical" in
`SPECIES_CLIMATE_CATEGORY` and already present in `growing_guides/archive_links.json` (the RFCA
"Jakfruit" folder, 8 articles), so it needed only one declarative JSON file plus a test file, no
code change and no archive-index regeneration.

**Decision:** Add `tools/scrapers/growing_guides/jackfruit.json` (state-invariant `core` plus
WA/QLD/NSW/VIC overlays) and `tests/test_guide_jackfruit.py`. Flagship is QLD by climate (the
humid wet tropics are jackfruit's natural home). Per-state framing: QLD = wet tropics and Cassowary
Coast strongholds; WA = the tropical north (Ord/Kununurra, Kimberley, Carnarvon) plus a Perth
pot/glasshouse note, and currently the only combo page that actually generates (WA builds all
3-plus-in-stock combos); NSW = the frost-limited Northern Rivers margin; VIC = not a field crop
(frost kills it, glasshouse only).

**Why:** Each state page is now genuinely unique and cited instead of sharing one generic blurb,
which earns search traffic and community trust, the audience that feeds the Treesmith funnel
(Track B). 22 sources, first-party archives preferenced.

**Actions:**
- 22 cited sources, all verified HTTP 200. First-party owned sources lead: RFCA (cultivation,
  eating qualities, seeds) and WANATCA (Goebel "Jak fruit, what to look for" Yearbook 16; Griffiths
  "Artocarpus" Yearbook 13), all owned and followed in Further reading. Third-party authorities
  (NT Government and NT DAF, UF/IFAS, FSHS, Sub-Tropical Fruit Club Qld, CRFG, Pacific Pests/UQ,
  USDA APHIS, Fruit Fly ID Australia, AgriFutures, DPIRD WA, BOM) cited nofollow.
- Cited feeding figure (rollout v2 rule): UF/IFAS home-garden rate (about 113 g of 6:6:6 with minor
  elements every eight weeks in year one, bearing trees 2 to 3 times with 6:6:6 or 8:3:9) plus the
  NT direction. No invented NPK numbers.
- Adversarial findings locked into the guide and test guards: Queensland fruit fly is NOT a recorded
  pest of jackfruit (APHIS pest list and the B. tryoni host list both omit it; thick rind resists
  it), so unlike the olive/mango guides it is not listed as a pest. Jackfruit is monoecious and
  self-fruitful, so one tree fruits. J33 and NS1 are distinct Malaysian clones (not conflated).
- Did NOT regenerate `archive_links.json` (jackfruit already indexed) and did NOT touch
  `decision-log.md`, the shared daily `public-ledger/2026-06-04.md`, or the Progress checklist, per
  the parallel-run merge convention.

**Status:** PR open on branch `dale/jackfruit-guide`, pending Benedict review, merge and deploy.
Full test suite green (374 tests). Only the WA combo page and `/species/jackfruit.html` generate on
current stock; QLD/NSW/VIC overlays light up when stock crosses the per-state thresholds.

**To revert:** delete `tools/scrapers/growing_guides/jackfruit.json` and
`tests/test_guide_jackfruit.py`. The species falls back to the generic `fruit_species.json` blurb.
