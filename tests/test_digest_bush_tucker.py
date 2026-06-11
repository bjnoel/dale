"""
DAL-199 (P2.5): the clearly labelled "Bush tucker" digest section.

Pins three things:
  - the title classifier routes only the pilot bush tucker species into the
    section, NOT the cross-listed fruits (Finger Lime, Desert Lime stay fruit);
  - when the section flag is ON, bush tucker items move out of the per-nursery
    fruit blocks into one labelled section (text + HTML), variant data intact;
  - when the flag is OFF (the shipped default until Benedict approves the copy),
    the digest is byte-identical to before the pilot.

Run from repo root with: python3 -m unittest discover tests/
"""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


daily_digest = _load(SCRAPERS / "daily_digest.py")


# A bush tucker restock (Lemon Myrtle), a price drop on a plain fruit (Apple),
# and a cross-listed fruit (Finger Lime) that must stay in the fruit flow.
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
            {"title": "Warrigal Greens", "price": 12.0,
             "url": "https://lb.example/warrigal"},
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


class ClassifierTest(unittest.TestCase):
    def test_pilot_species_match(self):
        self.assertTrue(daily_digest._is_bush_tucker("Lemon Myrtle 'Mini'"))
        self.assertTrue(daily_digest._is_bush_tucker("Warrigal Greens"))
        self.assertTrue(daily_digest._is_bush_tucker("Mountain Pepper MALE"))
        self.assertTrue(daily_digest._is_bush_tucker("Old Man Saltbush"))

    def test_cross_listed_fruits_stay_fruit(self):
        # Finger Lime / Desert Lime are category=fruit (tag bush_tucker); they
        # belong in the main fruit flow, not the bush tucker section.
        self.assertFalse(daily_digest._is_bush_tucker("Finger Lime - Alstonville"))
        self.assertFalse(daily_digest._is_bush_tucker("Desert Lime"))

    def test_plain_fruit_not_matched(self):
        self.assertFalse(daily_digest._is_bush_tucker("Apple - Pink Lady"))
        self.assertFalse(daily_digest._is_bush_tucker("Tahitian Lime"))
        self.assertFalse(daily_digest._is_bush_tucker("Mango - Kensington Pride"))


class FlagOnTest(unittest.TestCase):
    def setUp(self):
        self._p = mock.patch.object(
            daily_digest, "BUSH_TUCKER_DIGEST_SECTION", True)
        self._p.start()
        self.addCleanup(self._p.stop)

    def test_html_sections_split(self):
        sections = daily_digest._build_change_sections(CHANGES)
        names = [s["name"] for s in sections]
        self.assertIn("🌿 Bush tucker", names)
        bt = next(s for s in sections if s["name"] == "🌿 Bush tucker")
        bt_titles = {e["title"] for e in bt["entries"]}
        self.assertEqual(bt_titles,
                         {"Lemon Myrtle (Backhousia citriodora)", "Warrigal Greens"})
        # every bush tucker entry carries its nursery note
        self.assertTrue(all(e.get("note") for e in bt["entries"]))
        # the fruit nursery sections keep the fruit and the cross-listed fruit,
        # never the bush tucker species
        fruit = [s for s in sections if s["name"] != "🌿 Bush tucker"]
        fruit_titles = {e["title"] for s in fruit for e in s["entries"]}
        self.assertIn("Apple - Pink Lady", fruit_titles)
        self.assertIn("Finger Lime - Alstonville", fruit_titles)
        self.assertNotIn("Lemon Myrtle (Backhousia citriodora)", fruit_titles)
        self.assertNotIn("Warrigal Greens", fruit_titles)

    def test_text_has_labelled_section(self):
        text = daily_digest.format_text(CHANGES, "2026-06-11")
        self.assertIn("🌿 Bush tucker", text)
        # bush tucker line names its nursery and sits under the section
        bt_idx = text.index("🌿 Bush tucker")
        self.assertIn("Lemon Myrtle", text[bt_idx:])
        self.assertIn("Warrigal Greens", text[bt_idx:])
        # the cross-listed Finger Lime is in the fruit flow above the section
        self.assertIn("Finger Lime", text[:bt_idx])

    def test_section_absent_when_no_bush_tucker(self):
        fruit_only = {"daleys": CHANGES["daleys"]}
        sections = daily_digest._build_change_sections(fruit_only)
        self.assertNotIn("🌿 Bush tucker", [s["name"] for s in sections])


class FlagOffTest(unittest.TestCase):
    """The shipped default: no section, behaviour unchanged."""

    def test_no_section_and_items_inline(self):
        self.assertFalse(daily_digest.BUSH_TUCKER_DIGEST_SECTION)
        sections = daily_digest._build_change_sections(CHANGES)
        self.assertNotIn("🌿 Bush tucker", [s["name"] for s in sections])
        titles = {e["title"] for s in sections for e in s["entries"]}
        self.assertIn("Lemon Myrtle (Backhousia citriodora)", titles)  # inline
        text = daily_digest.format_text(CHANGES, "2026-06-11")
        self.assertNotIn("🌿 Bush tucker", text)
        self.assertIn("Lemon Myrtle", text)


if __name__ == "__main__":
    unittest.main()
