# Macadamia growing guide: the native Australian nut, with the phosphorus and pest myths corrected

**Decided by:** Dale (parallel guide run)

**Context:** Continuing the per-species growing-guide rollout (olive infrastructure, see the
shipped olive/citrus/stone-fruit batches). Macadamia is next down the priority order after the
pecan/macadamia/grape/pomegranate/passionfruit/feijoa group. The generic fruit_species.json blurb
for macadamia carried two outright errors and one oversimplification that a real guide had to fix.

**Decision:** Ship a full, per-state, evidence-backed macadamia guide (one
`growing_guides/macadamia.json` plus a one-line `SPECIES_CLIMATE_CATEGORY` entry mapping macadamia
to the existing `subtropical` note, plus `tests/test_guide_macadamia.py`). Flagship state is WA: it
is the only state that generates a combo page from current stock (Guildford WA carries it, plus
Daleys), and the standout owned source is WANATCA Yearbook 17, "The future for macadamia nuts in
Western Australia" by David Noel (WANATCA's founder). QLD/NSW/VIC overlays are authored and tested
and light up when stock crosses the top-20 cut (the tamarillo "judge done on the species page" rule).

**Why:** /species/macadamia.html and the buy-macadamia-trees-[state] pages shared a generic,
uncited blurb. Macadamia is a high-value native crop with a strong rare-fruit/heritage angle and
good owned archive coverage (WANATCA has ~20 yearbook articles; the RFCA "Nuts" folder has owned
macadamia content), so it is a strong candidate for a richer, more trustworthy page.

**Three corrections the research forced (each pinned by a test):**
- The old blurb called the **macadamia felted coccid "the main pest in Australia."** It is not: the
  felted coccid is a NATIVE Australian scale, usually minor here (held down by native parasitoids),
  and is the destructive INVADER only overseas (Hawaii 2005, South Africa 2017). The real flagship
  insect pest is the macadamia nut borer (Business Queensland; peer-reviewed felted-coccid study).
- The blurb implied macadamia **is a fruit fly pest** by analogy with other crops. It is NOT a fruit
  fly host: the hard woody shell excludes it, and it is absent from the Queensland fruit fly
  commercial host list. Framed as an advantage on the QLD/NSW pages.
- The blurb said macadamia is **"sensitive to phosphorus; use low-phosphorus native-plant
  fertiliser."** Honest balance: the AMS does recommend a low-P native blend for backyard trees, so
  the practical advice is kept, but the BIOLOGY is corrected. Macadamia IS fed phosphorus in
  commercial orchards (Stephenson et al. 2002, Qld DPI; "high rates of P were being applied
  throughout the Australian industry"); the real hazard is a large EXCESS of P (iron-deficiency
  chlorosis, depressed yield, cluster-root suppression), and it tolerates field rates that would
  harm an ornamental banksia. The guide says exactly that.

**Sourcing:** owned first (WANATCA Yearbooks 5/9/17/26 incl. the Cull fertiliser and Stephenson
agronomy papers, and the David Noel WA article; RFCA "Nuts" folder articles for home preparation and
cultivars), then verified-200 authorities: Australian Macadamia Society, Business Queensland, Qld DPI
grower's handbook, DPIRD WA (the plant-import/quarantine reality, which the blurb wrongly waved away),
ASPCA (toxic to dogs), BeeAware (self-incompatibility + cross-pollination), QAAFI (husk spot), ANPSA
and DCCEEW (the threatened wild-macadamia heritage angle), Hidden Valley Plantations + the A4 plant
patent (the Bell "A" series). Every cited and further-reading URL returns HTTP 200 under a browser
UA. No RFCA "Macadamia" folder exists, so `archive_links.json` is byte-identical (not committed) and
further reading is hand-curated owned links only.

**Actions:**
- Added `tools/scrapers/growing_guides/macadamia.json` (34 sources, 8 core sections + 4 FAQs, four
  unique state overlays + 2 FAQs each, 4 curated owned further-reading links).
- Added `"macadamia": "subtropical"` to `SPECIES_CLIMATE_CATEGORY` in
  `build_species_state_pages.py` (the existing subtropical WA/QLD/NSW/VIC notes are accurate for
  macadamia, including the WA quarantine line; no new category, low merge-conflict risk).
- Added `tests/test_guide_macadamia.py` (21 tests: per-state uniqueness, region-token leak guard,
  no dashes, the three correctness corrections, pollination, two species, dog toxicity, FAQ JSON-LD,
  sources, further reading). Full suite green (824 tests).

**Status:** PR open, pending Benedict review. Not yet merged or deployed.

**To revert:** delete `growing_guides/macadamia.json` and `tests/test_guide_macadamia.py`, and
remove the one `SPECIES_CLIMATE_CATEGORY` line. has_guide("macadamia") returns False and both pages
fall back to the generic fruit_species.json blurb.
