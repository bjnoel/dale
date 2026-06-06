"""
Tests for stocklib.layout.render_head (bound to the treestock config via
treestock_layout.render_head).

These pin the PR2 contract: Open Graph + Twitter Card tags are emitted on every
page with sensible fallbacks, the robots meta and JSON-LD hooks only appear when
asked for, and the older call style (no twitter/robots/jsonld kwargs) still works.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from treestock_layout import render_head, render_page, SITE_URL

DEFAULT_OG_IMAGE = f"{SITE_URL}/og-image.png"


class RenderHeadTest(unittest.TestCase):
    def test_defaults_emit_og_and_twitter(self):
        h = render_head(title="My Title", description="My desc")
        self.assertIn('<meta property="og:title" content="My Title">', h)
        self.assertIn('<meta property="og:description" content="My desc">', h)
        self.assertIn('<meta property="og:type" content="website">', h)
        self.assertIn(f'<meta property="og:image" content="{DEFAULT_OG_IMAGE}">', h)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', h)
        self.assertIn('<meta name="twitter:title" content="My Title">', h)
        self.assertIn(f'<meta name="twitter:image" content="{DEFAULT_OG_IMAGE}">', h)
        # No canonical passed -> no og:url
        self.assertNotIn("og:url", h)

    def test_canonical_adds_link_and_og_url(self):
        url = f"{SITE_URL}/variety/hass-avocado.html"
        h = render_head(title="T", canonical_url=url)
        self.assertIn(f'<link rel="canonical" href="{url}">', h)
        self.assertIn(f'<meta property="og:url" content="{url}">', h)

    def test_explicit_og_overrides_fallbacks(self):
        h = render_head(
            title="Page Title",
            description="Page desc",
            og_title="Sharable Title",
            og_description="Sharable desc",
            og_image="https://example.com/custom.png",
            og_type="product",
        )
        self.assertIn('<meta property="og:title" content="Sharable Title">', h)
        self.assertIn('<meta property="og:type" content="product">', h)
        self.assertIn('<meta property="og:image" content="https://example.com/custom.png">', h)
        self.assertIn('<meta name="twitter:title" content="Sharable Title">', h)
        self.assertIn('<meta name="twitter:image" content="https://example.com/custom.png">', h)
        # The plain <title> still uses the title arg, not og_title
        self.assertIn("<title>Page Title</title>", h)

    def test_twitter_can_be_suppressed(self):
        h = render_head(title="T", description="D", twitter_card="")
        self.assertNotIn("twitter:", h)
        # OG still present
        self.assertIn('<meta property="og:title" content="T">', h)

    def test_robots_meta_only_when_set(self):
        self.assertNotIn('name="robots"', render_head(title="T"))
        h = render_head(title="T", robots="noindex, follow")
        self.assertIn('<meta name="robots" content="noindex, follow">', h)

    def test_jsonld_string_and_list(self):
        a = '<script type="application/ld+json">{"@type":"A"}</script>'
        b = '<script type="application/ld+json">{"@type":"B"}</script>'
        h_str = render_head(title="T", jsonld=a)
        self.assertIn(a, h_str)
        h_list = render_head(title="T", jsonld=[a, "", b])
        self.assertIn(a, h_list)
        self.assertIn(b, h_list)
        # Empty entries are skipped (no stray blank script tags from "")
        self.assertEqual(render_head(title="T", jsonld=[]).count("ld+json"), 0)

    def test_no_description_skips_og_description(self):
        h = render_head(title="Only Title")
        self.assertIn('<meta property="og:title" content="Only Title">', h)
        self.assertNotIn("og:description", h)
        self.assertNotIn("twitter:description", h)

    def test_backward_compatible_call(self):
        # The pre-PR2 call style (no twitter/robots/jsonld kwargs) must still work.
        h = render_head(
            title="T",
            description="D",
            canonical_url=f"{SITE_URL}/x.html",
            og_title="OT",
            og_description="OD",
            og_image=DEFAULT_OG_IMAGE,
            og_type="website",
            extra_head="<!-- x -->",
            extra_style="  .x { color: red; }",
        )
        self.assertTrue(h.startswith("<!DOCTYPE html>"))
        self.assertIn("</head>", h)
        self.assertIn("<!-- x -->", h)

    def test_render_page_threads_jsonld(self):
        ld = '<script type="application/ld+json">{"@type":"Z"}</script>'
        page = render_page(title="T", body="<p>hi</p>", jsonld=ld)
        self.assertIn(ld, page)
        self.assertIn("<p>hi</p>", page)


if __name__ == "__main__":
    unittest.main()
