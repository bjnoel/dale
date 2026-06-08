# Variety descriptions rollout: olive, pomegranate, feijoa, lilly-pilly, jackfruit (39 added)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-olive-set)

**Context:** Continuation of the per-variety "what's unique" blurb layer on treestock
`/variety/<slug>.html` (DEC-178, see `docs/variety-descriptions-rollout.md`). This window
owned five species files: olive, pomegranate, feijoa, lilly-pilly, jackfruit. Olive and
pomegranate already held the DEC-178 pilot entries (2 and 1 respectively); feijoa, lilly-pilly,
and jackfruit were new files. REMAINING was computed from live server stock minus each file's
`varieties` and `skipped`.

**Decision:** Add 39 verified blurbs across the five species and record 51 thin-source or
noise skips, all gated by `tests/test_variety_descriptions.py` (>=2 sources, >=1 non-nursery,
confidence >= 0.80, every claim cited, no dashes, Australian spelling).

**Per-species result (added / skipped / remaining):**
- olive: +13 (15 total incl. pilot) / 18 skipped / 12 remaining
- pomegranate: +10 (11 total incl. pilot) / 10 skipped / 9 remaining
- feijoa: +9 / 6 skipped / 2 remaining
- lilly-pilly: +5 / 9 skipped / 29 remaining
- jackfruit: +2 / 8 skipped / 15 remaining

**Why:** Olive, pomegranate, and feijoa are well documented by authoritative and reputable
sources (IOC world catalogue, CRFG fruit facts, Auckland Botanic Gardens, the RFCA owned
archive). Lilly pilly and jackfruit have many nursery-trade-name cultivars with no independent
documentation, so most of their live varieties were correctly skipped (accuracy over coverage).

**Notes on accuracy review:**
- olive-picual: dropped a Wikipedia-only superlative ("~25% of world oil") and a ppm figure;
  reworded to qualitative claims confirmed by the IOC authoritative catalogue.
- olive-mission: replaced an unreachable Olive Oil Times link with the Northern Valleys News
  New Norcia article (verified); New Norcia heritage facts stated, no over-claim that the
  New Norcia trees are genetically Mission.
- pomegranate-azerbaijani and ben-hur: tightened to facts actually confirmed by Sustainable
  Gardening Australia and the RFCA archive (RFCA lists Azerbaijani in a yield table only, with
  no descriptive text, so appearance cites were re-scoped); dropped unconfirmed PBR and
  soft-seed specifics.

**Actions:**
- Wrote `tools/scrapers/variety_descriptions/{olive,pomegranate,feijoa,lilly-pilly,jackfruit}.json`
- `python3 -m unittest discover tests/` green (1401 tests). No golden regen (none of these are
  golden-fixture species).
- Public ledger fragment: `public-ledger/2026-06-08-varieties-olive-set.md`

**Status:** Shipped as a PR. Deploy and progress-ticking are the serialized close-out (not this
branch). None of the five species reached 0 remaining; re-run the command per species to finish
the tails.

**To revert:** Remove the 39 added keys (and this window's skip entries) from the five JSON
files; the renderer falls back to no blurb.
