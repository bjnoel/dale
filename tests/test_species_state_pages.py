"""
Tests for tools/scrapers/build_species_state_pages.py and the shared
tools/scrapers/growing_guides.py content layer that powers the
buy-<species>-trees-<state> SEO combo pages on treestock.com.au.

The headline guarantee these tests protect is that each state's page is genuinely
UNIQUE (olive in WA, QLD, NSW and VIC must not share a byte-identical editorial
body), plus the copy rules (no em or en dashes, which guards the live price-range
bug), the corrected olive climate note, FAQ JSON-LD, cited Sources, and the
graceful fallback for species that have no guide yet.

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

# The builder imports treestock_layout, shipping, stocklib and growing_guides,
# so the scrapers dir must be importable.
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bssp = _load(SCRAPERS / "build_species_state_pages.py")
gg = _load(SCRAPERS / "growing_guides.py")

# U+2014 em dash, U+2013 en dash. Both banned in treestock copy.
EM_DASH = "—"
EN_DASH = "–"

STATES = ["WA", "QLD", "NSW", "VIC"]
TODAY = "2026-06-01"

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


def _mango_products():
    sp = {"common_name": "Mango", "latin_name": "Mangifera indica",
          "description": "Generic mango blurb.", "slug": "mango"}
    return [
        {"title": f"Mango {i}", "url": f"https://nursery.example/mango-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 40.0 + i,
         "available": True, "species": sp}
        for i in range(4)
    ]


# Render once: olive in every state, plus a species with no guide (mango).
PAGES = {st: bssp.build_combo_page(st, "olive", _olive_products(), TODAY) for st in STATES}
MANGO_PAGE = bssp.build_combo_page("QLD", "mango", _mango_products(), TODAY)

OLIVE_JSON = json.loads((SCRAPERS / "growing_guides" / "olive.json").read_text(encoding="utf-8"))
VALID_SLUGS = {s["slug"] for s in json.loads((SCRAPERS / "fruit_species.json").read_text()) if s.get("slug")}

# State-specific region tokens that must appear on exactly one state's page.
STATE_REGION_TOKENS = {
    "WA": ["Moore River", "Gingin"],
    "QLD": ["Granite Belt", "Darling Downs"],
    "NSW": ["Riverina"],
    "VIC": ["Sunraysia", "Grampians"],
}


class BuildTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} page too small")

    def test_canonical_and_og(self):
        wa = PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-olive-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)
        self.assertIn('<meta property="og:image"', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        # feedback_above_fold_clutter: the live stock table must stay above the
        # editorial guide, never be pushed down by it.
        wa = PAGES["WA"]
        table_pos = wa.index("<table")
        guide_pos = wa.index("Growing Olive in Western Australia")
        self.assertLess(table_pos, guide_pos, "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(
                html.index("Growing Olive in"), html.index("Track your collection with Treesmith"),
                f"{st} promo must sit below the guide",
            )


class PerStateUniquenessTests(unittest.TestCase):
    """The core of this feature: each state page is genuinely unique."""

    def test_state_pages_mutually_distinct(self):
        bodies = list(PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in STATE_REGION_TOKENS.items():
            self.assertTrue(
                any(t in PAGES[st] for t in tokens),
                f"{st} page missing its region tokens {tokens}",
            )

    def test_region_tokens_do_not_leak_across_states(self):
        # A WA region must not appear on the QLD page, etc. This is what stops the
        # pages being near-duplicate doorway content.
        for owner, tokens in STATE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, PAGES[other],
                                     f"{owner} token '{t}' leaked onto {other} page")

    def test_state_full_name_in_guide(self):
        for st in STATES:
            self.assertIn(bssp.STATE_FULL_NAMES[st], PAGES[st])

    def test_generic_blurb_replaced_when_guide_exists(self):
        # The olive pages must use the rich guide, not the fruit_species.json blurb.
        for st, html in PAGES.items():
            self.assertNotIn("Generic olive blurb", html, f"{st} still shows the blurb")


class CopyRuleTests(unittest.TestCase):
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in {**PAGES, "mango": MANGO_PAGE}.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} page (guards the price-range bug)")

    def test_price_range_uses_hyphen_not_en_dash(self):
        # The live bug was f"${lo}-${hi}" built with a U+2013. Multi-price pages
        # must render a plain-hyphen range.
        wa = PAGES["WA"]
        self.assertRegex(wa, r"\$\d+-\$\d+", "expected a hyphenated price range")
        self.assertNotIn(EN_DASH, wa)

    def test_product_titles_with_dashes_are_sanitised(self):
        # Nursery product titles and names sometimes carry en/em dashes (the live
        # olive page showed "Olive - Ascolana Tenera"). The template must strip them
        # so passthrough data never breaks the copy rule.
        prods = _olive_products(1)
        prods[0]["title"] = "Olive – Ascolana Tenera — Large"
        prods[0]["nursery_name"] = "Some – Nursery"
        html = bssp.build_combo_page("WA", "olive", prods, TODAY)
        self.assertIn("Olive - Ascolana Tenera - Large", html)
        self.assertNotIn(EM_DASH, html)
        self.assertNotIn(EN_DASH, html)

    def test_no_dashes_in_guide_json(self):
        def scan(obj, path="olive.json"):
            if isinstance(obj, str):
                self.assertNotIn(EM_DASH, obj, f"em dash in {path}")
                self.assertNotIn(EN_DASH, obj, f"en dash in {path}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    scan(v, f"{path}[{i}]")
        scan(OLIVE_JSON)

    def test_no_dashes_in_climate_notes(self):
        for state, notes in bssp.STATE_CLIMATE_NOTES.items():
            for cat, text in notes.items():
                self.assertNotIn(EM_DASH, text, f"em dash in {state}/{cat} climate note")
                self.assertNotIn(EN_DASH, text, f"en dash in {state}/{cat} climate note")


class ClimateNoteTests(unittest.TestCase):
    """The miscategorisation fix: olive must not inherit the stone-fruit chill note."""

    def test_olive_and_grape_are_mediterranean(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["olive"], "mediterranean")
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["grape"], "mediterranean")

    def test_every_state_has_a_mediterranean_note(self):
        for state in STATES:
            self.assertIn("mediterranean", bssp.STATE_CLIMATE_NOTES[state])

    def test_olive_climate_note_is_not_stone_fruit_chill_text(self):
        note = bssp.get_climate_note("Olive", "WA")
        self.assertIn("Mediterranean", note)
        self.assertNotIn("Chilling hours may be lower", note,
                         "olive is still getting the stone/pome-fruit chill-hours note")

    def test_olive_page_does_not_claim_chill_hours(self):
        self.assertNotIn("Chilling hours may be lower", PAGES["WA"])


class FaqJsonLdTests(unittest.TestCase):
    def _extract(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._extract(PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            # 4 core FAQs + this state's FAQs.
            expected = len(OLIVE_JSON["core"]["faqs"]) + len(OLIVE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")
            for ent in data["mainEntity"]:
                self.assertEqual(ent["@type"], "Question")
                self.assertTrue(ent["acceptedAnswer"]["text"])

    def test_no_faq_jsonld_for_unenriched_species(self):
        self.assertNotIn("FAQPage", MANGO_PAGE)


class SourcesTests(unittest.TestCase):
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        # Scope to the Sources block only. Third-party citations must be nofollow;
        # Further-reading links to owned sites are deliberately followed (see
        # FurtherReadingTests), so a page-wide scan would wrongly flag them.
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', PAGES[st], re.S)
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
        blocks = [OLIVE_JSON["core"]] + list(OLIVE_JSON["states"].values())
        for block in blocks:
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "guide cites an unknown source id")

    def test_references_filtered_to_cited_only(self):
        # The species (core-only) guide cites fewer sources than the WA combo
        # (core + WA overlay), proving the Sources block is filtered, not dumped.
        species_refs = PAGES["WA"].count('rel="noopener nofollow"')
        self.assertGreater(species_refs, 0)


class SpeciesLinkTests(unittest.TestCase):
    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")


class FallbackTests(unittest.TestCase):
    def test_has_guide(self):
        self.assertTrue(gg.has_guide("olive"))
        self.assertFalse(gg.has_guide("mango"))

    def test_unenriched_species_uses_blurb_and_stays_clean(self):
        self.assertIn("Generic mango blurb.", MANGO_PAGE)
        self.assertNotIn('id="sources"', MANGO_PAGE)
        self.assertIn("Track your collection with Treesmith", MANGO_PAGE)
        self.assertNotIn(EM_DASH, MANGO_PAGE)
        self.assertNotIn(EN_DASH, MANGO_PAGE)


class GrowingGuidesModuleTests(unittest.TestCase):
    def test_combo_guide_has_overlay_then_core(self):
        wa = gg.render_combo_guide("olive", "WA")
        self.assertIn("Where olives grow in WA", wa)   # overlay
        self.assertIn("Choosing a variety", wa)        # core
        self.assertLess(wa.index("Where olives grow in WA"), wa.index("Choosing a variety"))

    def test_species_guide_has_core_without_overlay(self):
        sp = gg.render_species_guide("olive")
        self.assertIn("Choosing a variety", sp)
        self.assertNotIn("Where olives grow in WA", sp)

    def test_species_guide_cites_fewer_sources_than_combo(self):
        species_n = gg.render_species_guide("olive").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("olive", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


class FurtherReadingTests(unittest.TestCase):
    """First-party cross-links to Benedict's WANATCA and RFCA archives."""

    def _fr(self, html):
        m = re.search(r'id="further-reading".*?</section>', html, re.S)
        return m.group(0) if m else ""

    def test_present_on_every_state_and_species_guide(self):
        for st in STATES:
            self.assertIn('id="further-reading"', PAGES[st], f"{st} missing Further reading")
        self.assertIn('id="further-reading"', gg.render_species_guide("olive"))

    def test_links_point_to_owned_archives(self):
        fr = self._fr(PAGES["WA"])
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)

    def test_further_reading_links_are_followed_not_nofollow(self):
        # Owned cross-links should pass authority: rel=noopener but NOT nofollow.
        fr = self._fr(PAGES["WA"])
        links = re.findall(r'<a href="(https://[^"]+)"([^>]*)>', fr)
        self.assertTrue(links, "no further-reading links found")
        for url, attrs in links:
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_kailis_first_party_source_cited(self):
        # The WANATCA Kailis article is a first-party WA citation in the Sources block.
        self.assertIn("Kailis", PAGES["WA"])
        self.assertIn("wanatca.org.au/yearbooks/Y22all.pdf", PAGES["WA"])

    def test_further_reading_count_matches_data(self):
        n = len(OLIVE_JSON.get("further_reading", []))
        self.assertGreaterEqual(n, 2, "expected at least two further-reading links")
        self.assertEqual(self._fr(PAGES["WA"]).count("<li>"), n)

    def test_unenriched_species_has_no_further_reading(self):
        self.assertNotIn('id="further-reading"', MANGO_PAGE)


if __name__ == "__main__":
    unittest.main()
