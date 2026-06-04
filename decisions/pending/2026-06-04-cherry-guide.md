# Cherry growing guide (per-state-unique, NSW/VIC flagship; its own high-chill climate category)

**Decided by:** Dale (parallel guide run)

**Context:** Continuing the per-species growing-guide rollout (olive DEC-126 flagship, the archive
integration DEC-127, and the batches through DEC-145), cherry (Prunus avium, the sweet cherry) is the
next species down the docs/species-guide-rollout.md priority order to get a rich, per-state-unique,
cited growing guide on the buy-cherry-trees-[state] combo pages and /species/cherry.html. Cherry is
the most chill-demanding of the common stone fruits, which makes the generic content actively wrong
for it, so this guide is as much a correctness fix as an SEO and funnel play.

**Decision:** Add `tools/scrapers/growing_guides/cherry.json` (33 sources, a state-invariant core of
nine sections, four genuinely distinct state overlays, four core and eight state FAQs, and one curated
owned WANATCA "Further reading" article) plus `tests/test_guide_cherry.py`. One builder change was
needed: cherry was previously mapped to the `temperate` climate category, whose note tells growers to
"choose low-chill varieties". That is wrong for cherry (there are few low-chill cherries, and most of
WA and almost all of QLD cannot supply the chill at all), so cherry now has its OWN
`SPECIES_CLIMATE_CATEGORY` ("cherry") and four `STATE_CLIMATE_NOTES` entries that tell the true
cold-climate story, mirroring the banana precedent.

Flagship is the eastern cold-climate heartland, **New South Wales and Victoria** (researched deepest).
GSC/Plausible produced nothing locally (no creds, no `requests`, as on recent runs), so the flagship
was chosen on production reality and climate. Victoria is the largest producer by tonnage (Cherry
Growers Australia), while NSW's Young is "Australia's Cherry Capital" and hosts the National Cherry
Festival, so both earned first-class overlays (Yarra Valley plus the north-east high country for VIC;
Young, Orange and Batlow for NSW). QLD is an honest Granite-Belt-only overlay, and WA gets the
marginal-climate plus quarantine story the local audience needs.

**Why:** Each combo page used to share a byte-identical generic blurb. The guide makes WA/QLD/NSW/VIC
genuinely different and cited, and it corrects the chill-hours story for the single hardest backyard
stone fruit, so it is the kind of page a serious grower trusts (and a Treesmith funnel entry).

**Actions:**
- `growing_guides/cherry.json` + `tests/test_guide_cherry.py` (mirrors the olive/peach/apple guards
  plus cherry-specific correctness guards). One-line climate-category change in
  `build_species_state_pages.py` (cherry -> its own category, four new dash-free state notes). Full
  suite green (638 tests). All 33 cited and further-reading URLs return HTTP 200 under a browser UA.
- Only the WA combo page renders live now (cherry is below the QLD/NSW/VIC top-20 in-stock cut this
  month, as bare-rooted cherry stock is largely out of season); the species page plus all four
  overlays are authored and verified by force-building, and the eastern overlays light up when winter
  stock climbs (the tamarillo/jackfruit "judge done on the species page" rule).
- `archive_links.json` NOT changed: there is no RFCA Cherry folder (cherry is not a rare fruit, like
  apple), so the index regenerates byte-identical and the only owned Further reading is the WANATCA
  Yearbook 21 article "The True Cherries: Description of Species" (Crawford), hand-curated because the
  auto-matcher misses it ("cherry" is not a substring of the index's "cherries").
- Correctness calls the research corrected, each pinned by a test so a future edit cannot reintroduce
  them: (1) the low-chill Royal series (Minnie Royal, Royal Lee, Royal Crimson) is **Californian
  (Zaiger), not UC-Davis**, and Minnie Royal and Royal Lee **must cross-pollinate each other**;
  (2) cherries are **non-climacteric** (do not ripen after picking); (3) **prune in summer**, not
  winter, to avoid silver leaf and bacterial canker; (4) in WA the fly to manage is **Medfly**, and
  WA has **no established Queensland fruit fly** (declared/eradicated on detection), the opposite of
  the eastern states.
- Sourcing under the curl-200 gate: NSW DPI (dpi.nsw.gov.au) and Agriculture Victoria
  (agriculture.vic.gov.au) 403 to automated fetchers, so they are NOT cited (a test guards this);
  eastern claims are anchored on Cherry Growers Australia, the National Cherry Festival, Batlow,
  CherryHill Orchards, Queensland Country Life, Business Queensland and WSU/OSU/UC IPM/RHS, with DPIRD
  WA for the WA pest and quarantine facts.

**Status:** PR open, pending Benedict review. Not yet merged or deployed.

**To revert:** delete `growing_guides/cherry.json` and `tests/test_guide_cherry.py`, and restore
cherry to the `temperate` category in `build_species_state_pages.py` (removing the four `cherry`
climate notes). `has_guide("cherry")` then returns False and the pages fall back to the generic blurb.
