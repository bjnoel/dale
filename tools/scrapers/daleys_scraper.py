#!/usr/bin/env python3
"""
Daleys Fruit Tree Nursery Scraper

Scrapes product data from daleysfruit.com.au, the largest rare fruit nursery
in Australia. Parses both the Plant-List.php (all in-stock products) and
pre-purchase.php (upcoming stock) pages.

Uses only Python standard library. Respectful: single-page fetches, no
rapid-fire requests.

Usage:
  python3 daleys_scraper.py              # Scrape both pages
  python3 daleys_scraper.py --plant-list # Scrape only Plant-List.php
  python3 daleys_scraper.py --pre-purchase # Scrape only pre-purchase.php
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from html.parser import HTMLParser
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "nursery-stock" / "daleys"
BASE_URL = "https://www.daleysfruit.com.au"
USER_AGENT = "WalkthroughBot/1.0 (+https://scion.exchange; stock-monitoring)"
REQUEST_DELAY = 2  # seconds between page fetches


def fetch_html(url):
    """Fetch raw HTML from a URL."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} fetching {url}")
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


# ---------------------------------------------------------------------------
# Plant-List.php parser
# ---------------------------------------------------------------------------

class PlantListParser(HTMLParser):
    """
    Parses the Plant-List.php page. Structure per product row:

      <tr id="R{N}">
        <td>
          <a href="..."><img ...></a>
          <a href="..." id="P{N}">
            <span data="itemName">Plant Name</span>
            [optional: <i><a ...>Postage Included (About)</a></i>]
          </a>
        </td>
        <th><a ...>Size</a></th>   (Small/Medium/Large/XLarge)
        <th>$Price</th>
        <th>StockCount</th>
        <th><input ... name="Qty[SKU]" ...></th>
      </tr>

    Multiple rows can share the same product URL (one row per size variant).
    """

    def __init__(self):
        super().__init__()
        self.rows = []  # list of raw row dicts

        # Parser state
        self._in_product_row = False
        self._current_row = None
        self._cell_index = 0
        self._cell_depth = 0
        self._capture_text = False
        self._text_buf = ""
        self._in_item_name_span = False
        self._current_section = ""

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)

        # Detect product rows: <tr id="R{N}">
        if tag == "tr":
            rid = attr.get("id", "")
            if rid.startswith("R") and rid[1:].isdigit():
                self._in_product_row = True
                self._current_row = {
                    "name": "",
                    "url": "",
                    "size": "",
                    "price": "",
                    "stock": "",
                    "sku": "",
                    "section": self._current_section,
                }
                self._cell_index = 0
            return

        if not self._in_product_row:
            # Track section headers
            if tag == "td":
                cls = attr.get("class", "")
                if "Main-Desc" in cls:
                    self._capture_text = True
                    self._text_buf = ""
            if tag == "h1" and self._capture_text:
                pass  # keep capturing
            return

        # Inside a product row, count cells (td/th)
        if tag in ("td", "th"):
            self._cell_index += 1
            self._cell_depth += 1
            self._text_buf = ""
            self._capture_text = True
            return

        # Links inside cell 1 carry product URL
        if tag == "a" and self._cell_index == 1:
            href = attr.get("href", "")
            if href and not href.endswith("Fruit-Trees-Free-Postage.php"):
                self._current_row["url"] = href

        # <span data="itemName"> carries the plant name
        if tag == "span" and attr.get("data") == "itemName":
            self._in_item_name_span = True
            self._text_buf = ""

        # <input name="Qty[SKU]"> carries the SKU
        if tag == "input" and self._cell_index == 5:
            name = attr.get("name", "")
            m = re.match(r"Qty\[(\d+)\]", name)
            if m:
                self._current_row["sku"] = m.group(1)

    def handle_endtag(self, tag):
        if not self._in_product_row:
            # Section header capture
            if tag == "h1" and self._capture_text:
                self._current_section = self._text_buf.strip()
                self._capture_text = False
                self._text_buf = ""
            if tag == "td" and self._capture_text:
                self._capture_text = False
            return

        if tag == "span" and self._in_item_name_span:
            self._current_row["name"] = self._text_buf.strip()
            self._in_item_name_span = False

        if tag in ("td", "th") and self._cell_depth > 0:
            self._cell_depth -= 1
            text = self._text_buf.strip()

            if self._cell_index == 2:  # Size
                self._current_row["size"] = text
            elif self._cell_index == 3:  # Price
                self._current_row["price"] = text
            elif self._cell_index == 4:  # Stock
                self._current_row["stock"] = text

            self._capture_text = False
            self._text_buf = ""

        if tag == "tr" and self._in_product_row:
            if self._current_row and self._current_row.get("name"):
                self.rows.append(self._current_row)
            self._in_product_row = False
            self._current_row = None
            self._cell_index = 0
            self._cell_depth = 0

    def handle_data(self, data):
        if self._in_item_name_span:
            self._text_buf += data
        elif self._capture_text:
            self._text_buf += data


