# treestock lemon per-state growing guide (Track B)

**Decided by:** Dale (parallel guide run)

**Context:** Lemon is next down the growing-guide rollout (docs/species-guide-rollout.md): it is the
most widely planted fruit tree in Australian backyards and a genuine crop in every mainland state,
yet its buy-lemon-trees-<state> combo pages and /species/lemon.html shared a generic, uncited
fruit_species.json blurb. Lemon sits in the rollout's citrus group, where the guidance is to lean on
.gov.au, Citrus Australia and the web rather than RFCA (citrus is not a rare fruit), though the RFCA
Citrus folder turned out to carry two genuinely lemon-relevant owned articles.

**Decision:** Ship a comprehensive, cited, per-state lemon growing guide as a single JSON file
(tools/scrapers/growing_guides/lemon.json), matching the olive gold standard and the rollout-v2 bar
(net-new FAQs, deep cited water-and-feeding, hand-escaped inline HTML, no dashes).

**Why:**
- Flagship WA: the dry Mediterranean south-west is well suited to citrus, WA carries the distinctive
  quarantine and shipping angle (citrus is one of the hardest things to bring into WA), and the
  citrus topState pattern leans WA. All four states still earn a genuinely distinct overlay (WA the
  Gingin-to-Albany belt, Gascoyne and Medfly; QLD the Central Burnett around Gayndah and Mundubbera,
  melanose and lemon scab; NSW the Riverina, Australia's largest citrus region, and citrus gall
  wasp; VIC the Murray Valley around Mildura and frost as the real limit, with Meyer the cold-hardy
  pick).
- Correctness focus: variety choice tied to live stock (Eureka, Lisbon, Meyer, Villa Franca, Fino,
  Verna, Yuzu are all actually in the table); lemons are self-fertile and non-climacteric (the tree
  is the best store); cited feeding from NSW DPI (a complete citrus fertiliser about 10:4:6 at 500 g
  per year of tree age up to about 5 kg, late winter, with a sulphate of ammonia top-up in November,
  plus magnesium, zinc and manganese trace elements); and accurate biosecurity (citrus canker
  eradicated and Australia declared free April 2021; citrus gall wasp native to QLD and northern NSW
  but established in Perth suburbs, not WA orchards; Queensland fruit fly now established across
  Greater Sunraysia after the pest-free area ceased in 2024; Medfly endemic in WA). Research fanned
  out to three subagents, key claims adversarially cross-checked, and every cited URL verified
  (22 returned HTTP 200 directly; 6 NSW DPI pages are Cloudflare-blocked to bots but confirmed live
  in a browser via a reader proxy, the same domain peach.json already cites).

**Actions:**
- New: tools/scrapers/growing_guides/lemon.json (28 sources, all cited and verified; core plus WA,
  QLD, NSW and VIC overlays; 4 core plus 2-per-state net-new FAQs).
- New: tests/test_guide_lemon.py (uniqueness, region-leak, no-dash, FAQ JSON-LD, sources,
  further-reading, and a lemon-specific check that further reading is the curated RFCA Citrus links).
- No SPECIES_CLIMATE_CATEGORY change (lemon is already "citrus" with accurate per-state notes);
  archive_links.json was NOT regenerated (the RFCA "Citrus" folder does not map to the lemon slug,
  so there is no auto-merge, and lemon's Further reading is hand-curated owned RFCA Citrus articles).
- First-party archives preferenced: two owned RFCA Citrus articles (improved lemon and lime
  varieties; citrus rootstocks) curated as followed Further reading. No citable WANATCA lemon article
  exists, and rarefruitclub.au was not used (lemon is not a rare fruit).

**Status:** PR open on branch dale/lemon-guide, pending Benedict review. Full suite green (529 tests).
