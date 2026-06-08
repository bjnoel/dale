# Variety descriptions: mango batch (78 added, 52 skipped)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-mango)
**Context:** Mango is the largest treestock catalogue (161 live variety slugs). The DEC-178
pilot seeded only 4 mango blurbs (Keitt, Kensington Pride, Nam Doc Mai, R2E2). This branch
extends the per-variety "what's unique" blurb layer (see DEC-178) over two passes, following
docs/variety-descriptions-rollout.md.

**Decision:** Add 74 verified per-variety blurbs (4 pilot -> 78 total) to
`tools/scrapers/variety_descriptions/mango.json` and record 52 skips in that file's
`skipped` array. Pass 1 added 42 blurbs / 8 skips (Florida classics, Zill boutique cultivars,
Indian and SE-Asian cultivars). Pass 2 added 32 more and 44 skips: Australian cultivars
(Honey Gold, Titan, Beverley, Gulliver's Triumph, Bowen, Lady Grace), more Florida cultivars
(Brooks, Cushman, Graham, Van Dyke, Duncan, Anderson, Lemon Meringue, Orange Sherbet, Spirit
of '76, Harvest Moon, Parvin, Pico), Indian/Sri Lankan (Manjeera, Kalapadi, Red Mulgoba,
Willard), Indonesian/Vietnamese (Gedong, Golek, Cat Hoa Loc) and Thai/Hawaiian/Mexican (Hong
Sa, Kaew, Tong Dum, Okrong, Manzanillo, Little Gem, Ah Ping).

**Why:** Accuracy over coverage. Every blurb clears the gate: >=2 reputable sources, >=1
non-nursery, confidence >= 0.80, claims bound to sources, no em/en dashes, Australian spelling.
Notable QC in pass 2: two web sources surfaced by research agents, mangopedia.org and
biolens-ai.com, were spot-checked and found to be thin AI-generated content farms, so they were
dropped as sources. Entries that had rested on them were re-verified against reliable sources
(Wikipedia dedicated cultivar pages, Philippine government PCAARRD, the National Mango Board
FSHS Zill paper, UF/IFAS, ISHS, University of Hawaii CTAHR, the Sri Lanka Dept of Agriculture,
Good Fruit Guide, Specialty Produce) or skipped. Chandrakaran, Chereku Rasam and Rosa were
skipped because no reliable non-AI second source could be confirmed. One Lady Grace measurement
(Brix, fruit weight) whose source page was access-blocked was softened to qualitative prose.

**Actions:**
- mango.json: 46 -> 78 varieties; `skipped` array 8 -> 52 slugs (10 thin-source/quality skips
  plus 34 confident parser-noise skips: pot-size-suffix variants like keitt-s/florigon-s,
  misspellings of covered varieties like choc-anan/neelum/beverly, and synonym duplicates like
  bowen-kensington-pride/golden-queen-taiwan-gold/tuong).
- `python3 -m unittest discover tests/` green (1401 tests). Mango is a golden-fixture species,
  but the fixture variety pages (Kensington Pride, R2E2) were unchanged, so no golden page moved.

**Status:** Shipped via PR (not deployed). Deploy happens at the serialized rollout close-out.

**Remaining:** 31 of 161 live mango slugs are still uncovered: the lowest-ranked single-nursery
long tail (e.g. Rupee, Spychala, Batawi, Rad, Cat Thom, Mangga Madu, Springfels, Crimson Blush,
Senorita, Kamerunga White, Royal Red). Mango is NOT done; a future collision-free re-run of the
same file can continue or skip these.

**To revert:** restore mango.json to its 4-variety pilot state; remove this fragment.
