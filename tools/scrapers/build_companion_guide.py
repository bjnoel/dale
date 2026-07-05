#!/usr/bin/env python3
"""
Build companion planting guide page for treestock.com.au.

Targets keywords: 'companion plants for citrus', 'companion planting mango',
'fruit tree pollinator requirements', 'what to plant with avocado', etc.

Every companion/avoidance claim carries an evidence grade (see EVIDENCE_GRADES)
so the page is honest about what is research-backed versus traditional folklore.
Content is Australia-specific (pests, climate zones, cultivars) and cited.

Usage:
    python3 build_companion_guide.py /path/to/output/
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from stocklib.templates import render as render_template
from treestock_layout import render_head, render_header, render_breadcrumb, render_footer

from stocklib.evidence import EVIDENCE_GRADES, GRADE_BADGE, grade_badge
from stocklib.taxonomy import enabled_species


# ----- Content Data -----
# good:  (name, description, evidence_grade)
# avoid: (name, evidence_grade)
# Researched and adversarially verified for Australian conditions; see git log.

SPECIES_COMPANIONS = [
    {
        "name": 'Citrus (Lemon, Orange, Mandarin, Lime)',
        "slug": 'citrus',
        "species_slugs": ['lemon', 'orange', 'mandarin', 'lime', 'grapefruit', 'pomelo', 'finger-lime'],
        "icon": '🍋',
        "intro": 'Citrus grows across most of Australia, from Mediterranean WA and SA to subtropical Queensland, but no companion plant will protect it from the pests that actually cost growers fruit (citrus gall wasp, Queensland fruit fly and Mediterranean fruit fly). The honest value of companions here is soil building, attracting bees and hosting beneficial insects, not pest control.',
        "good": [
            ('Lavender', 'A reliable bee and beneficial-insect magnet that wants the same dry, sunny, well-drained spot as citrus, so it pairs naturally in Mediterranean and warm-temperate gardens (WA, SA, inland Victoria), though it tends to rot in humid subtropical and tropical coastal areas.', 'established-practice'),
            ('Borage', 'An easy-from-seed flower that strongly draws bees and beneficial insects; grow it for the pollinators, not for the folklore claim that it improves citrus flavour, and pull most plants before they self-seed across the garden.', 'established-practice'),
            ('Comfrey (Bocking 14)', 'Useful as a soil-builder for its biomass, not the debunked deep-root mining idea: chop its leaves several times a year for a potassium-rich mulch or liquid feed, and plant the sterile Bocking 14 strain about 1m out so it neither competes at the trunk nor seeds into a weed.', 'established-practice'),
            ('White clover (as groundcover, kept off the trunk)', 'A low living mulch that fixes some nitrogen and protects the orchard floor, but keep it clear of the shallow feeder roots at the trunk and treat it as a bonus, not a substitute for feeding hungry citrus.', 'context-dependent'),
            ('Nasturtium', 'Better understood as a possible trap crop than a repellent: plant it a metre or two away so aphids drawn to it do not simply move onto the tree, accept that the effect is inconsistent, and note it dies back in frosty temperate winters but self-sows as groundcover in warm and Mediterranean gardens.', 'traditional'),
            ('Marigold (French/African)', 'Despite real science behind alpha-terthienyl suppressing root-knot nematodes, a few plants scattered at the drip line do not work (University of Florida is blunt on this) and marigolds even host some other nematode types, so near citrus they are mainly decorative with a minor pollinator bonus in flower.', 'research-backed'),
        ],
        "avoid": [
            ('Fennel (especially wild fennel)', 'traditional'),
            ('Other large citrus trees too close (root and canopy competition)', 'established-practice'),
            ('Grass or lawn growing up to the trunk', 'research-backed'),
        ],
        "pollinator": 'Most citrus is self-fertile, so a single lemon, orange, grapefruit or lime tree will crop on its own (Australian nurseries such as Daleys list Eureka lemon as self-pollinating, one tree). Mandarins and tangelos are the exception worth planning for: many hybrids, including Minneola, Orlando, Nova, Robinson, Sunburst and Page, are self-incompatible and set a poor crop unless a second, different variety is nearby, and bees are needed to move the heavy, sticky pollen. The catch for anyone chasing seedless mandarins like Imperial or Afourer (Murcott) is that the same cross-pollination that lifts fruit set also raises seed count, so an isolated tree gives fewer seeds but a lighter crop.',
        "notes": 'Citrus are shallow-rooted, hungry feeders (feeder roots sit in roughly the top 30cm to 45cm), so keep a mulched, grass-free circle out to the drip line; trials on trees show grass competition cuts growth while mulch lifts it, and this matters most through dry Mediterranean and inland summers. Pull mulch back a hand-width from the trunk to prevent collar rot. They want free-draining, slightly acidic soil (around pH 6 to 6.5), so in heavy clay or high-rainfall coastal gardens plant on a mound or raised bed. None of the companions here control the real pests: prune out citrus gall wasp galls before adults emerge in spring (about September to November), destroy the prunings, ease off high-nitrogen feeding in late winter, and net or bait against Queensland fruit fly (eastern states) and Mediterranean fruit fly (WA).',
        "sources": [
            ('Citrus gall wasp (DPIRD Western Australia)', 'https://www.dpird.wa.gov.au/businesses/pests-weeds-and-diseases/animal-pests-diseases/pest-insects/citrus-gall-wasp/'),
            ('How to prevent and treat bugs and citrus gall wasp (ABC Organic Gardener Magazine Australia)', 'https://www.organicgardener.com.au/blogs/how-prevent-and-treat-bugs-and-citrus-gall-wasp'),
            ('Pollination of Citrus Hybrids (University of Florida IFAS Extension, CH082)', 'https://ask.ifas.ufl.edu/publication/CH082'),
            ('Organic Mulch and Grass Competition Influence Tree Root Development (Arboriculture and Urban Forestry)', 'https://auf.isa-arbor.com/content/14/8/200'),
        ],
    },
    {
        "name": 'Mango',
        "slug": 'mango',
        "species_slugs": ['mango'],
        "icon": '🥭',
        "intro": 'Mango (Mangifera indica) is a large tropical and subtropical tree, reliable in far north Queensland, the Northern Territory, southeast Queensland and northern New South Wales, and fruiting only in the warmest microclimates in Mediterranean Perth and warm-temperate southern areas. Honest companion planting for mango is mostly about living mulch, soil cover and pollinator habitat, not pest repellence, so most useful pairings sit at or just inside the drip line rather than against the trunk.',
        "good": [
            ('Vetiver grass (sterile Monto cultivar)', 'On a sloping site, vetiver hedges are a genuinely proven soil holder; Queensland research treats the deep roots as soil reinforcement, so plant the sterile Monto cultivar (no viable seed, no runners) on the contour above or below the mango. This is erosion control, not a pest or yield effect on the tree.', 'research-backed'),
            ('French marigold (Tagetes patula), as a pre-plant cover crop', 'Marigolds suppress root-knot nematodes, but only as a dense cover crop grown in the same soil for at least two months before planting, not scattered under an established tree. Use a Tagetes patula green manure in a bed before planting a young mango; interplanting around a mature tree will not protect its deep roots.', 'research-backed'),
            ('Turmeric (Curcuma longa)', 'A useful warm-season living groundcover under an established mango in tropical and subtropical gardens, shading out weeds and feeding soil life. It dies back over winter (the rhizome can survive in milder areas, including sheltered Perth gardens, if soil is well drained or you lift it), so treat it as seasonal cover, not pest control.', 'established-practice'),
            ('Sweet potato (Ipomoea batatas)', 'A fast, edible summer living mulch that shades soil and smothers weeds around an established mango, a weed-suppression effect that holds up in trials. It is frost tender and dies back in cooler southern gardens, so keep runners off the trunk and away from young trees so it does not compete for water.', 'established-practice'),
            ('Papaya (pawpaw), as a temporary nurse only', 'Sometimes used as a quick nurse plant to give a young mango light shade and biomass while it settles, but mangoes fruit best in full sun, so remove it as the tree grows. Papaya is frost tender and a known host of root-knot nematode, so do not plant it permanently hard against the mango.', 'traditional'),
            ('Lemongrass (Cymbopogon)', 'A tidy, non-invasive clumping perennial that adds biodiversity at the garden edge, but do not rely on it to repel pests; its oils only deter insects when leaves are crushed, and a growing clump gives off too little to protect a mango from fruit fly.', 'traditional'),
        ],
        "avoid": [
            ('Avocado (spacing and disease isolation, not chemistry)', 'context-dependent'),
            ('Other large trees within about 8m of a standard mango', 'established-practice'),
            ('Lawn grass up to the trunk and within the drip line', 'established-practice'),
            ('Basil (does not repel fruit fly and can attract it)', 'research-backed'),
        ],
        "pollinator": 'A single tree is usually enough. Yates states mangoes are self-pollinating, and Kensington Pride (the Bowen mango, the dominant Australian home and commercial variety, self-fertile and polyembryonic) needs no partner, though a nearby second variety such as R2E2, Calypso or Honey Gold can nudge fruit set up slightly. You do not need to buy a second tree. Both flies and bees do the pollinating (Yates notes flies are particularly effective, and in Northern Territory orchards native stingless bees are major contributors), and insect-pollinated flowers set far more fruit than excluded ones. The best move is a diversity of flowering plants nearby to draw in small pollinators.',
        "notes": 'The biggest backyard pest threat is fruit fly, and no companion plant controls it. Queensland fruit fly (Bactrocera tryoni) responds to cuelure, and Mediterranean fruit fly (now endemic right across WA from Esperance to Carnarvon, with mango a high-susceptibility host per DPIRD) responds to protein bait; neither is fooled by basil. Control with exclusion netting, protein baiting, lure traps and prompt removal of fallen fruit. In humid eastern Australia the main disease is anthracnose, which is worse in still, crowded conditions, so airflow and the grass-free, mulched zone out to the drip line matter.',
        "sources": [
            ('How to Grow a Mango Tree in Australia - Yates', 'https://www.yates.com.au/how-to-grow/mango/'),
            ('Companion Planting - Sustainable Gardening Australia', 'https://www.sgaonline.org.au/companion-planting/'),
            ('Mediterranean fruit fly - DPIRD Western Australia', 'https://www.dpird.wa.gov.au/businesses/pests-weeds-and-diseases/animal-pests-diseases/pest-insects/mediterranean-fruit-fly/'),
            ('Response of some mango-infesting fruit flies to aqueous solutions of the basil plant Ocimum tenuiflorum L. - Frontiers in Horticulture', 'https://www.frontiersin.org/journals/horticulture/articles/10.3389/fhort.2023.1139525/full'),
        ],
    },
    {
        "name": 'Avocado',
        "slug": 'avocado',
        "species_slugs": ['avocado'],
        "icon": '🥑',
        "intro": 'Avocado is a shallow, surface-rooted tree that, across Australia, lives or dies by drainage and Phytophthora root rot rather than by what you interplant. Most avocado companion pairings are folklore, so the honest wins are clearing grass, mulching well, sheltering young trees, and feeding pollinators, not planting a "helper" species.',
        "good": [
            ('Coarse organic mulch (woodchip, sugarcane, lucerne)', 'Not a plant companion as such, but the single best thing under an avocado in Australia: a thick, open mulch out to the dripline (kept off the trunk) feeds the surface roots and builds soil microbes that suppress Phytophthora.', 'research-backed'),
            ('Legume groundcover (pinto peanut, white clover)', 'A low legume cover is a recommended slow soil-builder under subtropical avocados, adding nitrogen gently as it breaks down rather than as a concentrated hit; an Australian trial measured pinto peanut fixing close to 150 kg N per hectare.', 'context-dependent'),
            ('Flowering herbs (basil, chives, parsley)', 'Pleasant and harmless at the sunny edge of the canopy, and when allowed to flower they feed the hoverflies and bees that help avocado pollination; just do not expect them to repel pests, and no herb repels fruit fly.', 'traditional'),
            ('Banana (subtropical, temporary nurse only)', 'A traditional northern NSW and SE Queensland trick for sheltering a young avocado from wind and sun, but bananas are thirsty and competitive, so site them a few metres away, keep water off the avocado collar, and remove them once the tree is established.', 'traditional'),
            ('Passionfruit (on its own fence or trellis)', 'Fine as a separate vertical crop rather than a true helper: on its own support it competes little for root space, but keep it off a young avocado because it is vigorous enough to smother the canopy.', 'traditional'),
            ('Comfrey (chop-and-drop, away from the trunk)', 'Useful as cut leaves laid as mulch or brewed into a potassium-rich liquid feed, not as a living nutrient pump (the deep-taproot accumulator story is largely unproven); keep crowns clear of the trunk so they do not hold moisture against the collar.', 'traditional'),
        ],
        "avoid": [
            ('Lawn and grass under the canopy', 'established-practice'),
            ('Concentrated nitrogen sources or a large vigorous nitrogen-fixing tree', 'context-dependent'),
            ('Fennel close to young trees (competition, and a weed in parts of Australia)', 'traditional'),
            ('Black walnut (juglone; barely grown in Australia, avocado not a listed sensitive plant)', 'traditional'),
        ],
        "pollinator": 'Avocados have A-type and B-type flowering, where the female and male phases open at opposite times of day. Type A includes Hass, Reed, Pinkerton and Wurtz (Little Cado); Type B includes Fuerte, Bacon, Sharwill and Shepard. Pairing an A with a B (for example Hass with Fuerte or Bacon) can lift fruit set, most usefully in cooler spring weather. But Australian field research found a single Hass self-pollinates a good crop (about 52 percent of fruit overall), with self and cross fruit the same size and quality (cross-pollinated fruit had roughly 10 percent more calcium), so a second variety boosts yield rather than being essential for a backyard tree. Bees are the main pollinators (commonly 5 to 8 hives per hectare in orchards) and hoverflies are present in Australian orchards (though their value here has not been measured), so keep flowers nearby. Compact A-types like Wurtz (Little Cado) suit small gardens.',
        "notes": "Phytophthora root rot (Phytophthora cinnamomi) is avocado's worst enemy in Australia and the most important point on this page. Plant on a mound in free-draining soil, water carefully (never waterlogged), and use a thick coarse organic mulch kept well clear of the trunk, since the mulch builds soil microbes that suppress the disease. Choose a Phytophthora-tolerant rootstock (Velvick is common in Australia, and clonal Dusa also performs well), add gypsum under the canopy, and buy certified disease-free trees. The same pathogen causes dieback in WA bushland, so never move soil from infected sites.",
        "sources": [
            ('Business Queensland (QLD DAF): Phytophthora root rot (integrated management, mulch off trunk, gypsum, drainage, tolerant rootstocks)', 'https://www.business.qld.gov.au/industries/farms-fishing-forestry/agriculture/biosecurity/plants/diseases/horticultural/phytophthora-root-rot'),
            ('BeeAware Australia: Avocados - Pollination (Type A/B flowering, both types planted together, honey bees, hive density, hoverflies)', 'https://beeaware.org.au/pollination/pollinator-reliant-crops/avocados/'),
            ('Avocados Australia: Hass self-pollination field study (52 percent self-pollinated, no significant fruit-quality difference)', 'https://avocado.org.au/public-articles/ta32v1pollination/'),
            ('UC ANR Ventura: FAQ about Avocados (shallow surface roots in top 8 inches, mulch versus grass, keep mulch off trunk)', 'https://ucanr.edu/sites/ucceventura/Gardening/Garden_Info/avocado_questions/'),
        ],
    },
    {
        "name": 'Fig',
        "slug": 'fig',
        "species_slugs": ['fig'],
        "icon": '🌳',
        "intro": 'Common figs grown in Australia (Black Genoa, Brown Turkey, White Adriatic, White Genoa, Preston Prolific) are self-fertile and need no pollinator, so most fig "companion" pairings are about the orchard floor rather than fruit set. Be honest about the evidence: the real fig problems here are fruit fly, blister mite, rust, birds and possums, and no companion plant controls any of them, so plant companions for soil, mulch and beneficial insects, not pest protection.',
        "good": [
            ('French marigold (Tagetes patula), as a pre-plant cover crop', 'The one companion claim with hard science behind it: French marigold roots release alpha-terthienyl that suppresses root-knot nematode (a genuine fig pest in warm, sandy Australian soils), but only when grown as a dense block (plants under about 18cm apart) over the planting site for roughly two months before you plant the fig, not as a few scattered plants, and note it can raise some other nematode species and attracts thrips and spider mites.', 'research-backed'),
            ('Comfrey (sterile Russian comfrey, Bocking 14)', 'A sound chop-and-drop mulch and potassium cycler (a Cornell field trial confirmed it accumulates potassium), but it concentrates nutrients already in your soil rather than adding them, and the deep-mining folklore is overstated, so use the sterile cultivar (so it does not seed) and treat it as mulch and moisture retention, not fertiliser.', 'established-practice'),
            ('Flowering insectary plants (yarrow, sweet alyssum, carrots or parsnips left to bloom)', 'Diverse flowering plantings reliably feed and retain bees and predatory and parasitoid insects, the one pest-related angle the strongest skeptics endorse, so frame these as feeding beneficials and pollinators rather than repelling fig pests (the fig itself needs no pollinator).', 'established-practice'),
            ('Living groundcover or mulch layer', 'A groundcover and mulch layer conserves soil moisture through hot Australian summers and suppresses weeds, just keep it from being over-irrigated because figs dislike wet feet.', 'established-practice'),
            ('Aromatic Mediterranean herbs (rosemary, thyme, oregano, sage)', "They share the fig's love of full sun and free-draining soil and flower for bees, but their pest-repellent reputation is folklore (controlled work found aromatic herbs had little effect on pest insect behaviour), so grow them for groundcover and bloom, not to protect the fig.", 'traditional'),
            ('Strawberry (woodland or alpine, Fragaria vesca)', 'Works as a living mulch under a fig in cooler and subtropical gardens, but expect groundcover and a light pick rather than a heavy crop because strawberries fruit best in full sun, and in fruit fly areas the berries need the same netting or bagging as the figs.', 'context-dependent'),
        ],
        "avoid": [
            ('Fennel (Foeniculum vulgare)', 'context-dependent'),
            ('Thirsty fruit-fly and nematode-host veg at the trunk (tomatoes and other nightshades, cucurbits)', 'established-practice'),
            ('Other large trees within 4 to 5m', 'established-practice'),
            ('Rue (Ruta graveolens)', 'traditional'),
        ],
        "pollinator": 'No pollinator partner is needed. The common Australian fig cultivars (Black Genoa, Brown Turkey, White Adriatic, White Genoa, Preston Prolific) are parthenocarpic and self-fertile, so a single tree sets fruit on its own. Only Smyrna and San Pedro type figs need the fig wasp (Blastophaga psenes), and that wasp is not established in mainland Australian fruit-growing areas, which is why those types are not grown as backyard figs here. Bees do not pollinate the common fig, so no bee-attracting companion is required for fruit set.',
        "notes": 'Figs have vigorous, moisture-seeking roots that Australian arborists rank among the worst for lifting paving and invading sewer and stormwater pipes, so keep a full-size tree well clear of pipes and foundations, or grow it in a large pot or raised bed in a small yard; a vertical root barrier about a metre out (plastic or pavers buried on edge) helps direct roots downward. Ignore the very large "plant 15 to 25m away" figures online, those are for giant ornamental figs like the Moreton Bay, not a backyard eating fig. Figs also dislike wet feet and are best on a mound or raised bed for drainage, and they are not heavy nitrogen feeders, so do not push nitrogen-fixing legumes as "feeders".',
        "sources": [
            ('Sustainable Gardening Australia: Grow and prune fig trees (self-fertile cultivars; root-knot nematode, blister mite, rust, anthracnose)', 'https://www.sgaonline.org.au/figs/'),
            ('Green Harvest: Fruit Fly Organic Control Information (exclusion, traps, baits, hygiene; no repellent companion plant listed)', 'https://greenharvest.com.au/blogs/pests-and-plant-diseases/fruit-fly-organic-control-information'),
            ('UF/IFAS EDIS NG045: Marigolds (Tagetes spp.) for Nematode Management (interplanting ineffective; dense stand under 7in; 2 months pre-plant; increases some other nematodes)', 'https://ask.ifas.ufl.edu/publication/NG045'),
            ('Weeds Australia: Fennel (Foeniculum vulgare) profile (declared/environmental weed; forms dense stands excluding other vegetation)', 'https://weeds.org.au/profiles/fennel-anise-aniseed/'),
        ],
    },
    {
        "name": 'Stone Fruit (Peach, Plum, Apricot, Nectarine, Cherry)',
        "slug": 'stone-fruit',
        "species_slugs": ['peach', 'nectarine', 'apricot', 'plum', 'cherry'],
        "icon": '🍑',
        "intro": 'In Australia the pests that actually ruin stone fruit are fruit flies (Queensland fruit fly in the eastern states, Mediterranean fruit fly in WA), and no companion plant stops them, so treat companions as a way to feed pollinators and beneficial insects, not as crop protection. The one companion-planting idea with real evidence behind it, accepted even by researchers who debunk most pairings, is that diverse nectar-rich flowers attract predators and parasitoids, so that is what this list is built around.',
        "good": [
            ('Yarrow', 'Open, accessible flowers feed hoverflies (whose larvae eat aphids), lacewings, ladybirds and parasitic wasps, and it is drought-hardy so it suits hot dry gardens like Perth and much of SA; note it helps with aphids and soft pests, not fruit fly.', 'established-practice'),
            ('Borage', 'A genuine heavy nectar producer that pulls in honeybees, native bees and hoverflies, though as a warm-season annual it flowers spring into summer and is usually not in bloom during the late-winter to early-spring stone fruit blossom, so grow it for whole-garden pollinator support rather than for fruit set.', 'established-practice'),
            ('Alyssum and calendula (winter-flowering insectary plants)', 'Useful for the early blossom window because they flower through the cool season when summer annuals are not up yet, feeding the bees and beneficials active around mid-August when apricots and peaches open in southern Australia.', 'established-practice'),
            ('Comfrey (sterile Russian, Bocking 14)', 'A chop-and-drop mulch around the drip line whose leaves genuinely test high in potassium, but understand it concentrates potassium already in your soil into leaf litter rather than creating fertility (the deep-root mineral-mining idea is mostly a myth), and use only the sterile Bocking 14 strain so it does not self-seed into a weed.', 'established-practice'),
            ('Garlic and chives', "Field trials in vegetable crops show Allium plants lower aphid numbers on their neighbours by masking the plant's scent with sulfur compounds, so a ring may reduce aphids (including green peach aphid) on young trees, but treat it as plausible rather than proven for orchards and do not expect it to stop borers.", 'context-dependent'),
            ('Marigolds (French or African, as a pre-plant cover crop)', 'The one nematode claim with science behind it, but only when grown as a dense block for a full season on the bare ground before you plant, not dotted under an established tree; genuinely useful for siting a new tree in warm sandy soils around Perth or the subtropics where root-knot nematode is a problem.', 'research-backed'),
        ],
        "avoid": [
            ('Tomatoes, potatoes, capsicum, strawberries and melons (and do not replant where they grew recently)', 'research-backed'),
            ('Grass growing over the root zone, especially while the tree is young', 'research-backed'),
            ('Tansy (toxic and an invasive weed, not a fruit fly repellent)', 'traditional'),
            ('Fennel (self-seeding weed that competes in the understorey)', 'context-dependent'),
        ],
        "pollinator": 'Most peaches and nectarines fruit on their own, and apricots are mostly self-fertile (a second variety can still lift the crop). Japanese plums (Santa Rosa is partially self-fertile, Mariposa and Satsuma) usually need a compatible Japanese-plum partner, and Japanese and European plums do not pollinate each other. Sweet cherries generally need two compatible varieties, though self-fertile types like Stella, Lapins and Sunburst exist (and even those crop better with company, while S-allele incompatibility groups can block a cross between two sweet cherries). Always check the specific cultivar and pick a polliniser that flowers at the same time. Stone fruit, apricots especially, blossom early (around mid-August in southern Australia) in cold, wet weather when honeybees barely fly, so support native bees such as blue-banded bees that forage in cooler conditions, and plant winter-flowering nectar plants rather than relying on summer annuals.',
        "notes": "Keep a mulched, grass-free circle out to the drip line while the tree establishes. Grass out-competes young trees for water and nitrogen in the topsoil and trials show turf to the trunk slows growth and delays cropping, with extra nitrogen failing to fix it, and the mulch also holds moisture, which matters most in Australia's drier and Mediterranean regions. Just mow any grass between the rows.",
        "sources": [
            ('Summerfruit: Pollination (BeeAware, Australia)', 'https://beeaware.org.au/pollination/pollinator-reliant-crops/summerfruit/'),
            ('Verticillium wilt of deciduous fruit trees (Agriculture Victoria)', 'https://agriculture.vic.gov.au/biosecurity/plant-diseases/fruit-and-nut-diseases/stone-fruits/verticillium-wilt-of-deciduous-fruit-trees'),
            ('Pollination (Heritage Fruit Trees, Australia)', 'https://www.heritagefruittrees.com.au/pollination/'),
            ('Marigolds (Tagetes spp.) for Nematode Management (University of Florida IFAS, NG045)', 'https://edis.ifas.ufl.edu/publication/NG045'),
        ],
    },
    {
        "name": 'Apple and Pear',
        "slug": 'apple-pear',
        "species_slugs": ['apple', 'pear'],
        "icon": '🍏',
        "intro": 'In Australia, the two things that actually decide whether you get clean apples and pears are matching the variety\'s winter chill to your district and managing fruit fly, not companion plants. Most companion pairings below are traditional folklore that is harmless to try; the genuinely useful "companions" are plants that feed pollinators and natural enemies, which is the part of companion planting the evidence supports.',
        "good": [
            ('Clover groundcover (white or subterranean)', 'A legume understorey that fixes nitrogen, suppresses weeds, holds moisture and feeds bees when flowering; the nitrogen boost is modest and slow, so treat it as a supplement, and keep a bare, mulched ring at the trunk to avoid collar rot and bark-chewing rabbits.', 'established-practice'),
            ('Phacelia (Phacelia tanacetifolia)', "One of the best nectar plants for honey bees and a magnet for aphid-eating hoverflies; Yates lists it for bee-friendly Australian gardens, so time its bloom to overlap your trees' flowering since there are no bumblebees on the mainland.", 'established-practice'),
            ('Flowering diversity (alyssum, umbellifers, native flowers)', "A mix of small flowers feeds the parasitoid wasps, hoverflies, ladybirds and lacewings that keep woolly apple aphid, mites and light brown apple moth in check; this beneficial-insect habitat is the defensible half of companion planting, far more reliable than any single 'pest-repelling' herb.", 'established-practice'),
            ('Nasturtium (as a living mulch and aphid trap)', 'Draws certain aphids off nearby plants and feeds bees and hoverflies as a low-competition groundcover; the evidence is thin (the same plant is sold as both an aphid repellent and a trap), and the popular claim that it repels codling moth is folklore since the larvae bore straight into the fruit. Self-seeds readily in frost-free gardens.', 'traditional'),
            ('Chives and garlic', 'Often claimed to deter apple scab and codling moth, but Australian authorities manage scab with resistant varieties, hygiene and fungicides, and codling moth with traps, bags and trunk banding, never alliums (and codling moth is absent from WA and the NT anyway); plant them if you like them, they are harmless and feed bees when flowering.', 'traditional'),
        ],
        "avoid": [
            ("Potatoes and tomatoes crowding the root zone (the 'shared blight' fear is a myth)", 'traditional'),
            ('Long grass and debris at the trunk (hides fallen fruit, invites collar rot and rodents)', 'established-practice'),
            ('Foxglove (toxic, and a declared weed in Tasmania, an environmental weed in Victoria)', 'traditional'),
            ("A mature black walnut's root zone (juglone, real chemistry but weak field evidence; black walnut is uncommon in Australia)", 'context-dependent'),
        ],
        "pollinator": "Most apples and pears need a second variety that flowers at the same time to set a good crop. Plant Health Australia's BeeAware confirms most apple varieties, most European pears (Pyrus communis) and most nashi are not self-fertile and need a compatible inter-planted donor. Apples pollinate apples and pears pollinate pears; the two groups cannot cross-pollinate each other. A long-flowering ornamental crabapple is a handy near-universal pollinizer for apples, as long as its bloom overlaps your eating variety. There are no bumblebees on mainland Australia, so honey bees and native bees do the work; plant for a calm, bee-friendly bloom. In warm, low-chill districts choose cultivars that flower together: Anna, Dorsett Golden and Tropic Sweet pollinate one another, and Anna is partly self-fertile.",
        "notes": "Chilling hours are the make-or-break choice across Australia's climate range: each variety needs a set amount of winter chill (hours below about 7C) to flower and fruit evenly. Cool-temperate and Mediterranean uplands (Tasmania, the Adelaide Hills, Stanthorpe, the WA south-west, the Victorian and NSW ranges) suit standard high-chill varieties like Granny Smith, Pink Lady (Cripps Pink) and Fuji, while warm coastal and subtropical districts (coastal Queensland, northern NSW, the Perth coastal plain) need low-chill cultivars such as Anna, Dorsett Golden and Tropic Sweet (roughly 100 to 300 hours). On the pest front, fruit fly is the number one problem, Queensland fruit fly in the east and Mediterranean fruit fly (endemic to WA), and no companion plant stops it: use exclusion netting or fruit bags, protein or spinosad splash baits, and strict hygiene (destroy every fallen fruit, never compost it).",
        "sources": [
            ('Apples and pears: Pollination (BeeAware, Plant Health Australia)', 'https://beeaware.org.au/pollination/pollinator-reliant-crops/apples-pears/'),
            ('Mediterranean fruit fly (DPIRD WA; endemic to WA, apples and pears are hosts, baiting plus netting plus hygiene)', 'https://www.dpird.wa.gov.au/businesses/pests-weeds-and-diseases/animal-pests-diseases/pest-insects/mediterranean-fruit-fly/'),
            ('How to Get Rid of Codling Moth (Yates Australia; established all states except WA and NT, controls are traps, banding, bags, sanitation)', 'https://www.yates.com.au/garden-hub/codling-moth/'),
            ('Venturia inaequalis: the causal agent of apple scab (peer-reviewed review; host range Rosaceae/Maloideae, not Solanaceae)', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC6640350/'),
        ],
    },
    {
        "name": 'Tropical Fruits (Lychee, Dragon Fruit, Banana, Longan)',
        "slug": 'tropical',
        "species_slugs": ['lychee', 'longan', 'dragon-fruit', 'banana', 'papaya'],
        "icon": '🍍',
        "intro": 'These are tropical and subtropical crops at home in the wet tropics, the NT Top End, SE Queensland and northern NSW; in Mediterranean and cool-temperate Australia they need a frost-free, wind-protected microclimate. Companion plants here earn their place by using the shaded ground productively, building soil and bringing in pollinators; they do not protect the crop from its real pests, which are managed by netting and monitoring.',
        "good": [
            ('French marigold (Tagetes patula)', 'The one companion with solid evidence: grown as a dense cover crop (rows and plants under about 18 cm apart) for a couple of months before planting in the same spot, its roots release alpha-terthienyl, which suppresses root-knot nematodes that stress young roots in sandy warm-climate soils; UF/IFAS extension is explicit that dotting a few plants between trees does not work, and that it suppresses rather than eradicates.', 'research-backed'),
            ('Sweet potato (Ipomoea batatas)', 'One of the better living mulches for warm-climate fruit gardens, with field trials confirming its sprawling canopy suppresses weeds, conserves soil moisture and reduces erosion while giving an edible tuber crop; keep it off the trunk and pull it back if it climbs into young trees.', 'established-practice'),
            ('Ginger and turmeric (Zingiber officinale, Curcuma longa)', 'A reliable understory layer under lychee, longan and banana in tropical and subtropical Australia: they want the same warm, humid, part-shade conditions, stay low so they never compete for light, and give an edible rhizome harvest (a space-stacking benefit, not pest control).', 'established-practice'),
            ('Pawpaw (papaya, Carica papaya) as a temporary nurse plant', 'Fast-growing (bearing within about a year) and useful for side shade and humidity while a young lychee or longan establishes, then removed once the permanent tree fills out; note it is a confirmed fruit-fly host (both Queensland and Mediterranean fruit fly), so net or harvest promptly, and do not rely on it as a windbreak because it becomes top-heavy and topples.', 'established-practice'),
            ('Insectary flowers (carrot and mustard families, alyssum, buckwheat, flowering herbs)', 'Small open flowers feed the hoverflies, lacewings and parasitic wasps that keep pest numbers down; Sustainable Gardening Australia identifies this biodiversity effect as the part of companion planting that genuinely holds up, so a mixed flowering border does more than any single pairing.', 'established-practice'),
            ('Heliconia as a screen', 'Forms a dense clumping screen that can work as a low windbreak or visual barrier in frost-free gardens, but the beneficial-insect claim is folklore: its flowers are built for bird pollination (sunbirds here, hummingbirds in their native range), not the small beneficials that control orchard pests, and some species spread vigorously by rhizome, so treat it as a screen only.', 'traditional'),
        ],
        "avoid": [
            ('Crowding with other tall trees', 'established-practice'),
            ('Cold-climate plants (brassicas, temperate-orchard understory, cool-season herbs)', 'established-practice'),
            ('A thick legume sward under mature lychee going into autumn', 'context-dependent'),
        ],
        "pollinator": "Lychee and longan are bee-pollinated and the honey bee is the principal pollinator. There is a real home-garden versus commercial conflict to know about: Yates calls a single lychee self-pollinating and says one tree will fruit, while BeeAware (Plant Health Australia) treats lychee as self-sterile and recommends at least two adjacent cultivars for good set (about 36 percent higher with two cultivars side by side, and fruit set roughly three times greater when flowers are open to bees versus bagged). For reliable crops, plant two cultivars. Dragon fruit flowers open at night and are worked by moths (and bats in their native range); some Australian-grown varieties are self-fertile (for example American Beauty) but others are self-sterile and need a second variety, and even self-fertile plants set larger fruit with cross or hand pollination, so confirm a variety's self-fertility with your supplier before relying on a single plant. Banana is parthenocarpic: triploid types like Cavendish and Lady Finger set fruit with no pollination and no seed.",
        "notes": 'Be honest about pests: no companion plant protects these crops. The major insect threat to lychee and longan in eastern Australia is the fruit-spotting bug (Amblypelta nitida) and its relatives, which pierce developing fruit so that more than 90 percent of green fruit can be lost in heavy infestations; the tools that work are exclusion netting, monitoring and removing nearby alternative-host trees. Lychee is also genuinely sensitive to excess nitrogen, which drives vegetative flushing in autumn and suppresses flowering, so keep any nitrogen-fixing groundcover light and mowed under mature trees rather than letting a thick legume sward build up before flowering.',
        "sources": [
            ('Lychees: Pollination (BeeAware, Plant Health Australia)', 'https://beeaware.org.au/pollination/pollinator-reliant-crops/lychees/'),
            ('Fruit-spotting bug (Business Queensland)', 'https://www.business.qld.gov.au/industries/farms-fishing-forestry/agriculture/biosecurity/plants/insects/horticultural/fruit-spotting-bug'),
            ('Marigolds (Tagetes spp.) for Nematode Management, ENY-056/NG045 (UF/IFAS Extension)', 'https://ask.ifas.ufl.edu/publication/NG045'),
            ('Companion Planting (Sustainable Gardening Australia)', 'https://www.sgaonline.org.au/companion-planting/'),
        ],
    },
]

# (name, description, evidence_grade)
AVOID_ALL = [
    ('Grass and turf right up to the trunk', 'The most reliable bad neighbour for any fruit tree, and the effect is competition (for water and nutrients), not allelopathy. Grass roots strip moisture and nutrients efficiently, slowing growth and delaying fruiting, and adding extra nitrogen does not overcome it. Keep a vegetation-free ring of roughly 0.6 to 1 m radius around young trees using woody mulch (kept off the trunk) or a clear circle. A larger cleared area gives no extra benefit. This is exactly what commercial Australian orchards do: a weed-free strip down the tree row with mown grass only in the alleyways. Applies Australia-wide.', 'research-backed'),
    ('Black walnut (Juglans nigra) and its juglone', "A genuinely allelopathic tree: juglone in roots, hulls, leaves and buds inhibits germination and growth of sensitive species in controlled studies, the best-documented case of tree allelopathy. But it is largely academic for Australian gardens, Juglans nigra is uncommon here (a declared environmental weed in parts of Victoria and NSW), and the popular 'kills apples, tomatoes, blueberries' victim lists are weakly sourced and rarely show a consistent field effect (poor growth nearby is often just shade and dry soil). The common English/grafted walnut (Juglans regia) produces far less juglone, so backyard walnut fears are usually misplaced. Treat juglone as a real but situational risk (worst in heavy, poorly drained soil directly under a mature tree), not a guaranteed plant killer.", 'research-backed'),
    ('Fennel (Foeniculum vulgare)', "Worth keeping away from an orchard, but for the right reason. The allelopathy evidence is in-vitro only (a petri-dish bioassay where 2.5 to 10 percent fennel extract suppressed germination of ryegrass, dandelion, wild barley and oat); there is no field evidence that living fennel harms fruit trees, and 'never plant fennel near anything' is folklore dressed as science. The genuine problem in Australia is that wild fennel is a serious declared weed across SA, Victoria, NSW and WA, so it escapes and competes. Discourage it near orchards on weediness and competition grounds, not on proven chemical harm.", 'context-dependent'),
    ('Brassicas in clubroot-prone soil (interplanting/rotation, not the trees)', 'Clubroot (Plasmodiophora brassicae) is a real, persistent soil pathogen (resting spores survive up to about 20 years) that is established in Australia and favours warm, wet, acidic soils. Crucially it only attacks brassicas (cabbage, broccoli, cauliflower, kale, radish, canola, brassica weeds) and does NOT infect fruit trees. It matters only if you interplant or rotate brassicas, including brassica green manures like mustard, under or near the trees in soil that is or could become infested. Manage with liming to pH 7.0 to 7.5, long non-brassica rotations and hygiene. A separate, modest brassica-on-brassica allelopathy (glucosinolate breakdown from residues) is also brassica-only and harmless to trees. Listed here as a caution about understorey vegetables, not the trees themselves.', 'context-dependent'),
]

# (name, description, evidence_grade)
NITROGEN_FIXERS = [
    ('White clover (Trifolium repens)', 'A genuine nitrogen-fixing perennial groundcover and long-established orchard/pasture floor species. Like all legumes it fixes nitrogen via rhizobia in root nodules (Australian rule of thumb: about 20 to 38 kg N per tonne of legume shoot dry matter, plus roughly another 30 percent from roots), and the benefit reaches trees slowly via residue and root breakdown, not as a direct live donation. Its real limit is water: poor drought and heat tolerance. Australian data show it dominates pastures only above about 700 mm rainfall and declines fast once soil moisture drops below about 35 mm with weekly maxima over 20C. Suits cool-temperate, high-rainfall or irrigated sites (Tasmania, southern Victoria, NSW tablelands, southwest WA, Adelaide Hills); the heat-tolerant Haifa cultivar extends it toward subtropical and lower-rainfall (about 700 mm) zones. Not reliable as an unirrigated cover in hot, dry-summer regions.', 'research-backed'),
    ('Tagasaste / tree lucerne (Chamaecytisus palmensis)', 'A fast-growing, deep-rooted leguminous shrub (roots to about 10 m on deep sands) that fixes nitrogen, yields abundant chop-and-drop mulch, and nurses frost-sensitive young trees. Best on deep, freely drained sandy soils; it dislikes waterlogging and heavy clay, and being deep-rooted it can draw down soil water, a real trade-off in low-rainfall alley cropping. Major Australian caveat: it is a recognised environmental weed in WA and Tasmania (in WA a serious invader of bushland on lateritic soils, naturalising from Badgingarra to Esperance, seedbank viable for over a decade, and by fixing N it raises soil nitrogen and encourages other weeds). Keep it well away from bushland, waterways and coastlines, and prune to prevent seed set. Where weediness is a concern, native nitrogen-fixers (some Acacia species) are alternatives.', 'established-practice'),
    ('Pigeon pea (Cajanus cajan)', 'A drought-tolerant, deep-rooted legume used as a fast green manure, nurse plant and chop-and-drop mulch shrub, deriving a very high proportion (often 90 percent plus) of its nitrogen from the atmosphere. Measured field fixation ranges widely (under 20 kg N/ha in a single season up to roughly 37 to 117 kg N/ha/yr in longer intercrops), but those figures come from African and Indian agroforestry studies, not Australian orchards, so treat them as indicative. In Australia it suits tropical, subtropical and warm-temperate frost-free areas (coastal and northern Queensland, the NT, northern NSW, warmer subtropical gardens); it is frost-sensitive and short-lived, so in cooler southern Australia use it as a summer green-manure annual.', 'research-backed'),
    ('Comfrey, ideally sterile Bocking 14 (NOT a nitrogen fixer)', "Include it for honesty: comfrey is not a legume and fixes NO nitrogen. The 'dynamic accumulator mining deep subsoil nutrients' claim is largely overstated folklore (most comfrey roots sit in the top foot of soil, and a plant cannot create nutrients that are not already there). What is real, from a single small Cornell field trial, is that comfrey foliage concentrates potassium (around 53,000 ppm) and silicon, so it is a useful fast-growing source of potassium-rich biomass for mulch and compost, recycling existing soil nutrients rather than generating fertility. Choose Bocking 14: it is sterile (sets no viable seed), spreading only by root division, so it is far less likely to become a weed than seeding types. Still divide clumps every few years and avoid letting root fragments escape.", 'context-dependent'),
    ('Legume groundcovers in general (how the benefit actually arrives)', 'A framing entry for the soil chapter. Legumes (clovers, tagasaste, pigeon pea) fix atmospheric nitrogen via rhizobia, and the amount scales with shoot biomass, but most of that nitrogen stays in the plant: at maturity 30 to 40 percent is locked in seed, and the rest reaches the orchard slowly as residues and roots decompose, not as a live root-to-root gift to the tree. Live transfer is modest and depends on layout (genuinely interplanting among the trees transfers more than a legume off to one side). Inoculate with the correct rhizobia strain if that host legume has not grown on the site in the last few years. Practical line: a legume floor is a slow soil-building contribution realised through slashing and mulching, not an instant fertiliser hit. Australian extension figures (soilquality.org.au) apply nationwide.', 'research-backed'),
]

POLLINATOR_SUMMARY = [
    ('Citrus', 'Self-fertile. One tree of any type fruits on its own.'),
    ('Mandarin and tangelo hybrids', 'Many (Imperial, Afourer, Minneola) set a light crop alone; a second variety lifts yield but adds seeds.'),
    ('Mango', 'Self-fertile. Kensington Pride (Bowen) crops reliably as a single tree.'),
    ('Avocado', 'A single tree sets some fruit. One Type A plus one Type B lifts yield, but it is not strictly required.'),
    ('Apple', 'Almost all need a different compatible apple flowering at the same time. Crabapple is a universal partner.'),
    ('Pear (European and Nashi)', 'Treat as needing a partner; plant two compatible varieties or a multi-graft tree.'),
    ('Sweet cherry', 'Most are self-infertile and fall into incompatibility groups; choose a known compatible pair.'),
    ('Plum', 'Many Japanese plums need a partner. A Japanese plus European pairing often fails, so match within type.'),
    ('Peach and nectarine', 'Self-fertile. One tree crops well.'),
    ('Apricot', 'Mostly self-fertile; a few varieties benefit from a partner.'),
    ('Fig', 'Common Australian varieties are parthenocarpic. No pollination or second tree needed.'),
    ('Lychee', 'Largely self-sterile in practice; bees must move pollen, so a lone tree crops erratically.'),
    ('Longan', 'Largely self-fertile; one tree usually crops (for example Biew Kiew).'),
    ('Dragon fruit', 'Varies by variety; some self-fertile, some need cross-pollen and hand pollination at night.'),
    ('Banana', 'No pollination required.'),
]

FAQS = [
    (
        'What is the best companion plant for all fruit trees?',
        'Comfrey (the sterile Bocking 14) is the most useful all-rounder. It mines nutrients from deep soil, makes excellent mulch, and does not spread by seed. Plant one or two per tree at the drip line. It does not fix nitrogen, so pair it with a legume groundcover for that.',
    ),
    (
        'Do companion plants actually repel pests?',
        "Mostly not in the way folklore claims. There is little evidence that a scattered herb repels a specific pest. What does work is biodiversity: a mix of flowering plants supports bees and natural predators (hoverflies, lacewings, parasitic wasps), and a few documented cases like dense marigolds suppressing soil nematodes. For Australia's main fruit pests, fruit fly and codling moth, rely on netting, bagging, traps and hygiene, not companions.",
    ),
    (
        'Do I need two fruit trees to get fruit?',
        'It depends on the species and variety. Most citrus, peaches, nectarines, figs and bananas are self-fertile. Apples, pears, sweet cherries and avocados crop far better with a second compatible variety. Check the pollinator requirements for your variety before buying.',
    ),
    (
        'Can I grow companion plants under a fruit tree?',
        'Yes, but avoid grass and keep a clear mulched circle right around the trunk to prevent collar rot. The most useful understorey plants are comfrey, white clover, alyssum and nasturtium. Plant them at the drip line, not against the trunk.',
    ),
    (
        'Why is fennel said to be bad near fruit trees?',
        'Fennel is the classic bad companion. The evidence that it chemically harms established fruit trees in garden soil is actually thin, but fennel self-seeds aggressively into a weed, so it is still sensible to keep it out of the orchard.',
    ),
    (
        'What can I plant to attract bees to my fruit trees?',
        'Borage, phacelia, alyssum, white clover and lavender all draw bees and other pollinators. Borage and phacelia are especially useful because they flower heavily in spring when most fruit trees bloom. Sow phacelia in autumn for spring flowers.',
    ),
    (
        'How close should companion plants be to fruit trees?',
        'Most companions work best at the drip line, the outer edge of the canopy, rather than against the trunk. Keep 30 to 50cm clear around the trunk with mulch. Tall companions like tagasaste should sit 2 to 3m out to avoid shading and root competition.',
    ),
]

# Page-level references for the evidence framing (not tied to one species).
GENERAL_SOURCES = [
    ('The Myth of Companion Plantings (Linda Chalker-Scott, Washington State University Extension)', 'https://s3.wp.wsu.edu/uploads/sites/403/2015/03/companion-plantings.pdf'),
    ('Companion Planting (Sustainable Gardening Australia)', 'https://www.sgaonline.org.au/companion-planting/'),
    ('Marigolds (Tagetes spp.) for Nematode Management (UF/IFAS Extension)', 'https://ask.ifas.ufl.edu/publication/NG045'),
    ('Flowering plants attract beneficial insects to vegetable farms (Cesar Australia)', 'https://cesaraustralia.com/blog/flowering-plants-attract-beneficial-insects-to-vegetable-farms/'),
    ('Do Black Walnut Trees Have Allelopathic Effects on Other Plants? (WSU Extension, Linda Chalker-Scott)', 'https://pubs.extension.wsu.edu/product/do-black-walnut-trees-have-allelopathic-effects-on-other-plants-home-garden-series/'),
    ('Managing Vegetation Around Fruit Trees (Utah State University Extension)', 'https://extension.usu.edu/yardandgarden/research/managing-vegetation-around-fruit-trees'),
]


# ----- Helpers -----

def load_valid_species_slugs() -> set:
    """Slugs that have a real /species/<slug>.html page. Empty set if the file is
    missing so internal links are silently omitted rather than 404."""
    try:
        return {s["slug"] for s in enabled_species()}
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return set()


def _species_link_html(sp: dict, valid_slugs: set) -> str:
    links = [
        f'<a href="/species/{s}.html" class="text-green-700 hover:underline">{s.replace("-", " ")}</a>'
        for s in sp.get("species_slugs", []) if s in valid_slugs
    ]
    if not links:
        return ""
    return (
        '<p class="text-xs text-gray-500 mt-3">Current stock and prices: '
        + ", ".join(links)
        + ".</p>"
    )


def _sources_html(sp: dict) -> str:
    srcs = sp.get("sources") or []
    if not srcs:
        return ""
    items = "".join(
        f'<li><a href="{url}" target="_blank" rel="noopener" class="text-green-700 hover:underline">{title}</a></li>'
        for title, url in srcs
    )
    return (
        '<details class="mt-3 text-xs text-gray-500">'
        '<summary class="cursor-pointer hover:text-gray-700">Sources and further reading</summary>'
        f'<ul class="list-disc pl-5 mt-1 space-y-0.5">{items}</ul></details>'
    )


def build_species_card(sp: dict, valid_slugs: set) -> str:
    good_rows = "".join(
        f'<li class="mb-2"><strong class="text-green-800">{name}</strong>. {desc}{grade_badge(grade)}</li>'
        for name, desc, grade in sp["good"]
    )
    avoid_items = "".join(
        '<span class="inline-flex items-center mr-2 mb-1">'
        f'<span class="bg-red-50 border border-red-200 text-red-700 text-xs px-2 py-0.5 rounded-full">{name}</span>'
        f"{grade_badge(grade)}</span>"
        for name, grade in sp["avoid"]
    )
    intro_html = f'\n  <p class="text-sm text-gray-600 mb-4">{sp["intro"]}</p>' if sp.get("intro") else ""
    return f"""
