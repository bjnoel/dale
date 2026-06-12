# Variety blurbs: citrus tail (mandarin, orange, tangelo, grapefruit) finished to 0 remaining

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-citrus-tail)
**Context:** Four citrus species still had live `/variety` stock with no "what's unique" blurb:
mandarin (9), orange (7), tangelo (4), grapefruit (1). Tangelo had no species file yet. Most of
the tail was reorderings, misspellings, size grades, or mislabels of cultivars already verified
in the pilot, plus a handful of genuine unknowns needing fresh research.
**Decision:** Added 19 verified variety blurbs across the four species and recorded 3 thin-source
skips, taking all four to 0 remaining. New `tangelo.json` (Minneola, Orlando, Seminole researched
against UC Riverside Givaudan Citrus Variety Collection plus Wikipedia/Specialty Produce; Mineola
mirrored from Minneola). Three genuine unknowns researched fresh: mandarin Jamaican (the Topaz
/ Ortanique tangor, Citrus Australia + Wikipedia), mandarin Hansen (Australian tangor, UC Riverside
CVC + USDA Citrus ID, both authoritative), orange Blood Meli Tarocco (nucellar Tarocco Meli clone,
Acireale 1988, NSW DPI primefact + Oscar Tintori + Wikipedia + Specialty Produce). The remaining
adds are verbatim mirrors of existing verified entries for the same cultivar: mandarin Silverhill
(from Silverhill Satsuma), Miho Wase (from Miho Wase Satsuma), Clemantine (misspelling of
Clementine), Imperial Jumbo (size grade of Imperial); orange Blood Rosso Tarocco and Ippolito
Blood / Blood Ippolito (reorderings of Blood Tarocco Rosso / Blood Tarocco Ippolito), Blood Cara
Cara (Cara Cara mislabelled blood, the entry clarifies the lycopene colouring), Blood Fruit Tree
(generic blood orange), Blood Tarocco Meli (reorder of Blood Meli Tarocco); grapefruit Red Star
Ruby (from Star Ruby).
**Why:** Accuracy over coverage. Mirroring a verified entry for a confirmed same-cultivar listing
is sound and matches the pilot precedent (cara-cara-blood-navel mirrors cara-cara). Genuine
unknowns were researched against 2+ reputable sources with at least one non-nursery; thin ones
were skipped, never guessed.
**Actions:** Wrote `tools/scrapers/variety_descriptions/{mandarin,orange,tangelo,grapefruit}.json`
(varieties + skipped). `python3 -m unittest discover tests/` green (1605 tests). No golden regen
needed (none of these four is a golden-fixture species).
**Status:** Shipped via PR on branch dale/varieties-citrus-tail. Deploy + progress-tick are the
serialized close-out, not this branch.
**To revert:** Drop the added keys from the four species files (or delete tangelo.json) and rebuild
`build_variety_pages.py`; the renderer falls back to no blurb.

Skipped this run (thin sources / parser noise):
- mandarin-japanese-blood-plum: parser mis-parse, the product is a plum, not a mandarin cultivar.
- mandarin-plum: noise, not a real mandarin cultivar name.
- mandarin-robbie-engalls-seedless: obscure local selection, no independent reputable sourcing.
