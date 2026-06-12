# Variety descriptions: mango tail (7 added, 29 skipped)

**Decided by:** Dale (parallel variety-descriptions run, branch dale/varieties-mango)
**Context:** Mango tail pass over the 36 live /variety slugs not yet described or skipped in
`variety_descriptions/mango.json` (pilot DEC-178 had seeded 78 varieties + 52 skips). Five
non-overlapping research subagents researched the remaining slugs against >=2 reputable sources
each (>=1 non-nursery), skipping anything thin or duplicate.
**Decision:** Added 7 verified blurbs and recorded 29 skips, leaving mango variety descriptions
at 85 described / 81 skipped, remaining 0.

Added: mango-rad (Thai green eating mango, GI-registered Rad Pad Riew), mango-springfels (1919
West Palm Beach Haden seedling), mango-cac (Vietnamese Xoai Cat group, lenticel-freckled),
mango-olour (Indian polyembryonic Alphonso rootstock), mango-sensations (1935 North Miami
Haden x Brooks, dark plum-red, late-season SA mainstay), mango-phoenix (2017 Zill Jakarta
seedling), mango-mangga-madu (Indonesian honey mango).

Skipped (thin/duplicate/noise): banana-callo, banana-ken, lime, batawi, cat-thom, harumanis-red,
rupee, carabao-filipino, choc-anon-miracle, strawberry-sensation, kasturi-green, spychala,
rubropetala, lashkars-khan, crimson-blush, senorita, cherry, bullock-s-heart, rock-saigon,
bundy-special, kamerunga-white, thong, ricks-bowen, royal-red, tree-sensation, ginger,
ataulfo-honey, lemon-meringue-ppk, kasturi-blue.

**Why:** Accuracy over coverage. Three subagent-drafted entries (banana-callo, batawi, cat-thom)
fell below the 0.80 confidence gate on blog/seller-only sourcing and were skipped. Bullock's
Heart was skipped on review because two of its four cited sources describe the custard apple
(Annona reticulata), not the mango, a conflation risk. Ataulfo-honey, choc-anon-miracle,
carabao-filipino, lemon-meringue-ppk, kasturi-blue/green are duplicate listings of already-covered
cultivars; ginger is Curcuma amada, not a Mangifera mango.
**Status:** Merged to mango.json; tests green; variety golden unchanged (fixture stock excludes
these tail slugs). Pending deploy at batch close-out.
**To revert:** Remove the 7 entries from `varieties` and the 29 slugs from `skipped` in
`tools/scrapers/variety_descriptions/mango.json`.
