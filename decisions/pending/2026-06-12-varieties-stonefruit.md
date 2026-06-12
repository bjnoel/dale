# Variety blurbs: stone fruit tail (cherry, peach, apricot, nectarine, mulberry)

**Decided by:** Dale (parallel variety-descriptions run)
**Context:** These five species had their top cultivars seeded in the DEC-178 pilot and
reported remaining=0 in the 2026-06-08 batch for cherry, peach and mulberry. A fresh rank
against live server stock surfaced 21 leftover slugs across the set, almost all of them
multi-graft trees, interspecific crosses already described under their canonical slug, or
parsing-noise duplicates.
**Decision:** Add one verified blurb (peach-ora-a, the "Peachcot Ora A" interspecific sold
at 3 nurseries) and skip the other 20 with reasons. Accuracy over coverage: a multi-graft
tree is not a single cultivar, and the crosses (peacharine, Sugar N Spice, Spicezee, Cot N
Candy) are already described under their existing slugs.

**Why:** peach-ora-a is corroborated by two independent nurseries (Daleys, Ross Creek) plus
a non-nursery source on low-chill stone-fruit interspecifics (UC ANR), clearing the >=2
sources / >=1 non-nursery gate. The remaining slugs are multi-graft listings, brand/dwarf
variants of cultivars already covered, or noise dupes, none describable as a distinct
cultivar.

**Actions:**
- peach.json: +peach-ora-a (confidence medium, 0.82), +4 skips.
- cherry.json: +7 skips (multi-graft and Trixzie dwarf variants).
- apricot.json: +3 skips (multi-graft, Cot N Candy dup).
- nectarine.json: +3 skips (multi-graft, Sugar N Spice / Spicezee dups).
- mulberry.json: +3 skips (noise/duplicate of existing white/weeping/majestic).
- `python3 -m unittest discover tests/` green (1605 tests).

**Status:** Shipped via PR (branch dale/varieties-stonefruit). All five species now report
remaining=0.
**To revert:** remove the peach-ora-a entry and the appended skip slugs from the five files.
