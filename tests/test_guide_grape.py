"""
Grape growing-guide tests (tools/scrapers/growing_guides/grape.json).

In its own file so parallel guide runs never collide on a shared test module;
cross-cutting guards (climate mapping, fallback, archive index, the gg module API,
the FAQ-overlap guard) live in tests/test_species_state_pages.py.

Grape is the second "mediterranean" climate-category guide after olive: it must NOT
inherit the stone/pome-fruit chill-hours note. The distinctive per-state story is
phylloxera (WA free, QLD a phylloxera exclusion zone, VIC and NSW with infested zones),
which the correctness guards below pin down so the states never blur together.
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

GRAPE_SPECIES = {
    "common_name": "Grape",
    "latin_name": "Vitis vinifera",
    "description": "Generic grape blurb that should be replaced by the rich guide.",
    "slug": "grape",
}


def _grape_products(n=6):
    # Real-stock-style cultivar names (these render in the product table on every
    # state page, so none of them may double as a region leak token).
    titles = ["Crimson Seedless", "Flame Seedless", "Thompson Seedless", "Red Globe",
              "Autumn Royal", "Black Muscat"]
    return [
        {
            "title": f"Grape - {titles[i % len(titles)]}",
            "url": f"https://nursery.example/grape-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 25.0 + i * 4,
            "available": True,
            "species": GRAPE_SPECIES,
        }
        for i in range(n)
    ]


GRAPE_PAGES = build_state_pages("grape", _grape_products())
GRAPE_JSON = load_guide("grape")

# State-specific region tokens that must appear on exactly one state's page. These
# are deliberately NOT grape cultivar names (Menindee, Waltham Cross, Carolina etc.
# are cultivars that render in the stock table on every page, so they would leak).
GRAPE_REGION_TOKENS = {
    "WA": ["Swan Valley", "Carnarvon"],
    "QLD": ["Granite Belt", "St George"],
    "NSW": ["Hunter Valley", "Riverina", "Griffith"],
    "VIC": ["Sunraysia", "Rutherglen", "King Valley"],
}


class GrapeGuideTests(unittest.TestCase):
    """The grape guide: each state page genuinely unique, dash-free, cited, FAQ-rich."""

    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in GRAPE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} page too small")

    def test_canonical_and_og(self):
        wa = GRAPE_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-grape-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the guide.
        wa = GRAPE_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Grape in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in GRAPE_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Grape in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(GRAPE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in GRAPE_REGION_TOKENS.items():
            self.assertTrue(any(t in GRAPE_PAGES[st] for t in tokens),
                            f"{st} page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in GRAPE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, GRAPE_PAGES[other],
                                     f"{owner} token '{t}' leaked onto {other} page")

    def test_state_full_name_in_guide(self):
        for st in STATES:
            self.assertIn(bssp.STATE_FULL_NAMES[st], GRAPE_PAGES[st])

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in GRAPE_PAGES.items():
            self.assertNotIn("Generic grape blurb", html, f"{st} still shows the blurb")

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in GRAPE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} page (guards the price-range bug)")

    def test_price_range_uses_hyphen_not_en_dash(self):
        wa = GRAPE_PAGES["WA"]
        self.assertRegex(wa, r"\$\d+-\$\d+", "expected a hyphenated price range")
        self.assertNotIn(EN_DASH, wa)

    def test_product_titles_with_dashes_are_sanitised(self):
        prods = _grape_products(1)
        prods[0]["title"] = "Grape – Crimson Seedless — Grafted"
        prods[0]["nursery_name"] = "Some – Nursery"
        html = bssp.build_combo_page("WA", "grape", prods, TODAY)
        self.assertIn("Grape - Crimson Seedless - Grafted", html)
        self.assertNotIn(EM_DASH, html)
        self.assertNotIn(EN_DASH, html)

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, GRAPE_JSON, "grape.json")

    # --- climate (grape must not inherit the stone-fruit chill note) ---
    def test_grape_climate_note_is_mediterranean_not_chill_text(self):
        note = bssp.get_climate_note("Grape", "WA")
        self.assertIn("Mediterranean", note)
        self.assertNotIn("Chilling hours may be lower", note,
                         "grape is still getting the stone/pome-fruit chill-hours note")

    def test_grape_page_does_not_claim_chill_hours(self):
        self.assertNotIn("Chilling hours may be lower", GRAPE_PAGES["WA"])

    # --- FAQ JSON-LD ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(GRAPE_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(GRAPE_JSON["core"]["faqs"]) + len(GRAPE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', GRAPE_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', GRAPE_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in GRAPE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in GRAPE_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "agriculture.gov.au",
                "vinehealth.com.au", "wineaustralia.com", "awri.com.au", "csiro.au",
            )),
            "expected at least one gov/industry authority among the sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in GRAPE_JSON["sources"]}
        cited = set()
        for block in [GRAPE_JSON["core"]] + list(GRAPE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "guide cites an unknown source id")

    def test_all_sources_are_cited_somewhere(self):
        # No dead weight: every declared source is used by some section.
        src_ids = {s["id"] for s in GRAPE_JSON["sources"]}
        cited = set()
        for block in [GRAPE_JSON["core"]] + list(GRAPE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(src_ids - cited, set(), "guide declares a source it never cites")

    def test_references_filtered_to_cited_only(self):
        self.assertGreater(GRAPE_PAGES["WA"].count('rel="noopener nofollow"'), 0)

    # --- internal links ---
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', GRAPE_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    # --- further reading (owned RFCA archives) ---
    def test_further_reading_present_on_state_and_species_guide(self):
        for st in STATES:
            self.assertIn('id="further-reading"', GRAPE_PAGES[st], f"{st} missing Further reading")
        self.assertIn('id="further-reading"', gg.render_species_guide("grape"))

    def test_further_reading_links_point_to_owned_archives(self):
        fr = self._fr(GRAPE_PAGES["WA"])
        self.assertIn("rfcarchives.org.au", fr)

    def test_further_reading_links_are_followed_not_nofollow(self):
        fr = self._fr(GRAPE_PAGES["WA"])
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    # ------------------------------------------------------------------
    # Correctness guards: the phylloxera story differs sharply by state and
    # must not blur. Getting variety/climate/pest/biosecurity advice wrong
    # wastes a grower's years, so pin the key facts.
    # ------------------------------------------------------------------
    def test_core_says_grapes_are_self_fertile(self):
        sp = gg.render_species_guide("grape")
        self.assertIn("self-fertile", sp)
        self.assertIn("single vine", sp)

    def test_core_says_grapes_do_not_ripen_after_picking(self):
        # Non-climacteric: do not repeat the olive/stone-fruit "ripens off the tree" error.
        sp = gg.render_species_guide("grape")
        self.assertIn("do not ripen any further once they are picked", sp)

    def test_core_explains_cane_and_spur_pruning(self):
        sp = gg.render_species_guide("grape")
        self.assertIn("Cane pruning", sp)
        self.assertIn("Spur pruning", sp)
        self.assertIn("Thompson Seedless", sp)

    def test_wa_is_phylloxera_free_with_own_rooted_vines(self):
        wa = GRAPE_PAGES["WA"]
        self.assertIn("free of grape phylloxera", wa)
        self.assertIn("own-rooted", wa)

    def test_wa_fruit_fly_is_medfly_not_queensland_fruit_fly(self):
        # WA's grape pest is Mediterranean fruit fly; Qfly must not be put on the WA page.
        wa = GRAPE_PAGES["WA"]
        self.assertIn("Mediterranean fruit fly", wa)
        self.assertNotIn("Queensland fruit fly", wa)

    def test_qld_is_a_phylloxera_exclusion_zone_not_simply_free(self):
        qld = GRAPE_PAGES["QLD"]
        self.assertIn("exclusion zone", qld)
        self.assertIn("not known to carry grape phylloxera", qld)

    def test_nsw_and_vic_have_phylloxera_infested_zones(self):
        self.assertIn("infested zones", GRAPE_PAGES["NSW"])
        self.assertIn("Albury", GRAPE_PAGES["NSW"])
        self.assertIn("infested zones", GRAPE_PAGES["VIC"])
        self.assertIn("resistant rootstock", GRAPE_PAGES["VIC"])

    def test_vic_is_the_flagship_table_grape_and_phylloxera_state(self):
        vic = GRAPE_PAGES["VIC"]
        self.assertIn("Sunraysia", vic)
        self.assertIn("Maroondah", vic)  # the Yarra Valley infested zone


if __name__ == "__main__":
    unittest.main()
