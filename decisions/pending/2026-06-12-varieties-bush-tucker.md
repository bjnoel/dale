# Variety blurbs for 20 bush tucker species (saltbush, pigface, quandong, myrtles, native ginger, and more)

**Decided by:** Dale (parallel variety-descriptions run)
**Context:** The bush tucker category went live (DEC-202) and these native species now carry
live stock on treestock, but none had per-variety "what's unique" blurbs. This run covers the
first 20 bush tucker species: saltbush, ruby-saltbush, pigface, native-ginger, native-river-mint,
native-thyme, quandong, blue-quandong, desert-lime, lemon-myrtle, cinnamon-myrtle, mountain-pepper,
native-raspberry, riberry, sea-celery, warrigal-greens, gumbi-gumbi, sandpaper-fig, bunya-nut,
burdekin-plum.

**Decision:** Added 41 verified variety blurbs across 20 new `variety_descriptions/<species>.json`
files, skipping 1 (pigface-orange, no verifiable taxon). Each blurb is verified against 2+ reputable
sources (>=1 non-nursery), following the standard gate (>=0.80 confidence, claims-to-sources ledger,
no em dashes, Australian spelling).

**Why:** Bush tucker buyers (and AI answer engines) get a distinctive, sourced description of each
native variety, deepening the category that DEC-200/201/202 opened. Many of these natives are poorly
documented elsewhere at the variety level, so accurate first-party-grounded blurbs are a genuine moat.

**Actions:**
- Researched live stock for all 20 species (42 live variety slugs) via 6 parallel research agents.
- Wrote 20 per-species JSON files (41 varieties added, 1 skipped).
- Corrected several taxonomy traps surfaced during research: all three "quandong" varieties (Hard,
  Eumundi, Kuranda) are Elaeocarpus species, NOT the desert quandong Santalum acuminatum; "Round Baby"
  pigface is Disphyma crassifolium (round-leaved), not Carpobrotus; the two "Sea Celery" listings are
  different species (Apium annuum vs Apium prostratum var. prostratum); Mountain Pepper male/female
  reflect the dioecious Tasmannia lanceolata (only females fruit).
- `python3 -m unittest discover tests/` green (1605 tests). No golden regen needed (no fixture species).
- Spot-checked authoritative sources (Wikipedia Elaeocarpus obovatus, FloraBase Carpobrotus virescens).

**Status:** Shipped via PR (branch dale/varieties-bush-tucker). Deploy is the serialized close-out.

**To revert:** delete the 20 new `tools/scrapers/variety_descriptions/<species>.json` files; the
renderer falls back to no blurb.
