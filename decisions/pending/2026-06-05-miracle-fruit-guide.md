# Miracle fruit per-state growing guide on treestock (archives-first, own climate category)

**Decided by:** Dale (parallel guide run)

**Context:** Continuing the species growing-guide rollout (docs/species-guide-rollout.md) down the
indexed-but-low-traffic tail. Miracle fruit (Synsepalum dulcificum) is a rare-fruit curiosity: a
frost-tender, strongly acid-soil West African shrub whose berry makes sour foods taste sweet. The
Rare Fruit Council of Australia archives hold five miracle fruit articles (1980 to 1997, including
the Cairns cultivation notes and the North Queensland introduction), the richest owned source for it,
so this guide is genuinely archives-first.

**Decision:** Ship a comprehensive, cited `growing_guides/miracle-fruit.json` matching the olive
gold standard: a seven-section state-invariant core (the taste-changing berry, seedlings not named
varieties, acid soil as the make-or-break, warmth/humidity/shelter, water and feeding, harvest and
how to eat it, buying tips) plus four genuinely distinct state overlays. Queensland is the flagship
on climate (the humid tropical north is the one part of Australia where it grows and fruits outdoors,
and where it was first fruited here), with a strong WA overlay (Perth's alkaline soils and limey
scheme water fight its acid need, so it is a pot plant; quarantine limits interstate shipping), a
warm-coast-or-pot NSW overlay, and an indoor/heated-glasshouse VIC overlay.

**Why:**
- Correctness for collectors: acid soil (pH 4.5 to 5.8, like a blueberry) is the single thing that
  decides success, it is self-fertile (one seedling fruits on its own), sold only as seedlings (no
  named cultivars), water drives fruit size, and the one real pest is scale (treated with something
  other than white oil). All pinned to owned RFCA articles and cross-checked against the California
  Rare Fruit Growers, Daleys, and the WA Rare Fruit Club.
- Archives-first keeps authority and traffic in-network: five RFCA articles cited and carried in
  Further reading (followed); the third-party WA Rare Fruit Club page is nofollow.
- Gave miracle fruit its own climate category. The generic "tropical" note misled (VIC's "stick to
  cold-hardy varieties" is wrong for a variety-less frost-tender shrub; WA's "warm dry suits tropical
  species" ignores its acid-soil and humidity needs).
- Added "Miracle Berry" and "Miraculous Berry" synonyms to fruit_species.json. "Miracle Berry" is the
  most common retail name (used by four of the seven nurseries that list it) and the matcher was
  missing every "Miracle Berry" listing, so the species page and the dashboard search now capture
  real in-stock plants (for example Ladybird's in-stock "Miracle Berry Fruit") that were invisible
  before.

**Actions:**
- New `tools/scrapers/growing_guides/miracle-fruit.json` (9 sources: 5 RFCA owned, DPIRD WA, CRFG,
  Daleys, WA Rare Fruit Club; core + WA/QLD/NSW/VIC overlays; 6 Further-reading links).
- New `tests/test_guide_miracle_fruit.py` (21 tests: per-state uniqueness, region-token leak, no
  dashes, FAQ JSON-LD counts, gov + owned-archive sourcing, self-fertile/seedling/acid-soil/white-oil
  correctness guards, RFCWA-nofollow).
- `build_species_state_pages.py`: new `miracle-fruit` climate category plus a per-state note for each
  of WA/QLD/NSW/VIC.
- `fruit_species.json`: added the two synonyms to the miracle-fruit entry.
- Regenerated the dashboard golden (`tests/golden/expected/dashboard/index.html`); the only change is
  the two new search aliases for miracle fruit.

**Status:** PR open, pending Benedict's review. Did not edit decision-log.md (folded at close-out),
did not commit a regenerated archive_links.json, did not tick the rollout Progress list (all
shared-edit conflict points in a parallel batch). Full suite green (1126 tests). Every cited and
Further-reading URL verified live (HTTP 200).

With current stock, miracle fruit sits below the threshold that builds the per-state buy pages (WA
has one in-stock plant; QLD/NSW/VIC each have three but fall outside the top-20 cap), so the live
change today is a much better species page; the four state overlays are built and tested and switch
on automatically as stock grows, exactly as for sapodilla, rambutan and white sapote.

**To revert:** delete `growing_guides/miracle-fruit.json` and `tests/test_guide_miracle_fruit.py`,
revert the `miracle-fruit` category and notes in `build_species_state_pages.py`, drop the two
synonyms from `fruit_species.json`, and restore the dashboard golden. The species page falls back to
the generic blurb.
