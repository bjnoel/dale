"""
Tests for stocklib.structured_data (BreadcrumbList / Organization / WebSite
JSON-LD) and the treestock_layout bindings, including render_breadcrumb now
emitting BreadcrumbList alongside the nav.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib import structured_data as sd
from treestock_layout import (
    render_breadcrumb, organization_jsonld, website_jsonld, SITE_URL,
)

DASH = ("—", "–")  # em dash, en dash (CLAUDE.md copy rule)


def parse_jsonld(script: str) -> dict:
    m = re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', script, re.S)
    assert m, f"no ld+json script found in: {script!r}"
    return json.loads(m.group(1))


class BreadcrumbTest(unittest.TestCase):
    CRUMBS = [("Home", "/"), ("Varieties", "/variety/"), ("Hass Avocado", "")]

    def test_parses_and_typed(self):
        data = parse_jsonld(sd.breadcrumb_jsonld(self.CRUMBS, SITE_URL))
        self.assertEqual(data["@type"], "BreadcrumbList")
        self.assertEqual(len(data["itemListElement"]), 3)

    def test_positions_and_absolute_urls(self):
        data = parse_jsonld(sd.breadcrumb_jsonld(self.CRUMBS, SITE_URL))
        items = data["itemListElement"]
        self.assertEqual([it["position"] for it in items], [1, 2, 3])
        self.assertEqual(items[0]["item"], f"{SITE_URL}/")
        self.assertEqual(items[1]["item"], f"{SITE_URL}/variety/")
        # Last (current page) crumb has empty url -> no "item"
        self.assertNotIn("item", items[2])
        self.assertEqual(items[2]["name"], "Hass Avocado")

    def test_absolute_url_passthrough(self):
        data = parse_jsonld(sd.breadcrumb_jsonld([("X", "https://other.test/x")], SITE_URL))
        self.assertEqual(data["itemListElement"][0]["item"], "https://other.test/x")

    def test_render_breadcrumb_includes_nav_and_jsonld(self):
        out = render_breadcrumb(self.CRUMBS)
        self.assertIn("<nav", out)
        self.assertIn('application/ld+json', out)
        self.assertEqual(parse_jsonld(out)["@type"], "BreadcrumbList")


class LinklessMiddleCrumbTest(unittest.TestCase):
    """Regression: Search Console "Missing field 'item' (in 'itemListElement')".

    Google requires "item" on every crumb EXCEPT the last one. build_variety_pages
    passes an empty url for the species crumb when that species has no species page
    (grandfathered non-fruit varieties), which produced a middle ListItem with no
    "item" and a dead <a href=""> in the nav. Such a crumb is dropped from both.
    """
    # Home > Varieties > Begonia (no species page) > Bewitched Red Black
    CRUMBS = [("Home", "/"), ("Varieties", "/variety/"), ("Begonia", ""),
              ("Bewitched Red Black", "")]

    def test_every_non_last_item_has_item(self):
        items = parse_jsonld(sd.breadcrumb_jsonld(self.CRUMBS, SITE_URL))["itemListElement"]
        for it in items[:-1]:
            self.assertIn("item", it, f"crumb {it['name']!r} is missing 'item'")

    def test_linkless_middle_crumb_dropped_and_positions_renumbered(self):
        items = parse_jsonld(sd.breadcrumb_jsonld(self.CRUMBS, SITE_URL))["itemListElement"]
        self.assertEqual([it["name"] for it in items],
                         ["Home", "Varieties", "Bewitched Red Black"])
        self.assertEqual([it["position"] for it in items], [1, 2, 3])
        self.assertNotIn("item", items[-1])

    def test_trailing_linkless_crumb_still_kept(self):
        """The last crumb legitimately has no url; only middles are dropped."""
        items = parse_jsonld(sd.breadcrumb_jsonld(
            [("Home", "/"), ("Varieties", "/variety/"), ("Hass", "")], SITE_URL,
        ))["itemListElement"]
        self.assertEqual([it["name"] for it in items], ["Home", "Varieties", "Hass"])

    def test_nav_has_no_empty_href_and_matches_jsonld(self):
        out = render_breadcrumb(self.CRUMBS)
        nav = re.search(r"<nav.*?</nav>", out, re.S).group(0)
        self.assertNotIn('href=""', nav)
        self.assertNotIn("Begonia", nav)
        # Visible trail and the markup must agree (Google's breadcrumb guidance)
        names = [it["name"] for it in parse_jsonld(out)["itemListElement"]]
        for name in names:
            self.assertIn(name, nav)


class OrganizationWebsiteTest(unittest.TestCase):
    def test_organization(self):
        data = parse_jsonld(organization_jsonld())
        self.assertEqual(data["@type"], "Organization")
        self.assertEqual(data["url"], f"{SITE_URL}/")
        self.assertTrue(data["logo"].startswith("https://"))
        self.assertIn("https://bjnoel.com", data["sameAs"])

    def test_website_has_no_searchaction(self):
        data = parse_jsonld(website_jsonld())
        self.assertEqual(data["@type"], "WebSite")
        self.assertEqual(data["url"], f"{SITE_URL}/")
        # SearchAction omitted until a working ?q= endpoint exists
        self.assertNotIn("potentialAction", data)


class CopyRuleTest(unittest.TestCase):
    def test_no_em_or_en_dashes(self):
        blobs = [
            sd.breadcrumb_jsonld([("Home", "/"), ("Now", "")], SITE_URL),
            organization_jsonld(),
            website_jsonld(),
        ]
        for blob in blobs:
            for d in DASH:
                self.assertNotIn(d, blob)


if __name__ == "__main__":
    unittest.main()
