# Variety descriptions: jaboticaba, grumichama, acerola, cherry-of-the-rio-grande, wax-jambu tails

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-jabo-cherries)
**Context:** Variety-descriptions rollout (DEC-178 layer) tail pass for five Myrtaceae/tropical
species. REMAINING was 19 live variety slugs not already described or skipped: jaboticaba (5),
grumichama (6), acerola (4, new file), cherry-of-the-rio-grande (2, new file), wax-jambu (2).
**Decision:** Added 5 verified blurbs, skipped 14 on thin sources or as listing-title noise. Two
new species files created (acerola, cherry-of-the-rio-grande). Accuracy held over coverage: the
jaboticaba "Restinga" blurb was rewritten on review to drop an unsourced "persistent crown of
sepals" detail the source did not actually support (the cited pages confirm only the coroada/
crowned name and the tree/fruit traits).

**Added (5):**
- jaboticaba-giant-oblongata: Plinia oblongata (sour jaboticaba, jaboticaba azeda), tart not sweet.
- jaboticaba-restinga: Plinia coronata (crowned/king jaboticaba), acidic succulent pulp vs sweet Sabara.
- grumichama-red: recognised red-skinned colour form (var. erythrocarpa), distinct from black/yellow.
- acerola-florida-sweet: improved 1956 clone, milder apple-like sweet flavour, very high vitamin C.
- acerola-barbados-cherry-california-sweet: California Sweet, compact sweeter selection.

**Skipped (14):** jaboticaba-giant-momotaro, jaboticaba-white-esalq, jaboticaba-white-plinia-aureana,
grumichama-cherry, grumichama-sweet-red, grumichama-obera, grumichama-regina, grumichama-black-beauty,
acerola-barbados-cherry-fruit-tree, acerola-cherry-florida-sweet (dup of Florida Sweet),
cherry-of-the-rio-grande-apricot (mis-parse), cherry-of-the-rio-grande-yellow (no source for a yellow form),
wax-jambu-roseapple-purple (listing noise), wax-jambu-green (no source for a distinct green form).

**Why:** Each added blurb has >=2 reputable sources, >=1 non-nursery; skips are thin-source or noise
artefacts, recorded per-species so a future re-run never re-attempts them.
**Actions:** Wrote/updated tools/scrapers/variety_descriptions/{jaboticaba,grumichama,acerola,
cherry-of-the-rio-grande,wax-jambu}.json. `python3 -m unittest discover tests/` green (1605 tests).
No golden regen (none of these are fixture species).
**Status:** Shipped via PR on branch dale/varieties-jabo-cherries. Deploy + progress-tick are the
serialized close-out.
**To revert:** Drop the five added entries from their species files (skips can stay).
