"""Search must not call a closed nursery's frozen stock current.

Aus Nurseries put its whole Shopify store behind a holiday password page on
2026-09-20 ("our online store will reopen on 20 October 2026"). The scraper
failed cleanly, latest.json kept the 09-19 catalogue, and the nursery page
correctly said "Closed for the season". Search did not: on 2026-09-23 data.js
still listed 190 of its 447 products as in stock, "Apple Jonathon $40" among
them, each one linking to the password page.
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

_spec = importlib.util.spec_from_file_location("build_dashboard", SCRAPERS / "build-dashboard.py")
build_dashboard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_dashboard)


def product(title, available=True):
    return {
        "title": title,
        "url": f"https://example.test/products/{title.lower().replace(' ', '-')}",
        "available": available,
        "min_price": 40.0,
        "variants": [{"sku": title, "price": 40.0, "available": available}],
    }


class WithdrawStaleStockTests(unittest.TestCase):
    def test_every_offer_claim_is_removed(self):
        row = {"t": "Apple Jonathon", "a": True, "p": 40.0, "s": 3,
               "pre": "presale", "ch": "back", "pp": 45.0}
        build_dashboard.withdraw_stale_stock([row])
        self.assertEqual(row, {"t": "Apple Jonathon", "a": False, "p": 40.0})


class LoaderDormancyTests(unittest.TestCase):
    """End to end through load_nursery_data, the function that feeds data.js."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, key, name, scraped_at):
        d = self.data_dir / key
        d.mkdir()
        (d / "latest.json").write_text(json.dumps({
            "nursery": key, "nursery_name": name, "scraped_at": scraped_at,
            "products": [product("Apple Jonathon"), product("Plum Santa Rosa"),
                         product("Pear Williams", available=False)],
        }))

    def load(self):
        products, nurseries, _ = build_dashboard.load_nursery_data(self.data_dir)
        return products, {n["key"]: n for n in nurseries}

    def test_closed_nursery_shows_nothing_in_stock(self):
        self.write("ausnurseries", "Aus Nurseries", "2026-09-19T00:02:00")
        products, nurseries = self.load()
        rows = [p for p in products if p["nk"] == "ausnurseries"]
        self.assertEqual(len(rows), 3, "the rows stay searchable as a record")
        self.assertFalse(any(p["a"] for p in rows))
        self.assertEqual(nurseries["ausnurseries"]["in_stock"], 0)

    def test_a_fresh_scrape_is_left_alone(self):
        """The self-clearing half: the night their store answers again, search
        goes back to reading the snapshot as live. The dormant_note alone must
        never hold stock down."""
        now = datetime.now(timezone.utc).isoformat()
        self.write("ausnurseries", "Aus Nurseries", now)
        _, nurseries = self.load()
        self.assertEqual(nurseries["ausnurseries"]["in_stock"], 2)


if __name__ == "__main__":
    unittest.main()
