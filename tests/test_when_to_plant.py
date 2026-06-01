"""
Tests for tools/scrapers/build_when_to_plant.py -- the "When to Plant Fruit
Trees in Australia" planting-calendar builder for treestock.com.au.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"

# build_when_to_plant imports treestock_layout, so the scrapers dir must be importable.
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wtp = _load(SCRAPERS / "build_when_to_plant.py")
HTML = wtp.build_page()

# U+2014 em dash, U+2013 en dash. Both banned in treestock copy.
EM_DASH = "—"
EN_DASH = "–"

# Slugs that resolve to a real /species/<slug>.html page.
VALID_SLUGS = wtp.load_valid_species_slugs()


class BuildTests(unittest.TestCase):
    def test_build_writes_named_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sys.argv = ["build_when_to_plant.py", tmp]
            wtp.main()
            out = Path(tmp) / "when-to-plant.html"
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 5000)

    def test_required_sections_present(self):
        for anchor in ('id="zones"', 'id="by-type"', 'id="calendar"',
                       'id="alerts"', 'id="faq"', 'id="related"'):
            self.assertIn(anchor, HTML, f"missing section {anchor}")
        self.assertIn("Bare-root season: June to August", HTML)

    def test_canonical_and_og(self):
        self.assertIn('<link rel="canonical" href="https://treestock.com.au/when-to-plant.html">', HTML)
        self.assertIn('<meta property="og:type" content="article">', HTML)
        self.assertIn('<meta property="og:image"', HTML)

    def test_versioned_stylesheet_not_bare(self):
        # The old orphaned page referenced an unversioned /styles.css. The shared
        # layout uses a cache-busting ?v= query, which is the fix we want.
        self.assertRegex(HTML, r'href="/styles\.css\?v=\d{8}"')


class CopyRuleTests(unittest.TestCase):
    def test_no_em_or_en_dashes(self):
        self.assertNotIn(EM_DASH, HTML, "em dash found (treestock copy rule)")
        self.assertNotIn(EN_DASH, HTML, "en dash found (treestock copy rule)")

    def test_no_dashes_in_source_data(self):
        # Guard the data tables directly, not just the rendered page.
        for s in wtp.SPECIES:
            self.assertNotIn(EM_DASH, s["notes"])
            self.assertNotIn(EN_DASH, s["notes"])
        for q, a in wtp.FAQS:
            self.assertNotIn(EM_DASH, q + a)
            self.assertNotIn(EN_DASH, q + a)


class SpeciesLinkTests(unittest.TestCase):
    def test_all_species_links_resolve(self):
        # Every /species/<slug>.html link in the page must point at a real page.
        linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', HTML))
        self.assertTrue(linked, "expected species links in the calendar")
        unknown = linked - VALID_SLUGS
        self.assertEqual(unknown, set(), f"species links would 404: {unknown}")

    def test_species_data_slugs_are_valid(self):
        # If a slug is in the data it should resolve, otherwise the row should
        # render as plain text (the builder guards this; assert the data is clean).
        for s in wtp.SPECIES:
            if s.get("slug"):
                self.assertIn(s["slug"], VALID_SLUGS,
                              f"{s['name']} -> {s['slug']} has no /species/ page")


class CalendarTests(unittest.TestCase):
    def test_table_rendered_server_side(self):
        # The old page rendered the table in client JS (empty <tbody> to crawlers).
        # Every species name must be present in the static HTML.
        for s in wtp.SPECIES:
            self.assertIn(s["name"], HTML, f"{s['name']} not server-rendered")

    def test_zone_filters_present(self):
        for z in wtp.ZONES:
            self.assertIn(f'data-filter="{z["key"]}"', HTML)
        self.assertIn('data-filter="all"', HTML)

    def test_bare_root_only_on_deciduous(self):
        # Evergreens must never carry a bare-root window; deciduous should.
        by_name = {s["name"]: s for s in wtp.SPECIES}
        for evergreen in ("Mango", "Avocado", "Lemon", "Banana", "Lychee", "Macadamia"):
            self.assertEqual(by_name[evergreen]["bareRoot"], [],
                             f"{evergreen} is evergreen, should have no bare-root window")
        for deciduous in ("Apple", "Pear", "Fig", "Grape", "Cherry", "Mulberry"):
            self.assertTrue(by_name[deciduous]["bareRoot"],
                            f"{deciduous} is deciduous, should have a bare-root window")

    def test_months_are_valid_range(self):
        for s in wtp.SPECIES:
            for field in ("best", "ok", "bareRoot"):
                for m in s[field]:
                    self.assertIn(m, range(1, 13), f"{s['name']} {field} bad month {m}")

    def test_frost_tender_temperate_species_warned(self):
        # Research-audit fix: dragon fruit is tagged temperate and is frost-tender,
        # so its note must carry a frost warning (it did not before the audit).
        df = next(s for s in wtp.SPECIES if s["slug"] == "dragon-fruit")
        self.assertIn("temperate", df["zones"])
        self.assertIn("frost", df["notes"].lower())

    def test_arid_species_tagged(self):
        # Research-audit fix: drought/heat-adapted species belong to the arid zone.
        arid = {s["name"] for s in wtp.SPECIES if "arid" in s["zones"]}
        for name in ("Olive", "Fig", "Pomegranate", "Grape", "Jujube", "Loquat", "Apricot"):
            self.assertIn(name, arid, f"{name} should be tagged arid")

    def test_apple_zone_matches_its_low_chill_note(self):
        # Audit fix: apple's note says low-chill varieties suit warm areas, so the
        # zone tag must include subtropical (was internally contradictory before).
        apple = next(s for s in wtp.SPECIES if s["slug"] == "apple")
        self.assertIn("subtropical", apple["zones"])


class FaqJsonLdTests(unittest.TestCase):
    def test_faq_jsonld_parses_and_matches(self):
        m = re.search(
            r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
            HTML, re.S,
        )
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        data = json.loads(m.group(1))
        self.assertEqual(data["@type"], "FAQPage")
        self.assertEqual(len(data["mainEntity"]), len(wtp.FAQS))
        for ent in data["mainEntity"]:
            self.assertEqual(ent["@type"], "Question")
            self.assertTrue(ent["acceptedAnswer"]["text"])


class SourcesTests(unittest.TestCase):
    def test_sources_present(self):
        self.assertGreaterEqual(len(wtp.SOURCES), 3,
                                "fill SOURCES with verified AU references")

    def test_sources_https(self):
        for s in wtp.SOURCES:
            self.assertTrue(s["url"].startswith("https://"),
                            f"non-https source: {s['url']}")

    def test_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in wtp.SOURCES)
        self.assertTrue(
            any(d in domains for d in ("nt.gov.au", "bom.gov.au", "dpird.wa.gov.au", "vic.gov.au")),
            "expected at least one gov/extension authority among the sources",
        )

    def test_references_use_noopener(self):
        if wtp.SOURCES:
            self.assertIn('id="references"', HTML)
            # external links open in a new tab and must be rel=noopener.
            refs = re.findall(r'<li><a href="https://[^"]+"[^>]*>', HTML)
            self.assertTrue(refs)
            for a in refs:
                self.assertIn("noopener", a)


if __name__ == "__main__":
    unittest.main()
