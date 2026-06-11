# 2026-06-11 — Variety descriptions: persimmon window

Ran one window of the variety-descriptions rollout for persimmon (branch
`dale/varieties-persimmon`).

- Computed REMAINING from live server stock: 62 persimmon variety slugs, none previously covered.
- Fanned out 8 non-overlapping research subagents grouped by cultivar so variant slugs (spelling
  and astringency qualifiers) reuse one set of verified facts.
- Result: 47 verified "what's unique" blurbs covering 21 distinct cultivars (Fuyu, Jiro, Maekawa
  Jiro, Izu, Nightingale, Dai Dai Maru, Suruga, Isahaya, Sunami, Yoho, Flat Seedless/Hira-tanenashi,
  Tanenashi, Tone Wase, Tamopan, Hachiya, Hyakume, Rojo Brillante, Nishimura Wase, Ichikikei Jiro,
  Shinshu, American/Common persimmon).
- 15 slugs recorded as verified skips (thin or contradictory sourcing, ambiguous cultivar mapping,
  or parser noise), so future passes never re-attempt them. Skipping is success: no guesses shipped.
- Spot-checked cited sources (Daleys Dai Dai Maru listing confirms the dark-flesh and seedless
  claims; Ladybird's "Common Persimmon" listing confirms it is Diospyros virginiana; RFCA archive
  serves https).
- Persimmon remaining = 0. Tests green (1463). Deploy happens at the batch close-out, not here.
