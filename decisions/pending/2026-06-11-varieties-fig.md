# Variety descriptions tail pass: fig (11 added, 28 skipped, species complete)

**Decided by:** Dale (parallel variety run, window fig)
**Context:** The DEC-178 pilot and the 2026-06-08 batch seeded fig's top 12 varieties.
The rank script showed 39 fig variety slugs still live with neither a blurb nor a
recorded skip. Fig is one of the biggest catalogues on the site, so it was queued
for a tail pass under docs/variety-descriptions-rollout.md.

**Decision:** Research all 39 remaining fig slugs via parallel subagents (2+ reputable
sources each, 1+ non-nursery, skip if thin), add 11 verified entries to
tools/scrapers/variety_descriptions/fig.json and record 28 skips in its skipped array.
Skips include parse noise (generic names like White/Brown/Gold/Sugar), ornamental
Ficus mis-parses (Green Island, Flash, Sabre, Sabre Tooth), nursery-only sourcing
(Ivans Brown, Black Copedi, Carmel, Stoney Yellow, Purple Prince), sub-0.80
researcher confidence (Peter Good, St John of Malta, Picone Green, Pingo de Mel,
Jenny Smith Blue, Sicilian Black, Black Sicilian), a product-title duplicate
(Sweet Temptation Extra), and one identity conflict (Adam, recorded in Fig Database
as an Australian synonym of Blue Provence, so the bare name cannot be tied to one
cultivar).

**Why:** Accuracy over coverage. Eleven names verified cleanly against Fig Database,
Wikipedia, Slow Food Ark of Taste, the Felix Gillet Institute and similar references;
the remainder fail the 2-source/non-nursery/0.80-confidence gate and publishing a
guess is worse than no blurb.

**Actions:**
- fig.json: varieties 12 -> 23, skipped 48 -> 76; REMAINING(fig) = 0, species complete
- Full test suite green (1463 tests); fig's only golden fixture variety
  (fig-black-genoa) already had a pilot blurb, so no golden regen was needed
- Shipped as PR on branch dale/varieties-fig; deploy and progress-tick happen at the
  serialized close-out

**Status:** Done (pending close-out deploy)
**To revert:** git revert the PR merge commit; fig.json is self-contained.
