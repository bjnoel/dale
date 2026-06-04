# Public Ledger — 2026-06-04

## Finger lime growing guide: Australia's own rainforest citrus, built on the owned archives

treestock now has a proper, per-state growing guide for the finger lime (Citrus australasica, the
native "caviar lime"), continuing the species-guide rollout. It replaces the generic blurb on
/species/finger-lime.html and on the buy-finger-lime-trees-[state] pages with scannable, cited,
state-aware advice that is genuinely different in each state. Finger lime is a real rare-fruit
species with healthy stock (48 products across six nurseries), so all four state combo pages plus
the species page are live from current stock.

Finger lime is a good fit for the "archives first" approach, because as a native bushfood it is one
of the species Benedict's own archives cover best. The guide is built on the Rare Fruit Council of
Australia's "Edible Native Fruits, Wild Lime" article (which covers the rainforest limes and CSIRO's
native-lime breeding) and a WANATCA conference paper on native citrus, cross-checked against CSIRO,
AgriFutures, the Australian National Botanic Gardens, DPIRD Western Australia, Business Queensland,
Sustainable Gardening Australia and peer-reviewed research. Every cited and further-reading link
returns HTTP 200.

### Why each state reads differently
- New South Wales is the flagship: the finger lime's native home is the Big Scrub rainforest of the
  Northern Rivers around Lismore, Byron and the Tweed, which is about the easiest place in the country
  to grow one and where most of the named cultivars were first selected.
- Queensland is the co-heartland, sharing the border-ranges rainforest of the southeast (the Scenic
  Rim and the Gold Coast and Sunshine Coast hinterlands), with some of the country's longest-running
  commercial groves, such as the orchard at Bellthorpe.
- Western Australia is defined by citrus biosecurity. The guide explains, honestly, that citrus is
  tightly controlled at the WA border (so buying a WA-grown plant is the way to go), that a finger
  lime there does best with afternoon shade and steady water, and that citrus gall wasp, whose wild
  host is the finger lime, is now established across Perth.
- Victoria is at the cold limit, where a finger lime is mostly a pot-and-shelter crop, but the state
  has a special place in the story: CSIRO bred the modern native limes at Merbein, near Mildura.

### A few things the guide gets right that a generic blurb would not
- Finger lime fruit is a very poor host for Mediterranean fruit fly and a recorded non-host for
  Queensland fruit fly, so unlike most citrus the fruit is rarely stung. That is a real backyard
  advantage, and the guide says so rather than copying the usual "fruit fly stings citrus" warning.
- The finger lime is the native host of the citrus gall wasp, the pest that galls backyard lemons
  and oranges across the country, so the guide explains how to cut the galls out over winter.
- The CSIRO Blood Lime (sold as Red Centre Lime) is correctly described as an acid mandarin crossed
  with a red finger lime, and the Outback Lime as a Desert Lime selection rather than a finger lime.
- Buy a grafted plant: a seedling is slow and variable and can take many years to fruit, where a
  grafted, named selection fruits in two to three years and comes true to colour.

### Verification
- Full test suite green (627 tests), including the per-state uniqueness, no-dash, FAQ structured-data
  and FAQ-overlap guards, plus correctness guards specific to finger lime. The four combo pages and
  the species page were built against real nursery stock: unique per state, no region names leaking
  across states, zero em or en dashes, cited Sources, and a Further reading list of Benedict's owned
  Rare Fruit Council and WANATCA archives.
- The species page and all four state overlays are generating from current stock; finger lime is in
  stock across nurseries in every state.
