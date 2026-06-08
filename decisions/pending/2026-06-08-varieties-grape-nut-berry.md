# Variety descriptions rollout: grape, raspberry, pecan, jujube, wax-jambu, grumichama (macadamia deferred)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-grape-nut-berry)
**Context:** Continuing the per-variety "what's unique" blurb layer (DEC-178) to more of the
stock-ranked tail. This window owned seven species: grape, raspberry, macadamia, pecan, jujube,
wax-jambu, grumichama. Research was fanned out to non-overlapping subagents (>=2 reputable sources
each, >=1 non-nursery, skip-if-thin, no guessing), then assembled per-species with claim types
normalised so any specific figure (Brix, percent kernel) keeps an authoritative/owned source.

**Decision:** Added 39 new verified variety blurbs across six species and recorded 18 thin-source or
noise skips. grumichama is complete (0 remaining). macadamia was deferred (its research subagent hit
the account session limit before returning), so macadamia has 0 added this run and stays fully
remaining for a follow-up pass in the same window.

Per-species result (described / skipped / remaining of live ranked slugs):
- jujube: 13 added (joins the pilot's jujube-li, 14 described total), 4 skipped, 14 remaining.
- grape: 11 added, 4 skipped, 35 remaining.
- raspberry: 7 added, 4 skipped, 8 remaining.
- pecan: 2 added (Wichita, Pawnee), 2 skipped, 14 remaining.
- wax-jambu: 4 added (colour forms pink/red/purple/white), 2 skipped, 1 remaining.
- grumichama: 2 added (black, yellow), 2 skipped, 0 remaining (DONE).
- macadamia: 0 added (deferred), 28 remaining.

**Why:** Accuracy over coverage. Grape, raspberry, pecan and the documented colour-forms verified
cleanly against authoritative sources (USDA-ARS, Plantgrape/IFV-INRAE, OSU/Cornell extension, US Plant
Patents, NMSU, Morton/Purdue, UF-IFAS). Jujube leaned on the NMSU Jujube Project (authoritative) plus
Trees and Shrubs Online and the NT DAF. Thin entries (nursery-only or contradictory sources) were
skipped, not guessed: jujube-hulu; raspberry-golden-glitz and raspberry-rocket (nursery-only
trademarks); grumichama-orange (no non-nursery source separates it from the yellow leucocarpa form).
Noise/dupe listing slugs (rootstock, ivy houseplant mis-parses, "potted" relistings, common-name
synonyms) were also skipped so re-runs do not re-attempt them.

**Actions:**
- Wrote tools/scrapers/variety_descriptions/{jujube,grape,raspberry,pecan,wax-jambu,grumichama}.json
  (varieties map + a per-species skipped array of slug strings).
- `python3 -m unittest discover tests/` green (1401 tests). No golden regen needed (none of these are
  golden-fixture species).
- Spot-checked one authoritative source per agent (NMSU jujube/pecan, USDA-ARS grape, Plantgrape,
  OSU PNW655, Morton/Purdue, growables) for existence and content.

**Status:** Shipped as PR for serialized close-out (fold this fragment, tick the rollout Progress list,
single deploy via build_variety_pages.py + purge_cloudflare.sh). Not deployed from this branch.

**To revert:** delete the six JSON files (or the specific entries); the renderer falls back to no blurb.
