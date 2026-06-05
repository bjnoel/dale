"""
Nectarine growing-guide tests (tools/scrapers/growing_guides/nectarine.json). A temperate
stone fruit and botanically a smooth-skinned peach (Prunus persica), so like peach it uses the
existing "temperate" climate note (no new SPECIES_CLIMATE_CATEGORY entry) and, being a mainstream
stone fruit, has NO owned-archive Further reading (no RFCA Nectarine folder, no WANATCA nectarine
article), which is asserted below. The nectarine-specific guards check the smooth-skin framing, the
brown-rot/bacterial-spot susceptibility delta, the self-fertility, and the corrected WA Qfly status
(eradicated on detection, NOT "free of"). In its own file so parallel guide runs never collide.
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

NECTARINE_SPECIES = {
    "common_name": "Nectarine",
    "latin_name": "Prunus persica var. nucipersica",
    "description": "Generic nectarine blurb that should be replaced by the rich guide.",
    "slug": "nectarine",
}


def _nectarine_products(n=6):
    return [
        {
            "title": f"Nectarine Variety {i}",
            "url": f"https://nursery.example/nectarine-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 30.0 + i * 5,
            "available": True,
            "species": NECTARINE_SPECIES,
        }
        for i in range(n)
    ]


NECTARINE_PAGES = build_state_pages("nectarine", _nectarine_products())
NECTARINE_JSON = load_guide("nectarine")

NECTARINE_REGION_TOKENS = {
    "WA": ["Donnybrook", "Manjimup"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Bilpin", "Batlow"],
    "VIC": ["Goulburn Valley", "Shepparton"],
}


class NectarineGuideTests(unittest.TestCase):
    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in NECTARINE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} nectarine page too small")

    def test_canonical_and_og(self):
        wa = NECTARINE_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-nectarine-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        wa = NECTARINE_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Nectarine in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in NECTARINE_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Nectarine in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in NECTARINE_PAGES.items():
            self.assertNotIn("Generic nectarine blurb", html, f"{st} still shows the blurb")

    def test_temperate_climate_note_used(self):
        # Nectarine inherits the stone-fruit "temperate" note (chill-hours advice),
        # NOT the mediterranean note, exactly like peach.
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["nectarine"], "temperate")
        note = bssp.get_climate_note("Nectarine", "WA")
        self.assertIn("low-chill", note)

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(NECTARINE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two nectarine state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in NECTARINE_REGION_TOKENS.items():
            self.assertTrue(any(t in NECTARINE_PAGES[st] for t in tokens),
                            f"{st} nectarine page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in NECTARINE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, NECTARINE_PAGES[other],
                                     f"{owner} nectarine token '{t}' leaked onto {other} page")

    def test_overlay_then_core(self):
        wa = gg.render_combo_guide("nectarine", "WA")
        self.assertIn("Where nectarines grow in WA", wa)   # overlay
        self.assertIn("Choosing a variety", wa)            # core
        self.assertLess(wa.index("Where nectarines grow in WA"), wa.index("Choosing a variety"))

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in NECTARINE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} nectarine page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} nectarine page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, NECTARINE_JSON, "nectarine.json")

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', NECTARINE_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', NECTARINE_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in NECTARINE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in NECTARINE_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in ("dpird.wa.gov.au", "business.qld.gov.au")),
            "expected at least one state-agriculture authority among the nectarine sources",
        )

    def test_no_bot_blocked_gov_sources(self):
        # dpi.nsw.gov.au and agriculture.vic.gov.au return 403 to automated curl (WAF), so they
        # cannot be confirmed under the URL-200 gate and must NOT be cited. The NSW/VIC facts are
        # anchored on FAO, SEDA, Business Queensland and DPIRD instead.
        domains = " ".join(s["url"] for s in NECTARINE_JSON["sources"])
        self.assertNotIn("dpi.nsw.gov.au", domains, "NSW DPI 403s to curl; do not cite it")
        self.assertNotIn("agriculture.vic.gov.au", domains, "Ag Vic 403s to curl; do not cite it")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in NECTARINE_JSON["sources"]}
        cited = set()
        for block in [NECTARINE_JSON["core"]] + list(NECTARINE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "nectarine guide cites an unknown source id")

    def test_sources_note_does_not_leak_olive_copy(self):
        self.assertNotIn("olive-industry", NECTARINE_PAGES["WA"])

    # --- nectarine-specific correctness ---
    def test_smooth_skin_framing_present(self):
        # The defining nectarine fact: a smooth-skinned (fuzz-free) peach. Must appear in the core.
        core = gg.render_species_guide("nectarine")
        self.assertTrue("smooth-skinned" in core or "fuzz-free" in core,
                        "nectarine core should frame the fruit as a smooth-skinned / fuzz-free peach")

    def test_brown_rot_susceptibility_delta(self):
        # The key agronomic delta vs peach: the bare skin makes nectarines more prone to brown rot.
        for st in STATES:
            html = NECTARINE_PAGES[st]
            self.assertIn("brown rot", html.lower(), f"{st} should mention brown rot")
        core = gg.render_species_guide("nectarine")
        self.assertIn("more prone than peaches", core,
                      "core should state nectarines are more prone than peaches to brown rot")

    def test_self_fertile_one_tree(self):
        core = gg.render_species_guide("nectarine")
        self.assertIn("self-fertile", core, "core should state nectarines are self-fertile")

    def test_wa_qfly_corrected_not_free_of(self):
        # Correctness: WA is NOT "free of" Queensland fruit fly. It is a declared/prohibited pest
        # eradicated whenever detected. This corrects the now-stale peach-guide wording.
        wa = NECTARINE_PAGES["WA"]
        self.assertIn("eradicated whenever it is detected", wa,
                      "WA overlay should frame Qfly as eradicated on detection")
        self.assertNotIn("free of Queensland fruit fly", wa,
                         "WA must NOT claim it is free of Queensland fruit fly")

    def test_vic_flagship_production_claim(self):
        # Victoria is the flagship: it grows the bulk of Australia's nectarines.
        vic = NECTARINE_PAGES["VIC"]
        self.assertIn("two thirds of Australia's nectarines", vic)

    # --- FAQ + links ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(NECTARINE_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(NECTARINE_JSON["core"]["faqs"]) + len(NECTARINE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', NECTARINE_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("nectarine"))

    # --- no owned-archive Further reading (mainstream stone fruit, like peach) ---
    def test_no_curated_or_archive_further_reading(self):
        self.assertNotIn("further_reading", NECTARINE_JSON)
        self.assertEqual(gg.get_further_reading("nectarine"), [])

    def test_no_further_reading_section_on_pages(self):
        for st in STATES:
            self.assertNotIn('id="further-reading"', NECTARINE_PAGES[st],
                             f"{st} nectarine page should have no archive Further reading section")


if __name__ == "__main__":
    unittest.main()
