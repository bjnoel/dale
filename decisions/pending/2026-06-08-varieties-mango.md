# Variety descriptions: mango batch (42 added, 8 skipped)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-mango)
**Context:** Mango is the largest treestock catalogue (161 live variety slugs). The DEC-178
pilot seeded only 4 mango blurbs (Keitt, Kensington Pride, Nam Doc Mai, R2E2). This run
extends the per-variety "what's unique" blurb layer (see DEC-178) to the next ~50 ranked
distinct mango cultivars, following docs/variety-descriptions-rollout.md.

**Decision:** Add 42 verified per-variety blurbs to
`tools/scrapers/variety_descriptions/mango.json` and record 8 thin-source skips in that
file's `skipped` array. Seven non-overlapping research subagents covered the Florida classics
(Haden, Kent, Zill, Brooks, Glenn, Irwin, Osteen, Palmer, Carrie, Pickering, Valencia Pride,
Florigon, Saigon), the modern Zill boutique cultivars (Lemon Zest, Cotton Candy, Fruit Punch,
Coconut Cream, Sweet Tart), the Indian cultivars (Alphonso, Dasheri, Mallika, Banganapalli,
Kesar, Jumbo Kesar, Neelam, Totapuri, Langra, Pairi), the SE-Asian cultivars (Chok Anan,
Cat Chu, Carabao, Falan, Keow Savoey, King Thai/Mahachanok, Harumanis, Elephant Tusk,
Taiwan Gold, Kasturi), plus Tommy Atkins, Ataulfo, Julie and the South African rootstock Sabre.

**Why:** Accuracy over coverage. Every blurb clears the gate: >=2 reputable sources, >=1
non-nursery, confidence >= 0.80, claims bound to sources, no em/en dashes, Australian spelling.
Thin entries were skipped rather than guessed. Two slice-1 entries (Alphonso, Palmer) were
repaired to add a verified second authoritative source (peer-reviewed PMC paper; UF/IFAS) so
they were not resting on a single source.

**Actions:**
- mango.json: 4 -> 46 varieties; new `skipped` array of 8 slugs.
- `python3 -m unittest discover tests/` green (1401 tests). Mango is a golden-fixture species
  but the new varieties are not in the golden fixture stock, so no golden page changed.

**Status:** Shipped via PR (not deployed). Deploy happens at the serialized rollout close-out.

**Remaining:** 107 of 161 live mango slugs are still uncovered. These are the lower-ranked
single-nursery long tail, duplicate spellings of varieties already covered (e.g. choc-anan,
keow-savoy, neelum, allison-red), and pot-size-suffix scraper variants (keitt-s, florigon-s,
etc.). Mango is NOT done; a future collision-free re-run of the same file can continue.

**To revert:** restore mango.json to its 4-variety pilot state; remove this fragment.
