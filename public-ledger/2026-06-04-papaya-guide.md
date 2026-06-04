# Public Ledger — 2026-06-04

## Papaya growing guide (Queensland flagship)

Papaya is the next species to get a proper, cited, per-state growing guide on treestock, after
olive, lychee, fig, peach, tamarillo, guava, mango and plum. Papaya (also sold as pawpaw, the same
plant) is a strongly tropical crop, so Queensland is the flagship: far north Queensland grows about
85 per cent of the national crop, and over 90 per cent of that is in the north. Western Australia
gets a thorough second treatment because it is the only state that generates a papaya page from
current stock, and it has a genuine papaya story (the Kimberley and Gascoyne up north, plus the
Perth "heat sink" trick from the WANATCA archives). New South Wales is covered as papaya's cool
southern edge and Victoria as a greenhouse-only curiosity.

### Shipped (pending review)
- A new guide, `tools/scrapers/growing_guides/papaya.json`, with a shared core (papaya versus
  pawpaw and red versus yellow flesh; the male, female and bisexual sex types that decide whether a
  single plant will fruit; planting for the sharp drainage papaya needs to dodge root rot; water and
  feeding; harvest at colour break and the papain in green-fruit latex; buying tips) plus four
  genuinely distinct state overlays for WA, QLD, NSW and VIC.
- The variety advice is tied to what is actually for sale: Red Lady, RB4, Sunrise Solo, Yellow H13,
  Broad Leaf and Red Army all appear in the live stock table on the WA page.
- First-party archives come first. Further reading curates four Rare Fruit Council papaya articles
  and the WANATCA "Exotic fruits in Perth" conference paper as followed links, with one WA Rare
  Fruit Club page as a nofollow third-party link. The babaco articles that share the RFCA papaya
  folder (a different fruit) are deliberately kept out.
- A dedicated test file, `tests/test_guide_papaya.py`, holds the new guide to the same bar as the
  others and adds a check that the owned archive links stay followed while the third-party link
  stays nofollow.

### Verification
- Full test suite green (371 tests, including the FAQ-overlap guard that now also covers papaya).
- Every one of the 24 cited and further-reading links returns HTTP 200. The Queensland, Northern
  Territory, Western Australia, Florida and rare-fruit archive sources were each opened and checked
  against the claim they support. Two pages that block automated checkers (NSW and Victoria
  agriculture) were left uncited; their points are carried by sources that do resolve, the same way
  the mango guide handles it.
- No em or en dashes. Each state page reads differently, with its own regions, harvest timing and
  pests, and the region names do not bleed across state pages.

This is Track B (treestock) work. Accurate, trustworthy, first-party-cited guides earn search
traffic and community trust, which is the audience that feeds the Treesmith funnel.
