"""
A hand-written page that skips treestock_layout.py also skips the analytics tag,
and a page with no analytics tag reports 0 pageviews forever.

/wa-rare-fruit-guide.html was live for 51 days, listed in the sitemap and linked
from the homepage, with no Plausible script on it. It recorded 0 pageviews for
its entire life, and DAL-176's premise cited it as a page that lifts subscribe
conversion. A zero and an absence of measurement look identical in Plausible
(DEC-249), so nothing about the number said it was not real.

Pages built through treestock_layout.py get the tag injected. Pages in
tools/scrapers/static/ are copied to the web root verbatim by deploy.sh, so they
are the only public pages where the tag has to be typed by hand. This asserts
they carry it, and forces a new one to declare itself either public (tagged and
in the sitemap) or deliberately untracked.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
STATIC_DIR = SCRAPERS / "static"

# The one substring that proves the page talks to our Plausible instance. Match
# the script src rather than the bare hostname: the preconnect and dns-prefetch
# hints also carry data.bjnoel.com and neither of them records anything.
ANALYTICS_SRC = "data.bjnoel.com/js/script"

# Static pages that must NOT be sent to analytics, with the reason. Their URLs
# carry HMAC tokens, and a pageview would put a working token in an analytics
# path we do not control (DEC-249).
TOKEN_BEARING = {
    "manage.html": "URL carries a subscriber HMAC token",
    "stop-watching.html": "URL carries a watch HMAC token",
}

# Static pages that are deliberately not public. Not in the sitemap, not linked,
# so a missing tag is correct rather than an oversight.
NOT_PUBLIC = {
    "advertise.html": "suppressed 2026-06-15, Benedict declined paid placement twice",
    "helena.html": "one-off shared by link, never in the sitemap",
}


def _load_build_sitemap():
    spec = importlib.util.spec_from_file_location(
        "build_sitemap", SCRAPERS / "build_sitemap.py"
    )
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.path.insert(0, str(SCRAPERS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRAPERS))
    return module


build_sitemap = _load_build_sitemap()

SITEMAP_LISTED = {
    path
    for path, _freq, _prio in build_sitemap.STATIC_PAGES + build_sitemap.STATE_LANDING_PAGES
    if path.endswith(".html")
}


class StaticPageInstrumentationTests(unittest.TestCase):
    def setUp(self):
        self.pages = sorted(p for p in STATIC_DIR.glob("*.html"))
        self.assertTrue(self.pages, "no static HTML found; has the layout moved?")

    def test_every_sitemap_listed_static_page_carries_the_analytics_tag(self):
        listed = [p for p in self.pages if p.name in SITEMAP_LISTED]
        self.assertTrue(
            listed,
            "no static page is sitemap-listed any more; delete this test if that is intended",
        )
        for page in listed:
            with self.subTest(page=page.name):
                self.assertIn(
                    ANALYTICS_SRC,
                    page.read_text(),
                    f"{page.name} is in build_sitemap.STATIC_PAGES but has no Plausible "
                    "script, so it will report 0 pageviews whatever its real traffic is",
                )

    def test_every_static_page_is_either_instrumented_or_explained(self):
        """A new hand-written page should not be able to arrive untracked by default."""
        for page in self.pages:
            with self.subTest(page=page.name):
                if ANALYTICS_SRC in page.read_text():
                    continue
                reason = TOKEN_BEARING.get(page.name) or NOT_PUBLIC.get(page.name)
                self.assertIsNotNone(
                    reason,
                    f"{page.name} carries no analytics tag and is not listed as "
                    "token-bearing or non-public. Add the tag, or add it to "
                    "TOKEN_BEARING / NOT_PUBLIC in this test with a reason.",
                )

    def test_token_bearing_pages_are_not_sent_to_analytics(self):
        """The exemption runs both ways: tagging these would leak a live token."""
        for name in TOKEN_BEARING:
            page = STATIC_DIR / name
            with self.subTest(page=name):
                self.assertTrue(page.exists(), f"{name} has moved; update TOKEN_BEARING")
                self.assertNotIn(ANALYTICS_SRC, page.read_text())
                self.assertNotIn(name, SITEMAP_LISTED)


if __name__ == "__main__":
    unittest.main()
