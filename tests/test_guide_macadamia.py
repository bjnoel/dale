"""
Macadamia growing-guide tests (tools/scrapers/growing_guides/macadamia.json). Macadamia is
a genuine native crop with a real story in every state, so each gets a distinct overlay: WA
(the Mediterranean southwest, irrigation/fertigation, the long backyard history, and the
plant-import quarantine angle), QLD (Bundaberg now the biggest region, the Mount Bauple
heartland), NSW (the Northern Rivers birthplace around Lismore), and VIC (not commercial,
frost the limit). In its own file so parallel guide runs never collide on a shared module.

Macadamia-specific correctness guards worth keeping (facts a grower must get right):
  * The macadamia felted coccid is a NATIVE Australian scale, usually minor here (held down by
    natural enemies); it is the destructive INVADER overseas. It must NOT be called "the main
    pest in Australia" (the old fruit_species.json blurb did). The real flagship insect pest is
    the macadamia nut borer.
  * The hard, woody shell means the macadamia is NOT a fruit fly host. No page may claim it is.
  * Phosphorus: the cluster roots dislike a large EXCESS of phosphorus, but it is a myth that a
    macadamia must never be fed phosphorus (commercial orchards do, guided by soil tests). The
    guide states the correction.
  * Most cultivars are self-incompatible, so cross-pollination (a second variety) lifts the crop.
  * Only Macadamia integrifolia, M. tetraphylla and their hybrids are edible; the nuts are toxic
    to dogs.
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

MACADAMIA_SPECIES = {
    "common_name": "Macadamia",
    "latin_name": "Macadamia integrifolia",
    "description": "Generic macadamia blurb that should be replaced by the rich guide.",
    "slug": "macadamia",
}


def _macadamia_products(n=8):
    # Named varieties that are actually in live Australian nursery stock: the backyard hybrid
    # (Beaumont), the patented Australian "A" selections (A4, A16, A38, A203), an older Hawaiian
    # number (816, 849) and Daddow. None of these contain a region token.
    names = ["Beaumont", "A4", "A16", "A38", "816", "Daddow", "A203", "849"]
    return [
        {"title": f"Macadamia {names[i % len(names)]}",
         "url": f"https://nursery.example/macadamia-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 39.0 + i * 4,
         "available": True, "species": MACADAMIA_SPECIES}
        for i in range(n)
    ]


MAC_PAGES = build_state_pages("macadamia", _macadamia_products())
MAC_JSON = load_guide("macadamia")

# Region tokens unique to one state (the leak guard relies on this). All chosen to be
# unambiguous place names that appear in only one state's overlay (not in product titles,
# nursery names, source names, or page chrome). "Perth" is avoided (footer); "Margaret River"
# and "Busselton" are WA-only but not used as tokens; QLD's "Beerwah" appears in the core
# (breeding-program origin) so it is not a state-unique token.
MAC_REGION_TOKENS = {
    "WA": ["Chittering", "Quindalup", "Cowaramup"],
    "QLD": ["Bundaberg", "Gympie", "Mount Bauple"],
    "NSW": ["Lismore", "Alstonville", "Nambucca"],
    "VIC": ["Melbourne", "Gippsland"],
}


class MacadamiaGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in MAC_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} macadamia page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(MAC_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two macadamia state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in MAC_PAGES.items():
            self.assertNotIn("Generic macadamia blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in MAC_REGION_TOKENS.items():
            self.assertTrue(any(t in MAC_PAGES[st] for t in tokens),
                            f"{st} macadamia page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in MAC_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, MAC_PAGES[other],
                                     f"{owner} macadamia token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in MAC_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on macadamia {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on macadamia {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, MAC_JSON, "macadamia.json")

    # --- correctness guards -------------------------------------------------

    def test_felted_coccid_not_called_main_pest(self):
        # The native felted coccid must be framed as usually minor (held down by natural
        # enemies), never as "the main pest" the way the old blurb had it.
        for st in ("QLD", "NSW"):
            self.assertIn("felted coccid", MAC_PAGES[st], f"{st} should still name the felted coccid")
            self.assertIn("natural enemies", MAC_PAGES[st],
                          f"{st} must frame the felted coccid as held in check by natural enemies")
        # The QLD page names the real flagship insect pest.
        self.assertIn("main insect pest is the macadamia nut borer", MAC_PAGES["QLD"],
                      "QLD page should name the nut borer as the main insect pest")
        for st in STATES:
            self.assertNotIn("felted coccid; monitor", MAC_PAGES[st],
                             f"{st} must not carry the old blurb's felted-coccid line")

    def test_macadamia_is_not_a_fruit_fly_host(self):
        # The hard shell makes it a non-host; no page may claim otherwise.
        self.assertIn("not a host of Queensland fruit fly", MAC_PAGES["QLD"],
                      "QLD page should state the macadamia is not a fruit fly host")
        self.assertIn("not a fruit fly host", MAC_PAGES["NSW"],
                      "NSW page should state the macadamia is not a fruit fly host")
        for st in STATES:
            self.assertNotIn("is a host of Queensland fruit fly", MAC_PAGES[st],
                             f"{st} must not claim the macadamia IS a fruit fly host")

    def test_phosphorus_myth_corrected(self):
        for st in STATES:
            self.assertIn("cluster roots", MAC_PAGES[st], f"{st} page missing the cluster-root note")
            self.assertIn("myth that a macadamia must never see phosphorus", MAC_PAGES[st],
                          f"{st} page must correct the phosphorus myth")
            self.assertNotIn("specifically formulated for Australian native plants", MAC_PAGES[st],
                             f"{st} must not repeat the old blurb's low-P native-fertiliser claim verbatim")

    def test_pollination_basics_present(self):
        for st in STATES:
            self.assertIn("self-incompatible", MAC_PAGES[st], f"{st} page missing pollination basics")
            self.assertIn("cross-pollination", MAC_PAGES[st], f"{st} page missing cross-pollination")

    def test_two_species_named(self):
        for st in STATES:
            self.assertIn("Macadamia integrifolia", MAC_PAGES[st], f"{st} page missing integrifolia")
            self.assertIn("Macadamia tetraphylla", MAC_PAGES[st], f"{st} page missing tetraphylla")

    def test_dog_toxicity_and_native_heritage(self):
        for st in STATES:
            self.assertIn("toxic to dogs", MAC_PAGES[st], f"{st} page missing the dog-toxicity safety note")
            self.assertIn("major commercial food crop", MAC_PAGES[st],
                          f"{st} page missing the native-heritage hook")

    def test_marquee_state_facts(self):
        # WA: Mediterranean climate, irrigation, the long backyard history, and the quarantine.
        self.assertIn("Mediterranean", MAC_PAGES["WA"], "WA page missing the Mediterranean climate framing")
        self.assertIn("Kings Park", MAC_PAGES["WA"], "WA page missing the long WA backyard history")
        self.assertIn("Western Australian Organism List", MAC_PAGES["WA"], "WA page missing the quarantine detail")
        # QLD: Bundaberg overtook NSW in 2016; Mount Bauple the ancestral home.
        self.assertIn("2016", MAC_PAGES["QLD"], "QLD page missing the Bundaberg-overtakes-NSW year")
        # NSW: the industry was born at Lismore in the 1880s.
        self.assertIn("1880s", MAC_PAGES["NSW"], "NSW page missing the industry's birth date")
        self.assertIn("Rous Mill", MAC_PAGES["NSW"], "NSW page missing the historic Rous Mill plantings")
        # VIC: not a commercial crop.
        self.assertIn("no commercial macadamia industry", MAC_PAGES["VIC"],
                      "VIC page should say there is no commercial industry")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          MAC_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(MAC_JSON["core"]["faqs"]) + len(MAC_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', MAC_PAGES[st], f"{st} missing Sources")
        for s in MAC_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in MAC_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "era.dpi.qld.gov.au",
                "australian-macadamias.org", "australianmacadamias.org",
            )),
            "expected at least one gov/industry authority among the macadamia sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in MAC_JSON["sources"]}
        cited = set()
        for block in [MAC_JSON["core"]] + list(MAC_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "macadamia guide cites an unknown source id")

    def test_sources_note_is_macadamia_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", MAC_PAGES[st])
            self.assertNotIn("Generic", MAC_PAGES[st])
        self.assertIn("Australian Macadamia Society", MAC_JSON["sources_note"])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', MAC_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")
            self.assertIn("pecan", linked, f"{st} should cross-link to the nut cousin /species/pecan.html")

    def test_further_reading_owned_followed_and_merged(self):
        # Macadamia has no RFCA "Macadamia" folder, so the archive index adds nothing and the
        # further reading is the hand-curated owned WANATCA + RFCA-Nuts links only. They must be
        # followed (owned), and the rendered count must match the merged list.
        self.assertIn('id="further-reading"', gg.render_species_guide("macadamia"))
        m = re.search(r'id="further-reading".*?</section>', MAC_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("macadamia")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("macadamia").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("macadamia", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
