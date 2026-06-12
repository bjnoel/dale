# Variety descriptions tail pass: lychee, longan and wampee (22 added, 12 skipped, all three complete)

**Decided by:** Dale (parallel variety-descriptions run, window lychee-longan-wampee)
**Context:** The pilot batch seeded lychee (3 entries) and longan (4 entries plus 1 skip); wampee
had no file at all. This window ran the full remaining tail: 30 lychee, 4 longan and 3 wampee
live slugs from the server rank.
**Decision:** Add verified blurbs where the 2-source gate holds, duplicate entries for live
alternate-spelling slugs of the same verified cultivar (the established kwai-mai/kwai-may
precedent), and record everything else in the per-species skipped ledgers. Added 19 lychee
entries (16 distinct cultivars: erdon-lee, red-ball, salathiel, baitaying, bengal, wai-chee,
brewster, chom-pogo, no-mai-chi, sah-keng, haak-yip, kiamana, fay-zee-siu, bosworth-3,
souey-tung, sue-lin-san; plus spelling variants baitayang, wai-chi, chompogo and the
lin-san-sue / seedless-sue-lin-san / sue-lin-san-seedless name shuffles of the seedless lychee),
1 longan entry (choompoo, the Choompoo spelling of Chompoo) and a new wampee.json with guy-sam
and yeem-pay. Skipped 8 lychee, 3 longan and 1 wampee slugs: nursery-only cultivars (Jean Hang,
Chucka Puc), generic stock labels (Plant, Organic Plant, SECONDS listings), "<variety> Fruit
Tree" duplicate parse labels, and longan Cats Eye (a common name for the species, not a
cultivar).
**Why:** Lychee is unusually well documented for an Australian audience (ALGA variety pages, the
RFCA Walkamin Research Station evaluation, FAO Asia-Pacific cultivar tables, CTAHR), so this tail
verified at a much higher rate than most species. Spelling-variant duplication keys the same
verified content to every live built page, which is how the layer is designed to work. Before
committing, the Baitayang = Baitaying identity was checked against ALGA and FAO (which lists
Baitang-ying) rather than assumed.
**Actions:** tools/scrapers/variety_descriptions/lychee.json (25 varieties, 8 skipped),
longan.json (5 varieties, 4 skipped) and new wampee.json (2 varieties, 1 skipped); full test
suite green (1546 tests) including the golden test (no fixture variety pages changed, so no
golden regen). Shipped as PR from branch dale/varieties-lychee-longan-wampee.
**Status:** lychee, longan and wampee all have 0 remaining live varieties; mark all three DONE on
the rollout Progress list at close-out.
**To revert:** git revert the PR merge commit; the per-species JSON files are the only content
change.
