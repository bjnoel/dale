"""
Feijoa growing-guide tests (tools/scrapers/growing_guides/feijoa.json).

Feijoa (pineapple guava) gets its OWN climate category rather than inheriting
"subtropical". It is one of the most cold-hardy exotic fruits, NEEDS a modest winter
chill to fruit well, and develops its best flavour in cooler areas, so it crops best in
the cool south (Victoria, the NSW tablelands, cooler WA) and only poorly in the warm,
humid tropics. The generic "subtropical" VIC note (frost-tender, "do not ship to VIC")
is exactly wrong for it. Every state gets a real, distinct overlay. Further reading is
owned-archive only (WANATCA yearbook + ACOTANC, plus the RFCA archive merge), so this
file asserts both a WANATCA and an RFCA link and that all are followed.

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

FEIJOA_SPECIES = {
    "common_name": "Feijoa",
    "latin_name": "Acca sellowiana",
    "description": "Generic feijoa blurb that should be replaced by the rich guide.",
    "slug": "feijoa",
}


def _feijoa_products(n=8):
    # Named varieties that are actually in live Australian nursery stock (Daleys,
    # Ladybird, Ross Creek, Fruitopia): a mix of self-fertile NZ types and others.
    names = ["Apollo", "Unique", "Duffy", "Mammoth", "Nazemetz",
             "Triumph", "White Goose", "Large Oval"]
    return [
        {"title": f"Feijoa {names[i % len(names)]}",
         "url": f"https://nursery.example/feijoa-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 30.0 + i * 5,
         "available": True, "species": FEIJOA_SPECIES}
        for i in range(n)
    ]


FEIJOA_PAGES = build_state_pages("feijoa", _feijoa_products())
FEIJOA_JSON = load_guide("feijoa")

# Region tokens unique to one state (the leak guard relies on this). Each appears
# only in its own state's overlay (and, for the ones that carry them, that state's
# climate note). None may appear on another state's page.
FEIJOA_REGION_TOKENS = {
    "WA": ["Perth Hills", "Great Southern"],
    "QLD": ["Granite Belt", "Darling Downs"],
    "NSW": ["Blue Mountains", "Southern Highlands"],
    "VIC": ["Yarra Valley", "Gippsland"],
}


class FeijoaGuideTests(unittest.TestCase):
    """Each state page genuinely unique, dash-free, cited, FAQ-rich; cool-climate fit."""

    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in FEIJOA_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} feijoa page too small")

    def test_canonical_and_og(self):
        wa = FEIJOA_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-feijoa-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the guide.
        wa = FEIJOA_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Feijoa in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in FEIJOA_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Feijoa in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(FEIJOA_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two feijoa state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in FEIJOA_REGION_TOKENS.items():
            self.assertTrue(any(t in FEIJOA_PAGES[st] for t in tokens),
                            f"{st} feijoa page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in FEIJOA_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, FEIJOA_PAGES[other],
                                     f"{owner} feijoa token '{t}' leaked onto {other} page")

    def test_generic_blurb_replaced(self):
        for st, html in FEIJOA_PAGES.items():
            self.assertNotIn("Generic feijoa blurb", html, f"{st} still shows the blurb")

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in FEIJOA_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on feijoa {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on feijoa {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, FEIJOA_JSON, "feijoa.json")

    # --- FAQ JSON-LD ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(FEIJOA_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(FEIJOA_JSON["core"]["faqs"]) + len(FEIJOA_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    # --- sources ---
    def test_sources_present_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', FEIJOA_PAGES[st], f"{st} missing Sources")
        for s in FEIJOA_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in FEIJOA_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "ask.ifas.ufl.edu", "daleysfruit.com.au",
            )),
            "expected at least one gov/university/industry source among the feijoa sources",
        )

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', FEIJOA_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in FEIJOA_JSON["sources"]}
        cited = set()
        for block in [FEIJOA_JSON["core"]] + list(FEIJOA_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "feijoa guide cites an unknown source id")

    # --- internal links ---
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', FEIJOA_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    # --- further reading (owned WANATCA + RFCA archives; all followed) ---
    def test_further_reading_present_and_owned_followed(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("feijoa"))
        for st in STATES:
            self.assertIn('id="further-reading"', FEIJOA_PAGES[st], f"{st} missing Further reading")
        fr = self._fr(FEIJOA_PAGES["WA"])
        self.assertIn("wanatca.org.au", fr, "feijoa Further reading missing WANATCA")
        self.assertIn("rfcarchives.org.au", fr, "feijoa Further reading missing RFCA merge")
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_count_matches_merged(self):
        merged = gg.get_further_reading("feijoa")
        self.assertGreaterEqual(len(merged), len(FEIJOA_JSON.get("further_reading", [])))
        self.assertEqual(self._fr(FEIJOA_PAGES["WA"]).count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("feijoa").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("feijoa", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    # --- climate: feijoa has its OWN category, not "subtropical" ---
    def test_feijoa_climate_category_is_dedicated(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["feijoa"], "feijoa",
                         "feijoa must not inherit the subtropical climate note")
        for st in STATES:
            note = bssp.get_climate_note("Feijoa", st)
            self.assertIn("feijoa", note.lower(), f"{st} feijoa climate note should mention feijoa")
            self.assertNotIn("Chilling hours may be lower", note,
                             "feijoa should not inherit the stone/pome-fruit chill-hours note")

    def test_vic_note_treats_feijoa_as_cold_hardy_not_marginal(self):
        # The bug we fixed: the old "subtropical" VIC note implied feijoa needs a
        # "sheltered, north-facing position" and that nurseries will not ship to VIC.
        note = bssp.get_climate_note("Feijoa", "VIC")
        self.assertIn("frost-hardy", note, "VIC note should state feijoa is frost-hardy")
        self.assertNotIn("sheltered, north-facing positions", note)
        self.assertNotIn("do not ship to VIC", note)

    # --- correctness guards specific to feijoa ---
    def test_needs_a_cool_winter_message_present(self):
        # A grower most needs to know feijoa is cool-loving and fruits poorly in the
        # warm, humid tropics. Guard against a future edit reverting it to a generic
        # frost-tender subtropical framing.
        for st, html in FEIJOA_PAGES.items():
            self.assertTrue(
                ("cold-tolerant" in html) or ("cool winter" in html) or ("frost-hardy" in html),
                f"{st} page should convey feijoa is cold-hardy / cool-loving",
            )

    def test_self_fertile_pollination_story_present(self):
        # Some feijoas are self-fertile (one tree crops); all bear more with a second
        # cultivar; for a single tree we steer growers to Unique or Apollo.
        for st, html in FEIJOA_PAGES.items():
            self.assertIn("self-fertile", html, f"{st} missing the self-fertile pollination point")
        # Core variety advice (rendered on every combo page) names the easy picks.
        wa = FEIJOA_PAGES["WA"]
        self.assertIn("Unique", wa)
        self.assertIn("Apollo", wa)

    def test_fruit_fly_flagged_as_main_pest(self):
        # Fruit fly (Qfly in the east, medfly in WA) is THE feijoa pest; every page
        # must say so and recommend netting/baiting.
        for st, html in FEIJOA_PAGES.items():
            self.assertIn("fruit fly", html.lower(), f"{st} page does not mention fruit fly")
            self.assertTrue("net" in html.lower() or "bait" in html.lower(),
                            f"{st} page does not recommend netting or baiting")


if __name__ == "__main__":
    unittest.main()
