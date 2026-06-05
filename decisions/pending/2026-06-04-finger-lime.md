# Finger lime growing guide: Australia's native rainforest citrus, archives-first

**Decided by:** Dale (parallel guide run)

**Context:** The species-guide rollout (docs/species-guide-rollout.md) continues down the
priority tail. Finger lime (Citrus australasica, formerly Microcitrus australasica) is the
native Australian "caviar lime" and a genuine four-state crop, with 48 products in stock across
six tracked nurseries, so all four buy-finger-lime-trees-[state] combo pages generate live plus
/species/finger-lime.html. It is a true rare-fruit species, so unlike the common citrus it is rich
in Benedict's owned archives.

**Decision:** Ship a per-state finger lime guide (tools/scrapers/growing_guides/finger-lime.json +
tests/test_guide_finger_lime.py), one JSON file, no code change. Flagship NSW (the Big Scrub /
Northern Rivers native heartland and the source of most named cultivars); QLD a co-heartland (SE
Queensland border ranges, Scenic Rim, the long-running Bellthorpe orchard); WA defined by citrus
biosecurity (and finger lime is the native host of citrus gall wasp, established in Perth since
2013); VIC the cold-limit pot crop with one distinctive hook, the CSIRO native-lime breeding at
Merbein. Kept the shared `citrus` climate category (the note is accurate; finger-lime nuances live
in the overlays), so no SPECIES_CLIMATE_CATEGORY change.

**Why:** Replaces the byte-identical generic blurb with scannable, cited, genuinely per-state advice,
and corrects several facts a generic citrus blurb gets wrong. Archives-first: built on the Rare Fruit
Council "Edible Native Fruits, Wild Lime" article (the rainforest limes plus CSIRO's Sykes breeding)
and the WANATCA ACOTANC citrus paper, cross-checked against CSIRO, AgriFutures, DPIRD WA, Business
Queensland, the Australian National Botanic Gardens, peer-reviewed research, and Sustainable
Gardening Australia.

**Actions:**
- Authored growing_guides/finger-lime.json (21 sources, 7 core sections + 4 per-state overlays,
  net-new FAQs, hand-curated owned Further reading). No clean RFCA folder exists for finger lime
  (its content sits in the mixed-genus AusNative/Citrus folders, which never auto-map), so
  archive_links.json is unchanged and Further reading is hand-curated, the citrus-batch pattern.
- Added tests/test_guide_finger_lime.py (per-state uniqueness + no-dash + FAQ JSON-LD + cited-https
  sources + Further-reading guards, plus correctness guards: finger lime is a poor/non-host for
  fruit fly; Blood Lime is an acid-mandarin x finger-lime cross, not Rangpur, and the Outback Lime
  is a Desert Lime selection; WA is not free of citrus gall wasp).
- Verified: full suite green (627 tests, FAQ-overlap max 0.30); all four combo pages + the species
  page built from real stock, per-state-unique, no region-token leaks, dash-free; all 23 cited and
  further-reading URLs return HTTP 200.

**Correctness calls worth keeping:**
- Finger lime fruit is a very poor host for Mediterranean fruit fly and a recorded non-host for
  Queensland fruit fly (Follett et al. 2022), the opposite of most citrus, so the guide does NOT
  copy the olive/lime "fruit fly stings citrus" line; it frames the poor-host status as an advantage.
- Finger lime is the native host of the citrus gall wasp (DPIRD factsheet), the headline pest, and
  WA is NOT free of it (established in Perth, not yet in WA commercial orchards).
- Blood Lime (Red Centre Lime) = acid mandarin x red finger lime (CSIRO), NOT finger-lime x Rangpur;
  Sunrise Lime is a Faustrimedin selection and Outback Lime is a Desert Lime selection, neither a
  finger lime cross.
- Seedlings are slow and variable and can take many years (up to about 15) to fruit; grafted plants
  fruit in two to three years true to type (corrects the fruit_species.json "5 to 7 years" in-guide,
  the species file left untouched).

**Status:** PR open, pending Benedict review. Not merged.

**To revert:** delete tools/scrapers/growing_guides/finger-lime.json and
tests/test_guide_finger_lime.py; both builders fall back to the generic blurb automatically
(has_guide returns False). No code or schema change to undo.
