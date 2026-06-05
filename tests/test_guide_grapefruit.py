"""
Grapefruit growing-guide tests (tools/scrapers/growing_guides/grapefruit.json). Flagship WA
(treestock's core audience, plus WA's unique grapefruit story: the Gascoyne/Carnarvon early
citrus district, the Kununurra dry tropics, the quarantine wall and a different fruit fly),
with strong QLD/NSW/VIC overlays. In its own file so parallel guide runs never collide on a
shared test module.

Grapefruit is deliberately NOT in the generic "citrus" climate category: it is the citrus that
needs the most heat to sweeten, so it has its own SPECIES_CLIMATE_CATEGORY entry and per-state
climate notes. These tests pin the calls the research turned up, so a future edit cannot quietly
reintroduce an error:
  * The defining fact: grapefruit needs the most heat of any common citrus; cool, short-summer
    districts give sour, thick-skinned fruit. The cool-climate fix is Wheeny (an Australian
    variety, lower heat requirement), so VIC must read as marginal, not as prime grapefruit country.
  * WA's headline citrus pest is Mediterranean fruit fly, NOT Queensland fruit fly, and WA is NOT
    "free of citrus gall wasp" (it is in Perth backyards but absent from WA commercial orchards).
  * Queensland's citrus canker outbreak was Emerald 2004 (eradicated; Australia declared free 2021),
    NOT a 2018 Emerald outbreak (2018 was Darwin NT and Kununurra/Wyndham WA).
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

GRAPEFRUIT_SPECIES = {
    "common_name": "Grapefruit",
    "latin_name": "Citrus paradisi",
    "description": "Generic grapefruit blurb that should be replaced by the rich guide.",
    "slug": "grapefruit",
}


def _grapefruit_products(n=8):
    # Real in-stock grapefruit cultivars, free of any region token so the product table
    # cannot trip the region-leak guard below.
    names = ["Marsh", "Rio Red", "Star Ruby", "Flame", "Ruby Blush",
             "Thompson Pink", "Wheeny", "Oroblanco"]
    return [
        {"title": f"Grapefruit {names[i % len(names)]}",
         "url": f"https://nursery.example/grapefruit-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 36.0 + i * 3,
         "available": True, "species": GRAPEFRUIT_SPECIES}
        for i in range(n)
    ]


GRAPEFRUIT_PAGES = build_state_pages("grapefruit", _grapefruit_products())
GRAPEFRUIT_JSON = load_guide("grapefruit")

# Pure place-name region tokens, unique per state, none of which is a grapefruit cultivar name
# or a substring of common prose (Perth is excluded: it lives in the site footer chrome, and
# also legitimately appears in the WA overlay).
GRAPEFRUIT_REGION_TOKENS = {
    "WA": ["Carnarvon", "Gascoyne", "Gingin", "Kununurra"],
    "QLD": ["Gayndah", "Mundubbera", "Central Burnett", "Emerald"],
    "NSW": ["Riverina", "Murrumbidgee", "Griffith", "Leeton"],
    "VIC": ["Sunraysia", "Mildura", "Robinvale", "Red Cliffs"],
}


class GrapefruitGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in GRAPEFRUIT_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} grapefruit page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(GRAPEFRUIT_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two grapefruit state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in GRAPEFRUIT_PAGES.items():
            self.assertNotIn("Generic grapefruit blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in GRAPEFRUIT_REGION_TOKENS.items():
            self.assertTrue(any(t in GRAPEFRUIT_PAGES[st] for t in tokens),
                            f"{st} grapefruit page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in GRAPEFRUIT_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, GRAPEFRUIT_PAGES[other],
                                     f"{owner} grapefruit token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in GRAPEFRUIT_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on grapefruit {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on grapefruit {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, GRAPEFRUIT_JSON, "grapefruit.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          GRAPEFRUIT_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(GRAPEFRUIT_JSON["core"]["faqs"]) + len(GRAPEFRUIT_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', GRAPEFRUIT_PAGES[st], f"{st} missing Sources")
        for s in GRAPEFRUIT_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in GRAPEFRUIT_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "citrusvariety.ucr.edu", "dpird.wa.gov.au", "wacitrus.com.au",
                "citrusaustralia.com.au",
            )),
            "expected at least one gov/industry/university authority among the grapefruit sources",
        )

    def test_no_bot_blocked_gov_sources(self):
        # NSW DPI and Agriculture Victoria return HTTP 403 to automated fetchers, so the
        # "every cited URL must curl 200" rule means they must not be cited directly. The
        # NSW and VIC facts are anchored on Citrus Australia, Murrumbidgee Irrigation, WA
        # Citrus, SGA and UC Riverside instead. Keep it that way.
        for s in GRAPEFRUIT_JSON["sources"]:
            self.assertNotIn("dpi.nsw.gov.au", s["url"], f"NSW DPI 403s to curl: {s['url']}")
            self.assertNotIn("agriculture.vic.gov.au", s["url"], f"Ag Vic 403s to curl: {s['url']}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in GRAPEFRUIT_JSON["sources"]}
        cited = set()
        for block in [GRAPEFRUIT_JSON["core"]] + list(GRAPEFRUIT_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "grapefruit guide cites an unknown source id")

    def test_no_dead_sources(self):
        # The renderer only shows cited sources, so an uncited source is dead weight.
        src_ids = {s["id"] for s in GRAPEFRUIT_JSON["sources"]}
        cited = set()
        for block in [GRAPEFRUIT_JSON["core"]] + list(GRAPEFRUIT_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(src_ids - cited, set(), "grapefruit guide lists a source it never cites")

    def test_sources_note_is_grapefruit_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", GRAPEFRUIT_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', GRAPEFRUIT_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("grapefruit"))
        m = re.search(r'id="further-reading".*?</section>', GRAPEFRUIT_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("grapefruit")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("grapefruit").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("grapefruit", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    # --- grapefruit-specific climate-category guards -----------------------------------

    def test_grapefruit_has_its_own_climate_category(self):
        # Grapefruit must NOT inherit the generic "citrus" note (which steers cool-climate
        # growers to "cold-tolerant varieties like Meyer Lemon", irrelevant to grapefruit).
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["grapefruit"], "grapefruit")
        for st in STATES:
            note = bssp.get_climate_note("Grapefruit", st)
            self.assertIn("grapefruit", note.lower(), f"{st} climate note not grapefruit-specific")
            self.assertNotIn("Meyer Lemon", note, f"{st} grapefruit note still steers to Meyer Lemon")
        # WA note must carry the quarantine line that every WA note carries.
        self.assertIn("quarantine", bssp.get_climate_note("Grapefruit", "WA").lower())

    # --- grapefruit-specific correctness guards ----------------------------------------

    def test_heat_is_the_defining_fact(self):
        # The single most important grapefruit fact: it needs the most heat of any common
        # citrus to sweeten. Must appear in the shared core (so every page carries it).
        species = gg.render_species_guide("grapefruit").lower()
        self.assertIn("heat", species)
        self.assertIn("sweet", species)

    def test_core_says_one_tree_is_enough(self):
        self.assertIn("self fertile", gg.render_species_guide("grapefruit").lower())

    def test_wheeny_is_the_cool_climate_australian_option(self):
        # Wheeny (Australian, lower heat requirement) is the cool-climate answer and must be
        # named in the core, and tied to its NSW (Wheeny Creek) origin on the NSW page.
        self.assertIn("Wheeny", gg.render_species_guide("grapefruit"))
        self.assertIn("Wheeny Creek", GRAPEFRUIT_PAGES["NSW"])

    def test_vic_reads_as_marginal_not_prime(self):
        vic = GRAPEFRUIT_PAGES["VIC"].lower()
        self.assertIn("least suited", vic)  # the honest framing in the VIC intro
        # Sunraysia is the one warm VIC pocket; Melbourne/south is too cool.
        self.assertIn("sunraysia", vic)

    def test_wa_pest_is_medfly_not_qfly(self):
        wa = GRAPEFRUIT_PAGES["WA"]
        self.assertIn("Mediterranean fruit fly", wa,
                      "WA's headline citrus pest is Mediterranean fruit fly, not Qfly")

    def test_wa_does_not_claim_gall_wasp_free(self):
        wa = GRAPEFRUIT_PAGES["WA"]
        self.assertNotIn("free of citrus gall wasp", wa.lower(),
                         "WA is NOT free of citrus gall wasp (it is in Perth backyards)")
        self.assertIn("commercial orchards", wa,
                      "WA overlay should note gall wasp is absent from commercial orchards")

    def test_qld_canker_history_is_correct(self):
        qld = GRAPEFRUIT_PAGES["QLD"]
        self.assertIn("Emerald in 2004", qld, "QLD canker outbreak was Emerald 2004")
        self.assertIn("2021", qld, "Australia was declared free of citrus canker in 2021")
        # The 2018 outbreak was Darwin NT and Kununurra/Wyndham WA, never Emerald.
        self.assertNotIn("2018", qld, "do not pin a 2018 outbreak on Queensland/Emerald")

    def test_oroblanco_is_the_sweet_low_acid_hybrid(self):
        # Oroblanco (in stock) is the sweet, low-acid grapefruit-pummelo hybrid.
        species = gg.render_species_guide("grapefruit")
        self.assertIn("Oroblanco", species)
        self.assertIn("pomelo", species.lower())


if __name__ == "__main__":
    unittest.main()
