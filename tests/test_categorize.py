"""
Tests for stocklib.categorize -- the classification ladder (DAL-194 P1.6,
DEC-200 design doc 3.2): species registry, then per-nursery category_raw
mapping, then keyword hint, else unclassified (counted per nursery).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib.categorize import (  # noqa: E402
    Categorizer, build_needs_review, keyword_hint, load_nursery_rules,
    match_category_raw,
)
from stocklib.taxonomy import KNOWN_CATEGORIES  # noqa: E402

RULES = {
    "daleys": [
        {"match": "Bush Food Plants", "mode": "exact", "category": "bush_tucker"},
    ],
    "guildford": [
        {"match": "Australian Native Food Plants", "mode": "contains",
         "category": "bush_tucker"},
    ],
    "prefixy": [
        {"match": "Natives", "mode": "prefix", "category": "native"},
    ],
}


class LadderPrecedenceTest(unittest.TestCase):
    def test_species_beats_category_raw_and_keyword(self):
        cz = Categorizer(species_matcher=lambda t: "fruit", nursery_rules=RULES)
        # Title would also hit the daleys rule AND a native keyword.
        cat, source = cz.categorize("Banksia Lime", "daleys", "Bush Food Plants")
        self.assertEqual((cat, source), ("fruit", "species"))

    def test_category_raw_beats_keyword(self):
        cz = Categorizer(species_matcher=lambda t: None, nursery_rules=RULES)
        cat, source = cz.categorize("Banksia Thing", "daleys", "Bush Food Plants")
        self.assertEqual((cat, source), ("bush_tucker", "category_raw"))

    def test_keyword_is_last_resort(self):
        cz = Categorizer(species_matcher=lambda t: None, nursery_rules=RULES)
        cat, source = cz.categorize("Banksia 'Giant Candles'", "daleys", "Shrubs")
        self.assertEqual((cat, source), ("native", "keyword"))

    def test_unclassified(self):
        cz = Categorizer(species_matcher=lambda t: None, nursery_rules=RULES)
        cat, source = cz.categorize("Mystery Plant", "daleys", "Shrubs")
        self.assertEqual((cat, source), (None, "unclassified"))


class MatcherModesTest(unittest.TestCase):
    def test_exact(self):
        rules = RULES["daleys"]
        self.assertEqual(match_category_raw("Bush Food Plants", rules), "bush_tucker")
        self.assertEqual(match_category_raw("bush food plants", rules),
                         "bush_tucker")  # case-insensitive
        self.assertIsNone(match_category_raw("Bush Food Plants and More", rules))

    def test_prefix(self):
        rules = RULES["prefixy"]
        self.assertEqual(match_category_raw("Natives - Grasses", rules), "native")
        self.assertIsNone(match_category_raw("All Natives", rules))

    def test_contains(self):
        rules = RULES["guildford"]
        self.assertEqual(
            match_category_raw("Edibles, Australian Native Food Plants", rules),
            "bush_tucker")

    def test_exact_outranks_contains_regardless_of_file_order(self):
        rules = [
            {"match": "Plants", "mode": "contains", "category": "native"},
            {"match": "Bush Food Plants", "mode": "exact", "category": "bush_tucker"},
        ]
        self.assertEqual(match_category_raw("Bush Food Plants", rules), "bush_tucker")

    def test_html_escaped_amp_case(self):
        # Guildford category strings arrive comma-joined and HTML-escaped;
        # rules match the verbatim string, no unescaping.
        rules = [{"match": "Berries &amp; Vines", "mode": "contains",
                  "category": "fruit"}]
        raw = "Fruits &amp; Nuts, Berries &amp; Vines, Australian Native Food Plants"
        self.assertEqual(match_category_raw(raw, rules), "fruit")
        self.assertEqual(
            match_category_raw(raw, RULES["guildford"]), "bush_tucker")

    def test_unknown_nursery_has_no_rules(self):
        cz = Categorizer(species_matcher=lambda t: None, nursery_rules=RULES)
        cat, source = cz.categorize("Mystery Plant", "no-such-nursery",
                                    "Bush Food Plants")
        self.assertEqual((cat, source), (None, "unclassified"))

    def test_empty_category_raw(self):
        self.assertIsNone(match_category_raw("", RULES["daleys"]))


class LoadRulesTest(unittest.TestCase):
    def test_missing_config_returns_empty(self):
        self.assertEqual(load_nursery_rules("/tmp/no-such-nursery-cats.json"), {})

    def test_committed_seed_file_is_valid(self):
        rules = load_nursery_rules()
        self.assertIn("daleys", rules)
        self.assertIn("guildford", rules)
        self.assertIn("ross-creek", rules)
        for nursery, nursery_rules in rules.items():
            for rule in nursery_rules:
                self.assertIn(rule["mode"], ("exact", "prefix", "contains"),
                              nursery)
                self.assertIn(rule["category"], KNOWN_CATEGORIES, nursery)
                self.assertTrue(rule["match"].strip(), nursery)

    def test_seed_semantics(self):
        rules = load_nursery_rules()
        self.assertEqual(
            match_category_raw("Bush Food Plants", rules["daleys"]), "bush_tucker")
        self.assertEqual(
            match_category_raw(
                "Edibles, Australian Native Food Plants", rules["guildford"]),
            "bush_tucker")
        self.assertEqual(
            match_category_raw("Australian Native", rules["ross-creek"]),
            "bush_tucker")


class KeywordHintTest(unittest.TestCase):
    def test_native_ornamental_vegetable_hints(self):
        self.assertEqual(keyword_hint("Banksia 'Giant Candles'"), "native")
        self.assertEqual(keyword_hint("Cordyline 'Rubra'"), "ornamental")
        self.assertEqual(keyword_hint("Asparagus Crown Purple"), "vegetable")

    def test_no_hint(self):
        self.assertIsNone(keyword_hint("Mango - Kensington Pride"))


class BuildNeedsReviewTest(unittest.TestCase):
    def test_counts_and_examples(self):
        cz = Categorizer(
            species_matcher=lambda t: "fruit" if "mango" in t.lower() else None,
            nursery_rules=RULES)
        products = [
            ("Mango - R2E2", "daleys", ""),
            ("Mystery One", "daleys", ""),
            ("Mystery Two", "daleys", ""),
            ("Banksia Candles", "ladybird", ""),
        ]
        report = build_needs_review(products, cz)
        daleys = report["nurseries"]["daleys"]
        self.assertEqual(daleys["total"], 3)
        self.assertEqual(daleys["unclassified"], 2)
        self.assertEqual(daleys["by_category"], {"fruit": 1})
        self.assertEqual(daleys["examples"], ["Mystery One", "Mystery Two"])
        ladybird = report["nurseries"]["ladybird"]
        self.assertEqual(ladybird["by_category"], {"native": 1})

    def test_examples_capped(self):
        cz = Categorizer(nursery_rules={})
        products = [(f"Mystery {i}", "x", "") for i in range(30)]
        report = build_needs_review(products, cz, max_examples=10)
        self.assertEqual(len(report["nurseries"]["x"]["examples"]), 10)
        self.assertEqual(report["nurseries"]["x"]["unclassified"], 30)


class DashboardIntegrationTest(unittest.TestCase):
    """build-dashboard wires rung 1 (match_species over ALL records) and the
    --needs-review-out writer."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "build_dashboard_cat", SCRAPERS / "build-dashboard.py")
        cls.bd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bd)

    def test_all_records_matcher_finds_fruit(self):
        matcher = self.bd._all_records_category_matcher()
        self.assertEqual(matcher("Mango - R2E2"), "fruit")
        self.assertIsNone(matcher("Cordyline 'Rubra'"))

    def test_write_needs_review_writes_json(self):
        products = [
            {"t": "Mango - R2E2", "nk": "daleys", "cat": "Fruit Trees"},
            {"t": "Mystery Plant", "nk": "daleys", "cat": "Shrubs"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "needs-review.json"
            self.bd.write_needs_review(products, out)
            report = json.loads(out.read_text())
            self.assertIn("generated_at", report)
            self.assertEqual(report["nurseries"]["daleys"]["total"], 2)
            self.assertEqual(report["nurseries"]["daleys"]["unclassified"], 1)


if __name__ == "__main__":
    unittest.main()
