# 2026-06-08: Variety descriptions: pear, loquat, apricot, grapefruit, tamarillo

Added verified "what's unique" blurbs to treestock `/variety` pages for five species, continuing
the DEC-178 content layer. Worked in an isolated worktree (branch `dale/varieties-plt-grt`) across
two passes, owning only those five species files so the run is collision-free with other rollout
windows.

- **61 variety blurbs added in total** across the batch (40 in pass 1, 21 in pass 2), with the
  rest of every species' live tail recorded as `skipped` so re-runs do not re-attempt them.
- **All five species are now complete** (REMAINING 0): pear (34 blurbs), apricot (18), grapefruit
  (8), loquat (3), tamarillo (3).
- Pass 2 covered the heritage tail: classic European pears (Clapp's Favourite, Durondeau, Beurre
  Diel, Beurre Superfin, Beurre Easter, Glou Morceau, Jargonelle, Duchesse d'Angouleme), Japanese
  nashi (Chojuro, Kosui, Shinseiki), English perry pears (Moorcroft, Green Horse, Gin, Red Longdon),
  two Italian pears (Paradise, Mirandino Rosso), Red Sensation, and two low-chill apricots
  (Newcastle, Bentley).
- Sources: USA Pears, NC State Extension and a PMC Japanese-pear breeding review (authoritative),
  plus Wikipedia, Orange Pippin, Specialty Produce, The Book of Pears, the National Perry Pear
  Centre, Slow Food Ark of Taste and the Rare Fruit Club WA varieties page. Nursery listings were
  grounding only, never the sole independent source.
- Accuracy over coverage: trademarked nursery-brand pears (PlantNet Cool Crisp and SunGold,
  Flemings genetic dwarfs) and ambiguous or single-source names were skipped, not guessed.

All tests pass (1401). No deploy in this branch; folding the decision, ticking the rollout
Progress list, and the single rebuild/deploy are the serialized close-out after the PRs merge.
