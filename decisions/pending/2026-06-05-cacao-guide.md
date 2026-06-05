# Cacao per-state growing guide (flagship Queensland, climate-restricted to the wet tropics)

**Decided by:** Dale (parallel guide run)

**Context:** Continuing the per-species growing-guide rollout on treestock.com.au (olive infrastructure, DEC-126/127). Cacao (Theobroma cacao, slug `cacao`) is the most climate-restricted species in the set: a true equatorial rainforest tree that needs constant warmth and humidity, no frost and no long dry season, so in Australia it crops only on the wet tropical coast of far north Queensland.

**Decision:** Shipped `tools/scrapers/growing_guides/cacao.json` plus a dedicated `"cacao"` climate category, mirroring the olive and rambutan schema. Flagship Queensland by climate; the WA, NSW and VIC overlays cover a glasshouse curiosity rather than a crop, with the WA overlay built on the real, discontinued Broome and Kununurra field trials.

**Flagship rationale:** The traffic tools (GSC, Plausible) need server credentials and were not runnable locally, and no `buy-cacao-trees-*` combo page currently generates (only Daleys ships cacao to WA, so one product; QLD, NSW and VIC each have four available but cacao falls outside the per-state top 20). So `/species/cacao.html` is the live surface today, and climate makes Queensland the unambiguous flagship (the eight-year RIRDC/NACDA research found the far north Queensland sites the only viable ones, with the WA and NT trials poor or sub-economic).

**Research (archives-first, adversarially verified):**
- Owned first-party: Rare Fruit Council of Australia Cacao folder (the Processing Cocoa fermentation article cited inline; the Cacao hub and Cupuassu pages auto-merge into Further reading), and the WANATCA Quandong Vol 33 No 4 (2007) cacao issue (curated Further reading).
- Authoritative third parties (rendered nofollow): RIRDC 09/092 "Producing Cocoa in Northern Australia" (Diczbalis et al. 2010, the spine), the Northern Territory Government home-grower guide, Business Queensland (cocoa pod borer), AgriFutures, the International Cocoa Organisation, and the US National Park Service (chocolate midge). The Rare Fruit Club WA page is cited as third-party (nofollow) for the WA detail.
- Correctness pinned and cross-checked: cauliflory plus midge (Ceratopogonidae, Forcipomyia) pollination with only 1 to 5 percent fruit set; pods ripen 5 to 6 months after flowering; the beans have no chocolate flavour until fermented; Australia is free of witches broom, frosty pod and swollen shoot, and eradicated the cocoa pod borer (found in far north Queensland in 2011, gone by 2014); the WA Broome and Kununurra trials were discontinued; varieties tie to live stock (SG2, Trinitario, seedlings), with mocambo (Theobroma bicolor) and cupuassu (Theobroma grandiflorum) flagged as relatives, not true cacao.

**Actions:**
- `tools/scrapers/growing_guides/cacao.json`: 16 sources, a 7-section + 4-FAQ core, four genuinely distinct state overlays, and a curated WANATCA further_reading entry.
- `tools/scrapers/build_species_state_pages.py`: added `"cacao"` to `SPECIES_CLIMATE_CATEGORY` and a per-state `"cacao"` entry to `STATE_CLIMATE_NOTES` for WA, QLD, NSW and VIC.
- `tests/test_guide_cacao.py`: 22 cacao-specific guards (cauliflory, midge-not-bee pollination, fermentation, QLD viability and disease-freedom, WA discontinued trials, cool-state cross-links, region-token uniqueness).
- Full suite green (1127 tests). All 16 cited and further-reading URLs verified live (HTTP 200). No em or en dashes.

**Status:** PR open for Benedict's review. Not merged. The committed `archive_links.json` already contained cacao's RFCA links, so no regeneration was needed.

**To revert:** delete `growing_guides/cacao.json` and `tests/test_guide_cacao.py`, and remove the `"cacao"` entries from `SPECIES_CLIMATE_CATEGORY` and the four `STATE_CLIMATE_NOTES`. `has_guide("cacao")` then returns False and the page falls back to the generic blurb.
