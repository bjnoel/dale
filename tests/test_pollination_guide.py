"""
Tests for tools/scrapers/build_pollination_guide.py -- the evidence-graded
fruit-tree pollination guide builder for treestock.com.au.

Run from repo root with:
    python3 -m unittest discover tests/

Pins the invariants that keep the page honest and link-safe:
  - every graded claim (family status, partner rows, chart rows) uses a valid
    evidence grade,
  - internal /species/ links only point at slugs that actually have a page,
  - every partner variety slug is well-formed (so a built page links, not 404s),
  - source URLs are well formed and external links use rel="noopener",
  - copy has no em or en dashes (CLAUDE.md copy rule),
  - the FAQ JSON-LD parses and matches the visible FAQs,
  - the target-query FAQs are present (the SEO intent of the page).
"""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pg = _load(SCRAPERS / "build_pollination_guide.py")
HTML = pg.build_page(Path(tempfile.gettempdir()) / "no_variety_pages_here")

EM_DASH = "—"
EN_DASH = "–"
GOOD_SLUGS = {s["slug"] for s in json.load(open(SCRAPERS / "fruit_species.json"))}
VSLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class BuildTests(unittest.TestCase):
    def test_build_runs(self):
        self.assertIn("<html", HTML)
        self.assertIn("</html>", HTML)
        self.assertGreater(len(HTML), 4000)

    def test_required_sections(self):
        for anchor in ('id="chart"', 'id="apple"', 'id="avocado"', 'id="kiwifruit"',
                       'id="faq"', 'id="related"'):
            self.assertIn(anchor, HTML, f"missing section {anchor}")

    def test_canonical_and_og(self):
        self.assertIn('<link rel="canonical" href="https://treestock.com.au/fruit-tree-pollination-guide.html">', HTML)
        self.assertIn('<meta property="og:type" content="article">', HTML)


class EvidenceGradeTests(unittest.TestCase):
    def test_family_status_grades_valid(self):
        for fam in pg.FAMILIES:
            label, grade = fam["status"]
            self.assertIn(grade, pg.EVIDENCE_GRADES, f"{fam['key']} status grade")

    def test_partner_row_grades_valid(self):
        for fam in pg.FAMILIES:
            for row in fam["partners"]:
                self.assertEqual(len(row), 4, f"{fam['key']} partner row arity")
                name, vslug, note, grade = row
                self.assertIn(grade, pg.EVIDENCE_GRADES, f"{fam['key']} partner grade")

    def test_summary_grades_valid(self):
        for fruit, verdict, grade in pg.SUMMARY:
            self.assertIn(grade, pg.EVIDENCE_GRADES, f"summary grade for {fruit}")


class LinkSafetyTests(unittest.TestCase):
    def test_species_links_resolve(self):
        for slug in re.findall(r'href="/species/([a-z0-9-]+)\.html"', HTML):
            self.assertIn(slug, GOOD_SLUGS, f"species link {slug} would 404")

    def test_family_species_slugs_are_real(self):
        for fam in pg.FAMILIES:
            for slug in fam["species_slugs"]:
                self.assertIn(slug, GOOD_SLUGS, f"{fam['key']} species_slug {slug}")

    def test_partner_variety_slugs_well_formed(self):
        for fam in pg.FAMILIES:
            for name, vslug, note, grade in fam["partners"]:
                if vslug is not None:
                    self.assertRegex(vslug, VSLUG_RE, f"{fam['key']} vslug {vslug}")

    def test_variety_links_render_when_page_exists(self):
        # With a real built /variety/ page present, the partner links out.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "variety").mkdir()
            (out / "variety" / "plum-santa-rosa.html").write_text("x")
            html = pg.build_page(out)
            self.assertIn('href="/variety/plum-santa-rosa.html"', html)

    def test_variety_links_degrade_without_page(self):
        # HTML built against a dir with no /variety/ pages: partner deep links
        # degrade to plain text. (The footer's /variety/ index link is separate.)
        self.assertNotIn('href="/variety/plum-santa-rosa.html"', HTML)
        self.assertNotIn('href="/variety/avocado-hass.html"', HTML)


class CopyAndSourceTests(unittest.TestCase):
    def test_no_em_or_en_dashes(self):
        self.assertNotIn(EM_DASH, HTML)
        self.assertNotIn(EN_DASH, HTML)

    def test_all_source_urls_well_formed(self):
        sources = list(pg.GENERAL_SOURCES)
        for fam in pg.FAMILIES:
            sources += fam.get("sources") or []
        for title, url in sources:
            self.assertTrue(title.strip(), "empty source title")
            parsed = urlparse(url)
            self.assertEqual(parsed.scheme, "https", f"non-https source {url}")
            self.assertTrue(parsed.netloc, f"no host in source {url}")

    def test_external_links_use_noopener(self):
        for tag in re.findall(r"<a [^>]*target=\"_blank\"[^>]*>", HTML):
            self.assertIn("noopener", tag, f"target=_blank without noopener: {tag}")


class FaqTests(unittest.TestCase):
    def test_faq_jsonld_matches_visible(self):
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', HTML, re.S)
        self.assertIsNotNone(m)
        data = json.loads(m.group(1))
        self.assertEqual(data["@type"], "FAQPage")
        self.assertEqual(len(data["mainEntity"]), len(pg.FAQS))

    def test_target_query_faqs_present(self):
        questions = " ".join(q.lower() for q, _ in pg.FAQS)
        self.assertIn("two apple trees", questions)
        self.assertIn("self pollinating", questions)
        self.assertIn("type a and type b avocado", questions)


class MainTests(unittest.TestCase):
    def test_main_writes_named_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sys.argv = ["build_pollination_guide.py", tmp]
            pg.main()
            out = Path(tmp) / "fruit-tree-pollination-guide.html"
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 4000)


if __name__ == "__main__":
    unittest.main()
