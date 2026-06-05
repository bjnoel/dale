"""
Finger lime growing-guide tests (tools/scrapers/growing_guides/finger-lime.json).

Finger lime (Citrus australasica, formerly Microcitrus australasica) is Australia's native
rainforest citrus, so it is a genuinely different guide from the cultivated lime: flagship NSW
(the Big Scrub / Northern Rivers native home), QLD a co-heartland (SE Queensland border ranges),
WA defined by citrus biosecurity (and finger lime is the native host of citrus gall wasp, now
established in Perth), and VIC the cold limit with one distinctive hook (CSIRO bred the native
limes at Merbein). Hyphenated slug, so this module file uses an underscore while the slug stays
"finger-lime". In its own file so parallel guide runs never collide on a shared test module.

Correctness traps this guide must get right (each pinned by a test below):
  * finger lime fruit is a POOR/NON-host for fruit fly (the opposite of most citrus) -- it must
    NOT carry the olive/lime "fruit fly stings citrus" line.
  * Blood Lime = acid mandarin x finger lime (NOT finger-lime x Rangpur); Outback Lime is a
    Desert Lime selection, not a finger lime.
  * WA is NOT free of citrus gall wasp (established in Perth since ~2013).
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

FINGER_LIME_SPECIES = {
    "common_name": "Finger Lime",
    "latin_name": "Microcitrus australasica",
    "description": "Generic finger lime blurb that should be replaced by the rich guide.",
    "slug": "finger-lime",
}


def _fl_products(n=8):
    # Named finger-lime cultivars actually in live Australian nursery stock, chosen so their
    # titles carry no region words (the leak guard relies on tokens coming only from prose).
    names = ["Rainforest Pearl", "Pink Ice", "Durham's Emerald", "Red Champagne",
             "Crystal", "Sunshine Yellow", "Blood Lime", "Byron Sunrise"]
    return [
        {"title": f"Finger Lime {names[i % len(names)]}",
         "url": f"https://nursery.example/finger-lime-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 32.0 + i * 5,
         "available": True, "species": FINGER_LIME_SPECIES}
        for i in range(n)
    ]


FL_PAGES = build_state_pages("finger-lime", _fl_products())
FL_JSON = load_guide("finger-lime")

# Region tokens unique to one state (the leak guard relies on these never appearing on another
# state's page, in prose OR a cited source name). All are real finger-lime-relevant places and
# none is also a cultivar name (Alstonville/Byron/Wauchope are cultivars, so they are NOT used).
FL_REGION_TOKENS = {
    "NSW": ["Lismore", "Big Scrub", "Northern Rivers"],
    "QLD": ["Scenic Rim", "Bellthorpe"],
    "WA": ["Gingin", "Carnarvon", "Gascoyne"],
    "VIC": ["Merbein", "Mildura", "Robinvale"],
}


class FingerLimeGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in FL_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} finger lime page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(FL_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two finger lime state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in FL_PAGES.items():
            self.assertNotIn("Generic finger lime blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in FL_REGION_TOKENS.items():
            self.assertTrue(any(t in FL_PAGES[st] for t in tokens),
                            f"{st} finger lime page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in FL_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, FL_PAGES[other],
                                     f"{owner} finger lime token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in FL_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on finger lime {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on finger lime {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, FL_JSON, "finger-lime.json")

    def test_core_facts_present_on_every_state(self):
        # The facts a finger lime buyer most needs, carried by the shared core, so they appear on
        # every combo page: self-fertility, the caviar pearls, and the gall-wasp native-host story.
        for st in STATES:
            self.assertIn("self-fertile", FL_PAGES[st], f"{st} page missing self-fertile note")
            self.assertIn("pearls", FL_PAGES[st], f"{st} page missing the caviar pearls")
            self.assertIn("native host of the citrus gall wasp", FL_PAGES[st],
                          f"{st} page missing the gall-wasp native-host fact")

    def test_correctness_finger_lime_is_a_poor_fruit_fly_host(self):
        # THE headline correctness trap: finger lime fruit is a poor/non-host for fruit fly, the
        # opposite of most citrus. The guide must say so and must NOT copy the olive/lime line that
        # fruit fly uses citrus as a host. (Carried by the core, so it is on every state page.)
        for st in STATES:
            page = FL_PAGES[st]
            self.assertIn("non-host for Queensland fruit fly", page,
                          f"{st} page should state finger lime is a non-host for Qfly")
            self.assertIn("very poor host for Mediterranean fruit fly", page,
                          f"{st} page should state finger lime is a very poor Medfly host")
            self.assertIn("rarely stung", page, f"{st} page missing the rarely-stung advantage")

    def test_correctness_blood_lime_parentage_and_outback(self):
        # Blood Lime = acid mandarin x red finger lime (CSIRO), NOT finger-lime x Rangpur; and the
        # Outback Lime is a Desert Lime selection, not a finger lime. Carried by the core.
        for st in STATES:
            page = FL_PAGES[st]
            self.assertIn("acid mandarin crossed with a red finger lime", page,
                          f"{st} page missing correct Blood Lime parentage")
            self.assertNotIn("Rangpur", page, f"{st} page wrongly invokes Rangpur for Blood Lime")
            self.assertIn("not a finger lime at all", page,
                          f"{st} page should flag the Outback Lime as a Desert Lime, not a finger lime")

    def test_correctness_naming_microcitrus_and_citrus(self):
        for st in STATES:
            self.assertIn("Citrus australasica", FL_PAGES[st], f"{st} missing accepted name")
            self.assertIn("Microcitrus", FL_PAGES[st], f"{st} missing the Microcitrus synonym")

    def test_wa_gall_wasp_established_not_free(self):
        wa = FL_PAGES["WA"]
        # Correctness guard (matches the lime/orange/mandarin citrus finding): WA is NOT free of
        # citrus gall wasp -- it is established in Perth (since ~2013), so the page must name it as
        # present and must not claim WA freedom from it.
        self.assertIn("gall wasp", wa, "WA page should name citrus gall wasp")
        self.assertIn("2013", wa, "WA page should date the Perth gall-wasp establishment")
        self.assertIn("Perth", wa, "WA page should locate the gall wasp in Perth")
        self.assertNotIn("free of citrus gall wasp", wa, "WA page must not claim freedom from gall wasp")

    def test_wa_biosecurity_framing(self):
        wa = FL_PAGES["WA"]
        self.assertIn("Organism List", wa, "WA page missing the WA Organism List import framing")
        self.assertIn("canker", wa, "WA page missing the citrus canker rationale")
        self.assertIn("Medfly", wa, "WA page missing Mediterranean fruit fly (Medfly)")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          FL_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(FL_JSON["core"]["faqs"]) + len(FL_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', FL_PAGES[st], f"{st} missing Sources")
        for s in FL_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in FL_JSON["sources"])
        self.assertTrue(
            all(d in domains for d in (
                "csiro.au", "dpird.wa.gov.au", "business.qld.gov.au", "agrifutures.com.au",
            )),
            "expected CSIRO + DPIRD + Business Qld + AgriFutures among the finger lime sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in FL_JSON["sources"]}
        cited = set()
        for block in [FL_JSON["core"]] + list(FL_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "finger lime guide cites an unknown source id")

    def test_sources_note_is_finger_lime_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", FL_PAGES[st])
            self.assertNotIn("Generic avocado blurb", FL_PAGES[st])

    def test_species_links_resolve(self):
        # Every /species/ link must be a real slug (no 404s); the core links to the cultivated lime page.
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', FL_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")
        self.assertIn("lime",
                      set(re.findall(r'/species/([a-z0-9-]+)\.html', FL_PAGES["NSW"])),
                      "expected a link to the cultivated lime page")

    def test_climate_category_is_citrus(self):
        # Finger lime keeps the shared 'citrus' climate note (it is a true citrus under the same WA
        # citrus biosecurity); the finger-lime-specific nuances live in the per-state overlays, so
        # no SPECIES_CLIMATE_CATEGORY change is needed (mirrors the mandarin decision).
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY.get("finger lime"), "citrus")

    def test_further_reading_owned_followed_and_merged(self):
        # Finger lime has no clean RFCA folder (its content sits in the mixed-genus AusNative/Citrus
        # folders, which never auto-map), so Further reading is the hand-curated owned archives:
        # the RFCA "Wild Lime / rainforest limes" article and the WANATCA ACOTANC citrus paper, both
        # owned and therefore followed.
        self.assertIn('id="further-reading"', gg.render_species_guide("finger-lime"))
        m = re.search(r'id="further-reading".*?</section>', FL_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://rfcarchives[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("finger-lime")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("finger-lime").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("finger-lime", "NSW").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the NSW overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
