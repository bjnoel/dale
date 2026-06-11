"""
Cinnamon myrtle growing-guide tests (tools/scrapers/growing_guides/cinnamon-myrtle.json).

Cinnamon myrtle (Backhousia myrtifolia) is the cold-hardy member of the leaf-myrtle family,
grown as a native cinnamon substitute. Its distinguishing hook (the trap a generic myrtle guide
would miss) is that mature plants take LIGHT FROST, unlike lemon/aniseed myrtle. Hyphenated slug
-> underscore module name.
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guide_helpers import (  # noqa: E402
    bssp, gg, EM_DASH, EN_DASH, STATES, VALID_SLUGS, load_guide, build_state_pages, assert_no_dashes,
)

CM_SPECIES = {
    "common_name": "Cinnamon Myrtle", "latin_name": "Backhousia myrtifolia",
    "description": "Generic cinnamon myrtle blurb that should be replaced by the rich guide.",
    "slug": "cinnamon-myrtle",
}


def _cm_products(n=6):
    sizes = ["Tube", "140mm", "200mm", "Advanced", "Tube", "300mm"]
    return [
        {"title": f"Cinnamon Myrtle {sizes[i]}", "url": f"https://nursery.example/cinnamon-myrtle-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 13.0 + i * 4,
         "available": True, "species": CM_SPECIES}
        for i in range(n)
    ]


CM_PAGES = build_state_pages("cinnamon-myrtle", _cm_products())
CM_JSON = load_guide("cinnamon-myrtle")


class CinnamonMyrtleGuideTests(unittest.TestCase):
    def test_pages_build_nonempty_and_distinct(self):
        bodies = list(CM_PAGES.values())
        for st, html in CM_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} cinnamon myrtle page too small")
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two cinnamon myrtle state pages identical")

    def test_generic_blurb_replaced(self):
        for st, html in CM_PAGES.items():
            self.assertNotIn("Generic cinnamon myrtle blurb", html, f"{st} still shows the blurb")

    def test_no_dashes(self):
        assert_no_dashes(self, CM_JSON, "cinnamon-myrtle.json")
        for st, html in CM_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on cinnamon myrtle {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on cinnamon myrtle {st} page")

    def test_correctness_cold_hardy_hook(self):
        # THE distinguishing fact: mature plants take light frost (carried by the core).
        for st in STATES:
            self.assertIn("light frost", CM_PAGES[st], f"{st} page missing the light-frost hardiness")

    def test_core_facts_on_every_state(self):
        for st in STATES:
            page = CM_PAGES[st]
            self.assertIn("cinnamon", page.lower(), f"{st} page missing the cinnamon use")
            self.assertIn("Myrtle rust", page, f"{st} page must still name myrtle rust")

    def test_faq_jsonld_parses(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          CM_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            expected = len(CM_JSON["core"]["faqs"]) + len(CM_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_https_and_resolve(self):
        for s in CM_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in CM_JSON["sources"]}
        cited = set()
        for block in [CM_JSON["core"]] + list(CM_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "cinnamon myrtle guide cites an unknown source id")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', CM_PAGES[st]))
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_climate_category_is_subtropical(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY.get("cinnamon myrtle"), "subtropical")

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("cinnamon-myrtle").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("cinnamon-myrtle", "NSW").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n, "the NSW overlay should add cited sources beyond core")


if __name__ == "__main__":
    unittest.main()
