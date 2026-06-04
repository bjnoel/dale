"""
Peach growing-guide tests (tools/scrapers/growing_guides/peach.json). A temperate stone
fruit: it uses the existing "temperate" climate note (no new SPECIES_CLIMATE_CATEGORY entry)
and, unlike olive, has NO owned-archive Further reading (no RFCA Peach folder, no WANATCA
peach article), which is asserted below. In its own file so parallel guide runs never collide.
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

PEACH_SPECIES = {
    "common_name": "Peach",
    "latin_name": "Prunus persica",
    "description": "Generic peach blurb that should be replaced by the rich guide.",
    "slug": "peach",
}


def _peach_products(n=6):
    return [
        {
            "title": f"Peach Variety {i}",
            "url": f"https://nursery.example/peach-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 30.0 + i * 5,
            "available": True,
            "species": PEACH_SPECIES,
        }
        for i in range(n)
    ]


PEACH_PAGES = build_state_pages("peach", _peach_products())
PEACH_JSON = load_guide("peach")

PEACH_REGION_TOKENS = {
    "WA": ["Donnybrook", "Perth Hills"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Bilpin", "Orange"],
    "VIC": ["Goulburn Valley", "Shepparton"],
}


class PeachGuideTests(unittest.TestCase):
    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in PEACH_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} peach page too small")

    def test_canonical_and_og(self):
        wa = PEACH_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-peach-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        wa = PEACH_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Peach in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in PEACH_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Peach in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in PEACH_PAGES.items():
            self.assertNotIn("Generic peach blurb", html, f"{st} still shows the blurb")

    def test_temperate_climate_note_used(self):
        # Peach must inherit the stone-fruit "temperate" note (chill-hours advice),
        # NOT the mediterranean note.
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["peach"], "temperate")
        note = bssp.get_climate_note("Peach", "WA")
        self.assertIn("low-chill", note)

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(PEACH_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two peach state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in PEACH_REGION_TOKENS.items():
            self.assertTrue(any(t in PEACH_PAGES[st] for t in tokens),
                            f"{st} peach page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in PEACH_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, PEACH_PAGES[other],
                                     f"{owner} peach token '{t}' leaked onto {other} page")

    def test_overlay_then_core(self):
        wa = gg.render_combo_guide("peach", "WA")
        self.assertIn("Where peaches grow in WA", wa)   # overlay
        self.assertIn("Choosing a variety", wa)         # core
        self.assertLess(wa.index("Where peaches grow in WA"), wa.index("Choosing a variety"))

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in PEACH_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} peach page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} peach page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, PEACH_JSON, "peach.json")

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', PEACH_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', PEACH_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in PEACH_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in PEACH_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "dpi.nsw.gov.au", "agriculture.vic.gov.au",
            )),
            "expected at least one state-agriculture authority among the peach sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in PEACH_JSON["sources"]}
        cited = set()
        for block in [PEACH_JSON["core"]] + list(PEACH_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "peach guide cites an unknown source id")

    def test_sources_note_does_not_leak_olive_copy(self):
        self.assertNotIn("olive-industry", PEACH_PAGES["WA"])

    # --- FAQ + links ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(PEACH_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(PEACH_JSON["core"]["faqs"]) + len(PEACH_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', PEACH_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("peach"))

    # --- no owned-archive Further reading (mainstream stone fruit) ---
    def test_no_curated_or_archive_further_reading(self):
        self.assertNotIn("further_reading", PEACH_JSON)
        self.assertEqual(gg.get_further_reading("peach"), [])

    def test_no_further_reading_section_on_pages(self):
        for st in STATES:
            self.assertNotIn('id="further-reading"', PEACH_PAGES[st],
                             f"{st} peach page should have no archive Further reading section")


if __name__ == "__main__":
    unittest.main()
