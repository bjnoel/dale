"""
Raspberry growing-guide tests (tools/scrapers/growing_guides/raspberry.json).

Raspberry gets its OWN climate category ("raspberry"), NOT the generic "temperate /
choose low-chill varieties" note, because it is a COOL-climate cane fruit: it wants a
genuinely cold winter (high chill) and a mild summer, and crops poorly in warm, humid or
hot-summer districts. Unlike blueberry it is NOT an auto-indexed RFCA species (the RFCA
article lives under the AusNative/ folder, which build_archive_index.py does not map to
the raspberry slug), so its first-party Further reading is hand-curated: the WANATCA
yearbook article AND the RFCA AusNative native-raspberry page (both Benedict-owned,
followed). In its own file so parallel guide runs never collide.

Correctness guards below pin the adversarially-verified research, especially the points
where the stale fruit_species.json blurb was WRONG:
  * Heritage is AUTUMN-fruiting / primocane (NOT a floricane "Heritage type"), and Tulameen
    is summer-fruiting / floricane (verified against four authorities).
  * The native Atherton raspberry (Rubus probus) is PRICKLY and a vigorous scrambler, NOT
    "compact, nearly thornless"; it is a Queensland-only warm-climate alternative.
  * Raspberries are self-fertile; soil pH 5.5 to 6.5; WA's fly is Medfly (Qfly in the east).
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

RASPBERRY_SPECIES = {
    "common_name": "Raspberry",
    "latin_name": "Rubus idaeus",
    "description": "Generic raspberry blurb that should be replaced by the rich guide.",
    "slug": "raspberry",
}


def _raspberry_products(n=9):
    # Real in-stock raspberry cultivars (summer/floricane + autumn/primocane) plus the
    # native Atherton raspberry, so the table renders alongside the guide and the variety
    # advice ties to live stock.
    names = ["Tulameen", "Chilcotin", "Chilliwack", "Sandford",
             "Heritage", "Autumn Bliss", "Coho", "Golden", "Atherton"]
    return [
        {
            "title": f"Raspberry {names[i % len(names)]}",
            "url": f"https://nursery.example/raspberry-{i}",
            "nursery_key": "diggers",
            "nursery_name": "The Diggers Club",
            "price": 15.0 + i * 3,
            "available": True,
            "species": RASPBERRY_SPECIES,
        }
        for i in range(n)
    ]


RASPBERRY_PAGES = build_state_pages("raspberry", _raspberry_products())
RASPBERRY_JSON = load_guide("raspberry")

# Each state's distinctive region tokens. Must appear on that state's page and on NO
# other state's page. Chosen as pure place names that are not substrings of in-stock
# cultivar names, common words, or site chrome.
RASPBERRY_REGION_TOKENS = {
    # NB: tokens are pure place names, NOT substrings of in-stock cultivar names. "Atherton"
    # is deliberately NOT a QLD token here: the fixture stocks a "Raspberry Atherton"
    # cultivar, so that word appears in the (identical) stock table on every state page.
    # The QLD-only native content is guarded separately via "Rubus probus" below.
    "WA": ["Donnybrook", "Bickley", "Porongurup"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Mittagong", "Armidale", "Blue Mountains"],
    "VIC": ["Dandenong", "Silvan", "Gippsland"],
}


class RaspberryGuideTests(unittest.TestCase):
    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in RASPBERRY_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} raspberry page too small")

    def test_canonical_and_og(self):
        wa = RASPBERRY_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-raspberry-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        wa = RASPBERRY_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Raspberry in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in RASPBERRY_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Raspberry in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in RASPBERRY_PAGES.items():
            self.assertNotIn("Generic raspberry blurb", html, f"{st} still shows the blurb")

    # --- climate category: raspberry is its own category, NOT temperate ---
    def test_raspberry_has_its_own_climate_category(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["raspberry"], "raspberry",
                         "raspberry must not inherit the generic temperate note")

    def test_every_state_has_a_raspberry_climate_note(self):
        for st in STATES:
            self.assertIn("raspberry", bssp.STATE_CLIMATE_NOTES[st],
                          f"{st} has no raspberry-specific climate note")

    def test_raspberry_climate_note_leads_with_cool_climate_not_low_chill(self):
        # The generic temperate note tells growers to "choose low-chill varieties", which is
        # exactly backwards for a cool-climate, high-chill cane fruit.
        for st in STATES:
            note = bssp.get_climate_note("Raspberry", st)
            self.assertNotEqual(note, bssp.STATE_CLIMATE_NOTES[st]["temperate"],
                                f"{st} raspberry note is the generic temperate note")
            self.assertIn("cool-climate", note.lower(), f"{st} raspberry note should say cool-climate")
            # The generic temperate note's tell is "choose low-chill varieties", which is
            # backwards for a high-chill cane fruit. (Saying "not a low-chill one" is fine.)
            self.assertNotIn("choose low-chill", note.lower(),
                             f"{st} raspberry note inherits the generic low-chill advice")
        self.assertIn("quarantine", bssp.get_climate_note("Raspberry", "WA").lower(),
                      "WA raspberry note should mention quarantine")
        self.assertIn("Mediterranean fruit fly", bssp.get_climate_note("Raspberry", "WA"),
                      "WA raspberry note should name Medfly")

    def test_raspberry_climate_notes_have_no_dashes(self):
        for st in STATES:
            note = bssp.get_climate_note("Raspberry", st)
            self.assertNotIn(EM_DASH, note, f"em dash in {st} raspberry climate note")
            self.assertNotIn(EN_DASH, note, f"en dash in {st} raspberry climate note")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(RASPBERRY_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two raspberry state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in RASPBERRY_REGION_TOKENS.items():
            self.assertTrue(any(t in RASPBERRY_PAGES[st] for t in tokens),
                            f"{st} raspberry page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in RASPBERRY_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, RASPBERRY_PAGES[other],
                                     f"{owner} raspberry token '{t}' leaked onto {other} page")

    def test_overlay_then_core(self):
        wa = gg.render_combo_guide("raspberry", "WA")
        self.assertIn("Where raspberries grow in WA", wa)   # overlay
        self.assertIn("Choose the type first", wa)          # core
        self.assertLess(wa.index("Where raspberries grow in WA"), wa.index("Choose the type first"))

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in RASPBERRY_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} raspberry page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} raspberry page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, RASPBERRY_JSON, "raspberry.json")

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', RASPBERRY_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', RASPBERRY_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in RASPBERRY_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in RASPBERRY_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "berries.net.au", "dpird.wa.gov.au", "business.qld.gov.au",
                "extension.oregonstate.edu", "extension.umn.edu",
            )),
            "expected at least one agriculture/industry/extension authority among the sources",
        )

    def test_no_bot_blocked_gov_sources(self):
        # NSW DPI, Agriculture Victoria and PIRSA 403 to automated fetchers, so they
        # cannot be cited under the URL-200 gate. Anchor claims on Berries Australia,
        # DPIRD WA, Business Queensland and the US/UK extension services instead.
        joined = json.dumps(RASPBERRY_JSON)
        for blocked in ("dpi.nsw.gov.au", "agriculture.vic.gov.au", "pir.sa.gov.au"):
            self.assertNotIn(blocked, joined, f"raspberry guide cites a bot-blocked source: {blocked}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in RASPBERRY_JSON["sources"]}
        cited = set()
        for block in [RASPBERRY_JSON["core"]] + list(RASPBERRY_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "raspberry guide cites an unknown source id")

    def test_sources_note_does_not_leak_other_species_copy(self):
        self.assertNotIn("olive", RASPBERRY_PAGES["WA"].lower())

    # --- FAQ + links ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(RASPBERRY_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(RASPBERRY_JSON["core"]["faqs"]) + len(RASPBERRY_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', RASPBERRY_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("raspberry"))

    # --- owned Further reading: hand-curated WANATCA + RFCA (NOT auto-indexed: AusNative/) ---
    def test_wanatca_and_rfca_further_reading_present(self):
        fr = gg.get_further_reading("raspberry")
        self.assertTrue(fr, "raspberry should have curated Further reading")
        self.assertTrue(any("wanatca.org.au" in e["url"] for e in fr),
                        "expected the WANATCA native-raspberry article in Further reading")
        self.assertTrue(any("rfcarchives.org.au" in e["url"] for e in fr),
                        "expected the curated RFCA native-raspberry page in Further reading")
        for st in STATES:
            self.assertIn('id="further-reading"', RASPBERRY_PAGES[st], f"{st} missing Further reading")
            self.assertIn("wanatca.org.au", RASPBERRY_PAGES[st], f"{st} missing WANATCA link")
            self.assertIn("rfcarchives.org.au", RASPBERRY_PAGES[st], f"{st} missing RFCA link")

    # --- correctness guards (pin the verified research) ---
    def test_both_fruiting_types_named_on_every_page(self):
        for st in STATES:
            html = RASPBERRY_PAGES[st]
            for term in ("floricane", "primocane", "summer-fruiting", "autumn-fruiting"):
                self.assertIn(term, html, f"{st} page missing fruiting-type term '{term}'")

    def test_heritage_is_primocane_tulameen_is_floricane(self):
        # The headline correctness fix: the stale fruit_species.json blurb wrongly grouped
        # "Heritage types" as floricane. Heritage is AUTUMN/primocane; Tulameen is SUMMER/
        # floricane. Pin the exact verified listing so it cannot silently regress.
        body = " ".join(s["body"] for s in RASPBERRY_JSON["core"]["sections"])
        self.assertIn("Tulameen, Chilcotin, Chilliwack and the very early Sandford fruit in early to midsummer", body,
                      "summer/floricane variety listing changed or wrong")
        self.assertIn("Heritage, Autumn Bliss and Coho fruit in late summer and autumn", body,
                      "autumn/primocane variety listing changed or wrong")

    def test_raspberries_are_self_fertile(self):
        for st in STATES:
            self.assertIn("self-fertile", RASPBERRY_PAGES[st], f"{st} missing the self-fertile fact")

    def test_soil_ph_on_every_page(self):
        for st in STATES:
            self.assertIn("5.5 to 6.5", RASPBERRY_PAGES[st], f"{st} missing the soil pH range")

    def test_pruning_by_type_present(self):
        for st in STATES:
            html = RASPBERRY_PAGES[st]
            self.assertIn("cut", html.lower(), f"{st} missing pruning advice")
            self.assertIn("to the ground", html.lower(), f"{st} missing the cut-to-ground method")

    def test_atherton_native_is_queensland_only_and_prickly_not_thornless(self):
        # The native Atherton raspberry (Rubus probus) is a QLD warm-climate alternative,
        # and it is PRICKLY and a vigorous scrambler, NOT "compact, nearly thornless".
        self.assertIn("Rubus probus", RASPBERRY_PAGES["QLD"], "QLD page should name Rubus probus")
        self.assertIn("prickly", RASPBERRY_PAGES["QLD"].lower(), "QLD page should call the native prickly")
        for st in STATES:
            self.assertNotIn("thornless", RASPBERRY_PAGES[st].lower(),
                             f"{st} wrongly calls the Atherton raspberry thornless")
        for st in ("WA", "NSW", "VIC"):
            self.assertNotIn("Rubus probus", RASPBERRY_PAGES[st],
                             f"the Atherton native leaked onto the {st} page")

    def test_wa_fly_is_medfly_eastern_states_name_qfly(self):
        self.assertIn("Mediterranean fruit fly", RASPBERRY_PAGES["WA"],
                      "WA page must name Medfly")
        for st in ("QLD", "NSW", "VIC"):
            self.assertIn("Queensland fruit fly", RASPBERRY_PAGES[st], f"{st} should name Qfly")

    def test_buy_certified_virus_free_stock(self):
        for st in STATES:
            self.assertIn("certified virus-free", RASPBERRY_PAGES[st],
                          f"{st} missing the certified virus-free buying advice")

    def test_birds_are_a_pest_and_netting(self):
        for st in STATES:
            self.assertIn("net", RASPBERRY_PAGES[st].lower(), f"{st} missing bird netting advice")


if __name__ == "__main__":
    unittest.main()
