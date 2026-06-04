"""
Apricot growing-guide tests (tools/scrapers/growing_guides/apricot.json). A temperate stone
fruit (Prunus armeniaca): it uses the existing "temperate" climate note (no new
SPECIES_CLIMATE_CATEGORY entry) and, like peach, has NO owned-archive Further reading
(no RFCA Apricot folder, no WANATCA apricot yearbook article), which is asserted below.
In its own file so parallel guide runs never collide.
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

APRICOT_SPECIES = {
    "common_name": "Apricot",
    "latin_name": "Prunus armeniaca",
    "description": "Generic apricot blurb that should be replaced by the rich guide.",
    "slug": "apricot",
}


def _apricot_products(n=6):
    return [
        {
            "title": f"Apricot Variety {i}",
            "url": f"https://nursery.example/apricot-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 30.0 + i * 5,
            "available": True,
            "species": APRICOT_SPECIES,
        }
        for i in range(n)
    ]


APRICOT_PAGES = build_state_pages("apricot", _apricot_products())
APRICOT_JSON = load_guide("apricot")

# Each state's distinctive region tokens: present on its own page, absent from the others.
APRICOT_REGION_TOKENS = {
    "WA": ["Donnybrook", "Perth Hills"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Hilltops", "Riverina"],
    "VIC": ["Goulburn Valley", "Sunraysia"],
}


class ApricotGuideTests(unittest.TestCase):
    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in APRICOT_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} apricot page too small")

    def test_canonical_and_og(self):
        wa = APRICOT_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-apricot-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        wa = APRICOT_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Apricot in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in APRICOT_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Apricot in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in APRICOT_PAGES.items():
            self.assertNotIn("Generic apricot blurb", html, f"{st} still shows the blurb")

    def test_temperate_climate_note_used(self):
        # Apricot must inherit the stone-fruit "temperate" note (chill-hours advice),
        # NOT the mediterranean note.
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["apricot"], "temperate")
        note = bssp.get_climate_note("Apricot", "WA")
        self.assertIn("low-chill", note)

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(APRICOT_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two apricot state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in APRICOT_REGION_TOKENS.items():
            self.assertTrue(any(t in APRICOT_PAGES[st] for t in tokens),
                            f"{st} apricot page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in APRICOT_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, APRICOT_PAGES[other],
                                     f"{owner} apricot token '{t}' leaked onto {other} page")

    def test_overlay_then_core(self):
        wa = gg.render_combo_guide("apricot", "WA")
        self.assertIn("Where apricots grow in WA", wa)   # overlay
        self.assertIn("Choosing a variety", wa)          # core
        self.assertLess(wa.index("Where apricots grow in WA"), wa.index("Choosing a variety"))

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in APRICOT_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} apricot page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} apricot page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, APRICOT_JSON, "apricot.json")

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', APRICOT_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', APRICOT_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in APRICOT_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in APRICOT_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "dpi.nsw.gov.au", "agriculture.vic.gov.au",
            )),
            "expected at least one state-agriculture authority among the apricot sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in APRICOT_JSON["sources"]}
        cited = set()
        for block in [APRICOT_JSON["core"]] + list(APRICOT_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "apricot guide cites an unknown source id")

    def test_no_orphan_sources(self):
        # Every declared source should actually be cited somewhere (no dead weight).
        src_ids = {s["id"] for s in APRICOT_JSON["sources"]}
        cited = set()
        for block in [APRICOT_JSON["core"]] + list(APRICOT_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(src_ids - cited, set(), "apricot guide declares sources it never cites")

    def test_no_bot_blocked_gov_sources(self):
        # NSW DPI and Agriculture Victoria return HTTP 403 to automated fetchers, so the
        # "every cited URL must curl 200" rule means they must not be cited directly (the
        # convention set by DEC-145). The VIC facts are anchored on the Goulburn Murray
        # Valley fruit fly project, Winetitles, Interstate Quarantine, SGA, BeeAware and
        # First 5000 instead, and the QLD DAF kit covers stone-fruit water and feeding.
        for s in APRICOT_JSON["sources"]:
            self.assertNotIn("dpi.nsw.gov.au", s["url"], f"NSW DPI 403s to curl: {s['url']}")
            self.assertNotIn("agriculture.vic.gov.au", s["url"], f"Ag Vic 403s to curl: {s['url']}")

    def test_sources_note_does_not_leak_olive_copy(self):
        self.assertNotIn("olive-industry", APRICOT_PAGES["WA"])

    # --- FAQ + links ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(APRICOT_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(APRICOT_JSON["core"]["faqs"]) + len(APRICOT_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', APRICOT_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("apricot"))

    # --- apricot-specific correctness guards ---
    def test_self_fertile_is_stated(self):
        # The headline difference from plum/cherry: apricots are self-fertile.
        core_text = " ".join(s["body"] for s in APRICOT_JSON["core"]["sections"])
        self.assertIn("self-fertile", core_text)
        headings = [s["heading"].lower() for s in APRICOT_JSON["core"]["sections"]]
        self.assertTrue(any("one tree" in h for h in headings),
                        "expected a 'one tree is enough' pollination heading")

    def test_summer_pruning_rule_present(self):
        # Apricot-specific: prune in summer/autumn, never winter (bacterial canker / silver leaf).
        core_text = " ".join(s["heading"] + " " + s["body"] for s in APRICOT_JSON["core"]["sections"])
        self.assertIn("never in winter", core_text)
        self.assertIn("bacterial canker", core_text)

    def test_not_peach_leaf_curl(self):
        # Correctness: apricots do not get peach leaf curl; the guide must say so, and must
        # not tell people their apricot needs a leaf-curl spray.
        faqs = " ".join(f["q"] + " " + f["a"] for f in APRICOT_JSON["core"]["faqs"])
        self.assertIn("leaf curl", faqs.lower())
        self.assertIn("not an apricot disease", faqs)

    def test_qld_is_honest_about_marginality(self):
        qld = APRICOT_JSON["states"]["QLD"]
        text = qld["intro"] + " " + " ".join(s["body"] for s in qld["sections"])
        self.assertIn("Granite Belt", text)
        # The humid coast/subtropics are called out as a poor fit.
        self.assertTrue("humid" in text and ("coast" in text or "subtropic" in text))

    # --- no owned-archive Further reading (no RFCA Apricot folder, no WANATCA article) ---
    def test_no_curated_or_archive_further_reading(self):
        self.assertNotIn("further_reading", APRICOT_JSON)
        self.assertEqual(gg.get_further_reading("apricot"), [])

    def test_no_further_reading_section_on_pages(self):
        for st in STATES:
            self.assertNotIn('id="further-reading"', APRICOT_PAGES[st],
                             f"{st} apricot page should have no archive Further reading section")


if __name__ == "__main__":
    unittest.main()
