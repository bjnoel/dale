# Public Ledger, 2026-06-04

## Pear growing guide: the pome cousin of apple, with the one fact most growers get wrong

treestock now has a proper, per-state growing guide for pear. Like the others, it replaces the
generic blurb on /species/pear.html and on the buy-pear-trees-[state] pages with scannable, cited,
state-aware advice, and it cross-links to the apple guide, since the two pome fruits share most of
their care, pests and pollination habits.

The species page was already getting search traffic (hundreds of impressions a month) but ranking
poorly, so it is a good candidate for a richer, more trustworthy page. The guide is built on the
Australian pear industry (Apple and Pear Australia), the state agriculture departments and
horticultural research, and it ties every variety it recommends to what is actually for sale: the
European pears on the shelves (Williams Bon Chretien, Beurre Bosc, the Australian-bred Packham's
Triumph, Josephine and Corella), the crisp nashi (Nijisseiki, Shinseiki, Hosui, Chojuro and Ya Li),
and the low-chill pears for warm gardens (Flordahome, Hood and Bonza).

### Two things the guide gets right that the old blurb did not
- Harvest: this is the fact that trips up most home growers. European pears are the rare fruit you
  pick while still hard and ripen indoors, never on the tree. A pear left to ripen on the branch
  ripens from the inside out and turns brown and gritty at the core before the outside is ready. The
  winter pears (Beurre Bosc, Josephine, Winter Nelis) need a few weeks of cold before they will
  ripen at all. Nashi are the exception that proves the rule: you leave them on the tree and eat them
  crisp like an apple.
- Pests and biosecurity: Western Australia is one of the few places on earth free of codling moth,
  the worst pear and apple pest, and Australia as a whole is free of fire blight, the serious
  bacterial disease of pears. The guide frames both honestly (a real WA advantage, and a national
  biosecurity win) rather than telling growers to spray for a pest they do not have, while still
  naming the pests they do have: pear and cherry slug everywhere, Mediterranean fruit fly in WA, and
  Queensland fruit fly in the eastern states.

### Shipped (pending review)
- One state-invariant core (choosing between European and nashi pears, pollination and self-fertile
  options, rootstocks and tree size, planting and soil, water and feeding, the pick-firm-ripen-off-
  the-tree harvest, and buying tips) plus four genuinely different state overlays. Victoria is the
  flagship, because the Goulburn Valley grows about 90 per cent of Australia's pears and gave the
  industry its canneries and the Tatura Trellis. New South Wales tells the story of Packham's
  Triumph, the variety bred at Garra near Molong that became Australia's main pear. Western Australia
  covers the cool Southern Forests and nashi in the warmer Swan Valley, and Queensland splits between
  the high Granite Belt for European pears and nashi for the subtropical coast.

### Verification
- Full test suite green (630 tests), including the per-state uniqueness and FAQ guards. The pear
  pages build unique per state with no region names leaking across states, zero em or en dashes, FAQ
  structured data, cited Sources, and a Further reading list with the WANATCA yearbook article on
  nashi. Every cited and further-reading link returns HTTP 200.
- The species page is live immediately; the Victoria, NSW, Queensland and WA combo overlays switch on
  automatically wherever pear stock crosses the in-stock threshold (all four overlays were verified
  by building them against real nursery stock).
