# 2026-06-11 — Variety descriptions: apple tail pass (window: apple)

Part of the parallel variety-descriptions rollout (docs/variety-descriptions-rollout.md).

Apple was finished in the 2026-06-08 batch, but live nursery stock keeps moving: 33 apple variety
slugs had appeared with no blurb and no skip record. This pass closed the gap.

- **15 entries added** to `tools/scrapers/variety_descriptions/apple.json`: 12 freshly researched
  (cider apples Kingston Black, Yarlington Mill, Cimetiere de Blangy, Verite; columnar Ballerina
  Polka and Waltz; heritage Crofton Red, Beauty of Bath, Grimes Golden, James Grieve, Worcester
  Pearmain; plus Braeburn) and 3 adapted for duplicate-spelling slugs of already-verified cultivars.
- **18 slugs skipped**: 16 multi-graft / "pollinating duo" / "way" parse artifacts (combination
  trees, not single cultivars), apple-cactus-pink (not an apple cultivar), and Lovejoy's Lunch
  (no reputable sources found; skipping beats guessing).
- Every researched entry is verified against 2+ sources with at least one independent non-nursery
  reference. One unsupported claim was dropped at spot-check rather than published.
- Tests: full suite green (1537). Apple remaining = 0.

Shipped as a PR on `dale/varieties-apple`; deploy happens at the serialized close-out.
