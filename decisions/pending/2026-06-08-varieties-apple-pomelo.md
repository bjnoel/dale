# Variety descriptions rollout: apple (+34) and pomelo (+1)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-apple-pomelo)
**Context:** Continuing the DEC-178 per-variety "what's unique" blurb layer on treestock
`/variety/<slug>.html` pages, per `docs/variety-descriptions-rollout.md`. This window owned the
apple and pomelo species files. Apple is a large catalogue (150 live cultivar slugs, only 6 had
blurbs from the pilot); pomelo is small (12 live slugs, none described, mostly nursery trade names).

**Decision:** Researched and committed 35 new verified variety blurbs (34 apple, 1 pomelo) and
recorded 17 skips (9 apple, 8 pomelo) in the per-species `skipped` arrays. Accuracy over coverage:
every entry has >=2 reputable sources (>=1 non-nursery), claims bound to sources, no fabricated
figures. Six non-overlapping research subagents (5 apple slices, 1 pomelo) each verified >=2 sources
per variety against the gate; thin or unidentifiable cultivars were skipped, not guessed.

**Why:**
- Apple is the second-biggest catalogue on the site; the pilot only covered 6 of 150 live cultivars.
  Famous commercial (Golden Delicious, Fuji, Jonagold, Mutsu, McIntosh), Australian/low-chill (Lady
  Williams, Sundowner/Cripps Red, Bonza, Democrat, Tropic Sweet, Tropical Beauty, Monty's Surprise),
  heritage dessert (Cox, Gravenstein, Cornish Aromatic, Geeveston Fanny, Orleans Reinette), modern
  disease-resistant (Crimson Crisp, Pixie Crunch) and traditional cider (Dabinett, Michelin, Stoke
  Red, etc.) cultivars are well documented in authoritative sources, so they verify cleanly and add
  real collector value.
- Pomelo is dominated by nursery trade names (Thai Sun, Watsons, Rouge Red, Carter's Red) with no
  independent corroboration, so only the well-documented Vietnamese Nam Roi cleared the bar. Skipping
  the rest is the correct, expected outcome.

**Actions:**
- Added 34 entries to `tools/scrapers/variety_descriptions/apple.json` (40 total now), 9 slugs in its
  `skipped` array (clear non-Malus mis-parses: Malay/Kei/Wood/Sugar/star/wax apples, plus Fraser
  Island which is the native Acronychia imperforata, not a Malus apple).
- Created `tools/scrapers/variety_descriptions/pomelo.json` (1 entry, 8 skipped, including the
  tangelo mis-parse).
- Two corrections applied on review: reclassified the Cox "leading dessert apple" claim from
  superlative to a qualitative use claim (no authoritative figure), and for Monty's Surprise retiered
  the Heritage Food Crops Research Trust source from owned to third_party and dropped the unverified
  "highest quercetin in the world" superlative, keeping only the health claim backed by the
  authoritative Cambridge Proceedings of the Nutrition Society paper (verified by direct fetch).
- `python3 -m unittest discover tests/` green (1401 tests). Apple golden fixture renders apple-pink-lady
  only (an existing blurb), so no golden regeneration was needed.

**Status:** Shipped via PR (not deployed). Apple remaining ~101, pomelo remaining 3 (both species still
have a tail; collision-free to re-run later since each owns its file). Deploy + progress-tick are the
serialized close-out.

**To revert:** Drop the 34 new apple entries / 9 apple skips and delete pomelo.json; the renderer falls
back to no blurb for un-enriched varieties (graceful).
