"""
Pear growing-guide tests (tools/scrapers/growing_guides/pear.json). Pear is a genuine
four-state crop, so every state gets a real, distinct overlay: VIC (the Goulburn Valley,
which grows about 90 per cent of Australia's pears, the canning-pear heritage and the
Tatura Trellis), NSW (the cool Central Tablelands and the birthplace of Packham's Triumph
at Garra near Molong), WA (the Southern Forests, nashi in the Swan Valley, and the rare
distinction of being free of codling moth), and QLD (the high-altitude Granite Belt plus
nashi and low-chill pears for the subtropics). In its own file so parallel guide runs never
collide on a shared module.

Pear-specific correctness guards worth keeping (these are facts a grower must get right):
  * European pears are picked firm and ripened OFF the tree, never left to soften on the
    branch (left in place they go brown and gritty at the core). The opposite of an apple.
  * Nashi (Asian pears) are the exception: tree-ripened and eaten crisp like an apple.
  * Codling moth is ABSENT from WA (kept out by quarantine) but PRESENT in the eastern
    states, exactly as for apple. So the WA page says "free of codling moth" and the
    QLD/NSW/VIC pages must not.
  * The fruit fly differs by state: Mediterranean fruit fly in WA, Queensland fruit fly in
    the east. The WA page must not tell WA growers to manage Queensland fruit fly.
  * Australia is free of fire blight, the serious bacterial disease of pears; never imply it
    is present here.
  * Packham's Triumph was bred at Garra near Molong, NSW, by Charles Henry Packham. That
    story belongs on the NSW page, not the others.
  * Pears are grafted on a vigorous Pyrus rootstock or a dwarfing quince (a pear-specific
    rootstock fact), and most European pears are self-incompatible.
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

PEAR_SPECIES = {
    "common_name": "Pear",
    "latin_name": "Pyrus communis",
    "description": "Generic pear blurb that should be replaced by the rich guide.",
    "slug": "pear",
}


def _pear_products(n=9):
    # Named varieties that are actually in live Australian nursery stock: a mix of mainstream
    # European pears (Williams, Beurre Bosc), the Australian-bred Packham's Triumph, a winter
    # keeper (Josephine), nashi (Nijisseiki, Shinseiki), and low-chill types (Flordahome, Hood).
    # "Nashi Pear ..." titles still match the pear species via the "Nashi Pear" synonym.
    names = ["Pear Williams", "Pear Packham's Triumph", "Pear Beurre Bosc", "Pear Josephine",
             "Pear Corella", "Nashi Pear Nijisseiki", "Nashi Pear Shinseiki", "Pear Flordahome",
             "Pear Hood"]
    return [
        {"title": names[i % len(names)],
         "url": f"https://nursery.example/pear-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 36.0 + i * 4,
         "available": True, "species": PEAR_SPECIES}
        for i in range(n)
    ]


PEAR_PAGES = build_state_pages("pear", _pear_products())
PEAR_JSON = load_guide("pear")

# Region tokens that are unique to one state (the leak guard relies on this). All chosen to be
# unambiguous place names that appear in only one state's overlay (and only in sources cited on
# that state's page). "Orange" is deliberately avoided (it rides on every page inside the
# "Orange Pippin Trees" rootstock source name, and is also a fruit/word); "Perth" is avoided
# (it is in the footer); "Donnybrook" is avoided (there are Donnybrooks in VIC and QLD too).
PEAR_REGION_TOKENS = {
    "WA": ["Manjimup", "Pemberton", "Swan Valley"],
    "QLD": ["Granite Belt", "Stanthorpe", "Ballandean"],
    "NSW": ["Molong", "Garra"],
    "VIC": ["Goulburn Valley", "Shepparton", "Tatura"],
}


class PearGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in PEAR_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} pear page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(PEAR_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two pear state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in PEAR_PAGES.items():
            self.assertNotIn("Generic pear blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in PEAR_REGION_TOKENS.items():
            self.assertTrue(any(t in PEAR_PAGES[st] for t in tokens),
                            f"{st} pear page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in PEAR_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, PEAR_PAGES[other],
                                     f"{owner} pear token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in PEAR_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on pear {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on pear {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, PEAR_JSON, "pear.json")

    # --- correctness guards -------------------------------------------------

    def test_european_pears_ripen_off_the_tree(self):
        # The signature pear fact (core, so it appears on every state page): European pears are
        # picked firm and ripened off the tree, the opposite of how you treat an apple.
        for st in STATES:
            self.assertIn("off the tree", PEAR_PAGES[st],
                          f"{st} pear page must explain ripening off the tree")

    def test_nashi_tree_ripened_contrast(self):
        # Nashi are the exception: tree-ripened and eaten crisp. Mentioned on every page (core).
        for st in STATES:
            self.assertIn("nashi", PEAR_PAGES[st].lower(), f"{st} pear page should name nashi")
        self.assertIn("ripen on the tree", gg.render_species_guide("pear"),
                      "core should state nashi ripen on the tree")

    def test_codling_moth_free_in_wa_only(self):
        self.assertIn("free of codling moth", PEAR_PAGES["WA"],
                      "WA page must state WA is free of codling moth")
        for st in ("QLD", "NSW", "VIC"):
            self.assertNotIn("free of codling moth", PEAR_PAGES[st],
                             f"{st} is NOT free of codling moth; do not claim it is")
            self.assertIn("codling moth", PEAR_PAGES[st],
                          f"{st} page should name codling moth as a present pest")

    def test_fruit_fly_is_state_correct(self):
        # WA = Mediterranean fruit fly (not Queensland fruit fly); the east = Queensland fruit fly.
        self.assertIn("Mediterranean fruit fly", PEAR_PAGES["WA"], "WA page should name Medfly")
        self.assertNotIn("Queensland fruit fly", PEAR_PAGES["WA"],
                         "WA has Medfly, not Queensland fruit fly; do not tell WA growers to manage Qfly")
        for st in ("QLD", "NSW", "VIC"):
            self.assertIn("Queensland fruit fly", PEAR_PAGES[st],
                          f"{st} page should name Queensland fruit fly")

    def test_fire_blight_framed_as_absent(self):
        # Australia is free of fire blight; never imply it is established here. The guide frames
        # it on the WA biosecurity page only and nowhere claims it is present.
        self.assertIn("free of fire blight", PEAR_PAGES["WA"],
                      "WA page should state Australia is free of fire blight")
        for st in ("QLD", "NSW", "VIC"):
            self.assertNotIn("fire blight", PEAR_PAGES[st],
                             f"{st} page should not raise fire blight (absent from Australia)")

    def test_pollination_basics_and_quince_rootstock(self):
        # Pear-specific: most European pears are self-incompatible, and pears are grafted on a
        # vigorous Pyrus rootstock or a dwarfing quince. Both are core, so on every page.
        for st in STATES:
            self.assertIn("self-incompatible", PEAR_PAGES[st], f"{st} page missing pollination basics")
            self.assertIn("quince", PEAR_PAGES[st], f"{st} page missing the quince rootstock")
            self.assertIn("Pyrus", PEAR_PAGES[st], f"{st} page missing the Pyrus rootstock")

    def test_pear_and_cherry_slug_on_every_state(self):
        # The characteristic pear pest, present in every state including WA (unlike codling moth).
        for st in STATES:
            self.assertIn("pear and cherry slug", PEAR_PAGES[st].lower(),
                          f"{st} page should name pear and cherry slug")

    def test_packhams_triumph_is_nsw_only(self):
        # NSW marquee: Packham's Triumph was bred at Garra near Molong by Charles Henry Packham.
        self.assertIn("Charles Henry Packham", PEAR_PAGES["NSW"], "NSW page missing the Packham origin")
        self.assertIn("Molong", PEAR_PAGES["NSW"], "NSW page missing Molong (the Packham birthplace)")
        for st in ("WA", "QLD", "VIC"):
            self.assertNotIn("Charles Henry Packham", PEAR_PAGES[st],
                             f"the Packham origin story belongs on NSW, not {st}")

    def test_marquee_state_facts(self):
        # VIC: about 90 per cent of Australia's pears, the Goulburn Valley, the Tatura Trellis.
        self.assertIn("Goulburn Valley", PEAR_PAGES["VIC"], "VIC page missing the Goulburn Valley")
        self.assertIn("90 per cent", PEAR_PAGES["VIC"], "VIC page missing its production share")
        self.assertIn("Tatura", PEAR_PAGES["VIC"], "VIC page missing the Tatura Trellis")
        # QLD: the Granite Belt is the European-pear district.
        self.assertIn("Stanthorpe", PEAR_PAGES["QLD"], "QLD page missing Stanthorpe/Granite Belt")
        # WA: nashi in the Swan Valley.
        self.assertIn("Swan Valley", PEAR_PAGES["WA"], "WA page missing the Swan Valley nashi note")

    def test_low_chill_varieties_named(self):
        # Warm-district readers (QLD/NSW coast) need the low-chill names.
        for st in ("QLD", "NSW"):
            self.assertIn("Flordahome", PEAR_PAGES[st], f"{st} page should name a low-chill pear (Flordahome)")
            self.assertIn("Hood", PEAR_PAGES[st], f"{st} page should name Hood")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          PEAR_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(PEAR_JSON["core"]["faqs"]) + len(PEAR_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', PEAR_PAGES[st], f"{st} missing Sources")
        for s in PEAR_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in PEAR_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "pomewest.net.au",
                "australianpears.com.au", "extensionaus.com.au",
            )),
            "expected at least one gov/industry authority among the pear sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in PEAR_JSON["sources"]}
        cited = set()
        for block in [PEAR_JSON["core"]] + list(PEAR_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "pear guide cites an unknown source id")

    def test_sources_note_is_pear_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", PEAR_PAGES[st])
            self.assertNotIn("Generic pear blurb", PEAR_PAGES[st])
        self.assertIn("apple and pear industry", PEAR_JSON["sources_note"])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', PEAR_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")
            self.assertIn("apple", linked, f"{st} should cross-link to the pome cousin /species/apple.html")

    def test_further_reading_owned_followed_and_merged(self):
        # Pear has no RFCA folder (it is not a rare fruit), so further reading is the curated
        # WANATCA article only (no auto-merged rfcarchives links). It must still be a followed,
        # owned cross-link, and the rendered count must match the merged list.
        self.assertIn('id="further-reading"', gg.render_species_guide("pear"))
        m = re.search(r'id="further-reading".*?</section>', PEAR_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://wanatca[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("pear")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("pear").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("pear", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
