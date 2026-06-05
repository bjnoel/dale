#!/usr/bin/env python3
"""
Lilly pilly growing-guide tests (tools/scrapers/growing_guides/lilly-pilly.json).

Lilly pilly gets its OWN climate category rather than inheriting "subtropical". It is a
hardy Australian native (Syzygium / former Acmena) grown chiefly as an evergreen hedge
plus a secondary bush food, so the generic subtropical note is wrong twice over: it
implies the plant is frost-tender and marginal in the cool south (it is hardy and the
default hedge plant across Victoria), and it implies the usual "a handful of eastern
nurseries can ship to WA" framing when the truth is the OPPOSITE of free: lilly pilly is
a MYRTLE, and WA restricts myrtle-family plants to keep out myrtle rust, so live plants
essentially cannot be posted in (the banana pattern). Every state gets a real, distinct
overlay. Further reading carries the WANATCA Wilson Y14 article plus owned RFCA links
(there is no RFCA lilly-pilly folder, so archive_links.json is unchanged and the links
are hand-curated, like tamarillo/custard-apple).

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

LILLY_PILLY_SPECIES = {
    "common_name": "Lilly Pilly",
    "latin_name": "Syzygium luehmannii",
    "description": "Generic lilly pilly blurb that should be replaced by the rich guide.",
    "slug": "lilly-pilly",
}


def _lilly_pilly_products(n=10):
    # Named forms that are actually in live Australian nursery stock (Ladybird, Daleys,
    # Guildford, Diggers): resistant Syzygium australe selections, the resistant former
    # Acmena (Syzygium smithii) cultivars, and the bush-food riberry.
    names = ["Resilience", "Backyard Bliss", "Big Red", "Bush Christmas",
             "Riberry", "Aussie Compact", "Firescreen", "Slim Jim",
             "Minnie Magic", "Cherry Surprise"]
    return [
        {"title": f"Lilly Pilly {names[i % len(names)]}",
         "url": f"https://nursery.example/lilly-pilly-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 18.0 + i * 4,
         "available": True, "species": LILLY_PILLY_SPECIES}
        for i in range(n)
    ]


LILLY_PILLY_PAGES = build_state_pages("lilly-pilly", _lilly_pilly_products())
LILLY_PILLY_JSON = load_guide("lilly-pilly")

# Region tokens unique to one state (the leak guard relies on this). Each appears only in
# its own state's overlay, never in the core, the climate note, or another state's overlay.
LILLY_PILLY_REGION_TOKENS = {
    "WA": ["Swan Coastal Plain", "Margaret River", "Mandurah"],
    "QLD": ["Sunshine Coast", "Atherton Tableland", "Scenic Rim"],
    "NSW": ["Northern Rivers", "Jervis Bay", "Coffs Harbour"],
    "VIC": ["East Gippsland", "Wilsons Promontory", "Mornington Peninsula"],
}


class LillyPillyGuideTests(unittest.TestCase):
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
        for st, html in LILLY_PILLY_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} lilly pilly page too small")

    def test_canonical_and_og(self):
        wa = LILLY_PILLY_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-lilly-pilly-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the guide.
        wa = LILLY_PILLY_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Lilly Pilly in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in LILLY_PILLY_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Lilly Pilly in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    # --- per-state uniqueness ---
    def test_state_pages_mutually_distinct(self):
        bodies = list(LILLY_PILLY_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two lilly pilly state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in LILLY_PILLY_REGION_TOKENS.items():
            self.assertTrue(any(t in LILLY_PILLY_PAGES[st] for t in tokens),
                            f"{st} lilly pilly page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in LILLY_PILLY_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, LILLY_PILLY_PAGES[other],
                                     f"{owner} lilly pilly token '{t}' leaked onto {other} page")

    def test_generic_blurb_replaced(self):
        for st, html in LILLY_PILLY_PAGES.items():
            self.assertNotIn("Generic lilly pilly blurb", html, f"{st} still shows the blurb")

    # --- copy rules ---
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in LILLY_PILLY_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on lilly pilly {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on lilly pilly {st} page")

    def test_no_dashes_in_guide_json(self):
        assert_no_dashes(self, LILLY_PILLY_JSON, "lilly-pilly.json")

    # --- FAQ JSON-LD ---
    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._faq_jsonld(LILLY_PILLY_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(LILLY_PILLY_JSON["core"]["faqs"]) + len(LILLY_PILLY_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    # --- sources ---
    def test_sources_present_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', LILLY_PILLY_PAGES[st], f"{st} missing Sources")
        for s in LILLY_PILLY_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in LILLY_PILLY_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "dcceew.gov.au",
                "rfcarchives.org.au", "wanatca.org.au",
            )),
            "expected at least one gov/archive/authority source among the lilly pilly sources",
        )

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', LILLY_PILLY_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in LILLY_PILLY_JSON["sources"]}
        cited = set()
        for block in [LILLY_PILLY_JSON["core"]] + list(LILLY_PILLY_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "lilly pilly guide cites an unknown source id")
        # Every declared source is actually used (else it never renders in References).
        self.assertEqual(src_ids - cited, set(), "lilly pilly guide declares an uncited source")

    # --- internal links ---
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', LILLY_PILLY_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")
        # "riberry" is part of lilly pilly, not its own species page; never link it.
        self.assertNotIn("/species/riberry.html", LILLY_PILLY_PAGES["NSW"])

    # --- further reading (WANATCA Wilson Y14 + owned RFCA; hand-curated, no RFCA folder) ---
    def test_further_reading_present_and_owned_followed(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("lilly-pilly"))
        for st in STATES:
            self.assertIn('id="further-reading"', LILLY_PILLY_PAGES[st], f"{st} missing Further reading")
        fr = self._fr(LILLY_PILLY_PAGES["WA"])
        self.assertIn("wanatca.org.au", fr, "lilly pilly Further reading missing WANATCA")
        self.assertIn("rfcarchives.org.au", fr, "lilly pilly Further reading missing RFCA")
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_count_matches_merged(self):
        merged = gg.get_further_reading("lilly-pilly")
        self.assertGreaterEqual(len(merged), len(LILLY_PILLY_JSON.get("further_reading", [])))
        self.assertEqual(self._fr(LILLY_PILLY_PAGES["WA"]).count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("lilly-pilly").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("lilly-pilly", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")

    # --- climate: lilly pilly has its OWN category, not "subtropical" ---
    def test_lilly_pilly_climate_category_is_dedicated(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["lilly pilly"], "lilly-pilly",
                         "lilly pilly must not inherit the subtropical climate note")
        for st in STATES:
            note = bssp.get_climate_note("Lilly Pilly", st)
            self.assertIn("lilly pilly", note.lower(), f"{st} climate note should mention lilly pilly")
            self.assertNotIn("Chilling hours may be lower", note,
                             "lilly pilly should not inherit the stone/pome-fruit chill-hours note")

    def test_wa_note_carries_the_myrtle_import_nuance(self):
        # The bug we avoid: the old "subtropical" WA note implied "a handful of eastern
        # nurseries can ship here". Lilly pilly is a myrtle and WA restricts myrtle-family
        # plants to keep out myrtle rust, so the real story is the opposite of free.
        note = bssp.get_climate_note("Lilly Pilly", "WA")
        self.assertIn("myrtle", note.lower(), "WA note should explain the myrtle / myrtle rust angle")

    # --- correctness guards specific to lilly pilly ---
    def test_psyllid_resistance_is_the_headline(self):
        # The make-or-break buying fact: pick a psyllid-resistant species or selection.
        for st, html in LILLY_PILLY_PAGES.items():
            self.assertIn("psyllid", html.lower(), f"{st} missing the psyllid story")
            self.assertIn("resistan", html.lower(), f"{st} missing psyllid resistance advice")

    def test_one_plant_fruits_no_false_pollinator_claim(self):
        # Lilly pillies are self-fertile: one plant crops. Do not invent a pollinator need.
        for st, html in LILLY_PILLY_PAGES.items():
            self.assertIn("single plant will set fruit", html, f"{st} missing the self-fertile fact")
            self.assertIn("you do not need to buy two", html.lower(),
                          f"{st} should reassure that one plant is enough")
            self.assertNotIn("must have a pollinator", html.lower(), f"{st} wrongly requires a pollinator")
            self.assertNotIn("need a second tree", html.lower(), f"{st} wrongly requires a second tree")

    def test_berries_are_edible_and_non_toxic(self):
        for st, html in LILLY_PILLY_PAGES.items():
            self.assertIn("poisonous", html.lower(), f"{st} should state the berries are not poisonous")
        # The defining bush food is the riberry; it appears on every page (core section).
        for st, html in LILLY_PILLY_PAGES.items():
            self.assertIn("riberry", html.lower(), f"{st} missing the riberry bush-food story")

    def test_not_phosphorus_sensitive(self):
        # Correctness: lilly pillies are Myrtaceae, NOT Proteaceae, so they take ordinary
        # phosphorus and do not need a low-P "native" fertiliser. The core feeding section
        # carries this on every page.
        for st, html in LILLY_PILLY_PAGES.items():
            self.assertIn("phosphorus", html.lower(), f"{st} missing the phosphorus feeding nuance")

    def test_myrtle_rust_on_every_combo_page(self):
        # Myrtle rust is the headline disease of the myrtle family; each state's overlay
        # addresses it (east coast established; WA kept out).
        for st, html in LILLY_PILLY_PAGES.items():
            self.assertIn("myrtle rust", html.lower(), f"{st} should address myrtle rust")

    def test_wa_kept_myrtle_rust_free_and_medfly_non_host(self):
        wa = LILLY_PILLY_PAGES["WA"]
        self.assertIn("import conditions", wa, "WA page must explain the myrtle import restriction")
        self.assertIn("Mediterranean fruit fly", wa, "WA page should name the WA fruit fly")
        self.assertIn("not on its list of host fruits", wa,
                      "WA page should state lilly pilly is not a Medfly host")

    def test_east_coast_qff_is_a_recorded_host(self):
        # Distinct from WA: in the east, Queensland fruit fly IS a recorded host of the berries.
        for st in ("NSW", "QLD"):
            self.assertIn("Queensland fruit fly", LILLY_PILLY_PAGES[st], f"{st} should flag Qfly")

    def test_nsw_magenta_lilly_pilly_endemic_story(self):
        nsw = LILLY_PILLY_PAGES["NSW"]
        self.assertIn("magenta lilly pilly", nsw.lower(), "NSW page missing the magenta lilly pilly")
        self.assertIn("endangered", nsw.lower(), "NSW page should note its threatened status")

    def test_vic_hardiness_and_frost_story(self):
        vic = LILLY_PILLY_PAGES["VIC"]
        self.assertIn("frost", vic.lower(), "VIC page should discuss frost")
        self.assertIn("hardy", vic.lower(), "VIC page should state the common lilly pilly is hardy")


if __name__ == "__main__":
    unittest.main()
