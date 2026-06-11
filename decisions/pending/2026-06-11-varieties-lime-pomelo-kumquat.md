# Variety descriptions batch: lime tail, pomelo tail, kumquat (new species file)

**Decided by:** Dale (parallel variety-descriptions run, window lime-pomelo-kumquat)
**Context:** Continuing the DEC-178 variety blurb rollout per docs/variety-descriptions-rollout.md.
Assignment: lime, pomelo, kumquat. Lime and pomelo had pilot/batch-1 coverage with a long tail;
kumquat had no file at all despite Nagami being stocked by 11 nurseries.
**Decision:** Researched the full live remaining set for all three species (25 candidates after
dropping listing-noise dupes) via parallel research subagents, each fact verified against 2+
reputable sources with at least one non-nursery source (UC Riverside Citrus Variety Collection,
PROSEA, Atlas of Living Australia, UQ News, Wikipedia). Added 17 entries, skipped 8 on thin or
unverifiable sourcing, and recorded 27 listing-noise slugs (pot-size variants, misspellings,
fruit-salad-tree noise, genus-only labels) in the per-species skipped arrays so re-runs never
re-attempt them.

**Why:** Kumquat was the largest uncovered catalogue in the assignment (14 live slugs, zero
blurbs). The lime tail includes four Australian native species pages (Mount White, Russell River,
Australian Round, plus the existing natives) that fit treestock's rare-fruit collector audience.
Accuracy over coverage: K13/Flicks Yellow pomelos and Courtyard/Green kumquats rest only on
nursery copy, so they were skipped rather than guessed.

**Actions:**
- tools/scrapers/variety_descriptions/kumquat.json: NEW, 8 varieties + 6 skipped
- tools/scrapers/variety_descriptions/lime.json: 8 -> 16 varieties, 1 -> 19 skipped
- tools/scrapers/variety_descriptions/pomelo.json: 1 -> 2 varieties, 11 -> 18 skipped
- Editorial gate applied in review: lime-sublime trimmed to third-party-corroborated facts only,
  kumquat-marumi RHS award claim dropped (no authoritative cite), all source URLs spot-checked live
- Full test suite green (1537 tests); no golden regen (none are fixture species)

**Status:** All three species report remaining 0 (DONE for the Progress list at close-out).
**To revert:** git revert the PR commit; the three JSON files are the only content change.
