# Variety descriptions rollout: finger-lime, lemon, lime, blueberry, longan

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-citrus-berry)
**Context:** Continuing the per-variety "what's unique" blurb layer (DEC-178) on treestock
/variety pages. This window owned five species' files: finger-lime, lemon, lime, blueberry
(new file), and longan. blueberry had no descriptions file before this run.

**Decision:** Added 30 verified variety blurbs and recorded 7 thin-source skips across the
five species, each blurb backed by >=2 reputable sources (>=1 non-nursery), authored under
the runbook gate (accuracy over coverage; skip rather than guess).

- blueberry (new file): +12 added, 2 skipped. Southern highbush (Sunshine Blue, Misty,
  Biloxi, Gulf Coast, Sharpe Blue/Sharpblue), northern highbush (Legacy), rabbiteye
  (Powder Blue, Brightwell, Climax, Premier), and ornamental dwarf Bushel-and-Berry types
  (Peach Sorbet, Pink Icing). Backed mainly by US university extension (UF/IFAS, UGA, NCSU,
  Texas A&M, MSU), USDA-ARS, Missouri Botanical Garden, American Pomological Society.
- finger-lime: +4 (Rainforest Pearl, Pink Ice, Judy's Everbearing, Byron Sunrise), 3 skipped.
  Judy's Everbearing and Byron Sunrise corroborated by the UC Riverside citrus collection and
  a peer-reviewed chemotype paper; nursery-coined names (Collette, Crystal, Tom Thumb) skipped.
- lemon: +7 (Lemonade, Yuzu, Bush, Fino, Verna, Seedless Eureka, Variegated Eureka), 0 skipped.
  Several are not true lemons (Yuzu = Citrus junos; Lemonade = NZ low-acid hybrid; Bush = rough
  lemon rootstock), described as such. Fino/Verna/Variegated-Eureka via UC Riverside CVC.
- lime: +6 (West Indian, Sweet, Sunrise, Red Centre, Rangpur, Sudachi), 1 skipped. Spans the
  true/Key lime, Palestine sweet lime, two CSIRO native hybrids (Sunrise, Red Centre), the
  mandarin-lime Rangpur, and Japanese Sudachi. Bare "Australian" lime skipped as ambiguous.
- longan: +3 (Haew, Chompoo, Biew Kiew), 1 skipped. Thai cultivars via FAO + the RFCA archive
  (tier "owned"). "Fijian longan" skipped: it is Pometia pinnata, a different species.

**Why:** Unique, verified per-variety copy makes /variety pages genuinely informative (and
distinct for SEO / AI answers) without inventing facts. Blueberry was a sizeable uncovered
catalogue; the citrus species extend the DEC-178 pilot tails.

**Actions:**
- Wrote tools/scrapers/variety_descriptions/{blueberry,finger-lime,lemon,lime,longan}.json
  (varieties + per-species skipped slug arrays).
- `python3 -m unittest discover tests/` green (1401 tests, incl. the 12 variety-description
  guards and golden). longan is a golden-fixture species but its golden output is unchanged
  (the new longan cultivars are not in the golden fixture stock; longan-kohala was already
  committed), so no golden regen was needed.
- Spot-checked cited sources (FAO longan TSS figures, UC Riverside Fino, the finger-lime
  chemotype paper) against the live pages; all resolve and support the claims.

**Status:** Shipped via PR from branch dale/varieties-citrus-berry. Deploy is the serialized
close-out (build_variety_pages.py + purge_cloudflare.sh), not this branch.

**To revert:** remove the added entries from the five species JSON files (or delete
blueberry.json entirely) and rebuild variety pages.
