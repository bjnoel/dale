"""
build_compare_pages must not abandon a page it stops writing.

Found 2026-08-20 while checking the DEC-309 reciprocal-link invariant in
production: 116 species pages linked to a compare page but 117 compare files
existed. The extra was /compare/chinese-bayberry-prices.html, last written
2026-08-11, still live, still ranking at position 9.5, serving nine-day-old
prices. Chinese Bayberry had dropped below MIN_NURSERIES and the builder simply
moved on. That is the same failure build_species_state_pages had before the page
ledger (never deletes, so a page below its threshold freezes forever), so it gets
the same fix rather than a second mechanism.

One thing differs from the other two families and it drives the whole design:
a compare page has a guaranteed-live parent. Every enabled species has a
/species/<slug>.html, so a compare page that stops being generated has an
obvious successor and its terminal state is REDIRECT, not TOMBSTONE. decide_night
stays family-agnostic; build_compare_pages does the substitution.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import build_compare_pages as bcp  # noqa: E402
from stocklib.page_ledger import (  # noqa: E402
    FAMILY_COMPARE, LIVE, REDIRECT, PageLedger,
)


def product(title, price=29.95):
    return {
        "title": title, "url": f"https://example.test/{title.lower().replace(' ', '-')}",
        "category": "Fruit Trees", "min_price": price, "any_available": True,
        "variants": [{"title": "140mm", "price": price, "available": True}],
    }


def _row(nk="daleys"):
    return {"nursery_key": nk, "nursery_name": nk.title(), "title": "Mango - Bowen",
            "price": 29.95, "available": True, "url": "https://example.test/m"}


def _established(ledger, slug, *, days=10):
    """A page with enough history to clear the entry guard (7 live days, 7 span)."""
    for d in range(1, days + 1):
        ledger.observe(slug, today=f"2026-08-{d:02d}", rows=[_row()],
                       species_name=slug.replace("-", " ").title())


class CompareLifecycleUnitTests(unittest.TestCase):
    """run_lifecycle directly, so the guards can be driven past without waiting."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.compare = self.root / "compare"
        self.species = self.root / "species"
        self.compare.mkdir(parents=True)
        self.species.mkdir(parents=True)
        self.ledger_path = self.root / "compare.json"

        # Ten established pages. Nine are written tonight, so the global floor
        # (85%) passes and only the tenth is classified.
        led = PageLedger.load(self.ledger_path, FAMILY_COMPARE)
        self.slugs = [f"species-{i}" for i in range(9)] + ["chinese-bayberry"]
        for slug in self.slugs:
            _established(led, slug)
            (self.compare / f"{slug}-prices.html").write_text("<html>old</html>")
            (self.species / f"{slug}.html").write_text("<html>species</html>")
        led.save(self.ledger_path, "2026-08-10")
        # Reload so `seeding` is False: a ledger with no file behind it cannot
        # classify anything, by design.
        self.ledger = PageLedger.load(self.ledger_path, FAMILY_COMPARE)
        self.assertFalse(self.ledger.seeding)
        self.args = Namespace(ledger=self.ledger_path, dry_run=False, health_dir=None)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, written, today="2026-08-11"):
        bcp.run_lifecycle(self.ledger, self.args, self.compare, self.root,
                          today, set(written))

    def test_exit_guard_holds_the_first_absent_night(self):
        self._run(self.slugs[:9])
        self.assertEqual(self.ledger.pages["chinese-bayberry"]["state"], LIVE)
        self.assertIn("old", (self.compare / "chinese-bayberry-prices.html").read_text())

    def test_second_absent_night_redirects_to_the_species_page(self):
        self._run(self.slugs[:9], today="2026-08-11")
        self._run(self.slugs[:9], today="2026-08-12")
        entry = self.ledger.pages["chinese-bayberry"]
        self.assertEqual(entry["state"], REDIRECT)
        html = (self.compare / "chinese-bayberry-prices.html").read_text()
        self.assertIn('href="/species/chinese-bayberry.html"', html)
        self.assertIn("treestock-page-state", html)

    def test_the_stub_does_not_use_the_variety_rename_wording(self):
        self._run(self.slugs[:9], today="2026-08-11")
        self._run(self.slugs[:9], today="2026-08-12")
        html = (self.compare / "chinese-bayberry-prices.html").read_text()
        # "is now listed as" is the rename copy. Nothing was renamed here: there
        # are simply too few nurseries left to compare.
        self.assertNotIn("is now listed as", html)
        self.assertNotIn("under a single name", html)
        self.assertIn("price comparison has moved", html)

    def test_never_redirects_to_a_species_page_that_is_not_there(self):
        (self.species / "chinese-bayberry.html").unlink()
        self._run(self.slugs[:9], today="2026-08-11")
        self._run(self.slugs[:9], today="2026-08-12")
        entry = self.ledger.pages["chinese-bayberry"]
        self.assertEqual(entry["state"], LIVE, "pointed a live URL at a 404")
        self.assertIn("old", (self.compare / "chinese-bayberry-prices.html").read_text())

    def test_a_page_that_comes_back_overwrites_its_own_stub(self):
        self._run(self.slugs[:9], today="2026-08-11")
        self._run(self.slugs[:9], today="2026-08-12")
        self.assertEqual(self.ledger.pages["chinese-bayberry"]["state"], REDIRECT)
        self.ledger.observe("chinese-bayberry", today="2026-08-13", rows=[_row()])
        self.assertEqual(self.ledger.pages["chinese-bayberry"]["state"], LIVE)

    def test_dry_run_writes_no_stub_and_no_ledger(self):
        self.args.dry_run = True
        before = self.ledger_path.read_bytes()
        self._run(self.slugs[:9], today="2026-08-11")
        self._run(self.slugs[:9], today="2026-08-12")
        self.assertIn("old", (self.compare / "chinese-bayberry-prices.html").read_text())
        self.assertEqual(self.ledger_path.read_bytes(), before)


