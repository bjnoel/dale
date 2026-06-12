# Variety blurbs: tropical tail (star-apple, coffee, abiu, starfruit, sapodilla, cacao)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-tropical-tail)
**Context:** Continuing the per-variety "what's unique" blurb rollout (DEC-178) into the
tropical long tail. Assignment: starfruit, star-apple, abiu, sapodilla, cacao, coffee.
Three non-overlapping research subagents verified each remaining live variety against 2+
reputable sources (>=1 non-nursery), skipping anything thin rather than guessing.
**Decision:** Added 8 verified blurbs and recorded the rest as skips:
- star-apple: +2 (green, haitian); skipped grimal/newcomb/weeping/tear-drop/pink/alva
  (nursery-only or unverifiable) plus parser-noise slugs.
- coffee: +4 (k7, red-catuai, yellow-catuai, catuai-rojo, all via World Coffee Research +
  third-party); skipped blue-mountain-kenya/gold/arabica-km35 (trade names) plus noise.
- abiu: +1 (z4, STFC Qld + nursery); skipped e4/pointed/z4-round/e4-pointed (e4 nursery-only,
  the rest are shape descriptors, not distinct cultivars).
- starfruit: +1 (kembangan, UF/IFAS x2); skipped karri (= misspelt Kary) and
  daleys-sweet-gold (nursery-only) plus the "Fruit X" parser-noise slugs.
- sapodilla: +0 (already had krasuey/ponderosa/sawo-manilla); only new live slug was a
  common-name listing -> skipped. DONE.
- cacao: +0 (already had mocambo/trinitario; sg2 previously skipped); cacao-tree is noise
  -> skipped. DONE.

**Why:** Accuracy over coverage. A fabricated cultivar fact is worse than no blurb, so
thin-source varieties are skipped (recorded per-species so re-runs never re-attempt them).
**Actions:** Wrote/updated tools/scrapers/variety_descriptions/{star-apple,coffee,abiu,
starfruit,sapodilla,cacao}.json. `python3 -m unittest discover tests/` green (1605). No
golden regen (none of these are fixture species). Not deployed (close-out folds + deploys).
**Status:** Shipped as PR. Deploy at serialized close-out.
**To revert:** Remove the added entries from those JSON files and rebuild variety pages.
