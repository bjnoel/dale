# Public Ledger — 2026-06-04

## Apple growing guide added to treestock, with the chill, pollination and biosecurity facts told straight

Apples are one of the most searched temperate fruits on treestock, and the buy-apple-trees pages for WA, QLD, NSW and Victoria all draw real interest, but until now they shared a generic blurb that glossed over the things that actually decide whether a backyard apple succeeds, and in one place was misleading. This change gives apple the same cited, per-state growing guide the other species have, and gets the details right.

### Shipped (pending review)
- A new, fully cited apple guide (35 sources) with a shared core (choosing a variety by winter chill, pollination and triploids, rootstocks and tree size, planting and soil, water and feeding, harvest and storage, and buying tips) plus a genuinely different overlay for each state.
- The advice is tied to reality. Varieties are matched to chill (low-chill Anna, Dorsett Golden and Tropic Sweet for warm and coastal gardens; mainstream Gala, Fuji, Jonathan, Granny Smith and the Delicious apples for cold winters; the West Australian-bred Cripps Pink, Cripps Red and Lady Williams as their own modest-chill but very-late group). The old blurb wrongly grouped Sundowner with Anna as a low-chill coastal apple; the guide corrects that. Pollination is explained honestly, including the warning that triploid varieties such as Gravenstein, Jonagold and Mutsu cannot pollinate and need two other varieties.
- Each state gets its own story. Western Australia leads, as the home of Pink Lady (bred by John Cripps at the WA Department of Agriculture) and, remarkably, one of the last apple-growing regions on earth still free of codling moth, kept out by quarantine. Victoria is Australia's biggest producer (about 43 per cent of the crop) and the home of the Tatura Trellis. New South Wales is the birthplace of the Granny Smith, found at Ryde in 1868. Queensland's apples come almost entirely from the high, cold Granite Belt, with only low-chill varieties possible nearer the coast.
- The biosecurity facts are correct: codling moth is absent from WA but present in the eastern states, the fruit fly to manage is the Mediterranean fruit fly in WA and the Queensland fruit fly in the east, and Australia as a whole is free of fire blight.
- Further reading links to Benedict's own WANATCA archive (the Granny Smith and Tatura Trellis yearbook article), keeping authority in network.

### Verification
- Full test suite green (535 tests), including a new 20-test apple file and the shared guard that fails the build if any FAQ just repeats a body section. Each state page is unique with no region names leaking across states, there are no em or en dashes, and all 35 cited and further-reading links were checked live and return HTTP 200. The one affected golden page was regenerated and the diff reviewed.

This is Track B (treestock) work: an accurate, trustworthy apple guide earns search traffic and community trust, the audience that feeds the Treesmith funnel.
