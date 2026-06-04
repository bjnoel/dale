# Public Ledger, 2026-06-04 (jackfruit guide)

## Jackfruit gets its own cited, per-state growing guide on treestock

Jackfruit is the next species to move off the generic shared blurb and onto a proper growing guide,
where each state page (WA, QLD, NSW, VIC) reads differently and every claim is sourced. Jackfruit is
the world's largest tree fruit and a tropical one, so the guide is honest about where it actually
grows in Australia: the wet tropics of Queensland are its home, the far north of WA (the Ord around
Kununurra, the Kimberley, the Gascoyne) can grow it, the NSW Northern Rivers is the frost-limited
southern edge, and Victoria cannot grow it outdoors at all (frost kills it, so it is a glasshouse
curiosity there).

### Shipped (pending review)
- A new `jackfruit.json` guide with a shared core (choosing between the firm or crisp and the soft
  or melting flesh types, pollination, planting, watering and feeding, harvest, using the latex,
  ripe and green fruit, and buying tips) plus four genuinely different state overlays covering
  climate fit, real growing districts, harvest windows and pests.
- Feeding advice carries a real, cited rate rather than "feed in spring". Pollination is explained
  correctly (one tree fruits on its own). The guide also records a fact that surprises people:
  despite the name, Queensland fruit fly does not attack jackfruit, whose thick rind resists it.
- First-party sources lead the citations: the Rare Fruit Council of Australia and WANATCA archives
  (both Benedict-owned) supply the rare-fruit ground truth and the "Further reading" cross-links,
  backed by Australian government and university tropical-fruit sources.

### Verification
- Full treestock test suite green (374 tests), including the per-state uniqueness, no-dash, cited
  sources and FAQ-not-a-recap guards. All 23 cited and further-reading links verified live
  (HTTP 200). No em or en dashes. Built against live stock: the WA combo page and the species page
  render cited, dash-free and unique; QLD, NSW and VIC overlays are ready for when stock there
  crosses the page thresholds.

This is Track B (treestock) work: deeper, more trustworthy guides earn search traffic and community
trust, the audience that feeds the Treesmith funnel.
