# Apricot growing guide (per-state-unique, WA flagship; self-fertile and summer-pruning correctness pinned; bot-blocked gov domains avoided)

**Decided by:** Dale (parallel guide run)

**Context:** Continuing the per-species growing-guide rollout (olive DEC-126 flagship, archive
integration DEC-127, the batch through DEC-140, and the citrus + apple batch DEC-141..145), apricot
(Prunus armeniaca) is the next species to get a rich, per-state-unique, cited growing guide on the
buy-apricot-trees-[state] combo pages and /species/apricot.html. Apricot is a temperate stone fruit,
so it sits alongside peach and plum. Of the 21 in-stock apricot listings across the monitored
nurseries, only Western Australia crosses the in-stock threshold for a live combo page right now
(apricot does not crack the QLD/NSW/VIC top-20, which are dominated by citrus, apple, mango and the
like), so WA plus the species page render live today. All four state overlays are still authored: the
tests build all four, and the eastern pages will render the moment stock grows.

**Decision:** Add `tools/scrapers/growing_guides/apricot.json` (44 sources, a state-invariant core of
nine sections, four genuinely distinct state overlays, four core and eight state FAQs) plus
`tests/test_guide_apricot.py`. No builder code change was needed: apricot is already `temperate` in
`SPECIES_CLIMATE_CATEGORY` (the stone-fruit chill-hours climate note already exists for all four
states), and there is no RFCA Apricot folder and no WANATCA apricot yearbook article, so
`build_archive_index.py` produces no apricot entries and `archive_links.json` is unchanged.

Flagship is **Western Australia**: GSC/Plausible produced nothing locally (no creds, as on recent
runs, and SSH credential scouting was correctly out of scope for the research phase), so the flagship
was chosen on production reality and climate. WA is the only state with a live apricot combo page, it
is the operator's home turf (matching the olive precedent), and its dry south-west spring is a genuine
disease advantage for a fruit that hates humidity. WA was researched deepest (Gingin, the Perth Hills
around Karragullen and Pickering Brook, and Donnybrook). QLD, NSW and VIC all got strong, unique
overlays.

**Why:** Each combo page used to share a byte-identical generic blurb. The guide makes WA/QLD/NSW/VIC
genuinely different and cited, lifts the SEO value of an early-season backyard favourite, and feeds the
Treesmith funnel by being the kind of page a serious stone-fruit grower trusts.

**Correctness calls, each pinned by a test so a future edit cannot reintroduce the error:**
- Apricots are self-fertile (a single tree crops), the headline difference from plums and cherries.
- Prune apricots in late summer or early autumn, never in winter, because they are very prone to
  bacterial canker and silver leaf and a winter wound in cool damp weather invites the infection that
  kills a limb. This is the apricot-specific rule the old generic blurb never carried.
- Apricots do not get peach leaf curl (that is a peach and nectarine disease), so the guide does not
  tell people to spray for it; their fungal troubles are brown rot and shot hole.
- Queensland is treated honestly as marginal: apricot is essentially a Granite Belt crop there, and
  is harder than peaches or plums because there is no established low-chill apricot.

**Actions:**
- `growing_guides/apricot.json` + `tests/test_guide_apricot.py` (mirrors the peach guards plus
  apricot-specific correctness guards and the no-orphan-sources guard). Full suite green (635 tests).
  All 44 cited URLs return HTTP 200. Pages build per-state-unique, dash-free, with FAQ JSON-LD,
  article OG and Sources; no region tokens leak across states (verified on the real pages).
- No "Further reading" section: there is no owned-archive apricot content (no RFCA Apricot folder, no
  WANATCA apricot yearbook article), so the guide omits it rather than padding with tangential links,
  exactly as peach does. `archive_links.json` regenerated to a temp file and confirmed byte-identical,
  so it is not committed.
- Sources avoid `agriculture.vic.gov.au` and `dpi.nsw.gov.au` (both 403 to curl, so they would fail
  the URL-200 gate, per the DEC-145 convention). The VIC facts are anchored on the Goulburn Murray
  Valley fruit fly project, Winetitles, Interstate Quarantine, Sustainable Gardening Australia,
  BeeAware and First 5000, and the QLD DAF low-chill kit covers stone-fruit water and feeding. A test
  guards against reintroducing the bot-blocked domains. (The two Ag Vic pages were confirmed live and
  on-topic in a real browser; they are simply not citable through the curl gate.)
- Variety advice is tied to what is actually in stock: Trevatt, Moorpark, Storey's, Divinity,
  Glengarry, Newcastle and the low-chill dwarf Fireball, plus the plumcot Plumscrumptious.

**Status:** PR open on branch `dale/apricot-guide`, pending Benedict review. On approval: merge,
`ssh dale-server`, `git pull`, `tools/deploy.sh`, rebuild combo + species pages into the dashboard,
rebuild purged Tailwind, verify live.

**To revert:** delete `growing_guides/apricot.json` and `tests/test_guide_apricot.py`.
`has_guide("apricot")` returns False again and both builders fall back to the generic
`fruit_species.json` blurb. No other code touched.
