# 2026-06-11: Variety descriptions, window lime-pomelo-kumquat

Part of the parallel variety-descriptions rollout (DEC-178 layer). This window owned the
lime, pomelo, and kumquat species files.

## What happened

- Built the live remaining list for lime, pomelo, and kumquat from the server's variety
  grouping (35 + 19 + 14 live slugs), subtracted existing entries and skips, and dropped
  obvious listing noise (pot-size duplicates, misspellings, fruit-salad-tree artefacts).
- Fanned out 5 parallel research subagents over 25 candidate varieties, each fact verified
  against 2+ reputable sources with at least one non-nursery source. Primary sources: UC
  Riverside Givaudan Citrus Variety Collection, PROSEA, Atlas of Living Australia, University
  of Queensland News, Wikipedia.
- Added 17 verified blurbs: 8 kumquat (Nagami, Meiwa, Variegated, Hong Kong, Marumi,
  Calamondin, Calamondin Variegated, Chinotto), 8 lime (Sublime, Kusaie, Mount White,
  Russell River, Australian Round, Indonesian, Jeruk Limo, Mosambi Sweet), 1 pomelo
  (Tahitian).
- Skipped 8 on thin sourcing (never guess): Courtyard and Green kumquats, Lemonade and
  Limello limes, the K13 pomelo family, Flicks Yellow pomelo.
- All three species now have zero remaining live varieties: lime, pomelo, and kumquat are
  DONE pending close-out.

## Notes

- The lime tail turned out to be a small showcase of Australian native citrus: Mount White
  lime (Citrus garrawayi), Russell River lime (Citrus inodora), and the Gympie lime
  (Citrus australis), all endemic species with verifiable stories, exactly the content the
  rare fruit collector audience wants.
- Shipped as a PR with pending-decision and ledger fragments; fold, progress tick, and the
  single deploy happen at the serialized close-out.
