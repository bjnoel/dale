"""
Banana growing-guide tests (tools/scrapers/growing_guides/banana.json).

In its own file so parallel guide runs never collide on a shared test module;
cross-cutting guards (climate mapping, fallback, archive index, the gg module API,
FAQ overlap) live in tests/test_species_state_pages.py.

Banana is the first guide to get its own SPECIES_CLIMATE_CATEGORY ("banana"): the
generic "tropical" WA note understated the reality (live banana planting material
cannot simply be brought into WA), so banana carries an accurate per-state note set.
These tests guard that, plus the correctness facts that matter most for a banana
grower: parthenocarpy (no pollinator/second plant needed), the variety-by-Panama-race
advice, and the bunchy-top / quarantine biosecurity story.
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guide_helpers import (  # noqa: E402
    bssp, gg, EM_DASH, EN_DASH, STATES, TODAY, VALID_SLUGS, load_guide, build_state_pages, assert_no_dashes,
)

BANANA_SPECIES = {
    "common_name": "Banana",
    "latin_name": "Musa spp.",
    "description": "Generic banana blurb that should be replaced by the rich guide.",
    "slug": "banana",
}


def _banana_products(n=6):
    # Variety names drawn from the live treestock stock table.
    names = ["Williams Cavendish", "Dwarf Cavendish", "Lady Finger", "Ducasse",
             "Goldfinger", "Blue Java", "Red Dacca", "Pisang Ceylon"]
    return [
        {
            "title": f"Banana {names[i % len(names)]}",
            "url": f"https://nursery.example/banana-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 24.0 + i * 4,
            "available": True,
            "species": BANANA_SPECIES,
        }
        for i in range(n)
    ]


BANANA_PAGES = build_state_pages("banana", _banana_products())
BANANA_JSON = load_guide("banana")

# State-specific region tokens that must appear on exactly one state's page.
# Chosen to avoid substring collisions (e.g. "Ord" would match "border") and the
# shared chrome (only "Perth" lives there, so it is never used as a token).
BANANA_REGION_TOKENS = {
    "WA": ["Carnarvon", "Gascoyne"],
    "QLD": ["Tully", "Atherton"],
    "NSW": ["Coffs Harbour", "Murwillumbah"],
    "VIC": ["Melbourne", "Gippsland"],
}


class BananaGuideTests(unittest.TestCase):
    """Each state page genuinely unique, dash-free, cited, FAQ-rich, and correct."""

    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in BANANA_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} page too small")

    def test_canonical_and_og(self):
        wa = BANANA_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-banana-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the guide.
        wa = BANANA_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Banana in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in BANANA_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Banana in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(BANANA_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in BANANA_REGION_TOKENS.items():
            self.assertTrue(any(t in BANANA_PAGES[st] for t in tokens),
                            f"{st} page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in BANANA_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, BANANA_PAGES[other],
                                     f"{owner} token '{t}' leaked onto {other} page")

    def test_state_full_name_in_guide(self):
        for st in STATES:
            self.assertIn(bssp.STATE_FULL_NAMES[st], BANANA_PAGES[st])

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in BANANA_PAGES.items():
            self.assertNotIn("Generic banana blurb", html, f"{st} still shows the blurb")

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in BANANA_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} page (guards the price-range bug)")

    def test_price_range_uses_hyphen_not_en_dash(self):
        wa = BANANA_PAGES["WA"]
        self.assertRegex(wa, r"\$\d+-\$\d+", "expected a hyphenated price range")
        self.assertNotIn(EN_DASH, wa)

    def test_product_titles_with_dashes_are_sanitised(self):
        prods = _banana_products(1)
        prods[0]["title"] = "Banana – Williams Cavendish — Tissue Culture"
        prods[0]["nursery_name"] = "Some – Nursery"
        html = bssp.build_combo_page("QLD", "banana", prods, TODAY)
        self.assertIn("Banana - Williams Cavendish - Tissue Culture", html)
        self.assertNotIn(EM_DASH, html)
        self.assertNotIn(EN_DASH, html)

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, BANANA_JSON, "banana.json")

    # --- climate (banana gets its own category, not generic tropical) ---
    def test_banana_has_its_own_climate_category(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["banana"], "banana")

    def test_wa_climate_note_states_the_import_reality(self):
        note = bssp.get_climate_note("Banana", "WA")
        self.assertIn("interstate", note,
                      "WA banana note should explain plants cannot simply be brought in interstate")
        self.assertNotIn("only a handful of eastern states nurseries", note,
                          "banana is still getting the generic tropical WA note")

    def test_every_state_has_a_banana_climate_note_without_dashes(self):
        for st in STATES:
            note = bssp.STATE_CLIMATE_NOTES[st]["banana"]
            self.assertTrue(note)
            self.assertNotIn(EM_DASH, note)
            self.assertNotIn(EN_DASH, note)

    # --- correctness facts that matter to a grower ---
    def test_parthenocarpy_is_explained(self):
        # The headline net-new angle: one plant fruits on its own, no pollinator.
        for st, html in BANANA_PAGES.items():
            self.assertIn("without pollination", html, f"{st} missing the no-pollination fact")

    def test_variety_by_panama_race_advice_present(self):
        # The single most decision-relevant fact: Cavendish vs race 4, Lady Finger vs race 1.
        wa = BANANA_PAGES["WA"]
        self.assertIn("tropical race 4", wa)
        self.assertIn("Lady Finger", wa)
        self.assertIn("Cavendish", wa)

    def test_wa_page_leads_with_quarantine_and_carnarvon(self):
        wa = BANANA_PAGES["WA"]
        self.assertIn("Carnarvon", wa)
        self.assertIn("quarantine", wa)

    def test_bunchy_top_is_the_nsw_headline(self):
        self.assertIn("bunchy top", BANANA_PAGES["NSW"])

    # --- FAQ JSON-LD ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(BANANA_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(BANANA_JSON["core"]["faqs"]) + len(BANANA_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', BANANA_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', BANANA_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in BANANA_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in BANANA_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "abgc.org.au",
                "ogtr.gov.au", "outbreak.gov.au", "era.dpi.qld.gov.au",
            )),
            "expected at least one gov/industry authority among the sources",
        )

    def test_sources_note_is_banana_specific(self):
        # Sources note can be overridden per guide; banana names the ABGC.
        self.assertIn("Australian Banana Growers' Council", BANANA_PAGES["WA"])

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in BANANA_JSON["sources"]}
        cited = set()
        for block in [BANANA_JSON["core"]] + list(BANANA_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "guide cites an unknown source id")

    # --- internal links ---
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', BANANA_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    # --- further reading (owned WANATCA + RFCA archives) ---
    def test_further_reading_present_on_state_and_species_guide(self):
        for st in STATES:
            self.assertIn('id="further-reading"', BANANA_PAGES[st], f"{st} missing Further reading")
        self.assertIn('id="further-reading"', gg.render_species_guide("banana"))

    def test_further_reading_links_point_to_owned_archives(self):
        fr = self._fr(BANANA_PAGES["WA"])
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)

    def test_further_reading_links_are_followed_not_nofollow(self):
        fr = self._fr(BANANA_PAGES["WA"])
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_rfca_banana_archive_merged_into_further_reading(self):
        urls = [e["url"] for e in gg.get_further_reading("banana")]
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/Banana" in u for u in urls),
                        "RFCA banana archive links should merge into further reading")
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA link missing")
        self.assertEqual(len(urls), len(set(urls)), "further reading not deduped")


if __name__ == "__main__":
    unittest.main()
