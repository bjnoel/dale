# Variety descriptions: kiwifruit (8 added, 18 skipped)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-kiwifruit)
**Context:** Continuing the treestock /variety "what's unique" blurb rollout (DEC-178) into
kiwifruit, which had no variety_descriptions file yet. Live stock for kiwifruit is dominated by
generic male/female pollination labels and parser noise ("Fruit Male", "Female Plant", "Issai
Going Dormant For Winter", "Bruno Female Potted"); only a handful of rows are genuine named
cultivars.
**Decision:** Added verified blurbs for the 8 real-cultivar slugs in
`tools/scrapers/variety_descriptions/kiwifruit.json`: Hayward and Hayward Female (the dominant
fuzzy green, dioecious female needing a male), Issai (self-fertile hardy kiwi), Ken's Red
(red-fleshed hardy kiwi hybrid), Chieftain Male and Matua (male pollinators of fuzzy kiwifruit),
and Dexter plus Dexter Female (low-chill Queensland female). 18 noise/generic slugs recorded in
the file's `skipped` array so re-runs do not re-attempt them.

**Why:** Kiwifruit collectors need to understand the male-vs-female pollination split (you cannot
fruit a Hayward or Dexter without a Matua/Chieftain nearby) and the fuzzy-vs-hardy-kiwi
distinction (Issai self-fertile, Ken's Red eaten whole). These are exactly the "what's unique"
facts that generic listings omit. Accuracy held to the rollout gate: >=2 sources, >=1 non-nursery,
no invented figures. During assembly three single-nursery-sourced details were trimmed for safety
(the "Matua means father in Maori" etymology and the "Ken's Red named for Ken Nobbs" attribution
were dropped), and a mislabelled CRFG source URL was corrected to the canonical CRFG fruit-facts
page (which independently lists Dexter among low-chill cultivars). Chieftain's status as a real
hexaploid male polleniser of Hayward was confirmed against research literature before keeping it.

**Actions:** New file only; `python3 -m unittest discover tests/` green (1605 tests). kiwifruit is
not a golden-fixture species, so no golden regen. No deploy in-branch (close-out deploys once).
**Status:** Shipped as PR; awaiting batch close-out (fold pending decisions, deploy).
**To revert:** Delete `tools/scrapers/variety_descriptions/kiwifruit.json`; the renderer falls
back to no blurb.
