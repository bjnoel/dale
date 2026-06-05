# Pomegranate per-state growing guide on treestock (WA flagship), with its own climate category

**Decided by:** Dale (parallel guide run)

**Context:** Pomegranate is on the species-guide rollout list (docs/species-guide-rollout.md). It is a
Mediterranean-climate fruit (hot dry summers, low winter chill) whose Australian commercial heartland
is South Australia's Riverland and Victoria's inland (the country's single largest grower is in the
Goulburn Valley, not SA as first assumed). But treestock's owned archives for pomegranate are
overwhelmingly Western Australian: the Agriculture WA cultivar trial at Medina, a grower account from
Yarloop, and an ACOTANC orchard paper from Yallingup. GSC and Plausible (queried on the server) show
pomegranate demand is variety-led (the dwarf-parfianka variety page earns the most search interest)
with only a thin Queensland combo-page signal, so flagship choice fell to climate plus the depth of
first-party WA material. Pomegranate also had no climate category yet, so it would have inherited the
generic note, which misses its decisive per-state story: fruit splitting and rot in humidity.

**Decision:** Ship a cited, per-state pomegranate guide (tools/scrapers/growing_guides/pomegranate.json)
matching the olive implementation, flagship WA, with every state given a genuine, unique overlay. Give
pomegranate its OWN climate category ("pomegranate") in build_species_state_pages.py with accurate,
dash-free per-state notes, rather than fold it into the shared "mediterranean" note (which a parallel
grape run may also be editing, and which says nothing about splitting).

**Why:** Correctness is the rollout's first rule. The headline fact for pomegranate is fruit splitting:
a dry-climate crop cracks when rain or erratic watering hits near-ripe fruit, so the core and every
state note lead with it. The guide also corrects three things the generic copy could not: pomegranates
are self-fruitful (one tree crops; a second only lifts the set), they are non-climacteric (they do not
ripen after picking, so they must be picked fully ripe), and the fruit fly differs by region
(Mediterranean fruit fly in WA, where pomegranate's thick rind keeps it off DPIRD's host list, versus
Queensland fruit fly in the east, where pomegranate IS a listed host). Variety advice is tied to live
stock (Wonderful, Gulosha Rosavaya, Azerbaijani, Midnight Velvet, Red Velvet, Elche, Parfianka, Veles)
and, for WA, to the Medina trial's actual verdicts (Gulosha Rosavaya best, Wonderful next).

**Actions:**
- New growing_guides/pomegranate.json: 22 sources (Diggers, City of Darwin gov fact sheet, AgriFutures
  management guide + industry overview, UGA / USU / Purdue NewCROP / UC ANR / UC IPM extension, DPIRD
  medfly + import quarantine, Business Queensland fruit fly, Green Harvest, Talga Estate, Rare Fruit
  Society SA, plus the owned RFCA Burt / Loeffler / Burmistrov / 1987 articles and the Cohen ACOTANC
  paper), a shared core + WA/QLD/NSW/VIC overlays, and WANATCA-yearbook + ACOTANC Further reading that
  auto-merges with the five RFCA pomegranate archive links.
- build_species_state_pages.py: added SPECIES_CLIMATE_CATEGORY["pomegranate"] = "pomegranate" and
  matching STATE_CLIMATE_NOTES for all four states (the notes carry no named regions, so nothing leaks
  across state pages).
- New tests/test_guide_pomegranate.py (24 tests): per-state uniqueness and no region-token leaks, no
  dashes, FAQ JSON-LD, Sources, WANATCA + RFCA Further reading followed, dedicated climate category, and
  correctness guards (splitting flagged everywhere, non-climacteric harvest, one-tree pollination, the
  right fruit fly per region).

**Status:** PR open (branch dale/pomegranate-guide), pending Benedict review. Full suite green (827
tests); all 24 cited and further-reading URLs return HTTP 200; worst FAQ/section overlap 0.33 (limit
0.45). With current stock all four combo pages generate (WA has enough WA-shipping stock; pomegranate
makes the top-20 in QLD/NSW/VIC). Per the parallel-batch protocol, this branch does not edit
decision-log.md, the shared daily ledger, the rollout Progress list, or archive_links.json; those are
folded at batch close-out.

**To revert:** delete tools/scrapers/growing_guides/pomegranate.json and tests/test_guide_pomegranate.py,
and remove the pomegranate entries from SPECIES_CLIMATE_CATEGORY and STATE_CLIMATE_NOTES in
build_species_state_pages.py. The species and combo pages fall back to the generic fruit_species.json
blurb automatically (has_guide returns False).
