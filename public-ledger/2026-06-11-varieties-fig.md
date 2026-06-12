# 2026-06-11 — Variety descriptions: fig tail pass (window fig)

Worked the fig tail of the variety-descriptions rollout in worktree branch
`dale/varieties-fig` (runbook: docs/variety-descriptions-rollout.md).

- Computed REMAINING(fig) from live server stock: 39 slugs with no blurb and no
  recorded skip.
- Fanned out 6 parallel research subagents over disjoint slices, each requiring
  2+ reputable sources (1+ non-nursery) per variety, skip if thin.
- Added 11 verified entries to `tools/scrapers/variety_descriptions/fig.json`:
  Archipal, Bedu, Blue Provence, Clown Mosaic, Deciduous (the native Ficus
  henneana), Flanders, French Paillard, Goutte D Or, Hivernenca De La Senyora,
  Purple Vigilante, Zidi.
- Recorded 28 skips with reasons: generic or ambiguous names (White, Brown, Gold,
  Sugar, Forest Green, The Magic, Margurette, White Lightning, Siyah Kis),
  ornamental Ficus mis-parses (Green Island, Flash, Sabre, Sabre Tooth),
  nursery-only sourcing (Ivans Brown, Black Copedi, Carmel, Stoney Yellow,
  Purple Prince, Diggers Purple Heart), researcher confidence below the 0.80
  gate (Peter Good, St John of Malta, Picone Green, Pingo de Mel, Jenny Smith
  Blue, Sicilian Black, Black Sicilian), a product-title duplicate (Sweet
  Temptation Extra), and an identity conflict (Adam = recorded synonym of Blue
  Provence in Australia).
- fig.json now: 23 varieties, 76 skips. REMAINING(fig) = 0, fig is complete.
- Tests green (1463). No golden regen needed (fig's golden fixture variety
  already had its pilot blurb). Shipped as a PR; deploy happens at close-out.
