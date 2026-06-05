# Pecan per-state growing guide (Carya illinoinensis), flagship NSW

**Decided by:** Dale (parallel guide run)

**Context:** Next species down the growing-guide rollout priority order after the batch-3 tail
(pecan, then macadamia, grape, pomegranate, passionfruit, feijoa). Pecan is a large deciduous nut
tree with healthy stock on treestock (daleys carries 7 varieties, conveniently labelled by
pollination type; fruitopia, ladybird, ross-creek and primal also list it). GSC and Plausible
produced nothing locally (no creds, the macOS `requests`-missing pattern), so the flagship was chosen
by climate plus production reality plus stock, like the recent batch.

**Decision:** Shipped `tools/scrapers/growing_guides/pecan.json` (one JSON file) with a state-invariant
`core` plus genuinely unique WA/QLD/NSW/VIC overlays, matching the olive gold standard. Flagship NSW
(the Gwydir Valley east of Moree grows the bulk of the national crop, and Stahmann's Trawalla is the
largest pecan operation in the southern hemisphere), with WA as the standout overlay: it is the only
combo page that renders from current stock, and it is the best-sourced state because pecan is a WA nut
tree with deep owned archive coverage (the WANATCA Stoneville variety trial + RFCA WA notes).

Pecan gets its OWN `SPECIES_CLIMATE_CATEGORY` ("pecan") plus four town-free `STATE_CLIMATE_NOTES`,
the banana/cherry/mulberry precedent: its limiting factor is a long, hot summer (heat units fill the
kernels), NOT winter chill, so the generic "temperate / choose low-chill varieties" note is the wrong
story for it. Added `tests/test_guide_pecan.py` (37 tests).

**Three corrections to the old `fruit_species.json` framing, each pinned by a test:**
1. Australia is currently FREE of pecan scab (Fusicladium effusum), the major overseas disease, so
   pecans here are grown largely without fungicides. This is a grower advantage and a quarantine
   reason, the OPPOSITE of the old "scab is the main disease in humid regions here" framing.
2. No pecan is reliably self-fruitful as a lone tree. The "self-pollinating" labels (Pabst, Western
   Schley) are nursery marketing, not extension science, so the guide says a single tree gives a
   light, unreliable crop and to plant a Type A (protandrous) plus a Type B (protogynous) for a full
   one. All 10 cultivar type assignments verified against UGA/NMSU (daleys' (A)=Type I / (B)=Type II
   labelling is correct).
3. WA quarantine is real (WAOL listing, certification, treatment); the old draft's "no quarantine
   restrictions apply to pecan entering WA" is false and was dropped for the standard DPIRD framing.

**Archives:** the RFCA pecan articles sit in the mixed-genus `Nuts` folder (macadamia, pili, saba,
pecan...), which `build_archive_index.py` does NOT map to a slug, so `archive_links.json` stays
byte-identical (no pecan key) and the owned Further reading (3 RFCA `Nuts` pecan articles + WANATCA
yearbooks Y16/Y5/Y6/Y17) is hand-curated, the dragon-fruit / finger-lime mixed-folder pattern. Both
WANATCA (the WA nut-tree association covers pecans richly) and RFCA appear in Further reading.

**Sources:** 25, all 26 cited + Further-reading URLs return HTTP 200 to a browser UA. Owned RFCA +
WANATCA first; then the Australian Pecan Growers, DPIRD WA, Queensland DAF, Gwydir Valley Irrigators,
Business Queensland, and US university pecan extension (UGA / NMSU, the global reference for the crop).
NSW DPI, Agriculture Victoria and APHIS were avoided because they 403/000 to the curl-200 gate; a test
guard locks those domains out, so the NSW heartland claims are anchored on Australian Pecan Growers +
Gwydir Valley Irrigators + Queensland DAF/Country Life instead.

**Actions:** Added `growing_guides/pecan.json`, the `pecan` climate category + 4 state notes in
`build_species_state_pages.py`, and `tests/test_guide_pecan.py`. Full suite green (840 tests). Built
against real stock: the WA combo page and `/species/pecan.html` render cited, dash-free, per-state
unique, with FAQ JSON-LD, Sources and Further reading; QLD/NSW/VIC overlays are authored and
force-verified but currently sit below the QLD/NSW/VIC top-20 in-stock cut, so they light up when
stock climbs (judge done on the species page, the tamarillo rule).

**Status:** PR open on `dale/pecan-guide`, pending Benedict review. Not merged.

**To revert:** delete `growing_guides/pecan.json` (the species falls back to the generic blurb via
`has_guide`), remove the `pecan` entries from `SPECIES_CLIMATE_CATEGORY` and `STATE_CLIMATE_NOTES`,
and delete `tests/test_guide_pecan.py`.
