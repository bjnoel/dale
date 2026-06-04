# Orange growing guide (per-state-unique, NSW flagship; citrus rootstock and biosecurity researched archives-first)

**Decided by:** Dale (parallel guide run)

**Context:** Continuing the per-species growing-guide rollout (olive DEC-126 flagship, the archive
integration DEC-127, and the batch through DEC-140), orange (Citrus sinensis) is the next species to
get a rich, per-state-unique, cited growing guide on the buy-orange-trees-[state] combo pages and
/species/orange.html. Orange is the most popular backyard citrus in Australia and a high-value SEO
target, and it is genuinely a multi-state crop, so every generated state earns a real overlay. With
56 orange products in stock across the monitored nurseries, all four states (WA 29, QLD/NSW/VIC 51
shippable each) cross the in-stock threshold, so all four combo pages render live now plus the
species page.

**Decision:** Add `tools/scrapers/growing_guides/orange.json` (39 sources, a state-invariant core of
eight sections, four genuinely distinct state overlays, four core and eight state FAQs, and a curated
owned "Further reading" list) plus `tests/test_guide_orange.py`. No builder code change was needed:
orange is already `citrus` in `SPECIES_CLIMATE_CATEGORY` (the citrus climate notes already exist for
all four states) and `build_archive_index.py` already aliases `oranges -> orange`.

Flagship is **New South Wales**: GSC/Plausible produced nothing locally (no creds, as on recent
runs), so the flagship was chosen on production reality and climate. The Riverina (Murrumbidgee
Irrigation Area, Griffith and Leeton) is the single largest citrus district in Australia and the
country's biggest orange-producing region (Citrus Australia, Murrumbidgee Irrigation), so NSW was
researched deepest. VIC (Sunraysia navels plus the cool-night blood-orange advantage), QLD (Central
Burnett heartland, the Emerald canker history) and WA (Mediterranean south-west, Medfly, quarantine)
all got strong, unique overlays.

**Why:** Each combo page used to share a byte-identical generic blurb. The guide makes WA/QLD/NSW/VIC
genuinely different and cited, lifts the SEO value of the highest-traffic citrus species, and feeds
the Treesmith funnel by being the kind of page a serious citrus grower trusts. Built archives-first
on Benedict's owned Rare Fruit Council "Citrus" articles (rootstocks, fruit characteristics, blood
oranges) and a WANATCA ACOTANC paper, which keeps first-party authority in-network.

**Actions:**
- `growing_guides/orange.json` + `tests/test_guide_orange.py` (mirrors the olive/lychee guards plus
  orange-specific correctness guards). Full suite green (536 tests). All 40 cited and further-reading
  URLs return HTTP 200. Pages build per-state-unique, dash-free, with FAQ JSON-LD, article OG,
  Sources and Further reading; no region tokens leak across states (verified on the real pages).
- `archive_links.json` deliberately NOT changed: the RFCA `Citrus` folder is a mixed-genus bucket
  (lemon, lime, cumquat, pummelo as well as orange), so aliasing it to orange would surface the wrong
  fruit. Instead the orange-specific RFCA Citrus articles are hand-curated into `further_reading`
  (the dragon-fruit / papaya mixed-folder pattern).
- Two correctness calls the research corrected, each pinned by a test so a future edit cannot
  reintroduce them: (1) Queensland's citrus canker outbreak was at **Emerald in 2004** (eradicated;
  Australia declared free in 2021), NOT a 2018 Emerald outbreak (2018 was Darwin NT and WA);
  (2) WA is **not** free of citrus gall wasp (it has been in Perth backyards since 2013) but is free
  of it in commercial orchards and country districts, and Medfly, not Queensland fruit fly, is the
  WA citrus pest.
- Sources avoid `dpi.nsw.gov.au` and `agriculture.vic.gov.au` (both 403 to curl, so they would fail
  the URL-200 gate); the NSW and VIC facts are anchored on Citrus Australia, Murrumbidgee Irrigation,
  USDA FAS, SGA, Business Queensland, DPIRD WA, IPPC/DAFF and university extension instead. A test
  guards against reintroducing the bot-blocked domains.

**Status:** PR open on branch `dale/orange-guide`, pending Benedict review. On approval: merge,
`ssh dale-server`, `git pull`, `tools/deploy.sh`, rebuild combo + species pages into the dashboard,
rebuild purged Tailwind, verify live.

**To revert:** delete `growing_guides/orange.json` and `tests/test_guide_orange.py`. `has_guide("orange")`
returns False again and both builders fall back to the generic `fruit_species.json` blurb. No other
code touched.
