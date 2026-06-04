"""
Longan growing-guide tests (tools/scrapers/growing_guides/longan.json). Flagship QLD by
climate (the Atherton Tableland heartland and the Walkamin variety trials), strongest WA
overlay by traffic and home turf. In its own file so parallel guide runs never collide on
a shared test module.
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

LONGAN_SPECIES = {
    "common_name": "Longan",
    "latin_name": "Dimocarpus longan",
    "description": "Generic longan blurb that should be replaced by the rich guide.",
    "slug": "longan",
}


def _longan_products(n=6):
    names = ["Kohala", "Haew", "Chompoo", "Biew Kiew", "Seedling", "Kohala"]
    return [
        {"title": f"Longan {names[i % len(names)]}",
         "url": f"https://nursery.example/longan-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 69.0 + i * 5,
         "available": True, "species": LONGAN_SPECIES}
        for i in range(n)
    ]


LONGAN_PAGES = build_state_pages("longan", _longan_products())
LONGAN_JSON = load_guide("longan")

# Tokens chosen to live ONLY in their own state overlay (never in the shared core or in a
# cited source's name, which would otherwise render on every state page). "Walkamin",
# "Cairns" etc. are deliberately NOT used here because they ride along in citation text.
LONGAN_REGION_TOKENS = {
    "QLD": ["Atherton", "Mareeba"],
    "WA": ["Kununurra", "Carnarvon"],
    "NSW": ["Northern Rivers", "Coffs Harbour"],
    "VIC": ["greenhouse", "Melbourne"],
}


class LonganGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in LONGAN_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} longan page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(LONGAN_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two longan state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in LONGAN_PAGES.items():
            self.assertNotIn("Generic longan blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in LONGAN_REGION_TOKENS.items():
            self.assertTrue(any(t in LONGAN_PAGES[st] for t in tokens),
                            f"{st} longan page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in LONGAN_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, LONGAN_PAGES[other],
                                     f"{owner} longan token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in LONGAN_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on longan {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on longan {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, LONGAN_JSON, "longan.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          LONGAN_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(LONGAN_JSON["core"]["faqs"]) + len(LONGAN_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', LONGAN_PAGES[st], f"{st} missing Sources")
        for s in LONGAN_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in LONGAN_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "ask.ifas.ufl.edu", "agrifutures.com.au",
            )),
            "expected at least one gov/industry authority among the longan sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in LONGAN_JSON["sources"]}
        cited = set()
        for block in [LONGAN_JSON["core"]] + list(LONGAN_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "longan guide cites an unknown source id")

    def test_sources_note_is_longan_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", LONGAN_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', LONGAN_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_cross_links_to_lychee(self):
        # Longan is the lychee's close cousin; the core should cross-link to it.
        self.assertIn("/species/lychee.html", gg.render_species_guide("longan"))

    def test_no_lychee_only_pests(self):
        # The lychee erinose mite is specific to Litchi, not longan: it must not be
        # copied across from the lychee guide onto any longan page.
        for st, html in LONGAN_PAGES.items():
            self.assertNotIn("erinose", html.lower(), f"lychee-only erinose mite on longan {st} page")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("longan"))
        m = re.search(r'id="further-reading".*?</section>', LONGAN_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("longan")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("longan").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("longan", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
