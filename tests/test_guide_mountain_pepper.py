"""
Mountain pepper growing-guide tests (tools/scrapers/growing_guides/mountain-pepper.json).

Mountain pepper (Tasmannia lanceolata) is the rule-breaking bush food: a cool-climate, frost-HARDY
highland shrub that needs a male and a female plant to set its hot black pepperberries. Flagship
VIC (its highland home); QLD/WA are the marginal warm-and-dry ends. Hyphenated slug -> underscore
module name.

Correctness traps pinned below:
  * dioecious: you need a male AND a female for berries (leaf comes from any plant);
  * it is frost-HARDY and cool-climate (the opposite of the frost-tender myrtles);
  * it is NOT mapped to the stone/pome 'temperate' chill-hours note (stays default).
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

MP_SPECIES = {
    "common_name": "Mountain Pepper", "latin_name": "Tasmannia lanceolata",
    "description": "Generic mountain pepper blurb that should be replaced by the rich guide.",
    "slug": "mountain-pepper",
}


def _mp_products(n=4):
    names = ["Female", "Male", "Female", "Male"]
    return [
        {"title": f"Mountain Pepper {names[i]}", "url": f"https://nursery.example/mountain-pepper-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 16.0 + i * 4,
         "available": True, "species": MP_SPECIES}
        for i in range(n)
    ]


MP_PAGES = build_state_pages("mountain-pepper", _mp_products())
MP_JSON = load_guide("mountain-pepper")


class MountainPepperGuideTests(unittest.TestCase):
    def test_pages_build_nonempty_and_distinct(self):
        bodies = list(MP_PAGES.values())
        for st, html in MP_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} mountain pepper page too small")
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two mountain pepper state pages identical")

    def test_generic_blurb_replaced(self):
        for st, html in MP_PAGES.items():
            self.assertNotIn("Generic mountain pepper blurb", html, f"{st} still shows the blurb")

    def test_no_dashes(self):
        assert_no_dashes(self, MP_JSON, "mountain-pepper.json")
        for st, html in MP_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on mountain pepper {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on mountain pepper {st} page")

    def test_correctness_dioecious_needs_a_pair(self):
        # THE trap: separate male and female plants are needed for berries; leaf from any plant.
        for st in STATES:
            page = MP_PAGES[st]
            self.assertIn("dioecious", page, f"{st} page should state it is dioecious")
            self.assertIn("male and a female", page,
                          f"{st} page should say a male and a female are needed for berries")

    def test_correctness_frost_hardy_cool_climate(self):
        for st in STATES:
            self.assertIn("frost-hardy", MP_PAGES[st], f"{st} page missing the frost-hardy fact")

    def test_vic_is_the_highland_home(self):
        self.assertIn("highland", MP_PAGES["VIC"].lower())

    def test_faq_jsonld_parses(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          MP_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            expected = len(MP_JSON["core"]["faqs"]) + len(MP_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_https_and_resolve(self):
        for s in MP_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://") or s["url"].startswith("http://"),
                            f"bad source url: {s['url']}")
        src_ids = {s["id"] for s in MP_JSON["sources"]}
        cited = set()
        for block in [MP_JSON["core"]] + list(MP_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "mountain pepper guide cites an unknown source id")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', MP_PAGES[st]))
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_climate_category_stays_default(self):
        # Deliberately NOT mapped: a cool-climate frost-hardy mountain shrub must not inherit the
        # stone/pome 'temperate / choose low-chill varieties' note. Its real story is in the overlays.
        self.assertIsNone(bssp.SPECIES_CLIMATE_CATEGORY.get("mountain pepper"))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("mountain-pepper").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("mountain-pepper", "VIC").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n, "the VIC overlay should add cited sources beyond core")


if __name__ == "__main__":
    unittest.main()
