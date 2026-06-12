# Variety descriptions: berries window (blueberry, raspberry, blackberry) researched to zero remaining

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-berries)

**Context:** The variety-descriptions rollout (DEC-178) covers /variety pages one species per
window. The pilot seeded blueberry (12 entries) and raspberry (7 entries); blackberry had no
file. The live catalogue still carried an unresearched tail for all three.

**Decision:** Research the full remaining live tail for blueberry, raspberry, and blackberry,
adding only multi-source-verified entries and recording everything else in the per-species
skipped arrays so all three species hit zero remaining.

**Why:** Berries are a popular, high-intent category; finishing whole species keeps the
Progress board meaningful and makes re-runs no-ops. Accuracy over coverage: thin trade names
(Blue Rose, BSA, OB1, Vitality, Sandford) and generic or mis-parsed listings (Thornless,
Blueberry Ash items, Nemesia, bundle noise) were skipped, never guessed.

**Actions:**
- blueberry.json: +5 entries (Kisses, Denise, Sharpblue, Magnolia, Sapphire), skipped 12 -> 21
- raspberry.json: +2 entries (Coho, Nootka), skipped 4 -> 9
- blackberry.json: NEW, 4 entries (Thornless Chester, Waldo, Thornless Waldo mirror,
  Blackberry Jam Fruit with its not-a-true-blackberry clarification), 4 skipped
- Waldo entry mirrored onto the duplicate-parse slug blackberry-thornless-waldo (same
  cultivar, lychee spelling-variant precedent)
- Spot-checked cited sources: UF/IFAS HS1245, MSU Extension, USDA-ARS Coho HortScience
  manuscript (full PDF), Wikipedia Rosenbergiodendron formosum; all claims confirmed
- Full test suite green (1546 tests); no golden regen needed (no fixture species in this set)

**Status:** Shipped as PR from dale/varieties-berries; deploy happens at the serialized
close-out. Blueberry, raspberry, and blackberry all report 0 remaining (mark DONE on the
Progress list at close-out).

**To revert:** Revert the PR merge commit; the three species files return to their pilot
state and blackberry.json disappears.
