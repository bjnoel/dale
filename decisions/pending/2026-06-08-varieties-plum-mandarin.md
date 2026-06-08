# Variety descriptions: plum + mandarin batch (treestock /variety pages)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-plum-mandarin)
**Context:** Continuing the DEC-178 variety-descriptions rollout (verified "what's unique"
blurbs on treestock `/variety/<slug>.html`). This window owned two species files,
`variety_descriptions/plum.json` and `variety_descriptions/mandarin.json`, and researched
their top live-stock varieties (ranked by nursery count then in-stock) not already covered by
the pilot batch.

**Decision:** Add 32 verified variety blurbs (18 plum, 14 mandarin) and record 3 plum skips.
Each blurb clears the gate: 2+ sources, 1+ independent (non-nursery) source, confidence_score
>= 0.80, no em/en dashes, Australian spelling, claims bound to sources. Mandarins are anchored
mostly on UC Riverside's Citrus Variety Collection and Citrus Australia fact sheets
(authoritative); plums on UF/IFAS, ASHS HortScience, RHS, the National Fruit Collection, and
third-party references (Wikipedia, Orange Pippin, Specialty Produce), with nurseries used only
for grounding.

**Why:** Plum and mandarin are two of the largest live catalogues on treestock and were
pilot-seeded but left with a long tail. Filling the genuinely-real, well-stocked varieties adds
unique, citable content to high-traffic pages and strengthens the Treesmith funnel, while the
obscure / mis-parsed tail is deliberately left to skip on thin sources.

**Actions:**
- `tools/scrapers/variety_descriptions/plum.json`: 3 -> 21 varieties; added a `skipped` array.
- `tools/scrapers/variety_descriptions/mandarin.json`: 4 -> 18 varieties.
- Accuracy calls during review: skipped `plum-king-billy` (its European-vs-Japanese
  classification rested only on a hobby site plus nursery listings), `plum-october-purple`
  (sources contradicted each other on flesh colour and breeder), and `plum-luisa` (documentation
  almost entirely nurseries, species classification disputed). Rebuilt `plum-flavour-supreme`
  to rest on an independent source (Wikipedia's Pluot article) after the research draft leaned on
  two nursery-tier sources; Dave Wilson Nursery reclassified to its true tier.

**Status:** Shipped as a PR. Not deployed (deploy + decision-log fold + Progress tick happen at
the serialized close-out, per docs/variety-descriptions-rollout.md).

**To revert:** Restore the prior `plum.json` / `mandarin.json` (3 and 4 varieties, no skipped);
the renderer falls back to no blurb for any slug not present.
