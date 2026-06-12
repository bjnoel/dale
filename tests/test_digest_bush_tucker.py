"""
DAL-199: per-subscriber plant-category opt-in in the digest (bush tucker OFF by default).

The digest renders a subscriber's chosen plant categories: "fruit" -> the per-nursery fruit
sections; "bush_tucker" -> a clearly labelled bush tucker section. The default (no preference)
is fruit only, so bush tucker reaches no one who has not opted in.

Pins:
  - the title classifier routes only the pilot bush tucker species into the section, NOT the
    cross-listed fruits (Finger Lime, Desert Lime stay fruit);
  - fruit-only (the default) drops bush tucker items entirely;
  - bush-tucker-only renders just the labelled section;
  - both renders fruit sections plus the labelled section;
  - has_any_changes respects the plant categories (a fruit-only subscriber is not emailed when
    only bush tucker changed).

Run from repo root with: python3 -m unittest discover tests/
"""
import importlib.util
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


daily_digest = _load(SCRAPERS / "daily_digest.py")

FRUIT = ["fruit"]
BUSH = ["bush_tucker"]
BOTH = ["fruit", "bush_tucker"]

# A bush tucker restock (Lemon Myrtle) + new (Warrigal Greens), a price drop on a plain fruit
# (Apple), and a cross-listed fruit (Finger Lime) that must stay in the fruit flow.
CHANGES = {
    "ladybird": {
        "back_in_stock": [
            {"title": "Lemon Myrtle (Backhousia citriodora)", "price": 18.0,
             "old_price": None, "url": "https://lb.example/lemon-myrtle"},
            {"title": "Finger Lime - Alstonville", "price": 30.0,
             "old_price": None, "url": "https://lb.example/finger-lime"},
        ],
        "price_drops": [],
        "new_products": [
            {"title": "Warrigal Greens", "price": 12.0, "url": "https://lb.example/warrigal"},
        ],
    },
    "daleys": {
        "back_in_stock": [],
        "price_drops": [
            {"title": "Apple - Pink Lady", "old_price": 40.0, "new_price": 30.0,
             "url": "https://daleys.example/apple"},
        ],
        "new_products": [],
    },
}

# Only bush tucker changed (for the has_any plant-category gate).
BT_ONLY_CHANGES = {
    "ladybird": {
        "back_in_stock": [{"title": "Lemon Myrtle", "price": 18.0, "old_price": None, "url": ""}],
        "price_drops": [], "new_products": [],
    },
}


class ClassifierTest(unittest.TestCase):
    def test_pilot_species_match(self):
        self.assertTrue(daily_digest._is_bush_tucker("Lemon Myrtle 'Mini'"))
        self.assertTrue(daily_digest._is_bush_tucker("Warrigal Greens"))
        self.assertTrue(daily_digest._is_bush_tucker("Mountain Pepper MALE"))
        self.assertTrue(daily_digest._is_bush_tucker("Old Man Saltbush"))

    def test_cross_listed_fruits_stay_fruit(self):
        self.assertFalse(daily_digest._is_bush_tucker("Finger Lime - Alstonville"))
        self.assertFalse(daily_digest._is_bush_tucker("Desert Lime"))

    def test_plain_fruit_not_matched(self):
        self.assertFalse(daily_digest._is_bush_tucker("Apple - Pink Lady"))
        self.assertFalse(daily_digest._is_bush_tucker("Tahitian Lime"))


class BothCategoriesTest(unittest.TestCase):
    def test_html_sections_split(self):
        sections = daily_digest._build_change_sections(CHANGES, plant_categories=BOTH)
        names = [s["name"] for s in sections]
        self.assertIn("🌿 Bush tucker", names)
        bt = next(s for s in sections if s["name"] == "🌿 Bush tucker")
        bt_titles = {e["title"] for e in bt["entries"]}
        self.assertEqual(bt_titles,
                         {"Lemon Myrtle (Backhousia citriodora)", "Warrigal Greens"})
        self.assertTrue(all(e.get("note") for e in bt["entries"]))
        fruit = [s for s in sections if s["name"] != "🌿 Bush tucker"]
        fruit_titles = {e["title"] for s in fruit for e in s["entries"]}
        self.assertIn("Apple - Pink Lady", fruit_titles)
        self.assertIn("Finger Lime - Alstonville", fruit_titles)
        self.assertNotIn("Lemon Myrtle (Backhousia citriodora)", fruit_titles)

    def test_text_has_labelled_section(self):
        text = daily_digest.format_text(CHANGES, "2026-06-11", plant_categories=BOTH)
        self.assertIn("🌿 Bush tucker", text)
        bt_idx = text.index("🌿 Bush tucker")
        self.assertIn("Lemon Myrtle", text[bt_idx:])
        self.assertIn("Finger Lime", text[:bt_idx])  # cross-listed fruit stays above


class FruitOnlyDefaultTest(unittest.TestCase):
    def test_default_is_fruit_only(self):
        # No plant_categories arg -> the default is fruit only.
        default = daily_digest._build_change_sections(CHANGES)
        explicit = daily_digest._build_change_sections(CHANGES, plant_categories=FRUIT)
        self.assertEqual([s["name"] for s in default], [s["name"] for s in explicit])

    def test_fruit_only_drops_bush_tucker(self):
        sections = daily_digest._build_change_sections(CHANGES, plant_categories=FRUIT)
        self.assertNotIn("🌿 Bush tucker", [s["name"] for s in sections])
        titles = {e["title"] for s in sections for e in s["entries"]}
        self.assertIn("Apple - Pink Lady", titles)
        self.assertIn("Finger Lime - Alstonville", titles)  # cross-listed fruit kept
        self.assertNotIn("Lemon Myrtle (Backhousia citriodora)", titles)  # bush tucker dropped
        self.assertNotIn("Warrigal Greens", titles)

    def test_fruit_only_not_emailed_when_only_bush_tucker_changed(self):
        self.assertFalse(daily_digest.has_any_changes(BT_ONLY_CHANGES, plant_categories=FRUIT))
        self.assertTrue(daily_digest.has_any_changes(BT_ONLY_CHANGES, plant_categories=BUSH))


class BushTuckerOnlyTest(unittest.TestCase):
    def test_only_the_labelled_section(self):
        sections = daily_digest._build_change_sections(CHANGES, plant_categories=BUSH)
        names = [s["name"] for s in sections]
        self.assertEqual(names, ["🌿 Bush tucker"])  # no per-nursery fruit sections
        bt_titles = {e["title"] for s in sections for e in s["entries"]}
        self.assertNotIn("Apple - Pink Lady", bt_titles)
        self.assertNotIn("Finger Lime - Alstonville", bt_titles)


if __name__ == "__main__":
    unittest.main()
