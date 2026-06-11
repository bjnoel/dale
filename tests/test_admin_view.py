"""
Tests for admin_view.build_admin_model — the pure aggregation behind the
read-only subscriber admin page (rendered by subscribe_server.py at /admin).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import admin_view


SUBSCRIBERS = [
    {"email": "a@x.com", "state": "WA", "frequency": "daily",
     "categories": ["new_products"], "subscribed_at": "2026-06-10T09:00:00"},
    # No categories field -> defaults to all three; explicit weekly frequency.
    {"email": "b@x.com", "state": "ALL", "frequency": "weekly",
     "subscribed_at": "2026-06-09T09:00:00"},
    # Legacy wa_only -> WA; empty categories -> none; off frequency.
    {"email": "c@x.com", "wa_only": True, "frequency": "off",
     "categories": [], "subscribed_at": "2026-06-08T09:00:00"},
]

PENDING = [
    {"email": "p@x.com", "state": "NSW", "requested_at": "2026-06-11T08:00:00"},
]

# (email, variety_slug, variety_title, species_slug, added_at)
WATCHES = [
    ("a@x.com", "fig-black-genoa", "Black Genoa Fig", "fig", "2026-06-10T10:00:00"),
    ("a@x.com", "mango-kp", "KP Mango", "mango", "2026-06-10T10:05:00"),
    ("d@x.com", "fig-black-genoa", "Black Genoa Fig", "fig", "2026-06-11T11:00:00"),
]

# (email, species_slug, added_at)
WISHLIST = [
    ("a@x.com", "durian", "2026-06-10T10:00:00"),
    ("e@x.com", "durian", "2026-06-11T10:00:00"),
    ("a@x.com", "mangosteen", "2026-06-10T10:01:00"),
]


class BuildAdminModelTest(unittest.TestCase):
    def setUp(self):
        self.model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES, WISHLIST)

    def test_totals(self):
        t = self.model["totals"]
        self.assertEqual(t["subscribers"], 3)
        self.assertEqual(t["pending"], 1)
        self.assertEqual(t["watches"], 3)
        self.assertEqual(t["watchers"], 2)  # a@x.com and d@x.com
        self.assertEqual(t["wishlist_votes"], 3)

    def test_by_state_legacy_wa_only(self):
        # c@x.com uses legacy wa_only -> WA. Only nonzero states, in STATES order.
        self.assertEqual(self.model["by_state"], [("ALL", 1), ("WA", 2)])

    def test_by_frequency(self):
        self.assertEqual(
            self.model["by_frequency"],
            [("daily", 1), ("weekly", 1), ("off", 1)],
        )

    def test_by_category_defaults_and_empty(self):
        # b has no categories field -> all three; a -> new_products only; c -> none.
        self.assertEqual(
            dict(self.model["by_category"]),
            {"new_products": 2, "price_drops": 1, "back_in_stock": 1},
        )

    def test_subscriber_watch_join(self):
        by_email = {r["email"]: r for r in self.model["subscribers"]}
        self.assertEqual(by_email["a@x.com"]["watches"], ["Black Genoa Fig", "KP Mango"])
        self.assertEqual(by_email["b@x.com"]["watches"], [])

    def test_subscribers_sorted_newest_first(self):
        emails = [r["email"] for r in self.model["subscribers"]]
        self.assertEqual(emails, ["a@x.com", "b@x.com", "c@x.com"])

    def test_watch_only_excludes_subscribers(self):
        # d@x.com has a watch but is not in subscribers.json.
        watch_only = self.model["watch_only"]
        self.assertEqual(len(watch_only), 1)
        self.assertEqual(watch_only[0]["email"], "d@x.com")
        self.assertEqual(watch_only[0]["watches"], ["Black Genoa Fig"])

    def test_top_varieties(self):
        self.assertEqual(
            self.model["top_varieties"],
            [("Black Genoa Fig", 2), ("KP Mango", 1)],
        )

    def test_top_wishlist(self):
        self.assertEqual(
            self.model["top_wishlist"],
            [("durian", 2), ("mangosteen", 1)],
        )

    def test_pending_rows(self):
        self.assertEqual(
            self.model["pending"],
            [{"email": "p@x.com", "state": "NSW", "requested_at": "2026-06-11"}],
        )

    def test_short_date_truncation(self):
        by_email = {r["email"]: r for r in self.model["subscribers"]}
        self.assertEqual(by_email["a@x.com"]["subscribed_at"], "2026-06-10")

    def test_empty_inputs(self):
        model = admin_view.build_admin_model([], [], [], [])
        self.assertEqual(model["totals"]["subscribers"], 0)
        self.assertEqual(model["subscribers"], [])
        self.assertEqual(model["top_varieties"], [])


class RenderAdminHtmlTest(unittest.TestCase):
    def test_render_contains_data_and_is_noindex(self):
        model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES, WISHLIST)
        page = admin_view.render_admin_html(model, generated_at="2026-06-11 12:00")
        self.assertIn("noindex", page)
        self.assertIn("a@x.com", page)
        self.assertIn("Black Genoa Fig", page)
        self.assertIn("2026-06-11 12:00", page)

    def test_render_escapes_html_in_titles(self):
        watches = [("z@x.com", "evil", "<script>alert(1)</script>", "sp", "2026-06-10")]
        model = admin_view.build_admin_model(
            [{"email": "z@x.com", "state": "ALL", "subscribed_at": "2026-06-10"}],
            [], watches, [],
        )
        page = admin_view.render_admin_html(model)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)


if __name__ == "__main__":
    unittest.main()
