# Variety descriptions: persimmon complete (47 blurbs, 15 verified skips)

**Decided by:** Dale (parallel variety-descriptions run, window: persimmon)
**Context:** The variety-descriptions rollout (DEC-178 pilot, DEC-180..191 first batch) had no
persimmon coverage. The live catalogue carried 62 persimmon variety slugs across 8+ nurseries,
many of them spelling or astringency-qualifier variants of the same cultivar (Fuyu alone appears
under 8 slugs).
**Decision:** Research every live persimmon slug in one window and ship a complete
`tools/scrapers/variety_descriptions/persimmon.json`: 47 verified entries covering 21 distinct
cultivars (variant slugs reuse the same verified facts with tailored lead sentences), plus 15
slugs recorded in `skipped` so re-runs never re-attempt them.
**Why:** Persimmon is a mid-size catalogue with strong collector interest, and the variant-heavy
slug list made it cheap to cover fully (research once per cultivar, emit per slug). Accuracy over
coverage: anything that could not be tied to a verifiable cultivar with 2+ reputable sources
(including at least one non-nursery source) was skipped, not guessed.
**Actions:**
- 8 parallel research subagents, each owning a disjoint cultivar group (Fuyu, Jiro/Izu,
  Nightingale/Dai Dai Maru, Suruga/Isahaya/Sunami/Yoho, Flat Seedless/Tanenashi/Tone Wase/Tamopan,
  Hachiya/Hyakume/Rojo Brillante, Wright's/Nishimura/misc, American/odd tail).
- Sources lean on UF/IFAS MG242, NC State Extension, Missouri Botanical Garden, NIFTS/PMC papers,
  ANFIC, CRFG, and the RFCA archive (tier owned, https). Nursery listings used as grounding only.
- Review rejections beyond agent skips: persimmon-black-sapote (semantic mis-parse, black sapote
  is its own species page) and persimmon-cultivar-vanilla (live product is ausnurseries
  "Cultivar Large Vanilla", cannot be confidently tied to the Italian Vaniglia kaki).
- Notable verified skips: Wright's Favourite (real Australian cultivar but nursery-only sourcing),
  Twentieth Century (sources contradict on astringency), the three Pomelo slugs (two contradictory
  nursery descriptions, no independent source), Maru (ambiguous between Dai Dai Maru and the US
  brown-fleshed Maru), Rojo A, Striped Nightingale, Akayaki, and three unverifiable Fuyu forms
  (Upright, Weeper, Shuvancy).
- Yoho's astringency is genuinely disputed (ANFIC says astringent, some research and nurseries say
  non-astringent); the blurb discloses the dispute rather than picking a side.
**Status:** Shipped as PR from branch dale/varieties-persimmon. Persimmon remaining = 0 (DONE for
the Progress list at close-out). All 1463 tests green; not a golden-fixture species.
**To revert:** delete `tools/scrapers/variety_descriptions/persimmon.json` and rebuild variety pages.
