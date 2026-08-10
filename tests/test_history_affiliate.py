"""Affiliate tagging on the /history.html timeline.

The history page renders its links in client-side JS from a JSON blob embedded
by build_history.py. That JS must never carry its own copy of AFFILIATE_REFS, so
the URLs are tagged in Python before serialisation.

This needs its own test because the golden fixture for `history` has no dated
snapshots at all (it pins the empty-timeline page), so test_golden.py exercises
none of this code path. Without this file the tagging could silently regress and
every test would still pass.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from build_history import build_history_data  # noqa: E402


def _snapshot(nursery: str, name: str, url: str, price: float, available: bool) -> dict:
    return {
        "nursery": nursery,
        "nursery_name": name,
        "scraped_at": "2026-08-09T05:00:00",
        "products": [{
            "nursery": nursery,
            "nursery_name": name,
            "title": "Fig - Black Genoa",
            "url": url,
            "variants": [{"title": "Pot", "price": price, "available": available}],
            "min_price": price,
            "max_price": price,
            "any_available": available,
        }],
    }


class HistoryAffiliateTest(unittest.TestCase):
    """One affiliate nursery and one non-affiliate nursery, both with a price
    drop, so a single build covers both the tagged and untagged branches."""

    PRIMAL_URL = "https://primalfruits.com.au/p/fig-black-genoa"
    # Ross Creek rather than Daleys: Daleys' FRUIT_FILTERS entry is
    # mode="categories" with include_prefixes, so an uncategorised fixture
    # product is dropped by the digest filter before it ever reaches the
    # affiliate code (the DEC-207/209 leaf-category gap). Ross Creek is
    # mode="all", which keeps this test about affiliate tagging.
    ROSS_CREEK_URL = "https://rosscreektropicals.com.au/p/fig-black-genoa"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for key, name, url in (
            ("primal-fruits", "Primal Fruits Perth", self.PRIMAL_URL),
            ("ross-creek", "Ross Creek Tropicals", self.ROSS_CREEK_URL),
        ):
            d = self.tmp / key
            d.mkdir(parents=True)
            # Two dated snapshots with a price change, so compare_snapshots
            # produces a price_drops entry carrying the product url.
            (d / "2026-08-08.json").write_text(
                json.dumps(_snapshot(key, name, url, 40.0, True)))
            (d / "2026-08-09.json").write_text(
                json.dumps(_snapshot(key, name, url, 30.0, True)))

    def _urls(self):
        found = {}
        for day in build_history_data(self.tmp):
            for nursery in day["nurseries"]:
                for items in nursery["changes"].values():
                    for item in items:
                        if item.get("url"):
                            found[nursery["key"]] = item["url"]
        return found

    def test_affiliate_nursery_url_carries_ref(self):
        urls = self._urls()
        self.assertIn("primal-fruits", urls,
                      "fixture produced no primal-fruits change; test is not exercising anything")
        self.assertEqual(urls["primal-fruits"], f"{self.PRIMAL_URL}?ref=treestock")

    def test_non_affiliate_nursery_url_untouched(self):
        urls = self._urls()
        self.assertIn("ross-creek", urls,
                      "fixture produced no ross-creek change; test is not exercising anything")
        self.assertEqual(urls["ross-creek"], self.ROSS_CREEK_URL)


if __name__ == "__main__":
    unittest.main()
