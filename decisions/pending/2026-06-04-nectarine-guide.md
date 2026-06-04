# Nectarine growing guide (per-state-unique, VIC flagship; smooth-skin agronomy researched and adversarially verified)

**Decided by:** Dale (parallel guide run)

**Context:** Continuing the per-species growing-guide rollout (olive DEC-126 flagship, archive
integration DEC-127, the batches through DEC-145), nectarine (Prunus persica var. nucipersica) is
the next species down the priority tail to get a rich, per-state-unique, cited growing guide on the
buy-nectarine-trees-[state] combo pages and /species/nectarine.html. A nectarine is botanically a
smooth-skinned peach, so peach (already shipped) is the closest model, but nectarine needed its own
guide rather than a peach copy: the fuzz-free skin is a genuine agronomic difference and a duplicate
peach page would be poor for both readers and SEO. With 43 nectarine products in stock across the
monitored nurseries, all four states cross the in-stock threshold, so all four combo pages render
live now (WA via Guildford, Daleys, Diggers, Fruit Salad Trees; the east via Ladybird and Ross
Creek) plus the species page.

**Decision:** Add `tools/scrapers/growing_guides/nectarine.json` (22 sources, a state-invariant core
of nine sections, four genuinely distinct state overlays, four core and two-per-state FAQs) plus
`tests/test_guide_nectarine.py`. No builder code change was needed: nectarine is already `temperate`
in `SPECIES_CLIMATE_CATEGORY` (it inherits the stone-fruit chill-hours climate note, exactly like
peach), and like peach it has NO owned-archive "Further reading" (there is no RFCA Nectarine folder
and no WANATCA nectarine article, confirmed by grep of both local archives and by running
build_archive_index.py, which leaves archive_links.json byte-identical), so the file is left
untouched.

Flagship is **Victoria**: GSC/Plausible produced nothing locally (no `requests` module / no creds,
as on recent runs), so the flagship was chosen on production reality and climate. Victoria grows
about two thirds of Australia's nectarines (SEDA Export: nectarines 66 per cent, peaches 81 per
cent), centred on the Goulburn Valley (Shepparton, Cobram) and the irrigated Sunraysia (Mildura,
Swan Hill), and the dry inland air particularly suits a nectarine's brown-rot-prone smooth skin, so
Victoria was researched deepest. Every other state still earns a real, distinct overlay: WA gets the
strongest unique overlay (the quarantine and shipping angle plus Benedict's WA audience: Donnybrook,
Perth Hills, the Southern Forests, Medfly, Prunus quarantine), QLD splits Granite Belt high-chill
from low-chill subtropics (humidity makes brown rot worse on a fuzzless nectarine), and NSW spans the
low-chill Sydney basin (Bilpin) to the high-chill Central Tablelands (Orange, Bathurst) and Batlow.

**The nectarine-specific story (what makes it not a peach copy), each fact cited and verified 200:**
- The fruit is a smooth-skinned peach, the same species, caused by a single recessive gene; it is
  NOT a peach crossed with a plum (a common myth). [Missouri IPM, Missouri Extension G6030]
- The bare skin gives less protection, so nectarines are more prone than peaches to brown rot
  (Clemson) and are more susceptible than peaches to bacterial spot (Michigan State, Missouri
  G6030); thrips and wind scar or silver the exposed skin (UC IPM). The guide turns this into
  practical advice (airflow, hard early thinning, clean prompt picking, a dry/airy site).
- Feeding depth meets the step-3b bar with a cited figure: the Queensland low-chill stonefruit kit's
  12:5:14 NPK at about 435 g per mature open-vase tree in late winter and early autumn with ~185 g
  spring and midsummer top-ups, plus the three make-or-break soil-moisture windows.

**Two corrections that differ from the now-stale peach guide (both flagged for a peach follow-up):**
1. WA is NOT "free of" Queensland fruit fly. The live DPIRD Qfly page shows Qfly is a declared,
   prohibited pest eradicated whenever it is detected (the peach guide, citing the same page, still
   says "free of"). The nectarine WA overlay uses the accurate "eradicated whenever it is detected"
   framing and a test guards it.
2. The Riverina is no longer safely citable as a "major producer of peaches and nectarines" (Letona
   cannery closed 1993, tree-pull program; no current 200-OK source supports it, and NSW DPI 403s to
   curl). The nectarine NSW overlay does not make that claim, anchoring NSW regions on FAO (Orange,
   Batlow) instead.

**Actions:**
- Authored nectarine.json and test_guide_nectarine.py; full suite green (635 tests), including the
  generic FAQ-overlap guard over every guide.
- Researched archives-first (no nectarine archive content exists), then state agriculture departments
  and university extension; all 22 cited URLs confirmed HTTP 200 with a browser UA; no Wikipedia,
  and the two WAF-403 domains (dpi.nsw.gov.au, agriculture.vic.gov.au) deliberately not cited (a test
  locks them out).
- Built all four combo pages plus /species/nectarine.html from real stock: per-state-unique, cited,
  zero em or en dashes, FAQ JSON-LD, article OG, Sources, no Further reading, region tokens never
  leaking across states.

**Status:** PR open, pending Benedict review. Logged parallel-safe (this fragment plus a per-entry
public-ledger file); no DEC number chosen, no edit to decision-log.md, the rollout Progress list,
the shared daily ledger, or archive_links.json. Close-out (fold_pending_decisions.py) assigns the
DEC number after merge.

**To revert:** delete tools/scrapers/growing_guides/nectarine.json and tests/test_guide_nectarine.py;
the builders fall back to the generic fruit_species.json blurb (has_guide goes False), no other code
depends on it.

**Follow-up for Benedict (separate from this PR):** the peach guide's WA section now cites the DPIRD
Qfly page for an outdated "free of Queensland fruit fly" claim, and its NSW section calls the Riverina
a major peach and nectarine producer. Both are worth correcting in peach.json on a future pass.
