"""
Mulberry growing-guide tests (tools/scrapers/growing_guides/mulberry.json).

Mulberry is a genuine pan-Australian crop (subtropical QLD through to cold-climate
VIC), so it gets its OWN climate category rather than inheriting "subtropical" (whose
VIC note wrongly implies it is frost-tender and marginal in the south). Every state
gets a real, distinct overlay. Further reading is RFCA-only (there is no WANATCA
yearbook article on mulberry), so this file does NOT assert a WANATCA link.

In its own file so parallel guide runs never collide on a shared test module;
cross-cutting guards live in tests/test_species_state_pages.py.
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

MULBERRY_SPECIES = {
    "common_name": "Mulberry",
    "latin_name": "Morus nigra",
    "description": "Generic mulberry blurb that should be replaced by the rich guide.",
    "slug": "mulberry",
}


def _mulberry_products(n=7):
    # Named varieties that are actually in live Australian nursery stock: a mix of
    # black types (Black English, Hicks Fancy, Beenleigh Black, Lena, Dwarf Black)
    # and white/Shahtoot types (White Shahtoot, White).
    names = ["Black English", "Hicks Fancy", "Beenleigh Black", "Lena",
             "Dwarf Black", "White Shahtoot", "White"]
    return [
        {"title": f"Mulberry {names[i % len(names)]}",
         "url": f"https://nursery.example/mulberry-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 20.0 + i * 5,
         "available": True, "species": MULBERRY_SPECIES}
        for i in range(n)
    ]


MULBERRY_PAGES = build_state_pages("mulberry", _mulberry_products())
MULBERRY_JSON = load_guide("mulberry")

# Region tokens unique to one state (the leak guard relies on this). Each appears
# only in its own state's overlay (and, for WA/VIC, that state's climate note).
MULBERRY_REGION_TOKENS = {
    "WA": ["Swan Valley", "Gascoyne"],
    "QLD": ["Lockyer Valley", "Atherton Tableland"],
    "NSW": ["Hawkesbury", "Northern Rivers"],
    "VIC": ["Goulburn Valley", "Gippsland"],
}


class MulberryGuideTests(unittest.TestCase):
    """Each state page genuinely unique, dash-free, cited, FAQ-rich; pan-Australian climate."""

    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in MULBERRY_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} mulberry page too small")

    def test_canonical_and_og(self):
        wa = MULBERRY_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-mulberry-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the guide.
        wa = MULBERRY_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Mulberry in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in MULBERRY_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Mulberry in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(MULBERRY_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two mulberry state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in MULBERRY_REGION_TOKENS.items():
            self.assertTrue(any(t in MULBERRY_PAGES[st] for t in tokens),
                            f"{st} mulberry page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in MULBERRY_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, MULBERRY_PAGES[other],
                                     f"{owner} mulberry token '{t}' leaked onto {other} page")

    def test_generic_blurb_replaced(self):
        for st, html in MULBERRY_PAGES.items():
            self.assertNotIn("Generic mulberry blurb", html, f"{st} still shows the blurb")

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in MULBERRY_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on mulberry {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on mulberry {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, MULBERRY_JSON, "mulberry.json")

    # --- FAQ JSON-LD ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(MULBERRY_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(MULBERRY_JSON["core"]["faqs"]) + len(MULBERRY_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    # --- sources ---
    def test_sources_present_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', MULBERRY_PAGES[st], f"{st} missing Sources")
        for s in MULBERRY_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in MULBERRY_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "crfg.org", "daleysfruit.com.au",
            )),
            "expected at least one gov/authority/industry source among the mulberry sources",
        )

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', MULBERRY_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in MULBERRY_JSON["sources"]}
        cited = set()
        for block in [MULBERRY_JSON["core"]] + list(MULBERRY_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "mulberry guide cites an unknown source id")

    # --- internal links ---
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', MULBERRY_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    # --- further reading (RFCA owned archives; no WANATCA article exists for mulberry) ---
    def test_further_reading_present_and_owned_followed(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("mulberry"))
        for st in STATES:
            self.assertIn('id="further-reading"', MULBERRY_PAGES[st], f"{st} missing Further reading")
        fr = self._fr(MULBERRY_PAGES["WA"])
        self.assertIn("rfcarchives.org.au", fr, "mulberry Further reading missing RFCA")
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_count_matches_merged(self):
        merged = gg.get_further_reading("mulberry")
        self.assertGreaterEqual(len(merged), len(MULBERRY_JSON.get("further_reading", [])))
        self.assertEqual(self._fr(MULBERRY_PAGES["WA"]).count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("mulberry").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("mulberry", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    # --- climate: mulberry has its OWN category, not "subtropical" ---
    def test_mulberry_climate_category_is_dedicated(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["mulberry"], "mulberry",
                         "mulberry must not inherit the subtropical climate note")
        for st in STATES:
            note = bssp.get_climate_note("Mulberry", st)
            self.assertIn("mulberr", note.lower(), f"{st} mulberry climate note should mention mulberries")
            self.assertNotIn("Chilling hours may be lower", note,
                             "mulberry should not inherit the stone/pome-fruit chill-hours note")

    def test_vic_note_does_not_call_mulberry_marginal(self):
        # The bug we fixed: the old "subtropical" VIC note implied mulberry needs a
        # "sheltered, north-facing position" and that nurseries will not ship to VIC.
        note = bssp.get_climate_note("Mulberry", "VIC")
        self.assertIn("cold-hardy", note, "VIC note should state mulberry is cold-hardy")
        self.assertNotIn("sheltered, north-facing positions", note)
        self.assertNotIn("do not ship to VIC", note)

    # --- correctness guards specific to mulberry ---
    def test_one_tree_is_enough_no_false_pollinator_claim(self):
        # A grower most needs to know mulberries are self-fertile (one tree crops).
        # Guard against a future edit wrongly telling people they need two trees.
        for st, html in MULBERRY_PAGES.items():
            self.assertIn("One tree is enough", html, f"{st} missing the pollination section")
            self.assertNotIn("must have a pollinator", html, f"{st} wrongly claims a pollinator is needed")
            self.assertNotIn("need a second tree", html, f"{st} wrongly claims a second tree is needed")

    def test_birds_are_flagged_as_the_main_pest(self):
        # Birds (and netting) are THE mulberry challenge; every page must say so.
        for st, html in MULBERRY_PAGES.items():
            self.assertIn("Birds", html, f"{st} page does not mention birds")
            self.assertIn("net", html.lower(), f"{st} page does not mention netting")


if __name__ == "__main__":
    unittest.main()
