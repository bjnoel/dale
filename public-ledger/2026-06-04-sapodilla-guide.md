# Public Ledger — 2026-06-04

## Sapodilla growing guide: a rare tropical, researched from the archives up

treestock now has a proper, per-state growing guide for sapodilla (also known as chico, chiku,
sapota or naseberry), one of the harder fruit trees to source in Australia. Like the others, it
replaces the generic blurb on /species/sapodilla.html and on the buy-sapodilla-trees-[state] pages
with scannable, cited, state-aware advice.

What makes this one accurate is that it is built on Benedict's own Rare Fruit Council archives
first: the "Sapodilla in Australia" culture article (with the North Queensland flowering and
harvest timing, the planting and fertiliser detail, and the pollen-sterility warning for
seedlings), the sapodilla fact sheet, and the clonal-propagation article. Those archives line up
with what is actually for sale: the named grafted varieties on the shelves (Krasuey, Sawo Manila and
Ponderosa) are the Asian selections the guide points buyers toward, alongside the dwarf Makok for a
pot.

### Two things the guide gets right that the old blurb did not
- Pollination: the old blurb said sapodilla is simply self-fertile. It is not that simple. Some
  named varieties cannot set fruit on their own pollen and need a second tree nearby, while others
  fruit alone but crop more heavily with a neighbour, so the guide says exactly that, with a citation
  to the University of Florida.
- Pests: there is a common mix-up where the latex-rich skin is said to make sapodilla resistant to
  fruit fly. That actually refers to a different fruit (mamey sapote). Sapodilla is on the
  Queensland fruit fly host list, so the guide tells growers in fruit-fly country to bag or bait,
  rather than giving them false confidence.

### Shipped (pending review)
- One state-invariant core (choosing a variety, seedling versus grafted, do you need two trees,
  planting and soil, water and feeding, the tricky business of telling when the fruit is ripe to
  pick, pruning and size, and buying tips) plus four genuinely different state overlays. Queensland
  is the flagship, since the far north (the wet tropics coast and the Atherton Tableland) is where
  sapodilla actually grows; the Northern Territory around Darwin grows the most. Western Australia
  gets an honest overlay (the warm north around Carnarvon and Kununurra, not cool Perth), New South
  Wales is limited to the frost-free Northern Rivers, and Victoria is treated as a glasshouse
  curiosity, since it is far too cold and frosty for a tropical tree.

### Verification
- Full test suite green (374 tests), including the per-state uniqueness and FAQ guards. The sapodilla
  pages build unique per state with no region names leaking across states, zero em or en dashes, FAQ
  structured data, cited Sources and a Further reading list that leads with the WANATCA yearbook
  article "The Sapodilla in Southeast Asia" and Benedict's Rare Fruit Council archives. Every cited
  and further-reading link returns HTTP 200.
- The species page is live immediately; the Queensland, NSW, Victoria and WA combo overlays switch on
  automatically as soon as sapodilla stock crosses the in-stock threshold in those states (all four
  overlays were verified by building them against real nursery stock).
