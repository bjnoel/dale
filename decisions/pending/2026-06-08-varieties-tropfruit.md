# Variety descriptions: tropical six (dragon fruit, passionfruit, guava, banana, starfruit, sapodilla)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-tropfruit)
**Context:** Continuing the per-variety "what's unique" blurb rollout (DEC-178) on treestock
`/variety/<slug>.html` pages. This window owns six tropical/subtropical species:
dragon-fruit, passionfruit, guava, banana, starfruit, sapodilla. REMAINING was computed from
live server stock minus each species file's existing `varieties` and `skipped`.
**Decision:** Researched the top demand-ranked, verifiable cultivars per species via fan-out
subagents (>=2 reputable sources each, >=1 non-nursery; skip on thin sources, never guess), then
committed verified blurbs into each species' `variety_descriptions/<species>.json` (`varieties`
plus a per-species `skipped` array). 43 varieties added, 21 skipped this run.

**Added (43):**
- banana (8): red-dacca, ducasse, blue-java, gold-finger, pisang-ceylon, horn-plantain,
  ambul-kesel, dwarf-duccase-sugar-banana
- dragon-fruit (9): yellow, american-beauty, dark-star, delight, purple-haze, vietnamese-white,
  sugar-dragon, red, white
- guava (9): hawaiian, mexican-cream, strawberry, thai-white, red-cherry, yellow-cherry,
  egyptian-long-neck, hawaiian-pink, china-pear
- passionfruit (11): black, panama-red, panama-gold, nellie-kelly, sweetheart, misty-gem, pandora,
  sweet-granadilla, giant-granadilla, banana, sweet-calabash
- sapodilla (3): krasuey, ponderosa, sawo-manilla
- starfruit (3): fwang-tung, arkin, kary

**Skipped (21):** thin/conflicting sources or parser noise. Notable: dragon-fruit aztec-gem and
aussie-gold (nursery-only, conflicting species/origin), dragon-fruit cosmic-charlie (nursery-only,
conflicting pollination), passionfruit flamenco (one non-nursery source, generic), guava thai-pink
(only nursery confirms a distinct cultivar) and guava pineapple (name usually means feijoa, a
different genus), starfruit thai-knight and giant-siam (named only in NT DAF Agnote, no descriptive
detail), plus banana parser noise (passionfruit, ken-mango-tree, pitanga, stock-4-pack, fruit-cover)
and duplicate-spelling banana pages (tree-blue-java, tree-goldfinger, goldfinger, tree-musa-nathan,
horned-plantain), and banana nathan / super-cavendish (Cavendish selections, nursery-only sourcing).

**Why:** Accuracy over coverage. Each blurb clears the test gate (>=2 sources, >=1 non-nursery,
confidence >= 0.80, specific figures need authoritative/owned backing). Sapodilla measurements rest
on the RFCA archive (owned tier, Benedict-owned); starfruit on UF/IFAS (authoritative).
**Actions:** Wrote/extended banana, dragon-fruit, guava, passionfruit, sapodilla, starfruit JSON.
`python3 -m unittest discover tests/` green (1401 tests). No golden change (new banana varieties are
not in the golden fixture pages).
**Status:** sapodilla and starfruit are DONE (0 remaining). banana, dragon-fruit, guava and
passionfruit have a verified tail remaining for a later pass (re-run the same command in this window).
**To revert:** remove the added entries (and this run's skip slugs) from the six species JSON files.
