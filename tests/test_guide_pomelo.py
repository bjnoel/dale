"""
Pomelo growing-guide tests (tools/scrapers/growing_guides/pomelo.json). Flagship QLD
(pomelo is the most heat- and humidity-tolerant citrus and the named-variety trade is
overwhelmingly Queensland-based), with strong WA/NSW/VIC overlays. In its own file so
parallel guide runs never collide on a shared test module.

Beyond the shared guards (per-state uniqueness, no dashes, FAQ JSON-LD, https sources,
further reading), this file pins the correctness calls the research turned up, so a future
edit cannot quietly reintroduce the errors:
  * Pomelo is the PARENT of grapefruit (grapefruit = pummelo x sweet orange), not a big
    grapefruit.
  * Pomelo carries the same furanocoumarin drug interaction as grapefruit (a safety point).
  * Pomelo self-fertility is CULTIVAR-dependent: some Asian pummelos are self-incompatible,
    so the blanket citrus "one tree is enough" is not the whole story.
  * Pomelo is BOTH the most heat-tolerant AND the most frost-tender of the common citrus,
    which is why it gets its own climate category instead of the generic "citrus" note (the
    generic VIC citrus note even recommends lemon cultivars, wrong on a pomelo page).
  * Citrus canker: Emerald QLD 2004 (eradicated) and the SEPARATE 2018 NT/WA outbreak
    (Australia declared free April 2021) are two distinct events, not one.
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

POMELO_SPECIES = {
    "common_name": "Pomelo",
    "latin_name": "Citrus maxima",
    "description": "Generic pomelo blurb that should be replaced by the rich guide.",
    "slug": "pomelo",
}


def _pomelo_products(n=8):
    # Real in-stock pummelo cultivars, deliberately free of any region token so the
    # product table cannot trip the region-leak guard below.
    names = ["Carters Red", "Nam Roi", "Flicks Yellow", "Thai Gold K13",
             "Red Rouge", "Tahitian", "K15", "Chandler"]
    return [
        {"title": f"Pummelo {names[i % len(names)]}",
         "url": f"https://nursery.example/pomelo-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 39.0 + i * 3,
         "available": True, "species": POMELO_SPECIES}
        for i in range(n)
    ]


POMELO_PAGES = build_state_pages("pomelo", _pomelo_products())
POMELO_JSON = load_guide("pomelo")

# Pure place-name region tokens, unique per state, none of which is a citrus cultivar name
# or a substring of common prose (Perth is excluded: it lives in the site footer chrome).
POMELO_REGION_TOKENS = {
    "QLD": ["Central Burnett", "Gayndah", "Mundubbera", "Mareeba"],
    "WA": ["Carnarvon", "Gascoyne", "Gingin", "Kununurra"],
    "NSW": ["Alstonville", "Tweed", "Lismore"],
    "VIC": ["Sunraysia", "Mildura", "Goulburn"],
}


class PomeloGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in POMELO_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} pomelo page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(POMELO_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two pomelo state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in POMELO_PAGES.items():
            self.assertNotIn("Generic pomelo blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in POMELO_REGION_TOKENS.items():
            self.assertTrue(any(t in POMELO_PAGES[st] for t in tokens),
                            f"{st} pomelo page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in POMELO_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, POMELO_PAGES[other],
                                     f"{owner} pomelo token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in POMELO_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on pomelo {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on pomelo {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, POMELO_JSON, "pomelo.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          POMELO_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(POMELO_JSON["core"]["faqs"]) + len(POMELO_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', POMELO_PAGES[st], f"{st} missing Sources")
        for s in POMELO_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in POMELO_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "citrusaustralia.com.au",
            )),
            "expected at least one gov/industry authority among the pomelo sources",
        )

    def test_no_bot_blocked_gov_sources(self):
        # NSW DPI and Agriculture Victoria return HTTP 403 to automated fetchers, so the
        # "every cited URL must curl 200" rule means they must not be cited directly. The
        # NSW and VIC facts are anchored on Citrus Australia, Yates, SGA, Leaf Root Fruit
        # and North West Farmer instead. Keep it that way.
        for s in POMELO_JSON["sources"]:
            self.assertNotIn("dpi.nsw.gov.au", s["url"], f"NSW DPI 403s to curl: {s['url']}")
            self.assertNotIn("agriculture.vic.gov.au", s["url"], f"Ag Vic 403s to curl: {s['url']}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in POMELO_JSON["sources"]}
        cited = set()
        for block in [POMELO_JSON["core"]] + list(POMELO_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "pomelo guide cites an unknown source id")

    def test_no_dead_sources(self):
        # Every listed source should actually be cited by a section (the renderer only
        # shows cited sources, so an uncited source is dead weight).
        src_ids = {s["id"] for s in POMELO_JSON["sources"]}
        cited = set()
        for block in [POMELO_JSON["core"]] + list(POMELO_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(src_ids - cited, set(), "pomelo guide lists a source it never cites")

    def test_sources_note_is_pomelo_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", POMELO_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', POMELO_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("pomelo"))
        m = re.search(r'id="further-reading".*?</section>', POMELO_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("pomelo")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_further_reading_has_pummelo_specific_articles(self):
        # The hand-curated, first-party further reading should lead with the pummelo-specific
        # archive articles (RFCA "The Pummelo" + WANATCA "Pummelos in California"), not just
        # generic citrus links.
        fr_urls = [e["url"] for e in gg.get_further_reading("pomelo")]
        self.assertTrue(any("Pummelo3-87" in u for u in fr_urls), "RFCA pummelo article missing")
        self.assertTrue(any("Y24all.pdf" in u for u in fr_urls), "WANATCA Pummelos in California missing")

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("pomelo").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("pomelo", "QLD").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the QLD overlay should add cited sources beyond the core")

    # --- pomelo-specific correctness guards -------------------------------------------

    def test_pomelo_is_the_parent_of_grapefruit(self):
        # The defining botanical fact: pomelo is the ANCESTOR grapefruit was bred from,
        # not a big grapefruit. Guard against getting the relationship backwards.
        species = gg.render_species_guide("pomelo").lower()
        self.assertIn("grapefruit", species)
        self.assertTrue("bred from" in species or "came first" in species,
                        "core should say grapefruit was bred from pomelo, not the reverse")

    def test_drug_interaction_is_flagged(self):
        # Safety: pomelo carries the same grapefruit-type medication interaction. This must
        # survive on the page (eating section + FAQ), with the mechanism and the advice.
        species = gg.render_species_guide("pomelo").lower()
        self.assertIn("furanocoumarin", species)
        self.assertIn("pharmacist", species)

    def test_self_fertility_is_cultivar_dependent(self):
        # Not the blanket citrus "one tree is enough": some Asian pummelos are
        # self-incompatible, so the guide must carry the nuance.
        species = gg.render_species_guide("pomelo").lower()
        self.assertIn("self incompatible", species)

    def test_pomelo_is_frost_tender_and_heat_loving(self):
        # The two facts that earn pomelo its own climate category.
        species = gg.render_species_guide("pomelo").lower()
        self.assertIn("frost tender", species)
        self.assertIn("heat", species)

    def test_climate_category_is_pomelo_not_generic_citrus(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["pomelo"], "pomelo")
        for st in STATES:
            self.assertIn("pomelo", bssp.STATE_CLIMATE_NOTES[st],
                          f"{st} is missing a pomelo-specific climate note")
        # The generic citrus VIC note recommends lemon cultivars; the pomelo note must not.
        self.assertNotIn("Meyer", bssp.STATE_CLIMATE_NOTES["VIC"]["pomelo"])
        for st in STATES:
            note = bssp.STATE_CLIMATE_NOTES[st]["pomelo"]
            self.assertNotIn(EM_DASH, note)
            self.assertNotIn(EN_DASH, note)

    def test_wa_pest_is_medfly(self):
        wa = POMELO_PAGES["WA"]
        self.assertIn("Mediterranean fruit fly", wa,
                      "WA's headline citrus pest is Mediterranean fruit fly, not Qfly")

    def test_wa_does_not_claim_gall_wasp_free(self):
        wa = POMELO_PAGES["WA"]
        self.assertNotIn("free of citrus gall wasp", wa.lower(),
                         "WA is NOT free of citrus gall wasp (it is in Perth backyards)")
        self.assertIn("commercial orchards", wa,
                      "WA overlay should note gall wasp is absent from commercial orchards")

    def test_qld_canker_history_distinguishes_2004_and_2018(self):
        qld = POMELO_PAGES["QLD"]
        self.assertIn("Emerald in 2004", qld, "QLD canker outbreak was Emerald 2004")
        self.assertIn("2021", qld, "Australia was declared free of citrus canker in 2021")
        # The 2018 outbreak was the Northern Territory and WA, never Emerald. Guard against
        # conflating the two events.
        self.assertNotIn("Emerald in 2018", qld, "do not pin a 2018 outbreak on Emerald")
        self.assertIn("Northern Territory", qld,
                      "the 2018 outbreak should be attributed to the NT (and WA)")

    def test_qld_only_shipping_is_explained(self):
        qld = POMELO_PAGES["QLD"]
        self.assertIn("Queensland only", qld,
                      "the QLD page should explain the common 'Queensland only' listing")

    def test_harvest_is_autumn_into_winter(self):
        # The fruit_species.json blurb said "May to August"; the verified window is
        # autumn into winter. Every state overlay should speak to an autumn/winter harvest.
        for st in STATES:
            self.assertIn("autumn", POMELO_PAGES[st].lower(), f"{st} harvest should be autumn-centred")

    def test_varieties_tie_to_real_stock(self):
        species = gg.render_species_guide("pomelo")
        self.assertIn("Carter's Red", species)
        self.assertIn("Nam Roi", species)


if __name__ == "__main__":
    unittest.main()
