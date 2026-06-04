# Public Ledger — 2026-06-04

## Growing guides reworked: FAQs that add something, feeding advice with real numbers

The per-species growing guides on treestock (olive, lychee, fig, peach, tamarillo, guava, mango and
plum) were good but had two weak spots Benedict pointed out. The FAQ at the bottom of each page
mostly repeated the body above it (the "do you need two trees?" answer appeared twice on nearly
every page), and the watering and feeding advice was generic ("feed in spring") with none of the
fertiliser detail a grower actually wants. This change fixes both across all eight guides and
updates the rollout template so future guides start from the higher bar.

### Shipped (pending review)
- Every FAQ now answers a question the body does not already cover. The repetitive
  pollination, harvest-timing and shipping recaps were replaced with questions a buyer actually
  asks: can I grow it in a pot, how big does it get and can I keep it small, how long until it
  fruits, how do I ripen it, how do I protect it from frost, which variety suits my district.
- The "Water and feeding" section now carries cited specifics where the evidence supports them:
  fertiliser type, NPK direction and ratio, application rate and timing, and soil pH. Examples:
  olive (about 4 kg of a 17:7:9 fertiliser a year), mango (a 15:4:11 complete fertiliser at
  30 to 60 g per young tree every six to eight weeks, plus the pre-flowering dry spell that triggers
  flowering), peach (the Queensland 12:5:14 program and the three critical watering windows), and
  guava (the University of Florida home-garden feeding schedule). Numbers are only stated where a
  recognised authority gives them; otherwise the advice stays specific but qualitative.
- A new automated test fails the build if any future guide's FAQ slips back into repeating the body,
  so the standard holds without manual policing.

### Verification
- Full test suite green (355 tests, including the new FAQ-overlap guard and a synthetic proof that
  it catches duplication). Newly cited sources verified live (HTTP 200), bar one Agriculture
  Victoria page that blocks automated checkers but is live in a browser and backed up by a second
  source. No em or en dashes; the rare-fruit archive citations stay first-party and followed.

This is Track B (treestock) work: better, more trustworthy guides earn search traffic and community
trust, which is the audience that feeds the Treesmith funnel.