def parse_plant_list(html):
    """Parse Plant-List.php HTML into normalized product dicts."""
    parser = PlantListParser()
    parser.feed(html)

    # Group rows by product URL (each size variant = separate row)
    products_by_url = {}
    for row in parser.rows:
        url = row["url"]
        if not url:
            continue

        # Ensure absolute URL
        if url.startswith("/"):
            url = BASE_URL + url
        elif not url.startswith("http"):
            url = BASE_URL + "/" + url

        if url not in products_by_url:
            products_by_url[url] = {
                "nursery": "daleys",
                "nursery_name": "Daleys Fruit Tree Nursery",
                "title": row["name"],
                "url": url,
                "category": row.get("section", ""),
                "variants": [],
            }

        # Parse price
        price_str = row["price"].replace("$", "").replace(",", "").strip()
        try:
            price = float(price_str)
        except (ValueError, TypeError):
            price = None

        # Parse stock count
        stock_str = row["stock"].strip()
        try:
            stock_count = int(stock_str)
        except (ValueError, TypeError):
            stock_count = 0

        sku = row.get("sku", "")

        products_by_url[url]["variants"].append({
            "title": row["size"] if row["size"] else "Default",
            "price": price,
            "available": stock_count > 0,
            "stock_count": stock_count,
            "sku": sku,
        })

    # Compute summary fields
    products = []
    for p in products_by_url.values():
        prices = [v["price"] for v in p["variants"] if v["price"] is not None]
        p["min_price"] = min(prices) if prices else None
        p["max_price"] = max(prices) if prices else None
        p["any_available"] = any(v["available"] for v in p["variants"])
        p["total_stock"] = sum(v["stock_count"] for v in p["variants"])
        products.append(p)

    return products


# ---------------------------------------------------------------------------
# pre-purchase.php parser
# ---------------------------------------------------------------------------

