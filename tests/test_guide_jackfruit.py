"""
Jackfruit growing-guide tests (tools/scrapers/growing_guides/jackfruit.json). Flagship QLD
(tropical wet north); NSW is the frost-limited southern margin, VIC is not a field crop, WA
is the tropical-north plus a Perth pot/glasshouse curiosity. In its own file so parallel
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

JACKFRUIT_SPECIES = {
    "common_name": "Jackfruit",
    "latin_name": "Artocarpus heterophyllus",
    "description": "Generic jackfruit blurb that should be replaced by the rich guide.",
    "slug": "jackfruit",
}


def _jackfruit_products(n=6):
    # Real, in-stock Australian cultivars; none contain a state region token (which would
    # otherwise render on every state page and trip the leak guard).
    names = ["Galaxy", "Black Gold", "Honey Gold", "Cheena", "Cosmic Gold", "J33"]
    return [
        {"title": f"Jackfruit {names[i % len(names)]}",
         "url": f"https://nursery.example/jackfruit-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 39.0 + i * 10,
         "available": True, "species": JACKFRUIT_SPECIES}
        for i in range(n)
    ]


JACKFRUIT_PAGES = build_state_pages("jackfruit", _jackfruit_products())
JACKFRUIT_JSON = load_guide("jackfruit")

# Each token must appear ONLY on its own state's page (per-state-unique overlays).
# Tokens are pure place names, NOT cultivar names: "Kyogle Gold" and "Tweed Crisp" are real
# in-stock cultivars, so "Kyogle"/"Tweed" would also show up in the product table on any
# state's page and make a poor leak guard. Murwillumbah/Lismore have no such collision.
JACKFRUIT_REGION_TOKENS = {
    "QLD": ["Atherton", "Innisfail"],
    "WA": ["Kununurra", "Carnarvon"],
    "NSW": ["Northern Rivers", "Murwillumbah"],
    "VIC": ["Melbourne", "Mildura"],
}


class JackfruitGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in JACKFRUIT_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} jackfruit page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(JACKFRUIT_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two jackfruit state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in JACKFRUIT_PAGES.items():
            self.assertNotIn("Generic jackfruit blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in JACKFRUIT_REGION_TOKENS.items():
            self.assertTrue(any(t in JACKFRUIT_PAGES[st] for t in tokens),
                            f"{st} jackfruit page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in JACKFRUIT_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, JACKFRUIT_PAGES[other],
                                     f"{owner} jackfruit token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in JACKFRUIT_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on jackfruit {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on jackfruit {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, JACKFRUIT_JSON, "jackfruit.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          JACKFRUIT_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(JACKFRUIT_JSON["core"]["faqs"]) + len(JACKFRUIT_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', JACKFRUIT_PAGES[st], f"{st} missing Sources")
        for s in JACKFRUIT_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in JACKFRUIT_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "nt.gov.au", "ask.ifas.ufl.edu", "dpird.wa.gov.au", "bom.gov.au",
                "agrifutures.com.au",
            )),
            "expected at least one gov/industry authority among the jackfruit sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in JACKFRUIT_JSON["sources"]}
        cited = set()
        for block in [JACKFRUIT_JSON["core"]] + list(JACKFRUIT_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "jackfruit guide cites an unknown source id")

    def test_sources_note_is_jackfruit_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", JACKFRUIT_PAGES[st])
            self.assertNotIn("Generic", JACKFRUIT_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', JACKFRUIT_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("jackfruit"))
        m = re.search(r'id="further-reading".*?</section>', JACKFRUIT_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("jackfruit")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("jackfruit").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("jackfruit", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    # --- Jackfruit-specific correctness guards (lock in the adversarially verified facts) ---

    def test_qff_is_not_claimed_as_a_pest(self):
        # Adversarially verified: Queensland fruit fly does NOT attack jackfruit (thick rind,
        # absent from B. tryoni host lists). Guard against a future copy edit re-adding it.
        self.assertIn("not a recorded pest of jackfruit", JACKFRUIT_PAGES["QLD"])

    def test_self_fruitful_one_tree(self):
        core = gg.render_species_guide("jackfruit")
        self.assertIn("single tree will set fruit", core)

    def test_feeding_has_a_cited_rate(self):
        # Rollout v2 rule: water/feeding must carry a real, cited fertiliser figure.
        core = gg.render_species_guide("jackfruit")
        self.assertIn("113 grams", core)


if __name__ == "__main__":
    unittest.main()
