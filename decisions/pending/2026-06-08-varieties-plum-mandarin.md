# Variety descriptions: plum + mandarin batch (treestock /variety pages)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-plum-mandarin)
**Context:** Continuing the DEC-178 variety-descriptions rollout (verified "what's unique"
blurbs on treestock `/variety/<slug>.html`). This window owned two species files,
`variety_descriptions/plum.json` and `variety_descriptions/mandarin.json`, and worked their
full live-stock variety lists (ranked by nursery count then in-stock) across two passes until
REMAINING reached 0 for both.

**Decision:** Describe 67 verified variety blurbs total (42 plum, 25 mandarin) and record the
rest of each species' live varieties as per-species skips. Both species are now COMPLETE
(0 remaining = every live-stock variety slug is either described or skipped). Each blurb clears
the gate: 2+ sources, 1+ independent (non-nursery) source, confidence_score >= 0.80, no em/en
dashes, Australian spelling, claims bound to sources. Mandarins are anchored mostly on UC
Riverside's Citrus Variety Collection, UF/IFAS and Citrus Australia (authoritative); plums on a
US plant patent, AgriFutures, ANBG, SANBI, the National Fruit Collection, Slow Food, and
third-party references (Wikipedia, Orange Pippin, Specialty Produce, Good Fruit Guide), with
nurseries used only for grounding.

**Why:** Plum and mandarin are two of the largest live catalogues on treestock and were
pilot-seeded but left with a long tail. Describing every genuinely-real variety adds unique,
citable content to high-traffic pages and strengthens the Treesmith funnel, while the obscure,
mis-parsed and duplicate tail is deliberately skipped (skipping is success). A notable subset of
the "Plum" catalogue is not botanically Prunus (Kakadu, Burdekin, Illawarra, Natal, Jambolan,
Java, Kaffir, Hog, Governor's plums); those blurbs open by clarifying the true species, which is
the single most useful thing such a page can say.

**Actions:**
- `tools/scrapers/variety_descriptions/plum.json`: 3 -> 42 described, skipped 71.
- `tools/scrapers/variety_descriptions/mandarin.json`: 4 -> 25 described, skipped 25.
- Pass-1 (earlier commit on this branch): +18 plum, +14 mandarin, 3 plum skips.
- Pass-2 (this run): +21 plum (incl. 9 non-Prunus "plum" clarifications), +7 mandarin; bulk
  skips folded in for multigraft trees, rootstock codes, typos, "type"-suffix duplicates of an
  already-described cultivar, nectarine mis-parses, and ornamentals mis-grouped under Plum.
- Accuracy calls during review: dropped a research draft for `plum-teagan-blue` (its only
  non-nursery source, freshfruitpalace.com, is a dead/unresolvable domain, so it could not clear
  the >=1 non-nursery gate); skipped `plum-sunrise-gulf` (no "Gulfsunrise"/"Sunrise" cultivar in
  the authoritative UF/IFAS Gulf-series list); corrected `mandarin-ponkanomi` (a proprietary
  Kiyomi x Ponkan trade name documented only by nurseries, NOT plain Ponkan). Re-pointed the
  Purdue Morton "Fruits of Warm Climates" citation for jambolan/java to its stable Internet
  Archive snapshot after the live NewCROP URL began serving a generic landing page.

**Status:** Shipped as a PR (updates existing PR #96). Not deployed (deploy + decision-log fold +
Progress tick happen at the serialized close-out, per docs/variety-descriptions-rollout.md).

**To revert:** Restore the prior `plum.json` / `mandarin.json`; the renderer falls back to no
blurb for any slug not present.
