# Variety descriptions: currant, elderberry, goji-berry, gooseberry (berries2 window)

**Decided by:** Dale (parallel variety-descriptions run)
**Context:** Variety-descriptions rollout (per `docs/variety-descriptions-rollout.md`,
extends DEC-178). This window owned the four "minor berry" species files: currant,
elderberry, goji-berry, gooseberry. Live stock had 23 candidate slugs across them.
**Decision:** Added 14 verified "what's unique" blurbs and recorded 9 skips, each against
2+ reputable sources (>=1 non-nursery), skipping rather than guessing wherever sourcing was thin.
**Why:** These four species had no variety blurbs. The "gooseberry" catalogue label is a
catch-all spanning four unrelated genera (Ribes, Phyllanthus, Physalis), so the blurbs do
useful work disambiguating what a buyer is actually looking at.
**Actions:**
- currant: added black, red, white, royal-de-naples; skipped magnus-black (Magnus-specific
  facts could not be confirmed on any live non-nursery source; the one paper naming it is paywalled).
- elderberry: added black-lace ('Eva'), black-tower ('Eiffel 1'), black-beauty ('Gerda'),
  madonna; skipped cane, sambucus-fruit-tree, variegated, purple (generic descriptors, not
  distinct named cultivars).
- goji-berry: added black (Lycium ruthenicum); skipped shrub (generic descriptor).
- gooseberry: added star (Phyllanthus acidus), captivator (Ribes hybrid), cape (Physalis
  peruviana), english (Ribes uva-crispa), amla-indian (Phyllanthus emblica); skipped
  ceylon-hill (ambiguous Dovyalis vs Rhodomyrtus), captivator-plant (noise dup),
  guava-psidium-quineense (mis-parse, actually a guava).
**Status:** Shipped via PR on branch dale/varieties-berries2. `python3 -m unittest discover
tests/` green. No golden regen (none of these are golden-fixture species). Not yet deployed
(deploy is the serialized close-out).
**To revert:** delete the four new files under `tools/scrapers/variety_descriptions/`.
