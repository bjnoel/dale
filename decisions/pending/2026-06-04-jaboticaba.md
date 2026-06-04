# Jaboticaba per-state growing guide (treestock), archives-first and adversarially verified

**Decided by:** Dale (parallel guide run)

**Context:** Continuing the per-species growing-guide rollout (olive, lychee, fig, peach, tamarillo,
guava, mango, plum already shipped). Jaboticaba is a strong treestock fit: a rare-fruit collector
tree with deep, citable coverage in Benedict's owned RFCA archive (40 articles) and a WANATCA
ACOTANC paper, plus heavy live stock across Ross Creek, Daleys, Ladybird and Fruitopia.

**Decision:** Add `tools/scrapers/growing_guides/jaboticaba.json` (one declarative file, the
established pattern) with a state-invariant `core` (7 cited sections + 4 net-new FAQs) and four
genuinely unique state overlays (WA, QLD, NSW, VIC). Reclassify jaboticaba from "tropical" to
"subtropical" in `SPECIES_CLIMATE_CATEGORY` (it is frost-tolerant once mature and most productive in
subtropical/warm-temperate zones, not the hot lowland tropics, per RFCA and Yates), so the per-state
climate notes are accurate. Add `tests/test_guide_jaboticaba.py`.

**Why:** Each `buy-jaboticaba-trees-<state>` page now carries unique, cited, state-aware guidance
instead of a shared blurb. Flagship by climate/evidence is the NSW Northern Rivers (the Australian
jaboticaba belt; best-sourced via RFCA + Daleys), but WA gets the standout overlay because it has
the most distinctive, true story: jaboticaba's thick skin makes it largely fruit-fly resistant (a
rare win in Medfly-ridden WA), it is a Permitted organism on the WA Organism List, and WA is still
almost free of myrtle rust. Archives-first sourcing keeps authority and traffic in-network.

**Actions:**
- Researched state-invariant vs state-variant facts; ground-truthed against the owned RFCA articles
  (pH 5.5 to 6.5, shallow roots, rust risk, polyembryonic true-from-seed but slow, frost-tolerant
  expanding to warm-temperate) and the WANATCA Passmore paper (grows well in Perth, 4 to 5 crops a
  year, fruit-fly-proof thick skin).
- Adversarially cross-checked every key claim against current authorities (CRFG, Morton, UF/IFAS,
  Yates, Business Queensland, DPIRD WA, DCCEEW, DBCA). Honored the corrections that came back:
  yellow jaboticaba framed as "sold as Plinia aureana" (authorities call it Myrciaria glazioviana);
  fruit-fly resistance stated as "largely resistant" (horticultural support only, no gov source),
  never "fruit fly proof"; followed CRFG (not the lone wallum anecdote) that it dislikes poorly
  drained soil; cited the UF/IFAS 4-3-4 NPK feeding figure rather than inventing numbers.
- Verified every cited and further-reading URL returns HTTP 200.

**Status:** PR open, pending Benedict review. Did not touch the shared decision log, daily ledger,
or `archive_links.json` (jaboticaba was already indexed there with 8 RFCA entries); parallel-safe
fragments used instead.

**To revert:** delete `growing_guides/jaboticaba.json` and `tests/test_guide_jaboticaba.py`, and
move "jaboticaba" back to the tropical line in `SPECIES_CLIMATE_CATEGORY`. The page falls back to
the generic `fruit_species.json` blurb (graceful, no code change needed).
