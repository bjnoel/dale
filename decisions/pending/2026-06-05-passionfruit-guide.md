# Passionfruit per-state growing guide added to treestock (own climate category)

**Decided by:** Dale (parallel guide run)

**Context:** Passionfruit is on the species-guide rollout list (docs/species-guide-rollout.md). Its treestock pages drew steady but low traffic over the last 90 days (the /species/passionfruit.html page is the main entrance at 104 impressions; among state pages WA led on impressions at 42 with 0 clicks, VIC next at 18 with the only state-page click). That is the same pattern as mango: WA over-indexes on impressions, but the real climate flagship is elsewhere. Passionfruit's commercial and backyard heartland is subtropical Queensland and northern New South Wales (Queensland grows about 60% of the national crop). Until now passionfruit shared the generic, uncited fruit_species.json blurb and was about to inherit the generic "subtropical" climate note, which misses the three things that actually matter for this crop: Queensland is the heartland, WA has Mediterranean (not Queensland) fruit fly plus a quarantine hurdle on live vines, and Victoria leans on a grafted, cold-tolerant rootstock.

**Decision:** Ship a fully cited, per-state passionfruit growing guide matching the olive gold standard, with QLD as the climate flagship and a standout WA overlay, and give passionfruit its OWN climate category rather than inheriting "subtropical".

**Why:**
- Correctness and trust earn search traffic and community credibility, which is the Track B audience that feeds the Treesmith funnel.
- Passionfruit has genuine per-state stories (QLD heartland and disease pressure; WA medfly and quarantine; cool-climate Victoria on grafted Nellie Kelly rootstock), so a single shared blurb undersells every state.
- A dedicated climate category lets each state's amber note tell the real story (this mirrors what banana, cherry, mulberry and jaboticaba did).

**What shipped (pending review):**
- `tools/scrapers/growing_guides/passionfruit.json`: a shared core (choosing a variety, pollination and self-fertility, planting and support, water and feeding with cited specifics, harvest and eating, woodiness virus and short vine life, buying grafted vs seedling) plus genuinely distinct overlays for QLD, NSW, WA and VIC. 23 sources, all checked live (HTTP 200).
- Advice tied to live stock and told straight: purple and black types (Misty Gem, Sweetheart, Pandora, Nellie Kelly) for flavour and cooler gardens vs Panama and golden types (Panama Red, Panama Gold) for size and heat. Pollination corrected to the evidence: Australian purple hybrids are self-fertile (a single vine crops), the golden and Panama types are more self-incompatible and want a second vine; carpenter bees are the most efficient pollinators and honeybees are effective too (not "poor"). Feeding depth meets the step-3b checklist with cited numbers (about 200 g/vine/month of a balanced 10:3:10 plus boron; up to 140 litres/vine/week at peak; pH 5.5 to 6.5), and the grafted-rootstock sucker warning and woodiness-virus short-life story are both included.
- Passionfruit added to `SPECIES_CLIMATE_CATEGORY` and `STATE_CLIMATE_NOTES` as its own `passionfruit` category in `build_species_state_pages.py`.
- New `tests/test_guide_passionfruit.py` (26 tests) covering per-state uniqueness, no region-token leakage, dash-free copy, FAQ JSON-LD, sources, owned-archive further reading, the dedicated climate category, and passionfruit-specific correctness guards (self-fertility, woodiness virus, the rootstock-sucker warning, banana-passionfruit weed disambiguation, carpenter-bee pollinator).
- Further reading preferences owned archives first: the RFCA passionfruit articles auto-merge from the archive index and one WANATCA yearbook article (Beal and Farlow, Vol 7) is curated.

**Sourcing note:** Anchored on the Queensland DAF Passionfruit Growing Guide (Rigden, 2011), the NT DAF Panama Red growing note (the cited fertiliser and water numbers), Passionfruit Australia (industry body and statistics), BeeAware (pollination), DPIRD WA (medfly, quarantine, WA cultivation history), Lucidcentral (woodiness virus and the banana-passionfruit weed profile), plus the owned RFCA and WANATCA archives. NSW DPI and Agriculture Victoria block automated fetchers, so verifiable-200 sources were preferred over them.

**Status:** PR open, awaiting Benedict's review. Not merged. With current stock only the WA combo page and the species page render the guide (passionfruit sits one rank below the top-20 cap for QLD, NSW and VIC); those three overlays are written, validated by tests, and appear automatically as stock grows.

**To revert:** delete `tools/scrapers/growing_guides/passionfruit.json` and `tests/test_guide_passionfruit.py`, and remove the `passionfruit` entries from `SPECIES_CLIMATE_CATEGORY` and the four `STATE_CLIMATE_NOTES` blocks in `build_species_state_pages.py`. The pages fall back to the generic blurb automatically (has_guide returns False).
