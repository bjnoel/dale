# Lilly pilly gets a cited, per-state growing guide on treestock

**Decided by:** Dale (parallel guide run)

**Context:** treestock's buy-lilly-pilly-trees-<state> combo pages and /species/lilly-pilly.html carried a single generic blurb. Lilly pilly is one of treestock's best-stocked species (Ladybird alone lists 180-plus, with dozens of named cultivars across Syzygium australe, the former Acmena now Syzygium smithii, the bush-food riberry and others) and a high-interest plant that buyers want two ways, as a fast evergreen hedge and for its edible berries. That makes it a strong candidate for the olive-style cited guide layer.

**Decision:** Add tools/scrapers/growing_guides/lilly-pilly.json: a state-invariant core (choosing a variety for hedge or bush food, the all-important psyllid resistance, self-fertile pollination, planting and soil, water and feeding, pruning and hedging, harvest and eating, buying tips) plus four genuinely distinct state overlays. New South Wales is the flagship (the native heartland of the genus, home to the endemic threatened magenta lilly pilly, and the start of the riberry bush-food trade). Give lilly pilly its OWN climate category rather than the generic "subtropical" note. Ship via PR off origin/main for Benedict to review and merge.

**Why:** The generic "subtropical" climate note was wrong for lilly pilly twice over. It implied a frost-tender plant that is marginal in the cool south (lilly pilly is hardy and the default hedge plant across Victoria), and it implied the usual "a handful of eastern nurseries can ship to WA" framing when the truth is the opposite of free: lilly pilly is a myrtle, and WA restricts myrtle-family plants to keep out myrtle rust, so live plants essentially cannot be posted in (the same pattern as banana). Better, trustworthy guides for the exact plants our community grows earn search traffic and trust, the audience that feeds the Treesmith funnel.

**Actions:**
- Authored growing_guides/lilly-pilly.json: 23 sources, an 8-section cited core, four unique state overlays, hand-curated owned "Further reading" (the WANATCA Wilson Yearbook 14 article plus two RFCA articles; there is no RFCA lilly-pilly folder, so archive_links.json is unchanged and the links are curated, as with tamarillo and custard apple).
- Added a dedicated "lilly pilly" entry to SPECIES_CLIMATE_CATEGORY and four town-free per-state notes in STATE_CLIMATE_NOTES in build_species_state_pages.py.
- Added tests/test_guide_lilly_pilly.py (29 tests: per-state uniqueness and region-token leak, no dashes, FAQ JSON-LD, https/noopener/nofollow sources, owned-followed further reading, dedicated climate category, and lilly-pilly correctness guards).
- Researched archives-first (RFCA, WANATCA), then cross-checked and verified every cited claim against state and Commonwealth biosecurity sources (DPIRD WA, Business Queensland, DCCEEW, DBCA), herbaria (VicFlora, ALA), ANPSA, the Australian Plants Society, the Australian Flora Foundation and AgriFutures. Every cited and further-reading URL returns HTTP 200 (browser UA).

**Status:** PR open, pending Benedict review. On merge the species page and the WA combo page go live; with current stock the QLD/NSW/VIC combo pages sit just below the top-20 cut (lilly pilly ranks about 26th in those states), so their overlays are built and tested and switch on automatically as stock climbs. Full suite green (1134 tests).

**To revert:** delete tools/scrapers/growing_guides/lilly-pilly.json (the page falls back to the generic blurb), remove the "lilly pilly" climate-category block and the four lilly-pilly STATE_CLIMATE_NOTES entries in build_species_state_pages.py, and delete tests/test_guide_lilly_pilly.py.
