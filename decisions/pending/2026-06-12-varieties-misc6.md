# Variety blurbs: pepino, tamarind, babaco, chinese-bayberry, feijoa tail, miracle-fruit

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-misc6)
**Context:** Variety-descriptions rollout window for six smaller catalogues (pepino, tamarind,
babaco, chinese-bayberry, feijoa tail, miracle-fruit). Accuracy over coverage: a fabricated
cultivar fact is worse than no blurb, so thin or mis-parsed slugs are skipped, not guessed.
**Decision:** Added 3 verified "what's unique" blurbs and recorded 15 skips across the six species.
Added: pepino-kendall-gold, tamarind-sweet, babaco-champagne-fruit. Each clears the gate
(>=2 sources, >=1 non-nursery, confidence_score >= 0.80, no dashes, Australian spelling).
**Why:** Most live slugs for these species are parser noise (generic descriptors like "Fruit Plant",
"Edible", "3 Pack") or taxonomic mis-parses (Spanish Tamarind is Vangueria madagascariensis;
Feijoa Correa is the unrelated native-fuchsia genus; babaco Papayuelo is the separate species
Vasconcellea goudotiana). Only three slugs resolved to genuine, multi-source-verified varieties.
**Actions:**
- New files: pepino.json (1 variety, 4 skipped), tamarind.json (1, 4), babaco.json (1, 1),
  chinese-bayberry.json (0, 2).
- Updated skipped arrays: feijoa.json (+feijoa-correa, +feijoa-pale-star), miracle-fruit.json
  (+miracle-fruit-fruit).
- `python3 -m unittest discover tests/` green (1605 tests). No golden regen (no fixture species).
**Status:** Shipped via PR. Deploy is the serialized close-out (build_variety_pages.py + purge).
**To revert:** delete the four new files and back out the two skipped-array additions.
