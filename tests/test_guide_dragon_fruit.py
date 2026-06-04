"""
Dragon fruit growing-guide tests (tools/scrapers/growing_guides/dragon-fruit.json).
Flagship QLD by climate and commercial reality (Queensland and the NT grow most of
Australia's crop); every state still gets a genuinely unique overlay. In its own file
so parallel guide runs never collide on a shared test module.
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

DRAGON_SPECIES = {
    "common_name": "Dragon Fruit",
    "latin_name": "Selenicereus undatus",
    "description": "Generic dragon fruit blurb that should be replaced by the rich guide.",
    "slug": "dragon-fruit",
}


def _dragon_products(n=6):
    names = ["Aussie Gold", "American Beauty", "Dark Star", "Sugar Dragon", "Delight", "Physical Graffiti"]
    return [
        {"title": f"Dragon Fruit {names[i % len(names)]}",
         "url": f"https://nursery.example/dragon-fruit-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 25.0 + i * 4,
         "available": True, "species": DRAGON_SPECIES}
        for i in range(n)
    ]


DRAGON_PAGES = build_state_pages("dragon-fruit", _dragon_products())
DRAGON_JSON = load_guide("dragon-fruit")

# Region tokens chosen to be genuinely state-exclusive: each appears only in its own
# overlay (body or that state's cited Sources), never in the shared core, the shared
# Sources, or another state. (Note: "Capricornia" is NOT used here because it rides
# along in a core-cited source attribution, so it legitimately appears on every page.)
DRAGON_REGION_TOKENS = {
    "QLD": ["Atherton", "Burdekin"],
    "WA": ["Carnarvon", "Kununurra"],
    "NSW": ["Northern Rivers", "Coffs Harbour"],
    "VIC": ["Sunraysia", "Mildura"],
}


class DragonFruitGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in DRAGON_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} dragon fruit page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(DRAGON_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two dragon fruit state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in DRAGON_PAGES.items():
            self.assertNotIn("Generic dragon fruit blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in DRAGON_REGION_TOKENS.items():
            for t in tokens:
                self.assertIn(t, DRAGON_PAGES[st], f"{st} dragon fruit page missing region token '{t}'")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in DRAGON_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, DRAGON_PAGES[other],
                                     f"{owner} dragon fruit token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in DRAGON_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on dragon fruit {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on dragon fruit {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, DRAGON_JSON, "dragon-fruit.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          DRAGON_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(DRAGON_JSON["core"]["faqs"]) + len(DRAGON_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', DRAGON_PAGES[st], f"{st} missing Sources")
        for s in DRAGON_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in DRAGON_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "nt.gov.au", "dpir.nt.gov.au", "daf.nt.gov.au",
                "business.qld.gov.au", "dpird.wa.gov.au", "edis.ifas.ufl.edu",
            )),
            "expected at least one gov/extension authority among the dragon fruit sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in DRAGON_JSON["sources"]}
        cited = set()
        for block in [DRAGON_JSON["core"]] + list(DRAGON_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "dragon fruit guide cites an unknown source id")

    def test_sources_note_is_dragon_fruit_specific(self):
        # Must not have been copy-pasted from another species' guide.
        for st in STATES:
            self.assertNotIn("olive-industry", DRAGON_PAGES[st])
            self.assertNotIn("olive", DRAGON_JSON["sources_note"].lower())

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', DRAGON_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("dragon-fruit"))
        m = re.search(r'id="further-reading".*?</section>', DRAGON_PAGES["QLD"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        # Owned cross-links are followed (no nofollow), per the archives policy.
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("dragon-fruit")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_further_reading_is_dragon_fruit_specific_not_generic_cactus(self):
        # The RFCA "Pitaya" folder also holds off-topic Opuntia/prickly-pear articles
        # ("Cactus: source of perhaps the perfect fruit", "...Tuna Cactus", "Cactus
        # Cure for skin cancer"). The guide curates the pitaya-specific articles so
        # those never surface as dragon fruit "further reading".
        fr = re.search(r'id="further-reading".*?</section>', DRAGON_PAGES["QLD"], re.S).group(0)
        for off_topic in ("Tuna Cactus", "Perfect Fruit", "Cactus Cure", "Skin Cancer"):
            self.assertNotIn(off_topic, fr, f"off-topic cactus article '{off_topic}' surfaced as dragon fruit reading")

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("dragon-fruit").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("dragon-fruit", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    def test_key_horticulture_facts_present(self):
        # Lock the grower-critical, correctness-sensitive facts that the research
        # established: night-flowering and pollination, the non-climacteric harvest,
        # and the climbing-cactus support requirement.
        core = gg.render_species_guide("dragon-fruit")
        for needle in ("hand pollination", "non-climacteric", "climbing cactus", "self-incompatible"):
            self.assertIn(needle, core, f"core guide missing key fact: {needle!r}")


if __name__ == "__main__":
    unittest.main()
