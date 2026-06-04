"""
Jaboticaba growing-guide tests (tools/scrapers/growing_guides/jaboticaba.json). NSW Northern
Rivers flagship by climate/evidence, with a standout WA overlay (fruit-fly resistance, permitted
but myrtle-rust-conditioned shipping). Frost-hardier than most subtropicals (classified
"subtropical"). In its own file so parallel guide runs never collide on a shared test module.
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

JABOTICABA_SPECIES = {
    "common_name": "Jaboticaba",
    "latin_name": "Plinia cauliflora",
    "description": "Generic jaboticaba blurb that should be replaced by the rich guide.",
    "slug": "jaboticaba",
}


def _jaboticaba_products(n=8):
    names = ["Sabara", "Large Leaf Grimal", "Red Hybrid", "Scarlet", "Yellow",
             "Small Leaf", "Costada", "Dwarf"]
    return [
        {"title": f"Jaboticaba {names[i % len(names)]}",
         "url": f"https://nursery.example/jaboticaba-{i}",
         "nursery_key": "ross-creek", "nursery_name": "Ross Creek Tropicals",
         "price": 29.0 + i * 6, "available": True, "species": JABOTICABA_SPECIES}
        for i in range(n)
    ]


JABOTICABA_PAGES = build_state_pages("jaboticaba", _jaboticaba_products())
JABOTICABA_JSON = load_guide("jaboticaba")

# Region tokens must be unique to each state's overlay (and absent from the shared core,
# the amber climate note, and the cross-links). "Perth" is excluded as a token because it
# appears in the site footer on every page.
JABOTICABA_REGION_TOKENS = {
    "WA": ["Swan Coastal Plain", "Gascoyne"],
    "QLD": ["Sunshine Coast", "Atherton Tableland"],
    "NSW": ["Northern Rivers", "Coffs Harbour"],
    "VIC": ["Mornington Peninsula", "Gippsland"],
}


class JaboticabaGuideTests(unittest.TestCase):
    def test_subtropical_climate_category(self):
        # Jaboticaba is frost-tolerant once mature and best in subtropical/warm-temperate
        # zones (RFCA/Yates), not the hot lowland tropics. It must use the subtropical note.
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["jaboticaba"], "subtropical")

    def test_pages_build_nonempty(self):
        for st, html in JABOTICABA_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} jaboticaba page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(JABOTICABA_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two jaboticaba state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in JABOTICABA_PAGES.items():
            self.assertNotIn("Generic jaboticaba blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in JABOTICABA_REGION_TOKENS.items():
            self.assertTrue(any(t in JABOTICABA_PAGES[st] for t in tokens),
                            f"{st} jaboticaba page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in JABOTICABA_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, JABOTICABA_PAGES[other],
                                     f"{owner} jaboticaba token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in JABOTICABA_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on jaboticaba {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on jaboticaba {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, JABOTICABA_JSON, "jaboticaba.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          JABOTICABA_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(JABOTICABA_JSON["core"]["faqs"]) + len(JABOTICABA_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', JABOTICABA_PAGES[st], f"{st} missing Sources")
        for s in JABOTICABA_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in JABOTICABA_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in ("business.qld.gov.au", "dpird.wa.gov.au")),
            "expected at least one gov authority among the jaboticaba sources",
        )

    def test_owned_archives_are_cited(self):
        # Archives-first: the guide must lean on Benedict's owned RFCA + WANATCA archives.
        domains = " ".join(s["url"] for s in JABOTICABA_JSON["sources"])
        self.assertIn("rfcarchives.org.au", domains, "expected an owned RFCA citation")
        self.assertIn("wanatca.org.au", domains, "expected an owned WANATCA citation")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in JABOTICABA_JSON["sources"]}
        cited = set()
        for block in [JABOTICABA_JSON["core"]] + list(JABOTICABA_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "jaboticaba guide cites an unknown source id")

    def test_sources_note_is_not_olive_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", JABOTICABA_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', JABOTICABA_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("jaboticaba"))
        m = re.search(r'id="further-reading".*?</section>', JABOTICABA_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)        # curated WANATCA Passmore paper
        self.assertIn("rfcarchives.org.au", fr)    # auto-merged RFCA index entries
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("jaboticaba")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("jaboticaba").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("jaboticaba", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    def test_fruit_fly_resistance_is_qualified_not_absolute(self):
        # Sources support "largely resistant" (Passmore + Green Harvest), NOT a gov
        # "fruit fly proof" claim. Guard against an over-strong assertion creeping in.
        blob = json.dumps(JABOTICABA_JSON).lower()
        self.assertIn("fruit-fly resistant", blob)
        self.assertNotIn("fruit fly proof", blob)
        self.assertNotIn("fruit-fly proof", blob)


if __name__ == "__main__":
    unittest.main()
