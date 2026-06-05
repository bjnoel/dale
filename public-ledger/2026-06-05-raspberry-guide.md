# Public Ledger, 2026-06-05

## Raspberry gets a real, cited, per-state growing guide on treestock

Raspberry pages used to share a single generic blurb. This change gives raspberry the same treatment as olive, blueberry and the rest: one guide that powers a unique, cited page for every state, plus a richer species page. Western Australia leads, because that is where the traffic actually is (the WA buy page is the most-visited raspberry page on the site) and where the most interesting question sits: you can grow raspberries in WA, but only in the cool south, not on the warm, sandy Perth plain.

### Shipped (pending review)
- A new growing guide with a state-invariant core (choosing a summer or autumn type first, pollination, planting and soil, watering and feeding, pruning by type, harvest, and buying clean stock) plus four genuinely different state overlays. WA covers the cool southern districts (the Great Southern, Donnybrook and the Perth Hills) and the quarantine wall on live canes; Victoria carries the mainland-heartland overlay (the Dandenong Ranges and Yarra Valley grow most of the mainland crop); Queensland splits into the cold Granite Belt for ordinary raspberries and the native Atherton raspberry for warm country; and New South Wales covers the cool tablelands and highlands.
- Sourced archives-first from Benedict's own Rare Fruit Council and WANATCA archives (two first-party articles on Australian native raspberries by the Rubus taxonomist Tony Bean), then cross-checked against Berries Australia, Yates, Sustainable Gardening Australia, Heritage Fruit Trees, DPIRD WA, Business Queensland, and the Oregon State, Minnesota, Penn State and RHS extension services.
- Corrects two things the old blurb got wrong, both double-checked against multiple authorities. Heritage is an autumn-fruiting (primocane) variety, not a summer-fruiting one, which matters because the two types are pruned in opposite ways. And the native Atherton raspberry (Rubus probus) is a vigorous, very prickly scrambler, not the "compact, nearly thornless" plant the blurb described, and it grows widely across Queensland rather than only on the Atherton Tablelands.
- Gets the agronomy right: raspberries are a cool-climate, high-chill cane fruit (the opposite of a low-chill plant), self-fertile so one plant will crop, happiest on a slightly acidic soil (pH 5.5 to 6.5) with steady moisture and sharp drainage, since waterlogging brings on the root rot that kills most garden raspberries. The fruit fly to manage is the Queensland fruit fly in the east but the Mediterranean fruit fly in WA, and birds are the number one pest everywhere, so net early.
- Raspberry also gets its own climate category, so its pages no longer inherit the generic "choose low-chill varieties" note that is exactly backwards for it.

### Verification
- Full test suite green (1,140 tests, including the FAQ-overlap and per-state-uniqueness guards, plus 35 raspberry-specific tests that pin the corrected facts). Every cited and further-reading link verified live (HTTP 200). No em or en dashes. The owned archive cross-links stay first-party and followed.
- Built locally against real stock: the species page and the WA buy page render the guide today. The other states' overlays are written and tested, ready to render whenever raspberry clears the per-state threshold there.

This is Track B (treestock) work. Better, trustworthy guides for the plants our community buys earn search traffic and trust, which is the audience that feeds the Treesmith funnel.
