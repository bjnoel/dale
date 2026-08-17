"""
Regression tests for build_nursery_pages.build_nursery_page.

The bug (found 2026-08-17, by the nursery owner, on her own page): every other
builder on the site runs products through stocklib.classify.is_real_product
before rendering them, but this one did not. Guildford Garden Centre loaded an
Eden Seeds vegetable range in August 2026, the WooCommerce Store API returns
newest first, and the builder took the first 20 in-stock products verbatim. The
result was 19 seed packets (carrot, cabbage, kohl rabi) and one blueberry in the
"In Stock Now" panel of a fruit tree site.

The counts were wrong in the same direction and for the same reason: they were
read from the snapshot's pre-filter in_stock_count/product_count, so the page
advertised seed packets in its "In Stock" and "Products Tracked" figures too.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from build_nursery_pages import build_nursery_page  # noqa: E402


def product(title, available=True, price=12.0, url="https://example.com/p"):
    return {
        "title": title,
        "any_available": available,
        "min_price": price,
        "url": url,
        "variants": [],
    }


# The real order from Guildford's snapshot on 2026-08-17: the seed range the
# store returned first, then the first genuine tree behind it.
SEED_PACKETS = [
    "Watermelon – Sugar Baby – Eden Seeds",
    "Silverbeet – Ruby Red Chard – Eden Seeds",
    "Cauliflower – All Year Round – Eden Seeds",
    "Carrot – Baby (Amsterdam) – Eden Seeds",
    "Kohl Rabi – Purple Vienna – Eden Seeds",
]
TREES = [
    "Blueberry – Premier",
    "Apricot Multi Graft – Glengarry/Newcastle",
    "Mango – Florigon – Grafted",
    "Pomegranate – Wonderful",
    "Pistachio – Sirora – Male",
]


def snapshot(products, **overrides):
    data = {
        "nursery_name": "Guildford Garden Centre",
        "location": "Guildford, WA",
        "scraped_at": "2026-08-17T00:17:23.261213",
        "products": products,
        # Deliberately pre-filter, exactly as the scraper writes them.
        "product_count": len(products),
        "in_stock_count": sum(1 for p in products if p.get("any_available")),
    }
    data.update(overrides)
    return data


class NurseryPageJunkFilterTests(unittest.TestCase):
    def setUp(self):
        self.products = [product(t) for t in SEED_PACKETS] + [product(t) for t in TREES]
        self.html = build_nursery_page("guildford", snapshot(self.products), {})

    def test_seed_packets_never_reach_the_page(self):
        for title in SEED_PACKETS:
            self.assertNotIn(
                title.split(" – ")[0], self.html,
                f"{title!r} is a vegetable seed packet and must not render on a "
                "fruit tree nursery page",
            )

    def test_real_trees_still_render(self):
        for title in TREES:
            self.assertIn(title.split(" – ")[0], self.html)

    def test_seed_packets_would_otherwise_have_taken_every_slot(self):
        """Pins the ordering that caused the bug: unfiltered, the junk is first."""
        unfiltered = [p for p in self.products if p.get("any_available")][:5]
        self.assertTrue(
            all("Eden Seeds" in p["title"] for p in unfiltered),
            "fixture no longer reproduces the store's newest-first ordering",
        )

    def test_counts_are_derived_after_filtering_not_from_the_snapshot(self):
        # 10 products in, 5 of them junk. The snapshot says 10/10; the page
        # must say 5/5.
        self.assertIn(">5</div><div class=\"label\">In Stock<", self.html)
        self.assertIn(">5</div><div class=\"label\">Products Tracked<", self.html)

    def test_out_of_stock_junk_is_excluded_from_the_tracked_count(self):
        products = [product(t, available=False) for t in SEED_PACKETS]
        products += [product(t) for t in TREES]
        html = build_nursery_page("guildford", snapshot(products), {})
        self.assertIn(">5</div><div class=\"label\">Products Tracked<", html)

    def test_a_nursery_of_pure_junk_renders_without_dividing_by_zero(self):
        html = build_nursery_page(
            "guildford", snapshot([product(t) for t in SEED_PACKETS]), {}
        )
        self.assertIn(">0</div><div class=\"label\">Products Tracked<", html)


if __name__ == "__main__":
    unittest.main()
