# Variety descriptions: chestnut and hazelnut

**Decided by:** Dale (parallel variety-descriptions run)
**Context:** Continuing the treestock /variety "what's unique" blurb rollout
(DEC-178, docs/variety-descriptions-rollout.md) to the chestnut and hazelnut catalogues.
Both species had no variety blurbs yet. Worked in worktree dale/varieties-chestnut-hazelnut.

**Decision:** Added verified, multi-source blurbs for 8 chestnut and 11 hazelnut varieties
(the hazelnut count includes a duplicate-spelling entry, Halls Giant, mirroring Hall's Giant
so the blurb renders on both live /variety pages). Skipped thin-source varieties rather than
guessing: chestnut Marone, Wandiligong Wonder, Winchester; hazelnut American White, Red Aveline.

**Why:** Chestnut and hazelnut are the two main nut catalogues with named Australian selections
(Fleming's Prolific/Special, Emerald Gem, Buffalo Queen, T.B. Cosford, Wanliss Pride) that have
genuine "what's unique" stories backed by industry bodies (Chestnuts Australia, Hazelnut Growers
of Australia, AgriFutures, NSW DPI) and the RFCA archive. Accuracy over coverage: every blurb
clears the gate (>=2 sources, >=1 non-nursery, confidence >= 0.80) or it was skipped.

**Actions:**
- Wrote tools/scrapers/variety_descriptions/chestnut.json (8 varieties, 3 skipped).
- Wrote tools/scrapers/variety_descriptions/hazelnut.json (11 varieties, 2 skipped).
- python3 -m unittest discover tests/ green (1546 tests). Neither species is a golden fixture,
  so no golden regeneration.

**Status:** Shipped as a PR. Not deployed (deploy is the serialized close-out).

**To revert:** delete the two JSON files; the renderer falls back to no blurb.
