# Variety descriptions rollout: apple (+64) and pomelo (+1), both species DONE

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-apple-pomelo, two passes)
**Context:** Continuing the DEC-178 per-variety "what's unique" blurb layer on treestock
`/variety/<slug>.html` pages, per `docs/variety-descriptions-rollout.md`. This window owned the
apple and pomelo species files. Apple is a large catalogue (150 live cultivar slugs, only 6 had
blurbs from the pilot); pomelo is small (12 live slugs, none described, mostly nursery trade names).
Worked in two passes in the same worktree (pass 1: top apple varieties + Nam Roi; pass 2: the apple
heritage/cider/columnar tail, then classify the remainder), each REMAINING recomputed from the branch.

**Decision:** Researched and committed 64 verified apple blurbs and 1 pomelo blurb (70 apple
described in total counting the pilot's 6, 1 pomelo), and recorded 91 skips (80 apple, 11 pomelo) in
the per-species `skipped` arrays. Both species now have 0 remaining (DONE). Accuracy over coverage:
every entry has >=2 reputable sources (>=1 non-nursery), claims bound to sources, no fabricated
figures. Twelve non-overlapping research subagents across the two passes each verified >=2 sources
per variety against the gate; thin or unidentifiable cultivars were skipped, not guessed.

**Why:**
- Apple is the second-biggest catalogue on the site. Pass 1 covered the famous commercial, low-chill
  and heritage core. Pass 2 added the well-documented long tail: English/American heritage dessert and
  cooking apples (Bramley's Seedling, Golden Harvey, Hubbardston Nonsuch, Tydeman's Early Worcester,
  the Flower of Kent "Isaac Newton's", Five Crown Pippin, Freyberg), traditional English and French
  cider apples (Sweet Alford, Sweet Coppin, Improved Foxwhelp, Frequin Rouge, Belle Cacheuse,
  Chataignier, Reine des Hâtives, Fenouillet Gris, Forfar Pippin), low-chill and Australian/NZ
  (Ein Shemer, Jerseymac, Vista Bella, Wandin Pride, Magnus Summer Surprise), red-fleshed (Redlove),
  highly-coloured sports (Royal Gala, Red Fuji) and the columnar/dwarf lines (Bolero and Flamenco
  Ballerina, the Holovousy columnar Cumulus and Herald, dwarf Pinkabelle and Leprechaun). The NSW DPI
  cider page (.gov.au, authoritative) and the Czech Holovousy journal were spot-checked by direct fetch.
- The rest of the apple catalogue is parser noise rather than distinct cultivars: multigraft combo
  trees (2way/3way/tree-3-way), alternate spellings of varieties already described (Coxs Orange Pippin,
  Gravensteins, Golden Dorsett, Jonothan, Lady William, Einshimer, Montys Surprise), form variants of
  described varieties (columnar/stepover/pome-fruit/PBR/Trixzie duplicates) and ambiguous one-word
  fragments (Star, Black, Winter, Velvet, Rose, Quince, Snow, Sweet Cheeks). These are recorded as
  skips so the species reads as complete and is never re-attempted.
- Pomelo is dominated by nursery trade names (Thai Sun, Watsons, Rouge Red, Carter's Red, K15) with no
  independent corroboration, so only the well-documented Vietnamese Nam Roi cleared the bar. Skipping
  the rest (including the tangelo mis-parse and the generic "Red"/"White" colour fragments) is the
  correct, expected outcome.

**Actions:**
- `tools/scrapers/variety_descriptions/apple.json`: 70 described varieties, 80 slugs in `skipped`,
  0 remaining of the 150 live cultivar slugs. Pass 2 added 30 entries (heritage/cider/columnar tail)
  and skipped 4 unverifiable cultivars (Peau d'Âne, Antoinette, Easy Care, Harmony) plus 67 noise
  slugs (multigraft / alternate-spelling / form-variant / ambiguous).
- `tools/scrapers/variety_descriptions/pomelo.json`: 1 described (Nam Roi), 11 skipped, 0 remaining.
- Apple is a golden-fixture species, but the pinned variety pages are apple-pink-lady and
  apple-dorsett-golden (both already blurbed), and none of the new entries overlaps them, so no golden
  regeneration was needed.
- `python3 -m unittest discover tests/` green.

**Status:** Shipped via PR #95 (not deployed). Apple and pomelo both 0 remaining (DONE; tick the
Progress list for both at close-out). Deploy + progress-tick are the serialized close-out.

**To revert:** Drop the new apple/pomelo entries and skips; the renderer falls back to no blurb for
un-enriched varieties (graceful).
