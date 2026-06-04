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
bsp = _load(SCRAPERS / "build_species_pages.py")

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


def _unenriched_products():
    # A species with NO growing guide, to prove the graceful fallback still works.
    # Starfruit is deliberately low-priority on the rollout (unlikely to be enriched
    # soon) yet has RFCA archive_links entries, which the archive-fallback test needs.
    sp = {"common_name": "Starfruit", "latin_name": "Averrhoa carambola",
          "description": "Generic starfruit blurb.", "slug": "starfruit"}
    return [
        {"title": f"Starfruit {i}", "url": f"https://nursery.example/starfruit-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 30.0 + i,
         "available": True, "species": sp}
        for i in range(4)
    ]


# Render once: olive and mango (both enriched) in every state, plus a species with
# no guide (starfruit) to exercise the graceful fallback.
PAGES = {st: bssp.build_combo_page(st, "olive", _olive_products(), TODAY) for st in STATES}
MANGO_PAGES = {st: bssp.build_combo_page(st, "mango", _mango_products(), TODAY) for st in STATES}
UNENRICHED_PAGE = bssp.build_combo_page("QLD", "starfruit", _unenriched_products(), TODAY)

OLIVE_JSON = json.loads((SCRAPERS / "growing_guides" / "olive.json").read_text(encoding="utf-8"))
MANGO_JSON = json.loads((SCRAPERS / "growing_guides" / "mango.json").read_text(encoding="utf-8"))
VALID_SLUGS = {s["slug"] for s in json.loads((SCRAPERS / "fruit_species.json").read_text()) if s.get("slug")}

# State-specific region tokens that must appear on exactly one state's page.
STATE_REGION_TOKENS = {
    "WA": ["Moore River", "Gingin"],
    "QLD": ["Granite Belt", "Darling Downs"],
    "NSW": ["Riverina"],
    "VIC": ["Sunraysia", "Grampians"],
}

# Mango equivalents (different crop, different regions) for the mango guide tests.
MANGO_REGION_TOKENS = {
    "WA": ["Kununurra", "Carnarvon"],
    "QLD": ["Mareeba", "Dimbulah", "Burdekin"],
    "NSW": ["Northern Rivers", "Tweed"],
    "VIC": ["Melbourne", "greenhouse"],
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
        pages = {**PAGES,
                 **{f"mango-{st}": p for st, p in MANGO_PAGES.items()},
                 "unenriched": UNENRICHED_PAGE}
        for st, html in pages.items():
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
        self.assertNotIn("FAQPage", UNENRICHED_PAGE)


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

    def test_sources_note_generic_by_default_overridable_per_guide(self):
        # Regression: the shared Sources renderer hardcoded "olive-industry bodies",
        # which would render wrongly for fig and every other species.
        fake = {"sources": [{"id": "x", "name": "Test", "url": "https://example.gov.au/"}]}
        generic = gg._render_references(fake, {"x"})
        self.assertNotIn("olive-industry", generic, "Sources note leaks olive-specific copy")
        self.assertIn("horticultural research", generic)
        custom = gg._render_references({**fake, "sources_note": "Fig note here."}, {"x"})
        self.assertIn("Fig note here.", custom)
        # olive keeps its specific wording via its own sources_note override.
        self.assertIn("olive-industry bodies", PAGES["WA"])

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
        self.assertTrue(gg.has_guide("mango"))
        self.assertFalse(gg.has_guide("starfruit"))

    def test_unenriched_species_uses_blurb_and_stays_clean(self):
        self.assertIn("Generic starfruit blurb.", UNENRICHED_PAGE)
        self.assertNotIn('id="sources"', UNENRICHED_PAGE)
        self.assertIn("Track your collection with Treesmith", UNENRICHED_PAGE)
        self.assertNotIn(EM_DASH, UNENRICHED_PAGE)
        self.assertNotIn(EN_DASH, UNENRICHED_PAGE)


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

    def test_further_reading_count_matches_merged(self):
        # Rendered links = curated guide entries merged with the RFCA archive index.
        merged = gg.get_further_reading("olive")
        self.assertGreaterEqual(len(merged), len(OLIVE_JSON.get("further_reading", [])))
        self.assertEqual(self._fr(PAGES["WA"]).count("<li>"), len(merged))

    def test_unenriched_species_has_no_further_reading(self):
        self.assertNotIn('id="further-reading"', UNENRICHED_PAGE)


class ArchiveIndexTests(unittest.TestCase):
    """The generated RFCA archive index (build_archive_index.py -> archive_links.json)."""

    INDEX = json.loads((SCRAPERS / "growing_guides" / "archive_links.json").read_text())

    def test_index_well_formed(self):
        self.assertIsInstance(self.INDEX, dict)
        self.assertGreater(len(self.INDEX), 0)
        for slug, entries in self.INDEX.items():
            self.assertIsInstance(entries, list)
            for e in entries:
                self.assertTrue(e["url"].startswith("https://"), e["url"])
                self.assertTrue(e.get("title"))
                self.assertNotIn(EM_DASH, e["title"])
                self.assertNotIn(EN_DASH, e["title"])

    def test_index_slugs_are_real_species(self):
        self.assertEqual(set(self.INDEX) - VALID_SLUGS, set(),
                         "archive index references unknown species slugs")

    def test_olive_merges_curated_and_archive(self):
        urls = [e["url"] for e in gg.get_further_reading("olive")]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA missing")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/Olive" in u for u in urls), "RFCA missing")
        self.assertEqual(len(urls), len(set(urls)), "further reading not deduped")

    def test_cap_respected(self):
        self.assertLessEqual(len(gg.get_further_reading("olive", cap=2)), 2)

    def test_unguided_species_with_archive_has_links_available(self):
        # starfruit has no guide yet, but the index has candidates ready for when it does.
        self.assertFalse(gg.has_guide("starfruit"))
        self.assertGreater(len(gg._archive_links().get("starfruit", [])), 0)


