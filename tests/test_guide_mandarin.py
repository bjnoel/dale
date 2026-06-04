"""
Mandarin growing-guide tests (tools/scrapers/growing_guides/mandarin.json). Mandarin is a
genuine four-state citrus crop (WA south-west + Gascoyne, QLD Central Burnett, NSW Riverina,
VIC Sunraysia), so every state gets a real, distinct overlay. The distinctive correctness
facts for mandarin are the pollination/seediness nuance (parthenocarpy; self-incompatible
varieties go seedy when cross-pollinated), the WA citrus-import quarantine, the citrus canker
biosecurity history, and Medfly-in-WA vs Queensland-fruit-fly-in-the-east. In its own file so
parallel guide runs never collide on a shared test module.
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

MANDARIN_SPECIES = {
    "common_name": "Mandarin",
    "latin_name": "Citrus reticulata",
    "description": "Generic mandarin blurb that should be replaced by the rich guide.",
    "slug": "mandarin",
}


def _mandarin_products(n=7):
    # Named varieties that are actually in live Australian nursery stock: the early
    # Imperial and Satsuma, the large Emperor, late Hickson/Ellendale/Afourer/Honey Murcott.
    names = ["Imperial", "Emperor", "Hickson", "Afourer", "Honey Murcott", "Ellendale",
             "Satsuma Okitsu Wase"]
    return [
        {"title": f"Mandarin {names[i % len(names)]}",
         "url": f"https://nursery.example/mandarin-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 35.0 + i * 5,
         "available": True, "species": MANDARIN_SPECIES}
        for i in range(n)
    ]


MANDARIN_PAGES = build_state_pages("mandarin", _mandarin_products())
MANDARIN_JSON = load_guide("mandarin")

# Region tokens that are unique to one state (the leak guard relies on this). Chosen to be
# pure place names that appear nowhere else: NOT "Emerald" (it rides along in the QLD canker
# history and as the "Emerald Green" satsuma marketing term), NOT "Perth" (site footer),
# NOT "Sunraysia" on the NSW page (Sunraysia spans the VIC/NSW border, kept to VIC here).
MANDARIN_REGION_TOKENS = {
    "WA": ["Gingin", "Harvey", "Carnarvon"],
    "QLD": ["Gayndah", "Mundubbera", "Mareeba"],
    "NSW": ["Griffith", "Leeton", "Hillston"],
    "VIC": ["Sunraysia", "Mildura", "Robinvale"],
}


class MandarinGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in MANDARIN_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} mandarin page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(MANDARIN_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two mandarin state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in MANDARIN_PAGES.items():
            self.assertNotIn("Generic mandarin blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in MANDARIN_REGION_TOKENS.items():
            self.assertTrue(any(t in MANDARIN_PAGES[st] for t in tokens),
                            f"{st} mandarin page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in MANDARIN_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, MANDARIN_PAGES[other],
                                     f"{owner} mandarin token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in MANDARIN_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on mandarin {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on mandarin {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, MANDARIN_JSON, "mandarin.json")

    def test_pollination_and_seediness_nuance_present(self):
        # The defining mandarin fact: a single tree fruits without pollination
        # (parthenocarpy), but self-incompatible varieties go seedy when cross-pollinated
        # by nearby citrus. This must appear on every state page (it is in the core).
        for st in STATES:
            self.assertIn("parthenocarpy", MANDARIN_PAGES[st], f"{st} page missing parthenocarpy")
            self.assertIn("self-incompatible", MANDARIN_PAGES[st], f"{st} page missing self-incompatible")
            self.assertIn("seedy", MANDARIN_PAGES[st], f"{st} page missing the seediness nuance")
            self.assertIn("Afourer", MANDARIN_PAGES[st], f"{st} page missing the Afourer example")

    def test_grafted_rootstock_and_dwarfing_present(self):
        # Correctness: mandarins are grafted onto a rootstock, not grown from seed; Flying
        # Dragon is the dwarfing rootstock for pots.
        for st in STATES:
            self.assertIn("rootstock", MANDARIN_PAGES[st], f"{st} page missing rootstock")
            self.assertIn("Flying Dragon", MANDARIN_PAGES[st], f"{st} page missing Flying Dragon")

    def test_wa_quarantine_and_canker_history(self):
        # The WA story is the citrus-import quarantine; QLD carries the citrus canker history.
        self.assertIn("WA Organism List", MANDARIN_PAGES["WA"], "WA page missing the import quarantine")
        self.assertIn("citrus canker", MANDARIN_PAGES["QLD"], "QLD page missing the citrus canker history")

    def test_fruit_fly_is_state_correct(self):
        # WA has Mediterranean fruit fly (not Queensland fruit fly); the eastern states have
        # Queensland fruit fly. Getting this wrong is a real correctness failure.
        self.assertIn("Mediterranean fruit fly", MANDARIN_PAGES["WA"], "WA page missing Medfly")
        for st in ("QLD", "NSW", "VIC"):
            self.assertIn("Queensland fruit fly", MANDARIN_PAGES[st], f"{st} page missing QFF")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          MANDARIN_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(MANDARIN_JSON["core"]["faqs"]) + len(MANDARIN_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', MANDARIN_PAGES[st], f"{st} missing Sources")
        for s in MANDARIN_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in MANDARIN_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "citrusaustralia.com.au",
            )),
            "expected at least one gov/industry authority among the mandarin sources",
        )

    def test_no_bot_blocked_gov_sources(self):
        # dpi.nsw.gov.au and agriculture.vic.gov.au 403 to a plain fetch, so they cannot
        # satisfy the URL-200 gate (docs/species-guide-rollout.md step 5). The NSW/VIC
        # facts here are anchored on Citrus Australia (region pages return 200) and other
        # clean-200 authorities instead. Same guard the orange guide uses.
        for s in MANDARIN_JSON["sources"]:
            for blocked in ("dpi.nsw.gov.au", "agriculture.vic.gov.au"):
                self.assertNotIn(blocked, s["url"],
                                 f"{blocked} 403s to fetch and fails the URL-200 gate: {s['id']}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in MANDARIN_JSON["sources"]}
        cited = set()
        for block in [MANDARIN_JSON["core"]] + list(MANDARIN_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "mandarin guide cites an unknown source id")

    def test_sources_note_is_mandarin_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", MANDARIN_PAGES[st])
            self.assertNotIn("Generic avocado blurb", MANDARIN_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', MANDARIN_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("mandarin"))
        m = re.search(r'id="further-reading".*?</section>', MANDARIN_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("mandarin")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("mandarin").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("mandarin", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
