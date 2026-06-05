"""
White sapote growing-guide tests (tools/scrapers/growing_guides/white-sapote.json).

White sapote (Casimiroa edulis) is a highland subtropical, a citrus relative
(Rutaceae) that is unusually cold-hardy for an exotic fruit yet dislikes humid
lowland tropics, so like banana/cherry/feijoa/loquat it gets its OWN climate
category ("white-sapote") rather than the generic "subtropical" note, which
understates the cold-hardiness in the cool south and wrongly implies the humid
SE Queensland coast suits it. In its own file so parallel guide runs never collide.
(The hyphenated slug means the module name uses an underscore; load_guide and the
builders keep the hyphenated "white-sapote".)

Correctness guards below pin the verified research:
  * It is a citrus relative (Rutaceae); that family link is why WA's citrus-family
    import rules restrict sending trees there (NOT the fruit_species.json claim that
    "no quarantine restrictions apply").
  * Pollination is nuanced: one tree sets some fruit, some cultivars are self-fruitful
    (Ortego, Vernon, Suebelle), but several popular ones (Reinekie Commercial, Golden
    Globe, Blumenthal) are functionally female and crop far better with a pollinator.
  * It dislikes humid lowland tropics (the QLD signature), is not prone to Phytophthora,
    and the seeds (not the flesh) are toxic.
  * WA's fly is Mediterranean fruit fly; the eastern states have Queensland fruit fly
    (which stings the fruit while still hard) plus the fruit spotting bug.
  * The 6:6:6 / 8:3:9 feeding figures are cited (CRFG), not invented.
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guide_helpers import (  # noqa: E402
    bssp, gg, EM_DASH, EN_DASH, STATES, VALID_SLUGS, load_guide, build_state_pages, assert_no_dashes,
)

WS_SPECIES = {
    "common_name": "White Sapote",
    "latin_name": "Casimiroa edulis",
    "description": "Generic white sapote blurb that should be replaced by the rich guide.",
    "slug": "white-sapote",
}


def _ws_products(n=8):
    # Real in-stock white sapote cultivars so the table renders alongside the guide.
    names = ["Reinecke Commercial", "Golden Globe", "Lemon Gold", "Suebelle",
             "Mac's Golden", "Pike", "Vista", "Vernon"]
    return [
        {
            "title": f"White Sapote - {names[i % len(names)]} Grafted",
            "url": f"https://nursery.example/white-sapote-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 79.0 + i * 5,
            "available": True,
            "species": WS_SPECIES,
        }
        for i in range(n)
    ]


WS_PAGES = build_state_pages("white-sapote", _ws_products())
WS_JSON = load_guide("white-sapote")

# Each state's distinctive region tokens. Must appear on that state's page and on
# NO other state's page. Pure place names, not substrings of in-stock cultivar names
# or site chrome ("Perth" alone is footer chrome and is also in the WA overlay prose,
# so WA uses other, WA-only tokens).
WS_REGION_TOKENS = {
    "WA": ["Swan Coastal Plain", "Great Southern", "Gascoyne", "Carnarvon"],
    "QLD": ["Nambour", "Rockhampton", "Gympie"],
    "NSW": ["Sydney", "Central Coast", "Northern Rivers", "Lismore"],
    "VIC": ["Melbourne", "Mornington Peninsula", "Gippsland"],
}


class WhiteSapoteGuideTests(unittest.TestCase):
    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in WS_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} white sapote page too small")

    def test_canonical_and_og(self):
        wa = WS_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-white-sapote-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        wa = WS_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing White Sapote in Western Australia"),
                        "stock table must precede the guide (search results above the fold)")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in WS_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing White Sapote in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in WS_PAGES.items():
            self.assertNotIn("Generic white sapote blurb", html, f"{st} still shows the blurb")

    # --- climate category: white-sapote is its own category, NOT subtropical/default ---
    def test_white_sapote_has_its_own_climate_category(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["white sapote"], "white-sapote",
                         "white sapote must not inherit the generic subtropical note")

    def test_every_state_has_a_white_sapote_climate_note(self):
        for st in STATES:
            self.assertIn("white-sapote", bssp.STATE_CLIMATE_NOTES[st],
                          f"{st} has no white-sapote-specific climate note")

    def test_white_sapote_climate_note_is_not_a_generic_note(self):
        for st in STATES:
            note = bssp.get_climate_note("White Sapote", st)
            self.assertNotEqual(note, bssp.STATE_CLIMATE_NOTES[st]["subtropical"],
                                f"{st} white sapote note is the generic subtropical note")
            self.assertNotEqual(note, bssp.STATE_CLIMATE_NOTES[st]["default"],
                                f"{st} white sapote note is the generic default note")

    def test_white_sapote_climate_notes_have_no_dashes(self):
        for st in STATES:
            note = bssp.get_climate_note("White Sapote", st)
            self.assertNotIn(EM_DASH, note, f"em dash in {st} white sapote climate note")
            self.assertNotIn(EN_DASH, note, f"en dash in {st} white sapote climate note")

    def test_wa_climate_note_frames_the_citrus_relative_import_rule(self):
        # The accurate WA story: it is a citrus relative, so WA's citrus-family import
        # rules limit shipping (not the fruit_species.json "no restrictions" claim).
        note = bssp.get_climate_note("White Sapote", "WA").lower()
        self.assertIn("citrus", note)
        self.assertIn("import", note)

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(WS_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two white sapote state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in WS_REGION_TOKENS.items():
            self.assertTrue(any(t in WS_PAGES[st] for t in tokens),
                            f"{st} white sapote page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in WS_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, WS_PAGES[other],
                                     f"{owner} white sapote token '{t}' leaked onto {other} page")

    def test_overlay_then_core(self):
        qld = gg.render_combo_guide("white-sapote", "QLD")
        self.assertIn("Where it grows in Queensland", qld)   # overlay
        self.assertIn("Choosing a variety", qld)             # core
        self.assertLess(qld.index("Where it grows in Queensland"), qld.index("Choosing a variety"))

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in WS_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} white sapote page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} white sapote page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, WS_JSON, "white-sapote.json")

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', WS_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', WS_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in WS_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_owned_archives(self):
        domains = " ".join(s["url"] for s in WS_JSON["sources"])
        self.assertIn("rfcarchives.org.au", domains, "expected the owned RFCA archive among sources")
        self.assertIn("wanatca.org.au", domains, "expected the owned WANATCA archive among sources")

    def test_no_bot_blocked_gov_sources(self):
        # NSW DPI and Agriculture Victoria 403 to automated fetchers, so they cannot
        # be cited under the URL-200 gate (citrus/cherry batch finding). Anchor on
        # Business Queensland, DPIRD WA and the owned archives instead.
        joined = json.dumps(WS_JSON)
        for blocked in ("dpi.nsw.gov.au", "agriculture.vic.gov.au"):
            self.assertNotIn(blocked, joined, f"white sapote guide cites a bot-blocked source: {blocked}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in WS_JSON["sources"]}
        cited = set()
        for block in [WS_JSON["core"]] + list(WS_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "white sapote guide cites an unknown source id")

    def test_no_other_species_copy_leaks(self):
        self.assertNotIn("olive", WS_PAGES["WA"].lower())

    # --- FAQ + links ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(WS_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(WS_JSON["core"]["faqs"]) + len(WS_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', WS_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("white-sapote"))

    # --- owned Further reading: WANATCA (Meyer) + RFCA, no third-party followed link ---
    def test_further_reading_has_wanatca_and_rfca(self):
        fr = gg.get_further_reading("white-sapote")
        self.assertTrue(fr, "white sapote should have curated Further reading")
        urls = [e["url"] for e in fr]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "expected the WANATCA Meyer link")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/WhiteSapote" in u for u in urls),
                        "expected an RFCA white sapote link")
        for st in STATES:
            self.assertIn('id="further-reading"', WS_PAGES[st], f"{st} missing Further reading")

    # --- correctness guards (pin the verified research) ---
    def test_citrus_relative_rutaceae(self):
        sp = gg.render_species_guide("white-sapote")
        self.assertIn("Rutaceae", sp, "core should state white sapote is in the citrus family Rutaceae")
        self.assertIn("citrus family", sp)

    def test_pollination_nuance_not_a_flat_self_fertile_claim(self):
        sp = gg.render_species_guide("white-sapote")
        self.assertIn("functionally female", sp,
                      "core must explain that many cultivars are functionally female (shy pollen)")
        self.assertIn("Reinekie Commercial", sp,
                      "core should name a cultivar that crops better with a pollinator")
        self.assertIn("self-fruitful", sp,
                      "core should still note self-fruitful options for a one-tree backyard")

    def test_cold_hardy_subtropical_but_young_trees_tender(self):
        sp = gg.render_species_guide("white-sapote").lower()
        self.assertIn("cold-hardy", sp, "core should frame white sapote as cold-hardy for a subtropical")
        self.assertIn("frost", sp, "core should mention protecting young trees from frost")

    def test_not_prone_to_phytophthora(self):
        sp = gg.render_species_guide("white-sapote")
        self.assertIn("Phytophthora", sp,
                      "core should note white sapote is not prone to Phytophthora (an advantage)")

    def test_seeds_are_toxic_flesh_is_safe(self):
        sp = gg.render_species_guide("white-sapote").lower()
        self.assertIn("seeds", sp)
        self.assertIn("not edible", sp,
                      "core should warn the seeds (not the flesh) are not edible")

    def test_feeding_ratio_is_the_cited_figure(self):
        # 6:6:6 / 8:3:9 come from the CRFG fruit facts, so the ratio is allowed (cited),
        # unlike species where no rate is published. Confirm the cited figure renders.
        sp = gg.render_species_guide("white-sapote")
        self.assertIn("6:6:6", sp, "core feeding section should carry the cited fertiliser ratio")

    def test_buy_grafted_not_seedling(self):
        sp = gg.render_species_guide("white-sapote").lower()
        self.assertIn("grafted", sp)
        self.assertIn("seedling", sp)

    def test_qld_dislikes_humid_tropics(self):
        qld = WS_PAGES["QLD"]
        self.assertIn("humid", qld, "QLD page must carry the dislikes-humidity signature")
        self.assertIn("fruits poorly", qld,
                      "QLD page should say the tree fruits poorly on the wet tropical coast")

    def test_wa_citrus_family_import_restriction_and_medfly(self):
        wa = WS_PAGES["WA"]
        self.assertIn("importing citrus and its relatives", wa,
                      "WA page must explain the citrus-family import restriction")
        self.assertIn("Mediterranean fruit fly", wa, "WA page must name Medfly, not Qfly")
        self.assertNotIn("no quarantine restrictions", wa.lower(),
                         "WA page must not repeat the fruit_species.json 'no restrictions' error")

    def test_eastern_states_qfly_and_fruit_spotting_bug(self):
        for st in ("QLD", "NSW"):
            html = WS_PAGES[st]
            self.assertIn("Queensland fruit fly", html, f"{st} should name Qfly")
            self.assertIn("fruit spotting bug", html, f"{st} should name the fruit spotting bug")


if __name__ == "__main__":
    unittest.main()
