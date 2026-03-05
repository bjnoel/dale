# Nursery Research — 2026-03-05

## Priority Targets (Shopify JSON API — easiest)

### 1. Ross Creek Tropicals (Gympie, QLD)
- URL: https://www.rosscreektropicals.com.au/
- Platform: Shopify
- API: `/products.json?limit=250&page=[N]`
- ~1,065 products, prices + stock status
- Ships: QLD, NSW, ACT, VIC

### 2. Ladybird Nursery (Kallangur, QLD)
- URL: https://www.ladybirdnursery.com.au/
- Platform: Shopify
- API: `/products.json?limit=250&page=[N]`
- 18 categories, broad range
- Ships: QLD, NSW, VIC, ACT

### 3. Fruitopia Nursery (Brisbane/Gold Coast, QLD)
- URL: https://fruitopianursery.com.au/
- Platform: Shopify
- API: `/products.json?limit=250`
- Ships: Brisbane/Gold Coast metro free

## High-Value Targets (custom scraping needed)

### 4. Daleys Fruit Tree Nursery (Kyogle, NSW)
- URL: https://www.daleysfruit.com.au/
- Platform: Custom PHP
- Scrape: `/Plant-List.php` (consolidated list with exact stock quantities)
- Largest range in Australia
- Has `/pre-purchase.php` for upcoming stock
- robots.txt: blocks specific bots but not general crawlers

### 5. Heritage Fruit Trees
- URL: https://www.heritagefruittrees.com.au/
- Platform: BigCommerce
- Scrape: `/fruit-trees/?page=[N]`, 24/page, ~309 items
- robots.txt: 10s crawl delay for AI bots (ClaudeBot, GPTBot etc.)
- SEASONAL: bare-root only March-August
- Does NOT ship to WA or Tasmania

## Difficult / Lower Priority

### 6. Heaven on Earth Fruit Trees (FNQ)
- URL: https://www.heavenonearthfruittrees.com.au/
- Platform: Wix (JS-rendered SPA)
- Requires headless browser (Playwright/Puppeteer)
- ~60+ varieties, smaller catalogue
- Does NOT ship to WA or Tasmania

## Dropped

### Exotica Rare Fruits Nursery
- Tell him he's dreaming — this is a California nursery, not Australian.

## Additional (needs investigation)
- Fruit Tree Cottage (Sunshine Coast) — fruittreecottage.com.au
- El Arish Tropical Exotics (Mission Beach FNQ) — elarishtropicalexotics.com
- Forever Seeds (Far North NSW) — Shopify, likely has JSON API
- Tropical Planet Nursery (Kingston QLD) — tropicalplanetnursery.com

## WA Shipping Note
Most east coast nurseries do NOT ship to WA (quarantine restrictions).
Daleys is the main exception. This is actually a huge value-add for Track B:
WA collectors especially need to know who ships to them and when.
Need to ask Benedict about WA-specific nurseries.
