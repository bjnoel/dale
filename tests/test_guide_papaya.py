"""
Papaya growing-guide tests (tools/scrapers/growing_guides/papaya.json). Flagship QLD.
In its own file so parallel guide runs never collide on a shared test module.

Papaya is the tropical, frost-tender crop whose state pages must stay genuinely
distinct: far-north Queensland is the heartland, the warm WA north and the NSW
far-north coast are the edges, and Victoria is a greenhouse-only curiosity. The
further-reading guard here is stronger than the other species files: papaya curates
an owned WANATCA + RFCA set that must stay followed, plus one third-party WA Rare
Fruit Club link that must stay nofollow.
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

PAPAYA_SPECIES = {"common_name": "Papaya", "latin_name": "Carica papaya",
                  "description": "Generic papaya blurb.", "slug": "papaya"}


def _papaya_products():
    return [
        {"title": f"Papaya {i}", "url": f"https://nursery.example/papaya-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 30.0 + i,
         "available": True, "species": PAPAYA_SPECIES}
        for i in range(4)
    ]


PAPAYA_PAGES = build_state_pages("papaya", _papaya_products())
PAPAYA_JSON = load_guide("papaya")

# Region tokens that must each appear on their own state page and on no other.
# Chosen to avoid leak vectors: "Perth" is deliberately NOT used because the
# WANATCA "Exotic fruits in Perth" further-reading title renders on every page.
PAPAYA_REGION_TOKENS = {
    "WA": ["Kununurra", "Kimberley", "Gascoyne", "Carnarvon"],
    "QLD": ["Mareeba", "Atherton", "Tully", "Innisfail", "Lakeland"],
    "NSW": ["Northern Rivers", "Tweed", "Murwillumbah", "Coffs Harbour"],
    "VIC": ["Melbourne", "greenhouse"],
}


class PapayaGuideTests(unittest.TestCase):
    """Same guarantees as olive/mango, on a tropical crop with its own regions and pests."""

    def test_pages_build_and_replace_blurb(self):
        for st, html in PAPAYA_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} papaya page too small")
            self.assertNotIn("Generic papaya blurb", html, f"{st} still shows the blurb")

    def test_state_pages_mutually_distinct(self):
        bodies = list(PAPAYA_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two papaya state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in PAPAYA_REGION_TOKENS.items():
            self.assertTrue(any(t in PAPAYA_PAGES[st] for t in tokens),
                            f"{st} papaya page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in PAPAYA_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, PAPAYA_PAGES[other],
                                     f"{owner} papaya token '{t}' leaked onto {other} page")

    def test_stock_table_stays_above_guide(self):
        qld = PAPAYA_PAGES["QLD"]
        self.assertLess(qld.index("<table"), qld.index("Growing Papaya in Queensland"),
                        "stock table must precede the papaya guide")

    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in PAPAYA_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on papaya {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on papaya {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, PAPAYA_JSON, "papaya.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          PAPAYA_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} papaya page missing FAQPage JSON-LD")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(PAPAYA_JSON["core"]["faqs"]) + len(PAPAYA_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} papaya FAQ count mismatch")

    def test_sources_present_https_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', PAPAYA_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} papaya page missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} papaya Sources has no links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, url)
                self.assertIn("nofollow", attrs, url)

    def test_guide_sources_https_and_cited_ids_resolve(self):
        for s in PAPAYA_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in PAPAYA_JSON["sources"]}
        cited = set()
        for block in [PAPAYA_JSON["core"]] + list(PAPAYA_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "papaya guide cites an unknown source id")

    def test_authoritative_domains_present(self):
        domains = " ".join(s["url"] for s in PAPAYA_JSON["sources"])
        for d in ("business.qld.gov.au", "nt.gov.au", "dpird.wa.gov.au", "australianpapaya.com.au"):
            self.assertIn(d, domains, f"expected a {d} source")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', PAPAYA_PAGES[st]))
            self.assertIn("papaya", linked, f"{st} should link to /species/papaya.html")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that 404")

    def test_further_reading_owned_followed_and_rfcwa_nofollow(self):
        """The WA page's Further reading must carry the owned WANATCA + RFCA archives
        as FOLLOWED links, and the one third-party WA Rare Fruit Club link as nofollow."""
        fr = re.search(r'id="further-reading".*?</section>', PAPAYA_PAGES["WA"], re.S)
        self.assertIsNotNone(fr, "papaya WA page missing Further reading")
        block = fr.group(0)
        self.assertIn("wanatca.org.au", block)
        self.assertIn("rfcarchives.org.au", block)
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block)
        self.assertTrue(links, "no further-reading links rendered")
        saw_owned = saw_rfcwa = False
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            if "rfcarchives.org.au" in url or "wanatca.org.au" in url:
                saw_owned = True
                self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
            elif "rarefruitclub.au" in url:
                saw_rfcwa = True
                self.assertIn("nofollow", attrs, f"third-party RFCWA link must be nofollow: {url}")
        self.assertTrue(saw_owned, "expected owned RFCA/WANATCA further-reading links")
        self.assertTrue(saw_rfcwa, "expected the third-party RFCWA nofollow link")

    def test_further_reading_merges_curated_and_archive(self):
        urls = [e["url"] for e in gg.get_further_reading("papaya")]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA missing")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/Papaya" in u for u in urls), "RFCA missing")
        self.assertEqual(len(urls), len(set(urls)), "papaya further reading not deduped")
        # The curated set fills the cap, so the off-topic babaco archive entries (same
        # RFCA folder, but a different fruit) must not surface in the rendered list.
        self.assertFalse(any("Babaco" in (e.get("title") or "") for e in gg.get_further_reading("papaya")),
                         "off-topic babaco archive entry leaked into papaya further reading")


if __name__ == "__main__":
    unittest.main()
