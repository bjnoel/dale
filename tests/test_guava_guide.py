"""
Tests for the guava growing guide (tools/scrapers/growing_guides/guava.json) as
rendered onto the buy-guava-trees-<state> SEO combo pages by
build_species_state_pages.py + the shared growing_guides.py content layer.

This mirrors the guarantees in test_species_state_pages.py (which pins olive) for
the second shipped species: each state's page is genuinely UNIQUE, the copy rules
hold (no em or en dashes), the cited Sources and FAQ JSON-LD are present, internal
/species/ links resolve, and the WANATCA/RFCA Further reading merges correctly
(owned links followed, third-party rarefruitclub nofollow).

It is a separate file (not appended to test_species_state_pages.py) so it stays
green independently as more species are added.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bssp = _load(SCRAPERS / "build_species_state_pages.py")
gg = _load(SCRAPERS / "growing_guides.py")

EM_DASH = "—"
EN_DASH = "–"
STATES = ["WA", "QLD", "NSW", "VIC"]
TODAY = "2026-06-02"

GUAVA_SPECIES = {
    "common_name": "Guava",
    "latin_name": "Psidium guajava",
    "description": "Generic guava blurb that should be replaced by the rich guide.",
    "slug": "guava",
}

# A spread of cultivars actually seen in the live stock table, so the test
# exercises real product titles (incl. a dash that must be sanitised).
_GUAVA_TITLES = [
    "Guava - Hawaiian", "Guava Mexican Cream", "Guava - China Pear",
    "Guava Thai Pink", "Guava Indian (Amman)", "Strawberry Guava",
]


def _guava_products(n=6):
    return [
        {
            "title": _GUAVA_TITLES[i % len(_GUAVA_TITLES)],
            "url": f"https://nursery.example/guava-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 15.0 + i * 5,
            "available": True,
            "species": GUAVA_SPECIES,
        }
        for i in range(n)
    ]


PAGES = {st: bssp.build_combo_page(st, "guava", _guava_products(), TODAY) for st in STATES}
GUAVA_JSON = json.loads((SCRAPERS / "growing_guides" / "guava.json").read_text(encoding="utf-8"))
VALID_SLUGS = {s["slug"] for s in json.loads((SCRAPERS / "fruit_species.json").read_text()) if s.get("slug")}

# State-specific region tokens that must appear on exactly one state's page.
STATE_REGION_TOKENS = {
    "WA": ["Carnarvon", "Kununurra", "Kimberley"],
    "QLD": ["Atherton", "Bundaberg", "wet tropics"],
    "NSW": ["Northern Rivers", "Tweed", "Coffs Harbour"],
    "VIC": ["Sunraysia", "Mildura", "Goulburn"],
}


class BuildTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} page too small")

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("guava"))

    def test_generic_blurb_replaced(self):
        for st, html in PAGES.items():
            self.assertNotIn("Generic guava blurb", html, f"{st} still shows the fallback blurb")

    def test_canonical_and_article_og(self):
        wa = PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-guava-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_guide(self):
        wa = PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Guava in Western Australia"),
                        "stock table must precede the editorial guide (above-the-fold rule)")

    def test_treesmith_promo_below_guide(self):
        for st, html in PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Guava in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")


class PerStateUniquenessTests(unittest.TestCase):
    def test_state_pages_mutually_distinct(self):
        bodies = list(PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two guava state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in STATE_REGION_TOKENS.items():
            self.assertTrue(any(t in PAGES[st] for t in tokens),
                            f"{st} page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in STATE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, PAGES[other],
                                     f"{owner} token '{t}' leaked onto {other} page")

    def test_correct_fruit_fly_species_per_state(self):
        # The single most error-prone fact: WA = Medfly (Qfly not established),
        # eastern states = Queensland fruit fly. Guard it so it can never drift.
        self.assertIn("Mediterranean fruit fly", PAGES["WA"])
        self.assertIn("not established in WA", PAGES["WA"])
        for st in ("QLD", "NSW", "VIC"):
            self.assertIn("Queensland fruit fly", PAGES[st], f"{st} should name Queensland fruit fly")
        # WA must not claim Qfly is a local established pest.
        self.assertNotIn("Mediterranean fruit fly", PAGES["QLD"])

    def test_state_full_name_in_guide(self):
        for st in STATES:
            self.assertIn(bssp.STATE_FULL_NAMES[st], PAGES[st])


class CopyRuleTests(unittest.TestCase):
    def test_no_dashes_in_pages(self):
        for st, html in PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} page")

    def test_no_dashes_in_guide_json(self):
        def scan(obj, path="guava.json"):
            if isinstance(obj, str):
                self.assertNotIn(EM_DASH, obj, f"em dash in {path}")
                self.assertNotIn(EN_DASH, obj, f"en dash in {path}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    scan(v, f"{path}[{i}]")
        scan(GUAVA_JSON)

    def test_product_title_dash_sanitised(self):
        # "Guava - Hawaiian" uses a hyphen; an en/em dash in a title must be stripped.
        prods = _guava_products(1)
        prods[0]["title"] = "Guava – Hawaiian — Pink"
        html = bssp.build_combo_page("QLD", "guava", prods, TODAY)
        self.assertIn("Guava - Hawaiian - Pink", html)
        self.assertNotIn(EM_DASH, html)
        self.assertNotIn(EN_DASH, html)


class ClimateNoteTests(unittest.TestCase):
    def test_guava_is_subtropical(self):
        # Guava fits the existing subtropical climate bucket; the rich per-state
        # overlay carries the real nuance, so no new category was needed.
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["guava"], "subtropical")

    def test_climate_note_present_and_clean(self):
        note = bssp.get_climate_note("Guava", "WA")
        self.assertTrue(note)
        self.assertNotIn(EM_DASH, note)
        self.assertNotIn(EN_DASH, note)


class FaqJsonLdTests(unittest.TestCase):
    def _extract(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def test_faq_jsonld_parses_each_state(self):
        for st in STATES:
            data = self._extract(PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(GUAVA_JSON["core"]["faqs"]) + len(GUAVA_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])


class SourcesTests(unittest.TestCase):
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', PAGES[st], f"{st} missing Sources section")

    def test_reference_links_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_all_sources_https(self):
        for s in GUAVA_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_sources_include_gov_authorities(self):
        domains = " ".join(s["url"] for s in GUAVA_JSON["sources"])
        for d in ("dpird.wa.gov.au", "business.qld.gov.au", "agriculture.gov.au"):
            self.assertIn(d, domains, f"expected {d} among guava sources")

    def test_every_cited_id_resolves(self):
        src_ids = {s["id"] for s in GUAVA_JSON["sources"]}
        cited = set()
        for block in [GUAVA_JSON["core"]] + list(GUAVA_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "guide cites an unknown source id")

    def test_sources_note_is_guava_specific_not_olive(self):
        wa = PAGES["WA"]
        self.assertIn("Rare Fruit Council of Australia archive", wa)
        self.assertNotIn("olive-industry", wa)


class SpeciesLinkTests(unittest.TestCase):
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_feijoa_crosslink_present(self):
        # Feijoa (a real species page) is the cold-hardy alternative we point to.
        self.assertIn("/species/feijoa.html", PAGES["VIC"])


class FurtherReadingTests(unittest.TestCase):
    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    def test_present_on_every_state_and_species_guide(self):
        for st in STATES:
            self.assertIn('id="further-reading"', PAGES[st], f"{st} missing Further reading")
        self.assertIn('id="further-reading"', gg.render_species_guide("guava"))

    def test_links_include_owned_rfca_archive(self):
        fr = self._fr(PAGES["QLD"])
        self.assertIn("rfcarchives.org.au/Next/Fruits/Guava", fr)

    def test_owned_links_followed_thirdparty_nofollow(self):
        fr = self._fr(PAGES["QLD"])
        for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr):
            if "rfcarchives.org.au" in url or "wanatca.org.au" in url:
                self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
            if "rarefruitclub.au" in url:
                self.assertIn("nofollow", attrs, f"third-party rarefruitclub must be nofollow: {url}")

    def test_count_matches_merged(self):
        merged = gg.get_further_reading("guava")
        self.assertGreaterEqual(len(merged), len(GUAVA_JSON.get("further_reading", [])))
        self.assertEqual(self._fr(PAGES["QLD"]).count("<li>"), len(merged))


class GrowingGuidesModuleTests(unittest.TestCase):
    def test_combo_guide_has_overlay_then_core(self):
        qld = gg.render_combo_guide("guava", "QLD")
        self.assertIn("Where guava grows in QLD", qld)   # overlay
        self.assertIn("Choosing a variety", qld)         # core
        self.assertLess(qld.index("Where guava grows in QLD"), qld.index("Choosing a variety"))

    def test_species_guide_has_core_without_overlay(self):
        sp = gg.render_species_guide("guava")
        self.assertIn("Choosing a variety", sp)
        self.assertNotIn("Where guava grows in QLD", sp)


if __name__ == "__main__":
    unittest.main()
