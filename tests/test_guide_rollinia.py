"""
Rollinia growing-guide tests (tools/scrapers/growing_guides/rollinia.json).
Flagship QLD (the far-north tropics are the only part of Australia where rollinia,
an ultra-tropical Annona mucosa / biriba, is genuinely at home), with the subtropical
NSW Northern Rivers as the realistic secondary region and WA/VIC marginal. In its own
file so parallel guide runs never collide on a shared test module.
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

ROLLINIA_SPECIES = {"common_name": "Rollinia", "latin_name": "Annona mucosa",
                    "description": "Generic rollinia blurb.", "slug": "rollinia"}


def _rollinia_products():
    return [
        {"title": f"Rollinia {i}", "url": f"https://nursery.example/rollinia-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 40.0 + i,
         "available": True, "species": ROLLINIA_SPECIES}
        for i in range(4)
    ]


ROLLINIA_PAGES = build_state_pages("rollinia", _rollinia_products())
ROLLINIA_JSON = load_guide("rollinia")

# Region tokens unique to each state's overlay (no leaks across states). Kept distinct
# from every nursery name and product title in the stock table so the shared table
# cannot trip the leak guard, and from the shared core.
# Note: "Perth" is deliberately NOT a WA token here, because the site footer
# ("A project by Benedict Noel, Perth WA") puts it on every page. The WA overlay
# copy still discusses Perth; these tokens just have to be WA-only on the page.
ROLLINIA_REGION_TOKENS = {
    "WA": ["Carnarvon", "Gascoyne", "Kununurra"],
    "QLD": ["Cairns", "Innisfail", "Atherton"],
    "NSW": ["Northern Rivers", "Lismore", "Murwillumbah", "Alstonville"],
    "VIC": ["Melbourne"],
}


class RolliniaGuideTests(unittest.TestCase):
    """Same guarantees as olive and custard apple, on an ultra-tropical, frost-tender Annona."""

    def test_pages_build_and_replace_blurb(self):
        for st, html in ROLLINIA_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} rollinia page too small")
            self.assertNotIn("Generic rollinia blurb", html, f"{st} still shows the blurb")

    def test_state_pages_mutually_distinct(self):
        bodies = list(ROLLINIA_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two rollinia state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in ROLLINIA_REGION_TOKENS.items():
            self.assertTrue(any(t in ROLLINIA_PAGES[st] for t in tokens),
                            f"{st} rollinia page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in ROLLINIA_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, ROLLINIA_PAGES[other],
                                     f"{owner} rollinia token '{t}' leaked onto {other} page")

    def test_stock_table_stays_above_guide(self):
        qld = ROLLINIA_PAGES["QLD"]
        self.assertLess(qld.index("<table"), qld.index("Growing Rollinia in Queensland"),
                        "stock table must precede the rollinia guide")

    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in ROLLINIA_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on rollinia {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on rollinia {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, ROLLINIA_JSON, "rollinia.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          ROLLINIA_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} rollinia page missing FAQPage JSON-LD")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(ROLLINIA_JSON["core"]["faqs"]) + len(ROLLINIA_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} rollinia FAQ count mismatch")

    def test_sources_present_https_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', ROLLINIA_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} rollinia page missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} rollinia Sources has no links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, url)
                self.assertIn("nofollow", attrs, url)

    def test_guide_sources_https_and_cited_ids_resolve(self):
        for s in ROLLINIA_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in ROLLINIA_JSON["sources"]}
        cited = set()
        for block in [ROLLINIA_JSON["core"]] + list(ROLLINIA_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "rollinia guide cites an unknown source id")

    def test_authoritative_domains_present(self):
        domains = " ".join(s["url"] for s in ROLLINIA_JSON["sources"])
        for d in ("rfcarchives.org.au", "ask.ifas.ufl.edu", "business.qld.gov.au",
                  "dpird.wa.gov.au", "custardapple.com.au", "daleysfruit.com.au"):
            self.assertIn(d, domains, f"expected a {d} source")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', ROLLINIA_PAGES[st]))
            self.assertIn("rollinia", linked, f"{st} should link to /species/rollinia.html")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that 404")

    def test_further_reading_owned_and_followed(self):
        fr = re.search(r'id="further-reading".*?</section>', ROLLINIA_PAGES["WA"], re.S)
        self.assertIsNotNone(fr, "rollinia WA page missing Further reading")
        block = fr.group(0)
        self.assertIn("wanatca.org.au", block)
        self.assertIn("rfcarchives.org.au", block)
        for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block):
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_merges_curated_and_archive(self):
        urls = [e["url"] for e in gg.get_further_reading("rollinia")]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA missing")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/Rollinia" in u for u in urls), "RFCA missing")
        self.assertEqual(len(urls), len(set(urls)), "rollinia further reading not deduped")


if __name__ == "__main__":
    unittest.main()
