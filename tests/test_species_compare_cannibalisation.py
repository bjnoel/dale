"""
The species page and the compare page must not compete for the same query.

Measured 2026-08-20 over 90 days of GSC: 414 queries across 27 species returned
BOTH /species/<slug>.html and /compare/<slug>-prices.html, and Google alternated
between them rather than settling on one. Those contested queries converted at
1.57%, below both parents (/species/ 1.71%, /compare/ 2.27%). On 8 of the top 16
species neither page reached the top 15. Worked example, "pecan tree":
/species/pecan.html at position 21.6, /compare/pecan-prices.html at 14.5.

The collision was self-inflicted at three levels, and this guards all three:

  1. The species <title> literally read "... Trees for Sale Australia, Compare
     Prices", bidding for the compare page's own keyword.
  2. Both pages emitted a schema.org Product named "<Name> Tree" against two
     different URLs, with near word-for-word descriptions.
  3. The compare page linked to the species page, but never the reverse, so
     internal link equity ran one way between two competing pages.

Test 3 asserts the invariant rather than a hand-picked species: a species page
links to its compare page if and only if that compare page was actually built.
build_species_pages runs BEFORE build_compare_pages in run-all-scrapers.sh and
so cannot see the file, it re-derives the rule from COMPARE_MIN_NURSERIES. If
that threshold ever moves, this fails instead of shipping broken links.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"


def product(title, price=29.95):
    return {
        "title": title, "url": f"https://example.test/{title.lower().replace(' ', '-')}",
        "category": "Fruit Trees", "min_price": price, "any_available": True,
        "variants": [{"title": "140mm", "price": price, "available": True}],
    }


def _jsonld_product_name(html):
    """The name of the schema.org Product node, or None."""
    for blob in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data.get("name")
    return None


class SpeciesCompareCannibalisationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        # Mango at 3 nurseries clears COMPARE_MIN_NURSERIES; fig at 2 does not.
        stock = {
            "daleys": ["Mango - Bowen", "Mango - R2E2", "Fig - Black Genoa"],
            "diacos": ["Mango - Kensington Pride", "Fig - Brown Turkey"],
            "diggers": ["Mango - Nam Doc Mai"],
        }
        for key, titles in stock.items():
            d = root / "data" / key
            d.mkdir(parents=True)
            (d / "latest.json").write_text(json.dumps({
                "nursery": key, "nursery_name": key.title(),
                "scraped_at": "2026-08-20T03:12:48",
                "products": [product(t) for t in titles],
            }))
        cls.out = root / "out"
        for builder in ("build_species_pages.py", "build_compare_pages.py"):
            subprocess.run(
                [sys.executable, str(SCRAPERS / builder), str(root / "data"), str(cls.out)],
                cwd=str(SCRAPERS), capture_output=True, text=True, check=True)
        cls.species_html = (cls.out / "species" / "mango.html").read_text()
        cls.compare_html = (cls.out / "compare" / "mango-prices.html").read_text()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_species_title_does_not_claim_price_comparison(self):
        title = re.search(r"<title>(.*?)</title>", self.species_html, re.S).group(1)
        self.assertIn("Trees for Sale Australia", title)
        for banned in ("Compare Prices", "Price Comparison", "Compare Price"):
            self.assertNotIn(banned, title,
                             f"species <title> reintroduced comparison wording: {title!r}")

    def test_meta_descriptions_do_not_both_lead_on_comparison(self):
        def meta(html):
            return re.search(r'<meta name="description" content="(.*?)"', html, re.S).group(1)
        # Assert on fig, not mango. Mango has sought varieties in its growing guide
        # and so takes the "Track <variety> and more" branch, which never carried the
        # colliding wording; asserting there would pass vacuously. Fig has none and
        # takes the plain branch, which is the one that read "Compare availability".
        fig = meta((self.out / "species" / "fig.html").read_text())
        self.assertIn("Check availability and shipping options", fig)
        self.assertNotIn("Compare availability", fig)
        # The compare page keeps comparison wording: that is what that page is for.
        self.assertIn("Compare", meta(self.compare_html))

    def test_pages_emit_distinct_product_entities(self):
        sp = _jsonld_product_name(self.species_html)
        cp = _jsonld_product_name(self.compare_html)
        self.assertIsNotNone(sp)
        self.assertIsNotNone(cp)
        self.assertNotEqual(sp, cp,
                            f"both pages emit Product name {sp!r} against different URLs")
        self.assertEqual(sp, "Mango Tree")

    def test_species_links_to_compare_page_iff_it_exists(self):
        species_dir = self.out / "species"
        compare_dir = self.out / "compare"
        checked = 0
        for page in species_dir.glob("*.html"):
            if page.name == "index.html":
                continue
            slug = page.stem
            linked = f'href="/compare/{slug}-prices.html"' in page.read_text()
            exists = (compare_dir / f"{slug}-prices.html").exists()
            self.assertEqual(linked, exists,
                             f"/species/{slug}.html links={linked} but compare page exists={exists}")
            checked += 1
        self.assertGreaterEqual(checked, 2, "fixture should cover a linked and an unlinked species")

    def test_the_fixture_actually_covers_both_arms(self):
        # Guards the test above from passing vacuously if the fixture drifts.
        self.assertTrue((self.out / "compare" / "mango-prices.html").exists())
        self.assertFalse((self.out / "compare" / "fig-prices.html").exists())
        self.assertIn('href="/compare/mango-prices.html"', self.species_html)
        self.assertNotIn("-prices.html", (self.out / "species" / "fig.html").read_text())


if __name__ == "__main__":
    unittest.main()
