# Species growing-guide queue (what to build next)

The prioritised hand-off list of tracked species that still need a growing guide. Pair this with
`docs/species-guide-rollout.md` (the method + the full authoring prompt) and the
`/species-guide-rollout` command (runs one species in a worktree + PR, concurrency-safe).

Snapshot: 2026-06-15. **108 enabled species, 55 have a guide, 53 still need one** (38 fruit, 15
bush tucker / native). The big fruit rollout (DEC-126 to DEC-173) is essentially done; what remains
is (a) mainstream fruit/nuts added to the catalogue since that rollout, and (b) most of the bush
tucker / native pilot species (only 5 of 20 have guides so far).

## How priority was set (read this)

These guideless pages are thin, so Google barely indexes them, so they earn **~0 GSC impressions**
(only wampee and mangosteen register any at all over 90 days). GSC demand is therefore useless as a
ranking signal here, it just measures the chicken-and-egg we are trying to break. So the queue is
ranked by **live in-stock product count**, which is the best available proxy for real Australian
demand and is independent of our current indexing. The mainstream Tier 1 species (persimmon, kiwifruit,
strawberry) have genuine search demand we are simply failing to capture today.

Re-generate this list any time (it is a snapshot): the inputs are `fruit_species.json` (enabled
species), `tools/scrapers/growing_guides/*.json` (existing guides), and live in-stock counts off the
`/species/` index. See the script at the bottom.

## Source angle (which sources to lean on)

The rollout doc's source order is RFC archives > WANATCA > RFCWA > gov, but most of what is left is
NOT in the rare-fruit archives, so the angle differs by species:

- **rare fruit** : RFCA-rich (rfcarchives.org.au). Archives first, exactly as the fruit rollout did.
- **native/BT** : Australian native / bush food. WANATCA yearbooks + bush-food and ag-dept sources;
  follow the bush-tucker FAQ caution in the rollout doc (single-section overlays need genuinely
  net-new FAQs, not a recap of the climate-fit section).
- **mainstream** : common temperate fruit/nuts with little or no RFCA presence. Lean on .gov.au
  (DPIRD WA, Business Queensland / DAF, NSW DPI, Agriculture Victoria) + the relevant industry body.
  `build_archive_index.py` will show no RFCA entries for these, that is expected, fall through to gov.

Confirm before guiding (arguably off-brand for a fruit-tree site, may be worth de-scoping instead of
guiding): **coffee, coconut, pineapple** (not backyard fruit trees in most of Australia), and
**goji-berry**. Quick call from Benedict on whether to guide or drop them.

## Queue

### Tier 1 (stock 12+, do first)  (5 species)

| # | Species | slug | Source angle | In stock |
|--:|---------|------|--------------|---------:|
| 1 | Persimmon | `persimmon` | mainstream | 39 |
| 2 | Kumquat | `kumquat` | mainstream | 33 |
| 3 | Kiwifruit | `kiwifruit` | mainstream | 19 |
| 4 | Strawberry | `strawberry` | mainstream | 19 |
| 5 | Chestnut | `chestnut` | mainstream | 12 |

### Tier 2 (stock 5 to 11)  (18 species)

| # | Species | slug | Source angle | In stock |
|--:|---------|------|--------------|---------:|
| 6 | Blackberry | `blackberry` | mainstream | 9 |
| 7 | Star Apple | `star-apple` | rare fruit | 9 |
| 8 | Tangelo | `tangelo` | mainstream | 9 |
| 9 | Wampee | `wampee` | rare fruit | 7 |
| 10 | Almond | `almond` | mainstream | 7 |
| 11 | Coffee | `coffee` | mainstream | 7 |
| 12 | Currant | `currant` | mainstream | 7 |
| 13 | Hazelnut | `hazelnut` | mainstream | 7 |
| 14 | Pepino | `pepino` | mainstream | 7 |
| 15 | Acerola | `acerola` | rare fruit | 6 |
| 16 | Davidson's Plum | `davidsons-plum` | native/BT | 6 |
| 17 | Midyim Berry | `midyim-berry` | native/BT | 6 |
| 18 | Quince | `quince` | mainstream | 6 |
| 19 | Soursop | `soursop` | rare fruit | 6 |
| 20 | Citron | `citron` | rare fruit | 5 |
| 21 | Elderberry | `elderberry` | mainstream | 5 |
| 22 | Native River Mint | `native-river-mint` | native/BT | 5 |
| 23 | Pistachio | `pistachio` | mainstream | 5 |

