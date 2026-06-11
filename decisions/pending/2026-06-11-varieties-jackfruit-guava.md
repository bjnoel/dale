# Variety descriptions tail pass: jackfruit and guava (10 added, 35 skipped, both species complete)

**Decided by:** Dale (parallel variety-descriptions run, window jackfruit-guava)
**Context:** The 2026-06-08 pilot batch (DEC-178 layer) seeded jackfruit (2 entries) and guava
(9 entries) with their top varieties, leaving a long tail of live slugs with no blurb. This window
ran the full remaining tail for both species: 24 jackfruit and 21 guava candidates from the live
server rank.
**Decision:** Add verified "what's unique" blurbs only where the 2-source gate holds, and record
everything else in the per-species skipped ledger so re-runs never re-attempt them. Added 4
jackfruit entries (crisp, yullatin, j33, red) and 6 guava entries (malay-red, purple-malay,
cherry, pearl-white, giant-thai, narrow-leaf). Skipped 20 jackfruit and 15 guava slugs, almost all
Australian nursery-only local selections (Kyogle Gold, Tyagarah Vanilla, Brinsmead Special) or
generic catalogue labels (Malay, Elite, White, Pink) with no reputable non-nursery source.
**Why:** Accuracy over coverage is the rollout rule; a fabricated cultivar fact is worse than no
blurb. The skip-heavy result is the expected profile for this long tail: these species' remaining
slugs are dominated by single-nursery seedling selections that only the selling nursery describes.
Notable saves: the ITFNet citation for red-fleshed jackfruit was a dead URL as returned by
research; the live article was located (percent-encoded apostrophe in the URL) and the entry's
claims were trimmed to what the source actually supports before committing.
**Actions:** tools/scrapers/variety_descriptions/jackfruit.json (6 varieties, 28 skipped) and
guava.json (15 varieties, 17 skipped) updated; full test suite green (1546 tests); no golden regen
needed (neither species is a fixture species). Shipped as PR from branch
dale/varieties-jackfruit-guava.
**Status:** Both species now have 0 remaining live varieties; mark jackfruit and guava DONE on the
rollout Progress list at close-out.
**To revert:** git revert the PR merge commit; the per-species JSON files are the only content
change.
