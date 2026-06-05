"""
Grumichama growing-guide tests (tools/scrapers/growing_guides/grumichama.json).

Grumichama (Eugenia brasiliensis, the Brazil cherry) is a subtropical to tropical
myrtle-family fruit, the close kin of jaboticaba, so it takes the SHARED "subtropical"
climate note rather than a dedicated category (unlike feijoa/loquat). The grumichama
story that the overlays must carry, and that these guards lock in:
  * self-fertile: one tree fruits (no false "needs a pollinator" claim);
  * thin, soft, edible skin makes it a fruit-fly HOST (the opposite of its
    thick-skinned cousin jaboticaba), so QFF in the east and medfly in WA both bite it;
  * cold-hardier than most subtropicals (mature trees take a light frost to about -3C),
    which is why it reaches sheltered Sydney and a warm-spot Melbourne;
  * a fast, short, concentrated crop about 4 to 5 weeks after spring flowering;
  * myrtle rust is the family disease to watch in the humid east; WA is nearly free of it.
Further reading carries the auto-merged RFCA owned archive links (there is no WANATCA
yearbook article on grumichama, so none is curated).

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

GRUMICHAMA_SPECIES = {
    "common_name": "Grumichama",
    "latin_name": "Eugenia brasiliensis",
    "description": "Generic grumichama blurb that should be replaced by the rich guide.",
    "slug": "grumichama",
}


def _grumichama_products(n=8):
    # Named forms actually in live Australian nursery stock (Daleys, Ross Creek,
    # Fruitopia, Ladybird): Black (the common form), Yellow/Orange, and Dwarf Black.
    names = ["Black", "Orange", "Yellow", "Dwarf Black", "Black 140mm",
             "Black 165mm", "Cherry", "Yellow Large"]
    return [
        {"title": f"Grumichama {names[i % len(names)]}",
         "url": f"https://nursery.example/grumichama-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 18.0 + i * 6,
         "available": True, "species": GRUMICHAMA_SPECIES}
        for i in range(n)
    ]


GRUMICHAMA_PAGES = build_state_pages("grumichama", _grumichama_products())
GRUMICHAMA_JSON = load_guide("grumichama")

# Region tokens unique to one state (the leak guard relies on this). Each appears
# only in its own state's overlay, never in the core, the climate note, or another
# state's overlay.
GRUMICHAMA_REGION_TOKENS = {
    "WA": ["Swan Coastal Plain", "Gascoyne"],
    "QLD": ["Atherton Tableland", "Sunshine Coast"],
    "NSW": ["Northern Rivers", "Coffs Harbour"],
    "VIC": ["Mornington Peninsula", "Gippsland"],
}


class GrumichamaGuideTests(unittest.TestCase):
    """Each state page genuinely unique, dash-free, cited, FAQ-rich; shared subtropical note."""

    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in GRUMICHAMA_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} grumichama page too small")

    def test_canonical_and_og(self):
        wa = GRUMICHAMA_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-grumichama-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the guide.
        wa = GRUMICHAMA_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Grumichama in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in GRUMICHAMA_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Grumichama in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(GRUMICHAMA_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two grumichama state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in GRUMICHAMA_REGION_TOKENS.items():
            self.assertTrue(any(t in GRUMICHAMA_PAGES[st] for t in tokens),
                            f"{st} grumichama page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in GRUMICHAMA_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, GRUMICHAMA_PAGES[other],
                                     f"{owner} grumichama token '{t}' leaked onto {other} page")

    def test_generic_blurb_replaced(self):
        for st, html in GRUMICHAMA_PAGES.items():
            self.assertNotIn("Generic grumichama blurb", html, f"{st} still shows the blurb")

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in GRUMICHAMA_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on grumichama {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on grumichama {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, GRUMICHAMA_JSON, "grumichama.json")

    # --- FAQ JSON-LD ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(GRUMICHAMA_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(GRUMICHAMA_JSON["core"]["faqs"]) + len(GRUMICHAMA_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    # --- sources ---
    def test_sources_present_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', GRUMICHAMA_PAGES[st], f"{st} missing Sources")
        for s in GRUMICHAMA_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in GRUMICHAMA_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "dcceew.gov.au",
                "agriculture.gov.au", "rfcarchives.org.au",
            )),
            "expected at least one gov/archive/authority source among the grumichama sources",
        )

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', GRUMICHAMA_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in GRUMICHAMA_JSON["sources"]}
        cited = set()
        for block in [GRUMICHAMA_JSON["core"]] + list(GRUMICHAMA_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "grumichama guide cites an unknown source id")

    # --- internal links ---
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', GRUMICHAMA_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    # --- further reading (auto-merged RFCA owned archives; no WANATCA article exists) ---
    def test_further_reading_present_and_owned_followed(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("grumichama"))
        for st in STATES:
            self.assertIn('id="further-reading"', GRUMICHAMA_PAGES[st], f"{st} missing Further reading")
        fr = self._fr(GRUMICHAMA_PAGES["WA"])
        self.assertIn("rfcarchives.org.au", fr, "grumichama Further reading missing RFCA owned links")
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_count_matches_merged(self):
        merged = gg.get_further_reading("grumichama")
        self.assertGreaterEqual(len(merged), len(GRUMICHAMA_JSON.get("further_reading", [])))
        self.assertEqual(self._fr(GRUMICHAMA_PAGES["WA"]).count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("grumichama").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("grumichama", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    # --- climate: grumichama shares the "subtropical" category (NOT dedicated) ---
    def test_grumichama_climate_category_is_subtropical(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["grumichama"], "subtropical",
                         "grumichama should take the shared subtropical note, like jaboticaba")
        for st in STATES:
            note = bssp.get_climate_note("Grumichama", st)
            self.assertIn("subtropical", note.lower(),
                          f"{st} grumichama climate note should be the subtropical one")
            self.assertNotIn("Chilling hours may be lower", note,
                             "grumichama must not inherit the stone/pome-fruit chill-hours note")
            self.assertNotIn("stone fruit, apples, and pears", note,
                             "grumichama must not inherit the temperate 'default' VIC note")

    # --- correctness guards specific to grumichama ---
    def test_self_fertile_one_tree_no_false_pollinator_claim(self):
        # A grower most needs to know grumichama is self-fertile (one tree crops).
        for st, html in GRUMICHAMA_PAGES.items():
            self.assertIn("self-fertile", html, f"{st} missing the self-fertile fact")
            self.assertNotIn("must have a pollinator", html, f"{st} wrongly claims a pollinator is needed")
            self.assertNotIn("need a second tree", html, f"{st} wrongly claims a second tree is needed")

    def test_thin_skin_fruit_fly_host_not_resistant(self):
        # The key divergence from jaboticaba: grumichama's thin skin makes it a
        # fruit-fly HOST. It must never be called fruit-fly resistant.
        for st, html in GRUMICHAMA_PAGES.items():
            self.assertNotIn("fruit-fly resistant", html, f"{st} wrongly calls grumichama fruit-fly resistant")
            self.assertNotIn("fruit-fly-resistant", html, f"{st} wrongly calls grumichama fruit-fly resistant")
            self.assertIn("thin", html.lower(), f"{st} should describe the thin skin")
        # The eastern states get Queensland fruit fly; WA gets Mediterranean fruit fly.
        for st in ("QLD", "NSW"):
            self.assertIn("Queensland fruit fly", GRUMICHAMA_PAGES[st], f"{st} must flag QFF")
        self.assertIn("Mediterranean fruit fly", GRUMICHAMA_PAGES["WA"], "WA must flag medfly, not QFF")

    def test_cold_hardiness_story_present(self):
        # The trait that lets grumichama reach Sydney and a warm-spot Melbourne.
        for st in ("NSW", "VIC"):
            self.assertIn("light frost", GRUMICHAMA_PAGES[st].lower().replace("frosts", "frost"),
                          f"{st} should carry the light-frost hardiness story")
        self.assertIn("minus 3", GRUMICHAMA_PAGES["VIC"], "VIC should give the approx -3C hardiness figure")

    def test_myrtle_rust_flagged_in_humid_east(self):
        for st in ("QLD", "NSW"):
            self.assertIn("myrtle rust", GRUMICHAMA_PAGES[st].lower(), f"{st} must flag myrtle rust")
        self.assertIn("myrtle rust", GRUMICHAMA_PAGES["WA"].lower(),
                      "WA should note WA is nearly free of myrtle rust")

    def test_birds_flagged_and_netting(self):
        # Birds (and netting) are a headline grumichama challenge; the core harvest
        # section carries it, so it appears on every page.
        for st, html in GRUMICHAMA_PAGES.items():
            self.assertIn("bird", html.lower(), f"{st} page does not mention birds")
            self.assertIn("net", html.lower(), f"{st} page does not mention netting")

    def test_short_concentrated_harvest_story(self):
        # The defining harvest fact: a fast crop about 4 to 5 weeks after flowering,
        # short and concentrated in the subtropics. Core section, so on every page.
        for st, html in GRUMICHAMA_PAGES.items():
            self.assertIn("four to five weeks", html, f"{st} missing the flower-to-fruit timing")

    def test_acid_soil_requirement_present(self):
        # Grumichama is intolerant of alkaline soil; the acid-soil need is core.
        for st, html in GRUMICHAMA_PAGES.items():
            self.assertIn("acid", html.lower(), f"{st} missing the acid-soil requirement")

    def test_variety_forms_present(self):
        # Tie recommendations to the forms actually in live stock: black, yellow, dwarf.
        core = gg.render_species_guide("grumichama").lower()
        for form in ("black", "yellow", "dwarf"):
            self.assertIn(form, core, f"core guide should mention the {form} form")

    def test_wa_myrtle_family_shipping_nuance(self):
        wa = GRUMICHAMA_PAGES["WA"]
        self.assertIn("myrtle-family", wa, "WA page should explain the myrtle-family import condition")
        self.assertIn("ship to WA", wa, "WA page should note the table is filtered to WA shippers")


if __name__ == "__main__":
    unittest.main()
