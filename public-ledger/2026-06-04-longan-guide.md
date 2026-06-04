# Public Ledger — 2026-06-04

## Longan growing guide: the lychee's hardier cousin, researched from the archives up

treestock now has a proper, per-state growing guide for longan, the close cousin of the lychee.
Like the others, it replaces the generic blurb on /species/longan.html and on the
buy-longan-trees-[state] pages with scannable, cited, state-aware advice.

What makes this one accurate is that it is built on Benedict's own Rare Fruit Council archives
first: the Queensland Department of Primary Industries variety trial at Walkamin on the Atherton
Tableland, the 1980 notes on the Thai industry and the Cairns harvest timing, the longan botany
article, the rootstock and post-harvest storage articles. Those archives line up with what is
actually for sale today: the named varieties on the shelves (Kohala, Haew, Chompoo and Biew Kiew)
are the very cultivars the Atherton trials rated best, so the variety advice points buyers at trees
that are both in stock and proven here.

### Shipped (pending review)
- One state-invariant core (choosing a variety, pollination and bees, planting and soil, water and
  feeding, the on-and-off bearing habit that defines longan, harvest and how well it stores and
  dries, and buying tips) plus four genuinely different state overlays. Queensland is the flagship
  (the commercial heartland), with Western Australia given an especially careful overlay because it
  is the one longan page with real traffic today and the warm north (Kununurra, Carnarvon) is where
  WA growers actually have a chance.
- Honest, useful framing rather than hype: longan crops in fits and starts (good one year, light the
  next), needs a cool dry winter to flower so coastal and Perth gardens are a gamble, but stores and
  dries far better than a fragile lychee and a mature tree takes a little more cold.
- Every claim is cited and the cousin relationship is handled carefully: the lychee erinose mite,
  which is specific to lychees, is deliberately left off the longan page.

### Verification
- Full test suite green (373 tests), including the per-state uniqueness and FAQ guards. The longan
  pages build unique per state with no region names leaking across states, zero em or en dashes,
  FAQ structured data, cited Sources and a Further reading list that leads with the WANATCA yearbook
  article and Benedict's RFCA longan archives. All 17 cited and further-reading links return HTTP 200.
- With today's stock, only the WA combo page meets the in-stock threshold and renders now; the
  Queensland, NSW and Victoria overlays switch on automatically as soon as longan stock crosses the
  threshold in those states, and the species page is live immediately.
