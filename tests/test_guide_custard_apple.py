"""
Custard apple growing-guide tests (tools/scrapers/growing_guides/custard-apple.json).
Flagship QLD (the heart of the Australian custard apple / atemoya industry), with a
near-equal Northern NSW region. In its own file so parallel guide runs never collide
on a shared test module. The slug is hyphenated (custard-apple) but a Python module
name cannot contain a dash, so this file uses an underscore; the slug passed to the
builders stays hyphenated.
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

CUSTARD_SPECIES = {"common_name": "Custard Apple", "latin_name": "Annona reticulata",
                   "description": "Generic custard apple blurb.", "slug": "custard-apple"}


def _custard_products():
    return [
        {"title": f"Custard Apple {i}", "url": f"https://nursery.example/custard-apple-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 80.0 + i,
         "available": True, "species": CUSTARD_SPECIES}
        for i in range(4)
    ]


CUSTARD_PAGES = build_state_pages("custard-apple", _custard_products())
CUSTARD_JSON = load_guide("custard-apple")

# Region tokens unique to each state's overlay (no leaks across states). Kept distinct
# from every nursery name and product title in the stock table so the shared table
# cannot trip the leak guard.
CUSTARD_REGION_TOKENS = {
    "WA": ["Carnarvon", "Kununurra", "Gingin"],
    "QLD": ["Sunshine Coast", "Atherton", "Yeppoon", "Wide Bay"],
    "NSW": ["Lismore", "Alstonville", "Coffs Harbour", "Stuarts Point"],
    "VIC": ["Melbourne", "greenhouse"],
}


class CustardAppleGuideTests(unittest.TestCase):
    """Same guarantees as olive and mango, on a subtropical Annona with hand pollination."""

    def test_pages_build_and_replace_blurb(self):
        for st, html in CUSTARD_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} custard apple page too small")
            self.assertNotIn("Generic custard apple blurb", html, f"{st} still shows the blurb")

    def test_state_pages_mutually_distinct(self):
        bodies = list(CUSTARD_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two custard apple state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in CUSTARD_REGION_TOKENS.items():
            self.assertTrue(any(t in CUSTARD_PAGES[st] for t in tokens),
                            f"{st} custard apple page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in CUSTARD_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, CUSTARD_PAGES[other],
                                     f"{owner} custard apple token '{t}' leaked onto {other} page")

    def test_stock_table_stays_above_guide(self):
        qld = CUSTARD_PAGES["QLD"]
        self.assertLess(qld.index("<table"), qld.index("Growing Custard Apple in Queensland"),
                        "stock table must precede the custard apple guide")

    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in CUSTARD_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on custard apple {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on custard apple {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, CUSTARD_JSON, "custard-apple.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          CUSTARD_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} custard apple page missing FAQPage JSON-LD")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(CUSTARD_JSON["core"]["faqs"]) + len(CUSTARD_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} custard apple FAQ count mismatch")

    def test_sources_present_https_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', CUSTARD_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} custard apple page missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} custard apple Sources has no links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, url)
                self.assertIn("nofollow", attrs, url)

    def test_guide_sources_https_and_cited_ids_resolve(self):
        for s in CUSTARD_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in CUSTARD_JSON["sources"]}
        cited = set()
        for block in [CUSTARD_JSON["core"]] + list(CUSTARD_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "custard apple guide cites an unknown source id")

    def test_authoritative_domains_present(self):
        domains = " ".join(s["url"] for s in CUSTARD_JSON["sources"])
        for d in ("custardapple.com.au", "business.qld.gov.au", "dpird.wa.gov.au",
                  "era.dpi.qld.gov.au", "rfcarchives.org.au"):
            self.assertIn(d, domains, f"expected a {d} source")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', CUSTARD_PAGES[st]))
            self.assertIn("custard-apple", linked, f"{st} should link to /species/custard-apple.html")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that 404")

    def test_further_reading_owned_and_followed(self):
        fr = re.search(r'id="further-reading".*?</section>', CUSTARD_PAGES["WA"], re.S)
        self.assertIsNotNone(fr, "custard apple WA page missing Further reading")
        block = fr.group(0)
        self.assertIn("wanatca.org.au", block)
        self.assertIn("rfcarchives.org.au", block)
        for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block):
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_merges_curated_and_archive(self):
        urls = [e["url"] for e in gg.get_further_reading("custard-apple")]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA missing")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/CustardApple" in u for u in urls), "RFCA missing")
        self.assertEqual(len(urls), len(set(urls)), "custard apple further reading not deduped")


if __name__ == "__main__":
    unittest.main()
