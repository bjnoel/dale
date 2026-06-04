# Sapodilla growing guide (per-state-unique, archives-first; QLD flagship)

**Decided by:** Dale (parallel guide run)

**Context:** Following the olive flagship (DEC-126), the archive integration (DEC-127) and the
lychee/fig/peach/tamarillo/guava/mango/plum/longan guides, sapodilla (Manilkara zapota; also chico,
chiku, sapota, naseberry) is the next species to get the rich, per-state-unique, cited growing guide
on the buy-sapodilla-trees-[state] combo pages and /species/sapodilla.html. Sapodilla is a genuinely
rare, hard-to-source tropical fruit with a deep, owned Rare Fruit Council archive (a "Sapodilla in
Australia" culture article with North Queensland flowering and harvest timing, a full fact sheet,
and a clonal-propagation article), and the live stock matches the research: the named grafted
varieties on sale (Krasuey, Sawo Manila and Ponderosa at Ross Creek) are the Asian selections the
guide recommends, alongside the international standards (Alano, Prolific, Brown Sugar) and the dwarf
Makok for pots. Flagship was chosen data-driven: GSC shows /species/sapodilla.html earning about 160
impressions a month (9 clicks, position 9.8, indexed) but NO buy-sapodilla-trees-[state] combo
entrances at all, so traffic does not pick a state; climate does. Sapodilla is strictly tropical, so
the Australian heartland is far north Queensland (the Northern Territory around Darwin grows the
most but is not a generated state), making QLD the horticultural flagship, researched deepest.

**Decision:** Ship `growing_guides/sapodilla.json` mirroring olive.json/mango.json. The additive
design held again: one new guide JSON plus a dedicated test file, no builder edits. Sapodilla already
sits in the existing "tropical" climate category (no new category needed, unlike olive's
"mediterranean"), and it was already present in the shared `growing_guides/archive_links.json` (its
RFCA folder predates this work), so neither shared-edit conflict point was touched.

**What shipped (PR branch dale/sapodilla-guide, pending Benedict review/merge/deploy):**
- `growing_guides/sapodilla.json`: 16 verified sources, a state-invariant `core` (choosing a
  variety; seedling vs grafted; the "do you need two trees?" pollination nuance; planting and soil;
  water and feeding with the long-used Australian 10:2:17 plus dolomite schedule; harvest and
  ripening, which is sapodilla's defining grower challenge because the fruit gives so few signs of
  maturity; pruning and size; buying tips) plus genuinely distinct WA/QLD/NSW/VIC overlays (climate
  fit, regions, harvest window, pests, and WA quarantine/shipping). Variety advice ties to live stock
  (Krasuey, Sawo Manila, Ponderosa, dwarf Makok).
- Two correctness wins over the generic blurb, both cited and adversarially cross-checked:
  - Pollination: the guide does NOT repeat the blurb's flat "sapodilla is self-fertile". UF/IFAS is
    explicit that some cultivars are self-incompatible (need a second tree/seedling) while others
    fruit alone but crop more heavily cross-pollinated, so the guide says exactly that.
  - Pests: sapodilla IS a Queensland fruit fly host (Business Queensland's commercial host list and
    Plant Health Australia's fruit-fly resource both name it). The "latex skin makes it resistant"
    idea is a sapote/sapodilla naming confusion (it refers to mamey sapote, Pouteria sapota) and was
    deliberately kept off the page; the QLD/NSW overlays tell growers to bag or bait.
- Archives first: the Australian-specific facts (North Queensland flowering November to February,
  fruit maturing seven to nine months later, main northern harvest around September to November, the
  scratch-and-scurf maturity test, the pollen-sterility caveat for seedlings, grafting by side
  veneer) are grounded in Benedict's RFCA sapodilla articles, then cross-checked against UF/IFAS and
  Morton (Fruits of Warm Climates) for the cold-tolerance numbers (young trees killed near minus 1
  degree, mature trees take brief cold to about minus 3 degrees) and cultivars, the NT Government
  fruit-availability page (sapodilla grown around Darwin, picked year-round), DPIRD WA (Carnarvon,
  Kununurra/Ord, Mediterranean fruit fly, Quarantine WA), the Gascoyne Development Commission, RDA
  Northern Rivers and the Bureau of Meteorology (Melbourne winter minima, to anchor "not a Victorian
  crop"). Further reading leads with the WANATCA yearbook article "The Sapodilla in Southeast Asia"
  (Coronel, Vol 23) and Benedict's RFCA sapodilla archives.

**Verification:**
- Full test suite green (374 tests), including the per-state uniqueness, no-dash, FAQ-overlap and
  FAQ-JSON-LD guards, plus a new `tests/test_guide_sapodilla.py` with sapodilla-specific anchors
  (the pollination nuance, the QFF host flag, and the stocked cultivars).
- The four state pages build unique per state with no region names leaking across states, zero em or
  en dashes, FAQ structured data, article OG, cited Sources and a Further reading list. The species
  page renders the cited core, FAQ and Sources. Every cited and further-reading link returns HTTP 200
  (re-checked on the rendered pages).
- With today's local stock the species page renders immediately; the QLD/NSW/VIC/WA combo overlays
  switch on automatically as soon as in-stock sapodilla crosses the per-state threshold (the overlays
  themselves were verified by force-building all four from real stock).

**Status:** PR open, awaiting Benedict review. Do not merge unilaterally.

**To revert:** delete `tools/scrapers/growing_guides/sapodilla.json` and
`tests/test_guide_sapodilla.py`; the species and combo pages fall back to the generic blurb with no
code change.
