"""
Pecan growing-guide tests (tools/scrapers/growing_guides/pecan.json).

Pecan (Carya illinoinensis) is a large deciduous NUT tree, not a stone or pome
fruit. Its limiting factor is a long, hot summer (heat units fill the kernels),
NOT winter chill (which it needs only a little of), so it gets its OWN climate
category ("pecan") rather than the generic "temperate / choose low-chill" note,
which is the wrong story for it (the banana/cherry/mulberry precedent).

Flagship NSW (the Gwydir Valley / Moree heartland, Stahmann's Trawalla orchard is
the largest pecan operation in the southern hemisphere), with WA as the standout
overlay (the only combo page that renders from current stock, plus the owned
WANATCA Stoneville variety trial and the quarantine story).

Owned Further reading is BOTH WANATCA (the WA nut-tree association covers pecans
richly) AND the RFCA "Nuts" folder articles, hand-curated: that folder is mixed
genus (macadamia, pili, saba, pecan...) so build_archive_index does NOT auto-map
it to the pecan slug, and archive_links.json has no pecan key (the dragon-fruit /
finger-lime mixed-folder pattern).

Correctness guards below pin the adversarially verified research, in particular
the three corrections to the old fruit_species.json framing:
  1. Australia is currently FREE of pecan scab (a grower advantage), not "scab is
     the main disease here".
  2. No pecan is reliably self-fruitful as a lone tree; the "self-pollinating"
     labels are nursery marketing, so a single tree gives a light, unreliable crop.
  3. WA quarantine is real (WAOL / certify / treat); there is NO blanket exemption.
In its own file so parallel guide runs never collide on a shared test module.
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

PECAN_SPECIES = {
    "common_name": "Pecan",
    "latin_name": "Carya illinoinensis",
    "description": "Generic pecan blurb that should be replaced by the rich guide.",
    "slug": "pecan",
}


def _pecan_products(n=7):
    # Real in-stock pecan cultivars (daleys labels them by pollination type), so
    # the stock table renders alongside the guide on every state page.
    names = ["Cape Fear (A) SP", "Cherokee (A) SP", "Desirable (A) SP", "Mahan (B)",
             "Shoshonii (B) SP", "Tejas (B) SP", "Riverside Seedling"]
    return [
        {
            "title": f"Pecan - {names[i % len(names)]}",
            "url": f"https://nursery.example/pecan-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 39.0 + i * 2,
            "available": True,
            "species": PECAN_SPECIES,
        }
        for i in range(n)
    ]


PECAN_PAGES = build_state_pages("pecan", _pecan_products())
PECAN_JSON = load_guide("pecan")

# Each state's distinctive region tokens. Must appear on that state's page and on
# NO other state's page. Chosen as pure place names that are NOT substrings of
# in-stock cultivar names, common words, site chrome, source NAMES, or the shared
# Further-reading titles. NB: "Moree" and "Carnarvon" appear in WANATCA Further-
# reading titles (rendered on every page), so they CANNOT be region tokens; use
# Trawalla/Kempsey/Lismore (NSW) and Wiluna/Esperance/Stoneville (WA) instead.
PECAN_REGION_TOKENS = {
    "WA": ["Wiluna", "Esperance", "Stoneville"],
    "QLD": ["Mundubbera", "Gatton", "Beaudesert"],
    "NSW": ["Trawalla", "Kempsey", "Lismore"],
    "VIC": ["Sunraysia", "Mildura"],
}


class PecanGuideTests(unittest.TestCase):
    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in PECAN_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} pecan page too small")

    def test_canonical_and_og(self):
        wa = PECAN_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-pecan-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        wa = PECAN_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Pecan in Western Australia"),
                        "stock table must precede the guide (search results above the fold)")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in PECAN_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Pecan in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in PECAN_PAGES.items():
            self.assertNotIn("Generic pecan blurb", html, f"{st} still shows the blurb")

    # --- climate category: pecan is its own category, NOT temperate ---
    def test_pecan_has_its_own_climate_category(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["pecan"], "pecan",
                         "pecan must not inherit the generic temperate (low-chill) note")

    def test_every_state_has_a_pecan_climate_note(self):
        for st in STATES:
            self.assertIn("pecan", bssp.STATE_CLIMATE_NOTES[st],
                          f"{st} has no pecan-specific climate note")

    def test_pecan_climate_note_is_not_the_temperate_low_chill_note(self):
        # The generic temperate note tells growers to "choose low-chill varieties",
        # which is the wrong story for pecan (its limit is summer heat, not chill).
        for st in STATES:
            note = bssp.get_climate_note("Pecan", st)
            self.assertNotEqual(note, bssp.STATE_CLIMATE_NOTES[st]["temperate"],
                                f"{st} pecan note is the generic temperate note")
            self.assertIn("summer", note.lower(), f"{st} pecan note should mention the (hot) summer")
        self.assertIn("quarantine", bssp.get_climate_note("Pecan", "WA").lower(),
                      "WA pecan note should mention quarantine")

    def test_pecan_climate_notes_have_no_dashes(self):
        for st in STATES:
            note = bssp.get_climate_note("Pecan", st)
            self.assertNotIn(EM_DASH, note, f"em dash in {st} pecan climate note")
            self.assertNotIn(EN_DASH, note, f"en dash in {st} pecan climate note")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(PECAN_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two pecan state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in PECAN_REGION_TOKENS.items():
            self.assertTrue(any(t in PECAN_PAGES[st] for t in tokens),
                            f"{st} pecan page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in PECAN_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, PECAN_PAGES[other],
                                     f"{owner} pecan token '{t}' leaked onto {other} page")

    def test_overlay_then_core(self):
        wa = gg.render_combo_guide("pecan", "WA")
        self.assertIn("Where pecans grow in WA", wa)   # overlay
        self.assertIn("Choosing a variety", wa)        # core
        self.assertLess(wa.index("Where pecans grow in WA"), wa.index("Choosing a variety"))

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in PECAN_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} pecan page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} pecan page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, PECAN_JSON, "pecan.json")

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', PECAN_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', PECAN_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in PECAN_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in PECAN_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "publications.qld.gov.au",
                "pecangrowers.org.au",
            )),
            "expected at least one agriculture-authority among the pecan sources",
        )

    def test_no_bot_blocked_gov_sources(self):
        # NSW DPI, Agriculture Victoria and APHIS 403/000 to automated fetchers, so
        # they cannot be cited under the URL-200 gate. The NSW heartland claims are
        # anchored on the Australian Pecan Growers, the Gwydir Valley Irrigators and
        # Queensland DAF/Country Life instead.
        joined = json.dumps(PECAN_JSON)
        for blocked in ("dpi.nsw.gov.au", "agriculture.vic.gov.au", "aphis.usda.gov"):
            self.assertNotIn(blocked, joined, f"pecan guide cites a bot-blocked source: {blocked}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in PECAN_JSON["sources"]}
        cited = set()
        for block in [PECAN_JSON["core"]] + list(PECAN_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "pecan guide cites an unknown source id")
        self.assertEqual(src_ids - cited, set(), "pecan guide has a source that is never cited")

    def test_sources_note_does_not_leak_other_species_copy(self):
        self.assertNotIn("olive", PECAN_PAGES["WA"].lower())

    # --- FAQ + links ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(PECAN_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(PECAN_JSON["core"]["faqs"]) + len(PECAN_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', PECAN_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_macadamia_crosslink_present(self):
        # The core FAQ and the QLD overlay point pecan shoppers at the smaller
        # backyard nut, macadamia, which is a real slug.
        self.assertIn("/species/macadamia.html", PECAN_PAGES["QLD"])

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("pecan"))

    # --- owned Further reading: BOTH WANATCA and RFCA, all hand-curated ---
    def test_further_reading_has_wanatca_and_rfca(self):
        fr = gg.get_further_reading("pecan")
        self.assertTrue(fr, "pecan should have curated Further reading")
        self.assertTrue(any("wanatca.org.au" in e["url"] for e in fr),
                        "expected the WANATCA pecan articles in Further reading")
        self.assertTrue(any("rfcarchives.org.au" in e["url"] for e in fr),
                        "expected the owned RFCA pecan articles in Further reading")
        for st in STATES:
            self.assertIn('id="further-reading"', PECAN_PAGES[st], f"{st} missing Further reading")
            self.assertIn("wanatca.org.au", PECAN_PAGES[st], f"{st} missing WANATCA link")

    def test_further_reading_is_owned_and_followed(self):
        # Owned archive links must NOT be nofollow (we endorse our own sites).
        for st in STATES:
            block = re.search(r'id="further-reading".*?</section>', PECAN_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Further reading section")
            for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block.group(0)):
                self.assertNotIn("nofollow", attrs, f"{st} owned Further-reading link is nofollow: {url}")

    def test_no_rfca_auto_merge_for_pecan(self):
        # The RFCA "Nuts" folder is mixed-genus, so build_archive_index does NOT map
        # it to the pecan slug: archive_links.json has no pecan key, and the RFCA
        # links in Further reading are hand-curated, not auto-merged.
        self.assertEqual(gg._archive_links().get("pecan", []), [],
                         "pecan must have no auto-merged RFCA archive entries")

    # --- correctness guards (pin the adversarially verified research) ---
    def test_australia_is_free_of_pecan_scab(self):
        # The headline correction: do NOT repeat the old blurb's "scab is the main
        # disease here". Australia is currently free of it (a grower advantage).
        for st in STATES:
            html = PECAN_PAGES[st]
            self.assertIn("Fusicladium effusum", html, f"{st} missing the scab pathogen name")
            self.assertIn("Australia is currently free of it", html,
                          f"{st} must state Australia is currently free of pecan scab")

    def test_pollination_type_a_and_type_b(self):
        # Dichogamy: a Type A (protandrous) plus a Type B (protogynous) variety.
        for st in STATES:
            html = PECAN_PAGES[st]
            self.assertIn("protandrous", html, f"{st} missing protandrous")
            self.assertIn("protogynous", html, f"{st} missing protogynous")
            self.assertIn("plant a Type A and a Type B", html, f"{st} missing the pairing rule")

    def test_single_tree_is_not_oversold(self):
        # No pecan is reliably self-fruitful; a lone tree gives a light, unreliable
        # crop (the "self-pollinating" labels are nursery marketing, not science).
        for st in STATES:
            self.assertIn("a single tree gives a light, unreliable crop", PECAN_PAGES[st],
                          f"{st} oversells a lone pecan tree")

    def test_does_not_come_true_from_seed(self):
        for st in STATES:
            self.assertIn("do not come true from seed", PECAN_PAGES[st],
                          f"{st} missing the grafted-not-seedling rule")

    def test_zinc_deficiency_named(self):
        for st in STATES:
            html = PECAN_PAGES[st]
            self.assertIn("zinc", html.lower(), f"{st} missing zinc")
            self.assertIn("rosette", html.lower(), f"{st} missing the zinc rosette / little leaf disorder")

    def test_nut_is_not_a_meaningful_fruit_fly_host(self):
        # The hard nut is not a meaningful fruit fly host; WA's fly is Medfly, the
        # east's is Qfly. Do not call the pecan a fruit fly host.
        self.assertIn("Mediterranean fruit fly", PECAN_PAGES["WA"], "WA must name Medfly")
        for st in ("QLD", "NSW"):
            self.assertIn("Queensland fruit fly", PECAN_PAGES[st], f"{st} must name Qfly")
        for st in ("WA", "QLD", "NSW"):
            self.assertIn("not a meaningful", PECAN_PAGES[st],
                          f"{st} should state the nut is not a meaningful fruit fly host")

    def test_nsw_is_the_flagship_heartland(self):
        nsw = PECAN_PAGES["NSW"]
        self.assertIn("largest pecan operation in the southern hemisphere", nsw,
                      "NSW page should carry the Stahmann/Trawalla heartland fact")
        self.assertIn("Gwydir", nsw, "NSW page should name the Gwydir Valley")
        # ...and that heartland claim must not leak onto the other states.
        for other in ("WA", "QLD", "VIC"):
            self.assertNotIn("largest pecan operation in the southern hemisphere", PECAN_PAGES[other],
                             f"{other} wrongly carries the NSW heartland claim")

    def test_long_hot_summer_is_the_theme(self):
        # The defining agronomy: a long hot summer fills the kernels (heat, not chill).
        for st in STATES:
            self.assertIn("long, hot summer", PECAN_PAGES[st], f"{st} missing the long-hot-summer theme")


if __name__ == "__main__":
    unittest.main()
