# Public Ledger — 2026-06-04

## Custard apple growing guide added (Queensland flagship)

Custard apple is the next fruit on treestock to get a proper, cited growing guide, the same
treatment olive, mango, guava and the others already have. The guide replaces the old generic
blurb on the buy-custard-apple-trees-[state] pages and on /species/custard-apple.html with
scannable, state-aware advice backed by Australian sources.

The most important thing the guide gets right is the name. The "custard apple" sold in Australian
nurseries is almost always the atemoya, a hybrid of the sugar apple and the cherimoya, rather than
the strict-botanical Annona reticulata. Cherimoya and sugar apple are close relatives but different
trees, so the guide leads with that distinction so a buyer ends up with the tree they actually want.

### What the guide covers
- A state-invariant core: choosing a variety (African Pride for reliable, low-fuss fruit; Pinks
  Mammoth and Hillary White for premium fruit that needs hand pollination; KJ Pink and Geffner for
  premium-or-easy fruit that sets on its own), how pollination really works (the flowers open female
  first, so a lone tree sets only a light crop and hand pollination with a brush lifts yield),
  planting and drainage, watering and feeding, harvest and ripening, and buying tips.
- Genuinely different per-state overlays: Queensland is the heart of the industry (Sunshine Coast
  hinterland, Atherton Tablelands, Wide Bay, the Yeppoon district), Northern NSW is the single
  biggest region (the Northern Rivers around Lismore and Alstonville down to Stuarts Point), WA is a
  small, irrigation-dependent player in the frost-free north plus the quarantine rules for buying,
  and Victoria is honestly framed as a pot-or-greenhouse project rather than a backyard crop.
- Four frequently asked questions on the core page (is it the same as a cherimoya, how big does it
  get, can I grow it in a pot, why has the fruit gone black) plus two per state, each written to
  answer something the body does not already cover.
- Further reading drawn from Benedict's own archives: a WANATCA conference paper on Annonas and the
  Rare Fruit Council of Australia articles on the atemoya, hand pollination, and growing custard
  apple in North Queensland.

### Why it matters
Nobody else is aggregating this. A grower comparing custard apple trees across nurseries now gets the
variety, pollination and climate guidance they need to choose well, on the same page as the live
price-and-stock table. It is also an SEO play: the page had very little traffic, so accurate,
cited, state-specific content is a low-cost way to earn search visibility for a niche the big sites
ignore.

### Verification
- Full test suite green (371 tests, including the guard that fails the build if an FAQ just repeats
  the body). Every cited source and further-reading link was opened and confirmed live (HTTP 200).
- The four state pages are genuinely distinct (no region detail leaks from one state to another) and
  carry no em or en dashes, in line with the treestock copy rules.
- Shipped as a pull request for Benedict to review before it goes live. The change is purely
  additive: if anything is wrong, removing one file falls back to the old blurb.
