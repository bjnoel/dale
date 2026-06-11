# Variety descriptions tail pass: finger-lime complete (10 added, 28 skipped, 0 remaining)

**Decided by:** Dale (parallel variety-rollout window, branch dale/varieties-finger-lime)

**Context:** The DEC-178/DEC-180..191 pilot seeded finger-lime with 5 variety blurbs and 3
skips, leaving a 38-slug live tail. Finger lime is a flagship rare-fruit species for the
treestock audience (46 live variety slugs across the tracked nurseries), so finishing its
tail was assigned to this window per docs/variety-descriptions-rollout.md.

**Decision:** Researched all 38 remaining slugs via 5 parallel research subagents (2+ source
gate, 1+ non-nursery). Added 10 verified blurbs: green-sapphire, red-champagne, mt-white,
chartreuse, jali-red, sunrise, d-emerald, d-emerald-llp, giant-jali-red, plus a
judys-everbearing alias entry (live spelling variant of the verified judy-s-everbearing,
same lychee-style alias treatment). Skipped 28 on thin or nursery-only sourcing, including
rejecting the researched Wauchope entry (all four sources were grower storefronts) and
dropping an unverifiable journal citation from Chartreuse. Notable verified finds: Jali Red
and Durham's Emerald hold ACRA cultivar registrations; "Mt White" is really Citrus
garrawayi; "Sunrise" is the CSIRO faustrimedin hybrid; both D Emerald listings map to
Durham's Emerald.

**Why:** Accuracy over coverage: the colour-name listings (Yellow, Red, Pink, Purple, Gold,
Green) and single-nursery names have no verifiable cultivar identity, so publishing blurbs
for them would be guessing. Recording them in the per-species skipped array stops future
windows re-attempting them.

**Actions:** tools/scrapers/variety_descriptions/finger-lime.json now holds 15 varieties +
31 skips (= all 46 live slugs, remaining 0). All cited source URLs verified live (the one
403, ScienceDirect, led to dropping that citation). Full test suite green (1509 tests).
Not a golden fixture species, so no golden regen.

**Status:** Shipped as PR from dale/varieties-finger-lime. Finger-lime is DONE for the
Progress list at close-out (remaining 0). Deploy happens at serialized close-out, not here.

**To revert:** git revert the PR merge commit; the blurbs are data-only (committed JSON),
no builder or template changes.
