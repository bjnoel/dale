"""
Lime growing-guide tests (tools/scrapers/growing_guides/lime.json). Lime is the first
citrus guide and a genuine four-state crop, but a very different one in each state: QLD is
the warm heartland (most of Australia's limes), NSW spans the biggest citrus region (Riverina)
and the best subtropical lime coast, WA is defined by citrus biosecurity, and VIC is at the
cold limit (pot-and-shelter country). So every state gets a real, distinct overlay. In its own
file so parallel guide runs never collide on a shared test module.
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

LIME_SPECIES = {
    "common_name": "Lime",
    "latin_name": "Citrus aurantiifolia",
    "description": "Generic lime blurb that should be replaced by the rich guide.",
    "slug": "lime",
}


def _lime_products(n=8):
    # Named lime types that are actually in live Australian nursery stock: the standard
    # Tahitian, the leaf crop makrut/kaffir, sweet and Rangpur (not true limes), and the
    # native desert/round limes. Titles deliberately carry no region words.
    names = ["Tahitian", "Kaffir", "Sweet", "Rangpur", "Desert", "Australian Round",
             "Dwarf Tahitian", "Red Centre"]
    return [
        {"title": f"Lime {names[i % len(names)]}",
         "url": f"https://nursery.example/lime-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 35.0 + i * 4,
         "available": True, "species": LIME_SPECIES}
        for i in range(n)
    ]


LIME_PAGES = build_state_pages("lime", _lime_products())
LIME_JSON = load_guide("lime")

# Region tokens unique to one state (the leak guard relies on these never appearing on
# another state's page, in prose OR in a cited source name).
LIME_REGION_TOKENS = {
    "WA": ["Carnarvon", "Gascoyne", "Kununurra"],
    "QLD": ["Gayndah", "Mundubbera", "Mareeba"],
    "NSW": ["Griffith", "Alstonville", "Coffs Harbour"],
    "VIC": ["Mildura", "Sunraysia", "Robinvale"],
}


class LimeGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in LIME_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} lime page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(LIME_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two lime state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in LIME_PAGES.items():
            self.assertNotIn("Generic lime blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in LIME_REGION_TOKENS.items():
            self.assertTrue(any(t in LIME_PAGES[st] for t in tokens),
                            f"{st} lime page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in LIME_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, LIME_PAGES[other],
                                     f"{owner} lime token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in LIME_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on lime {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on lime {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, LIME_JSON, "lime.json")

    def test_core_facts_present_on_every_state(self):
        # The facts a lime buyer most needs, carried by the shared core, so they appear on
        # every combo page: the standard variety, self-fertility, and the pick-green rule.
        for st in STATES:
            self.assertIn("Tahitian", LIME_PAGES[st], f"{st} page missing Tahitian")
            self.assertIn("self-fertile", LIME_PAGES[st], f"{st} page missing self-fertile note")
            self.assertIn("still green", LIME_PAGES[st], f"{st} page missing the pick-green rule")

    def test_correctness_tristeza_and_rangpur(self):
        # Two facts the research flagged as easy to get wrong: Tahitian is tristeza TOLERANT,
        # not "resistant"; Rangpur and sweet lime are NOT true limes.
        for st in STATES:
            self.assertIn("tolerance of tristeza", LIME_PAGES[st], f"{st} missing tristeza tolerance")
            self.assertNotIn("tristeza-resistant", LIME_PAGES[st], f"{st} overclaims tristeza resistance")
            self.assertNotIn("resistant to tristeza", LIME_PAGES[st], f"{st} overclaims tristeza resistance")
        self.assertIn("not true limes", LIME_PAGES["QLD"], "Rangpur/sweet lime should be flagged not true limes")

    def test_wa_biosecurity_and_pests_accurate(self):
        wa = LIME_PAGES["WA"]
        # The WA spine: import control + canker-free rationale, framed via the WAOL/permit system.
        self.assertIn("Organism List", wa, "WA page missing the WA Organism List import framing")
        self.assertIn("canker", wa, "WA page missing the citrus canker rationale")
        self.assertIn("Medfly", wa, "WA page missing Mediterranean fruit fly")
        # Correctness guard: WA is NOT free of citrus gall wasp (it is established in Perth),
        # so the page must name it as a present pest and must not claim freedom from it.
        self.assertIn("gall wasp", wa, "WA page should name citrus gall wasp (established in Perth)")
        self.assertNotIn("free of citrus gall wasp", wa)

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          LIME_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(LIME_JSON["core"]["faqs"]) + len(LIME_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', LIME_PAGES[st], f"{st} missing Sources")
        for s in LIME_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in LIME_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "citrusaustralia.com.au", "csiro.au",
            )),
            "expected at least one gov/industry authority among the lime sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in LIME_JSON["sources"]}
        cited = set()
        for block in [LIME_JSON["core"]] + list(LIME_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "lime guide cites an unknown source id")

    def test_sources_note_is_lime_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", LIME_PAGES[st])
            self.assertNotIn("Generic avocado blurb", LIME_PAGES[st])

    def test_species_links_resolve(self):
        # The guide links to the separate finger lime species page; every /species/ link
        # must be a real slug (no 404s).
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', LIME_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")
        self.assertIn("finger-lime",
                      set(re.findall(r'/species/([a-z0-9-]+)\.html', LIME_PAGES["NSW"])),
                      "expected a link to the separate finger lime page")

    def test_further_reading_owned_followed_and_merged(self):
        # Lime has no clean RFCA "Lime" folder and no lime-specific WANATCA yearbook article,
        # so Further reading is the hand-curated owned RFCA citrus articles (all followed).
        self.assertIn('id="further-reading"', gg.render_species_guide("lime"))
        m = re.search(r'id="further-reading".*?</section>', LIME_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://rfcarchives[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("lime")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("lime").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("lime", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
