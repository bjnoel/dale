# Variety descriptions: macadamia + pecan tails (rollout window)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-macadamia-pecan)
**Context:** Continuing the DEC-178 per-variety "what's unique" blurb rollout
(`docs/variety-descriptions-rollout.md`). Macadamia had no committed blurb file; pecan had
only Pawnee and Wichita. Both are nut species with deep Australian nursery catalogues
(HAES numbered selections, Hidden Valley A-series, USDA tribe-named pecans).
**Decision:** Researched the live macadamia and pecan variety catalogues against reputable
sources (Hawaii Ag Experiment Station Bulletin 121, Queensland DPI Macadamia Variety
Identifier, HortScience, USDA-ARS Carya cultivar database, UGA/NMSU/UF-IFAS pecan extension,
US plant patents, ACRA, RFCA archive), and committed verified blurbs.

- New file `tools/scrapers/variety_descriptions/macadamia.json`: 24 varieties added
  (HAES 246/Keauhou, 344/Kau, 741/Mauka, 814, 816, 849; Hidden Valley A4, A16, A38, A203,
  A268; Beaumont, Daddow, H2, Tetraphylla; Pinkalicious and MiniMaca alias sets; Lotsa Nuts),
  9 skipped.
- `tools/scrapers/variety_descriptions/pecan.json`: +14 varieties (Apache, Cape Fear, Cherokee,
  Cheyenne, Desirable, Kiowa, Mohawk, Nut/Pabst alias set, Riverside, Shoshoni alias set, Tejas),
  on top of the 2 already present; 0 new skips.

**Why:** Macadamia and pecan are high-stock nut catalogues with no prior variety blurbs;
the numbered/lettered cultivar codes are opaque to collectors, so a verified "what's unique"
line adds real value on the /variety pages.
**Actions:** Skipped where sourcing was thin (macadamia 842, A29, Gouros, the Integrifolia
Hybrid G6 nursery listing) or where the listing was generic noise rather than a cultivar
(macadamia "Nut", "Tree", "Bush Nut", "Nut Plant", and the unconfirmed "Lots A Lots" alias).
SP (self pollinating) tags in pecan nursery listings were NOT taken at face value: each pecan
blurb states the verified pollination type (protandrous type I / protogynous type II) and notes
the SP label is a seller grouping.
**Status:** Macadamia and pecan REMAINING both 0 after this window. `python3 -m unittest
discover tests/` green (1537 tests). Not a golden-fixture species, so no golden regen.
**To revert:** delete the macadamia.json file and the 14 new pecan.json entries.