class CompareLifecycleInertTests(unittest.TestCase):
    """Without --ledger the builder must behave exactly as it did before."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data = root / "data"
        for key in ("daleys", "diacos", "diggers"):
            d = self.data / key
            d.mkdir(parents=True)
            (d / "latest.json").write_text(json.dumps({
                "nursery": key, "nursery_name": key.title(),
                "scraped_at": "2026-08-20T03:12:48",
                "products": [product("Mango - Bowen"), product("Mango - R2E2")],
            }))
        self.out = root / "out"
        (self.out / "compare").mkdir(parents=True)
        # An orphan from an earlier run: no nursery lists it tonight.
        self.orphan = self.out / "compare" / "chinese-bayberry-prices.html"
        self.orphan.write_text("<html>stale</html>")

    def tearDown(self):
        self.tmp.cleanup()

    def _build(self, *extra):
        return subprocess.run(
            [sys.executable, str(SCRAPERS / "build_compare_pages.py"),
             str(self.data), str(self.out), *extra],
            cwd=str(SCRAPERS), capture_output=True, text=True, check=True)

    def test_no_ledger_leaves_the_orphan_alone(self):
        self._build()
        self.assertEqual(self.orphan.read_text(), "<html>stale</html>")

    def test_seeding_creates_an_entry_but_changes_no_page(self):
        ledger_path = Path(self.tmp.name) / "compare.json"
        self._build("--ledger", str(ledger_path), "--seed")
        self.assertTrue(ledger_path.exists())
        data = json.loads(ledger_path.read_text())
        self.assertIn("chinese-bayberry", data["pages"])
        # Seeded entries carry no history, so the entry guard holds them for a
        # week. Nothing may happen to the file on the seeding run.
        self.assertEqual(self.orphan.read_text(), "<html>stale</html>")


if __name__ == "__main__":
    unittest.main()
