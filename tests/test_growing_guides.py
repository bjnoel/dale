"""
Tests for the per-species growing-guide content layer
(tools/scrapers/growing_guides.py + growing_guides/<slug>.json).

This module is deliberately SEPARATE from test_species_state_pages.py so that
adding a new species guide does not collide with parallel work on that file.
It carries:

  * AllGrowingGuidesTests  -- structural guards applied to EVERY guide JSON
    (no em/en dashes, cited ids resolve, https sources, well-formed states,
    internal /species/ links that do not 404). Olive, plum and any future
    species are held to the same bar with no per-species boilerplate.
  * PlumGuideTests         -- the plum guide rendered into its four state combo
    pages: per-state uniqueness, region tokens that do not leak, no dashes,
    FAQ JSON-LD, cited Sources (nofollow), owned Further reading (followed),
    and the correctness facts that distinguish each state.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
GUIDES_DIR = SCRAPERS / "growing_guides"

# The builder imports treestock_layout, shipping, stocklib and growing_guides.
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bssp = _load(SCRAPERS / "build_species_state_pages.py")
gg = _load(SCRAPERS / "growing_guides.py")

EM_DASH = "—"
EN_DASH = "–"
STATES = ["WA", "QLD", "NSW", "VIC"]
TODAY = "2026-06-02"

VALID_SLUGS = {
    s["slug"] for s in json.loads((SCRAPERS / "fruit_species.json").read_text()) if s.get("slug")
}
GUIDE_FILES = sorted(p for p in GUIDES_DIR.glob("*.json") if p.name != "archive_links.json")


class AllGrowingGuidesTests(unittest.TestCase):
    """Structural guards that apply to every growing_guides/<slug>.json."""

    def test_olive_and_plum_present(self):
        names = {p.stem for p in GUIDE_FILES}
        self.assertIn("olive", names)
        self.assertIn("plum", names)

    def test_every_guide_is_structurally_sound(self):
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

            # The renderer only needs a core block; guides also carry states + sources.
            self.assertIsInstance(g.get("core"), dict, f"{p.name} missing core")

            src_ids = [s["id"] for s in g.get("sources", [])]
            self.assertEqual(len(src_ids), len(set(src_ids)), f"duplicate source id in {p.name}")
            for s in g.get("sources", []):
                self.assertTrue(s["url"].startswith("https://"),
                                f"non-https source in {p.name}: {s['url']}")

            cited = set()
            for block in [g["core"]] + list(g.get("states", {}).values()):
                for sec in block.get("sections", []):
                    cited.update(sec.get("cites", []))
            self.assertEqual(cited - set(src_ids), set(), f"{p.name} cites an unknown source id")

            for st, block in g.get("states", {}).items():
                self.assertTrue(block.get("sections"), f"{p.name} state {st} has no sections")
                self.assertTrue(block.get("faqs"), f"{p.name} state {st} has no faqs")

            for fr in g.get("further_reading", []):
                self.assertTrue(fr["url"].startswith("https://"),
                                f"{p.name} further-reading non-https: {fr['url']}")

    def test_internal_species_links_resolve(self):
        # Any /species/<slug>.html link a guide body emits must be a real species.
        for p in GUIDE_FILES:
            slug = p.stem
            html = gg.render_species_guide(slug) + "".join(
                gg.render_combo_guide(slug, st) for st in STATES
            )
            linked = set(re.findall(r"/species/([a-z0-9-]+)\.html", html))
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{p.name} has /species/ links that would 404: {linked - VALID_SLUGS}")


# --- Plum (the second enriched species, after olive) -----------------------

PLUM_SPECIES = {
    "common_name": "Plum",
    "latin_name": "Prunus domestica",
    "description": "Generic plum blurb that should be replaced by the rich guide.",
    "slug": "plum",
}


def _plum_products(n=5):
    return [
        {"title": f"Plum Variety {i}", "url": f"https://nursery.example/plum-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 25.0 + i * 5,
         "available": True, "species": PLUM_SPECIES}
        for i in range(n)
    ]


PLUM_PAGES = {st: bssp.build_combo_page(st, "plum", _plum_products(), TODAY) for st in STATES}
PLUM_JSON = json.loads((GUIDES_DIR / "plum.json").read_text(encoding="utf-8"))

# Distinctive region tokens that must appear on exactly one plum state page.
PLUM_REGION_TOKENS = {
    "WA": ["Perth Hills", "Donnybrook", "Manjimup"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Central Tablelands", "Riverina"],
    "VIC": ["Goulburn Valley", "Sunraysia"],
}


class PlumGuideTests(unittest.TestCase):
    def test_pages_build_and_are_mutually_distinct(self):
        bodies = list(PLUM_PAGES.values())
        for st, html in PLUM_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} plum page too small")
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two plum state pages are identical")

    def test_region_tokens_present_and_do_not_leak(self):
        for st, tokens in PLUM_REGION_TOKENS.items():
            self.assertTrue(any(t in PLUM_PAGES[st] for t in tokens),
                            f"plum {st} page missing its region tokens {tokens}")
            for other in STATES:
                if other == st:
                    continue
                for t in tokens:
                    self.assertNotIn(t, PLUM_PAGES[other],
                                     f"plum {st} token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes_in_combo_pages(self):
        for st, html in PLUM_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on plum {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on plum {st} page")

    def test_generic_blurb_replaced_by_rich_guide(self):
        for st, html in PLUM_PAGES.items():
            self.assertNotIn("Generic plum blurb", html, f"{st} still shows the blurb")
            self.assertIn("Choosing a variety", html, f"{st} missing the core guide")

    def test_faq_jsonld_parses_per_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          PLUM_PAGES[st], re.S)
            self.assertIsNotNone(m, f"plum {st} FAQ JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(PLUM_JSON["core"]["faqs"]) + len(PLUM_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"plum {st} FAQ count mismatch")

    def test_sources_present_and_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', PLUM_PAGES[st], re.S)
            self.assertIsNotNone(block, f"plum {st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"plum {st} has no reference links")
            for url, attrs in refs:
                self.assertIn("nofollow", attrs, f"plum {st} ref missing nofollow: {url}")

    def test_further_reading_owned_and_followed(self):
        # Plum's owned archive links are WANATCA yearbook/ACOTANC: followed (no nofollow).
        for st in STATES:
            self.assertIn('id="further-reading"', PLUM_PAGES[st], f"plum {st} missing Further reading")
        fr = re.search(r'id="further-reading".*?</section>', PLUM_PAGES["WA"], re.S).group(0)
        self.assertIn("wanatca.org.au", fr)
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_state_specific_facts_are_correct(self):
        # Each state leads with its own, correct specifics (guards region leak and the
        # Victoria-is-fruit-fly-free error that the research flagged).
        self.assertIn("Mediterranean fruit fly", PLUM_PAGES["WA"])
        self.assertIn("Organism List", PLUM_PAGES["WA"])
        self.assertIn("Granite Belt", PLUM_PAGES["QLD"])
        self.assertIn("Central Tablelands", PLUM_PAGES["NSW"])
        self.assertIn("now established in northern Victoria", PLUM_PAGES["VIC"])


if __name__ == "__main__":
    unittest.main()
