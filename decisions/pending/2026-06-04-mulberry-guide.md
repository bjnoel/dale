# Mulberry per-state growing guide on treestock (WA flagship), with its own climate category

**Decided by:** Dale (parallel guide run)

**Context:** Mulberry is on the species-guide rollout tail (docs/species-guide-rollout.md). It is a
pan-Australian backyard tree, so unlike mango (QLD) or olive (WA) there is no single climate-dominant
state. GSC and Plausible have no local credentials in the worktree, so flagship choice fell to climate
plus audience. Mulberry was also mis-filed under the "subtropical" climate category, whose Victorian
note wrongly implied it is frost-tender and that nurseries will not post to VIC, the opposite of the
truth for a tree hardy to well below freezing.

**Decision:** Ship a cited, per-state mulberry guide (tools/scrapers/growing_guides/mulberry.json)
matching the olive implementation, flagship WA (treestock's WA community plus the WA-all-species rule,
with every state given a genuine, unique overlay). Give mulberry its OWN climate category ("mulberry")
in build_species_state_pages.py with accurate, dash-free per-state notes, rather than letting it inherit
the misleading "subtropical" note (the same pattern banana and jaboticaba already use).

**Why:** Correctness is the rollout's first rule. The subtropical note actively misled Victorian
growers. The new guide gets the facts straight: mulberries are wind pollinated and self-fertile (one
tree crops, no pollinator), need no winter chill, are very frost and drought hardy, and their one real
pest is birds (netting, not sprays), with Queensland fruit fly only a secondary host. Varieties are tied
to live stock (Black English, Hicks Fancy, Beenleigh Black, Lena, dwarf black, White Shahtoot, White).

**Actions:**
- New growing_guides/mulberry.json: 10 sources (CRFG, Daleys x3, Business Queensland fruit fly, My
  Smart Garden, DPIRD medfly, DPIRD import quarantine, RFCA Shahtoot, RFCA "Making use of the mulberry"),
  shared core + WA/QLD/NSW/VIC overlays, RFCA-only Further reading (no WANATCA article exists for mulberry).
- build_species_state_pages.py: added SPECIES_CLIMATE_CATEGORY["mulberry"] = "mulberry" and matching
  STATE_CLIMATE_NOTES for all four states.
- New tests/test_guide_mulberry.py (21 tests): per-state uniqueness and no region-token leaks, no dashes,
  FAQ JSON-LD, Sources, RFCA Further reading followed, dedicated climate category, the VIC-not-marginal
  fix, and correctness guards (one-tree pollination, birds as the main pest).

**Status:** PR open (branch dale/mulberry-guide), pending Benedict review. Full suite green (628 tests);
all cited and further-reading URLs return HTTP 200; worst FAQ/section overlap 0.17 (limit 0.45). With
current stock only the WA combo page generates (mulberry is just outside the top-20 cap for QLD/NSW/VIC);
the other overlays are validated by tests and appear as stock grows. Per the parallel-batch protocol,
this branch does not edit decision-log.md, the shared daily ledger, the rollout Progress list, or
archive_links.json; those are folded at batch close-out.

**To revert:** delete growing_guides/mulberry.json (the builders fall back to the generic blurb via
has_guide()), revert the SPECIES_CLIMATE_CATEGORY / STATE_CLIMATE_NOTES change, and delete
tests/test_guide_mulberry.py.
