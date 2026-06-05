# Starfruit (carambola) gets a comprehensive, cited, per-state growing guide on treestock

**Decided by:** Dale (parallel guide run)

**Context:** treestock tracks starfruit (carambola, Averrhoa carambola) across five nurseries (Daleys, Ladybird, Ross Creek Tropicals, Fruitopia and others), with named cultivars including Sweet Gold, Kembangan, Thai Knight, Arkin, Kary and Fwang Tung in or recently in stock. Until now the species page and any state page showed the single generic fruit_species.json blurb. This continues the per-species growing-guide rollout (olive was the reference; see docs/species-guide-rollout.md), working into the indexed-but-low-click tail.

**Decision:** Ship a starfruit growing guide (tools/scrapers/growing_guides/starfruit.json) matching the olive gold standard: a state-invariant core (choosing a variety, pollination, planting and soil, water and feeding to the depth checklist, harvest and ripening, eating and food safety, buying tips) plus four genuinely distinct state overlays. Queensland is the flagship, because the warm, frost-free coast (the Wet Tropics around Innisfail, Tully and the Atherton Tableland) is the real Australian home of carambola; Western Australia gets the deepest secondary overlay (the tropical north around Kununurra, the Ord, Carnarvon and the Gascoyne, with Perth marginal on alkaline sand and a wall of quarantine rules); New South Wales covers the subtropical Northern Rivers as the southern outdoor limit; Victoria covers growing it under glass or in a pot, because frost kills it outdoors.

**Why:** Correct, trustworthy guides for exactly the rare fruit our community collects earn search traffic and trust, which is the audience that feeds the Treesmith funnel (Track B supporting Track A). Starfruit also carries several facts the generic blurb got wrong or glossed: the flowers are heterostylous (short-style cultivars like Kembangan and Fwang Tung set best with a long-style pollinator like Arkin or Kary, but a single self-fruitful tree still crops), the fruit does NOT sweeten after picking so it must be picked ripe, it is a fruit-fly host (Queensland fruit fly in the east, Mediterranean fruit fly in WA), and there is a genuine kidney-disease eating caution (oxalates and caramboxin).

**Actions:**
- New tools/scrapers/growing_guides/starfruit.json (core + WA/QLD/NSW/VIC overlays, sources, curated further_reading).
- Added "starfruit": "tropical" to SPECIES_CLIMATE_CATEGORY in build_species_state_pages.py.
- Sourced archives-first from Benedict's owned RFC archives (QDPI carambola culture, the fruit-set/heterostyly paper, the varieties chart, the fact sheet and the oxalic-acid paper) and the WANATCA ACOTANC "Annonas and Carambolas" paper, then cross-checked against UF/IFAS, the Northern Territory Government, Business Queensland, DPIRD WA and a peer-reviewed star-fruit toxicity review.
- Moved the cross-cutting "unenriched species" test fixture off starfruit (now enriched) onto jujube; added tests/test_guide_starfruit.py with starfruit-specific correctness anchors.

**Status:** PR open, pending Benedict review. Full test suite green (823 tests). Every cited and further-reading URL verified HTTP 200. No em or en dashes.

**Note on live surface:** with current stock, starfruit ranks below the top-20 cut that generates QLD/NSW/VIC buy pages, so today the live change is a much better species page plus the Western Australia buy page (WA builds all species with 3+ in stock). The other three state overlays are built and tested and switch on automatically as stock grows.

**To revert:** delete growing_guides/starfruit.json (the page falls back to the generic blurb), revert the one SPECIES_CLIMATE_CATEGORY line, and restore the starfruit test fixture.
