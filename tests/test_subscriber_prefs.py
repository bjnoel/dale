"""
Tests for the daily digest category filter and the subscriber-schema
fallback helpers used by send_digest.py.

Run from repo root with:
    python3 -m unittest discover tests/
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
send_digest = _load(SCRAPERS / "send_digest.py")


SAMPLE_CHANGES = {
    "daleys": {
        "back_in_stock": [
            {"title": "Rollinia", "price": 25.0, "url": "https://daleys.example/rollinia"},
        ],
        "price_drops": [
            {
                "title": "Soursop",
                "old_price": 35.0,
                "new_price": 28.0,
                "url": "https://daleys.example/soursop",
            }
        ],
        "new_products": [
            {"title": "Wax Apple", "price": 19.95, "url": "https://daleys.example/wax-apple"},
        ],
    }
}


class TestCategoryFilter(unittest.TestCase):
    def test_default_includes_all_three_sections(self):
        html = daily_digest.format_html(SAMPLE_CHANGES, "2026-05-28")
        self.assertIn("Rollinia", html)         # back_in_stock
        self.assertIn("Soursop", html)          # price_drops
        self.assertIn("Wax Apple", html)        # new_products
        self.assertNotIn("No changes today", html)

    def test_price_drops_only_excludes_other_sections(self):
        html = daily_digest.format_html(
            SAMPLE_CHANGES, "2026-05-28", categories={"price_drops"}
        )
        self.assertIn("Soursop", html)
        self.assertNotIn("Rollinia", html)
        self.assertNotIn("Wax Apple", html)

    def test_back_in_stock_only(self):
        html = daily_digest.format_html(
            SAMPLE_CHANGES, "2026-05-28", categories={"back_in_stock"}
        )
        self.assertIn("Rollinia", html)
        self.assertNotIn("Soursop", html)
        self.assertNotIn("Wax Apple", html)

    def test_unknown_category_is_silently_dropped(self):
        # Unknown values shouldn't crash; valid ones still work.
        html = daily_digest.format_html(
            SAMPLE_CHANGES, "2026-05-28", categories={"new_products", "nonsense"}
        )
        self.assertIn("Wax Apple", html)
        self.assertNotIn("Soursop", html)

    def test_empty_categories_yields_no_changes_today(self):
        # A subscriber who muted every category should see the "all quiet" line
        # if we rendered for them at all. (In practice send_digest.py short-
        # circuits before calling format_html, but the function must still be
        # safe to call.)
        html = daily_digest.format_html(SAMPLE_CHANGES, "2026-05-28", categories=set())
        self.assertIn("No changes today", html)

    def test_has_any_changes_respects_category_filter(self):
        self.assertTrue(daily_digest.has_any_changes(SAMPLE_CHANGES))
        self.assertTrue(
            daily_digest.has_any_changes(SAMPLE_CHANGES, categories={"price_drops"})
        )
        # Empty category set means nothing matches.
        self.assertFalse(daily_digest.has_any_changes(SAMPLE_CHANGES, categories=set()))
        # A category that has no items in the sample is False.
        empty_sample = {"unknown_nursery": {"back_in_stock": [], "price_drops": [], "new_products": []}}
        self.assertFalse(daily_digest.has_any_changes(empty_sample))

    def test_format_text_respects_categories(self):
        text = daily_digest.format_text(
            SAMPLE_CHANGES, "2026-05-28", categories={"price_drops"}
        )
        self.assertIn("Soursop", text)
        self.assertNotIn("Rollinia", text)
        self.assertNotIn("Wax Apple", text)


class TestSubscriberSchemaFallbacks(unittest.TestCase):
    def test_categories_default_is_all_three(self):
        legacy = {"email": "x@example.com", "state": "ALL"}
        self.assertEqual(
            send_digest.get_subscriber_categories(legacy),
            frozenset(daily_digest.ALL_CATEGORIES),
        )

    def test_categories_preserves_stored_subset(self):
        sub = {"email": "x@example.com", "categories": ["price_drops"]}
        self.assertEqual(
            send_digest.get_subscriber_categories(sub),
            frozenset({"price_drops"}),
        )

    def test_categories_drops_unknown_values(self):
        sub = {"email": "x@example.com", "categories": ["price_drops", "nonsense"]}
        self.assertEqual(
            send_digest.get_subscriber_categories(sub),
            frozenset({"price_drops"}),
        )

    def test_categories_empty_list_means_all_muted(self):
        # Distinct from "missing field" (which defaults to all three).
        sub = {"email": "x@example.com", "categories": []}
        self.assertEqual(send_digest.get_subscriber_categories(sub), frozenset())

    def test_frequency_defaults_to_daily(self):
        self.assertEqual(
            send_digest.get_subscriber_frequency({"email": "x@example.com"}),
            "daily",
        )

    def test_frequency_returns_stored_value(self):
        self.assertEqual(
            send_digest.get_subscriber_frequency(
                {"email": "x@example.com", "frequency": "weekly"}
            ),
            "weekly",
        )
        self.assertEqual(
            send_digest.get_subscriber_frequency(
                {"email": "x@example.com", "frequency": "off"}
            ),
            "off",
        )

    def test_frequency_falls_back_for_invalid_value(self):
        # Garbage in subscribers.json shouldn't break the daily run.
        self.assertEqual(
            send_digest.get_subscriber_frequency(
                {"email": "x@example.com", "frequency": "hourly"}
            ),
            "daily",
        )

    def test_state_legacy_wa_only_flag(self):
        # Pre-state schema: wa_only=true means WA.
        self.assertEqual(
            send_digest.get_subscriber_state({"email": "x@example.com", "wa_only": True}),
            "WA",
        )
        # No state and no wa_only → ALL.
        self.assertEqual(
            send_digest.get_subscriber_state({"email": "x@example.com"}),
            "ALL",
        )


if __name__ == "__main__":
    unittest.main()
