# Pear growing guide (per-state-unique, VIC flagship; the pick-firm-ripen-off-tree pome story researched archives-first)

**Decided by:** Dale (parallel guide run)

**Context:** Continuing the per-species growing-guide rollout (olive DEC-126 flagship, archive
integration DEC-127, the batch through DEC-140, and the citrus batch DEC-141..145), pear (Pyrus
communis) is the next species to get a rich, per-state-unique, cited growing guide on the
buy-pear-trees-[state] combo pages and /species/pear.html. Pear is the pome-fruit cousin of the
already-shipped apple guide and a real SEO target: GSC shows /species/pear.html already pulling 429
impressions but ranking poorly (position 35.9, 4 clicks), exactly the underperformance a cited guide
fixes. With 28 to 34 pear products in stock per state, all four states cross the in-stock threshold,
so all four combo pages render live now plus the species page.

**Decision:** Add `tools/scrapers/growing_guides/pear.json` (26 sources, a state-invariant core of
seven sections, four genuinely distinct state overlays, four core and two-per-state FAQs, and a
curated owned "Further reading" link) plus `tests/test_guide_pear.py`. No builder code change was
needed: pear is already `temperate` in `SPECIES_CLIMATE_CATEGORY` (the temperate climate notes
already exist for all four states), and there is no RFCA `Pear` folder (pear is not a rare fruit), so
`build_archive_index.py` output is unchanged and `archive_links.json` has no pear key, exactly like
apple. Further reading is therefore the one hand-curated WANATCA Nashi article (owned, followed), no
auto-merged RFCA links.

Flagship is **Victoria**: GSC confirmed demand but gave no state split (no buy-pear-trees-[state]
pages rank yet, which is the opportunity), and Plausible/GSC have no local creds, so the flagship was
chosen on production reality. Victoria's Goulburn Valley grows about 90 per cent of Australia's pears
(Australian Pears / APAL), so VIC was researched deepest: the canning-pear heritage (Williams Bon
Chretien is Bartlett, the SPC cannery from 1917), the Tatura Trellis, and the variety split (Packham
60 per cent, Williams 20, Bosc 10). NSW (the Packham's Triumph birthplace at Garra near Molong), WA
(Southern Forests, nashi in the Swan Valley, free of codling moth) and QLD (the high Granite Belt
plus nashi and low-chill pears for the subtropics) all got strong, unique overlays.

**Why:** Each combo page used to share a byte-identical generic blurb. The guide makes WA/QLD/NSW/VIC
genuinely different and cited, lifts a high-impression underperforming species, and feeds the
Treesmith funnel by being the kind of page a serious pear grower trusts. It leans on the verified
apple sources (pome cousins share pests, quarantine and rootstock habits) plus pear-specific
authorities, and cross-links to /species/apple.html (apple already cross-links back to pear).

**Actions:**
- `growing_guides/pear.json` + `tests/test_guide_pear.py` (mirrors the olive/apple guards plus
  pear-specific correctness guards). Full suite green (630 tests). All 27 cited and further-reading
  URLs return HTTP 200. Pages build per-state-unique, dash-free, with FAQ JSON-LD, article OG,
  Sources and Further reading; no region tokens leak across states (verified on the real pages).
- The signature pear fact is pinned by tests: European pears are picked firm and ripened OFF the tree
  (left in place they go brown and gritty at the core), with winter pears (Beurre Bosc, Josephine,
  Winter Nelis) needing a cold spell before they ripen, while nashi are the tree-ripened exception.
- Correctness calls pinned by tests so a future edit cannot reintroduce them: WA is free of codling
  moth and of fire blight (the serious pear disease, absent Australia-wide) but DOES have pear and
  cherry slug; the WA fruit fly is Medfly, not Queensland fruit fly; Packham's Triumph (Garra near
  Molong, the Uvedale St Germain x Williams cross) is an NSW-only story.
- Sources avoid `agriculture.vic.gov.au` and `apal.org.au` (both 403 to curl, so they would fail the
  URL-200 gate); pear scab is anchored on the extensionAUS Apple and Pear IPDM black-spot page (same
  trusted domain as the apple codling-moth source) instead. The Packham year (often cited as 1896)
  was left out: no fetchable source confirmed it, and the museum origin page omits it, so the guide
  states the verified facts (breeder, place, cross, ~60 per cent of the national crop) without a year.

**Status:** PR open on branch `dale/pear-guide`, pending Benedict review. On approval: merge,
`ssh dale-server`, `git pull`, `tools/deploy.sh`, rebuild combo + species pages into the dashboard,
rebuild purged Tailwind, verify live.

**To revert:** delete `growing_guides/pear.json` and `tests/test_guide_pear.py`. `has_guide("pear")`
returns False again and both builders fall back to the generic `fruit_species.json` blurb. No other
code touched.
