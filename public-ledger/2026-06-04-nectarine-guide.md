# Public Ledger — 2026-06-04

## Nectarine growing guide: the smooth-skinned peach gets its own honest, cited guide

treestock now has a proper, per-state growing guide for nectarines, replacing the generic blurb on
/species/nectarine.html and on the buy-nectarine-trees-[state] pages with scannable, cited,
state-aware advice. All four states (Western Australia, Queensland, New South Wales and Victoria)
generate a page from current stock, plus the species page.

A nectarine is botanically a smooth-skinned peach, the same species grown the same way, so it would
have been easy to clone the peach guide. We did not, because the fuzz-free skin is a real difference
that changes how you grow the fruit, and a near-duplicate page helps nobody.

### What the guide gets right (each fact checked against an authority that returns a live page)
- A nectarine is a peach with a fuzz-free skin, caused by a single recessive gene. It is not a peach
  crossed with a plum, a surprisingly common myth that the guide clears up.
- Because the skin lacks the peach's protective fuzz, nectarines are more prone to brown rot and more
  susceptible to bacterial spot than peaches, and the bare skin shows thrips and wind marking more
  plainly. So the guide leans hard on the practical fixes: an open, airy tree, early fruit thinning,
  a dry sunny site, and clean, prompt picking.
- Real feeding and watering detail, not hand-waving: the three make-or-break soil-moisture windows
  (around flowering, the weeks before harvest, and midsummer for next year's wood) and a cited
  fertiliser rate from the Queensland low-chill stonefruit program.

### Two things the guide gets right that the older stone-fruit copy did not
- Western Australia is not "free of" Queensland fruit fly. It is a declared, prohibited pest that WA
  eradicates whenever it is detected. The guide says exactly that, so WA growers plan around
  Mediterranean fruit fly (the resident pest) without false reassurance.
- The guide does not repeat the claim that the Riverina is a major nectarine district. That has not
  been true since the cannery years, so the New South Wales page is anchored on the districts that
  still grow the fruit: Bilpin near Sydney, the cool Central Tablelands around Orange and Bathurst,
  and Batlow.

### Per-state, genuinely different
- Victoria is the flagship, because it grows about two thirds of Australia's nectarines, centred on
  the Goulburn Valley (Shepparton and Cobram) and the irrigated Sunraysia (Mildura and Swan Hill),
  where the dry inland air suits a nectarine's rot-prone skin.
- Western Australia leads with the cooler hills and southern districts that carry the winter chill,
  the warm Swan coastal plain for low-chill varieties, and the quarantine rules that decide which
  nurseries can post a tree here.
- Queensland splits the high-chill Granite Belt from the low-chill subtropics, and is honest that
  humidity makes a smooth nectarine harder to keep clean than a fuzzy peach.
- New South Wales runs from the low-chill coast to the cold tablelands, giving it one of the longest
  nectarine seasons in the country.

### Verification
- Full test suite green (635 tests), including the per-state uniqueness, FAQ-overlap and no-dash
  guards. The four combo pages and the species page build unique per state, with no region names
  leaking across states, zero em or en dashes, FAQ structured data, article social tags and a Sources
  list. Every one of the 22 cited sources was confirmed to return a live page (HTTP 200) with no
  reliance on Wikipedia, and the guide deliberately avoids two government sites that block automated
  checks, anchoring those facts on sources that resolve cleanly.

Shipped as a pull request, pending Benedict's review.
