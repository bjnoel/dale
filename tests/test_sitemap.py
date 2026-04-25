"""
Tests for tools/scrapers/build_sitemap.py -- the sitemap-index builder for
treestock.com.au.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bs = _load(SCRAPERS / "build_sitemap.py")

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _build_fixture(root: Path) -> tuple[Path, Path]:
    """Build a minimal site directory layout. Returns (species_dir, output_dir)."""
    output_dir = root / "output"
    species_dir = output_dir / "species"
    for sub in ("species", "nursery", "compare", "variety"):
        (output_dir / sub).mkdir(parents=True, exist_ok=True)

    # Static + landing pages.
    for f in (
        "index.html", "digest.html", "history.html", "rare.html",
        "sample-digest.html", "guide.html", "finger-lime-guide.html",
        "when-to-plant.html", "companion-planting-guide.html", "advertise.html",
        "buy-fruit-trees-wa.html", "buy-fruit-trees-qld.html",
        "buy-fruit-trees-nsw.html", "buy-fruit-trees-vic.html",
        "buy-fruit-trees-by-species-state.html",
        "buy-mango-trees-wa.html", "buy-fig-trees-vic.html",
    ):
        (output_dir / f).write_text("")

    for sub in ("species", "nursery", "compare", "variety"):
        (output_dir / sub / "index.html").write_text("")

    (species_dir / "mango.html").write_text("")
    (species_dir / "fig.html").write_text("")
    (output_dir / "nursery" / "daleys.html").write_text("")
    (output_dir / "compare" / "mango-prices.html").write_text("")
    (output_dir / "variety" / "r2e2-mango.html").write_text("")
    (output_dir / "variety" / "keitt-mango.html").write_text("")

    # Backdate one variety file to verify mtime-driven lastmod.
    old = time.time() - 60 * 60 * 24 * 30  # ~30 days ago
    os.utime(output_dir / "variety" / "r2e2-mango.html", (old, old))

    return species_dir, output_dir


class SitemapStructureTests(unittest.TestCase):
    """The sitemap.xml is a sitemap *index* with one entry per non-empty section."""

    def test_index_lists_all_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            species_dir, output_dir = _build_fixture(Path(tmp))
            bs.build_sitemap(species_dir, output_dir)
            tree = ET.parse(output_dir / "sitemap.xml")
            root = tree.getroot()
            self.assertTrue(root.tag.endswith("sitemapindex"))
            locs = [el.text for el in root.findall(".//sm:sitemap/sm:loc", NS)]
            for name in ("static", "species", "nursery", "compare", "locations", "variety"):
                self.assertIn(f"https://treestock.com.au/sitemaps/{name}.xml", locs)

    def test_subsitemap_files_exist_and_are_well_formed(self):
        with tempfile.TemporaryDirectory() as tmp:
            species_dir, output_dir = _build_fixture(Path(tmp))
            bs.build_sitemap(species_dir, output_dir)
            for name in ("static", "species", "nursery", "compare", "locations", "variety"):
                sub = output_dir / "sitemaps" / f"{name}.xml"
                self.assertTrue(sub.exists(), f"missing {name}.xml")
                root = ET.parse(sub).getroot()
                self.assertTrue(root.tag.endswith("urlset"))


class SitemapContentTests(unittest.TestCase):
    """Each section sitemap contains the right URLs."""

    def _urls(self, path: Path) -> list[str]:
        root = ET.parse(path).getroot()
        return [el.text for el in root.findall(".//sm:url/sm:loc", NS)]

    def test_variety_sitemap_excludes_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            species_dir, output_dir = _build_fixture(Path(tmp))
            bs.build_sitemap(species_dir, output_dir)
            urls = self._urls(output_dir / "sitemaps" / "variety.xml")
            self.assertNotIn("https://treestock.com.au/variety/index.html", urls)
            self.assertIn("https://treestock.com.au/variety/r2e2-mango.html", urls)
            self.assertIn("https://treestock.com.au/variety/keitt-mango.html", urls)

    def test_locations_sitemap_includes_state_landings_and_combos(self):
        with tempfile.TemporaryDirectory() as tmp:
            species_dir, output_dir = _build_fixture(Path(tmp))
            bs.build_sitemap(species_dir, output_dir)
            urls = self._urls(output_dir / "sitemaps" / "locations.xml")
            self.assertIn("https://treestock.com.au/buy-fruit-trees-wa.html", urls)
            self.assertIn("https://treestock.com.au/buy-mango-trees-wa.html", urls)
            self.assertIn("https://treestock.com.au/buy-fig-trees-vic.html", urls)

    def test_combo_index_appears_exactly_once(self):
        """Regression: buy-fruit-trees-by-species-state.html matches COMBO_PATTERN
        and was previously emitted twice (once via the pattern, once via an
        explicit branch). It must appear exactly once."""
        with tempfile.TemporaryDirectory() as tmp:
            species_dir, output_dir = _build_fixture(Path(tmp))
            bs.build_sitemap(species_dir, output_dir)
            urls = self._urls(output_dir / "sitemaps" / "locations.xml")
            target = "https://treestock.com.au/buy-fruit-trees-by-species-state.html"
            self.assertEqual(urls.count(target), 1, f"expected 1 occurrence, got {urls.count(target)}")

    def test_state_landing_pages_excluded_from_combo_set(self):
        """The four state landing pages must appear only once each (in their
        STATE_LANDING_PAGES role), not duplicated by the combo glob."""
        with tempfile.TemporaryDirectory() as tmp:
            species_dir, output_dir = _build_fixture(Path(tmp))
            bs.build_sitemap(species_dir, output_dir)
            urls = self._urls(output_dir / "sitemaps" / "locations.xml")
            for state in ("wa", "qld", "nsw", "vic"):
                target = f"https://treestock.com.au/buy-fruit-trees-{state}.html"
                self.assertEqual(urls.count(target), 1)


class LastmodTests(unittest.TestCase):
    """<lastmod> reflects each file's mtime, not a blanket today's-date stamp."""

    def test_lastmod_uses_file_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            species_dir, output_dir = _build_fixture(Path(tmp))
            bs.build_sitemap(species_dir, output_dir)
            root = ET.parse(output_dir / "sitemaps" / "variety.xml").getroot()
            urls = root.findall(".//sm:url", NS)
            today = bs._today()
            old_lastmod = None
            new_lastmod = None
            for url in urls:
                loc = url.find("sm:loc", NS).text
                lastmod = url.find("sm:lastmod", NS).text
                if loc.endswith("/r2e2-mango.html"):
                    old_lastmod = lastmod
                if loc.endswith("/keitt-mango.html"):
                    new_lastmod = lastmod
            self.assertIsNotNone(old_lastmod)
            self.assertIsNotNone(new_lastmod)
            self.assertNotEqual(old_lastmod, today, "backdated file should not show today")
            self.assertEqual(new_lastmod, today, "freshly-created file should show today")


if __name__ == "__main__":
    unittest.main()
