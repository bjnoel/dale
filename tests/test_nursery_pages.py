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

from build_nursery_pages import (  # noqa: E402
    build_index_page,
    build_nursery_page,
    visible_counts,
)


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
        # Pinned to the fixture's own scrape date: without it these drift into
        # the dormant-nursery labels as wall-clock time passes the staleness cut.
        self.html = build_nursery_page("guildford", snapshot(self.products), {},
                                       today="2026-08-17")

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


class IndexAgreesWithProfileTests(unittest.TestCase):
    """The first fix corrected the profile page and left the index card reading
    the snapshot's pre-filter totals, so /nursery/ and /nursery/guildford.html
    disagreed about the same nursery. Both now go through visible_counts()."""

    def setUp(self):
        self.data = snapshot(
            [product(t) for t in SEED_PACKETS] + [product(t) for t in TREES]
        )

    def test_index_card_shows_filtered_counts(self):
        html = build_index_page({"guildford": self.data}, {}, "2026-08-17")
        self.assertIn("<strong>5</strong> in stock · 5 tracked", html)

    def test_index_card_does_not_show_the_snapshot_totals(self):
        html = build_index_page({"guildford": self.data}, {}, "2026-08-17")
        self.assertNotIn("<strong>10</strong> in stock", html)

    def test_the_two_pages_report_the_same_numbers(self):
        in_stock, total = visible_counts(self.data)
        index = build_index_page({"guildford": self.data}, {}, "2026-08-17")
        profile = build_nursery_page("guildford", self.data, {}, today="2026-08-17")
        self.assertIn(f"<strong>{in_stock}</strong> in stock · {total} tracked", index)
        self.assertIn(f">{in_stock}</div><div class=\"label\">In Stock<", profile)
        self.assertIn(f">{total}</div><div class=\"label\">Products Tracked<", profile)


class DormantNurseryTests(unittest.TestCase):
    """Heritage Fruit Trees closed online sales for 2026 on 2026-08-24 and every
    URL now serves HTTP 503. Until this existed the page went on rendering
    "128 In Stock" with live prices and a working-looking product table, its
    only hint a "Data updated daily" line sitting directly above a date that had
    stopped moving. A stock tracker that cannot say "this is a record, not an
    offer" is worse than no tracker."""

    def setUp(self):
        self.data = snapshot([product(t) for t in TREES],
                             nursery_name="Heritage Fruit Trees",
                             scraped_at="2026-08-23T00:26:29")

    def page(self, today):
        return build_nursery_page("heritage-fruit-trees", self.data, {}, today=today)

    def test_fresh_snapshot_keeps_the_live_wording(self):
        html = self.page("2026-08-24")
        self.assertIn('<div class="label">In Stock<', html)
        self.assertIn("In Stock Now", html)
        self.assertIn("Data updated daily. Last checked:", html)
        self.assertNotIn("Closed for the season", html)

    def test_stale_snapshot_says_closed_for_the_season(self):
        html = self.page("2026-08-30")
        self.assertIn("Closed for the season", html)

    def test_stale_page_never_claims_current_stock(self):
        """The banner alone is not enough: the labels around it have to move
        too, or the page contradicts itself two lines further down."""
        html = self.page("2026-08-30")
        self.assertIn('<div class="label">Last In Stock<', html)
        self.assertIn("Last Recorded In Stock", html)
        self.assertIn("Stock checks paused. Last checked:", html)
        self.assertNotIn("Data updated daily. Last checked:", html)

    def test_known_reason_beats_the_generic_wording(self):
        """We read the reason off their own holding page, so say it. The
        generic line ("we cannot reach them") reads like our fault."""
        html = self.page("2026-08-30")
        self.assertIn("closed online sales for 2026", html)
        self.assertIn("on-farm clearance", html)
        self.assertNotIn("We have not been able to reach", html)

    def test_unknown_reason_falls_back_to_the_generic_wording(self):
        data = snapshot([product(t) for t in TREES],
                        scraped_at="2026-08-23T00:26:29")
        html = build_nursery_page("guildford", data, {}, today="2026-08-30")
        self.assertIn("Closed for the season", html)
        self.assertIn("We have not been able to reach Guildford Garden Centre", html)

    def test_dormancy_outranks_the_low_stock_banner(self):
        """"Only 0% of tracked products are in stock, check back later" is the
        wrong and more alarming story for a nursery that has simply shut."""
        data = snapshot([product(t, available=False) for t in TREES],
                        scraped_at="2026-08-23T00:26:29")
        html = build_nursery_page("heritage-fruit-trees", data, {}, today="2026-08-30")
        self.assertIn("Closed for the season", html)
        self.assertNotIn("Low stock period", html)

    def test_index_card_agrees_with_the_profile_page(self):
        index = build_index_page({"heritage-fruit-trees": self.data}, {}, "2026-08-30")
        self.assertIn("Closed for the season", index)
        self.assertIn("last in stock", index)
        self.assertNotIn("</strong> in stock", index)

    def test_fresh_index_card_is_unchanged(self):
        index = build_index_page({"heritage-fruit-trees": self.data}, {}, "2026-08-24")
        self.assertIn("</strong> in stock", index)
        self.assertNotIn("Closed for the season", index)


class VisibleCountsTests(unittest.TestCase):
    def test_ignores_the_snapshots_own_counts_entirely(self):
        data = snapshot([product(t) for t in TREES],
                        in_stock_count=999, product_count=999)
        self.assertEqual(visible_counts(data), (5, 5))

    def test_empty_snapshot(self):
        self.assertEqual(visible_counts({"products": []}), (0, 0))

    def test_missing_products_key(self):
        self.assertEqual(visible_counts({}), (0, 0))


if __name__ == "__main__":
    unittest.main()