<section class="mb-10" id="{sp['slug']}">
  <h2 class="text-xl font-bold text-green-900 mb-3">{sp['icon']} {sp['name']}</h2>{intro_html}

  <div class="grid md:grid-cols-2 gap-6">
    <div>
      <h3 class="font-semibold text-gray-700 mb-2 text-sm uppercase tracking-wide">Good companions</h3>
      <ul class="text-sm text-gray-600 space-y-1 list-none pl-0">
        {good_rows}
      </ul>
    </div>
    <div>
      <h3 class="font-semibold text-gray-700 mb-2 text-sm uppercase tracking-wide">Avoid nearby</h3>
      <div class="mb-4 flex flex-wrap">{avoid_items}</div>

      <h3 class="font-semibold text-gray-700 mb-2 text-sm uppercase tracking-wide">Pollination</h3>
      <p class="text-sm text-gray-600">{sp['pollinator']}</p>
    </div>
  </div>

  <div class="mt-3 p-3 bg-gray-50 rounded-lg text-xs text-gray-500 border border-gray-100">
    {sp['notes']}
  </div>
  {_species_link_html(sp, valid_slugs)}
  {_sources_html(sp)}
</section>
"""


def build_how_to_read() -> str:
    legend = "".join(
        f'<li class="flex items-start gap-2">{grade_badge(g)}<span class="text-gray-600">{meaning}</span></li>'
        for g, meaning in [
            ("research-backed", "Supported by peer-reviewed studies or university research."),
            ("established-practice", "Broad horticultural consensus, low controversy."),
            ("traditional", "Commonly recommended folklore with little hard evidence."),
            ("context-dependent", "True only for certain varieties, climates or conditions."),
        ]
    )
    return f"""
