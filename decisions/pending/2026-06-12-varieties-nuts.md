# Variety blurbs for nut species: almond, pistachio, walnut

**Decided by:** Dale (parallel variety-descriptions rollout, window dale/varieties-nuts)
**Context:** The variety-descriptions layer (DEC-178) needed coverage extended to the nut
catalogue. Almond, pistachio and walnut had live /variety pages but no "what's unique" blurbs.
**Decision:** Researched and committed verified blurbs for the in-stock nut varieties across
those three species, one species file each, following docs/variety-descriptions-rollout.md.

**What shipped:**
- almond.json: 15 varieties described, 10 skipped.
- pistachio.json: 3 varieties described, 4 skipped.
- walnut.json: 5 varieties described, 0 skipped.
- Totals: 23 varieties added, 14 skipped.

**Why:** Every blurb clears the generation gate (>=2 sources, >=1 independent non-nursery
source, confidence_score >= 0.80, no em/en dashes, Australian spelling). Several listings were
clarified rather than padded: "Indian" almond is Terminalia catappa (a tropical tree, not a true
almond), and "Chinese" pistachio is Pistacia chinensis (an ornamental/rootstock, not the edible
nut). Skips were thin-source or generic-parse listings (for example "Brandes Jordan" almond, which
had only nursery listings; "Californian Papershell", an ambiguous trade name; and parser noise like
"almond-tree", "almond-pair", "pistachio-nut-female").

**Actions:** none outstanding; blurbs render at the next build_variety_pages.py run.
**Status:** Shipped via PR (branch dale/varieties-nuts). almond, pistachio and walnut each
report remaining = 0, so all three are DONE for the Progress list.
**To revert:** delete the three species JSON files; the renderer falls back to no blurb.
