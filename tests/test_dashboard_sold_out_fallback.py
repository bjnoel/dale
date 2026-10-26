"""
"In stock only" with nothing in stock shows the sold-out matches, not an empty page.

Every in-stock count on a nursery page links to the homepage pre-filtered, e.g.
/?nursery=fruitopia&species=pomegranate&stock=1. Fruitopia's only pomegranate
sold out on 2026-10-16; Googlebot followed the link on 10-18, got "No plants
found matching your filters." and filed the URL as a soft 404. People following
a day-old nursery page or a bookmark got the same empty page.

Runs static/dashboard.js under node against a stub DOM (tests/dashboard_harness.js).
Skipped when node is not installed.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_JS = REPO_ROOT / "tools" / "scrapers" / "static" / "dashboard.js"
HARNESS = Path(__file__).resolve().parent / "dashboard_harness.js"
NODE = shutil.which("node")


def _product(title, nk, sl, available):
    return {"t": title, "n": nk.title(), "nk": nk, "sl": sl, "a": available,
            "p": 39.95, "cat": "", "vs": f"{sl}-{title.split()[-1].lower()}"}


DATA = {
    "products": [
        _product("Pomegranate Wonderful", "fruitopia", "pomegranate", False),
        _product("Pomegranate Ben Hur", "fruitopia", "pomegranate", False),
        _product("Mango R2E2", "fruitopia", "mango", True),
        _product("Pomegranate Elche", "daleys", "pomegranate", True),
    ],
    "nurseries": [
        {"key": "fruitopia", "name": "Fruitopia", "st": ["QLD"], "in_stock": 1},
        {"key": "daleys", "name": "Daleys", "st": ["QLD", "NSW"], "in_stock": 1},
    ],
    "species_slugs": {
        "pomegranate": {"slug": "pomegranate", "name": "Pomegranate"},
        "mango": {"slug": "mango", "name": "Mango"},
    },
    "hard_to_find": [],
}


@unittest.skipUnless(NODE, "node is not installed")
class SoldOutFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name) / "data.json"
        cls.data.write_text(json.dumps(DATA))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def load(self, query):
        out = subprocess.run(
            [NODE, str(HARNESS), str(DASHBOARD_JS), query, str(self.data)],
            capture_output=True, text=True, check=True, timeout=30)
        return json.loads(out.stdout)

    def test_the_url_google_flagged_shows_the_sold_out_listings(self):
        page = self.load("?nursery=fruitopia&species=pomegranate&stock=1")
        self.assertNotIn("No plants found", page["html"])
        self.assertIn("None in stock right now", page["html"])
        self.assertIn("Pomegranate Wonderful", page["html"])
        self.assertIn("Pomegranate Ben Hur", page["html"])
        self.assertEqual(page["count"], "0 in stock, 2 sold out")

    def test_the_fallback_keeps_the_other_filters(self):
        """Relaxing stock must not relax nursery or species too."""
        page = self.load("?nursery=fruitopia&species=pomegranate&stock=1")
        self.assertNotIn("Pomegranate Elche", page["html"])  # other nursery
        self.assertNotIn("Mango R2E2", page["html"])  # other species

    def test_stock_stays_in_the_url_so_the_view_tightens_when_stock_returns(self):
        page = self.load("?nursery=fruitopia&species=pomegranate&stock=1")
        self.assertIn("stock=1", page["url"])

    def test_no_notice_when_something_is_in_stock(self):
        page = self.load("?nursery=fruitopia&species=mango&stock=1")
        self.assertNotIn("None in stock right now", page["html"])
        self.assertIn("Mango R2E2", page["html"])
        self.assertEqual(page["count"], "1 result")

    def test_genuinely_empty_filters_still_say_so(self):
        """Nothing at all matches (sold out or not), so there is nothing to
        fall back to. A species filter fills the search box with its name, so
        this is the "No results found for Mango" branch."""
        page = self.load("?nursery=daleys&species=mango&stock=1")
        self.assertIn("clear the filters", page["html"])
        self.assertNotIn("None in stock right now", page["html"])
        self.assertEqual(page["count"], "0 results")


if __name__ == "__main__":
    unittest.main()
