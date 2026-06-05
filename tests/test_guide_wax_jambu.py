"""
Wax jambu growing-guide tests (tools/scrapers/growing_guides/wax-jambu.json).
Flagship QLD (the wet-tropics heartland); WA carries the standout "can I even grow
it here?" overlay. In its own file so parallel guide runs never collide on a shared
test module. The slug is hyphenated (wax-jambu) but a Python module name cannot
contain a dash, so this file is test_guide_wax_jambu.py (underscore).

Wax jambu (Syzygium samarangense) is a rare tropical Myrtaceae crop sold under a
tangle of overlapping names, so the guide carries correctness anchors worth guarding
directly: it is self-compatible (one tree fruits, contra a flat "needs two trees");
it is non-climacteric (must ripen on the tree); it keeps the four Syzygium lookalikes
distinct (samarangense vs aqueum vs jambos vs malaccense); the fruit fly differs by
state (Queensland fruit fly host in the east, Mediterranean fruit fly in WA); WA is
essentially free of myrtle rust; and it is frost-tender (killed near 0 degrees).
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

WAX_JAMBU_SPECIES = {"common_name": "Wax Jambu", "latin_name": "Syzygium samarangense",
                     "description": "Generic wax jambu blurb.", "slug": "wax-jambu"}


def _wax_jambu_products():
    return [
        {"title": f"Wax Jambu {i}", "url": f"https://nursery.example/wax-jambu-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 24.0 + i,
         "available": True, "species": WAX_JAMBU_SPECIES}
        for i in range(4)
    ]


WAX_JAMBU_PAGES = build_state_pages("wax-jambu", _wax_jambu_products())
WAX_JAMBU_JSON = load_guide("wax-jambu")
CORE_TEXT = " ".join(s["body"] for s in WAX_JAMBU_JSON["core"]["sections"])

# Region tokens unique to each state overlay (must appear on that state, never leak).
WAX_JAMBU_REGION_TOKENS = {
    "WA": ["Kununurra", "Kimberley", "Carnarvon"],
    "QLD": ["Cairns", "Innisfail", "Atherton Tableland"],
    "NSW": ["Northern Rivers", "Tweed", "Lismore"],
    "VIC": ["Melbourne", "glasshouse", "Mildura"],
}


class WaxJambuGuideTests(unittest.TestCase):
    """Same guarantees as olive/sapodilla, on a rare tropical crop with its own
    regions, pests and naming traps."""

    def test_pages_build_and_replace_blurb(self):
        for st, html in WAX_JAMBU_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} wax jambu page too small")
            self.assertNotIn("Generic wax jambu blurb", html, f"{st} still shows the blurb")

    def test_state_pages_mutually_distinct(self):
        bodies = list(WAX_JAMBU_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two wax jambu state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in WAX_JAMBU_REGION_TOKENS.items():
            self.assertTrue(any(t in WAX_JAMBU_PAGES[st] for t in tokens),
                            f"{st} wax jambu page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in WAX_JAMBU_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, WAX_JAMBU_PAGES[other],
                                     f"{owner} wax jambu token '{t}' leaked onto {other} page")

    def test_stock_table_stays_above_guide(self):
        qld = WAX_JAMBU_PAGES["QLD"]
        self.assertLess(qld.index("<table"), qld.index("Growing Wax Jambu in Queensland"),
                        "stock table must precede the wax jambu guide")

    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in WAX_JAMBU_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on wax jambu {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on wax jambu {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, WAX_JAMBU_JSON, "wax-jambu.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          WAX_JAMBU_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} wax jambu page missing FAQPage JSON-LD")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(WAX_JAMBU_JSON["core"]["faqs"]) + len(WAX_JAMBU_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} wax jambu FAQ count mismatch")

    def test_sources_present_https_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', WAX_JAMBU_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} wax jambu page missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} wax jambu Sources has no links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, url)
                self.assertIn("nofollow", attrs, url)

    def test_guide_sources_https_and_cited_ids_resolve(self):
        for s in WAX_JAMBU_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in WAX_JAMBU_JSON["sources"]}
        cited = set()
        for block in [WAX_JAMBU_JSON["core"]] + list(WAX_JAMBU_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "wax jambu guide cites an unknown source id")

    def test_authoritative_domains_present(self):
        domains = " ".join(s["url"] for s in WAX_JAMBU_JSON["sources"])
        for d in ("business.qld.gov.au", "dpird.wa.gov.au", "nt.gov.au",
                  "wanatca.org.au", "rfcarchives.org.au", "hort.purdue.edu"):
            self.assertIn(d, domains, f"expected a {d} source")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', WAX_JAMBU_PAGES[st]))
            self.assertIn("wax-jambu", linked, f"{st} should link to /species/wax-jambu.html")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that 404")

    def test_further_reading_owned_and_followed(self):
        fr = re.search(r'id="further-reading".*?</section>', WAX_JAMBU_PAGES["WA"], re.S)
        self.assertIsNotNone(fr, "wax jambu WA page missing Further reading")
        block = fr.group(0)
        self.assertIn("wanatca.org.au", block)
        self.assertIn("rfcarchives.org.au", block)
        for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block):
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_merges_curated_and_archive(self):
        urls = [e["url"] for e in gg.get_further_reading("wax-jambu")]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA missing")
        # No dedicated RFCA WaxJambu folder exists (the Syzygium content lives in the
        # mixed-genus MyrtaceaeFamily folder, which build_archive_index does not
        # auto-map to a slug), so the RFCA links are hand-curated, not auto-merged.
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/MyrtaceaeFamily" in u for u in urls),
                        "curated RFCA MyrtaceaeFamily link missing")
        self.assertEqual(len(urls), len(set(urls)), "wax jambu further reading not deduped")

    # --- wax-jambu-specific correctness anchors -------------------------------

    def test_self_compatible_one_tree(self):
        """Wax jambu is self-compatible; a single tree fruits (PROSEA/RFCWA). The
        guide must say so rather than imply a pollinator partner is required."""
        self.assertIn("self-compatible", CORE_TEXT,
                      "core should state wax jambu is self-compatible")
        self.assertIn("one wax jambu", CORE_TEXT,
                      "core should make clear one tree is enough")
        self.assertNotIn("must have a pollinator", CORE_TEXT)

    def test_non_climacteric_ripens_on_tree(self):
        """Non-climacteric: it will not ripen further once picked (RFCWA/Growables)."""
        self.assertIn("non-climacteric", CORE_TEXT)
        self.assertIn("ripen", CORE_TEXT.lower())

    def test_syzygium_lookalikes_kept_distinct(self):
        """The naming trap: wax jambu (S. samarangense) must be kept distinct from
        water apple (S. aqueum), rose apple (S. jambos) and Malay apple
        (S. malaccense), which are sold under overlapping names."""
        for binomial in ("Syzygium samarangense", "Syzygium aqueum",
                         "Syzygium jambos", "Syzygium malaccense"):
            self.assertIn(binomial, CORE_TEXT, f"core should name {binomial}")

    def test_queensland_fruit_fly_host_in_qld(self):
        """Wax jambu IS a listed Queensland fruit fly host (Business Qld); the QLD
        page must flag it, not treat the fruit as resistant."""
        qld = WAX_JAMBU_PAGES["QLD"]
        self.assertIn("Queensland fruit fly", qld)
        self.assertIn("host", qld.lower())

    def test_wa_medfly_not_qfly_and_myrtle_rust_free(self):
        """WA's fruit fly is the Mediterranean fruit fly, and WA is essentially
        free of myrtle rust (a genuine WA advantage). The eastern states have it."""
        wa = WAX_JAMBU_PAGES["WA"]
        self.assertIn("Mediterranean fruit fly", wa)
        self.assertIn("myrtle rust", wa.lower())
        self.assertIn("essentially free", wa)
        # QLD should carry the myrtle-rust risk it actually faces.
        self.assertIn("myrtle rust", WAX_JAMBU_PAGES["QLD"].lower())

    def test_frost_tender_threshold_stated(self):
        """Frost-tender: killed around 0 degrees (Useful Tropical Plants). The VIC
        overlay (where cold is the limiting factor) must make the threshold concrete."""
        vic = WAX_JAMBU_PAGES["VIC"]
        self.assertIn("0 degrees", vic)
        self.assertNotIn("frost hardy", vic.lower())

    def test_named_and_colour_cultivars_present(self):
        """Variety advice is tied to the colour forms and named selections actually
        sold (pink/red/green wax jambu, and named Thai/Taiwan selections)."""
        for colour in ("pink", "red", "green"):
            self.assertIn(colour, CORE_TEXT.lower(), f"expected colour form '{colour}'")
        self.assertTrue(
            "Thabthim Chan" in CORE_TEXT or "Black Pearl" in CORE_TEXT,
            "expected a named Thai/Taiwan selection (Thabthim Chan / Black Pearl)",
        )


if __name__ == "__main__":
    unittest.main()
