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
