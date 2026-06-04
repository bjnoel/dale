"""
Olive growing-guide tests (tools/scrapers/growing_guides/olive.json), the reference
implementation. In its own file so parallel guide runs never collide on a shared test
module; cross-cutting guards (climate mapping, fallback, archive index, the gg module
API, FAQ overlap) live in tests/test_species_state_pages.py.
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

OLIVE_SPECIES = {
    "common_name": "Olive",
    "latin_name": "Olea europaea",
    "description": "Generic olive blurb that should be replaced by the rich guide.",
    "slug": "olive",
}


def _olive_products(n=5):
    return [
        {
            "title": f"Olive Variety {i}",
            "url": f"https://nursery.example/olive-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 20.0 + i * 5,
            "available": True,
            "species": OLIVE_SPECIES,
        }
        for i in range(n)
    ]


OLIVE_PAGES = build_state_pages("olive", _olive_products())
OLIVE_JSON = load_guide("olive")

# State-specific region tokens that must appear on exactly one state's page.
OLIVE_REGION_TOKENS = {
    "WA": ["Moore River", "Gingin"],
    "QLD": ["Granite Belt", "Darling Downs"],
    "NSW": ["Riverina"],
    "VIC": ["Sunraysia", "Grampians"],
}


class OliveGuideTests(unittest.TestCase):
    """The reference guide: each state page genuinely unique, dash-free, cited, FAQ-rich."""

    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in OLIVE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} page too small")

    def test_canonical_and_og(self):
        wa = OLIVE_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-olive-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the guide.
        wa = OLIVE_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Olive in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in OLIVE_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Olive in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(OLIVE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in OLIVE_REGION_TOKENS.items():
            self.assertTrue(any(t in OLIVE_PAGES[st] for t in tokens),
                            f"{st} page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in OLIVE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, OLIVE_PAGES[other],
                                     f"{owner} token '{t}' leaked onto {other} page")

    def test_state_full_name_in_guide(self):
        for st in STATES:
            self.assertIn(bssp.STATE_FULL_NAMES[st], OLIVE_PAGES[st])

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in OLIVE_PAGES.items():
            self.assertNotIn("Generic olive blurb", html, f"{st} still shows the blurb")

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in OLIVE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} page (guards the price-range bug)")

    def test_price_range_uses_hyphen_not_en_dash(self):
        # The live bug was f"${lo}-${hi}" built with a U+2013. Multi-price pages
        # must render a plain-hyphen range.
        wa = OLIVE_PAGES["WA"]
        self.assertRegex(wa, r"\$\d+-\$\d+", "expected a hyphenated price range")
        self.assertNotIn(EN_DASH, wa)

    def test_product_titles_with_dashes_are_sanitised(self):
        prods = _olive_products(1)
        prods[0]["title"] = "Olive – Ascolana Tenera — Large"
        prods[0]["nursery_name"] = "Some – Nursery"
        html = bssp.build_combo_page("WA", "olive", prods, TODAY)
        self.assertIn("Olive - Ascolana Tenera - Large", html)
        self.assertNotIn(EM_DASH, html)
        self.assertNotIn(EN_DASH, html)

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, OLIVE_JSON, "olive.json")

    # --- climate (olive must not inherit the stone-fruit chill note) ---
    def test_olive_climate_note_is_not_stone_fruit_chill_text(self):
        note = bssp.get_climate_note("Olive", "WA")
        self.assertIn("Mediterranean", note)
        self.assertNotIn("Chilling hours may be lower", note,
                         "olive is still getting the stone/pome-fruit chill-hours note")

    def test_olive_page_does_not_claim_chill_hours(self):
        self.assertNotIn("Chilling hours may be lower", OLIVE_PAGES["WA"])

    # --- FAQ JSON-LD ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(OLIVE_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(OLIVE_JSON["core"]["faqs"]) + len(OLIVE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    # --- sources ---
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', OLIVE_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', OLIVE_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in OLIVE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in OLIVE_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "dpi.nsw.gov.au",
                "australianolives.com.au", "agrifutures.com.au", "csiro.au",
            )),
            "expected at least one gov/industry authority among the sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in OLIVE_JSON["sources"]}
        cited = set()
        for block in [OLIVE_JSON["core"]] + list(OLIVE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "guide cites an unknown source id")

    def test_sources_note_generic_by_default_overridable_per_guide(self):
        fake = {"sources": [{"id": "x", "name": "Test", "url": "https://example.gov.au/"}]}
        generic = gg._render_references(fake, {"x"})
        self.assertNotIn("olive-industry", generic, "Sources note leaks olive-specific copy")
        self.assertIn("horticultural research", generic)
        custom = gg._render_references({**fake, "sources_note": "Fig note here."}, {"x"})
        self.assertIn("Fig note here.", custom)
        # olive keeps its specific wording via its own sources_note override.
        self.assertIn("olive-industry bodies", OLIVE_PAGES["WA"])

    def test_references_filtered_to_cited_only(self):
        self.assertGreater(OLIVE_PAGES["WA"].count('rel="noopener nofollow"'), 0)

    # --- internal links ---
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', OLIVE_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    # --- further reading (owned WANATCA + RFCA archives) ---
    def test_further_reading_present_on_state_and_species_guide(self):
        for st in STATES:
            self.assertIn('id="further-reading"', OLIVE_PAGES[st], f"{st} missing Further reading")
        self.assertIn('id="further-reading"', gg.render_species_guide("olive"))

    def test_further_reading_links_point_to_owned_archives(self):
        fr = self._fr(OLIVE_PAGES["WA"])
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)

    def test_further_reading_links_are_followed_not_nofollow(self):
        fr = self._fr(OLIVE_PAGES["WA"])
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_kailis_first_party_source_cited(self):
        self.assertIn("Kailis", OLIVE_PAGES["WA"])
        self.assertIn("wanatca.org.au/yearbooks/Y22all.pdf", OLIVE_PAGES["WA"])

    def test_further_reading_count_matches_merged(self):
        merged = gg.get_further_reading("olive")
        self.assertGreaterEqual(len(merged), len(OLIVE_JSON.get("further_reading", [])))
        self.assertEqual(self._fr(OLIVE_PAGES["WA"]).count("<li>"), len(merged))


if __name__ == "__main__":
    unittest.main()
