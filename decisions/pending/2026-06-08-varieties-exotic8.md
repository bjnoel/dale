# Variety descriptions: 6 tropical/exotic species completed (cacao, rambutan, miracle-fruit, jaboticaba, white-sapote, custard-apple)

**Decided by:** Dale (parallel variety-descriptions rollout, window exotic8)
**Context:** Continuing the per-variety "what's unique" blurb layer (DEC-178) to the next
stock-ranked batch. This window owned 8 assigned species (lychee, papaya, white-sapote,
custard-apple, jaboticaba, cacao, miracle-fruit, rambutan). One pass caps at ~50 varieties,
so it finished the 6 smaller species fully and deferred the two large catalogues (lychee tail,
papaya) to a re-run in the same worktree.
**Decision:** Added 30 verified variety blurbs and recorded 27 thin-source/noise skips across
cacao, rambutan, miracle-fruit, jaboticaba, white-sapote and custard-apple. Each species file's
`varieties` + `skipped` now covers 100% of that species' live stock (REMAINING = 0 for all six).

**Why:** Accuracy over coverage. Every blurb clears the gate (>=2 sources, >=1 independent
non-nursery, confidence >= 0.80, claims bound to sources). Skipping is success: nursery-only or
single-commercial-source varieties (cacao SG2, jaboticaba Scarlet/White, white sapote
Hawaiian Supreme/Aztec/Rainbow/Wilson/Chris/Kampong/Vista, custard apple Golden Emperor/Late
Gold/Mexican) and generic parser noise (miracle-fruit "Plant", rambutan "marcot" = a
propagation method, custard-apple "Plant"/Rollinia/Sugar Apple/seedling, jaboticaba
"Leaf"/Z4/AXP/ESALQ Red) were skip-listed rather than guessed.

**Notable accuracy calls (all verified against the cited source, not just the agent's word):**
- Geffner: stripped a Brix/grams `measurement` claim that rested only on Wikipedia (the gate
  bars specific figures without an authoritative source); kept the qualitative facts.
- Hilary White / Hillary White: re-sourced off the QLD DPI custard apple PDF (unreadable,
  could not confirm it supports the claims) to Wikipedia (atemoya parentage + hand pollination,
  verified) + Specialty Produce (lists Hilary White) + Daleys (Pink's Mammoth strain specifics).
- White sapote Mac's Golden and Lemon Gold: confirmed verbatim against the RFCA archive
  (rfcarchives.org.au); Smathers confirmed (8-9 oz, greenish-yellow, fair flavour) against
  UF/IFAS HS304 Table 1. Tropic Sun confirmed against STFC; Maroochydore Gold origin against
  FreshFruitPortal.
- Tier hygiene: only rfcarchives.org.au URLs are tier `owned`; growables.org reproductions of
  RFCA/CRFG content were set to `third_party`.
- Cacao Mocambo accurately flagged as Theobroma bicolor (a cacao relative, not T. cacao);
  jaboticaba Yellow/Giant Yellow flagged as Myrciaria glazioviana.

**Actions:** Wrote `tools/scrapers/variety_descriptions/{cacao,rambutan,miracle-fruit,jaboticaba,white-sapote,custard-apple}.json`.
`python3 -m unittest discover tests/` green (1401 tests). No golden regen needed (lychee, the only
golden-fixture species in the assignment, was not touched this pass).
**Status:** Shipped via PR on branch dale/varieties-exotic8. Not deployed (deploy is the
serialized close-out).
**To revert:** delete/restore the six JSON files; the renderer falls back to no blurb.
