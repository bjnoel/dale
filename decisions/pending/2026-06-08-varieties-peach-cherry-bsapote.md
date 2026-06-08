# Variety descriptions rollout: peach, cherry, black sapote

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-peach-cherry-bsapote)

**Context:** Continuing the per-variety "what's unique" blurb rollout (DEC-178) on treestock
`/variety/<slug>.html` pages. Pilot seeded peach, cherry and black-sapote with one top variety
each (Anzac, Stella, Mossman). This window worked the live tail for all three species via the
worktree/PR workflow in `docs/variety-descriptions-rollout.md`, fanning out non-overlapping
research subagents (>=2 reputable sources each, >=1 non-nursery, skip-if-thin, never guess).

**Decision:** Added 38 verified variety blurbs and recorded 64 thin-source/mis-parse skips across
the three species files (no shared-file edits; per-species `varieties` + `skipped` ledgers only).

- Peach: 16 added (golden-queen, elberta, o-henry, indian, china-flat, tropic-beauty, tropic-snow,
  crimson-rocket, tatura-204, trixzie-pixzee, red-haven, loring, flavourcrest, flordaprince,
  blackboy, okinawa), 16 skipped. Now 17 total with the pilot's Anzac.
- Cherry: 18 added (lapins, sir-don, morello, royal-lee, royal-crimson, napoleon, sunburst,
  royal-rainier, simone, bing, minnie-royal, starkrimson, lambert, early-burlat, van, rainier,
  capulin, nanking), 43 skipped (mostly non-cherry mis-parses, 2-way grafts, dwarf "Cherree"
  marketing variants, and spelling dups). Now 19 total with the pilot's Stella.
- Black sapote: 4 added (maher, bernecker, superb, ricks-late), 5 skipped. Now 5 total with Mossman.

**Why:** Accuracy over coverage. The four Zaiger low-chill cherries (royal-lee, royal-crimson,
minnie-royal, royal-rainier) were initially nursery-only; a second research pass anchored each on
its US Plant Patent (authoritative primary source), so they clear the >=1-non-nursery gate honestly
rather than being skipped. Flordaprince was given a second source (UF/IFAS authoritative + Daleys
grounding). Black-sapote cultivar facts spot-checked against Wikipedia's "Australian cultivars"
section. Bulleen Art Garden sources tiered as `nursery` (it is a retail nursery), with Wikipedia +
Growables carrying independence.

**Actions:** Wrote `tools/scrapers/variety_descriptions/{peach,cherry,black-sapote}.json`.
`python3 -m unittest discover tests/` green (1401 tests). Black-sapote is a golden-fixture species
but the fixture only builds `black-sapote-mossman` (the only one with fixture stock), which already
had its blurb, so no golden regeneration was needed.

**Status:** Shipped via PR. Deploy + progress-tick are the serialized close-out.

**To revert:** Drop the added entries from the three species JSON files (renderer falls back to no
blurb gracefully).
