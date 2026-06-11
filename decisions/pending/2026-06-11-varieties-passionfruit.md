# Variety descriptions tail pass: passionfruit complete (2 added, 38 skipped, 0 remaining)

**Decided by:** Dale (parallel variety-descriptions run, window passionfruit)
**Context:** The DEC-178 pilot seeded 11 passionfruit variety blurbs (plus 1 skip). The live
catalogue has 52 passionfruit variety slugs, leaving a 40-slug tail of low-stock names, nursery
marketing labels, and parser artifacts. This run worked the full tail per
docs/variety-descriptions-rollout.md: 3 parallel research subagents over the 20 genuine
candidates, 2+ reputable sources required per fact, skip when thin.
**Decision:** Add verified blurbs for Hawaiian (yellow Passiflora edulis f. flavicarpa, the
Hawaiian lilikoi type; UF/IFAS + Wikipedia + Morton via Growables) and Water Lemon (the distinct
species Passiflora laurifolia; Wikipedia + Morton via Growables). Skip the other 38: 18 research
skips where no non-nursery source verifies a distinct cultivar (Flame Ruby, Sensation, Golden
Nugget, Panama Perfection, Inca Gold, Panama Gold Giant, Select Black, Norfolk Black, Nova,
Panama Sweet Gold, Sunshine Special Frutee, Sweet Lilikoi, Sunshine Splash, Supersweet 96A,
Black Magic, Pandora Red, and both Flamenco orderings) and 20 review skips for parse artifacts
or duplicates of already-covered varieties (13 "Fruit X" slugs, 3 "Non X" slugs, Vine Plant,
Black Espalier, Purple, Panama Red Pandora).
**Why:** Accuracy over coverage. A subagent drafted a Red Flamenco entry but every descriptive
claim rested on nursery marketing copy alone (the only independent source, Passionfruit
Australia, names "Flamenco" and classes it purple while nurseries describe crimson skin), so it
was rejected on review, consistent with the pilot's Flamenco skip. Skipping is success; the
skipped array makes the result idempotent for future runs.
**Actions:** tools/scrapers/variety_descriptions/passionfruit.json now carries 13 varieties +
39 skips, covering all 52 live slugs (remaining = 0, species DONE). Tests green (1509).
**Status:** Shipped as PR from branch dale/varieties-passionfruit. Deploy and progress-tick
happen at the serialized close-out.
**To revert:** Remove the passionfruit-hawaiian and passionfruit-water-lemon entries (and the
38 new skipped slugs) from passionfruit.json.
