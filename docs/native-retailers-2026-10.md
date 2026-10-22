# Australian native plant retailers online

Checked 2026-10-22 by four parallel research agents (WA/SA/NT, VIC/TAS, NSW/ACT, QLD + national), merged and de-duplicated by Dale. Every site was opened directly; shipping states come from each site's own shipping page, not search snippets. Machine-readable copy: `data/native-retailers-2026-10.json` (evidence URLs, platform, notes per site).

**85 retailers with prices, 155 sites checked and excluded.** ★ = treestock already scrapes it.

| Group | Count |
|---|---|
| Ships live plants interstate | 21 |
| Delivers within its home state only | 8 |
| Ships, destination states unconfirmed | 11 |
| Native seed by post | 11 |
| Priced, pickup or local delivery only | 34 |

Interstate plant shippers reaching each state: WA 6 · NT 7 · SA 17 · QLD 20 · NSW 21 · ACT 20 · VIC 20 · TAS 7.

## What stands out

- **Only 5 sites post live native plants to every state**: Australian Plants Online, Nursery Near Me, Fernview, Garden Express and Diggers. Australian Plants Online charges a $15 biosecurity fee for WA/TAS/NT and ships those weekly. Nursery Near Me fills WA orders from WA nurseries, and sends TAS and NT tubestock only. Garden Express and Diggers charge quarantine surcharges.
- **No WA, SA or NT nursery posts live plants interstate.** WA's biggest online native range (Australian Native Nursery, Oakford, ~1,000 tube lines at ~$8) posts within WA only.
- **The famous specialists mostly don't sell online with prices**: Wariapendi, Newcastle Wildflower, Lullfitz, Zanthorrea, Kuranga, Austraflora, Gondwana and State Flora are all in section 6. The online natives trade is dominated by tubestock e-tailers, not the nurseries people know by name.
- **The usual exclusion is WA + TAS + NT**, and some VIC sellers (The Native Shop, Plantinspirations) also refuse Myrtaceae to SA.

## Corrections made while merging

The agents disagreed on four sites, so I opened their shipping pages again myself:

- **Evergreen Growers** ships to the NT but not WA or TAS. Its policy gives a flat NT rate of $35 and says it can't ship to WA or Tasmania. The WA agent's "no NT" was wrong.
- **Australian Plants Online** ships to all states, with the $15 WA/TAS/NT fee and a weekly dispatch. The QLD agent couldn't read its shipping page.
- **Hello Hello Plants** is alive (~1,376 natives). Its site moved to thetutuguru.com.au, which one agent mistook for a dead redirect. It delivers within Victoria only.
- **Nursery Near Me** and **Fernview**: the claims of shipping to all states hold as stated.

## Recheck later

- **State Flora (SA):** refused connections. Its order page says delivery anywhere in Australia.
- **Sydney Wildflower Nursery:** under maintenance. It previously did courier mail order.
- **Native Spirit Nursery (Wanneroo):** normally ships to every state except TAS, but its shop currently says pickup and local delivery only.
- **JavaScript-rendered or bot-blocked:** Flower Power, Verdigris Fern Nursery, Backyard Garden Enthusiast and Mitre 10.
- **Blerick Tree Farm:** its delivery page carries injected spam, so the site looks hacked. Don't link it.


## 1. Ships live plants interstate (21)

Sorted by how many states they reach.

