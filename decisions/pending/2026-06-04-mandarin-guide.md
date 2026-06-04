# Per-state mandarin growing guide for treestock (citrus, QLD flagship, all four states live)

**Decided by:** Dale (parallel guide run)

**Context:** Mandarin was next in the treestock growing-guide rollout (GSC: 8 clicks, 546
impressions over 28 days; tier 4 "high traffic, citrus, lean on .gov.au + WANATCA + web"). Until now
the buy-mandarin-trees-<state> pages and /species/mandarin.html shared one short, uncited blurb.
Mandarin is already classed `citrus` in `SPECIES_CLIMATE_CATEGORY`, so this needed only a new JSON
file plus its test, no builder change.

**Decision:** Ship `tools/scrapers/growing_guides/mandarin.json` (a cited, per-state guide) and
`tests/test_guide_mandarin.py`. Flagship QLD by production and climate (the Central Burnett around
Gayndah and Mundubbera is Australia's largest mandarin district, the Imperial heartland), but mandarin
is a genuine four-state crop, so every state earns a first-class overlay: WA (the citrus-import
quarantine and the WA Organism List, Gascoyne and the south-west belt, Medfly not Queensland fruit
fly, citrus gall wasp in Perth backyards but not commercial orchards), QLD (Central Burnett, the
citrus canker history at Emerald in 2004 and the 2021 national freedom, Queensland fruit fly), NSW
(the Riverina around Griffith and Leeton, citrus gall wasp as the headline pest), and VIC (Sunraysia
around Mildura and Robinvale, cool nights for deeper rind colour, the cold-hardy Satsumas for frosty
districts). All four combo pages generate on current stock.

**Why:** The defining mandarin facts are unusual and worth getting right: a single tree fruits without
a pollinator (parthenocarpy), yet self-incompatible varieties (Clementine, Afourer, Imperial) turn
seedy when bees bring pollen from other citrus nearby, so seedlessness is about isolation, not a
partner tree. The guide leads on that, plus the heavy-nitrogen feeding (with cited rates), the
non-climacteric harvest and why mandarins puff and dry if left too long, grafting onto a rootstock
(Flying Dragon for pots), and the citrus canker biosecurity that explains the many "pickup only" and
"QLD only" listings. Deeper, cited, per-state-unique guides earn search traffic and community trust,
the Track B audience that feeds the Treesmith funnel.

**Actions:**
- Authored `growing_guides/mandarin.json`: 36 sources (gov: DPIRD WA, Business Queensland,
  Queensland Agrilink, Gascoyne Development Commission, WA Government; industry: Citrus Australia, WA
  Citrus, Farm Biosecurity, Sustainable Gardening Australia, Bayer; university: UC Riverside, UF/IFAS,
  UC ANR; owned: RFCA citrus articles and a WANATCA ACOTANC citrus paper). Variety advice tied to live
  stock (Imperial, Emperor, Hickson, Afourer, Honey Murcott, Ellendale, Satsuma, Clementine, Daisy,
  Fremont, Pixie, Sumo).
- Added `tests/test_guide_mandarin.py`; full suite green (533 tests), including the FAQ-overlap guard.
- Curl-verified all 36 cited and further-reading URLs return 200; built against live stock and
  reviewed all four combo pages plus the species page (dash-free, per-state-unique, FAQ JSON-LD,
  article OG, Sources, Further reading).

**Status:** PR open, pending Benedict review. Parallel-safe logging (this fragment plus a per-entry
public-ledger file); decision-log.md and archive_links.json left untouched (the RFCA Citrus folder is
mixed-genus, so it is not auto-indexed to mandarin; the further_reading links are hand-curated).

**To revert:** delete `growing_guides/mandarin.json` and `tests/test_guide_mandarin.py`; the combo and
species pages fall back to the generic `fruit_species.json` blurb (graceful, no code change).