<section class="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-8 text-sm">
  <p class="font-semibold text-amber-900 mb-1">How to read this guide</p>
  <p class="text-gray-700 mb-3">Most companion planting advice online is tradition rather than tested science, so we grade every suggestion by how good the evidence is. The honest summary: a diverse, well-mulched garden that feeds bees and predatory insects helps your trees, while most specific "plant this to repel that" pairings are unproven.</p>
  <ul class="space-y-1">
    {legend}
  </ul>
</section>"""


def build_avoid_section() -> str:
    rows = "".join(
        '<div class="flex gap-3 mb-3"><span class="text-red-500 mt-0.5 flex-shrink-0">&#10060;</span>'
        f'<div><strong class="text-gray-800">{name}</strong>{grade_badge(grade)}'
        f'<p class="text-sm text-gray-600 mt-0.5">{desc}</p></div></div>'
        for name, desc, grade in AVOID_ALL
    )
    return f"""
<section class="mb-10" id="avoid">
  <h2 class="text-xl font-bold text-green-900 mb-4">Plants to Avoid Near Fruit Trees</h2>
  {rows}
</section>
"""


def build_nitrogen_fixers_section() -> str:
    rows = "".join(
        '<div class="flex gap-3 mb-3"><span class="text-green-500 mt-0.5 flex-shrink-0">&#9679;</span>'
        f'<div><strong class="text-gray-800">{name}</strong>{grade_badge(grade)}'
        f'<p class="text-sm text-gray-600 mt-0.5">{desc}</p></div></div>'
        for name, desc, grade in NITROGEN_FIXERS
    )
    return f"""
