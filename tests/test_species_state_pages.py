"""
Cross-cutting tests for the growing-guide system (tools/scrapers/growing_guides.py and
build_species_state_pages.py / build_species_pages.py).

Per-species tests live in tests/test_guide_<slug>.py (one file each, so parallel guide
runs never collide on a shared module). This file keeps only the guards that are NOT tied
to one species: the climate-category mapping, the graceful fallback for an unenriched
species, the generated RFCA archive index, the growing_guides module API, the species-page
dash passthrough, and the FAQ-overlap guard that runs over EVERY guide.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guide_helpers import (  # noqa: E402
    bssp, gg, bsp, EM_DASH, EN_DASH, STATES, TODAY, VALID_SLUGS, SCRAPERS, GUIDES_DIR,
)


def _unenriched_products():
    # A species with NO growing guide, to prove the graceful fallback still works.
    # This uses a SYNTHETIC slug ("example-unenriched") rather than a real species:
    # after the 2026-06-05 guide batch (PRs #75-#83) every real tracked species that had
    # archive_links is now guided, so there is no real unguided species left to point
    # this at. build_combo_page renders the fallback from the product's inline species
    # dict (common_name/description) and does not require a real or registered slug, so a
    # synthetic slug keeps has_guide(slug) False and exercises the same blurb path.
    # (This role was played by starfruit, then white sapote, then cacao, each until it
    # was enriched; it is now permanently synthetic.)
    sp = {"common_name": "Example Unenriched", "latin_name": "Exemplum ineditum",
          "description": "Generic unenriched blurb.", "slug": "example-unenriched"}
    return [
        {"title": f"Example Unenriched {i}",
         "url": f"https://nursery.example/example-unenriched-{i}",
         "nursery_key": "daleys", "nursery_name": "Daleys", "price": 30.0 + i,
         "available": True, "species": sp}
        for i in range(4)
    ]


UNENRICHED_PAGE = bssp.build_combo_page("QLD", "example-unenriched", _unenriched_products(), TODAY)


class ClimateNoteTests(unittest.TestCase):
    """The miscategorisation fix: the mediterranean category exists and is wired up.
    Olive/fig-specific climate assertions live in their per-species files."""

    def test_olive_and_grape_are_mediterranean(self):
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["olive"], "mediterranean")
        self.assertEqual(bssp.SPECIES_CLIMATE_CATEGORY["grape"], "mediterranean")

    def test_every_state_has_a_mediterranean_note(self):
        for state in STATES:
            self.assertIn("mediterranean", bssp.STATE_CLIMATE_NOTES[state])

    def test_no_dashes_in_climate_notes(self):
        for state, notes in bssp.STATE_CLIMATE_NOTES.items():
            for cat, text in notes.items():
                self.assertNotIn(EM_DASH, text, f"em dash in {state}/{cat} climate note")
                self.assertNotIn(EN_DASH, text, f"en dash in {state}/{cat} climate note")


class FallbackTests(unittest.TestCase):
    """A species with no guide JSON must fall back to the generic blurb, cleanly."""

    def test_has_guide(self):
        self.assertTrue(gg.has_guide("olive"))
        self.assertTrue(gg.has_guide("mango"))
        self.assertTrue(gg.has_guide("starfruit"))
        self.assertTrue(gg.has_guide("white-sapote"))
        self.assertTrue(gg.has_guide("cacao"))
        self.assertFalse(gg.has_guide("example-unenriched"))

    def test_unenriched_species_uses_blurb_and_stays_clean(self):
        self.assertIn("Generic unenriched blurb.", UNENRICHED_PAGE)
        self.assertNotIn('id="sources"', UNENRICHED_PAGE)
        self.assertIn("Track your collection with Treesmith", UNENRICHED_PAGE)
        self.assertNotIn(EM_DASH, UNENRICHED_PAGE)
        self.assertNotIn(EN_DASH, UNENRICHED_PAGE)

    def test_no_faq_jsonld_for_unenriched_species(self):
        self.assertNotIn("FAQPage", UNENRICHED_PAGE)

    def test_unenriched_species_has_no_further_reading(self):
        self.assertNotIn('id="further-reading"', UNENRICHED_PAGE)


class GrowingGuidesModuleTests(unittest.TestCase):
    """The growing_guides module API, exercised through olive as the example guide."""

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

    def test_guided_species_still_has_archive_index_entries(self):
        # After the 2026-06-05 batch (PRs #75-#83) every archived species is also guided,
        # so the old "unguided species that still has archive links" premise is extinct.
        # This now guards the other half: the archive index must still carry entries for a
        # guided species (cacao), which get_further_reading merges into the guide's
        # "further reading". (test_olive_merges_curated_and_archive covers the merge.)
        self.assertTrue(gg.has_guide("cacao"))
        self.assertGreater(len(gg._archive_links().get("cacao", [])), 0)


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


# ---------------------------------------------------------------------------
# FAQ-overlap guard. The FAQ must add a NET-NEW question, not recap a body
# section (docs/species-guide-rollout.md step 3a). Historically ~half of all
# FAQs restated a section: "Do I need two X trees to get fruit?" duplicating the
# "Pollination" section, "When do you harvest in <state>?" duplicating "Harvest
# window in <state>", "Why won't nurseries post to WA?" duplicating "Buying and
# shipping to WA". This guard fails the build when an FAQ answer substantially
# restates a section body, or an FAQ question restates a section heading, across
# EVERY growing_guides/*.json (so it covers species with no dedicated test file).
# FAQs are only compared against sections in the SAME block (core FAQs vs core
# sections; a state's FAQs vs that state's overlay), which is the right scope.
# ---------------------------------------------------------------------------

# Stopwords include the high-frequency question scaffold ("do you need two trees
# to get fruit") so a shared topic alone does not flag; the real signal is the
# distinctive content words (variety names, regions, mechanisms) an FAQ reuses
# verbatim from a section.
_FAQ_STOP = frozenset("""
a an and are as at be been but by can could did do does for from get got had has have how if in into is
it its may might must need no nor not of off on or our out over should so than that the their them then
they this to under until up was were what when where which who why will with you your i more most less
two tree trees fruit yes also some any one each per
""".split())

_WORD_RE = re.compile(r"[a-z0-9]+")


def _content_words(text):
    """Lowercased content-word set: strip HTML tags, drop stopwords and <=2-char tokens."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) > 2 and w not in _FAQ_STOP}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class FaqBodyOverlapTests(unittest.TestCase):
    """Every FAQ must be net-new, not a recap of a body section/heading."""

    # Tuned against the de-duplicated guides (which sit <= ~0.36) with margin,
    # while still catching the historical recaps (0.45 to 0.81). Do NOT raise
    # these to make a failing guide pass; rewrite the FAQ per step 3a instead.
    ANSWER_VS_BODY_MAX = 0.45
    QUESTION_VS_HEADING_MAX = 0.45

    def _blocks(self, guide):
        yield "core", guide.get("core") or {}
        for st, overlay in (guide.get("states") or {}).items():
            yield st, overlay or {}

    def _overlaps(self, guide):
        """Yield (kind, score, block, faq_question, section_heading) for every
        FAQ x section pair in a guide."""
        for block_name, block in self._blocks(guide):
            sections = block.get("sections", [])
            bodies = [(s.get("heading", ""), _content_words(s.get("body", ""))) for s in sections]
            heads = [(s.get("heading", ""), _content_words(s.get("heading", ""))) for s in sections]
            for f in block.get("faqs", []):
                ans, ques = _content_words(f.get("a", "")), _content_words(f.get("q", ""))
                for heading, body_words in bodies:
                    yield ("answer", _jaccard(ans, body_words), block_name, f.get("q", ""), heading)
                for heading, head_words in heads:
                    yield ("question", _jaccard(ques, head_words), block_name, f.get("q", ""), heading)

    def test_no_faq_recaps_a_section(self):
        guides = sorted(p for p in GUIDES_DIR.glob("*.json") if p.name != "archive_links.json")
        self.assertTrue(guides, "no growing-guide JSON files found")
        for path in guides:
            guide = json.loads(path.read_text(encoding="utf-8"))
            for kind, score, block, question, heading in self._overlaps(guide):
                limit = self.ANSWER_VS_BODY_MAX if kind == "answer" else self.QUESTION_VS_HEADING_MAX
                self.assertLess(
                    score, limit,
                    f"{path.name} [{block}]: FAQ {question!r} {kind}-overlaps section "
                    f"{heading!r} at {score:.2f} (limit {limit}). This FAQ recaps the body; "
                    f"rewrite it to ask something the body does not already headline "
                    f"(docs/species-guide-rollout.md step 3a).",
                )

    def test_guard_catches_a_synthetic_duplicate(self):
        # Prove the guard bites, independent of the live guides: an FAQ whose
        # answer is lifted from a section body must exceed the threshold.
        body = ("Several popular varieties such as Arbequina, Koroneiki, Manzanillo and Picual "
                "will set a useful crop on their own, but almost all olives fruit more heavily "
                "with a second compatible variety nearby, and Leccino must have a pollinator.")
        dup = {"core": {
            "sections": [{"heading": "Pollination: do you need two trees?", "body": body}],
            "faqs": [{"q": "Do I need two olive trees to get fruit?",
                      "a": ("Several popular varieties such as Arbequina, Koroneiki, Manzanillo "
                            "and Picual set a useful crop on their own, but almost all olives "
                            "fruit more heavily with a second compatible variety nearby, and "
                            "Leccino must have a pollinator.")}]}}
        answer_scores = [s for kind, s, *_ in self._overlaps(dup) if kind == "answer"]
        self.assertGreaterEqual(
            max(answer_scores), self.ANSWER_VS_BODY_MAX,
            "the synthetic duplicate FAQ should trip the overlap guard but did not",
        )


if __name__ == "__main__":
    unittest.main()
