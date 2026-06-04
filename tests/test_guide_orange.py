"""
Orange growing-guide tests (tools/scrapers/growing_guides/orange.json). Flagship NSW
(the Riverina is Australia's orange heartland), with strong WA/QLD/VIC overlays. In its
own file so parallel guide runs never collide on a shared test module.

Beyond the shared guards (per-state uniqueness, no dashes, FAQ JSON-LD, https sources,
further reading), this file pins two correctness calls the research turned up, so a future
edit cannot quietly reintroduce the errors:
  * Queensland's citrus canker outbreak was at Emerald in 2004 (eradicated; Australia
    declared free in 2021), NOT a 2018 Emerald outbreak (2018 was Darwin NT and WA).
  * WA is NOT "free of citrus gall wasp": it is in Perth backyards (since 2013) but absent
    from WA commercial orchards and country districts.
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

ORANGE_SPECIES = {
    "common_name": "Orange",
    "latin_name": "Citrus sinensis",
    "description": "Generic orange blurb that should be replaced by the rich guide.",
    "slug": "orange",
}


def _orange_products(n=8):
    # Real in-stock sweet-orange cultivars, deliberately free of any region token so the
    # product table cannot trip the region-leak guard below.
    names = ["Washington Navel", "Cara Cara", "Valencia", "Lanes Late Navel",
             "Tarocco Blood", "Hamlin", "Navelina", "Valencia Seedless"]
    return [
        {"title": f"Orange {names[i % len(names)]}",
         "url": f"https://nursery.example/orange-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 37.0 + i * 3,
         "available": True, "species": ORANGE_SPECIES}
        for i in range(n)
    ]


ORANGE_PAGES = build_state_pages("orange", _orange_products())
ORANGE_JSON = load_guide("orange")

# Pure place-name region tokens, unique per state, none of which is a citrus cultivar name
# or a substring of common prose (Perth is excluded: it lives in the site footer chrome).
ORANGE_REGION_TOKENS = {
    "NSW": ["Riverina", "Murrumbidgee", "Griffith", "Leeton"],
    "QLD": ["Gayndah", "Mundubbera", "Central Burnett", "Emerald"],
    "VIC": ["Mildura", "Robinvale", "Sunraysia", "Red Cliffs"],
    "WA": ["Carnarvon", "Gascoyne", "Gingin", "Harvey"],
}


class OrangeGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in ORANGE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} orange page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(ORANGE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two orange state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in ORANGE_PAGES.items():
            self.assertNotIn("Generic orange blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in ORANGE_REGION_TOKENS.items():
            self.assertTrue(any(t in ORANGE_PAGES[st] for t in tokens),
                            f"{st} orange page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in ORANGE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, ORANGE_PAGES[other],
                                     f"{owner} orange token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in ORANGE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on orange {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on orange {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, ORANGE_JSON, "orange.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          ORANGE_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(ORANGE_JSON["core"]["faqs"]) + len(ORANGE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', ORANGE_PAGES[st], f"{st} missing Sources")
        for s in ORANGE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in ORANGE_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "citrusaustralia.com.au",
            )),
            "expected at least one gov/industry authority among the orange sources",
        )

    def test_no_bot_blocked_gov_sources(self):
        # NSW DPI and Agriculture Victoria return HTTP 403 to automated fetchers, so the
        # "every cited URL must curl 200" rule means they must not be cited directly. The
        # NSW and VIC facts are anchored on Citrus Australia, Murrumbidgee Irrigation, USDA
        # and SGA instead. Keep it that way.
        for s in ORANGE_JSON["sources"]:
            self.assertNotIn("dpi.nsw.gov.au", s["url"], f"NSW DPI 403s to curl: {s['url']}")
            self.assertNotIn("agriculture.vic.gov.au", s["url"], f"Ag Vic 403s to curl: {s['url']}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in ORANGE_JSON["sources"]}
        cited = set()
        for block in [ORANGE_JSON["core"]] + list(ORANGE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "orange guide cites an unknown source id")

    def test_no_dead_sources(self):
        # Every listed source should actually be cited by a section (the renderer only
        # shows cited sources, so an uncited source is dead weight).
        src_ids = {s["id"] for s in ORANGE_JSON["sources"]}
        cited = set()
        for block in [ORANGE_JSON["core"]] + list(ORANGE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(src_ids - cited, set(), "orange guide lists a source it never cites")

    def test_sources_note_is_orange_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", ORANGE_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', ORANGE_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("orange"))
        m = re.search(r'id="further-reading".*?</section>', ORANGE_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("orange")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("orange").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("orange", "NSW").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the NSW overlay should add cited sources beyond the core")

    # --- orange-specific correctness guards -------------------------------------------

    def test_qld_canker_history_is_correct(self):
        qld = ORANGE_PAGES["QLD"]
        self.assertIn("Emerald in 2004", qld, "QLD canker outbreak was Emerald 2004")
        self.assertIn("2021", qld, "Australia was declared free of citrus canker in 2021")
        # The 2018 outbreak was Darwin NT and WA, never Emerald. Guard against the error.
        self.assertNotIn("2018", qld, "do not pin a 2018 outbreak on Queensland/Emerald")

    def test_wa_does_not_claim_gall_wasp_free(self):
        wa = ORANGE_PAGES["WA"]
        self.assertNotIn("free of citrus gall wasp", wa.lower(),
                         "WA is NOT free of citrus gall wasp (it is in Perth backyards)")
        self.assertIn("commercial orchards", wa,
                      "WA overlay should note gall wasp is absent from commercial orchards")

    def test_wa_pest_is_medfly_not_qfly(self):
        wa = ORANGE_PAGES["WA"]
        self.assertIn("Mediterranean fruit fly", wa,
                      "WA's headline citrus pest is Mediterranean fruit fly, not Qfly")

    def test_blood_orange_colour_needs_cold(self):
        # The defining sweet-orange fact: blood-orange red flesh needs cold nights, so warm
        # states colour poorly and cool states colour well. Appears on both QLD and VIC.
        self.assertIn("blood orange", ORANGE_PAGES["VIC"].lower())
        self.assertIn("cold", ORANGE_PAGES["VIC"].lower())
        self.assertIn("blood orange", ORANGE_PAGES["QLD"].lower())

    def test_core_says_one_tree_is_enough(self):
        species = gg.render_species_guide("orange").lower()
        self.assertIn("self fertile", species)


if __name__ == "__main__":
    unittest.main()
