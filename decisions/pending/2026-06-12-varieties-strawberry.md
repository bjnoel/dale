# Variety descriptions: strawberry (new species file, 10 blurbs)

**Decided by:** Dale (parallel variety-descriptions run)
**Context:** treestock had no `/variety` blurbs for any strawberry (Fragaria) cultivar. The live
catalogue carries 31 strawberry variety slugs. Following `docs/variety-descriptions-rollout.md`,
this run created the first `variety_descriptions/strawberry.json`.

**Decision:** Add verified "what's unique" blurbs for 10 strawberry cultivars and record 21 skips.

**Added (10):** chandler, delliz, fresca, loran, red-gauntlet, summer-breeze-rose,
summer-breeze-snow, sweetheart, tioga, alpine. Each clears the gate (>=2 sources, >=1 independent
non-nursery, confidence_score >=0.80, every claim cited). Authoritative anchors include RHS,
Kew, UC Davis / California Agriculture, NIAB East Malling, All-America Selections, PanAmerican Seed
and ABZ Seeds.

**Skipped (21):**
- 2 mis-parses: `strawberry-tree`, `strawberry-canary-island` are Arbutus (strawberry tree), not Fragaria.
- 5 packaging-format duplicates of base cultivars: the `-mega-tube` slugs (melba, adina, tioga,
  red-gauntlet) and `adina-organic-fruit-plant-runner` are pack formats, not distinct varieties.
- 14 thin-source: irish, melba-pbr, red-cascade-sh-pbr, toolangi-choice, beltran, running-white,
  running-red, handstand, pinkie, berrylicious, roman-pink, ruby-red, sweetie, adina. Each had
  fewer than 2 reputable non-nursery sources. Melba PBR and Adina are real Australian varieties but
  appear only in retailer/seed listings (no breeder/PBR/extension reference), so they were skipped
  rather than ship a blurb resting on marketing copy.

**Why:** Accuracy over coverage. A fabricated cultivar fact is worse than no blurb. Skips are
recorded in the file's `skipped` array so a later strawberry pass never re-attempts them.

**Actions:** Added `tools/scrapers/variety_descriptions/strawberry.json`. Full test suite green
(1605 tests). strawberry is not a golden fixture species, so no golden regen.

**Status:** Shipped via PR (branch `dale/varieties-strawberry`). Deploy happens at the serialized
close-out, not here.

**To revert:** Delete `tools/scrapers/variety_descriptions/strawberry.json`; the variety pages fall
back to no blurb.
