"""
Tests for tools/scrapers/build_finger_lime_guide.py (/finger-lime-guide.html).

The page used to be hand-written and every number on it went stale. These pin
the parts that are now computed, especially per-listing "QLD only" handling:
shipping is modelled per nursery, so without it the WA section would offer a
Ladybird listing that Ladybird will only send within Queensland.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fl = _load(SCRAPERS / "build_finger_lime_guide.py")


def listing(nursery, title, price, available=True):
    return {"nursery_key": nursery, "title": title, "price": price,
            "available": available, "url": "", "nursery_name": nursery}


PRODUCTS = [
    listing("daleys", "Finger Lime - Yellow", 39.0),
    listing("daleys", "Finger Lime - Red Champagne", 49.0),
    listing("ladybird", "Finger Lime 'Maleny Red' (QLD Only) - Large", 69.0),
    listing("ross-creek", "Finger lime - Byron Sunrise 5L (QLD ONLY)", 59.9),
    listing("primal-fruits", "Fingerlime Grafted - Judy Everbearing", 150.0),
    listing("fruit-tree-lane", "Alstonville Finger Lime 50mm", 5.7),
    listing("fruitopia", "Finger Lime - Champagne", 59.95, available=False),
]


class FingerLimeContextTests(unittest.TestCase):
    def setUp(self):
        self.ctx = fl.build_context(PRODUCTS)

    def test_counts_only_in_stock_listings(self):
        self.assertEqual(self.ctx["listing_count"], 6)
        self.assertEqual(self.ctx["nursery_count"], 5)
        self.assertNotIn("fruitopia", [r["key"] for r in self.ctx["rows"]])

    def test_qld_only_listings_never_reach_wa(self):
        wa = [w["name"] for w in self.ctx["wa"]]
        self.assertIn("Daleys Fruit Trees", wa)
        self.assertNotIn("Ladybird Nursery", wa)
        self.assertNotIn("Ross Creek Tropicals", wa)

    def test_a_nursery_whose_stock_is_all_qld_only_is_labelled_so(self):
        notes = {r["key"]: r["note"] for r in self.ctx["rows"]}
        self.assertEqual(notes["ladybird"], "QLD only")

    def test_cheapest_and_cheapest_for_wa(self):
        self.assertEqual(self.ctx["cheapest"]["price"], "$5.70")
        self.assertEqual(self.ctx["cheapest_wa"]["nursery"], "Daleys Fruit Trees")
        self.assertEqual(self.ctx["cheapest_wa"]["price"], "$39")

    def test_variety_badges_come_from_stock(self):
        badges = {v["name"]: v["badge"] for v in self.ctx["varieties"]}
        self.assertEqual(badges["Maleny Red"], "In stock at 1 nursery (QLD only)")
        self.assertEqual(badges["Red Champagne"], "In stock at 1 nursery")
        self.assertEqual(badges["Wauchope"], "Not in stock right now")

    def test_pickup_area_does_not_nest_brackets(self):
        self.assertNotIn("((", fl.nursery_label("perrys") + ")")
        self.assertNotIn("(pickup))", fl.nursery_label("perrys"))


class FingerLimePageTests(unittest.TestCase):
    def test_page_has_no_stale_or_banned_copy(self):
        html = fl.build_page(PRODUCTS, "2026-10-15")
        self.assertIn("Live Prices Across 5 Nurseries", html)
        for banned in ("Ships to WA", "130+", "$19.75", "—", "–", "{{", "{%"):
            self.assertNotIn(banned, html)

    def test_no_digest_signup_while_the_flag_is_off(self):
        from stocklib.flags import DIGEST_SIGNUP_ENABLED
        if DIGEST_SIGNUP_ENABLED:
            self.skipTest("digest signup is switched on")
        self.assertNotIn("/api/subscribe", fl.build_page(PRODUCTS, "2026-10-15"))

    def test_empty_stock_still_renders(self):
        html = fl.build_page([], "2026-10-15")
        self.assertIn("Live Prices and Stock", html)
        self.assertIn("None of the nurseries we track have finger limes in stock", html)
        self.assertIn("None of the nurseries with finger limes in stock right now can get one to WA", html)


if __name__ == "__main__":
    unittest.main()
