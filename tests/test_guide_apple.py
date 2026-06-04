"""
Apple growing-guide tests (tools/scrapers/growing_guides/apple.json). Apple is a genuine
four-state crop, so every state gets a real, distinct overlay: WA (Southern Forests, the
Cripps/Pink Lady breeding story, and the rare distinction of being codling-moth-free), QLD
(the high-altitude Granite Belt plus low-chill subtropics), NSW (Batlow/Orange/Bilpin and the
birthplace of the Granny Smith), and VIC (Goulburn Valley, the Tatura Trellis, Australia's
biggest producer). In its own file so parallel guide runs never collide on a shared module.

Apple-specific correctness guards worth keeping (these are facts a grower must get right):
  * Codling moth is ABSENT from WA (a declared pest kept out by quarantine) but PRESENT in the
    eastern states. So the WA page must say "free of codling moth" and the QLD/NSW/VIC pages
    must not.
  * The fruit fly differs by state: Mediterranean fruit fly in WA, Queensland fruit fly in the
    east. The WA page must not tell WA growers to manage Queensland fruit fly.
  * Triploid varieties (Gravenstein, Jonagold, Mutsu) cannot pollinate and need two pollinators.
  * Cripps Pink/Pink Lady was bred in WA (John Cripps); Granny Smith originated in NSW (1868);
    the Tatura Trellis came from Victoria.
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

APPLE_SPECIES = {
    "common_name": "Apple",
    "latin_name": "Malus domestica",
    "description": "Generic apple blurb that should be replaced by the rich guide.",
    "slug": "apple",
}


def _apple_products(n=8):
    # Named varieties that are actually in live Australian nursery stock: a mix of mainstream
    # mid/high-chill (Gala, Granny Smith, Fuji, Jonathan), WA-bred late (Pink Lady, Sundowner)
    # and low-chill subtropical (Anna, Dorsett Golden).
    names = ["Gala", "Granny Smith", "Pink Lady", "Fuji", "Jonathan", "Anna", "Dorsett Golden", "Sundowner"]
    return [
        {"title": f"Apple {names[i % len(names)]}",
         "url": f"https://nursery.example/apple-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 32.0 + i * 4,
         "available": True, "species": APPLE_SPECIES}
        for i in range(n)
    ]


APPLE_PAGES = build_state_pages("apple", _apple_products())
APPLE_JSON = load_guide("apple")

# Region tokens that are unique to one state (the leak guard relies on this). All chosen to be
# unambiguous place names that appear in only one state's overlay (not in product titles,
# nursery names, source names, or the page chrome). "Perth" is avoided (it is in the footer);
# "Orange" is avoided as a token (it is also a fruit/word) though it is used in NSW prose;
# "Donnybrook" is avoided (there are Donnybrooks in VIC and QLD too).
APPLE_REGION_TOKENS = {
    "WA": ["Manjimup", "Pemberton"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Batlow", "Bilpin"],
    "VIC": ["Goulburn Valley", "Yarra Valley"],
}


class AppleGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in APPLE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} apple page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(APPLE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two apple state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in APPLE_PAGES.items():
            self.assertNotIn("Generic apple blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in APPLE_REGION_TOKENS.items():
            self.assertTrue(any(t in APPLE_PAGES[st] for t in tokens),
                            f"{st} apple page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in APPLE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, APPLE_PAGES[other],
                                     f"{owner} apple token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in APPLE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on apple {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on apple {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, APPLE_JSON, "apple.json")

    # --- correctness guards -------------------------------------------------

    def test_codling_moth_free_in_wa_only(self):
        # The headline WA fact: WA is one of the last apple regions free of codling moth.
        self.assertIn("free of codling moth", APPLE_PAGES["WA"],
                      "WA page must state WA is free of codling moth")
        for st in ("QLD", "NSW", "VIC"):
            self.assertNotIn("free of codling moth", APPLE_PAGES[st],
                             f"{st} is NOT free of codling moth; do not claim it is")
            self.assertIn("codling moth", APPLE_PAGES[st],
                          f"{st} page should name codling moth as a present pest")

    def test_fruit_fly_is_state_correct(self):
        # WA = Mediterranean fruit fly (not Queensland fruit fly); the east = Queensland fruit fly.
        self.assertIn("Mediterranean fruit fly", APPLE_PAGES["WA"], "WA page should name Medfly")
        self.assertNotIn("Queensland fruit fly", APPLE_PAGES["WA"],
                         "WA has Medfly, not Queensland fruit fly; do not tell WA growers to manage Qfly")
        for st in ("QLD", "NSW", "VIC"):
            self.assertIn("Queensland fruit fly", APPLE_PAGES[st],
                          f"{st} page should name Queensland fruit fly")

    def test_pollination_and_triploids_present(self):
        for st in STATES:
            self.assertIn("self-incompatible", APPLE_PAGES[st], f"{st} page missing pollination basics")
            self.assertIn("triploid", APPLE_PAGES[st], f"{st} page missing triploid warning")
            self.assertIn("Gravenstein", APPLE_PAGES[st], f"{st} page missing a named triploid (Gravenstein)")

    def test_fire_blight_framed_as_absent(self):
        # Australia is free of fire blight; never imply it is established here.
        self.assertIn("free of fire blight", APPLE_PAGES["WA"],
                      "WA page should state Australia is free of fire blight")

    def test_marquee_state_facts(self):
        # WA: the Cripps / Pink Lady breeding story.
        self.assertIn("John Cripps", APPLE_PAGES["WA"], "WA page missing the Cripps breeding story")
        self.assertIn("Pink Lady", APPLE_PAGES["WA"], "WA page missing Pink Lady")
        # NSW: Granny Smith originated at Ryde in 1868.
        self.assertIn("Maria Ann Smith", APPLE_PAGES["NSW"], "NSW page missing the Granny Smith origin")
        self.assertIn("1868", APPLE_PAGES["NSW"], "NSW page missing the Granny Smith origin date")
        # QLD: the Granite Belt is the apple district.
        self.assertIn("Stanthorpe", APPLE_PAGES["QLD"], "QLD page missing Stanthorpe/Granite Belt")
        # VIC: biggest producer + the Tatura Trellis.
        self.assertIn("Tatura", APPLE_PAGES["VIC"], "VIC page missing the Tatura Trellis")
        self.assertIn("43 per cent", APPLE_PAGES["VIC"], "VIC page missing its production share")

    def test_low_chill_varieties_named(self):
        # Warm-district readers (QLD/NSW coast) need the low-chill names.
        for st in ("QLD", "NSW"):
            self.assertIn("Anna", APPLE_PAGES[st], f"{st} page should name a low-chill variety (Anna)")
            self.assertIn("Dorsett Golden", APPLE_PAGES[st], f"{st} page should name Dorsett Golden")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          APPLE_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(APPLE_JSON["core"]["faqs"]) + len(APPLE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', APPLE_PAGES[st], f"{st} missing Sources")
        for s in APPLE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in APPLE_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "pomewest.net.au", "aussieapples.com.au",
            )),
            "expected at least one gov/industry authority among the apple sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in APPLE_JSON["sources"]}
        cited = set()
        for block in [APPLE_JSON["core"]] + list(APPLE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "apple guide cites an unknown source id")

    def test_sources_note_is_apple_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", APPLE_PAGES[st])
            self.assertNotIn("Generic lychee blurb", APPLE_PAGES[st])
        self.assertIn("apple and pear industry", APPLE_JSON["sources_note"])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', APPLE_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")
            self.assertIn("pear", linked, f"{st} should cross-link to the pome cousin /species/pear.html")

    def test_further_reading_owned_followed_and_merged(self):
        # Apple has no RFCA folder (it is not a rare fruit), so further reading is the curated
        # WANATCA article only (no auto-merged rfcarchives links). It must still be a followed,
        # owned cross-link, and the rendered count must match the merged list.
        self.assertIn('id="further-reading"', gg.render_species_guide("apple"))
        m = re.search(r'id="further-reading".*?</section>', APPLE_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://wanatca[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("apple")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("apple").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("apple", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
