"""
Lychee growing-guide tests (tools/scrapers/growing_guides/lychee.json). Flagship QLD by
climate, strongest WA overlay by traffic. In its own file so parallel guide runs never
collide on a shared test module.
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

LYCHEE_SPECIES = {
    "common_name": "Lychee",
    "latin_name": "Litchi chinensis",
    "description": "Generic lychee blurb that should be replaced by the rich guide.",
    "slug": "lychee",
}


def _lychee_products(n=6):
    names = ["Kwai May Pink", "Wai Chee", "Tai So", "Salathiel", "Bengal", "Erdon Lee"]
    return [
        {"title": f"Lychee {names[i % len(names)]}",
         "url": f"https://nursery.example/lychee-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 49.0 + i * 5,
         "available": True, "species": LYCHEE_SPECIES}
        for i in range(n)
    ]


LYCHEE_PAGES = build_state_pages("lychee", _lychee_products())
LYCHEE_JSON = load_guide("lychee")

LYCHEE_REGION_TOKENS = {
    "QLD": ["Atherton", "Bundaberg"],
    "WA": ["Kununurra", "Carnarvon"],
    "NSW": ["Northern Rivers", "Coffs Harbour"],
    "VIC": ["hothouse", "Melbourne"],
}


class LycheeGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in LYCHEE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} lychee page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(LYCHEE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two lychee state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in LYCHEE_PAGES.items():
            self.assertNotIn("Generic lychee blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in LYCHEE_REGION_TOKENS.items():
            self.assertTrue(any(t in LYCHEE_PAGES[st] for t in tokens),
                            f"{st} lychee page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in LYCHEE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, LYCHEE_PAGES[other],
                                     f"{owner} lychee token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in LYCHEE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on lychee {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on lychee {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, LYCHEE_JSON, "lychee.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          LYCHEE_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(LYCHEE_JSON["core"]["faqs"]) + len(LYCHEE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', LYCHEE_PAGES[st], f"{st} missing Sources")
        for s in LYCHEE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in LYCHEE_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "fao.org", "australianlychee.com.au",
            )),
            "expected at least one gov/industry authority among the lychee sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in LYCHEE_JSON["sources"]}
        cited = set()
        for block in [LYCHEE_JSON["core"]] + list(LYCHEE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "lychee guide cites an unknown source id")

    def test_sources_note_is_lychee_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", LYCHEE_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', LYCHEE_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("lychee"))
        m = re.search(r'id="further-reading".*?</section>', LYCHEE_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("lychee")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("lychee").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("lychee", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
