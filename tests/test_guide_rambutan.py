"""
Rambutan growing-guide tests (tools/scrapers/growing_guides/rambutan.json). Flagship QLD
by climate (the far-north Queensland wet tropics, with the Top End of the NT the only other
viable region); WA/NSW/VIC overlays cover a tree that sits at or beyond the climate margin.
In its own file so parallel guide runs never collide on a shared test module.

Rambutan is the hairy Sapindaceae cousin of the lychee and longan, so this file reuses the
longan/lychee guards (cousin cross-links, no genus-Litchi erinose mite) and adds the
rambutan-specific correctness checks the research pinned down:
  * rambutan is NOT a recorded host of Queensland fruit fly (Business Qld + the Australian
    fruit fly handbook both omit it, though they list santol and wax jambu), so the QLD page
    must say so and must never claim it IS a host;
  * the distinctive feeding rule: never feed rambutan muriate of potash or any chloride;
  * the distinguishing pollination story: unlike a self-fruitful longan, most rambutan clones
    are functionally female and want a pollen partner to crop.
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

RAMBUTAN_SPECIES = {
    "common_name": "Rambutan",
    "latin_name": "Nephelium lappaceum",
    "description": "Generic rambutan blurb that should be replaced by the rich guide.",
    "slug": "rambutan",
}


def _rambutan_products(n=6):
    names = ["Red", "Yellow", "R134", "Binjai Marcot", "Jitlee", "Seedling"]
    return [
        {"title": f"Rambutan {names[i % len(names)]}",
         "url": f"https://nursery.example/rambutan-{i}",
         "nursery_key": "ross-creek", "nursery_name": "Ross Creek Tropicals",
         "price": 59.0 + i * 10, "available": True, "species": RAMBUTAN_SPECIES}
        for i in range(n)
    ]


RAMBUTAN_PAGES = build_state_pages("rambutan", _rambutan_products())
RAMBUTAN_JSON = load_guide("rambutan")

# Tokens chosen to live ONLY in their own state overlay (never in the shared core or in a
# cited source's name, which would otherwise render on every state page). NT places such as
# "Darwin"/"Adelaide River" and source-name tokens are deliberately avoided here.
RAMBUTAN_REGION_TOKENS = {
    "QLD": ["Innisfail", "Tully"],
    "WA": ["Kununurra", "Kimberley"],
    "NSW": ["Northern Rivers", "Ballina"],
    "VIC": ["Melbourne", "glasshouse"],
}


class RambutanGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in RAMBUTAN_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} rambutan page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(RAMBUTAN_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two rambutan state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in RAMBUTAN_PAGES.items():
            self.assertNotIn("Generic rambutan blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in RAMBUTAN_REGION_TOKENS.items():
            self.assertTrue(any(t in RAMBUTAN_PAGES[st] for t in tokens),
                            f"{st} rambutan page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in RAMBUTAN_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, RAMBUTAN_PAGES[other],
                                     f"{owner} rambutan token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in RAMBUTAN_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on rambutan {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on rambutan {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, RAMBUTAN_JSON, "rambutan.json")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          RAMBUTAN_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(RAMBUTAN_JSON["core"]["faqs"]) + len(RAMBUTAN_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', RAMBUTAN_PAGES[st], f"{st} missing Sources")
        for s in RAMBUTAN_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in RAMBUTAN_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "daf.nt.gov.au", "business.qld.gov.au", "dpird.wa.gov.au", "agrifutures.com.au",
            )),
            "expected at least one gov/industry authority among the rambutan sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in RAMBUTAN_JSON["sources"]}
        cited = set()
        for block in [RAMBUTAN_JSON["core"]] + list(RAMBUTAN_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "rambutan guide cites an unknown source id")

    def test_sources_note_is_rambutan_specific(self):
        for st in STATES:
            self.assertNotIn("olive-industry", RAMBUTAN_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', RAMBUTAN_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_cross_links_to_lychee_and_longan(self):
        # Rambutan is the hairy cousin of the lychee and longan; the core cross-links both.
        sp = gg.render_species_guide("rambutan")
        self.assertIn("/species/lychee.html", sp)
        self.assertIn("/species/longan.html", sp)

    def test_no_lychee_only_pests(self):
        # The lychee erinose mite is specific to genus Litchi, not Nephelium: it must not be
        # carried across onto any rambutan page (same guard as the longan guide).
        for st, html in RAMBUTAN_PAGES.items():
            self.assertNotIn("erinose", html.lower(), f"lychee-only erinose mite on rambutan {st} page")

    def test_not_a_queensland_fruit_fly_host(self):
        # Correctness: rambutan is NOT a recorded Qfly host (Business Qld host list and the
        # Australian fruit fly handbook both omit it). The QLD page must say so and must never
        # assert the opposite.
        qld = RAMBUTAN_PAGES["QLD"]
        self.assertIn("not listed as a host of Queensland fruit fly", qld)
        self.assertNotIn("rambutan is a host of queensland fruit fly", qld.lower())

    def test_chloride_feeding_caution_present(self):
        # Distinctive owned fact (RFCA Kamerunga leaf analysis): rambutan is chloride-sensitive,
        # so muriate of potash must be avoided. Lock it in so the feeding advice cannot drift.
        sp = gg.render_species_guide("rambutan").lower()
        self.assertIn("chloride", sp)
        self.assertIn("muriate of potash", sp)

    def test_pollination_needs_a_pollen_partner(self):
        # The distinguishing story vs the self-fruitful longan: most rambutan clones are
        # functionally female and want a pollen source. The core must raise this.
        sp = gg.render_species_guide("rambutan").lower()
        self.assertIn("pollen", sp)

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("rambutan"))
        m = re.search(r'id="further-reading".*?</section>', RAMBUTAN_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("rambutan")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("rambutan").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("rambutan", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


if __name__ == "__main__":
    unittest.main()