def parse_pre_purchase(html):
    """
    Parse pre-purchase.php HTML using regex on data attributes.

    Each product card has rich data-product-ecommerce-* attributes:
      data-product-ecommerce-name="..."
      data-product-ecommerce-price="..."
      data-product-ecommerce-quantity="..."
      data-product-ecommerce-id="..."
      data-product-ecommerce-category="..."
      data-product-ecommerce-category2="..."

    Product URLs come from <a data-product="name" href="...">.
    Availability is in <td> after data-offer="availability" row.
    Pot size is in <span data-offer-short-name="...">value</span>.
    """
    products_by_url = {}

    # Split into product cards
    cards = html.split('daley-product-card">')
    if len(cards) < 2:
        return []

    for card_html in cards[1:]:
        # Extract product name link: <a data-product="name" href="..." data-product-ecommerce-name="..." ...>
        name_match = re.search(
            r'<a\s+data-product="name"\s+href="([^"]*)"'
            r'[^>]*data-product-ecommerce-name="([^"]*)"'
            r'[^>]*data-product-ecommerce-price="([^"]*)"'
            r'[^>]*data-product-ecommerce-quantity="([^"]*)"'
            r'[^>]*data-product-ecommerce-category2="([^"]*)"',
            card_html
        )
        if not name_match:
            continue

        url = name_match.group(1)
        name = name_match.group(2)
        category2 = name_match.group(5)

        # Ensure absolute URL
        if url.startswith("/"):
            url = BASE_URL + url
        elif not url.startswith("http"):
            url = BASE_URL + "/" + url

        # Extract all offer/variant data from data-offer-cell="price" cells
        # Each offer cell: <span data-product-ecommerce-variant="..." data-product-ecommerce-price="..." data-product-ecommerce-quantity="...">price</span>
        offer_pattern = re.compile(
            r'data-offer-cell="price"[^>]*>\$<span'
            r'[^>]*data-product-offer_id="([^"]*)"'
            r'[^>]*data-product-ecommerce-variant="([^"]*)"'
            r'[^>]*data-product-ecommerce-price="([^"]*)"'
            r'[^>]*data-product-ecommerce-quantity="([^"]*)"'
            r'[^>]*>([^<]*)</span>'
        )

        variants = []
        for om in offer_pattern.finditer(card_html):
            offer_id = om.group(1)
            variant_id = om.group(2)
            price_str = om.group(3)
            quantity_str = om.group(4)

            try:
                price = float(price_str)
            except (ValueError, TypeError):
                price = None

            try:
                quantity = int(quantity_str)
            except (ValueError, TypeError):
                quantity = 0

            # Find availability for this variant
            # Look for availability text near this offer's section
            avail_text = ""
            # Check for Sold Out or Pre Order near this offer_id
            offer_section = card_html[om.start():om.start() + 5000]
            avail_match = re.search(
                r'data-offer="availability".*?<td[^>]*><span>(.*?)</span></td>',
                offer_section, re.DOTALL
            )
            if avail_match:
                avail_text = re.sub(r'<[^>]+>', ' ', avail_match.group(1)).strip()

            # Find pot volume for this variant
            pot_vol = ""
            pot_match = re.search(
                r'data-offer="potVolume".*?data-offer-short-name="[^"]*">([^<]*)</span>',
                offer_section, re.DOTALL
            )
            if pot_match:
                pot_vol = pot_match.group(1).strip()

            is_available = "Sold Out" not in avail_text
            is_pre_order = "Pre Order" in avail_text

            variant_title = pot_vol if pot_vol else f"Variant {variant_id}"

            variants.append({
                "title": variant_title,
                "price": price,
                "available": is_available,
                "stock_count": quantity if is_available else 0,
                "sku": offer_id,
                "pre_order": is_pre_order,
                "availability_text": avail_text,
            })

        if not variants:
            continue

        prices = [v["price"] for v in variants if v["price"] is not None]
        product = {
            "nursery": "daleys",
            "nursery_name": "Daleys Fruit Tree Nursery",
            "title": name,
            "url": url,
            "category": category2,
            "variants": variants,
            "min_price": min(prices) if prices else None,
            "max_price": max(prices) if prices else None,
            "any_available": any(v["available"] for v in variants),
            "total_stock": sum(v["stock_count"] for v in variants),
            "pre_purchase": True,
        }
        products_by_url[url] = product

    return list(products_by_url.values())


# ---------------------------------------------------------------------------
# Output and main
# ---------------------------------------------------------------------------

def save_snapshot(products, pre_purchase_products):
    """Save a dated snapshot of the scrape results."""
    today = date.today().isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Merge products: tag source
    all_products = []
    for p in products:
        p["source"] = "plant_list"
        p["pre_purchase"] = False
        all_products.append(p)
    for p in pre_purchase_products:
        p["source"] = "pre_purchase"
        all_products.append(p)

    in_stock = sum(1 for p in all_products if p["any_available"])
    out_of_stock = sum(1 for p in all_products if not p["any_available"])

    snapshot = {
        "nursery": "daleys",
        "nursery_name": "Daleys Fruit Tree Nursery",
        "scraped_at": datetime.now().isoformat(),
        "product_count": len(all_products),
        "in_stock_count": in_stock,
        "out_of_stock_count": out_of_stock,
        "plant_list_count": len(products),
        "pre_purchase_count": len(pre_purchase_products),
        "products": all_products,
    }

    snapshot_file = DATA_DIR / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    # Also save latest.json for easy access
    latest_file = DATA_DIR / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"\nSaved: {snapshot_file}")
    print(f"Saved: {latest_file}")
    return snapshot_file


