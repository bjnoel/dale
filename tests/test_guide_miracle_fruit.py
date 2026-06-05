"""
Miracle fruit growing-guide tests (tools/scrapers/growing_guides/miracle-fruit.json). QLD flagship
by climate (the humid tropical north is its one outdoor home in Australia), with a strong WA overlay
(alkaline-soil/water reality, pot culture, quarantine). Its own "miracle-fruit" climate category,
because the generic "tropical" note misleads (it is a humidity-and-acid-soil understorey shrub, not a
heat-and-sun crop, and is sold only as seedlings). Archives-first: the Rare Fruit Council of Australia
holds five miracle fruit articles, the richest owned source. In its own file so parallel guide runs
never collide on a shared test module.
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

MIRACLE_SPECIES = {
    "common_name": "Miracle Fruit",
    "latin_name": "Synsepalum dulcificum",
    "description": "Generic miracle fruit blurb that should be replaced by the rich guide.",
    "slug": "miracle-fruit",
    "synonyms": ["Miracle Berry", "Miraculous Berry"],
}


def _miracle_products(n=6):
    # No named cultivars exist; plants sell as seedlings or advanced potted plants.
    names = ["Seedling", "Advanced 200mm pot", "Berry", "Tube stock", "Advanced 6L", "Large plant"]
    return [
        {"title": f"Miracle Fruit {names[i % len(names)]}",
         "url": f"https://nursery.example/miracle-fruit-{i}",
         "nursery_key": "ross-creek", "nursery_name": "Ross Creek Tropicals",
         "price": 24.0 + i * 8, "available": True, "species": MIRACLE_SPECIES}
        for i in range(n)
    ]


MIRACLE_PAGES = build_state_pages("miracle-fruit", _miracle_products())
MIRACLE_JSON = load_guide("miracle-fruit")

# Region tokens must be unique to each state's overlay (and absent from the shared core, the amber
# climate note, and the cross-links). "Perth" is excluded as a token because it appears in the site
# footer on every page.
MIRACLE_REGION_TOKENS = {
    "WA": ["Swan Coastal Plain", "Carnarvon"],
    "QLD": ["Cassowary Coast", "Atherton Tableland"],
    "NSW": ["Northern Rivers", "Tweed Valley"],
    "VIC": ["Mornington Peninsula", "Goulburn Valley"],
}


class MiracleFruitGuideTests(unittest.TestCase):
    def test_own_climate_category(self):
        # The generic "tropical" note is wrong for a humidity-loving, acid-soil, frost-tender,
        # seedling-only shrub, so miracle fruit gets its own category (key is the common name).
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["miracle fruit"], "miracle-fruit")

    def test_every_state_has_a_miracle_fruit_climate_note(self):
        for st in STATES:
            self.assertIn("miracle-fruit", bssp.STATE_CLIMATE_NOTES[st],
                          f"{st} has no miracle-fruit climate note")
            note = bssp.get_climate_note("Miracle Fruit", st)
            self.assertNotIn(EM_DASH, note)
            self.assertNotIn(EN_DASH, note)

    def test_pages_build_nonempty(self):
        for st, html in MIRACLE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} miracle fruit page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(MIRACLE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two miracle fruit state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in MIRACLE_PAGES.items():
            self.assertNotIn("Generic miracle fruit blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in MIRACLE_REGION_TOKENS.items():
            self.assertTrue(any(t in MIRACLE_PAGES[st] for t in tokens),
                            f"{st} miracle fruit page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in MIRACLE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, MIRACLE_PAGES[other],
                                     f"{owner} miracle fruit token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in MIRACLE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on miracle fruit {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on miracle fruit {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, MIRACLE_JSON, "miracle-fruit.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          MIRACLE_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(MIRACLE_JSON["core"]["faqs"]) + len(MIRACLE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_gov_authority(self):
        for st in STATES:
            self.assertIn('id="sources"', MIRACLE_PAGES[st], f"{st} missing Sources")
        for s in MIRACLE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in MIRACLE_JSON["sources"])
        self.assertIn("dpird.wa.gov.au", domains, "expected the WA gov quarantine authority among sources")

    def test_owned_rfca_archives_are_cited(self):
        # Archives-first: lean on the owned RFCA archives (five miracle fruit articles). There is no
        # WANATCA yearbook article for miracle fruit, so RFCA carries the owned-source requirement.
        domains = " ".join(s["url"] for s in MIRACLE_JSON["sources"])
        self.assertIn("rfcarchives.org.au", domains, "expected an owned RFCA citation")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in MIRACLE_JSON["sources"]}
        cited = set()
        for block in [MIRACLE_JSON["core"]] + list(MIRACLE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "miracle fruit guide cites an unknown source id")

    def test_sources_note_is_not_olive_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", MIRACLE_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', MIRACLE_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_rfca_followed_rfcwa_nofollow(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("miracle-fruit"))
        m = re.search(r'id="further-reading".*?</section>', MIRACLE_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("rfcarchives.org.au", fr)  # owned RFCA archives, curated + auto-merged
        # Owned RFCA cross-links must be followed (no nofollow).
        for url, attrs in re.findall(r'<a href="(https://rfcarchives[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned RFCA cross-link should be followed: {url}")
        # The WA Rare Fruit Club is third-party (Benedict does not host it), so any link is nofollow.
        for url, attrs in re.findall(r'<a href="(https://rarefruitclub\.au[^"]+)"([^>]*)>', fr):
            self.assertIn("nofollow", attrs, f"third-party rarefruitclub.au link must be nofollow: {url}")
        merged = gg.get_further_reading("miracle-fruit")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("miracle-fruit").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("miracle-fruit", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    def test_acid_soil_is_emphasised(self):
        # Acid soil is the make-or-break for this species (RFCA + CRFG): the guide must say so,
        # with the citable pH band, or a grower plants it into alkaline ground and loses it.
        blob = json.dumps(MIRACLE_JSON).lower()
        self.assertIn("acid", blob)
        self.assertIn("4.5 to 5.8", blob)

    def test_self_fertile_not_pollinator_dependent(self):
        # Correctness: a single seedling fruits on its own (RFCA Whitman/Cannon). Guard against a
        # copied-in "needs a second tree / cross-pollination" claim, which is wrong for this species.
        blob = json.dumps(MIRACLE_JSON).lower()
        self.assertIn("on its own", blob)
        self.assertNotIn("cross-pollination", blob)
        self.assertNotIn("needs a pollinator", blob)

    def test_sold_as_seedlings_not_named_varieties(self):
        # There are no named cultivars in the trade; the guide must not invent one to "recommend".
        blob = json.dumps(MIRACLE_JSON).lower()
        self.assertIn("no named cultivars", blob)
        self.assertIn("seedling", blob)

    def test_white_oil_caution_present(self):
        # Species-specific correctness (RFCA Avondale, 1982): treat scale with something OTHER than
        # white oil, which strips this plant's leaves. A real, non-generic detail worth pinning.
        blob = json.dumps(MIRACLE_JSON).lower()
        self.assertIn("white oil", blob)


if __name__ == "__main__":
    unittest.main()
