# 2026-06-11 — Variety descriptions: finger-lime tail pass (window: finger-lime)

Part of the parallel variety-descriptions rollout (docs/variety-descriptions-rollout.md).
This window owned the finger-lime species file and finished its live tail.

## What happened

- Computed REMAINING from live server stock: 46 live finger lime variety slugs, minus the
  pilot's 5 blurbs and 3 skips, left 38 to research.
- Fanned out 5 parallel research subagents over disjoint slices, each required to verify
  facts against 2+ reputable sources with at least 1 non-nursery source, skipping anything
  thin rather than guessing.
- Added 10 verified "what's unique" blurbs; skipped 28 slugs with reasons (generic colour
  labels, nursery-only sourcing, mislabelled species, parser noise).
- Quality gates applied during review: rejected the researched Wauchope entry because all
  four of its sources were grower storefronts; dropped a journal citation from Chartreuse
  that could not be verified (paywalled, and the agent had mislabelled the journal);
  softened an unsupported "eight registered cultivars" figure in the D Emerald blurb.
- Verified every cited source URL responds (20 URLs checked), spot-checked content of the
  suspicious ones, and confirmed the Jali Red and Durham's Emerald ACRA registrations and
  the CSIRO Sunrise Lime pages directly.
- Full test suite green (1509 tests). No golden regen needed (finger-lime is not a fixture
  species).

## Outcome

finger-lime.json: 15 varieties + 31 skips = all 46 live slugs covered, 0 remaining.
Finger-lime can be marked DONE on the rollout Progress list at close-out. Deploy is
deferred to the serialized close-out per the runbook.

Highlights among the new blurbs: Jali Red (ACRA-registered, Whian Whian NSW origin),
Mt White (actually Citrus garrawayi, a Cape York rainforest species), Sunrise (the CSIRO
finger lime x calamondin hybrid), Red Champagne (commercial favourite with postharvest
research behind it), and Durham's Emerald under both of its trade listings.