def print_summary(products, pre_purchase_products):
    """Print summary of scrape results."""
    print("\n" + "=" * 60)
    print("DALEYS FRUIT TREE NURSERY - SCRAPE SUMMARY")
    print("=" * 60)

    # Plant List summary
    in_stock = sum(1 for p in products if p["any_available"])
    total_variants = sum(len(p["variants"]) for p in products)
    total_stock_units = sum(p["total_stock"] for p in products)
    print(f"\nPlant List (in-stock catalogue):")
    print(f"  Products:       {len(products)}")
    print(f"  Size variants:  {total_variants}")
    print(f"  In stock:       {in_stock}")
    print(f"  Total units:    {total_stock_units}")

    # Categories
    categories = {}
    for p in products:
        cat = p.get("category", "Uncategorised")
        if cat not in categories:
            categories[cat] = 0
        categories[cat] += 1
    if categories:
        print(f"  Categories:")
        for cat, count in sorted(categories.items()):
            print(f"    {cat}: {count}")

    # Price ranges
    all_prices = [p["min_price"] for p in products if p["min_price"] is not None]
    if all_prices:
        print(f"  Price range:    ${min(all_prices):.2f} - ${max(all_prices):.2f}")

    # Pre-purchase summary
    print(f"\nPre-Purchase (upcoming stock):")
    print(f"  Products:       {len(pre_purchase_products)}")
    pp_available = sum(1 for p in pre_purchase_products if p["any_available"])
    pp_sold_out = len(pre_purchase_products) - pp_available
    print(f"  Available:      {pp_available}")
    print(f"  Sold out:       {pp_sold_out}")

    # Highlight some rare/interesting finds
    rare_keywords = [
        "jaboticaba", "rollinia", "sapodilla", "sapote", "grumichama",
        "miracle fruit", "ice cream bean", "eugenia", "syzygium",
        "annona", "cherimoya", "soursop", "custard apple", "dragon fruit",
        "pitaya", "mangosteen", "rambutan", "longan", "lychee",
        "jackfruit", "durian", "cacao", "coffee", "vanilla",
        "fig", "mulberry", "pomegranate", "guava", "feijoa",
        "passionfruit", "tamarind", "carambola", "starfruit",
        "abiu", "achacha", "black sapote", "canistel", "mamey",
        "wampee", "kwai muk", "che", "jujube",
    ]

    print(f"\nNotable rare fruit in stock:")
    shown = 0
    for p in products:
        if not p["any_available"]:
            continue
        title_lower = p["title"].lower()
        for kw in rare_keywords:
            if kw in title_lower:
                price_str = f"${p['min_price']:.2f}" if p["min_price"] else "?"
                stock = p["total_stock"]
                print(f"  {p['title']:40s} {price_str:>10s}  ({stock} in stock)")
                shown += 1
                break
        if shown >= 20:
            print("  ... (showing top 20)")
            break

    print(f"\nTotal combined: {len(products) + len(pre_purchase_products)} products")
    print("=" * 60)


def main():
    do_plant_list = True
    do_pre_purchase = True

    if len(sys.argv) > 1:
        if sys.argv[1] == "--plant-list":
            do_pre_purchase = False
        elif sys.argv[1] == "--pre-purchase":
            do_plant_list = False
        elif sys.argv[1] in ("-h", "--help"):
            print(__doc__)
            return

    products = []
    pre_purchase_products = []

    if do_plant_list:
        print("Fetching Plant-List.php (full catalogue)...")
        html = fetch_html(f"{BASE_URL}/Plant-List.php")
        if html:
            print(f"  Received {len(html):,} bytes")
            products = parse_plant_list(html)
            print(f"  Parsed {len(products)} products")
        else:
            print("  FAILED to fetch Plant-List.php")

    if do_pre_purchase:
        if do_plant_list:
            print(f"\nWaiting {REQUEST_DELAY}s before next request...")
            time.sleep(REQUEST_DELAY)

        print("Fetching pre-purchase.php (upcoming stock)...")
        html = fetch_html(f"{BASE_URL}/pre-purchase.php")
        if html:
            print(f"  Received {len(html):,} bytes")
            pre_purchase_products = parse_pre_purchase(html)
            print(f"  Parsed {len(pre_purchase_products)} products")
        else:
            print("  FAILED to fetch pre-purchase.php")

    if products or pre_purchase_products:
        save_snapshot(products, pre_purchase_products)
        print_summary(products, pre_purchase_products)
    else:
        print("\nNo data scraped. Check errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
