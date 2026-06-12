# Variety descriptions: plum, pear, quince, medlar tail pass

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-plum-pear-quince-medlar)
**Context:** Continuing the DEC-178 per-variety "what's unique" blurb rollout
(`docs/variety-descriptions-rollout.md`) for four pome/stone species. plum and pear already had
their top varieties from the pilot; quince and medlar had no variety file yet. REMAINING this run
was plum 16, pear 13, quince 13, medlar 2 (live server slugs minus each file's `varieties` and
`skipped`).
**Decision:** Added 16 verified blurbs and recorded 30 skips across the four species.

- **plum:** added `plum-spring-satin` (first publicly bred plumcot, USDA ARS Okie). Skipped 15:
  4 thin-source PBR/exclusive cultivars (black-adder, apricot-plumscrumptious,
  interspecific-plumscrumptious, cherry-little-chum, all nursery-only) and 11 multi-graft combos /
  generic descriptors / duplicates.
- **pear:** added 5 (nashi-shinseiki, nashi-hosui, nashi-ya-li, clapp-s-favourite, williams-red).
  Skipped 8: 2 thin-source nashi (nashi-bonza, nashi-tropical-sunshu) and 6 multi-graft / misspelling
  duplicates of already-covered varieties.
- **quince:** new file, added 8 (smyrna, champion, pineapple, missouri-mammoth, rea-s-mammoth,
  chinese, de-bourgeaut, powell-s-prize). Skipped 5: master-s-early and heaven-lotus (unverifiable),
  plus 3 misspelling / tagged duplicates.
- **medlar:** new file, added 2 (dutch, nottingham). 0 skipped (both live varieties verified).

**Why:** Accuracy over coverage. Every blurb has >=2 reputable sources with >=1 non-nursery
(authoritative .gov/.edu/RHS/USDA ARS, NC State Extension, or third-party); thin or unverifiable
varieties were skipped, not guessed.
**Actions:** Wrote `variety_descriptions/{plum,pear,quince,medlar}.json`; full test suite green
(1546 tests). No golden regen (none of these four is a golden-fixture species).
**Status:** Shipped via PR. Deploy + progress-tick at the serialized close-out.
**To revert:** Drop the four added entries (and the new quince/medlar files) from
`tools/scrapers/variety_descriptions/`; the renderer falls back to no blurb.
