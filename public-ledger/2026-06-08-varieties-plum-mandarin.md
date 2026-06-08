# 2026-06-08 — Variety descriptions: plum + mandarin

Added verified "what's unique" blurbs to the treestock `/variety` pages for two of the largest
live catalogues: plum and mandarin. This continues the DEC-178 rollout (one species file per
parallel window, research each variety against 2+ reputable sources, skip rather than guess).
Run over two passes on branch dale/varieties-plum-mandarin until both species hit 0 remaining.

**Pass 1 added (32):**
- Plum (18): Damson, Green Gage, Elephant Heart, Ruby Blood, Narrabeen, Amber Jewel, Gulf Ruby,
  Gulf Beauty, Gulf Blaze, Gulf Gold, Sugar (prune), D'Agen Prune, Coe's Golden Drop, President,
  Angelina (Angeleno), Angelina Burdett, Victoria, Flavour Supreme (pluot).
- Mandarin (14): Hickson, Ellendale, Clementine, Nules Clementine, Pixie, Fremont, Daisy, Page,
  Sunburst, Encore, Ortanique, Miho Wase Satsuma, Okitsu Wase Satsuma, Lemonade.

**Pass 2 added (28):**
- Plum (21): Donsworth, Sultan Blood, Primetime, Black Amber, Black Diamond, Angelino, Jefferson,
  Mirabelle, Zwetschge, Purple Gage (Reine Claude Violette), Robe de Sergeant, Sloe (blackthorn),
  and nine "plums" that are NOT true Prunus, each blurb clarifying the real species: Kakadu
  (Terminalia ferdinandiana), Burdekin (Pleiogynium timoriense), Illawarra (Podocarpus elatus),
  Natal (Carissa macrocarpa), Jambolan and Java (both Syzygium cumini), Kaffir (Harpephyllum
  caffrum), Hog (Spondias mombin), Governor's (Flacourtia indica).
- Mandarin (7): Amigo, Shiranui (Dekopon/Sumo), Marisol clementine, Fallglo, Clausellina,
  Avana (Tardivo di Ciaculli), Silverhill Satsuma.

**Skipped by design:** the rest of each species' live varieties were recorded as per-species
skips so they are never re-attempted: multigraft "2-way/3-way" trees, rootstock codes (Myrobalan
H29C, 87-7), misspellings and duplicates of a described cultivar, "European"/"Japanese-blood"
type-suffix variants that are the same cultivar as a page already described, nectarine
mis-parses (Snow Queen), ornamentals mis-grouped under Plum, and obscure nursery-only selections
(plus thin-sourced reals like Yarrahapinni Blood, Iluka Blood, Maestro, Sugar Bubba, Eloise).

Sources lean on UC Riverside's Citrus Variety Collection, UF/IFAS and Citrus Australia for
mandarins; a US plant patent, AgriFutures, ANBG, SANBI, Slow Food and the UK National Fruit
Collection for plums, with reputable third-party references and nurseries used only for
grounding. Accuracy over coverage throughout.

**Result:** plum 42 described / 71 skipped (0 remaining), mandarin 25 described / 25 skipped
(0 remaining). Both species COMPLETE. Shipped as a PR (updates PR #96); deploy happens at the
serialized close-out.
