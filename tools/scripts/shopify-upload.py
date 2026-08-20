#!/usr/bin/env python3
"""Upload Leeming Fruit Trees products to Shopify dev store."""

import json
import base64
import urllib.request
import urllib.error
import time
import sys
import os

SHOP = "leeming-fruit-trees.myshopify.com"
def _token():
    """Admin API token from the environment, or the gitignored local .env.

    Never inline it here. This file is untracked but sits in a TRACKED
    directory, so a broad `git add -A` sweeps it into a commit. That has now
    happened twice, and the second time only GitHub push protection stopped a
    live token reaching a public repo. Failing loudly is the point: a silent
    fallback is what made the literal survive here in the first place.
    """
    token = os.environ.get("SHOPIFY_ADMIN_API")
    if token:
        return token
    env_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
    try:
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip().startswith("SHOPIFY_ADMIN_API="):
                    return line.strip().split("=", 1)[1]
    except FileNotFoundError:
        pass
    sys.exit(
        "SHOPIFY_ADMIN_API is not set.\n"
        "  export SHOPIFY_ADMIN_API=shpat_...   or put it in the repo's .env"
    )


TOKEN = _token()
API = f"https://{SHOP}/admin/api/2024-01"

PRODUCTS = [
    {
        "title": "Grafted Starfruit (Thai Knight)",
        "body_html": "<p>Grafted starfruit plants, approximately 1 metre tall. Thai Knight is a sweet, self-fertile variety with bright orange fruit. Carambolas are refreshing and juicy, excellent fresh or juiced.</p><p>The tree has an attractive weeping habit and produces a profusion of pink flowers. Thai Knight is a medium-sized fruit with excellent flavour, a great choice if you're not sure which starfruit to pick.</p><p><strong>Size:</strong> ~1m tall<br><strong>Type:</strong> Grafted<br><strong>Pickup:</strong> Canning Vale</p>",
        "price": "60.00",
        "sku": "LFT-STARFRUIT-THAIKNIGHT",
        "tags": ["starfruit", "carambola", "grafted", "tropical"],
        "image": "2-starfruit.jpg",
        "quantity": 5
    },
    {
        "title": "Achacha (Bolivian Mangosteen)",
        "body_html": "<p>Achacha (Garcinia humilis), also known as Bolivian Mangosteen. Highly prized and cultivated for centuries in the tropical Amazon Basin of Bolivia.</p><p>The fruit is delicious, refreshing, exotic, tangy, and effervescent with a fine balance between sweetness and acidity. Similar appeal to mangosteen, longan, rambutan, and lychee. The name Achacha translates as \"honey kiss.\"</p><p>Can be grown and will fruit in a large container (100L pot).</p><p><strong>Pickup:</strong> Canning Vale</p>",
        "price": "40.00",
        "sku": "LFT-ACHACHA",
        "tags": ["achacha", "mangosteen", "tropical", "rare fruit"],
        "image": "3-achacha.jpg",
        "quantity": 5
    },
    {
        "title": "Marcotted Kohala Longan (Chompoo / Haew)",
        "body_html": "<p>Marcotted Kohala longan plants (also known as Chompoo or Haew variety), approximately 1.2 to 1.5 metres tall. Should start fruiting within a year.</p><p>Produces thick, sweet, and crispy flesh with a beautiful aroma. A premium longan variety highly sought after by fruit collectors.</p><p><strong>Size:</strong> 1.2-1.5m tall<br><strong>Type:</strong> Marcotted (air-layered)<br><strong>Pickup:</strong> Canning Vale</p>",
        "price": "80.00",
        "sku": "LFT-LONGAN-KOHALA",
        "tags": ["longan", "tropical", "rare fruit", "marcotted"],
        "image": "4-chompoo.jpg",
        "quantity": 5
    },
    {
        "title": "Grafted Giant Jala Avocado",
        "body_html": "<p>Grafted Giant Jala Avocado, a new Australian variety. This supersized avocado is big on size and huge on flavour.</p><p>Features a lovely glossy skin that's relatively easy to peel. The flesh is rich, nutty, and doesn't brown as easily as other varieties, staying greener for longer. One Jala is enough to make a full batch of quality buttery guacamole for the family.</p><p><strong>Type:</strong> Grafted<br><strong>Pickup:</strong> Canning Vale</p>",
        "price": "95.00",
        "sku": "LFT-AVOCADO-JALA",
        "tags": ["avocado", "grafted", "rare fruit", "australian variety"],
        "image": "5-jala.jpg",
        "quantity": 5
    },
    {
        "title": "Grafted Royal Crimson Cherry",
        "body_html": "<p>Grafted Royal Crimson cherry plants, approximately 1.8 to 2 metres tall in 30-litre pots. A very sweet black cherry variety.</p><p>Low chill variety, meaning it doesn't need very cold winters to fruit. Performs well in Perth's climate. Self-fertile, so it doesn't need another variety for cross-pollination.</p><p><strong>Size:</strong> 1.8-2m tall, in 30L pots<br><strong>Type:</strong> Grafted, low chill, self-fertile<br><strong>Pickup:</strong> Canning Vale</p>",
        "price": "95.00",
        "sku": "LFT-CHERRY-ROYALCRIMSON",
        "tags": ["cherry", "grafted", "low chill", "self-fertile"],
        "image": "6-cherry.jpg",
        "quantity": 5
    },
    {
        "title": "Dwarf Red Dacca Banana",
        "body_html": "<p>Dwarf Red Dacca Banana, a stunning heirloom variety with deep maroon skin and creamy, sweet flesh. The flavour is richer than common Cavendish bananas, with subtle berry-like notes.</p><p>Vigorous, productive, and very ornamental in the garden. Perfect for anyone who loves rare tropical fruit and something truly different.</p><p><strong>Pickup:</strong> Canning Vale</p>",
        "price": "30.00",
        "sku": "LFT-BANANA-REDDACCA",
        "tags": ["banana", "tropical", "heirloom", "rare fruit"],
        "image": "7-dacca.jpg",
        "quantity": 5
    },
    {
        "title": "Graviola Soursop",
        "body_html": "<p>Graviola (soursop) plants. Soursop produces large, green, spiny fruit with creamy white flesh that has a unique sweet-tart flavour, often described as a combination of strawberry and pineapple with creamy citrus notes.</p><p>A tropical favourite prized for both its delicious fruit and its ornamental value.</p><p><strong>Pickup:</strong> Canning Vale</p>",
        "price": "45.00",
        "sku": "LFT-SOURSOP",
        "tags": ["soursop", "graviola", "tropical", "rare fruit"],
        "image": "8-soursop.jpg",
        "quantity": 5
    },
    {
        "title": "Sunshine Special Passionfruit",
        "body_html": "<p>Sunshine Special Passionfruit (Passiflora edulis). A delicious and highly productive variety known for its sweet, aromatic pulp and excellent flavour.</p><p>Produces beautiful purple fruits packed with juicy golden pulp, perfect for desserts, juices, smoothies, or simply eaten fresh. This vigorous vine grows well in Perth conditions and rewards growers with heavy crops once established.</p><p>Give it a sunny spot, a strong trellis, and good drainage, and it will thrive.</p><p><strong>Pickup:</strong> Canning Vale</p>",
        "price": "20.00",
        "sku": "LFT-PASSIONFRUIT-SUNSHINE",
        "tags": ["passionfruit", "vine", "tropical"],
        "image": "9-sunshine.jpg",
        "quantity": 10
    },
    {
        "title": "Grafted Pomelo (Red and White)",
        "body_html": "<p>Grafted pomelo plants, available in red and white varieties. Pomelos are the largest of all citrus fruits, with sweet, mild flesh that's less acidic than grapefruit.</p><p>A beautiful and productive tree for Perth gardens.</p><p><strong>Type:</strong> Grafted<br><strong>Varieties:</strong> Red, White<br><strong>Pickup:</strong> Canning Vale</p>",
        "price": "25.00",
        "sku": "LFT-POMELO",
        "tags": ["pomelo", "citrus", "grafted"],
        "image": "10-pomelo.jpg",
        "quantity": 10
    },
    {
        "title": "Grafted Japanese Seedless Mandarin",
        "body_html": "<p>Grafted Japanese Seedless Mandarin plants, approximately 60cm tall. Produces very sweet, medium to large seedless fruit.</p><p>An easy-to-grow citrus that does well in Perth's climate. Perfect for home gardens and container growing.</p><p><strong>Size:</strong> ~60cm tall<br><strong>Type:</strong> Grafted, seedless<br><strong>Pickup:</strong> Canning Vale</p>",
        "price": "20.00",
        "sku": "LFT-MANDARIN-JAPANESE",
        "tags": ["mandarin", "citrus", "grafted", "seedless"],
        "image": "11-mandarin.jpg",
        "quantity": 10
    },
    {
        "title": "Sapodilla (Chiku)",
        "body_html": "<p>Sapodilla (Chiku) plants, approximately 40cm tall. A tropical fruit native to Central America, known for its very sweet, caramel-like flavour and grainy, pear-like texture.</p><p>Typically eaten fresh after ripening, where the soft brown flesh is scooped out with a spoon. Also used in desserts, smoothies, and jams.</p><p><strong>Size:</strong> ~40cm tall<br><strong>Pickup:</strong> Canning Vale</p>",
        "price": "40.00",
        "sku": "LFT-SAPODILLA",
        "tags": ["sapodilla", "chiku", "tropical", "rare fruit"],
        "image": "12-sapodilla.jpg",
        "quantity": 5
    }
]

