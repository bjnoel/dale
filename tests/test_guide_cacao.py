"""
Cacao growing-guide tests (tools/scrapers/growing_guides/cacao.json). Flagship QLD by
climate: cacao is a true equatorial rainforest tree and crops in Australia ONLY on the wet
tropical coast of far north Queensland, so the WA/NSW/VIC overlays cover a tree that is a
glasshouse curiosity (or, in WA, a discontinued field trial) rather than a crop. In its own
file so parallel guide runs never collide on a shared test module.

The cacao-specific correctness checks the research pinned down:
  * cacao flowers by cauliflory (from cushions on the trunk) and is pollinated by tiny midges
    (Ceratopogonidae, Forcipomyia), NOT by bees, with only ~1 to 5% of flowers setting pods;
  * the beans have no chocolate flavour until fermented (the distinctive post-harvest step);
  * QLD is the only viable region (the eight-year NACDA research found the far north Qld sites
    best, with no major pest or disease problems), and Australia is free of the witches broom
    and frosty pod diseases and has eradicated the cocoa pod borer (found 2011, gone by 2014);
  * WA was actually trialled (Broome and Kununurra) and discontinued, so the WA page must say
    so and must never imply warm dry WA suits cacao.
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

CACAO_SPECIES = {
    "common_name": "Cacao",
    "latin_name": "Theobroma cacao",
    "description": "Generic cacao blurb that should be replaced by the rich guide.",
    "slug": "cacao",
}


def _cacao_products(n=6):
    names = ["SG2", "Trinitario", "Cocoa Tree", "Theobroma", "Seedling", "SG2 Grafted"]
    return [
        {"title": f"Cacao {names[i % len(names)]}",
         "url": f"https://nursery.example/cacao-{i}",
         "nursery_key": "ross-creek", "nursery_name": "Ross Creek Tropicals",
         "price": 39.0 + i * 10, "available": True, "species": CACAO_SPECIES}
        for i in range(n)
    ]


CACAO_PAGES = build_state_pages("cacao", _cacao_products())
CACAO_JSON = load_guide("cacao")

# Tokens chosen to live ONLY in their own state overlay (and that state's climate note),
# never in the shared core or in a cited source's name (which would render on every page).
CACAO_REGION_TOKENS = {
    "QLD": ["Mossman", "Innisfail"],
    "WA": ["Broome", "Kununurra"],
    "NSW": ["Northern Rivers", "Tweed"],
    "VIC": ["Melbourne"],
}


class CacaoGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in CACAO_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} cacao page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(CACAO_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two cacao state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in CACAO_PAGES.items():
            self.assertNotIn("Generic cacao blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in CACAO_REGION_TOKENS.items():
            self.assertTrue(any(t in CACAO_PAGES[st] for t in tokens),
                            f"{st} cacao page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in CACAO_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, CACAO_PAGES[other],
                                     f"{owner} cacao token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in CACAO_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on cacao {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on cacao {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, CACAO_JSON, "cacao.json")

    def test_climate_note_present_and_dash_free(self):
        # cacao has its own climate category; every state must carry a (dash-free) note.
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["cacao"], "cacao")
        for st in STATES:
            note = bssp.STATE_CLIMATE_NOTES[st]["cacao"]
            self.assertTrue(note)
            self.assertNotIn(EM_DASH, note)
            self.assertNotIn(EN_DASH, note)

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          CACAO_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(CACAO_JSON["core"]["faqs"]) + len(CACAO_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', CACAO_PAGES[st], f"{st} missing Sources")
        for s in CACAO_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in CACAO_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "era.dpi.qld.gov.au", "nt.gov.au", "business.qld.gov.au", "agrifutures.com.au",
            )),
            "expected at least one gov/industry authority among the cacao sources",
        )

    def test_owned_archives_are_cited(self):
        # First-party preference: the RFCA processing article and the WANATCA Quandong
        # cacao issue are both used, so first-party authority leads the source list.
        domains = " ".join(s["url"] for s in CACAO_JSON["sources"])
        self.assertIn("rfcarchives.org.au", domains, "RFCA archive source missing")
        self.assertIn("wanatca.org.au", domains, "WANATCA source missing")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in CACAO_JSON["sources"]}
        cited = set()
        for block in [CACAO_JSON["core"]] + list(CACAO_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "cacao guide cites an unknown source id")

    def test_sources_note_is_cacao_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", CACAO_PAGES[st])
            self.assertNotIn("Generic cacao blurb", CACAO_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', CACAO_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_cauliflory_and_low_fruit_set_in_core(self):
        # Distinctive cacao botany: flowers from cushions on the trunk (cauliflory) and a very
        # low natural fruit set. The shared core must carry both so every page states them.
        sp = gg.render_species_guide("cacao").lower()
        self.assertIn("cauliflory", sp)
        self.assertIn("trunk", sp)

    def test_pollinated_by_midges_not_bees(self):
        # Correctness: cacao is pollinated by tiny Ceratopogonidae midges (Forcipomyia), not
        # by bees. The core must say midges and must never claim bees are the pollinator.
        sp = gg.render_species_guide("cacao").lower()
        self.assertIn("midge", sp)
        self.assertTrue("ceratopogonidae" in sp or "forcipomyia" in sp)
        self.assertNotIn("pollinated by bees", sp)

    def test_fermentation_is_required_for_flavour(self):
        # The distinctive post-harvest fact (RFCA processing article): raw beans have no
        # chocolate flavour; fermentation creates it. Lock it so the advice cannot drift.
        sp = gg.render_species_guide("cacao").lower()
        self.assertIn("ferment", sp)
        self.assertIn("no chocolate flavour", sp)

    def test_qld_is_the_viable_region_with_no_major_disease(self):
        qld = CACAO_PAGES["QLD"]
        self.assertIn("no major pest or disease", qld)
        self.assertIn("witches broom", qld)
        self.assertIn("eradicated", qld)  # cocoa pod borer, found 2011, gone by 2014

    def test_wa_trials_were_discontinued(self):
        # WA was actually trialled and failed; the WA page must say so, not imply warm dry
        # WA suits cacao. Broome and Kununurra are the WA trial sites.
        wa = CACAO_PAGES["WA"]
        self.assertIn("discontinued", wa)
        self.assertIn("Broome", wa)
        self.assertIn("Kununurra", wa)

    def test_cool_states_cross_link_to_hardier_fruit(self):
        # NSW and VIC cannot crop cacao, so each points the reader to a hardier alternative:
        # NSW to the black sapote (the chocolate pudding fruit), VIC to feijoa/tamarillo.
        self.assertIn("/species/black-sapote.html", CACAO_PAGES["NSW"])
        self.assertTrue("/species/feijoa.html" in CACAO_PAGES["VIC"]
                        or "/species/tamarillo.html" in CACAO_PAGES["VIC"])

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("cacao"))
        m = re.search(r'id="further-reading".*?</section>', CACAO_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("cacao")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("cacao").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("cacao", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