### Tier 3 (stock 2 to 4)  (16 species)

| # | Species | slug | Source angle | In stock |
|--:|---------|------|--------------|---------:|
| 24 | Burdekin Plum | `burdekin-plum` | native/BT | 4 |
| 25 | Saltbush | `saltbush` | native/BT | 4 |
| 26 | Chinese Bayberry | `chinese-bayberry` | rare fruit | 3 |
| 27 | Gooseberry | `gooseberry` | mainstream | 3 |
| 28 | Gumbi Gumbi | `gumbi-gumbi` | native/BT | 3 |
| 29 | Pigface | `pigface` | native/BT | 3 |
| 30 | Pineapple | `pineapple` | mainstream | 3 |
| 31 | Aniseed Myrtle | `aniseed-myrtle` | native/BT | 2 |
| 32 | Babaco | `babaco` | rare fruit | 2 |
| 33 | Blue Quandong | `blue-quandong` | native/BT | 2 |
| 34 | Bunya Nut | `bunya-nut` | native/BT | 2 |
| 35 | Coconut | `coconut` | mainstream | 2 |
| 36 | Mangosteen | `mangosteen` | rare fruit | 2 |
| 37 | Sugar Apple | `sugar-apple` | rare fruit | 2 |
| 38 | Tamarind | `tamarind` | rare fruit | 2 |
| 39 | Walnut | `walnut` | mainstream | 2 |

### Tier 4 (stock 0 to 1, lowest)  (14 species)

| # | Species | slug | Source angle | In stock |
|--:|---------|------|--------------|---------:|
| 40 | Abiu | `abiu` | rare fruit | 1 |
| 41 | Cherry of the Rio Grande | `cherry-of-the-rio-grande` | rare fruit | 1 |
| 42 | Desert Lime | `desert-lime` | native/BT | 1 |
| 43 | Goji Berry | `goji-berry` | mainstream | 1 |
| 44 | Native Thyme | `native-thyme` | native/BT | 1 |
| 45 | Sandpaper Fig | `sandpaper-fig` | native/BT | 1 |
| 46 | Kakadu Plum | `kakadu-plum` | native/BT | 0 |
| 47 | Medlar | `medlar` | mainstream | 0 |
| 48 | Muntries | `muntries` | native/BT | 0 |
| 49 | Quandong | `quandong` | native/BT | 0 |
| 50 | Riberry | `riberry` | native/BT | 0 |
| 51 | Ruby Saltbush | `ruby-saltbush` | native/BT | 0 |
| 52 | Sea Celery | `sea-celery` | native/BT | 0 |
| 53 | Warrigal Greens | `warrigal-greens` | native/BT | 0 |

(Stock 0 = tracked species with no live stock right now; a guide still helps the `/species/` page and
catches the next restock, but it is the lowest-value end of the queue. `quandong` has no `/species/`
page yet.)

## Regenerating this snapshot

```bash
# species needing a guide = enabled species (fruit_species.json) minus growing_guides/*.json,
# ranked by live in-stock count from https://treestock.com.au/species/
# (GSC 90d impressions can be layered in via tools/scrapers/gsc_analysis.py query_gsc on the
# 'page' dimension, but they are ~0 for guideless species, so stock is the ranking signal.)
```
The exact merge script used to build this table lives in the PR that introduced this file.
