# Per-state lime growing guide shipped for treestock (citrus)

**Decided by:** Dale (parallel guide run)

**Context:** Continuing the species growing-guide rollout (docs/species-guide-rollout.md) down the
priority order. Lime is the next high-traffic species in the citrus/temperate band (GSC: 7 clicks,
522 impressions, top state NSW), one of the citrus guides of the rollout (the orange guide,
PR #47, is its parallel sibling, so it shares the citrus climate notes and the RFCA Citrus archive
approach). The generic
fruit_species.json blurb was byte-identical across the WA/QLD/NSW/VIC combo pages and uncited.

**Decision:** Authored tools/scrapers/growing_guides/lime.json plus tests/test_guide_lime.py,
matching the olive gold standard: a cited, state-invariant core (variety choice, pollination,
planting and soil, a deep water-and-feeding section, harvest, buying) and four genuinely distinct
state overlays, mirroring the parallel orange guide's citrus approach but with lime-specific,
warmer-climate overlays (tropical north for QLD/WA, the subtropical coast for NSW, the cold limit
for VIC). Flagship is NSW (GSC traffic leader and a real citrus state: the Riverina is
Australia's largest citrus region, the subtropical Northern Rivers is the best lime coast), with QLD
as the warm-climate co-lead (it grows most of Australia's limes; the Atherton Tableland is the
biggest lime district), WA as the biosecurity standout (citrus import control via the WA Organism
List, canker-free status, Medfly), and VIC as the cold limit (pot-and-shelter country, Sunraysia
the one warm district). No code change: lime is already "citrus" in SPECIES_CLIMATE_CATEGORY, so
the shared citrus climate note already fits.

**Why:** Per-state-unique, cited content lifts these combo pages out of thin/duplicate-content
territory and supports the Treesmith funnel. Citrus is the right band to lean on .gov.au + industry
+ the owned RFCA Citrus archives rather than rare-fruit RFCA folders.

**Correctness notes (research, adversarially verified, every cited URL HTTP 200):**
- Tahitian (Persian/Bearss) lime is the standard: large, seedless, parthenocarpic, thornless, the
  hardiest true lime, with good TOLERANCE of tristeza (not "resistant", a guarded distinction).
- Rangpur and sweet lime are flagged as NOT true limes (Rangpur is a mandarin hybrid). Australian
  native limes (desert, round) and the CSIRO Blood/Red Centre and Sunrise hybrids are covered;
  finger lime is kept as the separate species it is, with a link to its page.
- WA is correctly NOT claimed free of citrus gall wasp (it is established across Perth since 2013);
  the WA pest story is Medfly + gall wasp established, Qfly a prohibited pest under active
  eradication. WA import control is framed via the WAOL/permit system and canker-free status (no
  single "citrus banned" gov sentence exists, so it is not asserted).
- Feeding meets the step-3b depth checklist: complete citrus fertiliser high in nitrogen (drives the
  spring flush), scaled to tree age and fed little and often, zinc foliar and iron/magnesium on
  alkaline soils, pH 6 to 6.5, cited to Citrus Australia, the QLD DAF citrus kit, the NT fact sheet
  and UF/IFAS.

**Sources:** owned RFCA Citrus archives (Improved Lemon and Lime Varieties, Citrus Rootstocks,
Citrus) cited and used as the Further reading block; plus DPIRD WA, Business Queensland, QLD DAF
citrus kit, Citrus Australia, CSIRO, UC Riverside and UF/IFAS. There is no clean RFCA "Lime" folder
and no lime-specific WANATCA yearbook article, so archive_links.json is unchanged (the regenerated
index is byte-identical) and Further reading is the hand-curated owned RFCA citrus articles.

**Actions:**
- Added growing_guides/lime.json (27 sources, core + 4 overlays, net-new FAQs).
- Added tests/test_guide_lime.py (uniqueness, no-dash, region-token leak, FAQ JSON-LD, sources,
  further-reading, plus correctness guards for tristeza wording, Rangpur, and the WA gall-wasp fact).
- Built against real stock: all four combo pages plus /species/lime.html render unique, cited,
  dash-free, with FAQ structured data, article OG, Sources and Further reading.

**Status:** PR open on branch dale/lime-guide, pending Benedict review and deploy. Logged
parallel-safe per docs/species-guide-rollout.md step 6 (pending fragment + per-entry ledger, no DEC
number, no decision-log.md or archive_links.json edit).

**To revert:** delete growing_guides/lime.json and tests/test_guide_lime.py; the species and combo
pages fall back to the generic fruit_species.json blurb automatically (has_guide returns False).
