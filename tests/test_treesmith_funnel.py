"""
Tests for the treestock -> Treesmith funnel surfaces (DAL-219, DAL-222).

The funnel audit (DAL-218) found /treesmith.html taking 12 unique visitors a
month out of treestock's 2,865, with the 225/month homepage contributing none of
them because it carried no CTA at all. These tests pin the two fixes so a later
refactor cannot quietly remove them:

  * the homepage and category landing pages carry a Treesmith promo block, and
    it stays BELOW the results (treestock rule 1: nothing above the results);
  * every promo context deep-links only to /treesmith.html (hub and spoke) and
    tags a distinct utm_content so Plausible can attribute per surface;
  * /treesmith.html uses the vendors' official store badge artwork, links the
    AU App Store storefront rather than /us/, and carries the trademark
    attribution those badges require.

The goldens also cover this markup, but a golden only fails until someone
regenerates it. These assertions state the intent.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from golden_runner import run_builder  # noqa: E402
from treestock_layout import render_treesmith_promo  # noqa: E402

STATIC = SCRAPERS / "static" / "treesmith"


class PromoBlockTest(unittest.TestCase):
    CONTEXTS = ["homepage", "landing", "species", "variety", "rootstock"]

    def test_every_context_links_only_to_the_hub(self):
        """Hub and spoke: promo blocks never link straight to treesmith.app."""
        for context in self.CONTEXTS:
            with self.subTest(context=context):
                html = render_treesmith_promo(context)
                self.assertIn("/treesmith.html?", html)
                self.assertNotIn("treesmith.app", html)

    def test_utm_content_is_distinct_per_context(self):
        """Attribution: each surface is separable in Plausible."""
        seen = {}
        for context in self.CONTEXTS:
            html = render_treesmith_promo(context)
            self.assertIn(f"utm_content={context}", html)
            seen[context] = html
        self.assertEqual(len(set(seen.values())), len(self.CONTEXTS))

    def test_copy_rules(self):
        """No em dashes, and Pro is never described as a subscription."""
        for context in self.CONTEXTS:
            with self.subTest(context=context):
                html = render_treesmith_promo(context)
                self.assertNotIn("\u2014", html)
                self.assertNotIn("subscription", html.lower())


class HomepagePromoTest(unittest.TestCase):
    """The DAL-219 fix, asserted against the actually-built pages."""

    @classmethod
    def setUpClass(cls):
        cls.home = run_builder(
            "build-dashboard.py",
            ["{DATA}", "{OUT}"],
            ["index.html"],
        )["index.html"]
        cls.landing = run_builder(
            "build-dashboard.py",
            ["{DATA}", "{OUT}", "--category", "bush_tucker"],
            ["index.html"],
        )["index.html"]

    def test_homepage_has_the_promo(self):
        self.assertIn("Track your collection with Treesmith", self.home)
        self.assertIn("utm_content=homepage", self.home)

    def test_landing_page_has_the_promo(self):
        self.assertIn("Track your collection with Treesmith", self.landing)
        self.assertIn("utm_content=landing", self.landing)

    def test_promo_sits_below_the_results(self):
        """treestock rule 1. Also below the subscribe block, which stays primary."""
        for name, html in (("homepage", self.home), ("landing", self.landing)):
            with self.subTest(page=name):
                results = html.index('<div id="results">')
                subscribe = html.index('id="subscribeForm"')
                promo = html.index("Track your collection with Treesmith")
                self.assertLess(results, promo)
                self.assertLess(subscribe, promo)

    def test_promo_is_inside_main(self):
        for name, html in (("homepage", self.home), ("landing", self.landing)):
            with self.subTest(page=name):
                promo = html.index("Track your collection with Treesmith")
                self.assertLess(promo, html.index("</main>"))


class TreesmithPageBadgeTest(unittest.TestCase):
    """The DAL-222 fix."""

    @classmethod
    def setUpClass(cls):
        cls.html = run_builder(
            "build_treesmith_page.py", ["{OUT}"], ["treesmith.html"]
        )["treesmith.html"]

    def test_badge_assets_are_committed(self):
        """The page references them by path, so they must ship with it."""
        for name in ("app-store-badge.svg", "google-play-badge.png"):
            with self.subTest(asset=name):
                self.assertTrue((STATIC / name).is_file(), f"missing static/treesmith/{name}")

    def test_hero_uses_the_official_badge_images(self):
        self.assertIn("/treesmith/app-store-badge.svg", self.html)
        self.assertIn("/treesmith/google-play-badge.png", self.html)
        # The plain text buttons the badges replaced are gone.
        self.assertNotIn(">\n        Get it on iOS\n", self.html)
        self.assertNotIn(">\n        Get it on Android\n", self.html)

    def test_badges_are_sized_to_prevent_layout_shift(self):
        for asset in ("app-store-badge.svg", "google-play-badge.png"):
            with self.subTest(asset=asset):
                tag = self.html[self.html.index(asset):]
                tag = tag[:tag.index(">")]
                self.assertIn("width=", tag)
                self.assertIn("height=", tag)
                self.assertIn("alt=", self.html[self.html.index(asset) - 200:])

    def test_ios_link_uses_the_au_storefront(self):
        self.assertIn("apps.apple.com/au/app/", self.html)
        self.assertNotIn("apps.apple.com/us/", self.html)

    def test_trademark_attribution_present(self):
        """Required by both vendors once their badge artwork is used."""
        self.assertIn("trademarks of Apple Inc.", self.html)
        self.assertIn("trademarks of Google LLC", self.html)

    def test_exactly_one_main_landmark(self):
        """render_page already wraps the body; the template must not add a second."""
        self.assertEqual(self.html.count("<main"), 1)
        self.assertEqual(self.html.count("</main>"), 1)

    def test_store_links_keep_utm_tags(self):
        self.assertIn("utm_source=treestock", self.html)
        self.assertIn("utm_medium=treesmith_page", self.html)


if __name__ == "__main__":
    unittest.main()
