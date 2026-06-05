"""
Pomegranate growing-guide tests (tools/scrapers/growing_guides/pomegranate.json).

Pomegranate gets its OWN climate category rather than joining "mediterranean": it
shares the low-chill, hot-dry-summer profile of olive/grape/fig, but its decisive
per-state story is fruit SPLITTING and rot in humidity (a non-issue for olives), so
the eastern-state notes must say that plainly. Every state gets a real, distinct
overlay, anchored on WA by first-party owned sources (the Agriculture WA Medina trial,
and the Yarloop and Yallingup grower accounts in the RFCA/WANATCA archives).

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

POMEGRANATE_SPECIES = {
    "common_name": "Pomegranate",
    "latin_name": "Punica granatum",
    "description": "Generic pomegranate blurb that should be replaced by the rich guide.",
    "slug": "pomegranate",
}


def _pomegranate_products(n=7):
    # Named varieties actually in live Australian nursery stock: a mix of the soft-seeded
    # fresh-eating types and the hard-seeded / juice types the guide names.
    names = ["Wonderful", "Gulosha Rosavaya", "Azerbaijani", "Midnight Velvet",
             "Red Velvet", "Elche", "Parfianka"]
    return [
        {"title": f"Pomegranate {names[i % len(names)]}",
         "url": f"https://nursery.example/pomegranate-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 25.0 + i * 5,
         "available": True, "species": POMEGRANATE_SPECIES}
        for i in range(n)
    ]


POMEGRANATE_PAGES = build_state_pages("pomegranate", _pomegranate_products())
POMEGRANATE_JSON = load_guide("pomegranate")

# Region tokens unique to one state (the leak guard relies on this). Each appears only
# in its own state's overlay; the per-state climate notes (amber box) are kept region-free.
POMEGRANATE_REGION_TOKENS = {
    "WA": ["Medina", "Yarloop", "Yallingup"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Riverina", "Hunter Valley"],
    "VIC": ["Goulburn Valley", "Sunraysia"],
}


class PomegranateGuideTests(unittest.TestCase):
    """Each state page genuinely unique, dash-free, cited, FAQ-rich; own climate category."""

    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in POMEGRANATE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} pomegranate page too small")

    def test_canonical_and_og(self):
        wa = POMEGRANATE_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-pomegranate-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the guide.
        wa = POMEGRANATE_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Pomegranate in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in POMEGRANATE_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Pomegranate in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(POMEGRANATE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two pomegranate state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in POMEGRANATE_REGION_TOKENS.items():
            self.assertTrue(any(t in POMEGRANATE_PAGES[st] for t in tokens),
                            f"{st} pomegranate page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in POMEGRANATE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, POMEGRANATE_PAGES[other],
                                     f"{owner} pomegranate token '{t}' leaked onto {other} page")

    def test_generic_blurb_replaced(self):
        for st, html in POMEGRANATE_PAGES.items():
            self.assertNotIn("Generic pomegranate blurb", html, f"{st} still shows the blurb")

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in POMEGRANATE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on pomegranate {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on pomegranate {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, POMEGRANATE_JSON, "pomegranate.json")

    # --- FAQ JSON-LD ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(POMEGRANATE_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(POMEGRANATE_JSON["core"]["faqs"]) + len(POMEGRANATE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    # --- sources ---
    def test_sources_present_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', POMEGRANATE_PAGES[st], f"{st} missing Sources")
        for s in POMEGRANATE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in POMEGRANATE_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "agrifutures.com.au", "darwin.nt.gov.au",
            )),
            "expected at least one gov/industry authority among the pomegranate sources",
        )

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', POMEGRANATE_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in POMEGRANATE_JSON["sources"]}
        cited = set()
        for block in [POMEGRANATE_JSON["core"]] + list(POMEGRANATE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "pomegranate guide cites an unknown source id")

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("pomegranate").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("pomegranate", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    # --- internal links ---
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', POMEGRANATE_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    # --- further reading (owned WANATCA + RFCA archives, followed) ---
    def test_further_reading_present_and_owned_followed(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("pomegranate"))
        for st in STATES:
            self.assertIn('id="further-reading"', POMEGRANATE_PAGES[st], f"{st} missing Further reading")
        fr = self._fr(POMEGRANATE_PAGES["WA"])
        self.assertIn("wanatca.org.au", fr, "pomegranate Further reading missing WANATCA")
        self.assertIn("rfcarchives.org.au", fr, "pomegranate Further reading missing RFCA")
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_count_matches_merged(self):
        merged = gg.get_further_reading("pomegranate")
        self.assertGreaterEqual(len(merged), len(POMEGRANATE_JSON.get("further_reading", [])))
        self.assertEqual(self._fr(POMEGRANATE_PAGES["WA"]).count("<li>"), len(merged))

    def test_first_party_wa_trial_cited(self):
        # The Agriculture WA Medina cultivar trial is the spine of the WA overlay.
        self.assertIn("rfcarchives.org.au/Next/Fruits/Pomegranate", POMEGRANATE_PAGES["WA"])
        self.assertIn("Medina", POMEGRANATE_PAGES["WA"])

    # --- climate: pomegranate has its OWN category, not "mediterranean" ---
    def test_pomegranate_climate_category_is_dedicated(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["pomegranate"], "pomegranate",
                         "pomegranate must not inherit the mediterranean climate note")
        for st in STATES:
            note = bssp.get_climate_note("Pomegranate", st)
            self.assertIn("pomegran", note.lower(), f"{st} pomegranate climate note should mention pomegranates")
            self.assertNotIn("Chilling hours may be lower", note,
                             "pomegranate should not inherit the stone/pome-fruit chill-hours note")

    # --- correctness guards specific to pomegranate ---
    def test_splitting_is_flagged_as_the_main_problem(self):
        # Fruit splitting is THE pomegranate challenge; every page must cover it.
        for st, html in POMEGRANATE_PAGES.items():
            self.assertIn("Why pomegranates split", html, f"{st} missing the splitting section")
            self.assertIn("split", html.lower(), f"{st} page does not mention splitting")

    def test_non_climacteric_harvest_advice_present(self):
        # A grower must know pomegranates do NOT ripen after picking (pick fully ripe).
        for st, html in POMEGRANATE_PAGES.items():
            self.assertIn("do not ripen after picking", html,
                          f"{st} missing the non-climacteric harvest rule")

    def test_one_tree_is_enough_no_false_pollinator_claim(self):
        # Pomegranates are self-fruitful; a second tree only improves the crop.
        for st, html in POMEGRANATE_PAGES.items():
            self.assertIn("one tree is enough", html, f"{st} missing the self-fruitful pollination point")
            self.assertNotIn("must have a pollinator", html, f"{st} wrongly claims a pollinator is required")
            self.assertNotIn("need a second tree", html, f"{st} wrongly claims a second tree is needed")

    def test_correct_fruit_fly_per_region(self):
        # WA = Mediterranean fruit fly (and pomegranate is not a listed host); the
        # eastern states = Queensland fruit fly (pomegranate IS a host).
        self.assertIn("Mediterranean fruit fly", POMEGRANATE_PAGES["WA"])
        for st in ("QLD", "NSW", "VIC"):
            self.assertIn("Queensland fruit fly", POMEGRANATE_PAGES[st],
                          f"{st} should name Queensland fruit fly as the pest")


if __name__ == "__main__":
    unittest.main()