<section class="mb-10" id="nitrogen">
  <h2 class="text-xl font-bold text-green-900 mb-4">Nitrogen Fixers and Soil Builders</h2>
  <p class="text-gray-600 text-sm mb-4">These plants improve soil fertility, reducing fertiliser needs across your whole orchard.</p>
  {rows}
</section>
"""


def build_pollinator_table() -> str:
    rows = "".join(
        f'<tr class="border-b border-gray-100 hover:bg-gray-50"><td class="py-2 pr-4 font-medium text-sm text-gray-800">{species}</td><td class="py-2 text-sm text-gray-600">{note}</td></tr>'
        for species, note in POLLINATOR_SUMMARY
    )
    return f"""
<section class="mb-10" id="pollinators">
  <h2 class="text-xl font-bold text-green-900 mb-3">Pollinator Requirements Quick Reference</h2>
  <p class="text-gray-600 text-sm mb-4">Check this before buying a single tree. Getting it wrong means years without fruit. For the full picture, see our <a href="/fruit-tree-pollination-guide.html" class="text-green-700 hover:underline">fruit tree pollination guide</a>.</p>
  <div class="overflow-x-auto rounded-lg border border-gray-200">
    <table class="w-full bg-white text-left">
      <thead class="bg-gray-50 border-b border-gray-200">
        <tr>
          <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Species</th>
          <th class="py-2 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Pollination</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100">
        {rows}
      </tbody>
    </table>
  </div>
