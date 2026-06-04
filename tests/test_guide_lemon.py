"""
Lemon growing-guide tests (tools/scrapers/growing_guides/lemon.json). Flagship WA.
In its own file so parallel guide runs never collide on a shared test module.

Lemon is a citrus, so (unlike the rare-fruit guides) its owned "Further reading"
comes from the RFCA Citrus folder hand-curated into further_reading, not from the
generated archive index (the "Citrus" folder name does not map to the lemon slug).
There is no citable WANATCA lemon article, so this guide intentionally has no
WANATCA Further reading link.
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

LEMON_SPECIES = {"common_name": "Lemon", "latin_name": "Citrus limon",
                 "description": "Generic lemon blurb.", "slug": "lemon"}


def _lemon_products():
    return [
        {"title": f"Lemon {i}", "url": f"https://nursery.example/lemon-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 35.0 + i,
         "available": True, "species": LEMON_SPECIES}
        for i in range(4)
    ]


LEMON_PAGES = build_state_pages("lemon", _lemon_products())
LEMON_JSON = load_guide("lemon")

# Tokens unique to one state's overlay (deliberately excluding shared names such as
# "Riverina" and "Sunraysia", which appear in more than one state's pest notes).
LEMON_REGION_TOKENS = {
    "WA": ["Gingin", "Carnarvon", "Gascoyne"],
    "QLD": ["Central Burnett", "Gayndah", "Mundubbera"],
    "NSW": ["Griffith", "Leeton", "Murrumbidgee"],
    "VIC": ["Mildura", "Robinvale", "Murray Valley"],
}


class LemonGuideTests(unittest.TestCase):
    """Same guarantees as olive, on a citrus crop with citrus regions and pests."""

    def test_pages_build_and_replace_blurb(self):
        for st, html in LEMON_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} lemon page too small")
            self.assertNotIn("Generic lemon blurb", html, f"{st} still shows the blurb")

    def test_state_pages_mutually_distinct(self):
        bodies = list(LEMON_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two lemon state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in LEMON_REGION_TOKENS.items():
            self.assertTrue(any(t in LEMON_PAGES[st] for t in tokens),
                            f"{st} lemon page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in LEMON_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, LEMON_PAGES[other],
                                     f"{owner} lemon token '{t}' leaked onto {other} page")

    def test_stock_table_stays_above_guide(self):
        qld = LEMON_PAGES["QLD"]
        self.assertLess(qld.index("<table"), qld.index("Growing Lemon in Queensland"),
                        "stock table must precede the lemon guide")

    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in LEMON_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on lemon {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on lemon {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, LEMON_JSON, "lemon.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          LEMON_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} lemon page missing FAQPage JSON-LD")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(LEMON_JSON["core"]["faqs"]) + len(LEMON_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} lemon FAQ count mismatch")

    def test_sources_present_https_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', LEMON_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} lemon page missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} lemon Sources has no links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, url)
                self.assertIn("nofollow", attrs, url)

    def test_guide_sources_https_and_cited_ids_resolve(self):
        for s in LEMON_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in LEMON_JSON["sources"]}
        cited = set()
        for block in [LEMON_JSON["core"]] + list(LEMON_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "lemon guide cites an unknown source id")

    def test_authoritative_domains_present(self):
        domains = " ".join(s["url"] for s in LEMON_JSON["sources"])
        for d in ("dpird.wa.gov.au", "dpi.nsw.gov.au", "business.qld.gov.au",
                  "citrusaustralia.com.au", "rfcarchives.org.au"):
            self.assertIn(d, domains, f"expected a {d} source")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', LEMON_PAGES[st]))
            self.assertIn("lemon", linked, f"{st} should link to /species/lemon.html")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that 404")

    def test_further_reading_owned_and_followed(self):
        fr = re.search(r'id="further-reading".*?</section>', LEMON_PAGES["WA"], re.S)
        self.assertIsNotNone(fr, "lemon WA page missing Further reading")
        block = fr.group(0)
        # Owned RFCA Citrus articles, hand-curated and followed (no nofollow).
        self.assertIn("rfcarchives.org.au", block)
        for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block):
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_is_curated_rfca_citrus(self):
        # The Citrus RFCA folder does not map to the lemon slug, so further reading is
        # purely the hand-curated owned links (no generated archive merge), deduped.
        items = gg.get_further_reading("lemon")
        urls = [e["url"] for e in items]
        self.assertTrue(urls, "lemon has no further reading")
        self.assertTrue(all("rfcarchives.org.au/Next/Fruits/Citrus" in u for u in urls),
                        "lemon further reading should be the curated RFCA Citrus articles")
        self.assertEqual(len(urls), len(set(urls)), "lemon further reading not deduped")


if __name__ == "__main__":
    unittest.main()
