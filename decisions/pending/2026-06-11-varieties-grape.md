# Grape variety descriptions: full tail finished (47 described, 0 remaining)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-grape)
**Context:** The grape `/variety` pages had 11 verified "what's unique" blurbs from the DEC-178
pilot, leaving a long tail of live, in-stock grape varieties without a blurb. Grape is one of
the biggest catalogues on treestock (56 live variety slugs).
**Decision:** Researched and added 36 new verified blurbs, taking grape to 47 described and 0
remaining (every live grape variety is now either described or recorded as a thin-source skip).

**Why:** Variety blurbs are the per-variety content layer (DEC-178) that makes each `/variety`
page substantive for SEO and for collectors; grape is high traffic and was the largest unfinished
catalogue. Accuracy over coverage: each blurb rests on >=2 reputable sources, >=1 non-nursery,
verified against the stored claims ledger.

**Actions:**
- Added 36 entries to `tools/scrapers/variety_descriptions/grape.json` across table grapes
  (Crimson/Flame-family kin, Christmas Rose, Red Globe relatives), CSIRO Australian breeds
  (Marroo/Maroo, Sun Muscat, Carina Currant, Sultana H5 clone), classic wine grapes sold as
  home vines (Shiraz, Chardonnay, Merlot, Grenache, Pinot Noir/Gris, Sangiovese), muscadines
  (Fry, Dixie, Noble), and three "not really a grape" mis-groupings honestly clarified in copy
  (Sea Grape = Coccoloba uvifera, Burmese = Baccaurea ramiflora, Amazon = Pourouma cecropiifolia).
- Skipped 5 new thin-source varieties (recorded in the file's `skipped` array): muscadine-adonis,
  muscadine-achilles, black-opal, black-lady-finger, muscat-gold (nursery-only or unidentifiable).
- Spot-checked the fabrication-prone citations (USPP5056 Christmas Rose, USPP7377 Marroo, four
  UC Davis FPS variety IDs, two VIVC IDs, UGA Fry, UAEX Saturn PDF) against the live sources.
- `python3 -m unittest discover tests/` green (1463 tests). Grape is not a golden-fixture species,
  so no golden regeneration.

**Status:** Shipped via PR from branch dale/varieties-grape. Deploy is the serialized close-out
(build_variety_pages.py + purge_cloudflare.sh), not this branch.
**To revert:** revert the grape.json change; the renderer falls back to no blurb per slug.