</section>
"""


def build_faq_section() -> str:
    items = "".join(
        f"""<div class="mb-5">
  <h3 class="font-semibold text-gray-800 mb-1">{q}</h3>
  <p class="text-sm text-gray-600">{a}</p>
</div>"""
        for q, a in FAQS
    )
    return f"""
<section class="mb-10" id="faq">
  <h2 class="text-xl font-bold text-green-900 mb-4">Frequently Asked Questions</h2>
  {items}
</section>
"""


def build_references_section() -> str:
    items = "".join(
        f'<li><a href="{url}" target="_blank" rel="noopener" class="text-green-700 hover:underline">{title}</a></li>'
        for title, url in GENERAL_SOURCES
    )
    return f"""
<section class="mb-10" id="references">
  <h2 class="text-xl font-bold text-green-900 mb-3">References and Further Reading</h2>
  <ul class="list-disc pl-5 text-sm text-gray-600 space-y-1">
    {items}
  </ul>
</section>
"""


def build_toc() -> str:
    species_links = "".join(
        f'<li><a href="#{sp["slug"]}" class="text-green-700 hover:underline text-sm">{sp["icon"]} {sp["name"]}</a></li>'
        for sp in SPECIES_COMPANIONS
    )
    return f"""
<div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-8">
  <p class="font-semibold text-green-900 mb-2 text-sm">Contents</p>
  <ul class="space-y-1">
    {species_links}
    <li><a href="#avoid" class="text-green-700 hover:underline text-sm">Plants to avoid</a></li>
    <li><a href="#nitrogen" class="text-green-700 hover:underline text-sm">Nitrogen fixers and soil builders</a></li>
    <li><a href="#pollinators" class="text-green-700 hover:underline text-sm">Pollinator requirements quick reference</a></li>
    <li><a href="#faq" class="text-green-700 hover:underline text-sm">FAQs</a></li>
    <li><a href="#references" class="text-green-700 hover:underline text-sm">References and further reading</a></li>
  </ul>
