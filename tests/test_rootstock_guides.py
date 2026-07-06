"""
Tests for the per-species ROOTSTOCK content layer
(tools/scrapers/rootstock_guides.py + rootstock_guides/<slug>.json + build_rootstock_page.py).

Kept SEPARATE from the growing-guide tests so adding a rootstock species does not
collide with parallel work. It carries:

  * AllRootstockGuidesTests -- structural guards applied to EVERY rootstock JSON
    (no em/en dashes, well-formed rootstock rows, cited ids resolve, https sources,
    slug matches filename and is a real species).
  * RootstockRenderTests    -- the loader/renderer contract (has_guide fallback,
    section rendering, FAQ extraction).
  * RootstockPageTests      -- the assembled /rootstock.html page: FAQPage JSON-LD,
    key facts present, internal /species/ links that do not 404, restriction framing
    (no "Ships to WA" badge), and no dashes.

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
GUIDES_DIR = SCRAPERS / "rootstock_guides"

# The builder imports treestock_layout, stocklib and rootstock_guides.
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rg = _load(SCRAPERS / "rootstock_guides.py")
brp = _load(SCRAPERS / "build_rootstock_page.py")

EM_DASH = "—"
EN_DASH = "–"

VALID_SLUGS = {
    s["slug"] for s in json.loads((SCRAPERS / "fruit_species.json").read_text()) if s.get("slug")
}
GUIDE_FILES = sorted(GUIDES_DIR.glob("*.json"))


class AllRootstockGuidesTests(unittest.TestCase):
    """Structural guards that apply to every rootstock_guides/<slug>.json."""

    def test_pilot_species_present(self):
        names = {p.stem for p in GUIDE_FILES}
        # Pilot (peach/plum/apple) plus the batch-2 species. "lemon" carries the shared
        # citrus guide (common_name "Citrus"), since "citrus" is not an enabled species.
        for slug in ("peach", "plum", "apple", "apricot", "cherry", "pear", "lemon"):
            self.assertIn(slug, names, f"missing rootstock guide for {slug}")

    def test_every_guide_is_structurally_sound(self):
        self.assertTrue(GUIDE_FILES, "no rootstock guide JSON files found")
        for p in GUIDE_FILES:
            g = json.loads(p.read_text(encoding="utf-8"))

            def scan(obj, path=p.name):
                if isinstance(obj, str):
                    self.assertNotIn(EM_DASH, obj, f"em dash in {path}")
                    self.assertNotIn(EN_DASH, obj, f"en dash in {path}")
                elif isinstance(obj, dict):
                    for k, v in obj.items():
                        scan(v, f"{path}.{k}")
                elif isinstance(obj, list):
                    for i, v in enumerate(obj):
                        scan(v, f"{path}[{i}]")
            scan(g)

            # slug matches filename and is a real, enabled species.
            self.assertEqual(g.get("slug"), p.stem, f"{p.name} slug != filename")
            self.assertIn(p.stem, VALID_SLUGS, f"{p.name} is not a known species slug")

            # The renderer needs at least one well-formed rootstock row.
            rows = g.get("rootstocks")
            self.assertIsInstance(rows, list, f"{p.name} missing rootstocks list")
            self.assertTrue(rows, f"{p.name} has no rootstocks")
            for r in rows:
                for key in ("name", "vigour", "soils", "notes"):
                    self.assertTrue(r.get(key), f"{p.name} rootstock missing {key}: {r.get('name')}")
                self.assertIsInstance(r.get("cites", []), list, f"{p.name} cites not a list")

            # Source ids unique and https.
            src_ids = [s["id"] for s in g.get("sources", [])]
            self.assertEqual(len(src_ids), len(set(src_ids)), f"duplicate source id in {p.name}")
            for s in g.get("sources", []):
                self.assertTrue(s["url"].startswith("https://"),
                                f"non-https source in {p.name}: {s['url']}")

            # Every cite (rows + grow_your_own sections) resolves to a real source id.
            cited = set()
            for r in rows:
                cited.update(r.get("cites", []))
            for sec in (g.get("grow_your_own") or {}).get("sections", []):
                cited.update(sec.get("cites", []))
            self.assertEqual(cited - set(src_ids), set(),
                             f"{p.name} cites an unknown source id: {cited - set(src_ids)}")

            # grow_your_own sections and faqs are well-formed where present.
            for sec in (g.get("grow_your_own") or {}).get("sections", []):
                self.assertTrue(sec.get("heading"), f"{p.name} grow_your_own section missing heading")
                self.assertTrue(sec.get("body"), f"{p.name} grow_your_own section missing body")
            for f in g.get("faqs", []):
                self.assertTrue(f.get("q") and f.get("a"), f"{p.name} malformed faq")


class RootstockRenderTests(unittest.TestCase):
    def test_has_guide_and_fallback(self):
        for slug in ("peach", "plum", "apple", "apricot", "cherry", "pear", "lemon"):
            self.assertTrue(rg.has_guide(slug))
        self.assertFalse(rg.has_guide("durian"))
        self.assertEqual(rg.render_species_section("durian"), "")

    def test_section_renders_key_content(self):
        for slug, token in (("peach", "Nemaguard"), ("plum", "Myrobalan"), ("apple", "MM106"),
                            ("apricot", "Citation"), ("cherry", "Gisela 5"),
                            ("pear", "Quince C"), ("lemon", "Flying Dragon")):
            html = rg.render_species_section(slug)
            self.assertIn(token, html, f"{slug} section missing {token}")
            self.assertIn(f'id="{slug}"', html)
            self.assertNotIn(EM_DASH, html)
            self.assertNotIn(EN_DASH, html)

    def test_get_faqs(self):
        for slug in ("peach", "plum", "apple", "apricot", "cherry", "pear", "lemon"):
            faqs = rg.get_faqs(slug)
            self.assertTrue(faqs, f"{slug} has no faqs")
            for q, a in faqs:
                self.assertTrue(q and a)


class RootstockPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.html = brp.build_page(Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_no_dashes(self):
        self.assertNotIn(EM_DASH, self.html)
        self.assertNotIn(EN_DASH, self.html)

    def test_faq_jsonld_parses_and_counts(self):
        m = re.search(r'<script type="application/ld\+json">(\{.*?"FAQPage".*?\})</script>',
                      self.html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD not found")
        data = json.loads(m.group(1))
        self.assertEqual(data["@type"], "FAQPage")
        expected = len(brp.PAGE_FAQS) + sum(len(rg.get_faqs(s)) for s in brp.SPECIES)
        self.assertEqual(len(data["mainEntity"]), expected, "FAQ count mismatch")

    def test_key_facts_present(self):
        for token in ("Nemaguard", "Myrobalan", "MM106", "Olea Nurseries",
                      "Western Australian Organism List", "Grow your own peach rootstock",
                      "Plant Health Assurance Certificate"):
            self.assertIn(token, self.html, f"page missing '{token}'")

    def test_internal_species_links_resolve(self):
        linked = set(re.findall(r"/species/([a-z0-9-]+)\.html", self.html))
        self.assertTrue(linked, "no /species/ links on the page")
        self.assertEqual(linked - VALID_SLUGS, set(),
                         f"page has /species/ links that would 404: {linked - VALID_SLUGS}")

    def test_no_ships_to_wa_badge(self):
        # House rule: show restriction warnings, never a "Ships to WA" badge.
        self.assertNotIn("Ships to WA", self.html)

    def test_canonical_and_active_nav(self):
        self.assertIn("https://treestock.com.au/rootstock.html", self.html)
        self.assertIn("Rootstock Guide", self.html)  # nav dropdown + footer deep link


if __name__ == "__main__":
    unittest.main()
