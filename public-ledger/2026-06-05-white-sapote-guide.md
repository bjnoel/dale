# Public ledger entry, 2026-06-05: White sapote growing guide

Shipped a comprehensive, cited, per-state growing guide for **white sapote** (Casimiroa edulis)
on treestock.com.au, matching the olive gold standard. One JSON file
(`growing_guides/white-sapote.json`) gives the species page and the buy-white-sapote-trees-by-state
pages a unique, evidence-backed body in place of the old generic blurb.

**Flagship QLD** (Queensland did the foundational Australian research on white sapote: A.P. George
and the cultivar trials at the Maroochy Horticultural Research Station near Nambour), with **WA** and
**NSW** as standout overlays. WA's Mediterranean climate suits the fruit about as well as anywhere in
the country, and NSW has grown it in the Sydney basin for generations.

What makes it accurate, and not just a rewrite:
- **Correct WA quarantine:** white sapote is a citrus relative (Rutaceae), so WA's strict rules on
  importing the citrus family are why most eastern nurseries cannot ship trees there. That replaces
  the old "no quarantine restrictions apply" claim, which was wrong.
- **Honest pollination advice:** a single tree sets some fruit, but several popular cultivars are
  functionally female (little pollen) and crop far better with a pollinator, while a few (Suebelle,
  Ortego, Vernon) are reliably self-fruitful for a one-tree backyard.
- **The real climate story:** it is one of the more cold-hardy subtropical fruits (takes light frost)
  yet dislikes the humid lowland tropics, so it has its own climate category rather than the generic
  subtropical note that gets this wrong.
- **A safety note growers ask about:** the flesh is delicious and safe, but the seeds are toxic.

Archives-first sourcing (owned RFCA and WANATCA, then the California Rare Fruit Growers fruit facts,
Useful Tropical Plants, World Agroforestry, Daleys, DPIRD WA and Business Queensland). All 15 cited and
further-reading URLs resolve. Full test suite green (1142 tests, including 37 new white sapote guards).
With current stock only the species page renders live; the four state pages light up as stock grows.
PR open for review.
