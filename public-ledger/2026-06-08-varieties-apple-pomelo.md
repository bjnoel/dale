# 2026-06-08 — Variety descriptions: apple + pomelo (both complete)

Added verified "what's unique about this variety" blurbs to the treestock `/variety` pages for
apple and pomelo, part of the DEC-178 rollout (branch `dale/varieties-apple-pomelo`, two passes).
Both species are now fully triaged: every distinct, verifiable cultivar has a blurb and the rest is
recorded as a skip, so there is 0 remaining for each.

**Apple (70 described, 80 skipped, 0 remaining of 150 live):** pass 1 covered the commercial,
low-chill and heritage core; pass 2 added the documented long tail. New in pass 2: English and
American heritage apples (Bramley's Seedling, Golden Harvey, Hubbardston Nonsuch, Tydeman's Early
Worcester, Flower of Kent / "Isaac Newton's", Five Crown Pippin, Freyberg), traditional cider apples
(Sweet Alford, Sweet Coppin, Improved Foxwhelp, Frequin Rouge, Belle Cacheuse, Chataignier, Reine
des Hâtives, Fenouillet Gris, Forfar Pippin), low-chill and Australian/NZ (Ein Shemer, Jerseymac,
Vista Bella, Wandin Pride, Magnus Summer Surprise), red-fleshed Redlove, the highly-coloured sports
Royal Gala and Red Fuji, and the columnar/dwarf lines (Bolero and Flamenco Ballerina, Cumulus,
Herald, Pinkabelle, Leprechaun). The skipped slugs are not real cultivars: multigraft combo trees,
alternate spellings of varieties already described, dwarf/columnar form variants of described
varieties, and ambiguous one-word fragments.

**Pomelo (1 described, 11 skipped, 0 remaining of 12 live):** only Nam Roi (a documented Vietnamese
cultivar) cleared the two-source bar; the rest are nursery trade names or generic colour fragments
with no independent source.

Every blurb is verified against at least two reputable sources (at least one non-nursery), with a
stored claims-to-sources ledger and no fabricated figures; four cultivars that could not be confirmed
(Peau d'Âne, Antoinette, Easy Care, Harmony) were skipped rather than guessed. Tests green; shipped
via PR #95, not yet deployed.
