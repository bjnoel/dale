# Variety descriptions rollout: peach, cherry, black sapote (complete)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-peach-cherry-bsapote)

**Context:** Continuing the per-variety "what's unique" blurb rollout (DEC-178) on treestock
`/variety/<slug>.html` pages. Pilot seeded peach, cherry and black-sapote with one top variety
each (Anzac, Stella, Mossman). This window worked the full live tail for all three species via the
worktree/PR workflow in `docs/variety-descriptions-rollout.md` across multiple passes, researching
each remaining variety against >=2 reputable sources (>=1 non-nursery), skip-if-thin, never guess.
All three species are now at 0 remaining (DONE).

**Decision:** Across the run, added 55 verified variety blurbs and recorded 102 thin-source/mis-parse
skips across the three species files (no shared-file edits; per-species `varieties` + `skipped`
ledgers only). Final per-species state (live slugs = varieties + skipped, 0 remaining):

- Peach: 28 blurbs, 52 skipped. Pass 1 added the top 16 (golden-queen, elberta, o-henry, indian,
  china-flat, tropic-beauty, tropic-snow, crimson-rocket, tatura-204, trixzie-pixzee, red-haven,
  loring, flavourcrest, flordaprince, blackboy, okinawa) plus the pilot Anzac. Pass 2 added the
  heritage/documented tail: coronet, briggs-red-may, double-jewel (US Plant Patent PP6410),
  pullar-s-cling, j-h-hale-million-dollar, late-italian-red, stark-earliglo, maycrest (USPP6229),
  bendigo-beauty, aztec-gold, albatross.
- Cherry: 25 blurbs, 45 skipped. Pass 2 added vista (Hedelfingen x Victor, Ontario), merchant
  (RHS AGM, John Innes), burgsdorf (colonial-era Australian heritage), st-margaret AND
  saint-margaret (same variety, both live slugs given the same verified blurb), and ron-s
  (Ron's Seedling; ACS Omega study found the highest total flavonoid content of the Australian
  cultivars tested).
- Black sapote: 5 blurbs, 5 skipped (completed in pass 1; unchanged this pass).

**Why:** Accuracy over coverage. Specific-fact claims (awards, the cherry flavonoid superlative, the
patents) are anchored on authoritative sources per the test gate. Modern proprietary Australian
nursery cultivars with only nursery sources (peach Angel, Silvan Sunset, Okee Dokee, Ruby Sensation,
Early Beauty, Maravilha) were SKIPPED rather than blurbed on marketing copy alone, as were varieties
that could not be resolved to a verifiable cultivar (peach Orion, Tasty Zee, Valley Red, Wiggins,
Spring Gold, Melodie) and obvious noise (2-way grafts, spelling dups, marketing variants, generic
"Donut"). Cherry Country Red and Pretty Gully skipped for lack of an independent reputable source.

**Actions:** Wrote `tools/scrapers/variety_descriptions/{peach,cherry,black-sapote}.json`.
`python3 -m unittest discover tests/` green (1401 tests). No golden regeneration needed: peach and
cherry are not golden-fixture species, and black-sapote (a fixture species) was unchanged this pass.

**Status:** Shipped via PR. Deploy + progress-tick (peach, cherry, black-sapote all DONE) are the
serialized close-out.

**To revert:** Drop the added entries from the three species JSON files (renderer falls back to no
blurb gracefully).
