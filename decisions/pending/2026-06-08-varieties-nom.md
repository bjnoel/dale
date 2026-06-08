# Variety descriptions rollout: nectarine, orange, mulberry (window nom)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-nom)
**Context:** Continuing the per-variety "what's unique" blurb rollout (DEC-178) to the next
stock-ranked species. This window owned nectarine, orange and mulberry. REMAINING was computed
from live server stock (build_variety_pages.group_by_cultivar) minus each species file's existing
`varieties` and `skipped`. Five non-overlapping general-purpose research subagents verified each
candidate against multiple reputable sources (UC Riverside Citrus Variety Collection, NSW DPI,
USDA, NC State, RHS, Te Ara, Missouri Botanical Garden, Wikipedia, Specialty Produce; nurseries
for grounding only).

**Decision:** Added 26 verified variety blurbs and recorded 12 thin-source skips, across the three
species files only (`tools/scrapers/variety_descriptions/{nectarine,orange,mulberry}.json`):
- nectarine: +6 (arctic-rose, crimson-baby, early-rivers, fairlane, flavortop, goldmine), 8 skipped
- orange: +12 (arnold-blood, bergamot, blood, chinotto, hamlin, lanes-late-navel, navelina,
  newhall-navel, pineapple, salustiana, seville, tarocco-blood), 2 skipped
- mulberry: +8 (black-english, hicks-fancy, king-white-shahtoot, pakistan-black, red-shahtoot,
  weeping, white, white-shahtoot), 2 skipped

**Why:** Accuracy over coverage. Each kept entry clears the gate (>=2 sources, >=1 non-nursery,
confidence_score >= 0.80, every claim cited, no orphan sources, no dashes, Australian spelling).
Anything resting only on Australian nursery trademarks (e.g. Sundowner, Royal Gem, Sun Snow,
Tuscany, White Satin, Necta Red, Lena, Majestic) or on a single source padded with a site homepage
(orange Mediterranean Sweet, Joppa) was skipped, not guessed. Two orange entries the subagent had
kept (mediterranean-sweet, joppa-sweet) were demoted to skips on review because each genuinely
rested on a single UC Riverside page. Ornamental mis-parses on the orange species page (canna,
clivia, bougainvillea, hibiscus, etc.) were excluded from REMAINING entirely.

**Actions:** Wrote the three species JSON files; `python3 -m unittest discover tests/` green (1401
tests). No golden regen (none of nectarine/orange/mulberry is a golden-fixture species). No deploy,
no decision-log edit, no progress tick (all of that is the serialized close-out).

**Status:** Shipped as PR from dale/varieties-nom. Remaining after this run: nectarine ~43, orange
~62, mulberry ~13 live slugs, but most of those are spelling variants, 2-way graft listings, and
(orange) ornamental mis-parses, not new distinct varieties to research. No species reached 0
remaining, so none are DONE on the Progress list yet.

**To revert:** Restore the three species files to their pre-run state (single seeded entry each:
nectarine-fantasia, orange-cara-cara/valencia/washington-navel, mulberry-black) and rebuild the
variety pages. The renderer falls back to no blurb for any removed entry.
