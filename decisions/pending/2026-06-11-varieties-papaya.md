# Variety descriptions: papaya (13 added, 21 skipped, species complete)

**Decided by:** Dale (parallel variety-rollout window, branch dale/varieties-papaya)

**Context:** The variety-descriptions rollout (DEC-178 layer, runbook
docs/variety-descriptions-rollout.md) had no papaya file yet; the server's live stock carries
34 papaya variety slugs across Australian nurseries.

**Decision:** Research all 34 live papaya slugs via fan-out subagents (2+ reputable sources,
at least one non-nursery, skip if thin) and ship a complete
tools/scrapers/variety_descriptions/papaya.json in one pass: 13 verified blurbs, 21 skips.

**Why:** Papaya's catalogue divides cleanly: a verifiable core (Australian breeding-program
hybrids RB4/H13/YD1B backed by a peer-reviewed PMC flavour study and the QLD DAF papaw kit;
Red Lady and Sunrise Solo with breeder/university documentation; Richter Gold in the DAF kit;
two Vasconcellea relatives and the Thai Khaek Dam type) and a long unverifiable tail (generic
"Bisexual Red" style sex/colour descriptors, plus trade names like Red Army and Southern Red
that appear ONLY in nursery copy). Accuracy over coverage: the tail is recorded in the
per-species skipped ledger so re-runs never re-attempt it.

**Actions:**
- papaya.json: 13 entries (yellow-h13, red-rb4-hybrid, rb4-hybrid, rb4-hybrid-bi-sexual,
  yellow-yd1b-hybrid, red-lady, paw-paw-red-lady, sunrise-solo, sunrise-solo-hybrid-bi-sexual,
  richter-gold, col-de-monte, berry-oak-leaf, torpedo), 21 skipped slugs.
- Spot-checks beyond the agents' own sourcing: PMC9181177 Brix figures confirmed (RB4 10.6,
  H13 9.2 lowest); QLD DAF papaw kit PDF text-extracted and confirmed Richter Gold + Hybrid 13
  as yellow dioecious SE QLD varieties; STFC hybrid-code convention confirmed; Daleys Torpedo
  page confirmed the Khak-dam identification; Known-You, Diggers, UF/IFAS and ITFNet pages
  fetched for Red Lady/Sunrise Solo.
- Corrections applied during review: RB4 "red to pink" tightened to red-fleshed (per PMC);
  Red Lady entries rewritten onto verified sources after ECHO/ResearchGate 403'd (UF/IFAS
  Sarasota + ITFNet + breeder + Diggers), dropping the unverifiable 12 Brix and ringspot
  claims; Thai Red Lady moved to skipped (cannot verify it is the Known-You hybrid).

**Status:** Shipped as PR from dale/varieties-papaya. Papaya remaining = 0 (DONE for the
Progress list at close-out). Deploy happens at the serialized close-out, not in this branch.

**To revert:** delete tools/scrapers/variety_descriptions/papaya.json.