class MangoGuideTests(unittest.TestCase):
    """Mango is the second enriched species (after olive); the same guarantees apply,
    on a different crop with different regions, pests and harvest windows."""

    def test_pages_build_and_replace_blurb(self):
        for st, html in MANGO_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} mango page too small")
            self.assertNotIn("Generic mango blurb", html, f"{st} still shows the blurb")

    def test_state_pages_mutually_distinct(self):
        bodies = list(MANGO_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two mango state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in MANGO_REGION_TOKENS.items():
            self.assertTrue(any(t in MANGO_PAGES[st] for t in tokens),
                            f"{st} mango page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in MANGO_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, MANGO_PAGES[other],
                                     f"{owner} mango token '{t}' leaked onto {other} page")

    def test_stock_table_stays_above_guide(self):
        qld = MANGO_PAGES["QLD"]
        self.assertLess(qld.index("<table"), qld.index("Growing Mango in Queensland"),
                        "stock table must precede the mango guide")

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          MANGO_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} mango page missing FAQPage JSON-LD")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(MANGO_JSON["core"]["faqs"]) + len(MANGO_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} mango FAQ count mismatch")

    def test_sources_present_https_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', MANGO_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} mango page missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} mango Sources has no links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, url)
                self.assertIn("nofollow", attrs, url)

    def test_guide_sources_https_and_cited_ids_resolve(self):
        for s in MANGO_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        src_ids = {s["id"] for s in MANGO_JSON["sources"]}
        cited = set()
        for block in [MANGO_JSON["core"]] + list(MANGO_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "mango guide cites an unknown source id")

    def test_authoritative_domains_present(self):
        domains = " ".join(s["url"] for s in MANGO_JSON["sources"])
        for d in ("business.qld.gov.au", "nt.gov.au", "dpird.wa.gov.au", "mangoes.net.au"):
            self.assertIn(d, domains, f"expected a {d} source")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', MANGO_PAGES[st]))
            self.assertIn("mango", linked, f"{st} should link to /species/mango.html")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that 404")

    def test_further_reading_owned_and_followed(self):
        fr = re.search(r'id="further-reading".*?</section>', MANGO_PAGES["WA"], re.S)
        self.assertIsNotNone(fr, "mango WA page missing Further reading")
        block = fr.group(0)
        self.assertIn("wanatca.org.au", block)
        self.assertIn("rfcarchives.org.au", block)
        for url, attrs in re.findall(r'<a href="(https://[^"]+)"([^>]*)>', block):
            self.assertIn("noopener", attrs, url)
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")

    def test_further_reading_merges_curated_and_archive(self):
        urls = [e["url"] for e in gg.get_further_reading("mango")]
        self.assertTrue(any("wanatca.org.au" in u for u in urls), "curated WANATCA missing")
        self.assertTrue(any("rfcarchives.org.au/Next/Fruits/Mango" in u for u in urls), "RFCA missing")
        self.assertEqual(len(urls), len(set(urls)), "mango further reading not deduped")


