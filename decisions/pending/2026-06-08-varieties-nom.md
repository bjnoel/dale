# Variety descriptions rollout: nectarine, orange, mulberry COMPLETE (window nom)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-nom)
**Context:** Continuing the per-variety "what's unique" blurb rollout (DEC-178). This window owned
nectarine, orange and mulberry and ran in two passes (the worktree is reused across `/clear`).
REMAINING was recomputed each pass from live server stock (build_variety_pages.group_by_cultivar)
minus each species file's `varieties` and `skipped`. Non-overlapping general-purpose research
subagents verified each candidate against multiple reputable sources (UC Riverside Citrus Variety
Collection, UF/IFAS, US plant patents, SAPO Trust variety registry, Dave Wilson, Wikipedia, Orange
Pippin, Good Fruit Guide; nurseries for grounding only).

**Decision:** All three species are now finished (0 remaining live slugs). The branch holds, across
the three species files only (`tools/scrapers/variety_descriptions/{nectarine,orange,mulberry}.json`):
- nectarine: 22 verified blurbs, 36 skipped (DONE)
- orange: 43 verified blurbs, 36 skipped (DONE)
- mulberry: 18 verified blurbs, 6 skipped (DONE)

This second pass added 52 entries (nectarine +15, orange +28, mulberry +9). Of those, 13 were newly
researched distinct cultivars and 39 were clones: spelling/format variants of an already-verified
variety carry that variety's verified content under the live slug (the documented lychee
kwai-may/kwai-mai pattern), so the blurb renders on every real page. Examples: Flavortop/Flavourtop,
the Lane's Late Navel cluster (Lane, Lane's Navel, Navel Lanes Late), Cara Cara Navel/Blood Navel,
the Tarocco Rosso/Ippolito clones, Washington/Newhall/Navelina label variants, Pakistan(=Pakistan
Black), the Shahtoot variants, OkeeDokee(=cv Mesembrine). New research this pass: nectarine Spicezee,
Trixzie Nectazee, Sunraycer, Sunlite, Maygrand, Firebrite, OkeeDokee, Sugar-and-Spice; orange Jaffa
(Shamouti), Maltese blood, Delta and Midknight Valencia, Seedless Valencia.

**Why:** Accuracy over coverage. Each kept entry clears the gate (>=2 sources, >=1 non-nursery,
confidence_score >= 0.80, every claim cited, no orphan sources, no dashes, Australian spelling).
Anything resting only on Australian nursery trademarks (Sunbob, Sunwright, Queen Giant, Sweet
Sensation, Sunny Belle, Cannonball, Flat Tango, Aussie Sunset blood orange, mulberry Angela) was
skipped, not guessed. Genuine mis-parses were skipped with reasons: generic terms (Nectarina,
Peacharine, Donut), wrong-fruit parses (Peachcot is peach x apricot, mulberry Giant Yellow is
Myrianthus not Morus), multi-graft "2-way" tree listings, marketing slogans (No Bubble No Trouble),
not-a-sweet-orange (Lemonade is a lemon x mandarin), and the large block of ornamental colour
mis-parses on the orange species page (canna, clivia, bougainvillea, hibiscus, grevillea, rose,
spider plant, etc.). All skips are recorded in each file's `skipped` array so a future rank shows 0.

**Actions:** Wrote the three species JSON files; `python3 -m unittest discover tests/` green (1401
tests). No golden regen (none of nectarine/orange/mulberry is a golden-fixture species). No deploy,
no decision-log edit, no progress tick (all of that is the serialized close-out).

**Status:** Shipped via PR #97 from dale/varieties-nom. All three species reached 0 remaining, so
nectarine, orange and mulberry can be ticked DONE on the rollout Progress list at close-out.

**To revert:** Restore the three species files to their pre-run state and rebuild the variety pages.
The renderer falls back to no blurb for any removed entry.
