"""
Species pages must not offer an Alerts link that goes nowhere.

Found while mapping the alert surfaces rather than reported: every species page
emitted a bell reading "Alerts" on out-of-stock rows it could not parse into a
cultivar, pointing at #subscribeBox. DEC-294 set DIGEST_SIGNUP_ENABLED to
false, which stopped that anchor being rendered, so the link had been dead on
every species page since.

The golden fixture has no unparseable out-of-stock row, which is exactly why
the dead link survived a golden suite: this builds one on purpose.

There is no replacement destination and the fix is not to invent one. Species
pages do not load dashboard.js, so there is no inline watch control to redirect
to, and a row that does not name a cultivar has no /variety/ page by
definition.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"


def product(title, available, price=29.95):
    return {
        "nursery": "somenursery", "nursery_name": "Some Nursery",
        "title": title, "url": f"https://example.test/{title.lower().replace(' ', '-')}",
        "category": "Fruit Trees", "min_price": price,
        "any_available": available,
        "variants": [{"title": "140mm", "price": price, "available": available}],
    }


class SpeciesAlertLinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        data = root / "data" / "somenursery"
        data.mkdir(parents=True)
        (data / "latest.json").write_text(json.dumps({
            "nursery": "somenursery", "nursery_name": "Some Nursery",
            "scraped_at": "2026-03-05T03:12:48",
            "products": [
                # Out of stock and NOT parseable into a cultivar: a bare
                # species name. This is the row that used to carry the dead
                # bell.
                product("Mango", False),
                # Out of stock and parseable: keeps its link, to a real page.
                product("Mango - R2E2", False),
                # In stock: no link either way.
                product("Mango - Bowen", True),
            ],
        }))
        self.out = root / "out"
        subprocess.run(
            [sys.executable, str(SCRAPERS / "build_species_pages.py"),
             str(root / "data"), str(self.out)],
            cwd=str(SCRAPERS), capture_output=True, text=True, check=False)
        page = self.out / "species" / "mango.html"
        self.html = page.read_text() if page.exists() else ""

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_page_was_built(self):
        self.assertTrue(self.html, "no species page produced")

    def test_no_link_points_at_the_anchor_that_stopped_being_rendered(self):
        self.assertNotIn("#subscribeBox", self.html)

    def test_a_parseable_out_of_stock_row_keeps_its_alert_link(self):
        """Dropping the dead one must not take the working one with it."""
        self.assertIn("/variety/mango-r2e2.html#watchSection", self.html)

    def test_the_alert_link_names_both_triggers(self):
        """One watch fires on both, and the tooltip promised only restocks."""
        self.assertIn("back in stock or drops in price", self.html)


if __name__ == "__main__":
    unittest.main()
