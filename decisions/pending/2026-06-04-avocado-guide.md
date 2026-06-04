# treestock avocado per-state growing guide (Track B)

**Decided by:** Dale (parallel guide run)

**Context:** Avocado is next in the growing-guide rollout (docs/species-guide-rollout.md): 8 GSC
clicks and 589 impressions in 28 days, RFCA-rich, and a genuine commercial crop in every mainland
state. Its buy-avocado-trees-<state> combo pages and /species/avocado.html previously shared a
generic, uncited fruit_species.json blurb.

**Decision:** Ship a comprehensive, cited, per-state avocado growing guide as a single JSON file
(tools/scrapers/growing_guides/avocado.json), matching the olive and guava gold standard and the
rollout-v2 bar (net-new FAQs, deep cited water-and-feeding, hand-escaped inline HTML, no dashes).

**Why:**
- Avocado is unusual in being a real crop in all four generated states (WA Southern Forests around
  Pemberton and Manjimup; QLD Bundaberg and Childers plus the Atherton Tableland; NSW Northern
  Rivers and the Mid North Coast Comboyne plateau; VIC Sunraysia around Mildura), so each state
  earns a genuinely distinct overlay rather than a token one. The GSC traffic leader is NSW, QLD is
  the production heartland, and WA carries the distinctive quarantine and shipping angle. All four
  were researched deeply.
- Correctness focus: drainage and Phytophthora root rot, Type A and Type B flowering and
  cross-pollination, dry-matter maturity (Hass 23 percent, Shepard 21 percent, fruit ripens off the
  tree), salinity sensitivity, and cited feeding (nitrogen and potassium dominant, about 110 kg N
  and 80 kg K per hectare for a mature Hass, little-and-often for the shallow feeder roots, plus
  zinc, boron and iron). Research fanned out to three subagents, key claims adversarially
  cross-checked, and every cited URL verified HTTP 200.

**Actions:**
- New: tools/scrapers/growing_guides/avocado.json (37 sources, all cited and 200-verified; core plus
  WA, QLD, NSW and VIC overlays; 5 core plus 2-per-state net-new FAQs).
- New: tests/test_guide_avocado.py (uniqueness, no-dash, region-leak, FAQ JSON-LD, sources,
  further-reading, and avocado-specific A/B plus Phytophthora correctness guards).
- Regenerated goldens: species/avocado.html and buy-avocado-trees-western-australia.html (avocado is
  in tests/golden/fixture/; the diff was confirmed to be only the two avocado pages).
- No SPECIES_CLIMATE_CATEGORY change (avocado is already "subtropical"); archive_links.json was NOT
  regenerated (avocado already has its 4 RFCA entries, which auto-merge into Further reading).
- First-party archives preferenced: RFCA (auto-merged) plus WANATCA (Whiley, Yearbook Vol 8)
  followed; rarefruitclub.au third-party (nofollow).

**Status:** PR open on branch dale/avocado-guide, pending Benedict review. Full suite green (372 tests).

**To revert:** delete avocado.json and test_guide_avocado.py and restore the two golden files; the
pages fall back to the generic fruit_species.json blurb automatically (has_guide returns False).
