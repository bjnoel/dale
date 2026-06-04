"""
Mango growing-guide tests (tools/scrapers/growing_guides/mango.json). Flagship QLD.
In its own file so parallel guide runs never collide on a shared test module.
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

MANGO_SPECIES = {"common_name": "Mango", "latin_name": "Mangifera indica",
                 "description": "Generic mango blurb.", "slug": "mango"}


def _mango_products():
    return [
        {"title": f"Mango {i}", "url": f"https://nursery.example/mango-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 40.0 + i,
         "available": True, "species": MANGO_SPECIES}
        for i in range(4)
    ]


MANGO_PAGES = build_state_pages("mango", _mango_products())
MANGO_JSON = load_guide("mango")

MANGO_REGION_TOKENS = {
    "WA": ["Kununurra", "Carnarvon"],
    "QLD": ["Mareeba", "Dimbulah", "Burdekin"],
    "NSW": ["Northern Rivers", "Tweed"],
    "VIC": ["Melbourne", "greenhouse"],
}


class MangoGuideTests(unittest.TestCase):
    """Same guarantees as olive, on a different crop with different regions and pests."""

    def test_pages_build_and_replace_blurb(self):
        for st, html in MANGO_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} mango page too small")
            self.assertNotIn("Generic mango blurb", html, f"{st} still shows the blurb")

    def test_state_pages_mutually_distinct(self):
        bodies = list(MANGO_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two mango state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in MANGO_REGION_TOKENS.items():
            self.assertTrue(any(t in MANGO_PAGES[st] for t in tokens),
                            f"{st} mango page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in MANGO_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, MANGO_PAGES[other],
                                     f"{owner} mango token '{t}' leaked onto {other} page")

    def test_stock_table_stays_above_guide(self):
        qld = MANGO_PAGES["QLD"]
        self.assertLess(qld.index("<table"), qld.index("Growing Mango in Queensland"),
                        "stock table must precede the mango guide")

    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in MANGO_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on mango {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on mango {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, MANGO_JSON, "mango.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          MANGO_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} mango page missing FAQPage JSON-LD")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(MANGO_JSON["core"]["faqs"]) + len(MANGO_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} mango FAQ count mismatch")

    def test_sources_present_https_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', MANGO_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} mango page missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} mango Sources has no links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, url)
                self.assertIn("nofollow", attrs, url)

    def test_guide_sources_https_and_cited_ids_resolve(self):
        for s in MANGO_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in MANGO_JSON["sources"]}
        cited = set()
        for block in [MANGO_JSON["core"]] + list(MANGO_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "mango guide cites an unknown source id")

    def test_authoritative_domains_present(self):
        domains = " ".join(s["url"] for s in MANGO_JSON["sources"])
        for d in ("business.qld.gov.au", "nt.gov.au", "dpird.wa.gov.au", "mangoes.net.au"):
            self.assertIn(d, domains, f"expected a {d} source")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', MANGO_PAGES[st]))
            self.assertIn("mango", linked, f"{st} should link to /species/mango.html")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that 404")

    def test_further_reading_owned_and_followed(self):
        fr = re.search(r'id="further-reading".*?</section>', MANGO_PAGES["WA"], re.S)
        self.assertIsNotNone(fr, "mango WA page missing Further reading")
        block = fr.group(0)
        self.assertIn("wanatca.org.au", block)
        self.assertIn("rfcarchives.org.au", block)
        for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block):
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_merges_curated_and_archive(self):
        urls = [e["url"] for e in gg.get_further_reading("mango")]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA missing")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/Mango" in u for u in urls), "RFCA missing")
        self.assertEqual(len(urls), len(set(urls)), "mango further reading not deduped")


if __name__ == "__main__":
    unittest.main()