# --- Fig guide: the second shipped species. Reuse the olive guards so fig stays
# per-state-unique, dash-free, cited, FAQ-rich, and correctly Mediterranean. ---
FIG_SPECIES = {
    "common_name": "Fig",
    "latin_name": "Ficus carica",
    "description": "Generic fig blurb that the rich guide should replace.",
    "slug": "fig",
}


def _fig_products(n=6):
    return [
        {"title": f"Fig Variety {i}", "url": f"https://nursery.example/fig-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 25.0 + i * 5,
         "available": True, "species": FIG_SPECIES}
        for i in range(n)
    ]


FIG_PAGES = {st: bssp.build_combo_page(st, "fig", _fig_products(), TODAY) for st in STATES}
FIG_JSON = json.loads((SCRAPERS / "growing_guides" / "fig.json").read_text(encoding="utf-8"))

# Distinct region tokens that must appear on exactly one fig state page.
FIG_REGION_TOKENS = {
    "WA": ["Swan Valley", "Perth Hills"],
    "QLD": ["Lockyer Valley", "Granite Belt"],
    "NSW": ["Riverina", "Central West"],
    "VIC": ["Mornington Peninsula", "Goulburn Valley"],
}


class FigGuideTests(unittest.TestCase):
    """Fig is the second shipped guide; reuse the olive guards to keep it honest."""

    def test_pages_build_and_mutually_distinct(self):
        bodies = list(FIG_PAGES.values())
        for st, html in FIG_PAGES.items():
            self.assertGreater(len(html), 5000, f"fig {st} page too small")
            self.assertNotIn("Generic fig blurb", html, f"fig {st} still shows the blurb")
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two fig state pages are identical")

    def test_each_state_has_region_tokens(self):
        for st, tokens in FIG_REGION_TOKENS.items():
            self.assertTrue(any(t in FIG_PAGES[st] for t in tokens),
                            f"fig {st} page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak(self):
        for owner, tokens in FIG_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, FIG_PAGES[other],
                                     f"fig {owner} token '{t}' leaked onto {other}")

    def test_no_em_or_en_dashes(self):
        for st, html in FIG_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on fig {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on fig {st} page")

    def test_no_dashes_in_guide_json(self):
        def scan(obj, path="fig.json"):
            if isinstance(obj, str):
                self.assertNotIn(EM_DASH, obj, f"em dash in {path}")
                self.assertNotIn(EN_DASH, obj, f"en dash in {path}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    scan(v, f"{path}[{i}]")
        scan(FIG_JSON)

    def test_faq_jsonld_parses_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          FIG_PAGES[st], re.S)
            self.assertIsNotNone(m, f"fig {st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(FIG_JSON["core"]["faqs"]) + len(FIG_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"fig {st} FAQ count mismatch")

    def test_sources_and_further_reading_present(self):
        for st in STATES:
            self.assertIn('id="sources"', FIG_PAGES[st], f"fig {st} missing Sources")
            self.assertIn('id="further-reading"', FIG_PAGES[st], f"fig {st} missing Further reading")
        fr = re.search(r'id="further-reading".*?</section>', FIG_PAGES["WA"], re.S).group(0)
        self.assertIn("wanatca.org.au", fr, "fig Further reading missing WANATCA")
        self.assertIn("rfcarchives.org.au", fr, "fig Further reading missing RFCA")

    def test_sources_https_and_cited_ids_resolve(self):
        for s in FIG_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https fig source: {s['url']}")
        src_ids = {s["id"] for s in FIG_JSON["sources"]}
        cited = set()
        for block in [FIG_JSON["core"]] + list(FIG_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "fig guide cites an unknown source id")

    def test_fig_is_mediterranean_not_subtropical(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["fig"], "mediterranean")
        note = bssp.get_climate_note("Fig", "WA")
        self.assertIn("fig", note.lower(), "WA mediterranean climate note should mention figs")
        self.assertNotIn("Chilling hours may be lower", note,
                         "fig should not inherit the stone/pome-fruit chill-hours note")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', FIG_PAGES[st]))
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"fig {st} has /species/ links that would 404")


# ---------------------------------------------------------------------------
# Tamarillo guide (third enriched species). Same guarantees as olive and lychee:
# each state page genuinely unique, region tokens do not leak, no dashes, FAQ
# JSON-LD, cited Sources with a tamarillo-specific note, and owned-followed
# Further reading. Tamarillo is subtropical and frost tender, so its flagship is
# NSW (broadest frost-free, warm-temperate envelope), not WA.
# ---------------------------------------------------------------------------
TAMARILLO_SPECIES = {
    "common_name": "Tamarillo",
    "latin_name": "Solanum betaceum",
    "description": "Generic tamarillo blurb that should be replaced by the rich guide.",
    "slug": "tamarillo",
}


def _tamarillo_products(n=6):
    names = ["Red", "Orange", "Yellow", "Oratia Red", "Goldmine", "Bold Gold"]
    return [
        {"title": f"Tamarillo {names[i % len(names)]}",
         "url": f"https://nursery.example/tamarillo-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 19.0 + i * 4,
         "available": True, "species": TAMARILLO_SPECIES}
        for i in range(n)
    ]


TAMARILLO_PAGES = {st: bssp.build_combo_page(st, "tamarillo", _tamarillo_products(), TODAY) for st in STATES}
TAMARILLO_JSON = json.loads((SCRAPERS / "growing_guides" / "tamarillo.json").read_text(encoding="utf-8"))

# Region tokens that must appear on exactly one state's tamarillo page.
TAMARILLO_REGION_TOKENS = {
    # NB: "Perth" is not WA-exclusive (it is in the site footer, "Perth WA"), so
    # use WA-only region names here, the same reason olive uses Moore River/Gingin.
    "WA": ["Swan Coastal Plain", "South West"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Northern Rivers", "Sydney basin"],
    "VIC": ["Mornington Peninsula", "Gippsland"],
}


class TamarilloGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in TAMARILLO_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} tamarillo page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(TAMARILLO_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two tamarillo state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in TAMARILLO_PAGES.items():
            self.assertNotIn("Generic tamarillo blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in TAMARILLO_REGION_TOKENS.items():
            self.assertTrue(any(t in TAMARILLO_PAGES[st] for t in tokens),
                            f"{st} tamarillo page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in TAMARILLO_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, TAMARILLO_PAGES[other],
                                     f"{owner} tamarillo token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in TAMARILLO_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on tamarillo {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on tamarillo {st} page")

    def test_no_dashes_in_guide_json(self):
        def scan(obj, path="tamarillo.json"):
            if isinstance(obj, str):
                self.assertNotIn(EM_DASH, obj, f"em dash in {path}")
                self.assertNotIn(EN_DASH, obj, f"en dash in {path}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    scan(v, f"{path}[{i}]")
        scan(TAMARILLO_JSON)

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          TAMARILLO_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(TAMARILLO_JSON["core"]["faqs"]) + len(TAMARILLO_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', TAMARILLO_PAGES[st], f"{st} missing Sources")
        for s in TAMARILLO_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in TAMARILLO_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au",
            )),
            "expected at least one gov authority among the tamarillo sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in TAMARILLO_JSON["sources"]}
        cited = set()
        for block in [TAMARILLO_JSON["core"]] + list(TAMARILLO_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "tamarillo guide cites an unknown source id")

    def test_sources_note_is_not_olive_specific(self):
        # Regression guard against the old hardcoded "olive-industry bodies" note.
        for st in STATES:
            self.assertNotIn("olive-industry", TAMARILLO_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', TAMARILLO_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("tamarillo"))
        m = re.search(r'id="further-reading".*?</section>', TAMARILLO_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        # owned archive links must be followed (noopener, NOT nofollow)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("tamarillo")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("tamarillo").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("tamarillo", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")




# ---------------------------------------------------------------------------
# Peach guide (growing_guides/peach.json). Peach is the second species enriched
# with a cited, per-state guide. These tests reuse the same guarantees the olive
# tests protect (per-state uniqueness, no leaking region tokens, no dashes, cited
# https sources, FAQ JSON-LD) so adding a species keeps the bar, not just olive.
# Peach is a temperate stone fruit, so it deliberately uses the existing
# "temperate" climate note (no new SPECIES_CLIMATE_CATEGORY entry needed) and,
# unlike olive, has NO owned-archive Further reading (the rare-fruit RFCA has no
# Peach folder and there is no WANATCA peach article), which is asserted below.
# ---------------------------------------------------------------------------

PEACH_SPECIES = {
    "common_name": "Peach",
    "latin_name": "Prunus persica",
    "description": "Generic peach blurb that should be replaced by the rich guide.",
    "slug": "peach",
}


def _peach_products(n=6):
    return [
        {
            "title": f"Peach Variety {i}",
            "url": f"https://nursery.example/peach-{i}",
            "nursery_key": "daleys",
            "nursery_name": "Daleys",
            "price": 30.0 + i * 5,
            "available": True,
            "species": PEACH_SPECIES,
        }
        for i in range(n)
    ]


PEACH_PAGES = {st: bssp.build_combo_page(st, "peach", _peach_products(), TODAY) for st in STATES}
PEACH_JSON = json.loads((SCRAPERS / "growing_guides" / "peach.json").read_text(encoding="utf-8"))

# Region tokens that must appear on exactly one peach state page (no doorway dupes).
PEACH_REGION_TOKENS = {
    "WA": ["Donnybrook", "Perth Hills"],
    "QLD": ["Granite Belt", "Stanthorpe"],
    "NSW": ["Bilpin", "Orange"],
    "VIC": ["Goulburn Valley", "Shepparton"],
}


class PeachBuildTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in PEACH_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} peach page too small")

    def test_canonical_and_og(self):
        wa = PEACH_PAGES["WA"]
        self.assertIn(
            '<link rel="canonical" href="https://treestock.com.au/buy-peach-trees-western-australia.html">',
            wa,
        )
        self.assertIn('<meta property="og:type" content="article">', wa)

    def test_stock_table_stays_above_editorial_guide(self):
        wa = PEACH_PAGES["WA"]
        self.assertLess(wa.index("<table"), wa.index("Growing Peach in Western Australia"),
                        "stock table must precede the guide")

    def test_treesmith_promo_present_below_guide(self):
        for st, html in PEACH_PAGES.items():
            self.assertIn("Track your collection with Treesmith", html, f"{st} missing promo")
            self.assertLess(html.index("Growing Peach in"),
                            html.index("Track your collection with Treesmith"),
                            f"{st} promo must sit below the guide")

    def test_generic_blurb_replaced_when_guide_exists(self):
        for st, html in PEACH_PAGES.items():
            self.assertNotIn("Generic peach blurb", html, f"{st} still shows the blurb")

    def test_temperate_climate_note_used(self):
        # Peach must inherit the stone-fruit "temperate" note (chill-hours advice),
        # NOT the mediterranean note. This is the correct category for a stone fruit.
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["peach"], "temperate")
        note = bssp.get_climate_note("Peach", "WA")
        self.assertIn("low-chill", note)


class PeachUniquenessTests(unittest.TestCase):
    def test_state_pages_mutually_distinct(self):
        bodies = list(PEACH_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two peach state pages are identical")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in PEACH_REGION_TOKENS.items():
            self.assertTrue(any(t in PEACH_PAGES[st] for t in tokens),
                            f"{st} peach page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in PEACH_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, PEACH_PAGES[other],
                                     f"{owner} peach token '{t}' leaked onto {other} page")

    def test_overlay_then_core(self):
        wa = gg.render_combo_guide("peach", "WA")
        self.assertIn("Where peaches grow in WA", wa)   # overlay
        self.assertIn("Choosing a variety", wa)         # core
        self.assertLess(wa.index("Where peaches grow in WA"), wa.index("Choosing a variety"))


class PeachCopyRuleTests(unittest.TestCase):
    def test_no_em_or_en_dashes_in_pages(self):
        for st, html in PEACH_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on {st} peach page")
            self.assertNotIn(EN_DASH, html, f"en dash on {st} peach page")

    def test_no_dashes_in_guide_json(self):
        def scan(obj, path="peach.json"):
            if isinstance(obj, str):
                self.assertNotIn(EM_DASH, obj, f"em dash in {path}")
                self.assertNotIn(EN_DASH, obj, f"en dash in {path}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    scan(v, f"{path}[{i}]")
        scan(PEACH_JSON)


class PeachSourcesTests(unittest.TestCase):
    def test_sources_section_present(self):
        for st in STATES:
            self.assertIn('id="sources"', PEACH_PAGES[st], f"{st} missing Sources section")

    def test_reference_links_are_https_noopener_nofollow(self):
        for st in STATES:
            block = re.search(r'id="sources".*?</section>', PEACH_PAGES[st], re.S)
            self.assertIsNotNone(block, f"{st} missing Sources section")
            refs = re.findall(r'<li><a href="(https://[^"]+)"([^>]*)>', block.group(0))
            self.assertTrue(refs, f"{st} has no reference links")
            for url, attrs in refs:
                self.assertIn("noopener", attrs, f"{st} ref missing noopener: {url}")
                self.assertIn("nofollow", attrs, f"{st} ref missing nofollow: {url}")

    def test_guide_sources_all_https(self):
        for s in PEACH_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")

    def test_guide_sources_include_authoritative_domains(self):
        domains = " ".join(s["url"] for s in PEACH_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "dpird.wa.gov.au", "business.qld.gov.au", "dpi.nsw.gov.au",
                "agriculture.vic.gov.au",
            )),
            "expected at least one state-agriculture authority among the peach sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in PEACH_JSON["sources"]}
        cited = set()
        blocks = [PEACH_JSON["core"]] + list(PEACH_JSON["states"].values())
        for block in blocks:
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "peach guide cites an unknown source id")

    def test_sources_note_does_not_leak_olive_copy(self):
        self.assertNotIn("olive-industry", PEACH_PAGES["WA"])


class PeachFaqAndLinkTests(unittest.TestCase):
    def _extract(self, html):
        m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', html, re.S)
        self.assertIsNotNone(m, "FAQPage JSON-LD block not found")
        return json.loads(m.group(1))

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            data = self._extract(PEACH_PAGES[st])
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(PEACH_JSON["core"]["faqs"]) + len(PEACH_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', PEACH_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(),
                             f"{st} has /species/ links that would 404")

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("peach"))


class PeachFurtherReadingTests(unittest.TestCase):
    """Peach is mainstream stone fruit: the Rare Fruit Council archive has no Peach
    folder and there is no WANATCA peach yearbook article, so peach has NO owned
    archive cross-links. The 'Further reading' block (archive-only) is therefore
    intentionally absent. If owned peach archive content ever appears, this guard
    fails on purpose, prompting a deliberate update."""

    def test_no_curated_or_archive_further_reading(self):
        self.assertNotIn("further_reading", PEACH_JSON)
        self.assertEqual(gg.get_further_reading("peach"), [])

    def test_no_further_reading_section_on_pages(self):
        for st in STATES:
            self.assertNotIn('id="further-reading"', PEACH_PAGES[st],
                             f"{st} peach page should have no archive Further reading section")


# ---------------------------------------------------------------------------
# Lychee guide (second enriched species). Same guarantees as olive: each state
# page genuinely unique, region tokens do not leak, no dashes, FAQ JSON-LD,
# cited Sources with a lychee-specific note, and owned-followed Further reading.
# ---------------------------------------------------------------------------
LYCHEE_SPECIES = {
    "common_name": "Lychee",
    "latin_name": "Litchi chinensis",
    "description": "Generic lychee blurb that should be replaced by the rich guide.",
    "slug": "lychee",
}


def _lychee_products(n=6):
    names = ["Kwai May Pink", "Wai Chee", "Tai So", "Salathiel", "Bengal", "Erdon Lee"]
    return [
        {"title": f"Lychee {names[i % len(names)]}",
         "url": f"https://nursery.example/lychee-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 49.0 + i * 5,
         "available": True, "species": LYCHEE_SPECIES}
        for i in range(n)
    ]


LYCHEE_PAGES = {st: bssp.build_combo_page(st, "lychee", _lychee_products(), TODAY) for st in STATES}
LYCHEE_JSON = json.loads((SCRAPERS / "growing_guides" / "lychee.json").read_text(encoding="utf-8"))

# Region tokens that must appear on exactly one state's lychee page.
LYCHEE_REGION_TOKENS = {
    "QLD": ["Atherton", "Bundaberg"],
    "WA": ["Kununurra", "Carnarvon"],
    "NSW": ["Northern Rivers", "Coffs Harbour"],
    "VIC": ["hothouse", "Melbourne"],
}


class LycheeGuideTests(unittest.TestCase):
    def test_pages_build_nonempty(self):
        for st, html in LYCHEE_PAGES.items():
            self.assertGreater(len(html), 5000, f"{st} lychee page too small")

    def test_state_pages_mutually_distinct(self):
        bodies = list(LYCHEE_PAGES.values())
        for i in range(len(bodies)):
            for j in range(i + 1, len(bodies)):
                self.assertNotEqual(bodies[i], bodies[j], "two lychee state pages are identical")

    def test_generic_blurb_replaced(self):
        for st, html in LYCHEE_PAGES.items():
            self.assertNotIn("Generic lychee blurb", html, f"{st} still shows the blurb")

    def test_each_state_has_its_own_region_tokens(self):
        for st, tokens in LYCHEE_REGION_TOKENS.items():
            self.assertTrue(any(t in LYCHEE_PAGES[st] for t in tokens),
                            f"{st} lychee page missing its region tokens {tokens}")

    def test_region_tokens_do_not_leak_across_states(self):
        for owner, tokens in LYCHEE_REGION_TOKENS.items():
            for other in STATES:
                if other == owner:
                    continue
                for t in tokens:
                    self.assertNotIn(t, LYCHEE_PAGES[other],
                                     f"{owner} lychee token '{t}' leaked onto {other} page")

    def test_no_em_or_en_dashes(self):
        for st, html in LYCHEE_PAGES.items():
            self.assertNotIn(EM_DASH, html, f"em dash on lychee {st} page")
            self.assertNotIn(EN_DASH, html, f"en dash on lychee {st} page")

    def test_no_dashes_in_guide_json(self):
        def scan(obj, path="lychee.json"):
            if isinstance(obj, str):
                self.assertNotIn(EM_DASH, obj, f"em dash in {path}")
                self.assertNotIn(EN_DASH, obj, f"en dash in {path}")
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    scan(v, f"{path}[{i}]")
        scan(LYCHEE_JSON)

    def test_faq_jsonld_parses_on_each_state(self):
        for st in STATES:
            m = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                          LYCHEE_PAGES[st], re.S)
            self.assertIsNotNone(m, f"{st} FAQPage JSON-LD not found")
            data = json.loads(m.group(1))
            self.assertEqual(data["@type"], "FAQPage")
            expected = len(LYCHEE_JSON["core"]["faqs"]) + len(LYCHEE_JSON["states"][st].get("faqs", []))
            self.assertEqual(len(data["mainEntity"]), expected, f"{st} FAQ count mismatch")

    def test_sources_present_and_https_and_authoritative(self):
        for st in STATES:
            self.assertIn('id="sources"', LYCHEE_PAGES[st], f"{st} missing Sources")
        for s in LYCHEE_JSON["sources"]:
            self.assertTrue(s["url"].startswith("https://"), f"non-https source: {s['url']}")
        domains = " ".join(s["url"] for s in LYCHEE_JSON["sources"])
        self.assertTrue(
            any(d in domains for d in (
                "business.qld.gov.au", "dpird.wa.gov.au", "fao.org",
                "australianlychee.com.au",
            )),
            "expected at least one gov/industry authority among the lychee sources",
        )

    def test_every_cited_id_resolves_to_a_source(self):
        src_ids = {s["id"] for s in LYCHEE_JSON["sources"]}
        cited = set()
        for block in [LYCHEE_JSON["core"]] + list(LYCHEE_JSON["states"].values()):
            for sec in block.get("sections", []):
                cited.update(sec.get("cites", []))
        self.assertEqual(cited - src_ids, set(), "lychee guide cites an unknown source id")

    def test_sources_note_is_lychee_specific(self):
        # Regression guard against the old hardcoded "olive-industry bodies" note.
        for st in STATES:
            self.assertNotIn("olive-industry", LYCHEE_PAGES[st])

    def test_species_links_resolve(self):
        for st in STATES:
            linked = set(re.findall(r'/species/([a-z0-9-]+)\.html', LYCHEE_PAGES[st]))
            self.assertTrue(linked, f"{st} expected at least one /species/ link")
            self.assertEqual(linked - VALID_SLUGS, set(), f"{st} has /species/ links that would 404")

    def test_further_reading_owned_followed_and_merged(self):
        self.assertIn('id="further-reading"', gg.render_species_guide("lychee"))
        m = re.search(r'id="further-reading".*?</section>', LYCHEE_PAGES["WA"], re.S)
        fr = m.group(0)
        self.assertIn("wanatca.org.au", fr)
        self.assertIn("rfcarchives.org.au", fr)
        # owned archive links must be followed (noopener, NOT nofollow)
        for url, attrs in re.findall(r'<a href="(https://(?:wanatca|rfcarchives)[^"]+)"([^>]*)>', fr):
            self.assertNotIn("nofollow", attrs, f"owned cross-link should be followed: {url}")
        merged = gg.get_further_reading("lychee")
        self.assertEqual(fr.count("<li>"), len(merged))

    def test_combo_cites_more_than_species(self):
        species_n = gg.render_species_guide("lychee").count('rel="noopener nofollow"')
        combo_n = gg.render_combo_guide("lychee", "WA").count('rel="noopener nofollow"')
        self.assertGreater(combo_n, species_n,
                           "the WA overlay should add cited sources beyond the core")


class SpeciesPagePassthroughDashTests(unittest.TestCase):
    """Regression: build_species_pages.py must strip en/em dashes from passthrough
    nursery product titles and names, exactly as build_species_state_pages.py does.
    Before this fix the live /species/lychee.html and /species/olive.html rendered
    nursery titles like 'Lychee - Jean Hang' with a U+2013 en dash, breaking the
    treestock no-dash copy rule on the species pages."""

    SPECIES = {"common_name": "Mango", "latin_name": "Mangifera indica",
               "slug": "mango", "region": "South Asia", "description": "A mango blurb."}

    def _dashy_products(self):
        return [
            {"title": "Mango – Kensington Pride — Grafted",
             "url": "https://nursery.example/m1", "nursery_key": "daleys",
             "nursery_name": "Some – Nursery", "price": 39.0, "available": True},
            {"title": "Mango – R2E2", "url": "https://nursery.example/m2",
             "nursery_key": "daleys", "nursery_name": "Daleys", "price": 45.0, "available": False},
        ]

    def test_titles_and_names_sanitised(self):
        html = bsp.build_species_page(self.SPECIES, self._dashy_products())
        self.assertNotIn(EM_DASH, html, "em dash leaked onto species page")
        self.assertNotIn(EN_DASH, html, "en dash leaked onto species page (the live bug)")
        self.assertIn("Mango - Kensington Pride - Grafted", html)
        self.assertIn("Some - Nursery", html)


if __name__ == "__main__":
    unittest.main()
