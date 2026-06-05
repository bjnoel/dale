"""
Black sapote growing-guide tests (tools/scrapers/growing_guides/black-sapote.json). Flagship QLD.
In its own file so parallel guide runs never collide on a shared test module.

Black sapote is a rare tropical persimmon (Diospyros nigra), so the guide carries correctness
anchors worth guarding directly:

* Seedlessness is NOT a flat "self-fertile" story: female-flowered selections set seedless fruit
  only when grown away from a pollinator, and a nearby pollinator lifts yield at the cost of seeds
  (RFCA flowering article; Daleys; City of Darwin).
* Black sapote is NOT a listed Queensland fruit fly host (Plant Health Australia / Fruit Fly ID
  Australia). This is the opposite of sapodilla, so a careless copy-paste of the sapodilla QFF line
  would be wrong; the QLD page must keep the "not a listed host" wording.
* It is a true persimmon (Diospyros) and the unripe fruit is astringent, caustic and an irritant
  (Morton; City of Darwin), so the eating note must carry that warning, not just praise the flavour.
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

BLACK_SAPOTE_SPECIES = {"common_name": "Black Sapote", "latin_name": "Diospyros nigra",
                        "description": "Generic black sapote blurb.", "slug": "black-sapote"}


def _black_sapote_products():
    return [
        {"title": f"Black Sapote {i}", "url": f"https://nursery.example/black-sapote-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 59.0 + i,
         "available": True, "species": BLACK_SAPOTE_SPECIES}
        for i in range(4)
    ]


BLACK_SAPOTE_PAGES = build_state_pages("black-sapote", _black_sapote_products())
BLACK_SAPOTE_JSON = load_guide("black-sapote")

# Region tokens unique to each state overlay (must appear on that state, never leak).
BLACK_SAPOTE_REGION_TOKENS = {
    "WA": ["Kununurra", "Ord River", "Carnarvon"],
    "QLD": ["Atherton Tableland", "Mareeba", "Innisfail"],
    "NSW": ["Northern Rivers", "Tweed", "Lismore"],
    "VIC": ["Melbourne", "glasshouse"],
}


class BlackSapoteGuideTests(unittest.TestCase):
    """Same guarantees as olive/mango/sapodilla, on a rare tropical persimmon."""

    def test_pages_build_and_replace_blurb(self):
        for st, html in BLACK_SAPOTE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} black sapote page too small")
            self.assertNotIn("Generic black sapote blurb", html, f"{st} still shows the blurb")

    def test_state_pages_mutually_distinct(self):
        bodies = list(BLACK_SAPOTE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two black sapote state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in BLACK_SAPOTE_REGION_TOKENS.items():
            self.assertTrue(any(t in BLACK_SAPOTE_PAGES[st] for t in tokens),
                            f"{st} black sapote page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in BLACK_SAPOTE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, BLACK_SAPOTE_PAGES[other],
                                     f"{owner} black sapote token '{t}' leaked onto {other} page")

    def test_stock_table_stays_above_guide(self):
        qld = BLACK_SAPOTE_PAGES["QLD"]
        self.assertLess(qld.index("<table"), qld.index("Growing Black Sapote in Queensland"),
                        "stock table must precede the black sapote guide")

    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in BLACK_SAPOTE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on black sapote {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on black sapote {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, BLACK_SAPOTE_JSON, "black-sapote.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          BLACK_SAPOTE_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} black sapote page missing FAQPage JSON-LD")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(BLACK_SAPOTE_JSON["core"]["faqs"]) + len(BLACK_SAPOTE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} black sapote FAQ count mismatch")

    def test_sources_present_https_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', BLACK_SAPOTE_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} black sapote page missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} black sapote Sources has no links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, url)
                self.assertIn("nofollow", attrs, url)

    def test_guide_sources_https_and_cited_ids_resolve(self):
        for s in BLACK_SAPOTE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in BLACK_SAPOTE_JSON["sources"]}
        cited = set()
        for block in [BLACK_SAPOTE_JSON["core"]] + list(BLACK_SAPOTE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "black sapote guide cites an unknown source id")

    def test_authoritative_domains_present(self):
        domains = " ".join(s["url"] for s in BLACK_SAPOTE_JSON["sources"])
        for d in ("darwin.nt.gov.au", "hort.purdue.edu", "dpird.wa.gov.au",
                  "rfcarchives.org.au", "wanatca.org.au", "fruitflyidentification.org.au"):
            self.assertIn(d, domains, f"expected a {d} source")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', BLACK_SAPOTE_PAGES[st]))
            self.assertIn("black-sapote", linked, f"{st} should link to /species/black-sapote.html")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that 404")

    def test_further_reading_owned_and_followed(self):
        fr = re.search(r'id="further-reading".*?</section>', BLACK_SAPOTE_PAGES["WA"], re.S)
        self.assertIsNotNone(fr, "black sapote WA page missing Further reading")
        block = fr.group(0)
        self.assertIn("wanatca.org.au", block)
        self.assertIn("rfcarchives.org.au", block)
        for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block):
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_merges_curated_and_archive(self):
        urls = [e["url"] for e in gg.get_further_reading("black-sapote")]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA missing")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/BlackSapote" in u for u in urls), "RFCA missing")
        self.assertEqual(len(urls), len(set(urls)), "black sapote further reading not deduped")

    # --- black-sapote-specific correctness anchors ----------------------------

    def _core_text(self):
        return " ".join(s["body"] for s in BLACK_SAPOTE_JSON["core"]["sections"])

    def test_seedlessness_pollination_nuance_not_oversimplified(self):
        """Seedlessness depends on pollination: female-flowered selections set seedless fruit only
        when isolated, and a pollinator lifts yield but brings seeds (RFCA flowering article)."""
        core_text = self._core_text()
        self.assertIn("seedless", core_text, "core should explain seedless fruit")
        self.assertIn("pollinator", core_text, "core should explain a pollinator's effect on seediness")
        self.assertIn("female", core_text.lower(),
                      "core should explain female-flowered selections set seedless fruit")
        # Must not regress to a flat "self-fertile" / "self-pollinating means seedless" claim.
        self.assertNotIn("is self-fertile", core_text,
                         "do not flatten black sapote pollination to 'self-fertile'")

    def test_not_a_queensland_fruit_fly_host(self):
        """Unlike sapodilla, black sapote is NOT a listed Queensland fruit fly host (Plant Health
        Australia). The QLD page must keep that wording so a careless edit does not invert it."""
        qld = BLACK_SAPOTE_PAGES["QLD"]
        self.assertIn("Queensland fruit fly", qld)
        self.assertIn("not a listed Queensland fruit fly host", qld,
                      "QLD page must state black sapote is not a listed QFF host")

    def test_persimmon_identity_and_unripe_warning(self):
        """It is a true persimmon (Diospyros) and unripe fruit is astringent: the eating note must
        carry the warning, not just praise the chocolate-pudding flavour."""
        core_text = self._core_text()
        self.assertIn("persimmon", core_text, "core should flag the persimmon relationship")
        self.assertIn("astringent", core_text, "core should warn that unripe fruit is astringent")

    def test_calyx_harvest_test_and_never_tree_ripen(self):
        """The maturity signal is the lifting calyx, and the fruit is picked hard, never tree-ripened."""
        core_text = self._core_text()
        self.assertIn("calyx", core_text, "core should describe the calyx maturity test")
        self.assertIn("picked hard", core_text, "core should say the fruit is picked hard")

    def test_named_stocked_cultivars_present(self):
        """Variety advice is tied to cultivars actually grafted and sold in Australia."""
        core_text = self._core_text()
        for cultivar in ("Maher", "Bernecker", "Mossman", "Superb", "Ricks Late", "Colossal"):
            self.assertIn(cultivar, core_text, f"expected named cultivar {cultivar} in the guide")


if __name__ == "__main__":
    unittest.main()
