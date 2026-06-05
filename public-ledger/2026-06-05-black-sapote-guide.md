# Public Ledger, 2026-06-05

## Black sapote growing guide: the chocolate pudding fruit, researched from the archives up

treestock now has a proper, per-state growing guide for black sapote, the tropical persimmon better
known as the chocolate pudding fruit. Like the others, it replaces the generic blurb on
/species/black-sapote.html and on the buy-black-sapote-trees-[state] pages with scannable, cited,
state-aware advice.

What makes this one accurate is that it is built on Benedict's own sources first: the Rare Fruit
Council of Australia archives (the fact sheet, the flower-biology article, and the drier-culture
"chocolate pudding fruit" piece) and two WANATCA conference papers from 2001, Roger Meyer's "Fruits
Called Sapotes" and Neville Passmore's "Exotic Fruits in Perth", the second of which records black
sapote being grown and tasted around Carnarvon and Perth. Those owned sources are backed up by the
City of Darwin's community-orchard sheet, Plant Health Australia, the Morton reference and the WA
agriculture department, so the facts line up across several authorities. The variety advice is tied to
the cultivars actually sold here: Maher, Bernecker, Mossman, Superb, Ricks Late and Colossal.

### Things the guide gets right that the generic copy did not
- Seedless fruit is not automatic, and it is not simply "self-fertile". Some prized selections carry
  female-only flowers and set seedless fruit only when they are grown away from any other black
  sapote. Put a pollinator nearby and the same tree sets a bigger crop, but with seeds. The guide
  spells out that trade-off so a grower can choose seedlessness or sheer quantity on purpose.
- It is a persimmon, with a persimmon's sting. An unripe black sapote is not just disappointing but
  astringent, caustic and an irritant, so the guide insists you wait until the fruit is completely
  soft, and it explains the calyx test for knowing when to pick (the green cap on top lifts away from
  the fruit) and why you never let it ripen on the tree.
- The kindness trap. A black sapote that is heavily fed and watered runs to leaf and bears shyly; the
  heaviest croppers are the leaner, drier, half-neglected trees. The guide passes on that
  hard-won growers' lesson, straight from the Rare Fruit Council archives.
- No false fruit-fly warning. It would be easy to copy the standard tropical-fruit pest advice across,
  but black sapote is not a listed Queensland fruit fly host, so the Queensland page says so rather
  than giving a warning that does not apply.

### Shipped (pending review)
- One state-invariant core (choosing a variety, the seedless-or-seeded question, planting and soil,
  water and the shy-bearer trap, the calyx harvest test, eating and the unripe warning, and buying
  tips) plus four genuinely different state overlays. Queensland is the flagship, since the wet
  tropical coast behind Cairns (Innisfail, the Atherton Tableland, Mareeba) and the Mackay country are
  the heart of Australian black sapote growing, with the tree also fruiting down into the subtropical
  south-east. New South Wales gets the Northern Rivers story (where several of the best Australian
  cultivars were bred), Western Australia an honest overlay (the tropical north around Kununurra,
  Broome and Carnarvon, while Perth is a sheltered-microclimate gamble), and Victoria a
  glasshouse-curiosity overlay.

### Verification
- Full test suite green (822 tests), including the per-state uniqueness and FAQ guards plus
  black-sapote-specific checks for the pollination nuance, the persimmon astringency warning, the
  calyx harvest test, the not-a-fruit-fly-host fact, and the stocked-cultivar names. The pages build
  unique per state with no region names leaking across states, zero em or en dashes, FAQ structured
  data, cited Sources, and a Further reading list that leads with the Rare Fruit Council archives and
  the WANATCA papers. Every cited and further-reading link returns HTTP 200.
- The species page is the live deliverable; the Queensland, NSW, Victoria and WA combo overlays switch
  on automatically once black sapote stock crosses the in-stock threshold in those states (all four
  overlays were verified by building them against real nursery stock).