| Retailer | Based | Type | Natives range | Ships to | Excludes | Freight | Conf. | Sample price | Platform |
|---|---|---|---|---|---|---|---|---|---|
| [Australian Plants Online](https://www.australianplantsonline.com.au) | near Nambour, Sunshine Coast, QLD | General | ~409 in native tubestock category; 800+… | **All states** | - | AusPost by weight; +$15 biosecurity fee for WA/TAS/NT, which ship wee… | high | Acacia baileyana Purpurea (purple wattle) tubestock, $7.05 | Magento |
| [Fernview Nurseries](https://fernview.com.au) | Victoria (03 5968 area code, Yarra Valley region; town not stated on site) | General | ~170 products, 47 in Native category | **All states** | - | Postage estimate page; not read | high | Eremophila glabra prostrate tubestock, $3.10 | WooCommerce |
| [Garden Express](https://gardenexpress.com.au/collections/native-plants) ★ | Monbulk, VIC | General (plants+seed) | ~238 in native-plants collection | **All states** | - | Basic delivery charge (historically $12.50); +$5 quarantine inspectio… | medium | Grevillea 'Winter Delight' 50mm pot, $6.90 | Shopify |
| [Nursery Near Me](https://nurserynearme.com.au) | Utchee Creek, QLD (not open to public) | General | ~946 in australian-natives collection;… | **All states** | - | From $9.95, calculated at checkout | high | Lilly Pilly 'Resilience' (Syzygium australe), tube, $17.95 | Shopify |
| [The Diggers Club](https://www.diggers.com.au) ★ | Dromana, VIC | General (plants+seed) | ~45 native-tagged products | **All states** | - | Plant shipping from ~$14.50 (third-party snippet) | medium | Hardenbergia violacea 'Happy Wanderer' super tube, $15.95 | Shopify |
| [Taz Wild Plants](https://www.tazwildplants.com) | Fingal Valley, TAS | Specialist | small (edible Tasmanian natives; count… | NT, SA, QLD, NSW, ACT, VIC, TAS | WA | - | medium | Bower Spinach (Tetragonia implexicoma), $4.85 (marked unava… | Square Online / Weebly |
| [Daleys Fruit Tree Nursery](https://www.daleysfruit.com.au/) ★ | Geneva via Kyogle, NSW | General | ~52 bush food plants plus rainforest tr… | WA, SA, QLD, NSW, ACT, VIC | TAS, NT | - | medium | Native Mulberry (Pipturus argenteus), from $3.40 | custom |
| [Evergreen Growers](https://www.evergreengrowers.com.au/) | Dural, NSW | Specialist | ~120 varieties, mostly natives (tubesto… | NT, SA, QLD, NSW, ACT, VIC | WA, TAS | flat per state: NSW/ACT $18.50, VIC/QLD $24, SA $28, NT $35; free ove… | high | Coast Banksia (Banksia integrifolia) tube stock, $12.00; tu… | custom (Next.js) |
| [Plants of Tasmania Nursery](https://www.potn.com.au) | Ridgeway (Hobart), TAS | Specialist | ~500 species (Tasmanian natives plus so… | SA, QLD, NSW, ACT, VIC, TAS | - | - | low | Baeckea gunniana tubestock, $6.50 | custom static HTML |
| [Native Plant Project](https://nativeplantproject.com.au) | Melbourne, VIC (nursery at Merricks, Mornington Peninsula per third-party listing) | Specialist | ~184 WooCommerce products (native tubes… | SA, QLD, NSW, ACT, VIC | WA, TAS, NT | - | high | 4 Plant Box (tubestock), $54.95 | WooCommerce |
| [Online Plants](https://www.onlineplants.com.au) | Research (Melbourne), VIC | General | ~1,440 products total; ~356 in Australi… | SA, QLD, NSW, ACT, VIC | WA, TAS, NT | Postcode-based freight; free Melbourne metro delivery over a threshol… | high | Superb Grevillea 14cm, $21.95 | Shopify |
| [Plantinspirations](https://www.plantinspirations.com.au) | near Tatura, VIC | General | ~261 in Australian Native Plants catego… | SA, QLD, NSW, ACT, VIC | WA, TAS, NT | Flat Australia Post rate $19.95 regardless of plant count | medium | Acacia acinacea 'Gold Dust Wattle' 1 plant, $5.45 | OpenCart (likely) |
| [Plants In A Box](https://plantsinabox.com.au) | Currumbin Valley, QLD | Specialist | ~420 natives (australian-native-plants-… | SA, QLD, NSW, ACT, VIC | WA, TAS, NT | Free standard delivery over $54; express available | high | Chamelaucium x Verticordia 'Paddy's Pink' waxflower, tube /… | Shopify |
| [Ross Creek Tropicals](https://www.rosscreektropicals.com.au) ★ | Gympie, QLD | General | ~93 in australian-native collection (25… | SA, QLD, NSW, ACT, VIC | WA, NT, TAS | - | high | Lemon Myrtle 140mm, $39.90 | Shopify |
| [The Native Shop (Wimmera Native Nursery)](https://www.nativeshop.com.au) | Dimboola, VIC | Specialist (plants+seed) | ~1,000 plant listings (mostly natives,… | SA, QLD, NSW, ACT, VIC | WA, TAS, NT | - | high | Grevillea 'Rowdy' 40mm tubestock, $8.50 | Shopify |
| [The Plant Hub (The Stoney Creek Trust)](https://theplanthub.com.au/) | Wauchope, NSW | General | ~122 products, ~65 natives (grasses, gr… | SA, QLD, NSW, ACT, VIC | - | free on full box (40+ tubes); flat rate below that (amount not stated… | high | Themeda 'Big Blue' (Blue Kangaroo Grass) 50mm tube, $8.95 | Shopify |
| [AllNatives Online Tubestock Nursery](https://www.allnatives.com.au/) | Hogarth Range (34 km SW of Casino), NSW | Specialist | large tubestock range across ~14 themed… | QLD, NSW, ACT, VIC | - | freight charged per block of 66 tubes; online freight estimator; mini… | high | Callistemon 'Great Balls of Fire' tubestock, $3.75 | custom |
| [Garden Variety](https://gardenvariety.com.au/) | NSW Central Coast | General | 200+ varieties overall, 25 in Native ca… | QLD, NSW, ACT, VIC | - | - | medium | Lomandra longifolia 'Lime Tuff' tubestock, $5.95 | WooCommerce |
| [IndigiGrow (First Hand Solutions Aboriginal Corporation)](https://indigigrow.com.au/shop/) | La Perouse and Chifley (Matraville), NSW | Specialist (plants+seed) | ~370 listings (31 pages x 12), local-pr… | QLD, NSW, ACT, VIC | WA, SA, NT, TAS | - | medium | Banksia integrifolia (Coast Banksia), $5.00-$15.00 by size | WooCommerce |
| [Wildtech Plants (Collectors Online)](https://www.wildtechnursery.com.au) | Glenmaggie / Heyfield, VIC | Specialist | ~986 products (native tubestock, large… | SA, QLD, NSW, VIC | - | Carton-based post and packing (standard carton up to 35 plants, large… | medium | Eucalyptus globoidea tubestock, $5.75 | WooCommerce |
| [Mountain View Nursery](https://mountainviewnursery.com.au) | Moruya, NSW | General | ~625-990 in natives collection; ~1,900… | NSW, ACT | - | Varies by delivery zone; free over $280 (search snippet) | high | Pycnosorus globosus 'Billy Buttons' 140mm, $20.00 | Shopify |

## 2. Delivers within its home state only (8)

Post, courier or the nursery's own vans, but statewide or regional rather than a local radius.

| Retailer | Based | Type | Natives range | Ships to | Delivery | Sample price | Platform |
|---|---|---|---|---|---|---|---|
| [Qld Tubestock](https://qldtubestock.com) | Lake Barrine, Atherton Tablelands, QLD | General | ~128 in natives collection (only a hand… | QLD | Banner: 'WE SHIP THROUGHOUT QUEENSLAND ONLY - NOT INTERSTATE.' | Castanospermum australe 'Black Bean' tubestock, $4.50 | Shopify |
| [Stoneman's Garden Centre](https://shop.stonemans.com.au/collections/natives) | Glenorchy, TAS | General | ~30 in Natives collection (1,019 produc… | TAS | FAQ: 'We currently offer plant delivery within Tasmania only.' Pots and tools ship Australia-wide. | Adenanthos 140mm, $18.95 | Shopify |
| [Blerick Tree Farm](https://www.blericktreefarm.com.au) | Neerim South, VIC | General | ~44 Australian native advanced trees (4… | VIC | 'Advanced trees delivered Victoria wide' via own zones and Van Berkel plant transport. | Acacia howittii 'Honey Bun', $30.00 | WooCommerce |
| [Garden World](https://gardenworld.au) ★ | Keysborough (Melbourne), VIC | General | ~100 natives (Australian Natives 83, Na… | VIC | 'Fast Local Melbourne Delivery' banner; shipping policy text not extractable. | Chrysocephalum 'Desert Flame' 14cm, $16.95 | Shopify |
| [Hello Hello Plants & Garden Supplies](https://www.thetutuguru.com.au/product-category/plant-types/natives-indigenous/) | Campbellfield, VIC | General | ~1,376 in Natives & Indigenous category | VIC | 'We currently deliver within Metro Melbourne and across Victoria only due to strict quarantine regulations.' | Grevillea 'Dezire' 6" pot, $19.99 | WooCommerce |
| [Plants for Spaces](https://www.plantsforspaces.com.au) | Melbourne, VIC (address not stated) | General | ~527 in native-plants category | VIC | Own van delivery within Victoria only ('Delivering plants across Melbourne, Geelong & Mornington Peninsula').… | Grevillea range $14.25-$49.25 depending on size | WooCommerce |
| [Australian Native Nursery](https://www.australiannativenursery.com.au) | Oakford, WA | Specialist | ~1,016 products (tubes) on Square store… | WA | Posts Mon/Tue; 'Due to quarantine restrictions we cannot ship plants outside of Western Australia.' | Grevillea diminuta tube, $8.00; Boronia megastigma tube, $8… | Square Online |
| [The Plant Cellar](https://theplantcellar.com.au) | Mount Helena, WA | General | ~296 natives (Natives category) of ~730… | WA | Hand delivery Perth metro; tubestock only shipped to regional WA by Australia Post (contact to order); 'canno… | Adenanthos 'Platinum', $16.99; Acacia cognata 'Limelight' $… | WooCommerce |

## 3. Ships, but destination states unconfirmed (11)

Policy unpublished, contradictory or rendered by JavaScript the agents could not read. Check by hand before relying on these.

| Retailer | Based | Type | Natives range | Delivery | Sample price | Platform |
|---|---|---|---|---|---|---|
| [Bush to Bowl](https://bushtobowl.com/) | Terrey Hills / Ingleside (Northern Beaches), NSW | Specialist | ~47 in Native Plants collection (bush f… | Shipping policy page is blank; a product listing indexed by search shows local pickup at 40 Myoora Rd, Terrey… | Midyim Berry, $13.00; Riberry (Syzygium luehmannii), $12.00 | Shopify |
| [Mole Station Native Nursery](http://www.molerivernursery.com/) | Tenterfield, NSW | Specialist | ~130 priced lines on the Sept 2026 orde… | Online order form (retail prices incl GST) with delivery address field offering every state; no freight terms… | Backhousia citriodora (Lemon Myrtle) 140mm, $14.60 | custom (ASP order form) |
| [Garden Centre Sunshine Coast](https://www.gardencentresunshinecoast.com.au) | 49 Caloundra Rd, Caloundra, QLD | General | ~214-232 in native-plants collection; ~… | Local truck on Sunshine Coast; 'independent transport companies' outside it, no states listed. Pickup 7 days. | Acmena smithii minor 'Allyn Magic' 140mm, $15.00 | Shopify |
| [Yuruga Nursery](https://yuruga.com.au) | Walkamin, Atherton Tablelands, QLD | Specialist | ~350 priced lines in Oct 2026 retail li… | Order by email/phone from the stock list. Calyx directory says mail order for 140mm pots, Australia only; own… | Asplenium australasicum 'Bird's Nest Fern' 140mm, $16.50 (R… | WordPress (no cart) |
| [Harmony Garden Centre](https://harmonygc.com.au/shop-online/plants/native-tube-lines/) | Lauderdale (Hobart eastern shore), TAS | General | ~26 native tube lines plus a Native Bus… | Online cart exists but no delivery or pickup terms published. | Allocasuarina verticillata 50mm tubestock, $6.95 (10 for $6… | BigCommerce |
| [Conservation Collective](https://www.conservationcollective.shop) | Somerville, VIC | Specialist | ~181 products (indigenous tubestock, gr… | Store config has shipping and pickup enabled; a Delivery page exists but is JS-rendered and could not be read… | Themeda triandra (Kangaroo Grass), $6.00 | Square Online |
| [Diaco's Garden Nursery](https://diacos.com.au/australian-natives/) ★ | Heatherton, Mornington and Geelong, VIC | General | ~139 in australian-native-plants catego… | FAQ mentions shipping and handling costs but no area; a directory says online with delivery in Melbourne. Tea… | Billy Buttons, $12.95 | WooCommerce |
| [Formosa Gardens Nursery](https://www.formosagardensnursery.com.au) | Ballarat, VIC | General | ~159 in Natives category (2,090 product… | Online store is JS-rendered; delivery terms not readable. Store platform advertises delivery/pickup/shipping… | Brachyscome 'Fresco Purple', $14.95 | Square Online |
| [Peppermint Ridge Farm (Native Food Plant Nursery)](https://peppermintridgefarm.au/product-category/nursery/) | Victoria (Bunurong Country; town not stated on page) | Specialist | ~37 bush food plants (tubestock, 14cm,… | No shipping, pickup or delivery terms found on site. | Mountain Pepper (Tasmannia lanceolata) female, $25.00 | WooCommerce |
| [Reforest Bush Nursery](https://www.reforestnursery.com) | Mornington Peninsula, VIC (town not stated) | Specialist (plants+seed) | ~126 products (indigenous/native tubest… | 'Our online shop is designed for postal orders... delivered by Australia Post.' No state list found. Nursery… | Acacia suaveolens square tubestock, $7.00 | unknown (custom/hosted builder) |
| [Wombat Gully Plant Farm](https://shop.wombatgullyplantfarm.com.au) | Moolap (Geelong), VIC | General | ~69 Native + 17 Native Trees (513 produ… | Header: 'Delivery or Pickup in Store Available'. Shipping policy page has no terms; delivery area not stated… | Grevillea 'Deua Flame' 6 inch, $12.99 | Shopify |

## 4. Native seed by post (11)

| Retailer | Based | Natives range | Ships to | Excludes | Conf. | Sample price |
|---|---|---|---|---|---|---|
| [Mr Fothergill's Seeds](https://www.mrfothergills.com.au/collections/australian-native-seeds) | South Windsor, NSW | ~41 Australian native seed products | **All states** | - | low | Billy Button wildflower seeds, $6.70 |
| [Nindethana Seed Service](https://www.nindethana.net.au) | Albany, WA (seed hubs also in VIC and SA) | large: hundreds of native seed species,… | **All states** | - | medium | Carex appressa seed, $1.089/g (25-249 g) |
| [Olive Pink Botanic Garden (Garden Gift Shop, Centralian Seeds)](https://opbg.com.au/shop/) | Alice Springs, NT | ~8 Central Australian native seed packe… | **All states** | - | low | Desert Rose seed, $9.00 |
| [Australian Seed](https://www.australianseed.com) | Bridgetown, WA | ~623 products in Australian Native cate… | WA, NT, SA, QLD, NSW, ACT, VIC | TAS | high | Gold Dust Wattle (Acacia acinacea) seed, $5.06/packet |
| [Australian Wildflower Seeds](https://australianwildflowerseeds.com.au) | Donnybrook, WA | ~63 products (WA wildflower seed packet… | WA, NT, SA, QLD, NSW, ACT, VIC | TAS | high | Banksia prionotes seed packet (~5 seeds), $7.35 |
| [Native Seeds Pty Ltd](https://nativeseeds.com.au/shop/) | North East Victoria | ~34 native grass/pasture seed products… | NT, SA, QLD, NSW, ACT, VIC, TAS | - | medium | Kangaroo Grass seed, $88.00 |
| [AustraHort](https://austrahort.com.au) | Queensland (07 3821 phone, Redlands area); warehouse in QLD | ~416 seed products (500+ species claime… | ? | - | low | Acacia excelsa seed, $1.00 ex GST (sold by weight, min 25 g… |
| [Australian Seed Company](https://www.ausseed.com.au) | Hazelbrook, NSW | hundreds of tree/shrub/wildflower seed… | ? | - | low | Banksia aemula (Wallum Banksia), 100 seeds $36.70 ex GST (2… |
| [Blackwood Seeds](https://www.blackwoodseeds.com.au) | Inman Valley, SA | 450+ South Australian native species | ? | - | low | Acacia pycnantha (golden wattle) seed, $8 per 25 g / $200 p… |
| [Royston Petrie Seeds (RP Seeds)](https://rpseeds.com.au/seedcatalog/aust+natives) | Mudgee, NSW | 80+ native lines in 'Aust Natives' alon… | ? | - | low | Acacia acinacea (Gold Dust Wattle) seed 1g, $6.79 |
| [Wildseed Tasmania](https://wildseedtasmania.com.au) | Sorell area, TAS (per ANPSA) | large Tasmanian native seed catalogue (… | ? | - | low | Banksia seed, packet $4.50 / 100 seeds $11.00 |

## 5. Priced, but pickup or local delivery only (34)

Includes community and Landcare nurseries whose "price" is a flat tube price or a priced stock list rather than a cart.

| Retailer | Based | Type | Natives range | Delivery | Sample price |
|---|---|---|---|---|---|
| [The Heritage Nursery (Yarralumla)](https://heritagenursery.com.au/) ★ | Yarralumla, ACT | General | ~230 products typed NATIVES out of ~1,6… | Local delivery to ACT and Queanbeyan suburban areas only; click & collect. | Hardenbergia 'Regent' 20cm pot, $39.99 |
| [Blue Mountains Conservation Society Native Plant Nursery](https://www.bluemountains.org.au/nursery.shtml) | Blue Mountains, NSW | Specialist | local-provenance Blue Mountains species… | Buy at nursery / Blackheath Growers Market; enquiries by email; no delivery stated. | tubestock $5 each, ferns/round pots $6, supertubes $10 (pri… |
| [Canberra Native Nursery](https://canberranativenursery.com.au/) | Carwoola, NSW (Canberra region) | Specialist | ~88 lines on Spring/Summer 2026 list | Order by email/text/DM from the PDF list, invoiced; delivery for orders of 30+ plants in the Canberra region;… | 70mm $11, 90mm $14, 125mm $16, 140mm $18; Correa alba 200mm… |
| [Friends of the Koala Nursery](https://friendsofthekoala.org/native-plant-nursery-northern-rivers/) | East Lismore, NSW | Specialist | 240+ tubestock species (ANPSA) | Open by appointment; no delivery mentioned. | Koala food eucalypts (e.g. E. microcorys Tallowood) tubesto… |
| [Native Grace](https://www.nativegrace.com.au/) | Robertson (Southern Highlands), NSW | Specialist (plants+seed) | ~219 plant listings (68 in stock today)… | Local delivery across the Southern Highlands and from Wollongong to Nowra; pickup at 98 Hoddle St Robertson;… | Callistemon 'Harkness' 140mm, $18.50 |
| [Northern Rivers Natives](https://northernriversnatives.com.au/) | Mooball, NSW | Specialist | rainforest and bush food tubestock, lon… | Retail nursery open Wed-Sun; no delivery or postage mentioned. | Rainforest tubestock in NPT, $4.50 (50+ $4.00); Cassia mark… |
| [Weddin Community Native Nursery](https://weddinnativenursery.com) | Grenfell, NSW | Specialist | ~36 local species | Visit 43 East St Grenfell Tue-Sat mornings; no delivery mentioned. | individual tubes $3.00 (100-499 $2.80) |
| [Plants Direct NT](https://www.plantsdirectnt.com.au) | Humpty Doo, NT | General | ~25 natives (tropical natives: Syzygium… | Own delivery Darwin city to Berry Springs, arranged by phone within 48 h; outside that area contact for a quo… | Xanthostemon chrysanthus 'Little Goldie' / Acmena smithii '… |
| [Coolum Community Native Nursery](https://www.coolumnatives.com) | 157 Warran Rd, Yaroomba, QLD | Specialist | ~250 lines on monthly retail stocklist… | Walk-in / pickup at Yaroomba only. No delivery mentioned. | Native tube 50mm, $4.00 ($3.50 each for 50+); 140mm pots $1… |
| [Delivertree](https://delivertree.com.au) | Caboolture, QLD | General | ~65 in native-plants-for-sale (plus bus… | Personal delivery to Brisbane, Moreton Bay, Sunshine Coast and Gold Coast per site/search snippet; no courier… | Eumundi Quandong (Elaeocarpus eumundi) 300mm, $235.00 |
| [Mooloolah River Landcare Native Plant Nursery](https://mrl.org.au/native-plant-nursery/) | 2671 Steve Irwin Way, Glenview, QLD | Specialist | unknown; monthly 'Current Nursery Stock… | Order by phone/email, pickup Mon/Tue by arrangement or visit. No delivery. | Tubes (50mm) $4.00; 140mm $12; 200mm $25 (size price list,… |
| [Platypus Plants](https://www.platypusplants.com.au) | Palmwoods, QLD (PO box; online only) | General | ~160 in natives collection (59 currentl… | Own delivery to Brisbane, Sunshine Coast, Gold Coast, Toowoomba, Gympie 'and beyond' (SEQ regional delivery,… | Lilly Pilly 'Resilience' (Syzygium australe) 140mm, $21.00 |
| [Sunshine Coast Plants](https://sunshinecoastplants.com.au) | Forest Glen, QLD (depot; online only) | General | ~50+ natives by keyword scan of 372 pro… | Own pallet delivery to SEQ, Wide Bay and Northern NSW only; click & collect at Forest Glen by appointment. | Grevillea 'Honey Gem', $20.00 |
| [Adelaide Plant Co](https://adelaideplantco.com.au) | Adelaide, SA | General | ~386 products in Australian Native Plan… | Own delivery runs: metro Adelaide Mon-Fri (Seaford to Gawler); fortnightly regional (Murray Bridge, Adelaide… | Eremophila glabra 'Blue Horizon' 140mm, $14.49 |
| [Barossa Bushgardens Community Nursery](https://barossabushgardens.com.au/community-nursery) | Nuriootpa, SA | Specialist | ~80 local Barossa species on plant list | Order online (form), by phone, or visit; pickup at nursery Tue-Thu. No delivery mentioned. | Any tubestock $4.00 (e.g. Kennedia prostrata, Running Postm… |
| [Provenance Indigenous Plants](https://provenance.net.au) | Salisbury Park, SA | Specialist | ~100 local-provenance species on monthl… | Pickup at nursery (Mon-Fri, last Sat of month). No delivery or shipping mentioned. | All standard tubes $4 each, 6 for $20 (e.g. Kennedia prostr… |
| [Derwent Catchment Project Native Nursery](https://derwentcatchment.org/nursery/) | Hamilton, TAS | Specialist | shelterbelt/revegetation species list (… | Order by contacting the nursery manager; pickup at 5349 Lyell Highway, Hamilton. | Tubestock $3.50 ($3.00 for 100+) |
| [Understorey Network](https://www.understorey-network.org.au) | Glenorchy (Hobart), TAS | Specialist | Tasmanian native tubestock (community n… | 'We do not have an online store. Items can be purchased at the nursery.' Orders by email. | Tubestock $3.00 each ($2.50 for 100+) |
| [Park Lane Nursery](https://www.parklanenursery.com.au) | Wangaratta, VIC | Specialist | ~369 tubestock lines (mostly native/ind… | Online orders show 'Pickup available, usually ready in 2-4 days' at 95 Park Ln Wangaratta. No shipping policy… | Leptospermum petersonii (Lemon-scented Tea-tree) tubestock,… |
| [Victorian Indigenous Nurseries Co-operative (VINC)](https://www.vinc.net.au) | Fairfield, VIC | Specialist (plants+seed) | large indigenous tubestock range (catal… | Retail in store (Mon/Tue/Fri, Sat seasonal) or pre-order small quantities; minimum 20 plants for pre-orders.… | Standard forestry tubestock, retail non-member $6.90 (membe… |
| [Dawson's Garden World](https://dawsonsgardenworld.com.au) | Forrestfield, WA | General | ~24 natives (Native category) of ~256 p… | T&Cs mention 'Delivery & Click & Collect' but no delivery area or fees published; Perth garden centre so assu… | Anigozanthos 'Celebrations Masquerade' kangaroo paw, $19.95 |
| [Geographe Community Landcare Nursery (Geographe Plants)](https://gcln.org.au) | Ambergate (Busselton), WA | Specialist | ~218 species available (779 species pag… | Pickup only; T&Cs require an estimated pick-up date. Retail area Mon-Fri 9am-2pm. 'Bulk order online' via Woo… | Retail 50mm tube $5.50, 140mm pot $11.00; Acacia saligna (s… |
| [Guildford Garden Centre](https://guildfordgardencentre.com.au) ★ | Guildford, WA | General (plants+seed) | ~615 products in 'Australian Native' +… | Delivers to Perth metro; mails selected items (e.g. seeds) Australia-wide; cannot send plants and trees outsi… | Grevillea 'Coral Baby', $19.99 |
| [Kambarang Garden Centre](https://www.kambagc.com.au) | Bentley, WA | General (plants+seed) | ~241 natives (Small/Medium/Large Native… | Online orders are pickup at 75 Manning Rd, Bentley; 'To arrange delivery (WA only) call...'. Search snippet s… | Eremophila glabra 'Kalbarri Sunset' 140mm, $18.00 |
| [Lakeside Plants & Nursery](https://lakesideplants.com) | 10 min south of Bunbury, WA | General | ~34 natives (25 Native Bushes + 9 Nativ… | Click & collect; delivery by contact from $45 for local Bunbury areas; no Australia Post; 'we do not ship pla… | Grevillea 'Loopy Lou', $22.50 |
| [Muchea Tree Farm](https://www.mucheatreefarm.com.au) | Muchea, WA | Specialist | ~487 products, mostly WA natives | 'Due to difficulties in shipping, we only take orders from WA customers.' Site notice: 'NO DELIVERY TO PRIVAT… | Acacia alata tube, $3.60; Grevillea 'Royal Mantle' $15.00 |
| [Native Plants WA](https://www.nativeplantswa.org.au) | Cooloongup, WA | Specialist | retail plant list PDF (Sept 2026), loca… | Pickup from retail nursery (Mon-Wed 9am-12pm); email list for quote. No delivery mentioned. | Any forestry tube $6 |
| [Snippy's Yard](https://www.snippysyard.com.au) | Dianella, WA | Specialist (plants+seed) | ~63 plants + ~39 seed lines (194 produc… | Live plants: Perth only, local delivery within 50 km of Dianella, or pickup. Seeds shipped Australia-wide exc… | Grevillea 'Mello Yellow' 140mm pot, $18.00; Banksia menzies… |
| [Tintuppa Nursery](https://www.tintuppanursery.com.au) | Bridgetown (Winnejup), WA | Specialist | ~100+ species on 2026 plant list PDF | Orders by contact; pickup by appointment or at local markets (market calendar). | Any 50mm forestry tube $5.00 (1-9), $4.50 (10-400) |
| [Trillion Trees (formerly Men of the Trees)](https://trilliontrees.org.au) | Hazelmere, WA | Specialist | ~300 species on 2027 price list | Order via contact form/phone from priced PDF catalogue; Perth metro delivery or pickup Hazelmere. Online shop… | Acacia acuminata (Jam Wattle) tube, $2.65; 130mm pots $15 |
| [Waldecks Garden Centres](https://www.waldecks.com.au) | Perth (multiple stores), WA | General | ~274 natives (product_type 'Natives') o… | Plants delivered by in-house team within 40 km of their Perth stores only; 'unable to ship greenstock outside… | Kangaroo Paw Anigozanthos 'Bush Coral' 140mm, $17.99 |
| [Westgrow Farm Trees](https://westgrow.com.au) | Meckering, WA | Specialist | ~336 products (mostly natives: eucalypt… | 'We do not ship/post seedlings so they will need to be collected or delivered.' 'we only supply to customers… | Banksia nivea (Honeypot Dryandra), listed from $25.00 (opti… |
| [Wheatbelt Native Gardens](https://www.wheatbeltng.com.au) | Kellerberrin, WA | Specialist | stocklist incl. up to 80 Eremophila for… | 'Can you post plants to me? Unfortunately not... all plants are to be collected from WNG HQ in Kellerberrin.'… | Any forestry tube $6.00, super tube $10.00 |
| [Bunnings Warehouse](https://www.bunnings.com.au) | National chain (stores in all states) | General | large natives range in 140mm (dozens of… | Plant listings checked are marked 'In-store only': prices online, but buy in store; no plant delivery. | 140mm Grevillea 'Robyn Gordon', $13.48 |

## 6. Checked and excluded (155)

No prices, wholesale only, dead, or too few natives. Kept so nobody re-checks them blind.

| Site | Reason |
|---|---|
| [All Green Nursery](https://shop.allgreen.com.au/collections/australian-native-plants) | Only 9 natives in online shop (Melbourne delivery) |
| [All Rare Herbs](https://www.allrareherbs.com.au) | QLD (tracked by treestock). No native/bush tucker category; herbs and exotics. |
| [Allan's Garden Centre Prospect](https://allansprospect.spiffystores.com) | Online store sells gifts/books/seeds; no live natives |
| [Apace WA](https://www.apacewa.org.au) | No online prices; retail is walk-in (North Fremantle WA), wholesale by email |
| [AridSmart Nursery (Australian Arid Lands Botanic Garden)](https://www.aalbg.sa.gov.au) | Site unreachable 2026-10-22; walk-in nursery/shop at Port Augusta SA, no online prices verified |
| [Arnhem Nursery](https://www.arnhemnursery.com.au) | Site unreachable 2026-10-22 (McMinns Lagoon NT, tropical general) |
| [Aspects of Kings Park](https://www.aspectsofkingspark.com.au) | Shopify gift shop (961 products) with books/gifts, no plants or seed |
| [Austplant Nursery & Gardens](https://austplant.com.au) | Online shop sells gift vouchers only; plant catalogue unpriced |
| [Austraflora](https://austraflora.com) | Wholesale grower; no retail prices |
| [Australian Native Farm Forestry](https://iwanttrees.com.au) | Revegetation/farm forestry supplier, no public prices |
| [Backyard Garden Enthusiast](https://backyardgardenenthusiast.com.au/) | native seed packet shop (regional NSW, $5 post, no TAS/WA), but JS store; could not verify prices. Recheck by hand |
| [Ballarat Nursery](https://www.ballaratnursery.com/shop) | Advanced trees; no prices shown, no native listings |
| [Barung Landcare Native Nursery](https://barunglandcare.org.au/native-nursery/) | QLD (Maleny). No plant prices online; in-person sales. |
| [Benara Nurseries](https://www.benaranurseries.com) | Trade/wholesale (Trademart), no public retail prices |
| [Bilby Blooms](https://www.bilbyblooms.com.au/) | plant list download only, no prices seen; open days, Binnaway |
| [Bili Nursery (Westgate Biodiversity)](https://westgatebiodiversity.org.au/bili-nursery/) | Plant lists without prices; shop sells vouchers |
| [Boyanup Botanical](https://boyanupbotanical.com.au) | No prices or shop visible (600+ species, wholesale and retail, Boyanup WA) |
| [Brent's Natives (Kilsyth)](https://www.facebook.com/Brentsnatives) | Facebook only, no priced website (mail order by arrangement) |
| [Burringbar Rainforest Nursery](https://burringbarrainforestnursery.com.au/) | 'We no longer do online shopping'; local delivery only, no priced list |
| [Bushland Flora Vic (Bush Magik)](https://www.outdoordesign.com.au/landscape-supplies/bushland-flora-bush-magik/9466) | Wholesale only (Mount Evelyn) |
| [Bywong Nursery](https://bywongnursery.com.au/) | wholesale; shop 'coming soon' |
| [Candlebark Community Nursery](https://candlebark.org.au) | Plants-available list without prices |
| [Cape Nursery](https://capenursery.com.au/) | wholesale advanced-tree/project nursery |
| [Cedar Grove Landcare Native Nursery](https://cedargrovelandcare.org.au) | QLD (Logan). No plant prices online. |
| [CERES Nursery](https://ceres.org.au/nursery/) | No online shop or prices |
| [Cheeky Plant Co](https://cheekyplantco.com.au/) | indoor plants/gifts, no natives |
| [Codrington Nursery](https://www.codrington-nursery.com.au) | No prices; 'call to discover our range' |
| [Cool Country Natives](https://www.coolcountrynatives.com.au/) | no prices or online shop; walk-in nursery Pialligo ACT |
| [Cool Natives Nursery (Armidale)](https://coolnativesnursery.com/) | dead: .com is a parked ad redirect, .com.au does not resolve |
| [Coromandel Native Nursery / Adelaide Advanced Trees](https://natives.net.au) | Plant list without prices; call or email (Coromandel East SA) |
| [CRISP Nursery](https://www.crispnursery.org.au) | No prices online |
| [Darwin Plant Wholesalers](https://www.darwinplantwholesalers.com.au) | Trade only, login required (Lambells Lagoon NT) |
| [Diversity Native Seeds](https://diversitynativeseeds.com.au/) | seed by quote only, no prices |
| [Domus Nursery](https://www.domusnursery.com.au) | Wholesale grower supplying WA garden retailers; store finder, no prices |
| [Eastern Forest Nursery](https://easternforestnursery.com.au/) | wholesale revegetation/project seedlings |
| [eBay / Etsy](https://www.ebay.com.au) | No established native nursery storefront found; only private seed sellers (e.g. Grevillea banksii seed from Hay NSW, AU$6.50). Not listed. |
| [Ecolife Plants](https://www.ecolifeplants.com.au/australiannative) | No prices on natives listings (Bass Coast, local delivery) |
| [Eden Gardens](https://edengardens.com.au/) | Shopify returns 0 products |
| [Fairhill Native Botanic Gardens & Nursery](https://www.fairhill.com.au) | QLD (Ninderry/Yandina). No plant prices or online plant sales. |
| [Firewheel Rainforest Nursery](https://www.firewheelnursery.com.au/) | wholesale; availability list as image, no prices |
| Fleurieu Natives | Contact by phone/email only, no website shop (Mount Compass SA) |
| [Flower Power Garden Centres](https://www.flowerpower.com.au/products/plants/australian-natives) | unverified: bot protection blocked fetch. Has an Australian natives category ('hundreds') with Sydney-metro truck delivery from $55. Recheck by hand |
| [Forest Heart eco-Nursery](https://www.forestheart.com.au/shop) | QLD (Maleny). Online shop sells books, mulch, sprays and vouchers only; no plants online. |
| [Friends of Kings Park plant sales](https://www.friendsofkingspark.com.au/friends-plant-sales/) | Quarterly plant-sale events only; online pre-sale window (WooCommerce, ~263 species for the Nov 2026 sale) currently shows $0 prices, pickup at the sale; gener… |
| [Fruit Tree Man](https://fruittreeman.com.au) | Fruit trees, prices show $0, not a natives range (WA) |
| [Future Generation Natives](https://www.futurenatives.com.au) | 'Until further notice not taking plant orders or supplying plants' (Mt Torrens SA) |
| [Garden Grove](https://gardengrove.com.au) | Online shop sells landscape products only, no plants (Golden Grove SA) |
| [Gardening with Angus](https://gardeningwithangus.com.au/shop) | sells fertiliser/books, no plants; owners now in Tasmania |
| [Geelong Native Plants](https://www.geelongnativeplants.com.au) | Domain now redirects to an unrelated abrasive-blasting business |
| [GHEMS Revegetation](https://www.ghems.com.au) | Contracting/reveg services, no shop |
| [Goldfields Revegetation](https://www.goldfieldsrevegetation.com.au) | Website unreachable (connection refused); listings say no current website |
| [Gondwana Nursery](https://gondwananursery.com.au/) | wholesale only (5-tray minimum) |
| [Greengold Nursery](https://www.greengoldnursery.au/) | 37 products, giftware, no natives range |
| [Greening Australia SA nursery (Pasadena)](https://www.greeningaustralia.org.au) | Wholesale provenance seed/tubestock for revegetation projects, no retail prices |
| [Greenlink Box Hill](https://greenlinkboxhill.org/products) | Catalogue of ~200 plants without prices; in-person sales |
| [Growing Bush / Indigeflora / Ecodynamics / Creation Care / Environmental Regeneration Australia / Dealtry Native Nursery](https://cdn.environment.sa.gov.au/landscape/docs/hf/Landscape-SA-Hills-and-Fleurieu-Native-Plant-Nurseries.pdf) | SA growers by appointment, contract or wholesale (Creation Care min 2,000 seedlings); no websites with prices |
| [Gympie Landcare Retail Nursery](https://gympielandcare.org.au/nursery/retail/) | QLD. Only 'prices start from $3.20'; no product prices or online shop. |
| [Habitat Plants](https://habitatplants.com.au) | Closed to the public Nov 2022; contract growing only, orders closed |
| [Hamel Nursery](https://www.hamelnursery.com.au) | Wholesale full-tray pre-orders only, no prices |
| [Harvest Seeds & Native Plants](https://www.harvestseeds-nativeplants.com.au/) | stock lists (Google Drive PDFs) have quantities, no prices |
| [Harvest Seeds / RP Seeds / Seedworld / Kimseed / Red Dirt Seeds / Seed Shed / Wildseed Tasmania / Seeding Victoria](https://anpsa.org.au/plant-guides/australian-native-seed-suppliers/) | Native seed suppliers with no visible online prices on homepage probes (bulk/quote or catalogue on request). Not deep-checked. |
| [Highway Haven Nursery](https://www.hwyhaven.com.au/) | no shop or prices; Wardell |
| [Kersbrook Landcare Nursery](https://kersbrook.landcaregroup.org.au) | Grow-to-order and plant sale days; no online prices found (Williamstown SA) |
| [Kimseed Australia](https://kimseed.com.au) | Site now sells seed-harvesting machinery; no seed prices online (Wangara WA) |
| [Kingscliff Nursery](https://kingscliffnursery.net.au/) | general coastal nursery, no online shop |
| [Knox Environment Society nursery](https://www.kes.org.au) | No prices online |
| [Ku-ring-gai Wildflower Nursery](https://www.krg.nsw.gov.au/Things-to-do/Ku-ring-gai-Wildflower-Garden/Wildflower-Nursery) | order form with no prices visible; delivery to Ku-ring-gai residents only |
| [Kumbartcho Nursery](https://www.kumbartcho.org.au) | QLD (Eatons Hill). Says 'from $2.50 ea' and has a Pick & Collect page, but no product prices readable (Wix store has no products in sitemap). |
| [Kuranga Native Nursery](https://www.kuranga.com.au) | Online shop sells gifts only; no plant prices online |
| [Leschenault Community Nursery](https://leschenaultcommunitynursery.com.au) | WooCommerce catalogue (154 products) shows no prices; nursery under administrators (BRI Ferrier) (Bunbury WA) |
| [Lullfitz Nursery](https://www.lullfitz.com.au) | No prices or shop; site says 'prepaid orders on hold till further notice'; now garden design consulting (WA) |
| [Mallee Native Plants](https://www.malleenativeplants.au) | Blog of a (closed) SA nursery; owner deceased 2018; no shop |
| [Manuka Native Nursery](https://manukanativenursery.com) | Website returns Wix 404 (Allendale North SA); walk-in Wed-Sun |
| [McLaren Vale Natives](https://www.mclarenvalenatives.com) | Domain parked/redirects to ww17 (dead site); Saturday-morning retail only per Landscape SA list |
| [Melaleuca Nursery (Inverloch)](https://www.melaleucanursery.com.au) | Site timed out repeatedly; could not verify (search mentions a 'New Online Store') |
| [Mildura Native Nursery](https://nativegrowth.com.au/mildura-native-nursery) | URL now redirects to The Native Shop (Wimmera Native Nursery); covered there |
| [Misty Ridge Plant Farm](https://www.mistyridgeplantfarm.com) | No prices or shop on Wix site (Wundowie WA) |
| [Mitre 10 (AU)](https://www.mitre10.com.au) | Could not verify: site returns 403 to fetches and search found only NZ plant listings. |
| [Mount Barker Community Nursery / Second Nature](https://www.secondnature.org.au/mount-barker-community-nursery) | Community nursery open Thursdays, no plant prices; Squarespace shop has a single 'Coming Soon' native plant pack ($10) |
| [Mullum Creek Native Nursery](https://mcnativenursery.com.au/) | placeholder site |
| [Muru Mittigar](https://www.murumittigar.com.au/shop/) | online store 'launching soon'; no prices |
| [Native Instinct (nativeplantsonline.com.au)](https://nativeplantsonline.com.au/) | old static site, no prices; seeds/tubestock by order, Bermagui |
| [Native Spirit Nursery](https://nativespiritnursery.com.au) | GoDaddy shop shows no products/prices (banner: 'NO SHIPPING ORDERS - PICKUP AND LOCAL DELIVERY ORDERS ONLY'; normally 'we send to all states, except Tas'). Ind… |
| [Natives 'R' Us](https://nativesrus.com.au) | QLD (Traveston). 227-plant directory with WooCommerce cart, but no plant prices shown (only gift cards); cash on pickup. |
| [Natural Area Nursery](https://naturalarea.com.au/perth-native-nursery/) | No prices or shop found (Malaga WA, revegetation/wholesale focus) |
| [Newcastle Wildflower Nursery](https://www.newcastlewildflower.com.au/) | stock list has no prices; no online shop |
| [Nielsen's Native Nursery](https://nielsensnativenursery.com.au) | QLD (Loganholme). Site did not respond (connection failed); no evidence of online prices. |
| [Nuthin' but Natives](https://www.nuthinbutnatives.com.au) | Website renders empty; no prices found (Booleroo Centre SA) |
| [Nuts About Natives](https://nutsaboutnatives.com.au) | Contract wholesale propagation only (Karnup WA); no retail prices |
| [Online Plants NT](https://www.onlineplantsnt.com.au) | Domain unreachable 2026-10-22 (Darwin online tropical/native nursery per enjoy-darwin.com listing) |
| [Outback Pride (Reedy Creek Nursery)](https://www.outbackpride.com.au) | Bush food producer (SA); site unreachable and no evidence of live plants sold online |
| [Ozbreed](https://www.ozbreed.com.au/) | breeder; 'buy plants retail' points to where-to-buy, no direct sales |
| [Paradise Group NT](https://www.paradisegroupnt.com.au/online) | Online page says to purchase plants contact by email or phone; general tropical nursery (Knuckey Lagoon NT) |
| [Paten Park Native Nursery](https://www.ppnn.org.au) | QLD (The Gap, Brisbane). Products page is books/fertiliser; plant stock list PDF, prices not shown on site. |
| [Peninsula Plants](https://www.peninsulaplants.com.au) | Indigenous grower; no online shop or prices seen (local supply/services) |
| [Pete's Hobby Nursery](https://www.peteshobbynursery.com.au) | QLD (Lowood). No prices or shop on Wix site; in-person and Fernvale markets only. |
| [Plant Collective NT](https://plantcollectivent.com.au) | General online plant store (Darwin to Humpty Doo delivery, NT only) with only ~13 products in Natives category, below threshold |
| [Plant Daddy](https://plantdaddy.com.au/) | indoor plants, no natives range |
| [Plantmark](https://www.plantmark.com.au) | Wholesale only (trade registration). |
| [Plantrite](https://www.plantrite.com.au) | Wholesale native nursery, no public prices |
| [Plants Direct Tasmania](https://www.plantsdirecttas.com.au) | Priced Shopify shop but only ~6 native items (roses, herbs, edibles) |
| [Port Macquarie Landcare Nursery](https://landcareportmac.com.au/nursery) | no prices on site |
| [Primal Fruits Perth / Perth Mobile Nursery / All Season Plants WA](https://primalfruits.com.au) | Already tracked by treestock; fruit/edible focus with only a handful of natives (lilly pilly, finger lime), below the natives-range threshold |
| [Provincial Plants and Landscapes](https://plantsandlandscapes.com.au/) | retail price list only behind mailing-list opt-in; no prices on site |
| [QLD council/community nurseries (Redlands IndigiScapes, Coochiemudlo, Noosa Landcare, Friends of GC Botanic Gardens, Bribie, Redcliffe, Florabunda, Crows Nest, Mackay NEC, Gin Gin Landcare, Bundaberg Landcare)](https://npq.org.au/where-to-buy/) | Flat 'tubes from $X' quoted in NPQ directory only; no priced stock list or online ordering on their own sites (several sites unreachable). |
| [Red Centre Enterprises](https://www.red-centre.com.au) | Site unreachable 2026-10-22 (Lower Light SA) |
| [Red Dirt Seeds](https://www.reddirtseeds.com.au) | Mine-site revegetation seed, no prices (Mount Barker WA) |
| [Redbreast Plants](https://redbreastplants.com.au) | Site is a placeholder WordPress 'Hello world' page |
| [ReForest Now](https://www.reforestnow.org.au/) | reforestation charity; tree-planting donations, not plant sales |
| [Regen Nurseries](https://regennurseries.com.au) | Trade only ('We are not a retail nursery'), although tray prices are publicly visible |
| [River Road Nursery](https://www.riverroadnursery.com.au/) | Shopify store has no native range |
| [Rochester Nursery](https://rochesternursery.com.au) | No visible prices; local Echuca/Moama delivery only |
| [Rodney's Plants Plus](https://shop.rodneys.com.au/) | general garden centre; only 13 natives online (below range threshold) |
| [Rosemount Nursery](https://www.rosemountnursery.com.au) | QLD (Sunshine Coast). No prices; delivery Gympie-Brisbane by arrangement. |
| [Ross Evans Garden Centres](https://rossevansgardencentre.com.au/product-category/native-plants/) | QLD (Gold Coast/Brisbane). 31 natives listed with no prices; in-store only. |
| [Sandgroper Seeds (eBay)](https://www.ebay.com/usr/sandgroperseeds) | eBay seller (WA seed), not a standalone retail site; not verified |
| [Seed Shed](https://www.seedshed.com.au) | Commercial reveg seed by enquiry; only a $25/species minimum, no per-item price list (Donnybrook WA) |
| [Seeds West](https://www.seedswest.com.au) | Domain did not resolve (connection failed 2026-10-22) |
| [Seedworld Australia](https://seedworld.com.au/) | website under construction |
| [Silver Banksia Nursery](https://www.silverbanksia.com.au) | Wholesale and trade only (Margate TAS) |
| [Soul-Lee Native Flora](https://soul-lee.org) | QLD (Bundamba). Stock list without prices; by appointment. |
| [South Coast Flora](https://southcoastflora.com.au/) | wholesale propagation nursery, no prices |
| [Southern Flora / Esperance Farm Trees](https://www.southernflora.com.au) | Domains did not resolve 2026-10-22 |
| [State Flora](https://www.stateflora.sa.gov.au) | Website unreachable 2026-10-22 (connection refused); ordering is by phone/email/order form from a catalogue, 'can arrange delivery anywhere in Australia', but… |
| [Sunshine Coast Tubestock Growers](https://sctg.com.au) | QLD (Palmwoods). Wholesale only (Evergreen Connect ordering); ships QLD/NSW/VIC/SA/ACT. |
| [Sunvalley Plant Nursery](http://www.sunvalleyplants.com.au) | Domain does not resolve; appointment-only grafted grevillea grower |
| [Sydney Wildflower Nursery](https://www.sydneywildflowernursery.com.au/) | site under maintenance 2026-10-22; previously did mail order by courier. Recheck. |
| [Tailored Botanical](https://www.tailoredbotanical.com/natives) | Hobart; priced shop ships to TAS/VIC/NSW/ACT/QLD but natives range is ~14 items, almost all out of stock |
| [Tall Trees](https://www.talltrees.com.au) | Wholesale availability list only |
| [Tarrawood Native Nursery](https://www.tarrawood.com.au/) | wholesale (supplies Tucker Bush and retailers) |
| [Territory Exotics & Watergardens](https://www.territoryexoticsandwatergardens.com.au) | Exotics/water plants, no natives range or prices found (NT) |
| [Territory Native Plants](https://www.territorynativeplants.com.au) | No visible prices; buy by booked visit at Millner (Darwin NT); outside Greater Darwin MOQ is a full pallet + freight |
| [The Garden (Dickson ACT)](https://www.thegarden.com.au/) | domain now a marketing agency site |
| [The Wetlands Centre Conservation Nursery](https://www.thewetlandscentre.org.au/nursery-plant-sale/) | Monthly in-person plant sales, no prices online (Bibra Lake WA) |
| [Trees For Life (Westwood Nursery)](https://www.treesforlife.org.au/westwood-nursery) | Plants by order/contact and annual sale; online shop sells books, gifts and empty tubes only (Brooklyn Park SA) |
| [Tubestock Nursery Australia](https://tubestocknursery.com.au) | QLD (Bellmere). Wholesale; site did not respond. |
| [Tucker Bush](https://tuckerbush.com.au) | WA brand; plants only via retailers or Perth-metro Square site (WA agent's region). |
| [Tussock & Thyme Nursery](https://www.tussockandthymenursery.com.au) | Sells at Hobart markets only; no online prices; 'We are not able to post plants' |
| [Understorey-style council/community nurseries (Bayside, Frankston, Bungalook, Edendale, La Trobe Nangak Tamboree, Queenscliff, St Kilda SKINC)](https://gardensforwildlifevictoria.com/indigenous-plant-nurseries/) | No online shops or published prices found in directories; Edendale site blocked (403) |
| [Verdigris Fern Nursery](https://www.verdigris.com.au/) | mail-order fern nursery; stock list is JS and prices could not be verified; native/exotic mix unclear. Recheck by hand |
| [Victorian Native Seed](https://www.victoriannativeseed.com.au) | Business permanently closed; catalogue kept as reference |
| [Virginia Nursery](https://www.virginianursery.com.au) | 189 natives listed but prices hidden: 'Registration is Required to place an Order' (Virginia SA) |
| [WA community/landcare nurseries without priced sites: Kalgoorlie-Boulder Urban Landcare, Geraldton Community Nursery, Drylands Foundation, Katanning Environmental Nursery, Bridgetown Community Landcare, Esperance Native Nursery, Mamabulanjin (Broome), Ardess (Albany), Morande Native Plants, York Bushland Nursery](https://wildflowersocietywa.org.au/grow/western-australian-native-plant-nurseries/) | Walk-in, annual-order or social-media-only nurseries; no online prices (Geraldton: once-a-year surplus sale; Drylands site offline; KBULG page 404) |
| [WA Wildflower Nursery (Wildflower Society, Madeley)](https://wawildflowernursery.org.au) | Website effectively empty; no prices |
| [Wagtail Natives Nursery](https://www.wagtailnativesnursery.com.au/) | no shop or prices; markets and orders by contact |
| [Waikerie Nursery](https://www.waikerienursery.com.au) | Site unreachable 2026-10-22 (Riverland SA) |
| Wallum Nurseries / Mad About Plants / Brush Turkey Enterprises / Corella Native Nursery | QLD wholesale/revegetation growers; no public prices. |
| [Wariapendi Nursery](https://wariapendi.com.au/) | no online shop or prices (only Square gift cards); Colo Vale retail nursery |
| [Weddin-style council nurseries without web prices (Sutherland, Hawkesbury, Randwick)](https://www.sutherlandshire.nsw.gov.au/your-environment/community-nursery) | 403 to fetch / no online shop; walk-in community nurseries |
| [Weeping Grevillea Nursery](https://www.weepers.com.au) | Stocklist (xlsx) shows availability, no prices |
| Western Wildflower Farm (Coorow) | No website found |
| [Wild Mint Acres](https://www.wildmintacres.com.au) | Plant stock page has no prices |
| [Witjuti Grub Bushfoods Nursery](https://witjutigrub.com.au) | QLD bush food nursery; site is an empty directory listing. |
| [Wollemi Natives](https://www.wolleminatives.com) | Listed (Landscape SA list) as 'online orders only', min 50 tubes, Willunga SA; domain does not resolve (ENOTFOUND 2026-10-22) |
| [Zanthorrea Nursery](https://www.zanthorrea.com) | Walk-in only (Maida Vale WA); WooCommerce sells only gift vouchers; only a generic tubestock price ($5.95 each, $5.40 for 9+) on the nursery page, no catalogue |

## Affiliate programs (checked 2026-10-22)

Scanned all 85 homepages for affiliate apps and networks (GoAffPro, UpPromote, Refersion, AffiliateWP, Commission Factory, Awin, Impact, CJ, Partnerize and others), affiliate or ambassador links and text, and common `/affiliate` paths, then web-searched the main shippers.

| Retailer | Finding |
|---|---|
| Mr Fothergill's Seeds | **Real program.** UpPromote installed, live signup at `af.uppromote.com/fothergills-au/register`. Commission not shown (page is JavaScript). Seed only. |
| Plantinspirations | OpenCart's built-in affiliate module is switched on at `/affiliate`, but the standard commission is **0%**. Dormant; would need negotiating. |
| Native Grace | Smile.io loyalty and refer-a-friend for customers. Not an affiliate program. |
| Everyone else (82) | Nothing found. False positives ruled out: Ross Creek ("Made For Impact" web designer), Diggers (Growave wishlist only), Evergreen (`/affiliate` is a 404 page). |

Two nurseries outside the list turned up with programs:

- **Advanced Plants** (advancedplants.com.au): **5% verified**. Sells advanced trees, with an Australian Natives category. Free delivery to Sydney, Gold Coast, Brisbane, Melbourne and Adelaide.
- **The Australian Plant Shop**: UpPromote program linked from the footer, reportedly 10% with a 30-day cookie (not verified). Has 96 native-tagged products, but delivers to metropolitan Sydney only.
