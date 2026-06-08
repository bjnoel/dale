# 2026-06-08 — Variety descriptions: pear, loquat, apricot, grapefruit, tamarillo

Added verified "what's unique" blurbs to treestock `/variety` pages for five species, continuing
the DEC-178 content layer. Worked in an isolated worktree (branch `dale/varieties-plt-grt`),
owning only those five species files so the run is collision-free with other rollout windows.

- **40 variety blurbs added**, **8 thin-source varieties skipped** (recorded so re-runs skip them).
- Per species: apricot +14, grapefruit +6, loquat +3 (new file), pear +14, tamarillo +3 (new file).
- **tamarillo is complete** (every live colour form now has a blurb).
- Sources: UC Riverside Citrus Variety Collection (citrus), USA Pears / UF-IFAS / NC State /
  Orange Pippin / Wikipedia (pears), UC Davis FPS / a US plant patent / Virginia Cooperative
  Extension / CSIC / Rare Fruit Club WA (apricots), CRFG fruit facts and the RFCA archive
  (loquat, tamarillo). Nursery listings used only as grounding, never as the sole independent source.
- Accuracy over coverage: where fewer than two reputable sources existed (several Australian
  heirloom loquats, an ambiguous pear, an under-sourced grapefruit) the variety was skipped, not guessed.

All tests pass (1401). No deploy in this branch; folding the decision, ticking the rollout
Progress list, and the single rebuild/deploy are the serialized close-out after the PRs merge.
