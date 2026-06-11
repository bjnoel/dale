"""
Lemon myrtle growing-guide tests (tools/scrapers/growing_guides/lemon-myrtle.json).

Lemon myrtle (Backhousia citriodora) is the flagship Australian native food herb: a SE
Queensland rainforest tree grown for its citral-rich leaf, not a fruit. Flagship QLD (its
native home and the heart of the commercial leaf industry), WA defined by the dry-climate /
quarantine context, VIC the cold limit (pot culture). Hyphenated slug, so this module file
uses an underscore while the slug stays "lemon-myrtle". In its own file so parallel guide
runs never collide on a shared test module.

Correctness traps this guide must get right (each pinned below):
  * it is grown for LEAF, not fruit, and is frost-tender when young;
  * myrtle rust (Austropuccinia psidii) is the headline disease, worse in the humid north;
  * it is native to Queensland (the QLD page must say so).
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

LEMON_MYRTLE_SPECIES = {
    "common_name": "Lemon Myrtle",
    "latin_name": "Backhousia citriodora",
    "description": "Generic lemon myrtle blurb that should be replaced by the rich guide.",
    "slug": "lemon-myrtle",
}


def _lm_products(n=6):
    return [
        {"title": f"Lemon Myrtle {sz}", "url": f"https://nursery.example/lemon-myrtle-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 14.0 + i * 4,
         "available": True, "species": LEMON_MYRTLE_SPECIES}
        for i, sz in enumerate(["Tube", "140mm", "200mm", "Advanced", "Tube", "300mm"][:n])
    ]


LM_PAGES = build_state_pages("lemon-myrtle", _lm_products())
LM_JSON = load_guide("lemon-myrtle")

LM_REGION_TOKENS = {
    "QLD": ["humid"],
    "WA": ["Perth", "quarantine"],
    "VIC": ["Melbourne", "pot"],
}


class LemonMyrtleGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in LM_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} lemon myrtle page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(LM_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two lemon myrtle state pages identical")

    def test_generic_blurb_replaced(self):
        for st, html in LM_PAGES.items():
            self.assertNotIn("Generic lemon myrtle blurb", html, f"{st} still shows the blurb")

    def test_no_em_or_en_dashes(self):
        for st, html in LM_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on lemon myrtle {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on lemon myrtle {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, LM_JSON, "lemon-myrtle.json")

    def test_core_facts_present_on_every_state(self):
        # Leaf not fruit, frost-tender young, citral/lemon, and tip pruning all ride the core.
        for st in STATES:
            page = LM_PAGES[st]
            self.assertIn("citral", page, f"{st} page missing the citral fact")
            self.assertIn("tip prun", page.lower(), f"{st} page missing tip pruning")
            self.assertIn("frost-tender", page, f"{st} page missing the frost-tender note")

    def test_myrtle_rust_is_the_named_disease(self):
        # THE disease trap: myrtle rust by name + its fungus, carried by the core.
        for st in STATES:
            page = LM_PAGES[st]
            self.assertIn("Myrtle rust", page, f"{st} page must name myrtle rust")
            self.assertIn("Austropuccinia psidii", page,
                          f"{st} page must name the myrtle-rust fungus")

    def test_qld_is_the_native_home(self):
        qld = LM_PAGES["QLD"]
        self.assertIn("native to Queensland", qld.replace("\n", " "))

    def test_wa_quarantine_framing(self):
        wa = LM_PAGES["WA"]
        self.assertIn("quarantine", wa.lower())
        self.assertIn("Perth", wa)

    def test_each_state_has_its_own_tokens(self):
        for st, tokens in LM_REGION_TOKENS.items():
            self.assertTrue(any(t in LM_PAGES[st] for t in tokens),
                            f"{st} lemon myrtle page missing its tokens {tokens}")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          LM_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(LM_JSON["core"]["faqs"]) + len(LM_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_https_and_resolve(self):
        for s in LM_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in LM_JSON["sources"]}
        cited = set()
        for block in [LM_JSON["core"]] + list(LM_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "lemon myrtle guide cites an unknown source id")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', LM_PAGES[st]))
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_climate_category_is_subtropical(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY.get("lemon myrtle"), "subtropical")

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("lemon-myrtle").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("lemon-myrtle", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
