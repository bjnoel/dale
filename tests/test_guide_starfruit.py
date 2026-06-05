"""
Starfruit (carambola) growing-guide tests (tools/scrapers/growing_guides/starfruit.json).
Flagship QLD. In its own file so parallel guide runs never collide on a shared test module.

Starfruit carries a few correctness anchors worth guarding directly:
  * Pollination is heterostylous, NOT a flat "self-fertile" nor a flat "needs two trees":
    short-style cultivars (Kembangan, Fwang Tung) set best with a long-style pollinator
    (Arkin, Kary), but a single self-fruitful tree still crops (RFCA fruit-set / UF IFAS).
  * Carambola does NOT ripen (get sweeter) off the tree, so it must be picked ripe (UF IFAS).
  * It IS a fruit-fly host: Queensland fruit fly in the east, Mediterranean fruit fly in WA.
  * The famous eating caution (oxalates / caramboxin and kidney disease) must be present.
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

STARFRUIT_SPECIES = {"common_name": "Starfruit", "latin_name": "Averrhoa carambola",
                     "description": "Generic starfruit blurb.", "slug": "starfruit"}


def _starfruit_products():
    return [
        {"title": f"Starfruit {i}", "url": f"https://nursery.example/starfruit-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 49.0 + i,
         "available": True, "species": STARFRUIT_SPECIES}
        for i in range(4)
    ]


STARFRUIT_PAGES = build_state_pages("starfruit", _starfruit_products())
STARFRUIT_JSON = load_guide("starfruit")

# Region tokens unique to each state overlay (must appear on that state, never leak).
STARFRUIT_REGION_TOKENS = {
    "WA": ["Kununurra", "Ord", "Carnarvon", "Kimberley", "Gascoyne"],
    "QLD": ["Innisfail", "Tully", "Atherton Tableland", "Mareeba"],
    "NSW": ["Northern Rivers", "Tweed", "Lismore", "Coffs Harbour"],
    "VIC": ["Melbourne", "conservatory", "sunroom"],
}


def _core_text():
    return " ".join(s["body"] for s in STARFRUIT_JSON["core"]["sections"])


class StarfruitGuideTests(unittest.TestCase):
    """Same guarantees as olive/sapodilla, on a tropical crop with its own regions and pests."""

    def test_pages_build_and_replace_blurb(self):
        for st, html in STARFRUIT_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} starfruit page too small")
            self.assertNotIn("Generic starfruit blurb", html, f"{st} still shows the blurb")

    def test_state_pages_mutually_distinct(self):
        bodies = list(STARFRUIT_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two starfruit state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in STARFRUIT_REGION_TOKENS.items():
            self.assertTrue(any(t in STARFRUIT_PAGES[st] for t in tokens),
                            f"{st} starfruit page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in STARFRUIT_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, STARFRUIT_PAGES[other],
                                     f"{owner} starfruit token '{t}' leaked onto {other} page")

    def test_stock_table_stays_above_guide(self):
        qld = STARFRUIT_PAGES["QLD"]
        self.assertLess(qld.index("<table"), qld.index("Growing Starfruit in Queensland"),
                        "stock table must precede the starfruit guide")

    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in STARFRUIT_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on starfruit {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on starfruit {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, STARFRUIT_JSON, "starfruit.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          STARFRUIT_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} starfruit page missing FAQPage JSON-LD")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(STARFRUIT_JSON["core"]["faqs"]) + len(STARFRUIT_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} starfruit FAQ count mismatch")

    def test_sources_present_https_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', STARFRUIT_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} starfruit page missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} starfruit Sources has no links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, url)
                self.assertIn("nofollow", attrs, url)

    def test_guide_sources_https_and_cited_ids_resolve(self):
        for s in STARFRUIT_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in STARFRUIT_JSON["sources"]}
        cited = set()
        for block in [STARFRUIT_JSON["core"]] + list(STARFRUIT_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "starfruit guide cites an unknown source id")

    def test_authoritative_domains_present(self):
        domains = " ".join(s["url"] for s in STARFRUIT_JSON["sources"])
        for d in ("rfcarchives.org.au", "ifas.ufl.edu", "nt.gov.au",
                  "business.qld.gov.au", "dpird.wa.gov.au"):
            self.assertIn(d, domains, f"expected a {d} source")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', STARFRUIT_PAGES[st]))
            self.assertIn("starfruit", linked, f"{st} should link to /species/starfruit.html")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that 404")

    def test_further_reading_owned_and_followed(self):
        fr = re.search(r'id="further-reading".*?</section>', STARFRUIT_PAGES["QLD"], re.S)
        self.assertIsNotNone(fr, "starfruit QLD page missing Further reading")
        block = fr.group(0)
        self.assertIn("wanatca.org.au", block)
        self.assertIn("rfcarchives.org.au", block)
        for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block):
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_merges_curated_and_archive(self):
        urls = [e["url"] for e in gg.get_further_reading("starfruit")]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA missing")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/Carambola" in u for u in urls), "RFCA missing")
        self.assertEqual(len(urls), len(set(urls)), "starfruit further reading not deduped")

    # --- starfruit-specific correctness anchors --------------------------------

    def test_pollination_heterostyly_not_oversimplified(self):
        """The core must carry the cited heterostyly nuance: short-style cultivars are
        partly self-incompatible and crop best with a long-style pollinator, while a
        single self-fruitful tree still crops. Not a flat 'self-fertile' or 'needs two'."""
        core = _core_text()
        self.assertIn("heterostylous", core, "core should name the heterostyly mechanism")
        self.assertIn("self-incompatible", core,
                      "core should say short-style cultivars are partly self-incompatible")
        self.assertIn("self-fruitful", core,
                      "core should say a single self-fruitful tree still crops (the nuance)")
        self.assertIn("self-fertile", core, "core should note long-style types are self-fertile")

    def test_does_not_ripen_off_tree(self):
        """Correctness anchor: carambola does not get sweeter after picking, so pick ripe.
        The generic blurb does not say this; growers who pick green get sour fruit."""
        core = _core_text()
        self.assertIn("does not get any sweeter after picking", core,
                      "harvest section must state carambola does not sweeten off the tree")

    def test_named_stocked_cultivars_present(self):
        """Variety advice is tied to cultivars actually grafted and sold in Australia."""
        core = _core_text()
        for cultivar in ("Sweet Gold", "Kembangan", "Thai Knight", "Arkin", "Kary", "Fwang Tung"):
            self.assertIn(cultivar, core, f"expected named cultivar {cultivar} in the guide")

    def test_eating_safety_kidney_caution_present(self):
        """The well-documented eating caution (oxalates / caramboxin, kidney disease) must
        be present and cited, not silently dropped from a comprehensive guide."""
        core = _core_text()
        self.assertIn("caramboxin", core, "eating section should name the caramboxin caution")
        self.assertIn("kidney", core, "eating section should flag the kidney-disease caution")

    def test_queensland_fruit_fly_host_flagged(self):
        """Carambola IS a Queensland fruit fly host (Business Qld); the QLD page must say so."""
        qld = STARFRUIT_PAGES["QLD"]
        self.assertIn("Queensland fruit fly", qld)
        self.assertIn("host", qld.lower())

    def test_wa_quarantine_and_medfly_flagged(self):
        """WA is a special case: Mediterranean fruit fly host plus live-plant quarantine."""
        wa = STARFRUIT_PAGES["WA"]
        self.assertIn("Mediterranean fruit fly", wa)
        self.assertIn("quarantine", wa.lower())


if __name__ == "__main__":
    unittest.main()
