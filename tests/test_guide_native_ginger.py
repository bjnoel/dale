"""
Native ginger growing-guide tests (tools/scrapers/growing_guides/native-ginger.json).

Native ginger (Alpinia caerulea) is a shade-loving clumping rainforest plant grown for edible
blue berries and gingery shoots, native up the QLD coast and into NSW. Hyphenated slug, so this
module file uses an underscore while the slug stays "native-ginger".

Correctness traps pinned below:
  * it WANTS shade (the opposite of most edibles) and is frost-tender;
  * it is Alpinia caerulea, NOT the supermarket ginger Zingiber officinale;
  * it is native to QLD/NSW (the QLD page must say so).
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

NG_SPECIES = {
    "common_name": "Native Ginger", "latin_name": "Alpinia caerulea",
    "description": "Generic native ginger blurb that should be replaced by the rich guide.",
    "slug": "native-ginger",
}


def _ng_products(n=6):
    forms = ["Green", "Atherton Red Back", "Wavy Leaf", "Green", "Atherton Red Back", "Green"]
    return [
        {"title": f"Native Ginger {forms[i]}", "url": f"https://nursery.example/native-ginger-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 9.0 + i * 3,
         "available": True, "species": NG_SPECIES}
        for i in range(n)
    ]


NG_PAGES = build_state_pages("native-ginger", _ng_products())
NG_JSON = load_guide("native-ginger")


class NativeGingerGuideTests(unittest.TestCase):
    def test_pages_build_nonempty_and_distinct(self):
        bodies = list(NG_PAGES.values())
        for st, html in NG_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} native ginger page too small")
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two native ginger state pages identical")

    def test_generic_blurb_replaced(self):
        for st, html in NG_PAGES.items():
            self.assertNotIn("Generic native ginger blurb", html, f"{st} still shows the blurb")

    def test_no_dashes(self):
        assert_no_dashes(self, NG_JSON, "native-ginger.json")
        for st, html in NG_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on native ginger {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on native ginger {st} page")

    def test_core_facts_on_every_state(self):
        for st in STATES:
            page = NG_PAGES[st]
            self.assertIn("shade", page.lower(), f"{st} page missing the shade story")
            self.assertIn("blue berries", page.lower(), f"{st} page missing the edible blue berries")
            self.assertIn("frost-tender", page, f"{st} page missing the frost-tender note")

    def test_correctness_not_supermarket_ginger(self):
        for st in STATES:
            page = NG_PAGES[st]
            self.assertIn("Alpinia caerulea", page, f"{st} missing the accepted name")
            self.assertIn("Zingiber officinale", page,
                          f"{st} should distinguish it from supermarket ginger")

    def test_qld_is_native_home(self):
        self.assertIn("native to Queensland", NG_PAGES["QLD"].replace("\n", " "))

    def test_wa_quarantine(self):
        self.assertIn("import", NG_PAGES["WA"].lower())

    def test_faq_jsonld_parses(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          NG_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            expected = len(NG_JSON["core"]["faqs"]) + len(NG_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_https_and_resolve(self):
        for s in NG_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in NG_JSON["sources"]}
        cited = set()
        for block in [NG_JSON["core"]] + list(NG_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "native ginger guide cites an unknown source id")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', NG_PAGES[st]))
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_climate_category_is_subtropical(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY.get("native ginger"), "subtropical")

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("native-ginger").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("native-ginger", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n, "the WA overlay should add cited sources beyond core")


if __name__ == "__main__":
    unittest.main()
