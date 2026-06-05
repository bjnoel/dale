"""
Blueberry growing-guide tests (tools/scrapers/growing_guides/blueberry.json).

Blueberry gets its OWN climate category ("blueberry"), not the generic "temperate /
choose low-chill varieties" note, because its defining need is a strongly acidic soil
(pH 4.5 to 5.5), not winter chill, and it splits into low-chill (southern highbush,
rabbiteye) and high-chill (northern highbush) types. Unlike cherry/apple it IS a rare-
fruit-archive species (an RFCA Blueberry folder exists), so Further reading carries both
the curated WANATCA Ridley Bell articles AND the auto-merged RFCA links. In its own file
so parallel guide runs never collide. Correctness guards below pin the verified research:
the three types and their chill, the acid-soil pH, rabbiteye self-incompatibility (vs
self-fertile highbush), blueberry rust = Thekopsora minima (NOT myrtle rust), WA's fly is
Medfly not Qfly, and ammonium-not-lime feeding.
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

BLUEBERRY_SPECIES = {
    "common_name": "Blueberry",
    "latin_name": "Vaccinium corymbosum",
    "description": "Generic blueberry blurb that should be replaced by the rich guide.",
    "slug": "blueberry",
}


def _blueberry_products(n=9):
    # Real in-stock blueberry cultivars (southern highbush + rabbiteye) so the table
    # renders alongside the guide and the variety advice ties to live stock.
    names = ["Biloxi", "Misty", "Sharpblue", "Gulf Coast", "Sunshine Blue",
             "Powder Blue", "Brightwell", "Climax", "Blue Rose"]
    return [
        {
            "title": f"Blueberry {names[i % len(names)]}",
            "url": f"https://nursery.example/blueberry-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 18.0 + i * 4,
            "available": True,
            "species": BLUEBERRY_SPECIES,
        }
        for i in range(n)
    ]


BLUEBERRY_PAGES = build_state_pages("blueberry", _blueberry_products())
BLUEBERRY_JSON = load_guide("blueberry")

# Each state's distinctive region tokens. Must appear on that state's page and on NO
# other state's page. Chosen as pure place names that are not substrings of in-stock
# cultivar names, common words, or site chrome.
BLUEBERRY_REGION_TOKENS = {
    "WA": ["Manjimup", "Albany", "Bickley"],
    "QLD": ["Bundaberg", "Atherton Tablelands"],
    "NSW": ["Coffs Harbour", "Corindi", "Woolgoolga"],
    "VIC": ["Yarra Valley", "Silvan", "Gippsland"],
}


class BlueberryGuideTests(unittest.TestCase):
    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in BLUEBERRY_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} blueberry page too small")

    def test_canonical_and_og(self):
        wa = BLUEBERRY_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-blueberry-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        wa = BLUEBERRY_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Blueberry in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in BLUEBERRY_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Blueberry in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in BLUEBERRY_PAGES.items():
            self.assertNotIn("Generic blueberry blurb", html, f"{st} still shows the blurb")

    # --- climate category: blueberry is its own category, NOT temperate ---
    def test_blueberry_has_its_own_climate_category(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["blueberry"], "blueberry",
                         "blueberry must not inherit the generic temperate note")

    def test_every_state_has_a_blueberry_climate_note(self):
        for st in STATES:
            self.assertIn("blueberry", bssp.STATE_CLIMATE_NOTES[st],
                          f"{st} has no blueberry-specific climate note")

    def test_blueberry_climate_note_leads_with_acid_soil_not_chill(self):
        # The generic temperate note tells growers to "choose low-chill varieties", which
        # misses the point for blueberries: the headline is the acid-soil pH requirement.
        for st in STATES:
            note = bssp.get_climate_note("Blueberry", st)
            self.assertNotEqual(note, bssp.STATE_CLIMATE_NOTES[st]["temperate"],
                                f"{st} blueberry note is the generic temperate note")
            self.assertIn("acid", note.lower(), f"{st} blueberry note should mention acid soil")
            self.assertIn("4.5 to 5.5", note, f"{st} blueberry note should give the pH range")
        self.assertIn("quarantine", bssp.get_climate_note("Blueberry", "WA").lower(),
                      "WA blueberry note should mention quarantine")

    def test_blueberry_climate_notes_have_no_dashes(self):
        for st in STATES:
            note = bssp.get_climate_note("Blueberry", st)
            self.assertNotIn(EM_DASH, note, f"em dash in {st} blueberry climate note")
            self.assertNotIn(EN_DASH, note, f"en dash in {st} blueberry climate note")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(BLUEBERRY_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two blueberry state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in BLUEBERRY_REGION_TOKENS.items():
            self.assertTrue(any(t in BLUEBERRY_PAGES[st] for t in tokens),
                            f"{st} blueberry page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in BLUEBERRY_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, BLUEBERRY_PAGES[other],
                                     f"{owner} blueberry token '{t}' leaked onto {other} page")

    def test_overlay_then_core(self):
        wa = gg.render_combo_guide("blueberry", "WA")
        self.assertIn("Where blueberries grow in WA", wa)   # overlay
        self.assertIn("Choosing a variety", wa)             # core
        self.assertLess(wa.index("Where blueberries grow in WA"), wa.index("Choosing a variety"))

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in BLUEBERRY_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} blueberry page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} blueberry page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, BLUEBERRY_JSON, "blueberry.json")

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', BLUEBERRY_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', BLUEBERRY_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in BLUEBERRY_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in BLUEBERRY_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "berries.net.au", "cogs.asn.au",
            )),
            "expected at least one agriculture/industry authority among the blueberry sources",
        )

    def test_no_bot_blocked_gov_sources(self):
        # NSW DPI, Agriculture Victoria and PIRSA 403 to automated fetchers, so they
        # cannot be cited under the URL-200 gate. Anchor claims on Berries Australia,
        # COGS, NRE Tasmania, DPIRD WA and Business Queensland instead.
        joined = json.dumps(BLUEBERRY_JSON)
        for blocked in ("dpi.nsw.gov.au", "agriculture.vic.gov.au", "pir.sa.gov.au"):
            self.assertNotIn(blocked, joined, f"blueberry guide cites a bot-blocked source: {blocked}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in BLUEBERRY_JSON["sources"]}
        cited = set()
        for block in [BLUEBERRY_JSON["core"]] + list(BLUEBERRY_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "blueberry guide cites an unknown source id")

    def test_sources_note_does_not_leak_other_species_copy(self):
        self.assertNotIn("olive", BLUEBERRY_PAGES["WA"].lower())

    # --- FAQ + links ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(BLUEBERRY_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(BLUEBERRY_JSON["core"]["faqs"]) + len(BLUEBERRY_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', BLUEBERRY_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("blueberry"))

    # --- owned Further reading: curated WANATCA + auto-merged RFCA (rare-fruit species) ---
    def test_wanatca_and_rfca_further_reading_present(self):
        fr = gg.get_further_reading("blueberry")
        self.assertTrue(fr, "blueberry should have curated Further reading")
        self.assertTrue(any("wanatca.org.au" in e["url"] for e in fr),
                        "expected the WANATCA Ridley Bell articles in Further reading")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/Blueberry" in e["url"] for e in fr),
                        "expected the auto-merged RFCA blueberry links in Further reading")
        for st in STATES:
            self.assertIn('id="further-reading"', BLUEBERRY_PAGES[st], f"{st} missing Further reading")
            self.assertIn("wanatca.org.au", BLUEBERRY_PAGES[st], f"{st} missing WANATCA link")

    # --- correctness guards (pin the verified research) ---
    def test_three_blueberry_types_named(self):
        for st in STATES:
            html = BLUEBERRY_PAGES[st]
            for kind in ("southern highbush", "northern highbush", "rabbiteye"):
                self.assertIn(kind, html, f"{st} page missing blueberry type '{kind}'")

    def test_acid_soil_ph_on_every_page(self):
        for st in STATES:
            self.assertIn("4.5 to 5.5", BLUEBERRY_PAGES[st], f"{st} missing the acid-soil pH range")

    def test_rabbiteye_cross_pollination_correctness(self):
        # Rabbiteye are self-incompatible and need a second rabbiteye; highbush are
        # self-fertile but crop better with a partner. Triple-confirmed by RFCA, Berries
        # Australia variety pairings, and the in-stock "Rabbiteye Pollinating Combo".
        for st in STATES:
            html = BLUEBERRY_PAGES[st]
            self.assertIn("self-incompatible", html, f"{st} missing rabbiteye self-incompatibility")
            self.assertIn("self-fertile", html, f"{st} missing the self-fertile highbush fact")
            self.assertIn("same type", html.lower(), f"{st} should say plant two of the same type")

    def test_blueberry_rust_is_thekopsora_not_myrtle_rust(self):
        # The adversarial catch: blueberry rust is Thekopsora minima, a different fungus
        # from myrtle rust (Austropuccinia psidii). Never conflate the two.
        for st in STATES:
            html = BLUEBERRY_PAGES[st]
            self.assertIn("Thekopsora minima", html, f"{st} should name the blueberry rust fungus")
            self.assertNotIn("myrtle rust", html.lower(), f"{st} wrongly calls it myrtle rust")
            self.assertNotIn("Austropuccinia", html, f"{st} wrongly names the myrtle-rust fungus")

    def test_wa_fly_is_medfly_eastern_states_name_qfly(self):
        self.assertIn("Mediterranean fruit fly", BLUEBERRY_PAGES["WA"],
                      "WA page must name Medfly")
        for st in ("QLD", "NSW", "VIC"):
            self.assertIn("Queensland fruit fly", BLUEBERRY_PAGES[st], f"{st} should name Qfly")

    def test_feeding_is_ammonium_not_lime(self):
        for st in STATES:
            html = BLUEBERRY_PAGES[st]
            self.assertIn("ammonium", html, f"{st} missing ammonium-nitrogen advice")
            self.assertIn("never lime", html, f"{st} missing the never-lime rule")

    def test_birds_are_the_main_pest_and_netting(self):
        for st in STATES:
            self.assertIn("net", BLUEBERRY_PAGES[st].lower(), f"{st} missing bird netting advice")


if __name__ == "__main__":
    unittest.main()
