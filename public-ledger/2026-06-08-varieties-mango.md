# 2026-06-08 — Variety descriptions: mango batch

Extended the treestock per-variety "what's unique" blurb layer (DEC-178) to mango, our largest
catalogue. The pilot had only 4 mango blurbs; this run adds 42 more verified cultivar
descriptions and records 8 thin-source skips.

**What shipped (via PR, branch dale/varieties-mango):**
- 42 new verified blurbs in `tools/scrapers/variety_descriptions/mango.json` (4 -> 46 total).
- 8 thin-source skips recorded in the file's per-species `skipped` array.
- All 1401 tests green.

**How:** Seven non-overlapping research subagents, each given a disjoint slice of ranked live
mango varieties, verified every fact against 2+ reputable sources (UF/IFAS mango science,
Wikipedia, Specialty Produce, peer-reviewed papers, government GI registries, and the RFCA
archive). Accuracy was the rule: a variety with fewer than two reputable sources was skipped,
never guessed.

**Coverage:** Florida classics (Haden, Kent, Zill, Brooks, Glenn, Irwin, Osteen, Palmer, Carrie,
Pickering, Valencia Pride, Florigon, Saigon), Zill boutique cultivars (Lemon Zest, Cotton Candy,
Fruit Punch, Coconut Cream, Sweet Tart), Indian cultivars (Alphonso, Dasheri, Mallika,
Banganapalli, Kesar, Jumbo Kesar, Neelam, Totapuri, Langra, Pairi), SE-Asian cultivars (Chok
Anan, Cat Chu, Carabao, Falan, Keow Savoey, King Thai, Harumanis, Elephant Tusk, Taiwan Gold,
Kasturi), plus Tommy Atkins, Ataulfo, Julie and the rootstock Sabre.

**Skipped (thin sources):** Ono, Kwan, Bambaroo, Zillate, Early Gold, Alison Red, Bullocks Heart,
Banana. These are mostly real Australian Kensington Pride selections documented only by nurseries,
or ambiguous/dubious names.

**Remaining:** 107 of 161 live mango slugs still uncovered (single-nursery long tail, duplicate
spellings, pot-size-suffix scraper variants). Mango is not done; a future run continues.

Deploy is deferred to the serialized rollout close-out (build_variety_pages.py + Cloudflare purge).
