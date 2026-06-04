# Public Ledger — 2026-06-04

## Rambutan growing guide: the hairy cousin of the lychee, researched from the archives up

treestock now has a proper, per-state growing guide for rambutan, the spiny red (or yellow) tropical
fruit that is a close relative of the lychee and longan. Like the others, it replaces the generic
blurb on /species/rambutan.html and on the buy-rambutan-trees-[state] pages with scannable, cited,
state-aware advice.

What makes this one accurate is that it is built on Benedict's own Rare Fruit Council archives
first: the North Queensland crop summary (with the flower biology and the southern growing limit
around Innisfail), the far-north cultivation notes, the Kamerunga leaf-analysis work that drives the
feeding advice, the fruit-drop report, the postharvest study, and a grower's first-hand account of
trying rambutan in the cooler subtropics. Those owned sources are backed up by the Northern Territory
Government agnotes, Business Queensland, AgriFutures, University of Hawaii extension and the Morton
reference, so the facts line up across several authorities.

### Three things the guide gets right
- Pollination: this is where rambutan differs from its cousins. Most named clones carry almost only
  female-functioning flowers and make very little pollen, so a lone tree often sets a light crop of
  small, pulpless fruit. The guide explains that, unlike a longan, a rambutan really wants a second,
  different tree nearby and plenty of bees to crop well.
- Feeding: rambutan is unusually sensitive to chloride, so the guide warns against muriate of potash
  (a very common potassium fertiliser) and points growers to potassium nitrate or sulphate of potash
  instead, straight from the Kamerunga leaf-analysis research.
- Fruit fly: it would be easy to copy the standard tropical-fruit pest warnings across, but rambutan
  is not on the Queensland fruit fly host list, nor in the Australian fruit fly handbook, so the guide
  says so rather than giving a false warning.

### Shipped (pending review)
- One state-invariant core (choosing a variety, the pollination question, planting and shelter, water
  and feeding, harvest and eating, and buying tips) plus four genuinely different state overlays.
  Queensland is the flagship, since the wet tropical coast behind Cairns (Innisfail, Tully, Mission
  Beach, Babinda) is the heart of Australian rambutan growing, with the Top End of the Northern
  Territory the only other real region. Western Australia gets an honest overlay (the tropical
  Kimberley around Kununurra is the only candidate and even there it is unproven, while Perth is out),
  New South Wales is treated as marginal at best (its far north coast is too cool in winter, where the
  hardier lychee and longan still manage), and Victoria as a heated-glasshouse curiosity.

### Verification
- Full test suite green (625 tests), including the per-state uniqueness and FAQ guards, plus
  rambutan-specific checks for the chloride feeding rule, the pollen-partner point, and the fruit-fly
  fact. The pages build unique per state with no region names leaking across states, zero em or en
  dashes, FAQ structured data, cited Sources, and a Further reading list that leads with the Rare
  Fruit Council archives and the WANATCA conference paper on tropical fruits in Australia. Every cited
  and further-reading link returns HTTP 200.
- The species page is the live deliverable; the Queensland, NSW, Victoria and WA combo overlays switch
  on automatically once rambutan stock crosses the in-stock threshold in those states (all four
  overlays were verified by building them against real nursery stock).
