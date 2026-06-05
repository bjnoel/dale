# Raspberry per-state growing guide (WA flagship, own cool-climate category)

**Decided by:** Dale (parallel guide run)

**Context:** Raspberry had only the generic fruit_species.json blurb. Data-driven flagship
pick: GSC (28 days) shows zero raspberry impressions, and Plausible (30 days) shows the WA
buy page as the single most-visited raspberry page (6 views), with /species/raspberry.html
next. On live stock only buy-raspberry-trees-western-australia.html generates today (QLD/NSW/VIC
raspberry is below their top-20 cap), and WA is Benedict's home turf and rare-fruit community.
So WA is the flagship; all four state overlays are still authored (tests build all four, and
stock fluctuates).

**Decision:** Ship a comprehensive, cited, per-state raspberry guide
(tools/scrapers/growing_guides/raspberry.json) mirroring olive/blueberry, and give raspberry
its OWN climate category ("raspberry") rather than the generic "temperate / choose low-chill
varieties" note, which is backwards for a high-chill, cool-climate cane fruit.

**Why:**
- Raspberry is a cool-climate, HIGH-chill cane fruit (the opposite of low-chill), heat and
  humidity sensitive, so the generic temperate note misled growers. The new per-state notes
  tell the real story: cool south only in WA, the cold Granite Belt (plus the native Atherton
  raspberry) in QLD, the cool tablelands in NSW, and the Dandenongs/Yarra Valley heartland in VIC.
- Corrects two errors in the stale blurb, both adversarially verified: Heritage is an
  AUTUMN-fruiting primocane (not a floricane "Heritage type"); and the native Atherton raspberry
  (Rubus probus) is PRICKLY and a rampant scrambler, not "compact, nearly thornless", and is
  widespread in Queensland, not Atherton-endemic.
- Archives-first sourcing: raspberry has no RFCA Fruits/Raspberry folder, but the first-party
  RFCA "Australian native raspberries" page lives under AusNative/ (so it does not auto-index);
  it and the matching WANATCA Yearbook Vol 23 article (both by Rubus taxonomist Tony Bean) are
  hand-curated into Further reading as followed, owned links.

**Actions:**
- Added growing_guides/raspberry.json (7 core sections + 5 core FAQs; WA/QLD/NSW/VIC overlays,
  each genuinely unique; 27 sources; 2 owned Further-reading links).
- Added "raspberry" to SPECIES_CLIMATE_CATEGORY + four per-state STATE_CLIMATE_NOTES in
  build_species_state_pages.py.
- Added tests/test_guide_raspberry.py (35 tests, including the Heritage-primocane and
  Atherton-prickly-not-thornless correctness guards). Did NOT regenerate archive_links.json
  (AusNative folder does not map to the slug, so it is unchanged).

**Status:** PR open, awaiting Benedict's review. Not merged.

**To revert:** delete growing_guides/raspberry.json and tests/test_guide_raspberry.py, and
revert the raspberry climate-category + STATE_CLIMATE_NOTES additions in
build_species_state_pages.py. has_guide("raspberry") then returns False and the pages fall
back to the generic blurb.
