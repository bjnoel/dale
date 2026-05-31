"""
Tests for tools/scrapers/build_companion_guide.py -- the evidence-graded
companion planting guide builder for treestock.com.au.

Run from repo root with:
    python3 -m unittest discover tests/

These pin the invariants that keep the page honest and link-safe:
  - every companion/avoidance claim carries a valid evidence grade,
  - internal /species/ links only point at slugs that actually have a page
    (prevents 404 drift, the CLAUDE.md slug-drift rule),
  - source URLs are well formed, external links use rel="noopener",
  - copy has no em or en dashes (CLAUDE.md copy rule),
  - the fig icon is not the blueberry emoji (regression for a known bug),
  - the FAQ JSON-LD parses and matches the visible FAQs.
"""
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
# build_companion_guide imports treestock_layout, so its dir must be importable.
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bc = _load(SCRAPERS / "build_companion_guide.py")
HTML = bc.build_page()

BLUEBERRY = "\U0001fad0"  # the emoji that was wrongly used for figs
EM_DASH = "—"
EN_DASH = "–"
GOOD_SLUGS = {s["slug"] for s in json.load(open(SCRAPERS / "fruit_species.json"))}
# group anchor slugs that are NOT real /species/ pages and must never be linked
NON_PAGE_GROUP_SLUGS = {"citrus", "stone-fruit", "apple-pear", "tropical"}


class TestCompanionGuide(unittest.TestCase):
    def test_build_page_runs(self):
        self.assertIsInstance(HTML, str)
        self.assertIn("<html", HTML)
        self.assertIn("</html>", HTML)
        self.assertGreater(len(HTML), 2000)

    def test_every_species_has_required_keys(self):
        for sp in bc.SPECIES_COMPANIONS:
            for key in ("name", "slug", "icon", "good", "avoid", "pollinator", "notes"):
                self.assertIn(key, sp, f"{sp.get('slug')} missing {key}")
            self.assertIsInstance(sp["good"], list)
            self.assertIsInstance(sp["avoid"], list)
            self.assertIsInstance(sp.get("species_slugs", []), list)
            self.assertIsInstance(sp.get("sources", []), list)

    def test_every_claim_has_valid_grade(self):
        for sp in bc.SPECIES_COMPANIONS:
            for entry in sp["good"]:
                self.assertEqual(len(entry), 3, f"good entry not a 3-tuple: {entry}")
                self.assertIn(entry[2], bc.EVIDENCE_GRADES, f"bad grade in {sp['slug']}: {entry}")
            for entry in sp["avoid"]:
                self.assertEqual(len(entry), 2, f"avoid entry not a 2-tuple: {entry}")
                self.assertIn(entry[1], bc.EVIDENCE_GRADES, f"bad grade in {sp['slug']}: {entry}")
        for entry in bc.AVOID_ALL:
            self.assertEqual(len(entry), 3)
            self.assertIn(entry[2], bc.EVIDENCE_GRADES)
        for entry in bc.NITROGEN_FIXERS:
            self.assertEqual(len(entry), 3)
            self.assertIn(entry[2], bc.EVIDENCE_GRADES)

    def test_internal_species_links_resolve(self):
        # Every declared species_slug must have a real /species/<slug>.html page.
        for sp in bc.SPECIES_COMPANIONS:
            for s in sp.get("species_slugs", []):
                self.assertIn(s, GOOD_SLUGS, f"{sp['slug']} links to non-existent species page: {s}")
        # The rendered page must never deep-link the group anchor slugs.
        for bad in NON_PAGE_GROUP_SLUGS:
            self.assertNotIn(f'href="/species/{bad}.html"', HTML, f"page links 404 slug: {bad}")
        # And the feature actually renders for at least one known-good slug.
        self.assertIn('href="/species/mango.html"', HTML)

    def test_all_source_urls_well_formed(self):
        sources = list(bc.GENERAL_SOURCES)
        for sp in bc.SPECIES_COMPANIONS:
            sources.extend(sp.get("sources", []))
        self.assertTrue(sources, "expected at least some sources")
        for title, url in sources:
            self.assertTrue(title.strip(), f"empty source title for {url}")
            self.assertTrue(url.startswith("https://"), f"non-https source url: {url}")
            self.assertTrue(urlparse(url).netloc, f"source url has no host: {url}")

    def test_no_em_or_en_dashes_in_rendered_html(self):
        self.assertNotIn(EM_DASH, HTML, "em dash found in rendered HTML (CLAUDE.md copy rule)")
        self.assertNotIn(EN_DASH, HTML, "en dash found in rendered HTML (CLAUDE.md copy rule)")

    def test_external_links_use_noopener(self):
        for tag in re.findall(r"<a\b[^>]*>", HTML):
            if 'target="_blank"' in tag:
                self.assertIn('rel="noopener"', tag, f"target=_blank without rel=noopener: {tag}")

    def test_fig_icon_is_not_blueberry(self):
        fig = next(sp for sp in bc.SPECIES_COMPANIONS if sp["slug"] == "fig")
        self.assertNotEqual(fig["icon"], BLUEBERRY, "fig icon is still the blueberry emoji")

    def test_faq_jsonld_valid(self):
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', HTML, re.DOTALL)
        self.assertIsNotNone(m, "no JSON-LD block found")
        data = json.loads(m.group(1))
        self.assertEqual(data["@type"], "FAQPage")
        self.assertEqual(len(data["mainEntity"]), len(bc.FAQS))
        for q in data["mainEntity"]:
            text = q["acceptedAnswer"]["text"]
            self.assertNotIn(EM_DASH, text)
            self.assertNotIn(EN_DASH, text)

    def test_no_dead_filtered_entries(self):
        # The old builder filtered out good entries containing "Wait"/"NOT";
        # that dead data and filter are gone, so none should remain.
        for sp in bc.SPECIES_COMPANIONS:
            for name, _desc, _grade in sp["good"]:
                self.assertNotIn("Wait", name)
                self.assertNotIn("NOT", name)

    def test_grade_badge_covers_all_grades(self):
        for grade in bc.EVIDENCE_GRADES:
            self.assertIn(grade, bc.GRADE_BADGE, f"GRADE_BADGE missing {grade}")
            # grade_badge must not raise for any valid grade
            self.assertIn("span", bc.grade_badge(grade))


if __name__ == "__main__":
    unittest.main()
