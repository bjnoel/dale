"""
Loquat growing-guide tests (tools/scrapers/growing_guides/loquat.json).

Loquat gets its OWN climate category rather than inheriting "subtropical". It flowers
in autumn and ripens in late winter to spring (the reverse of most fruit trees), so the
limiter is frost on the BLOSSOM, not tree hardiness (the tree takes about -10C). The
generic subtropical note is wrong twice over: it implies the tree is frost-tender and
marginal in the cool south (it is hardy and widely grown in Melbourne), and it implies
the usual WA quarantine wall (loquat is a permitted WA plant with no loquat-specific
restriction). Every state gets a real, distinct overlay. Further reading carries the
WANATCA loquat article (Schroeder) plus the auto-merged RFCA archive links.

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

LOQUAT_SPECIES = {
    "common_name": "Loquat",
    "latin_name": "Eriobotrya japonica",
    "description": "Generic loquat blurb that should be replaced by the rich guide.",
    "slug": "loquat",
}


def _loquat_products(n=8):
    # Named varieties that are actually in live Australian nursery stock (Daleys,
    # Ladybird, Ross Creek, Fruitopia): Bessell Brown, Nagasakiwase, Champagne,
    # Enormity, Herds Mammoth, Honey Dew, Sewells Prolific, plus seedlings.
    names = ["Bessell Brown", "Nagasakiwase", "Champagne", "Enormity",
             "Herds Mammoth", "Honey Dew", "Sewells Prolific", "Seedling"]
    return [
        {"title": f"Loquat {names[i % len(names)]}",
         "url": f"https://nursery.example/loquat-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 44.0 + i * 5,
         "available": True, "species": LOQUAT_SPECIES}
        for i in range(n)
    ]


LOQUAT_PAGES = build_state_pages("loquat", _loquat_products())
LOQUAT_JSON = load_guide("loquat")

# Region tokens unique to one state (the leak guard relies on this). Each appears
# only in its own state's overlay, never in the core, the climate note, or another
# state's overlay.
LOQUAT_REGION_TOKENS = {
    "WA": ["Swan Valley", "Perth Hills"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Hawkesbury", "Central Coast"],
    "VIC": ["Mornington Peninsula", "Gippsland"],
}


class LoquatGuideTests(unittest.TestCase):
    """Each state page genuinely unique, dash-free, cited, FAQ-rich; dedicated climate."""

    def _faq_jsonld(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    # --- build + layout ---
    def test_pages_build_nonempty(self):
        for st, html in LOQUAT_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} loquat page too small")

    def test_canonical_and_og(self):
        wa = LOQUAT_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-loquat-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the guide.
        wa = LOQUAT_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Loquat in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in LOQUAT_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Loquat in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(LOQUAT_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two loquat state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in LOQUAT_REGION_TOKENS.items():
            self.assertTrue(any(t in LOQUAT_PAGES[st] for t in tokens),
                            f"{st} loquat page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in LOQUAT_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, LOQUAT_PAGES[other],
                                     f"{owner} loquat token '{t}' leaked onto {other} page")

    def test_generic_blurb_replaced(self):
        for st, html in LOQUAT_PAGES.items():
            self.assertNotIn("Generic loquat blurb", html, f"{st} still shows the blurb")

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in LOQUAT_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on loquat {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on loquat {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, LOQUAT_JSON, "loquat.json")

    # --- FAQ JSON-LD ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(LOQUAT_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(LOQUAT_JSON["core"]["faqs"]) + len(LOQUAT_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    # --- sources ---
    def test_sources_present_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', LOQUAT_PAGES[st], f"{st} missing Sources")
        for s in LOQUAT_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in LOQUAT_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "rfcarchives.org.au",
                "wanatca.org.au", "hgic.clemson.edu",
            )),
            "expected at least one gov/archive/authority source among the loquat sources",
        )

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', LOQUAT_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in LOQUAT_JSON["sources"]}
        cited = set()
        for block in [LOQUAT_JSON["core"]] + list(LOQUAT_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "loquat guide cites an unknown source id")

    # --- internal links ---
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', LOQUAT_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    # --- further reading (WANATCA loquat article + auto-merged RFCA owned archives) ---
    def test_further_reading_present_and_owned_followed(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("loquat"))
        for st in STATES:
            self.assertIn('id="further-reading"', LOQUAT_PAGES[st], f"{st} missing Further reading")
        fr = self._fr(LOQUAT_PAGES["WA"])
        self.assertIn("wanatca.org.au", fr, "loquat Further reading missing WANATCA")
        self.assertIn("rfcarchives.org.au", fr, "loquat Further reading missing RFCA")
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_count_matches_merged(self):
        merged = gg.get_further_reading("loquat")
        self.assertGreaterEqual(len(merged), len(LOQUAT_JSON.get("further_reading", [])))
        self.assertEqual(self._fr(LOQUAT_PAGES["WA"]).count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("loquat").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("loquat", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    # --- climate: loquat has its OWN category, not "subtropical" ---
    def test_loquat_climate_category_is_dedicated(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["loquat"], "loquat",
                         "loquat must not inherit the subtropical climate note")
        for st in STATES:
            note = bssp.get_climate_note("Loquat", st)
            self.assertIn("loquat", note.lower(), f"{st} loquat climate note should mention loquats")
            self.assertNotIn("Chilling hours may be lower", note,
                             "loquat should not inherit the stone/pome-fruit chill-hours note")

    def test_wa_note_carries_the_permitted_plant_nuance(self):
        # The bug we avoid: the old "subtropical" WA note implied the usual quarantine
        # wall. Loquat is a permitted WA plant with no loquat-specific restriction.
        note = bssp.get_climate_note("Loquat", "WA")
        self.assertIn("permitted", note, "WA note should state loquat is a permitted WA plant")

    def test_vic_note_does_not_call_loquat_marginal(self):
        # The old "subtropical" VIC note implied subtropical trees are frost-tender and
        # that nurseries will not ship to VIC. Loquat the tree is hardy and widely grown.
        note = bssp.get_climate_note("Loquat", "VIC")
        self.assertIn("hardy", note, "VIC note should state loquat is hardy")
        self.assertNotIn("sheltered, north-facing positions", note)
        self.assertNotIn("do not ship to VIC", note)

    # --- correctness guards specific to loquat ---
    def test_self_fertile_one_tree_no_false_pollinator_claim(self):
        # A grower most needs to know loquats are self-fertile (one tree crops).
        for st, html in LOQUAT_PAGES.items():
            self.assertIn("self-fertile", html, f"{st} missing the self-fertile fact")
            self.assertIn("One tree will fruit", html, f"{st} missing the pollination section")
            self.assertNotIn("must have a pollinator", html, f"{st} wrongly claims a pollinator is needed")
            self.assertNotIn("need a second tree", html, f"{st} wrongly claims a second tree is needed")

    def test_autumn_winter_flowering_story_present(self):
        # The defining loquat fact: it flowers in autumn/winter and the frost risk is to
        # the blossom, not the tree. Every page must carry this (it is the core FAQ).
        for st, html in LOQUAT_PAGES.items():
            self.assertIn("autumn and winter", html, f"{st} missing the autumn/winter flowering story")

    def test_birds_flagged_and_netting(self):
        # Birds (and netting) are a headline loquat challenge; every page must say so.
        for st, html in LOQUAT_PAGES.items():
            self.assertIn("bird", html.lower(), f"{st} page does not mention birds")
            self.assertIn("net", html.lower(), f"{st} page does not mention netting")

    def test_wa_medfly_host_and_permitted_shipping(self):
        wa = LOQUAT_PAGES["WA"]
        self.assertIn("Mediterranean fruit fly", wa, "WA page must flag medfly")
        self.assertIn("susceptible", wa, "WA page should state loquat is a susceptible medfly host")
        self.assertIn("permitted plant", wa, "WA page should explain loquat's permitted WA status")

    def test_qld_tropics_fruit_poorly_story(self):
        qld = LOQUAT_PAGES["QLD"]
        self.assertIn("ornamental", qld, "QLD page should explain loquat fruits poorly in the humid tropics")
        self.assertIn("tropical", qld.lower(), "QLD page should mention the tropics")

    def test_thinning_section_present(self):
        # Thinning to a few fruit per cluster is the job that makes loquats worthwhile;
        # it is a core section, so it appears on every page.
        for st, html in LOQUAT_PAGES.items():
            self.assertIn("Thinning for size", html, f"{st} missing the thinning section")


if __name__ == "__main__":
    unittest.main()
