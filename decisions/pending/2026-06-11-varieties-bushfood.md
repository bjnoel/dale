# Variety blurbs: bush tucker set (lilly-pilly, midyim-berry, muntries)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-bushfood)
**Context:** Treestock per-variety "what's unique" blurb rollout (DEC-178 layer). The bush tucker
category is now live, so the lilly pilly, midyim berry and muntries catalogues needed verified
blurbs. lilly-pilly already had 5 pilot entries; midyim-berry and muntries had none.
**Decision:** Added 23 new verified blurbs across the three species and recorded 9 thin-source
skips, all keyed to live server variety slugs and gated by the standard rule (>=2 sources,
>=1 non-nursery, confidence >= 0.80, no dashes, Australian spelling).

- lilly-pilly: +23 (now 28 total), covering the "umbrella" species sold as lilly pilly
  (blue / Syzygium oleosum, weeping / Waterhousea floribunda, broad-leaved, giant water gum,
  paperbark satinash, rain cherry, river cherry, red apple / S. ingens, coolamon / S. moorei)
  plus the verifiable hedging and dwarf cultivars (Allyn Magic, Pink Cascade, Powder Puff,
  Superior Psyllid Free, Baby Boomer, Forest Flame, Hinterland Gold, Big Red, Elite, Minor,
  Sublime, Firescreen) and the two Tucker Bush brand selections.
- midyim-berry: +3 (Tucker Bush / straight Austromyrtus dulcis, Blush, Copper Tops).
- muntries: +1 (Tucker Bush / straight Kunzea pomifera).

Skipped (thin or ambiguous sources, nursery-marketing-only, or unverifiable identity):
lilly-pilly Minor Allyn Magic, Plum Magic, Green Machine, Pinnacle, Slim Jim, Silver Streaker,
Purple Rain, Minor Red Tip, Long Island; midyim-berry Ruby.

**Why:** Accuracy over coverage. Many lilly pilly hedging cultivars (Ozbreed-style PBR brands)
only have breeder marketing pages, so they correctly skip. The species sold under the lilly pilly
umbrella are genuinely distinct botanical species and carry the most collector value (fruit colour,
edibility, bush tucker use), so those got the strongest entries from authoritative sources (PlantNET,
ANBG, NSW Threatened Species, AgriFutures).
**Actions:** Wrote tools/scrapers/variety_descriptions/{lilly-pilly,midyim-berry,muntries}.json.
`python3 -m unittest discover tests/` green (1546 tests). No golden regen (none are fixture species).
**Status:** Shipped via PR. Deploy is the serialized close-out (build_variety_pages.py + purge).
**To revert:** Drop the new entries from the three JSON files and rebuild.
