# Variety descriptions: Annona group (custard-apple, sugar-apple, soursop) plus mangosteen

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-annona)
**Context:** Continuing the treestock /variety "what's unique" blurb rollout
(DEC-178, runbook docs/variety-descriptions-rollout.md). This window covered the
Annona relatives and the Garcinia "mangosteens": custard-apple (cherimoya/atemoya),
sugar-apple, soursop, and mangosteen. REMAINING was computed from live server stock
minus each species file's existing varieties and skipped lists.
**Decision:** Added 10 verified variety blurbs and recorded 14 thin-source skips
across the four species. Each blurb clears the gate (>=2 sources, >=1 non-nursery,
every claim cited, no dashes, confidence_score >= 0.80); accuracy was preferred over
coverage so anything resting on nursery marketing copy alone was skipped.

Added (10):
- custard-apple: fino-de-jete, bays, white (cherimoya cultivars; white kept at
  medium confidence because source descriptions of size/sweetness conflict).
- mangosteen: purple (true Garcinia mangostana), lemon-drop (G. intermedia),
  yellow (umbrella name for G. dulcis / G. xanthochymus). The blurbs are explicit
  that only "purple" is the true mangosteen.
- soursop: cuban-fiberless, whitman-fibreless (the two documented fibreless lines,
  both backed by the RFCA archive).
- sugar-apple: kampong-mauve, purple (the purple/red-skinned Annona squamosa forms).

Skipped (14):
- custard-apple: atkinson, sofia (nursery-only sourcing), rosa (no reputable
  sources), seedling (generic parser noise).
- mangosteen: honey-drop (nursery-only "Tangosteen" marketing name).
- soursop: golden (conflicting blog/nursery claims), diny (no sources), kyogle,
  giant (nursery-only), fruit-tree (parser noise).
- sugar-apple: none.

**Why:** Annona and Garcinia are high-interest collector species on treestock with
no variety blurbs yet, and several live varieties (the "mangosteens" especially)
are commonly confused across different Garcinia species, so a verified blurb adds
real clarity. Skipping is success: a fabricated cultivar fact is worse than no blurb.
**Actions:** Wrote tools/scrapers/variety_descriptions/{soursop,sugar-apple,
mangosteen}.json (new) and merged 3 entries + 4 skips into custard-apple.json. Full
test suite green (1605 tests). No golden regen needed (none of these are fixture
species).
**Status:** Shipped via PR on branch dale/varieties-annona. Deploy is the serialized
close-out (build_variety_pages.py + Cloudflare purge), not this run.
**To revert:** Drop the three new files and revert the custard-apple.json merge; the
renderer falls back to no blurb for un-enriched varieties.
