# Variety descriptions: fig, avocado, rollinia (rollout window fig-avo-roll)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-fig-avo-roll)

**Context:** Continuing the per-variety "what's unique" blurb rollout (DEC-178,
`docs/variety-descriptions-rollout.md`) for three assigned species: fig, avocado, rollinia.
Each blurb is 1-2 short paragraphs rendered above the price table on `/variety/<slug>.html`,
verified against 2+ reputable sources (>=1 non-nursery), with a stored claims/sources ledger
and confidence score. Accuracy over coverage: a thin or unresolved variety is skipped, not guessed.

**Decision:** Added 27 verified variety blurbs and recorded deliberate skips, owning only the
three assigned species files (collision-free with other rollout windows):

- **avocado** (now DONE, 0 remaining): added 15 (sharwill, shepard, edranol, sir-prize, linda,
  pinkerton, lamb-hass, rincon, russell, mexicola, choquette, zutano, gwen, nabal, ryan) on top
  of the 5 pilot entries; skip-listed 41 (Hazzard and Ramona could not be verified against 2
  non-nursery sources; the rest are A/B flower-type duplicates, spelling variants, rootstock or
  nursery-brand noise, and obscure unverifiable selections).
- **rollinia** (new file, DONE, 0 remaining): added 2 (biriba, brazilian-custard-apple, both
  framed on the species since Rollinia has no widely documented true cultivars); skip-listed 4
  (limberlost, sputnik, picone are nursery selections with no independent sourcing; custard-apple
  is a generic mis-parse).
- **fig** (partial): added 10 (white-adriatic, preston-prolific, white-genoa, cape-white,
  violette-de-bordeaux, celeste, panache, bourjassotte-noire, black-mission, yellow-excel) on top
  of the 2 pilot entries; skip-listed 48 (Sweet Temptation and Figalicious have unresolved or
  trademarked cultivar identities, Red Conadria/Picone Black/Midnight Petite/Deanna lacked 2
  independent non-nursery sources, plus a large tail of "Tree X" parser artifacts, exact
  duplicates, and non-carica Ficus species). 37 obscure long-tail fig cultivars remain for a
  later pass.

**Why:** Verified, distinctive blurbs make variety pages genuinely useful (origin, flavour,
season, flower type for avocados, breba vs main crop for figs) and unique per page, strengthening
the treestock audience moat without any change to the nightly build (generation is dev-time only).

**Actions:**
- `tools/scrapers/variety_descriptions/{fig,avocado,rollinia}.json` updated/created (varieties +
  per-species skipped arrays).
- `python3 -m unittest discover tests/` green (1401 tests). No golden regen needed: the pinned
  variety fixtures (avocado-hass, avocado-reed, fig-black-genoa) were not modified, so output is
  unchanged.

**Status:** Shipped via PR on branch dale/varieties-fig-avo-roll. avocado and rollinia are DONE;
fig has 37 remaining (re-run `/variety-rollout fig` later to continue, collision-free).

**To revert:** Drop the added entries from the three JSON files (or revert this branch). The
renderer falls back to no blurb for any missing slug, so there is no build dependency to unwind.
