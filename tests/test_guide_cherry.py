"""
Cherry growing-guide tests (tools/scrapers/growing_guides/cherry.json).

Cherry is the highest-chill of the common stone fruits (most sweet cherries want
~800 to 1200 hours), so unlike peach/apple it gets its OWN climate category
("cherry") instead of the generic "temperate / choose low-chill" note, which is
wrong for it. Like apple it is a mainstream fruit (no RFCA folder), so its only
owned Further reading is the WANATCA Yearbook "The True Cherries" article and
there is NO rfcarchives.org.au auto-merge. In its own file so parallel guide runs
never collide. Correctness guards below pin the research findings (low-chill Royal
series bred in California not UC-Davis; Minnie Royal and Royal Lee must cross-
pollinate; WA's fly is Medfly not Qfly; prune in summer; non-climacteric harvest).
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

CHERRY_SPECIES = {
    "common_name": "Cherry",
    "latin_name": "Prunus avium",
    "description": "Generic cherry blurb that should be replaced by the rich guide.",
    "slug": "cherry",
}


def _cherry_products(n=8):
    # Real-ish in-stock cherry cultivars so the table renders alongside the guide.
    names = ["Stella", "Lapins", "Sunburst", "Minnie Royal", "Royal Lee",
             "Royal Crimson", "Starkrimson", "Morello"]
    return [
        {
            "title": f"Cherry {names[i % len(names)]}",
            "url": f"https://nursery.example/cherry-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 35.0 + i * 5,
            "available": True,
            "species": CHERRY_SPECIES,
        }
        for i in range(n)
    ]


CHERRY_PAGES = build_state_pages("cherry", _cherry_products())
CHERRY_JSON = load_guide("cherry")

# Each state's distinctive region tokens. Must appear on that state's page and on
# NO other state's page (peach/apple precedent). Chosen to be pure place names that
# are not substrings of in-stock cultivar names, common words, or site chrome.
CHERRY_REGION_TOKENS = {
    "WA": ["Manjimup", "Pickering Brook"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Young", "Batlow"],
    "VIC": ["Yarra Valley", "Beechworth"],
}


class CherryGuideTests(unittest.TestCase):
    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in CHERRY_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} cherry page too small")

    def test_canonical_and_og(self):
        wa = CHERRY_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-cherry-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        wa = CHERRY_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Cherry in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in CHERRY_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Cherry in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in CHERRY_PAGES.items():
            self.assertNotIn("Generic cherry blurb", html, f"{st} still shows the blurb")

    # --- climate category: cherry is its own category, NOT temperate ---
    def test_cherry_has_its_own_climate_category(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["cherry"], "cherry",
                         "cherry must not inherit the generic temperate note")

    def test_every_state_has_a_cherry_climate_note(self):
        for st in STATES:
            self.assertIn("cherry", bssp.STATE_CLIMATE_NOTES[st],
                          f"{st} has no cherry-specific climate note")

    def test_cherry_climate_note_is_not_the_temperate_low_chill_note(self):
        # The generic temperate note tells growers to "choose low-chill varieties",
        # which is wrong for cherries; the cherry note must tell the cold-climate story.
        for st in STATES:
            note = bssp.get_climate_note("Cherry", st)
            self.assertNotEqual(note, bssp.STATE_CLIMATE_NOTES[st]["temperate"],
                                f"{st} cherry note is the generic temperate note")
            self.assertIn("chill", note.lower(), f"{st} cherry note should mention chill")
        self.assertIn("quarantine", bssp.get_climate_note("Cherry", "WA").lower(),
                      "WA cherry note should mention quarantine")

    def test_cherry_climate_notes_have_no_dashes(self):
        for st in STATES:
            note = bssp.get_climate_note("Cherry", st)
            self.assertNotIn(EM_DASH, note, f"em dash in {st} cherry climate note")
            self.assertNotIn(EN_DASH, note, f"en dash in {st} cherry climate note")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(CHERRY_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two cherry state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in CHERRY_REGION_TOKENS.items():
            self.assertTrue(any(t in CHERRY_PAGES[st] for t in tokens),
                            f"{st} cherry page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in CHERRY_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, CHERRY_PAGES[other],
                                     f"{owner} cherry token '{t}' leaked onto {other} page")

    def test_overlay_then_core(self):
        wa = gg.render_combo_guide("cherry", "WA")
        self.assertIn("Where cherries grow in WA", wa)   # overlay
        self.assertIn("Choosing a variety", wa)          # core
        self.assertLess(wa.index("Where cherries grow in WA"), wa.index("Choosing a variety"))

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in CHERRY_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} cherry page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} cherry page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, CHERRY_JSON, "cherry.json")

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', CHERRY_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', CHERRY_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in CHERRY_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in CHERRY_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "cherrygrowers.org.au", "treefruit.wsu.edu",
            )),
            "expected at least one agriculture-authority among the cherry sources",
        )

    def test_no_bot_blocked_gov_sources(self):
        # NSW DPI and Agriculture Victoria 403 to automated fetchers, so they cannot
        # be cited under the URL-200 gate (same finding as the citrus batch). Anchor
        # eastern claims on Cherry Growers Australia, Business Queensland, WSU/OSU instead.
        joined = json.dumps(CHERRY_JSON)
        for blocked in ("dpi.nsw.gov.au", "agriculture.vic.gov.au"):
            self.assertNotIn(blocked, joined, f"cherry guide cites a bot-blocked source: {blocked}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in CHERRY_JSON["sources"]}
        cited = set()
        for block in [CHERRY_JSON["core"]] + list(CHERRY_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "cherry guide cites an unknown source id")

    def test_sources_note_does_not_leak_other_species_copy(self):
        self.assertNotIn("olive", CHERRY_PAGES["WA"].lower())

    # --- FAQ + links ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(CHERRY_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(CHERRY_JSON["core"]["faqs"]) + len(CHERRY_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', CHERRY_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("cherry"))

    # --- owned Further reading: WANATCA only, no RFCA (mainstream fruit, no RFCA folder) ---
    def test_wanatca_further_reading_present(self):
        fr = gg.get_further_reading("cherry")
        self.assertTrue(fr, "cherry should have curated Further reading")
        self.assertTrue(any("wanatca.org.au" in e["url"] for e in fr),
                        "expected the WANATCA cherry article in Further reading")
        for st in STATES:
            self.assertIn('id="further-reading"', CHERRY_PAGES[st], f"{st} missing Further reading")
            self.assertIn("wanatca.org.au", CHERRY_PAGES[st], f"{st} missing WANATCA link")

    def test_no_rfca_auto_merge_for_cherry(self):
        # Cherry is not a rare fruit, so there is no RFCA Cherry folder and the
        # archive index has no cherry key; Further reading must stay WANATCA-only.
        self.assertEqual(gg._archive_links().get("cherry", []), [])
        for st in STATES:
            self.assertNotIn("rfcarchives.org.au", CHERRY_PAGES[st],
                             f"{st} unexpectedly has an RFCA archive link")

    # --- correctness guards (pin the verified research) ---
    def test_low_chill_royal_series_correctness(self):
        # The Royal series is Californian (Zaiger), NOT UC-Davis, and Minnie Royal
        # and Royal Lee must cross-pollinate each other.
        for st in STATES:
            html = CHERRY_PAGES[st]
            self.assertIn("bred in California", html, f"{st} missing the California origin")
            self.assertNotIn("UC Davis", html, f"{st} wrongly attributes the Royal series to UC Davis")
            self.assertNotIn("UC-Davis", html, f"{st} wrongly attributes the Royal series to UC-Davis")
            self.assertIn("Minnie Royal and Royal Lee must be grown together", html,
                          f"{st} missing the low-chill cross-pollination rule")

    def test_summer_pruning_not_winter(self):
        for st in STATES:
            self.assertIn("prune in summer", CHERRY_PAGES[st], f"{st} missing the summer-pruning rule")

    def test_harvest_is_non_climacteric(self):
        for st in STATES:
            self.assertIn("non-climacteric", CHERRY_PAGES[st], f"{st} missing the non-climacteric harvest fact")

    def test_wa_fly_is_medfly_not_qfly(self):
        wa = CHERRY_PAGES["WA"]
        self.assertIn("Mediterranean fruit fly", wa, "WA page must name Medfly")
        self.assertIn("no established Queensland fruit fly", wa,
                      "WA page must state WA has no established Qfly (declared/eradicated)")

    def test_eastern_states_name_qfly_as_a_cherry_pest(self):
        for st in ("QLD", "NSW", "VIC"):
            self.assertIn("Queensland fruit fly", CHERRY_PAGES[st], f"{st} should name Qfly")


if __name__ == "__main__":
    unittest.main()