</div>
"""


def build_faq_jsonld() -> str:
    """schema.org FAQPage structured data, kept in sync with FAQS."""
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in FAQS
        ],
    }
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>"


def build_page() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    valid_slugs = load_valid_species_slugs()

    species_sections = "".join(build_species_card(sp, valid_slugs) for sp in SPECIES_COMPANIONS)

    head = render_head(
        title="Companion Planting Guide for Fruit Trees (Australia) | treestock.com.au",
        description="Evidence-graded companion planting for citrus, mango, avocado, fig, stone fruit, apple and pear in Australia. Pollinator requirements, soil builders, plants to avoid, and which pest claims actually hold up.",
        canonical_url="https://treestock.com.au/companion-planting-guide.html",
        og_title="Companion Planting for Fruit Trees, an Evidence-Graded Australian Guide",
        og_description="Which companions actually help citrus, mango, avocado, fig and stone fruit in Australia, which are folklore, and what your trees really need for pollination.",
        og_type="article",
        og_image="https://treestock.com.au/og-image.png",
        extra_head=build_faq_jsonld(),
    )
    header = render_header()
    breadcrumb = render_breadcrumb([("Home", "/"), ("Companion Planting Guide", "")])
    footer = render_footer()

    return render_template(
        "companion_guide_page.html.j2",
        head=head, header=header, breadcrumb=breadcrumb, footer=footer,
        today=today, species_sections=species_sections,
        how_to_read=build_how_to_read(), toc=build_toc(),
        avoid_section=build_avoid_section(),
        nitrogen_fixers=build_nitrogen_fixers_section(),
        pollinator_table=build_pollinator_table(),
        faq_section=build_faq_section(),
        references_section=build_references_section(),
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: build_companion_guide.py /path/to/output/")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    output_dir.mkdir(parents=True, exist_ok=True)

    html = build_page()
    out_file = output_dir / "companion-planting-guide.html"
    out_file.write_text(html)
    print(f"Written: {out_file} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
