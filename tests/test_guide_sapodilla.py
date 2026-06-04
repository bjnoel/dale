"""
Sapodilla growing-guide tests (tools/scrapers/growing_guides/sapodilla.json). Flagship QLD.
In its own file so parallel guide runs never collide on a shared test module.

Sapodilla is a rare tropical crop, so the guide carries two correctness anchors worth
guarding directly: pollination is NOT a flat "self-fertile" (UF/IFAS: some cultivars are
self-incompatible), and sapodilla IS a Queensland fruit fly host (Business Qld / Plant
Health Australia), not the latex-skinned "resistant" fruit it is sometimes confused with.
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

SAPODILLA_SPECIES = {"common_name": "Sapodilla", "latin_name": "Manilkara zapota",
                     "description": "Generic sapodilla blurb.", "slug": "sapodilla"}


def _sapodilla_products():
    return [
        {"title": f"Sapodilla {i}", "url": f"https://nursery.example/sapodilla-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 39.0 + i,
         "available": True, "species": SAPODILLA_SPECIES}
        for i in range(4)
    ]


SAPODILLA_PAGES = build_state_pages("sapodilla", _sapodilla_products())
SAPODILLA_JSON = load_guide("sapodilla")

# Region tokens unique to each state overlay (must appear on that state, never leak).
SAPODILLA_REGION_TOKENS = {
    "WA": ["Carnarvon", "Kununurra", "Ord River"],
    "QLD": ["Atherton Tableland", "Mareeba", "Innisfail"],
    "NSW": ["Northern Rivers", "Tweed", "Lismore"],
    "VIC": ["Melbourne", "glasshouse"],
}


class SapodillaGuideTests(unittest.TestCase):
    """Same guarantees as olive/mango, on a rare tropical crop with its own regions and pests."""

    def test_pages_build_and_replace_blurb(self):
        for st, html in SAPODILLA_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} sapodilla page too small")
            self.assertNotIn("Generic sapodilla blurb", html, f"{st} still shows the blurb")

    def test_state_pages_mutually_distinct(self):
        bodies = list(SAPODILLA_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two sapodilla state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in SAPODILLA_REGION_TOKENS.items():
            self.assertTrue(any(t in SAPODILLA_PAGES[st] for t in tokens),
                            f"{st} sapodilla page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in SAPODILLA_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, SAPODILLA_PAGES[other],
                                     f"{owner} sapodilla token '{t}' leaked onto {other} page")

    def test_stock_table_stays_above_guide(self):
        qld = SAPODILLA_PAGES["QLD"]
        self.assertLess(qld.index("<table"), qld.index("Growing Sapodilla in Queensland"),
                        "stock table must precede the sapodilla guide")

    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in SAPODILLA_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on sapodilla {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on sapodilla {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, SAPODILLA_JSON, "sapodilla.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          SAPODILLA_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} sapodilla page missing FAQPage JSON-LD")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(SAPODILLA_JSON["core"]["faqs"]) + len(SAPODILLA_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} sapodilla FAQ count mismatch")

    def test_sources_present_https_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', SAPODILLA_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} sapodilla page missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} sapodilla Sources has no links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, url)
                self.assertIn("nofollow", attrs, url)

    def test_guide_sources_https_and_cited_ids_resolve(self):
        for s in SAPODILLA_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in SAPODILLA_JSON["sources"]}
        cited = set()
        for block in [SAPODILLA_JSON["core"]] + list(SAPODILLA_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "sapodilla guide cites an unknown source id")

    def test_authoritative_domains_present(self):
        domains = " ".join(s["url"] for s in SAPODILLA_JSON["sources"])
        for d in ("business.qld.gov.au", "nt.gov.au", "dpird.wa.gov.au", "ifas.ufl.edu"):
            self.assertIn(d, domains, f"expected a {d} source")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', SAPODILLA_PAGES[st]))
            self.assertIn("sapodilla", linked, f"{st} should link to /species/sapodilla.html")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that 404")

    def test_further_reading_owned_and_followed(self):
        fr = re.search(r'id="further-reading".*?</section>', SAPODILLA_PAGES["WA"], re.S)
        self.assertIsNotNone(fr, "sapodilla WA page missing Further reading")
        block = fr.group(0)
        self.assertIn("wanatca.org.au", block)
        self.assertIn("rfcarchives.org.au", block)
        for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block):
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_merges_curated_and_archive(self):
        urls = [e["url"] for e in gg.get_further_reading("sapodilla")]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA missing")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/Sapodilla" in u for u in urls), "RFCA missing")
        self.assertEqual(len(urls), len(set(urls)), "sapodilla further reading not deduped")

    # --- sapodilla-specific correctness anchors -------------------------------

    def test_pollination_nuance_not_oversimplified(self):
        """The core must carry the cited self-incompatibility nuance, not a flat
        'sapodilla is self-fertile' (which the generic fruit_species.json blurb implies
        but UF/IFAS contradicts)."""
        core_text = " ".join(s["body"] for s in SAPODILLA_JSON["core"]["sections"])
        self.assertIn("self-incompatible", core_text,
                      "core should explain that some cultivars are self-incompatible")
        self.assertIn("cross-pollinate", core_text,
                      "core should explain cross-pollination lifts fruit set")
        # Must not regress to the generic blurb's flat "Sapodilla is self-fertile" claim.
        # (The guide's own "is not simply self-fertile" wording is the corrective, and is fine.)
        self.assertNotIn("is self-fertile", core_text,
                         "do not claim sapodilla is plainly self-fertile (UF/IFAS disagrees)")

    def test_queensland_fruit_fly_host_flagged(self):
        """Sapodilla IS a QFF host (Business Qld / Plant Health Australia); the QLD page
        must say so rather than treat it as a resistant, latex-skinned fruit."""
        qld = SAPODILLA_PAGES["QLD"]
        self.assertIn("Queensland fruit fly", qld)
        self.assertIn("host", qld.lower())

    def test_named_stocked_cultivars_present(self):
        """Variety advice is tied to cultivars actually grafted and sold in Australia."""
        core_text = " ".join(s["body"] for s in SAPODILLA_JSON["core"]["sections"])
        for cultivar in ("Krasuey", "Sawo Manila", "Ponderosa", "Makok"):
            self.assertIn(cultivar, core_text, f"expected named cultivar {cultivar} in the guide")


if __name__ == "__main__":
    unittest.main()
