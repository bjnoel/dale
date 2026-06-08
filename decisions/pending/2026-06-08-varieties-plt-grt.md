# Variety descriptions rollout: pear, loquat, apricot, grapefruit, tamarillo (batch plt-grt)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-plt-grt)
**Context:** Continuing the DEC-178 per-variety "what's unique" blurb layer on treestock
`/variety/<slug>.html` pages, following `docs/variety-descriptions-rollout.md`. This window
owned five species files (pear, loquat, apricot, grapefruit, tamarillo) and ran in two passes
(re-run in the same worktree after a context clear). REMAINING was recomputed each pass from
live server stock minus each species file's existing `varieties` and `skipped`.

**Decision:** Researched the live catalogue for all five species with non-overlapping subagents
(>=2 reputable sources each, >=1 non-nursery; nursery copy is grounding only). Added 61 verified
blurbs in total and recorded the remainder of every species' live tail as `skipped`, so all five
species now reach REMAINING 0 (fully triaged). Accuracy was the rule: anything that could not
clear the >=2-source / >=1-independent / confidence >= 0.80 gate was skipped, not guessed.

Final per-species state (cumulative across both passes):
- pear: 34 varieties, 60 skipped, REMAINING 0.
- apricot: 18 varieties, 16 skipped, REMAINING 0.
- grapefruit: 8 varieties, 9 skipped, REMAINING 0.
- loquat: 3 varieties, 11 skipped, REMAINING 0.
- tamarillo: 3 varieties, 0 skipped, REMAINING 0.

Added in pass 2 (21 new entries):
- pear (19): beurre-diel, beurre-easter, beurre-superfin, chojuro-nashi, clapp,
  duchess-d-anglouleme-european, durondeau, gin-perry, glou-morceau-european, green-horse-perry,
  henry-s-red-longdon-perry, jargonelle-european, ko-sui-nashi, mirandino-rosso, moorcroft-perry,
  paradise, red-sensation, san-giovanni-european, shinseiki. (Classic European heritage pears,
  Japanese nashi, English perry pears, and two Italian cocktail/summer pears.)
- apricot (2): newcastle, bentley (low-chill Australian heritage selections).

Skipped in pass 2 on thin/ambiguous sources (recorded in each file's `skipped` array): pear
cool-crisp, grosse-louise-european, sungold, golden-globe, faccia-rosa, l-inconnue, snow,
shepherds-flat-pound, nashi-sunshu; grapefruit ruby-blush. The remainder of each tail
(multigraft listings, rootstocks, ornamental Callery/Manchurian pears, nursery-brand genetic
dwarfs, misspellings, and spelling variants or synonyms of already-covered varieties) was added
to the per-species `skipped` arrays as mechanical noise so re-runs do not re-attempt them.

**Why:** A fabricated cultivar fact is worse than no blurb. Pass 1 leaned on the UC Riverside
Citrus Variety Collection (citrus), USA Pears / UF-IFAS / NC State / Orange Pippin / Wikipedia
(pears), UC Davis FPS / a US plant patent / Virginia Cooperative Extension / CSIC / Rare Fruit
Club WA (apricots), and CRFG / the RFCA archive (loquat, tamarillo). Pass 2 added a PMC
Japanese-pear breeding review and NC State Extension (authoritative) plus The Book of Pears, the
National Perry Pear Centre and Slow Food Ark of Taste (third_party). Trademarked nursery-brand
pears (PlantNet Cool Crisp / SunGold, Flemings genetic dwarfs) were skipped because their only
sources are the breeder and resellers, failing the >=1-non-nursery rule.

**Actions:** Wrote tools/scrapers/variety_descriptions/{pear,apricot,grapefruit,loquat,tamarillo}.json
only. `python3 -m unittest discover tests/` green (1401 tests). No golden regen needed (none of
these are golden-fixture species). No deploy, no decision-log/shared-ledger edits, no Progress
tick (all serialized close-out).

**Status:** Shipped as PR #99 from dale/varieties-plt-grt. All five species DONE (REMAINING 0).

**To revert:** Remove the added entries from the five species JSON files (or drop loquat.json
and tamarillo.json entirely). The renderer falls back to no blurb, so pages are unaffected.
