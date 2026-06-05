# Public Ledger — 2026-06-04

## Apricot growing guide: the fussiest stone fruit, done state by state

treestock now has a proper, per-state growing guide for apricot (Prunus armeniaca). Like the others,
it replaces the generic blurb on /species/apricot.html and on the buy-apricot-trees-[state] pages with
scannable, cited, state-aware advice. Apricot is the first stone fruit of summer and, honestly, the
fussiest to grow, so the guide leans hard on getting the climate, variety and pruning right.

The variety advice is tied to what is actually for sale: Trevatt (the classic Australian drying and
canning apricot), Moorpark (the big old all-rounder), Storey's, Divinity, Glengarry, the low-chill
Newcastle, and the low-chill dwarf Fireball, plus the plum and apricot cross Plumscrumptious. So a
reader who likes a named tree in the in-stock table can read why it suits, or does not suit, their
district.

### Three things the guide gets right that a generic blurb would not
- Pollination: apricots are self-fertile, so a single tree crops on its own. That is the one big
  thing that makes them easier than plums or cherries, and the guide says so up front.
- Pruning: apricots must be pruned in late summer or early autumn, never in winter. They are very
  prone to bacterial canker and silver leaf, and a winter cut in cool, damp weather is how a pruning
  wound ends up killing a whole limb. This is the single most common way people lose an apricot tree,
  and the old blurb never warned about it.
- Leaf curl: apricots do not get peach leaf curl (that is a peach and nectarine problem), so the
  guide does not send people off to buy a spray they do not need. Their real fungal troubles are
  brown rot and shot hole.

### Shipped (pending review)
- One state-invariant core (choosing a variety, matching the variety to your winter chill,
  pollination, planting and soil, the summer-pruning rule, water and feeding, harvest and ripening,
  the pests and diseases to watch, and buying tips) plus four genuinely different state overlays.
  Western Australia is the flagship: it is the only state with enough apricots in stock to generate a
  live buy-apricot-trees page right now, it is home turf, and its dry south-west spring is actually a
  disease advantage for a fruit that hates humidity (the catch is the mild coastal winters give low
  chill, so the guide steers coastal gardeners to low-chill varieties and the cooler hills and inland
  to the richer heritage types). Queensland gets an honest overlay: apricot is really only a Granite
  Belt crop there, and harder than peaches or plums because there is no established low-chill apricot.
  New South Wales covers the cool Central West, the Hilltops around Young, and the irrigated Riverina.
  Victoria, which grows more apricots than any other state, covers the Goulburn Valley and Sunraysia,
  and notes that Queensland fruit fly is now established there (the Greater Sunraysia Pest Free Area
  was wound up in 2024), so even a backyard tree needs netting or baiting now.

### Verification
- Full test suite green (635 tests), including the per-state uniqueness and FAQ guards. The apricot
  pages build unique per state with no region names leaking across states, zero em or en dashes, FAQ
  JSON-LD, article Open Graph tags, and a Sources block limited to what each page cites. Every one of
  the 44 cited source URLs returns HTTP 200.
- Sources lead with Australian authorities (DPIRD WA, Business Queensland, the Queensland Department
  of Agriculture and Fisheries low-chill stonefruit kit, NSW Local Land Services) alongside
  Sustainable Gardening Australia, BeeAware, the Goulburn Murray Valley fruit fly project and named
  nurseries for the variety detail. There is no owned-archive "Further reading" this time, because
  the Rare Fruit Council and WANATCA archives carry no apricot article, so we left it out rather than
  padding it with off-topic links.

Next: the tail of the species-guide rollout priority list.