def api_call(method, endpoint, data=None):
    url = f"{API}{endpoint}"
    headers = {
        "X-Shopify-Access-Token": TOKEN,
        "Content-Type": "application/json"
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"  ERROR: {e.code} - {err}", file=sys.stderr)
        return None

def upload_image(product_id, image_path):
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    data = {
        "image": {
            "attachment": img_b64,
            "filename": os.path.basename(image_path)
        }
    }
    return api_call("POST", f"/products/{product_id}/images.json", data)

def main():
    """Create every product in PRODUCTS on the store.

    Guarded, because this WRITES. It used to run at import time, and on
    2026-08-20 two throwaway imports (checking where the token came from,
    of all things) created 15 duplicate products on the live dev store
    before anyone noticed. Importing a module must never cost 11 API writes.
    """
    img_dir = os.path.expanduser("~/Desktop/leeming")

    for i, prod in enumerate(PRODUCTS):
        print(f"[{i+1}/{len(PRODUCTS)}] Creating: {prod['title']}...", end=" ", flush=True)

        product_data = {
            "product": {
                "title": prod["title"],
                "body_html": prod["body_html"],
                "vendor": "Leeming Fruit Trees",
                "product_type": "Fruit Trees",
                "tags": prod["tags"],
                "variants": [{
                    "price": prod["price"],
                    "sku": prod["sku"],
                    "inventory_management": "shopify",
                    "inventory_quantity": prod["quantity"],
                    "requires_shipping": False
                }]
            }
        }

        result = api_call("POST", "/products.json", product_data)
        if not result:
            print("FAILED")
            continue

        product_id = result["product"]["id"]
        print(f"OK (ID: {product_id})", end="", flush=True)

        # Upload image
        img_path = os.path.join(img_dir, prod["image"])
        if os.path.exists(img_path):
            print(" | Uploading image...", end=" ", flush=True)
            img_result = upload_image(product_id, img_path)
            if img_result:
                print("OK")
            else:
                print("FAILED")
        else:
            print(f" | Image not found: {prod['image']}")

        # Small delay to avoid rate limits
        time.sleep(0.5)

    print("\nDone! All products created.")


if __name__ == "__main__":
    main()
