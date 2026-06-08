# Variety descriptions rollout: pear, loquat, apricot, grapefruit, tamarillo (batch plt-grt)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-plt-grt)
**Context:** Continuing the DEC-178 per-variety "what's unique" blurb layer on treestock
`/variety/<slug>.html` pages, following `docs/variety-descriptions-rollout.md`. This window
owned five species files: pear, loquat, apricot, grapefruit, tamarillo. REMAINING was computed
from live server stock minus each species file's existing `varieties` and `skipped`.

**Decision:** Researched 48 candidate varieties across the five species with non-overlapping
subagents (>=2 reputable sources each, >=1 non-nursery; nursery copy is grounding only). Added
40 verified blurbs and recorded 8 thin-source skips. Accuracy was the rule: anything that could
not clear the >=2-source / >=1-independent / confidence >= 0.80 gate was skipped, not guessed.

Added per species (new entries this run):
- apricot (14): bulida, castlebrite, cot-n-candy-interspecific, divinity, fireball, glengarry,
  goldrich, hunter, katy, patterson, rival, storeys, tardif-de-bordaneil, tilton.
- grapefruit (6): flame, oro-blanco, ruby-red, star-ruby, thompson-s-pink, wheeny.
- loquat (3, new file): champagne, herds-mammoth, nagasakiwase.
- pear (14): beurre-hardy, conference, corella, doyenne-du-comice, flemish-beauty, flordahome,
  hood, josephine-de-malines, nashi-nijisseiki, packham-s-triumph, williams, winter-cole,
  winter-nelis, ya-li-nashi.
- tamarillo (3, new file): red, yellow, orange.

Skipped (thin/ambiguous sources, recorded in each file's `skipped` array):
- grapefruit: honneffs-surprise.
- loquat: bessell-brown, enormity, honey-dew, sewells-prolific, springtime (Australian seedling
  selections documented only on nursery listings; RFCA archive covers Japanese cultivars only).
- pear: bonza (species/identity ambiguous across sources), red-princess (under-sourced, appears
  only as a pollinator name).

**Why:** A fabricated cultivar fact is worse than no blurb. Citrus leaned on the UC Riverside
Citrus Variety Collection (authoritative); pears on USA Pears / UF-IFAS / NC State / Wikipedia /
Orange Pippin; apricots on UC Davis FPS, a US plant patent, Virginia Cooperative Extension,
CSIC, and the Rare Fruit Club WA varieties page; loquat and tamarillo on CRFG fruit facts and
the RFCA archive (owned). CRFG canonical URLs were re-derived (the old /pubs/ff/ paths 404) and
the loquat Champagne / Herd's Mammoth and tamarillo colour-form facts were spot-checked against
the live CRFG pages.

**Actions:** Wrote tools/scrapers/variety_descriptions/{apricot,grapefruit,loquat,pear,tamarillo}.json
only. `python3 -m unittest discover tests/` green (1401 tests). No golden regen needed (none of
these are golden-fixture species). No deploy, no decision-log/shared-ledger edits, no Progress
tick (all serialized close-out).

**Status:** Shipped as PR from dale/varieties-plt-grt. tamarillo is DONE (0 remaining).
Post-run REMAINING (mostly parser noise, multigraft listings, and spelling variants of
covered varieties): apricot 18, grapefruit 8, loquat 6, pear 77, tamarillo 0.

**To revert:** Remove the added entries from the five species JSON files (or drop loquat.json
and tamarillo.json entirely). The renderer falls back to no blurb, so pages are unaffected.
