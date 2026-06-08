# 2026-06-08 — Variety descriptions: mango batch

Extended the treestock per-variety "what's unique" blurb layer (DEC-178) to mango, our largest
catalogue, over two passes on branch dale/varieties-mango. The pilot had only 4 mango blurbs;
this branch now carries 78 verified cultivar descriptions and 52 recorded skips.

**What shipped (via PR, branch dale/varieties-mango):**
- 74 new verified blurbs in `tools/scrapers/variety_descriptions/mango.json` (4 -> 78 total).
- 52 skips recorded in the file's per-species `skipped` array (thin-source plus parser-noise).
- All 1401 tests green.

**How:** Non-overlapping research subagents, each given a disjoint slice of ranked live mango
varieties, verified every fact against 2+ reputable sources. Accuracy was the rule: a variety
with fewer than two reputable sources was skipped, never guessed.

**Pass 2 coverage:** Australian cultivars (Honey Gold, Titan, Beverley, Gulliver's Triumph,
Bowen, Lady Grace), Florida cultivars (Brooks, Cushman, Graham, Van Dyke, Duncan, Anderson,
Lemon Meringue, Orange Sherbet, Spirit of '76, Harvest Moon, Parvin, Pico), Indian and Sri
Lankan (Manjeera, Kalapadi, Red Mulgoba, Willard), Indonesian and Vietnamese (Gedong, Golek,
Cat Hoa Loc), and Thai, Hawaiian and Mexican (Hong Sa, Kaew, Tong Dum, Okrong, Manzanillo,
Little Gem, Ah Ping).

**Quality note:** two sources surfaced during research, mangopedia.org and biolens-ai.com, were
spot-checked and found to be AI-generated content farms. They were dropped, and any entry that
had leaned on them was re-verified against reliable references (Wikipedia, Philippine government
PCAARRD, the National Mango Board FSHS Zill paper, UF/IFAS, ISHS, University of Hawaii, the Sri
Lanka Dept of Agriculture, Good Fruit Guide, Specialty Produce) or skipped.

**Skipped:** 52 total. Thin or unverifiable cultivars (e.g. Lucinda, Kensington Red, Smith,
Harum Wangi, Bali Apple, Red Harumanis, Pineapple, Chandrakaran, Chereku Rasam, Rosa) plus
parser noise: pot-size-suffix scraper variants, misspellings, and synonym duplicates of
varieties already covered.

**Remaining:** 31 of 161 live mango slugs still uncovered (lowest-ranked single-nursery long
tail). Mango is not done; a future run continues or skips these.

Deploy is deferred to the serialized rollout close-out (build_variety_pages.py + Cloudflare purge).
