# Variety descriptions: dragon-fruit tail pass (2 added, 33 skipped, species complete)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-dragon-fruit)

**Context:** The DEC-178/DEC-180..191 pilot seeded dragon-fruit with 9 variety blurbs and 3 skips.
The live catalogue had 35 more dragon-fruit variety slugs with no blurb. This window ran the
documented rollout (docs/variety-descriptions-rollout.md) over that full tail.

**Decision:** Researched all 35 remaining live dragon-fruit varieties with fan-out subagents
(2+ reputable sources required, nursery pages grounding only). Added verified blurbs for 2
(Palora, Zamorano). Skipped 33: nearly the entire dragon-fruit long tail consists of grower or
nursery marketing names (Pink Panther, Frankies Red, Lucille Lemonade, Peony Perfection...),
generic colour or catalogue descriptors (Purple, Magenta, Red Commercial, White Commercial,
Red Skin And White Flesh, Orange), or names too ambiguous to attach facts to safely (Big Red is
both the Taiwanese commercial clone Da Hong and an unrelated US hobbyist hybrid, and the
Australian listing has no cultivar detail to disambiguate). Skipping is the designed outcome
for thin sources; a fabricated cultivar fact is worse than no blurb.

**Why:** Accuracy over coverage (the rollout's stated rule). Dragon fruit cultivars are mostly
hobbyist-named clones with no independent documentation, unlike apples or citrus, so a low
add rate is expected and correct.

**Actions:**
- tools/scrapers/variety_descriptions/dragon-fruit.json: varieties 9 -> 11, skipped 3 -> 36
- Sources spot-checked directly (growables.org UF/IFAS-derived variety table, Wikipedia
  Selenicereus megalanthus, FreshFruitPortal, Tridge); two agent claims were tightened to match
  what the sources actually say (dropped a misattributed "Rolls Royce" nickname for Palora and a
  nursery-only naming claim for Zamorano), and agent-proposed Big Red was demoted to skipped.
- Tests green (1509). Not a golden fixture species, so no golden regen.

**Status:** dragon-fruit remaining = 0 (DONE, tick at close-out). Deploy is the serialized
close-out, not this branch.

**To revert:** git revert the PR commit; the JSON layer is additive and rendering falls back
gracefully when an entry is absent.
