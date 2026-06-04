"""
Avocado growing-guide tests (tools/scrapers/growing_guides/avocado.json). Avocado is a
genuine four-state crop (WA Southern Forests, QLD Bundaberg/Atherton, NSW north coast,
VIC Sunraysia), so every state gets a real, distinct overlay. In its own file so parallel
guide runs never collide on a shared test module.
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guide_helpers import (  # noqa: E402
    gg, EM_DASH, EN_DASH, STATES, VALID_SLUGS, load_guide, build_state_pages, assert_no_dashes,
)

AVOCADO_SPECIES = {
    "common_name": "Avocado",
    "latin_name": "Persea americana",
    "description": "Generic avocado blurb that should be replaced by the rich guide.",
    "slug": "avocado",
}


def _avocado_products(n=7):
    # Named varieties that are actually in live Australian nursery stock, a mix of
    # Type A (Hass, Reed, Wurtz) and Type B (Fuerte, Bacon, Shepard, Edranol).
    names = ["Hass", "Fuerte", "Reed", "Wurtz", "Bacon", "Shepard", "Edranol"]
    return [
        {"title": f"Avocado {names[i % len(names)]}",
         "url": f"https://nursery.example/avocado-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 45.0 + i * 5,
         "available": True, "species": AVOCADO_SPECIES}
        for i in range(n)
    ]


AVOCADO_PAGES = build_state_pages("avocado", _avocado_products())
AVOCADO_JSON = load_guide("avocado")

# Region tokens that are unique to one state (the leak guard relies on this).
AVOCADO_REGION_TOKENS = {
    "WA": ["Pemberton", "Manjimup"],
    "QLD": ["Bundaberg", "Atherton"],
    "NSW": ["Northern Rivers", "Comboyne"],
    "VIC": ["Sunraysia", "Mildura"],
}


class AvocadoGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in AVOCADO_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} avocado page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(AVOCADO_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two avocado state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in AVOCADO_PAGES.items():
            self.assertNotIn("Generic avocado blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in AVOCADO_REGION_TOKENS.items():
            self.assertTrue(any(t in AVOCADO_PAGES[st] for t in tokens),
                            f"{st} avocado page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in AVOCADO_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, AVOCADO_PAGES[other],
                                     f"{owner} avocado token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in AVOCADO_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on avocado {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on avocado {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, AVOCADO_JSON, "avocado.json")

    def test_flower_types_and_root_rot_present(self):
        # Correctness guards specific to avocado: the A/B flowering split and
        # Phytophthora root rot are the two facts a grower most needs.
        for st in STATES:
            self.assertIn("Type A", AVOCADO_PAGES[st], f"{st} page missing Type A")
            self.assertIn("Type B", AVOCADO_PAGES[st], f"{st} page missing Type B")
            self.assertIn("Phytophthora", AVOCADO_PAGES[st], f"{st} page missing Phytophthora")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          AVOCADO_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(AVOCADO_JSON["core"]["faqs"]) + len(AVOCADO_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', AVOCADO_PAGES[st], f"{st} missing Sources")
        for s in AVOCADO_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in AVOCADO_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "avocado.org.au", "fao.org",
            )),
            "expected at least one gov/industry authority among the avocado sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in AVOCADO_JSON["sources"]}
        cited = set()
        for block in [AVOCADO_JSON["core"]] + list(AVOCADO_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "avocado guide cites an unknown source id")

    def test_sources_note_is_avocado_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", AVOCADO_PAGES[st])
            self.assertNotIn("Generic lychee blurb", AVOCADO_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', AVOCADO_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("avocado"))
        m = re.search(r'id="further-reading".*?</section>', AVOCADO_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("avocado")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("avocado").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("avocado", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
