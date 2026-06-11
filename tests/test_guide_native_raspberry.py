"""
Native raspberry growing-guide tests (tools/scrapers/growing_guides/native-raspberry.json).

Native raspberry covers two Australian Rubus species under one name: the wide-ranging, hardy
Rubus parvifolius (cool/dry areas, VIC/WA) and the warm-climate Rubus rosifolius (Atherton
raspberry, QLD coast). The trap a generic guide would miss is that "native raspberry" is two
species matched to climate, and that the plant is a thorny scrambler needing a yearly prune.
Hyphenated slug -> underscore module name.
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

NR_SPECIES = {
    "common_name": "Native Raspberry", "latin_name": "Rubus parvifolius",
    "description": "Generic native raspberry blurb that should be replaced by the rich guide.",
    "slug": "native-raspberry",
}


def _nr_products(n=6):
    names = ["Rubus parvifolius", "Rubus rosifolius", "Atherton", "Rubus parvifolius",
             "Rubus rosifolius", "Atherton"]
    return [
        {"title": f"Native Raspberry {names[i]}", "url": f"https://nursery.example/native-raspberry-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 12.0 + i * 3,
         "available": True, "species": NR_SPECIES}
        for i in range(n)
    ]


NR_PAGES = build_state_pages("native-raspberry", _nr_products())
NR_JSON = load_guide("native-raspberry")


class NativeRaspberryGuideTests(unittest.TestCase):
    def test_pages_build_nonempty_and_distinct(self):
        bodies = list(NR_PAGES.values())
        for st, html in NR_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} native raspberry page too small")
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two native raspberry state pages identical")

    def test_generic_blurb_replaced(self):
        for st, html in NR_PAGES.items():
            self.assertNotIn("Generic native raspberry blurb", html, f"{st} still shows the blurb")

    def test_no_dashes(self):
        assert_no_dashes(self, NR_JSON, "native-raspberry.json")
        for st, html in NR_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on native raspberry {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on native raspberry {st} page")

    def test_correctness_two_species(self):
        # THE trap: native raspberry is two species matched to climate (carried by the core).
        for st in STATES:
            page = NR_PAGES[st]
            self.assertIn("Rubus parvifolius", page, f"{st} page missing R. parvifolius")
            self.assertIn("Rubus rosifolius", page, f"{st} page missing R. rosifolius")

    def test_core_facts_on_every_state(self):
        for st in STATES:
            page = NR_PAGES[st].lower()
            self.assertIn("prune", page, f"{st} page missing the yearly prune")
            self.assertIn("thorn", page + " " + NR_PAGES[st].lower(),
                          f"{st} page missing the thorny-cane note")

    def test_qld_leans_rosifolius(self):
        self.assertIn("Atherton raspberry", NR_PAGES["QLD"])

    def test_faq_jsonld_parses(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          NR_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            expected = len(NR_JSON["core"]["faqs"]) + len(NR_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_https_and_resolve(self):
        for s in NR_JSON["sources"]:
            self.assertTrue(s["url"].startswith("http"), f"bad source url: {s['url']}")
        src_ids = {s["id"] for s in NR_JSON["sources"]}
        cited = set()
        for block in [NR_JSON["core"]] + list(NR_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "native raspberry guide cites an unknown source id")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', NR_PAGES[st]))
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_climate_category_stays_default(self):
        # Deliberately NOT mapped to the cultivated-'raspberry' cool-climate note: the native
        # species span subtropical to temperate and are far hardier, so the overlays tell the story.
        self.assertIsNone(bssp.SPECIES_CLIMATE_CATEGORY.get("native raspberry"))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("native-raspberry").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("native-raspberry", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n, "the WA overlay should add cited sources beyond core")


if __name__ == "__main__":
    unittest.main()
