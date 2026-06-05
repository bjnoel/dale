"""
Passionfruit growing-guide tests (tools/scrapers/growing_guides/passionfruit.json).

Passionfruit is a frost-tender subtropical VINE with a story the generic "subtropical"
note misses (Queensland heartland, WA medfly + quarantine, Victoria's grafted cold-tolerant
rootstock), so it gets its OWN climate category. Every state gets a real, distinct overlay.
Further reading is RFCA (auto-merged from the archive index) plus one curated WANATCA yearbook
article, so this file asserts both an RFCA and a WANATCA link.

In its own file so parallel guide runs never collide on a shared test module; cross-cutting
guards (climate mapping, the unenriched fallback, the archive index, the growing_guides module
API, and the FAQ-overlap guard) live in tests/test_species_state_pages.py.
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

PASSIONFRUIT_SPECIES = {
    "common_name": "Passionfruit",
    "latin_name": "Passiflora edulis",
    "description": "Generic passionfruit blurb that should be replaced by the rich guide.",
    "slug": "passionfruit",
}


def _passionfruit_products(n=8):
    # Named varieties actually in live Australian nursery stock: purple/black types
    # (Black, Sweetheart, Misty Gem, Pandora, Nellie Kelly) and Panama/golden types
    # (Panama Red, Panama Gold), plus a granadilla.
    names = ["Panama Red", "Panama Gold", "Black", "Sweetheart", "Pandora",
             "Misty Gem", "Nellie Kelly", "Sweet Granadilla"]
    return [
        {"title": f"Passionfruit {names[i % len(names)]}",
         "url": f"https://nursery.example/passionfruit-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 12.0 + i * 4,
         "available": True, "species": PASSIONFRUIT_SPECIES}
        for i in range(n)
    ]


PASSIONFRUIT_PAGES = build_state_pages("passionfruit", _passionfruit_products())
PASSIONFRUIT_JSON = load_guide("passionfruit")

# Region tokens unique to one state (the leak guard relies on this). Each appears
# only in its own state's overlay.
PASSIONFRUIT_REGION_TOKENS = {
    "WA": ["Albany", "Manjimup", "Kununurra"],
    "QLD": ["Sunshine Coast", "Wide Bay", "Daintree"],
    "NSW": ["Tweed", "Coffs Harbour", "Northern Tablelands"],
    "VIC": ["Melbourne", "Mornington"],
}


class PassionfruitGuideTests(unittest.TestCase):
    """Each state page genuinely unique, dash-free, cited, FAQ-rich; vine agronomy correct."""

    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in PASSIONFRUIT_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} passionfruit page too small")

    def test_canonical_and_og(self):
        wa = PASSIONFRUIT_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-passionfruit-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the guide.
        wa = PASSIONFRUIT_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Passionfruit in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in PASSIONFRUIT_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Passionfruit in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(PASSIONFRUIT_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two passionfruit state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in PASSIONFRUIT_REGION_TOKENS.items():
            self.assertTrue(any(t in PASSIONFRUIT_PAGES[st] for t in tokens),
                            f"{st} passionfruit page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in PASSIONFRUIT_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, PASSIONFRUIT_PAGES[other],
                                     f"{owner} passionfruit token '{t}' leaked onto {other} page")

    def test_generic_blurb_replaced(self):
        for st, html in PASSIONFRUIT_PAGES.items():
            self.assertNotIn("Generic passionfruit blurb", html, f"{st} still shows the blurb")

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in PASSIONFRUIT_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on passionfruit {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on passionfruit {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, PASSIONFRUIT_JSON, "passionfruit.json")

    # --- FAQ JSON-LD ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(PASSIONFRUIT_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(PASSIONFRUIT_JSON["core"]["faqs"]) + len(PASSIONFRUIT_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    # --- sources ---
    def test_sources_present_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', PASSIONFRUIT_PAGES[st], f"{st} missing Sources")
        for s in PASSIONFRUIT_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in PASSIONFRUIT_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpi.qld.gov.au", "daf.nt.gov.au", "dpird.wa.gov.au", "beeaware.org.au",
                "passionfruitaustralia.org.au",
            )),
            "expected at least one gov/authority/industry source among the passionfruit sources",
        )

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', PASSIONFRUIT_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in PASSIONFRUIT_JSON["sources"]}
        cited = set()
        for block in [PASSIONFRUIT_JSON["core"]] + list(PASSIONFRUIT_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
            for f in block.get("faqs", []):
                cited.update(f.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "passionfruit guide cites an unknown source id")

    # --- internal links ---
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', PASSIONFRUIT_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    # --- further reading (owned RFCA archives auto-merged + curated WANATCA, both followed) ---
    def test_further_reading_present_and_owned_followed(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("passionfruit"))
        for st in STATES:
            self.assertIn('id="further-reading"', PASSIONFRUIT_PAGES[st], f"{st} missing Further reading")
        fr = self._fr(PASSIONFRUIT_PAGES["WA"])
        self.assertIn("rfcarchives.org.au", fr, "passionfruit Further reading missing RFCA")
        self.assertIn("wanatca.org.au", fr, "passionfruit Further reading missing curated WANATCA article")
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_count_matches_merged(self):
        merged = gg.get_further_reading("passionfruit")
        self.assertGreaterEqual(len(merged), len(PASSIONFRUIT_JSON.get("further_reading", [])))
        self.assertEqual(self._fr(PASSIONFRUIT_PAGES["WA"]).count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("passionfruit").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("passionfruit", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    # --- climate: passionfruit has its OWN category, not "subtropical" ---
    def test_passionfruit_climate_category_is_dedicated(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["passionfruit"], "passionfruit",
                         "passionfruit must not inherit the subtropical climate note")
        for st in STATES:
            note = bssp.get_climate_note("Passionfruit", st)
            self.assertIn("passion", note.lower(), f"{st} passionfruit climate note should mention passionfruit")

    def test_wa_note_carries_the_medfly_and_quarantine_story(self):
        note = bssp.get_climate_note("Passionfruit", "WA")
        self.assertIn("Mediterranean fruit fly", note, "WA note should name Mediterranean fruit fly, not Qld fruit fly")
        self.assertIn("quarantine", note.lower(), "WA note should mention quarantine on live vines")

    def test_vic_note_leans_on_grafted_cold_tolerant_vine(self):
        note = bssp.get_climate_note("Passionfruit", "VIC")
        self.assertIn("grafted", note.lower(), "VIC note should recommend a grafted vine")
        self.assertIn("Nellie Kelly", note, "VIC note should name the cold-tolerant grafted type")

    # --- correctness guards specific to passionfruit ---
    def test_self_fertility_is_stated_correctly(self):
        # A grower most needs to know a single purple vine sets fruit, while the golden
        # /Panama types are self-incompatible. Guard both halves on every page (core renders
        # on all states).
        for st, html in PASSIONFRUIT_PAGES.items():
            self.assertIn("self-fertile", html, f"{st} should state purple types are self-fertile")
            self.assertIn("single healthy vine", html, f"{st} should say a single vine crops")
            self.assertIn("self-incompatible", html, f"{st} should flag the golden/Panama self-incompatibility")

    def test_woodiness_virus_flagged_everywhere(self):
        # PWV is THE reason passionfruit vines are short-lived; every page must say so.
        for st, html in PASSIONFRUIT_PAGES.items():
            self.assertIn("woodiness virus", html, f"{st} page does not mention woodiness virus")

    def test_grafted_rootstock_sucker_warning_present(self):
        # The classic passionfruit gotcha: grafted onto a rootstock, whose suckers must be removed.
        for st, html in PASSIONFRUIT_PAGES.items():
            self.assertIn("rootstock", html, f"{st} page does not mention the rootstock")
            self.assertIn("grafted", html, f"{st} page does not mention grafting")

    def test_banana_passionfruit_weed_disambiguation(self):
        # Banana passionfruit is a different species and an environmental weed; the guide
        # must disambiguate it (it appears in live stock, so buyers ask).
        for st, html in PASSIONFRUIT_PAGES.items():
            self.assertIn("Banana passionfruit", html, f"{st} missing banana passionfruit disambiguation")
            self.assertIn("weed", html.lower(), f"{st} should flag banana passionfruit as a weed")

    def test_carpenter_bees_named_as_key_pollinator(self):
        # Correctness: carpenter bees are the most efficient pollinator (honeybees are
        # effective too, not "poor"). Guard the carpenter-bee mention.
        for st, html in PASSIONFRUIT_PAGES.items():
            self.assertIn("carpenter bees", html, f"{st} should name carpenter bees as pollinators")


if __name__ == "__main__":
    unittest.main()
