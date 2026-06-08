"""
Structural guards over every committed tools/scrapers/variety_descriptions/*.json.

Variety blurbs are short, multi-source-verified "what's unique" descriptions rendered on
/variety/<slug>.html (build_variety_pages.py via stocklib/variety_descriptions.py). These
tests make the generation gate a permanent repo invariant: a hand-edit that weakens a
blurb (too few sources, low confidence, a dash, a dangling cite, an orphan source, or a
slug that points at parser noise rather than a real variety) fails CI.

Mirrors the all-guides cross-cutting guards in tests/test_species_state_pages.py and the
copy-rule helper in tests/guide_helpers.py. Pure stdlib unittest.
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
DESC_DIR = SCRAPERS / "variety_descriptions"
sys.path.insert(0, str(SCRAPERS))

# Reuse the shared slug function (anti-noise key check); never reimplement it (the
# variety slug MUST match what build_variety_pages.py computes or the blurb attaches to
# the wrong page). test_no_forking.py guards against forking these helpers.
from cultivar_parsing import slugify  # noqa: E402
from stocklib import variety_descriptions as vd  # noqa: E402

# U+2014 em dash, U+2013 en dash. Both banned in treestock copy.
EM_DASH = "—"
EN_DASH = "–"

VALID_SPECIES_SLUGS = {
    s["slug"]
    for s in json.loads((SCRAPERS / "fruit_species.json").read_text())
    if s.get("slug")
}

MIN_SOURCES = 2
MIN_CONFIDENCE_SCORE = 0.80
VALID_CONFIDENCE = {"high", "medium"}
VALID_TIERS = {"authoritative", "owned", "nursery", "third_party"}
AUTHORITATIVE_TIERS = {"authoritative", "owned"}
# Sources that count as independent corroboration (anything but a nursery's own listing).
# A blurb may not rest solely on nursery marketing copy.
INDEPENDENT_TIERS = {"authoritative", "owned", "third_party"}
MAX_PARAGRAPHS = 2
MAX_PARAGRAPH_CHARS = 800
# Claim types asserting a specific, falsifiable agronomic figure or a marketing
# superlative: these are the genuinely fabricable facts and must rest on an
# authoritative/owned source (the no-invention rule). Qualitative claims (origin,
# flavour, season, appearance, use, pollination, growing, storage, naming, breeding,
# climate) and well-corroborated historical facts only need the general gate below.
SPECIFIC_FACT_TYPES = {"measurement", "yield", "chill", "award", "superlative", "health"}

REQUIRED_ENTRY_KEYS = {
    "slug", "species", "variety", "paragraphs", "claims", "sources",
    "confidence", "confidence_score", "verified", "generated_date",
}


def _iter_files():
    if not DESC_DIR.exists():
        return
    yield from sorted(DESC_DIR.glob("*.json"))


def _iter_entries():
    """Yield (filename, species_slug, variety_slug, entry) for every committed entry."""
    for path in _iter_files():
        data = json.loads(path.read_text(encoding="utf-8"))
        species_slug = data.get("species_slug")
        for vslug, entry in (data.get("varieties") or {}).items():
            yield path.name, species_slug, vslug, entry


class VarietyDescriptionFileTests(unittest.TestCase):
    """Per-file shape checks."""

    def test_files_have_species_slug_matching_filename(self):
        for path in _iter_files():
            with self.subTest(file=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict)
                self.assertIsInstance(data.get("varieties"), dict, "missing 'varieties' map")
                self.assertEqual(
                    data.get("species_slug"), path.stem,
                    "file-level species_slug must equal the filename stem",
                )

    def test_no_em_or_en_dashes(self):
        for path in _iter_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotIn(EM_DASH, text, f"em dash in {path.name}")
                self.assertNotIn(EN_DASH, text, f"en dash in {path.name}")


class VarietyDescriptionEntryTests(unittest.TestCase):
    """Per-entry guards run over every committed description."""

    def test_required_keys_and_types(self):
        for fname, _sp, vslug, e in _iter_entries():
            with self.subTest(file=fname, variety=vslug):
                self.assertTrue(REQUIRED_ENTRY_KEYS.issubset(e), f"missing keys: {REQUIRED_ENTRY_KEYS - set(e)}")
                self.assertIs(e["verified"], True, "verified must be True")
                self.assertIn(e["confidence"], VALID_CONFIDENCE)
                self.assertIsInstance(e["confidence_score"], (int, float))
                self.assertGreaterEqual(e["confidence_score"], 0.0)
                self.assertLessEqual(e["confidence_score"], 1.0)
                self.assertTrue(str(e["generated_date"]).strip())

    def test_paragraphs_present_and_tight(self):
        for fname, _sp, vslug, e in _iter_entries():
            with self.subTest(file=fname, variety=vslug):
                paras = e["paragraphs"]
                self.assertIsInstance(paras, list)
                self.assertGreaterEqual(len(paras), 1, "need at least one paragraph")
                self.assertLessEqual(len(paras), MAX_PARAGRAPHS, "keep it to a paragraph or two")
                for p in paras:
                    self.assertIsInstance(p, str)
                    self.assertTrue(p.strip(), "empty paragraph")
                    self.assertLessEqual(len(p), MAX_PARAGRAPH_CHARS, "paragraph too long for the above-table slot")

    def test_slug_matches_real_variety(self):
        """The key MUST equal slugify(species-variety) and the species MUST be a real
        species page slug. This is the anti-noise guard: blurbs can only attach to a
        variety whose /variety/<slug>.html the builder actually emits."""
        for fname, sp, vslug, e in _iter_entries():
            with self.subTest(file=fname, variety=vslug):
                expected = slugify(f"{e['species']}-{e['variety']}")
                self.assertEqual(vslug, expected, "variety key != slugify(species-variety)")
                self.assertEqual(e["slug"], vslug, "entry.slug must equal its map key")
                self.assertEqual(slugify(e["species"]), sp, "entry species must match the file species_slug")
                self.assertIn(sp, VALID_SPECIES_SLUGS, f"{sp} is not a real species (parser noise?)")

    def test_sources_https_and_tiers(self):
        for fname, _sp, vslug, e in _iter_entries():
            with self.subTest(file=fname, variety=vslug):
                sources = e["sources"]
                self.assertIsInstance(sources, list)
                self.assertGreaterEqual(len(sources), MIN_SOURCES, "need >=2 sources")
                ids = [s.get("id") for s in sources]
                self.assertEqual(len(ids), len(set(ids)), "duplicate source ids")
                for s in sources:
                    self.assertTrue(s.get("id"), "source missing id")
                    self.assertTrue(s.get("name"), "source missing name")
                    self.assertTrue(str(s.get("url", "")).startswith("https://"), f"non-https url: {s.get('url')}")
                    self.assertIn(s.get("tier"), VALID_TIERS, f"bad tier: {s.get('tier')}")

    def test_claims_cite_real_sources_and_no_orphans(self):
        for fname, _sp, vslug, e in _iter_entries():
            with self.subTest(file=fname, variety=vslug):
                source_ids = {s["id"] for s in e["sources"] if s.get("id")}
                self.assertTrue(e["claims"], "need at least one claim")
                cited = set()
                for c in e["claims"]:
                    self.assertTrue(str(c.get("text", "")).strip(), "claim missing text")
                    self.assertTrue(str(c.get("type", "")).strip(), "claim missing type")
                    cites = c.get("cites") or []
                    self.assertTrue(cites, f"claim '{c.get('text')}' has no cites")
                    for cid in cites:
                        self.assertIn(cid, source_ids, f"claim cites unknown source id: {cid}")
                    cited.update(cites)
                orphans = source_ids - cited
                self.assertFalse(orphans, f"sources never cited by any claim: {orphans}")

    def test_gate_is_a_permanent_invariant(self):
        """Every committed blurb must clear the generation gate: at least two sources,
        at least one of them an independent (non-nursery) reference so a blurb is never
        built on nursery marketing copy alone, and a high enough confidence score."""
        for fname, _sp, vslug, e in _iter_entries():
            with self.subTest(file=fname, variety=vslug):
                self.assertGreaterEqual(len(e["sources"]), MIN_SOURCES)
                self.assertGreaterEqual(e["confidence_score"], MIN_CONFIDENCE_SCORE)
                tiers = {s.get("tier") for s in e["sources"]}
                self.assertTrue(
                    tiers & INDEPENDENT_TIERS,
                    "need >=1 independent (non-nursery) source",
                )

    def test_specific_facts_have_authoritative_backing(self):
        """No-invention rule: a claim asserting a specific figure/superlative must cite
        an authoritative or owned source, not just a nursery listing or blog."""
        for fname, _sp, vslug, e in _iter_entries():
            by_id = {s["id"]: s for s in e["sources"] if s.get("id")}
            for c in e["claims"]:
                if c.get("type") in SPECIFIC_FACT_TYPES:
                    with self.subTest(file=fname, variety=vslug, claim=c.get("text")):
                        tiers = {by_id.get(cid, {}).get("tier") for cid in (c.get("cites") or [])}
                        self.assertTrue(
                            tiers & AUTHORITATIVE_TIERS,
                            f"specific-fact claim '{c.get('text')}' needs an authoritative/owned source",
                        )


class VarietyDescriptionRenderTests(unittest.TestCase):
    """The loader/renderer round-trips committed content and falls back gracefully."""

    def test_committed_entries_render(self):
        for fname, sp, vslug, _e in _iter_entries():
            with self.subTest(file=fname, variety=vslug):
                self.assertTrue(vd.has_description(vslug, sp), "committed entry not usable by loader")
                html = vd.render_blurb(vslug, sp)
                self.assertIn("text-gray-700 text-sm leading-relaxed", html)
                self.assertIn("variety-about", html)

    def test_missing_variety_falls_back_to_empty(self):
        self.assertFalse(vd.has_description("totally-made-up-xyz", "apple"))
        self.assertEqual(vd.render_blurb("totally-made-up-xyz", "apple"), "")


if __name__ == "__main__":
    unittest.main()
