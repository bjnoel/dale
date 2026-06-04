# Public Ledger — 2026-06-04

## Lime growing guide: a citrus guide built on the owned archives and the .gov record

treestock now has a proper, per-state growing guide for the lime, one of the citrus species in the
rollout (the orange guide is its parallel sibling). Like the others, it replaces the generic blurb
on /species/lime.html and on the
buy-lime-trees-[state] pages with scannable, cited, state-aware advice that is genuinely different in
each state.

Lime is a good test of the "lean on government and industry sources, plus Benedict's own archives"
approach, because the rare-fruit archives are thin on such a common citrus. So the guide is built on
the Rare Fruit Council of Australia's Citrus archives (Improved Lemon and Lime Varieties, Citrus
Rootstocks, and the Citrus overview), cross-checked against the Queensland citrus kit, DPIRD Western
Australia, Citrus Australia, CSIRO and university citrus research. Every cited and further-reading
link returns HTTP 200.

### Why each state reads differently
- New South Wales is the flagship: it holds both the largest citrus region in Australia (the
  Riverina, around Griffith and Leeton) and the country's best lime coast (the subtropical Northern
  Rivers around Alstonville and Coffs Harbour), so the guide explains why a lime is easy on the warm
  coast and needs a sheltered, frost-free spot inland.
- Queensland is the warm heartland that grows most of Australia's limes, with the Atherton Tableland
  the biggest lime district, so a Tahitian lime there can crop most of the year.
- Western Australia is defined by citrus biosecurity. The guide explains, honestly, that citrus is
  tightly controlled at the WA border (so most eastern nurseries will not post citrus there, and
  buying a WA-grown tree is the way to go), and that the backyard pests are Mediterranean fruit fly
  and, now, citrus gall wasp, which has become established across Perth.
- Victoria is at the cold limit, where limes are best grown in a pot that can be sheltered from
  frost, with the warm Sunraysia district around Mildura the exception.

### A few things the guide gets right that a generic blurb would not
- Limes are self-fertile, so a single tree crops on its own, and the Tahitian lime is seedless
  because it sets fruit without pollination at all.
- Pick limes while they are still green: that is when the juice and aroma peak, and it heads off
  stylar-end rot. A yellow lime is over-ripe, not riper.
- Rangpur lime and sweet lime are flagged as not being true limes, and the separate Australian finger
  lime is linked to its own page rather than lumped in.
- It does not overclaim: the Tahitian lime is described as tolerant of tristeza virus rather than
  "resistant", and Western Australia is correctly described as having citrus gall wasp established,
  not free of it.

### Verification
- Full test suite green (532 tests), including the per-state uniqueness, no-dash, FAQ structured-data
  and FAQ-overlap guards, plus correctness guards specific to lime. The four combo pages and the
  species page were built against real nursery stock: unique per state, no region names leaking
  across states, zero em or en dashes, cited Sources, and a Further reading list of Benedict's Rare
  Fruit Council Citrus archives.
- The species page is live immediately; the four state overlays are already generating from current
  stock (lime is in stock across many nurseries in every state).
