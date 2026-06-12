# 2026-06-12 — Variety descriptions: kiwifruit

Added verified "what's unique" blurbs to the treestock `/variety` pages for kiwifruit, the
species with no description file yet. Kiwifruit live stock is mostly generic pollination labels
and parser noise, so the real work was separating the genuine named cultivars from the chaff.

**Added (8 slugs, 6 cultivars):**
- **Hayward** / **Hayward Female** — the classic fuzzy green kiwifruit (NZ, c.1924); dioecious
  female that needs a male pollinator (Matua or Tomuri).
- **Issai** — Japanese self-fertile hardy kiwi (kiwiberry); small smooth fruit eaten whole, no
  separate male needed.
- **Ken's Red** — red-skinned, red-fleshed hardy kiwi hybrid bred in New Zealand; fruiting female.
- **Chieftain Male** — a male pollinator cultivar of fuzzy kiwifruit, a documented polleniser of
  Hayward; bears no fruit itself.
- **Matua** — common mid-season male pollinator; flowers just before Hayward.
- **Dexter** / **Dexter Female** — low-chill Queensland female (Hayward seedling) for warm-winter
  districts.

**Skipped (18):** generic "Male"/"Female", "Fruit Male/Female", "Female Plant", "Gold", "Sweetie",
"Red Female", "H4 Female", "Waynes Female", "Bruno Female Potted", "Issai Going Dormant For Winter"
and similar parser/packaging noise that is not a verifiable named cultivar.

Accuracy held to the rollout gate (>=2 sources, >=1 non-nursery, no invented numbers); three
thin single-nursery details were trimmed during review. Tests green. Ships via PR; deploy happens
at the serialized batch close-out.
