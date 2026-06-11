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


class BuildAdminModelTest(unittest.TestCase):
    def setUp(self):
        self.model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES)

    def test_totals(self):
        t = self.model["totals"]
        self.assertEqual(t["subscribers"], 3)
        self.assertEqual(t["pending"], 1)
        self.assertEqual(t["watches"], 3)
        self.assertEqual(t["watchers"], 2)  # a@x.com and d@x.com
        self.assertNotIn("wishlist_votes", t)  # wishlist no longer tracked

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
        # Watches are (title, slug) pairs so the renderer can link to the variety page.
        by_email = {r["email"]: r for r in self.model["subscribers"]}
        self.assertEqual(
            by_email["a@x.com"]["watches"],
            [("Black Genoa Fig", "fig-black-genoa"), ("KP Mango", "mango-kp")],
        )
        self.assertEqual(by_email["b@x.com"]["watches"], [])

    def test_subscribers_sorted_newest_first(self):
        emails = [r["email"] for r in self.model["subscribers"]]
        self.assertEqual(emails, ["a@x.com", "b@x.com", "c@x.com"])

    def test_watch_only_excludes_subscribers(self):
        # d@x.com has a watch but is not in subscribers.json.
        watch_only = self.model["watch_only"]
        self.assertEqual(len(watch_only), 1)
        self.assertEqual(watch_only[0]["email"], "d@x.com")
        self.assertEqual(watch_only[0]["watches"], [("Black Genoa Fig", "fig-black-genoa")])

    def test_top_varieties_by_slug_with_title(self):
        # (slug, title, count), most-watched first.
        self.assertEqual(
            self.model["top_varieties"],
            [("fig-black-genoa", "Black Genoa Fig", 2), ("mango-kp", "KP Mango", 1)],
        )

    def test_no_wishlist_key(self):
        self.assertNotIn("top_wishlist", self.model)

    def test_pending_rows(self):
        self.assertEqual(
            self.model["pending"],
            [{"email": "p@x.com", "state": "NSW", "requested_at": "2026-06-11"}],
        )

    def test_short_date_truncation(self):
        by_email = {r["email"]: r for r in self.model["subscribers"]}
        self.assertEqual(by_email["a@x.com"]["subscribed_at"], "2026-06-10")

    def test_empty_inputs(self):
        model = admin_view.build_admin_model([], [], [])
        self.assertEqual(model["totals"]["subscribers"], 0)
        self.assertEqual(model["subscribers"], [])
        self.assertEqual(model["top_varieties"], [])


class RenderAdminHtmlTest(unittest.TestCase):
    def test_render_contains_data_and_is_noindex(self):
        model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES)
        page = admin_view.render_admin_html(model, generated_at="2026-06-11 12:00")
        self.assertIn("noindex", page)
        self.assertIn("a@x.com", page)
        self.assertIn("Black Genoa Fig", page)
        self.assertIn("2026-06-11 12:00", page)

    def test_render_links_varieties_to_main_site(self):
        model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES)
        page = admin_view.render_admin_html(model)
        self.assertIn(
            'href="https://treestock.com.au/variety/fig-black-genoa.html"', page
        )
        # Wishlist section is gone.
        self.assertNotIn("wishlist", page.lower())

    def test_render_escapes_html_in_titles(self):
        watches = [("z@x.com", "evil", "<script>alert(1)</script>", "sp", "2026-06-10")]
        model = admin_view.build_admin_model(
            [{"email": "z@x.com", "state": "ALL", "subscribed_at": "2026-06-10"}],
            [], watches,
        )
        page = admin_view.render_admin_html(model)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)


def _hrec(nursery, ok=True, products=100, error=None, ts="2026-06-11T01:00:00"):
    return {"ts": ts, "nursery": nursery, "ok": ok, "products": products,
            "in_stock": 50, "duration_s": 1.0, "http_403": 0, "http_429": 0,
            "error": error}


class BuildHealthModelTest(unittest.TestCase):
    """The scrape-health grid behind the /admin panel (DAL-193 P0.3)."""

    def test_empty_input_renders_empty_state(self):
        model = admin_view.build_health_model([])
        self.assertEqual(model["rows"], [])
        page = admin_view._health_section(model)
        self.assertIn("No scrape-health records yet", page)

    def test_statuses_ok_fail_zero_and_gap(self):
        day_records = [
            ("2026-06-11", [_hrec("daleys"),
                            _hrec("ladybird", ok=False, products=0, error="HTTP 500"),
                            _hrec("fruitopia", products=0)]),
            ("2026-06-10", [_hrec("daleys")]),
        ]
        model = admin_view.build_health_model(day_records)
        rows = {r["nursery"]: r for r in model["rows"]}
        # Days run oldest -> newest.
        self.assertEqual(model["days"], ["2026-06-10", "2026-06-11"])
        self.assertEqual(rows["daleys"]["cells"], ["ok", "ok"])
        self.assertEqual(rows["ladybird"]["cells"], [None, "fail"])
        self.assertEqual(rows["fruitopia"]["cells"], [None, "zero"])

    def test_last_success_and_latest_products(self):
        day_records = [
            ("2026-06-11", [_hrec("daleys", ok=False, products=0,
                                  ts="2026-06-11T01:00:00")]),
            ("2026-06-10", [_hrec("daleys", products=617,
                                  ts="2026-06-10T01:00:00")]),
        ]
        model = admin_view.build_health_model(day_records)
        row = model["rows"][0]
        self.assertEqual(row["last_success"], "2026-06-10T01:00:00")
        self.assertEqual(row["latest_products"], 0)

    def test_rerun_same_day_last_record_wins(self):
        day_records = [
            ("2026-06-11", [_hrec("daleys", ok=False, products=0), _hrec("daleys")]),
        ]
        model = admin_view.build_health_model(day_records)
        self.assertEqual(model["rows"][0]["cells"], ["ok"])

    def test_recent_errors_newest_first_and_capped(self):
        day_records = [
            ("2026-06-11", [_hrec("daleys", ok=False, products=0, error="new boom")]),
            ("2026-06-10", [_hrec("daleys", ok=False, products=0, error="old boom")]),
        ]
        model = admin_view.build_health_model(day_records)
        self.assertEqual([e["error"] for e in model["recent_errors"]],
                         ["new boom", "old boom"])

    def test_render_mixed_records(self):
        day_records = [
            ("2026-06-11", [_hrec("daleys", products=617),
                            _hrec("ladybird", ok=False, products=0,
                                  error="HTTP 403 https://x")]),
        ]
        page = admin_view._health_section(admin_view.build_health_model(day_records))
        self.assertIn("daleys", page)
        self.assertIn("617", page)
        self.assertIn("Recent errors", page)
        self.assertIn("HTTP 403 https://x", page)

    def test_render_escapes_error_text(self):
        day_records = [
            ("2026-06-11", [_hrec("daleys", ok=False, products=0,
                                  error="<img onerror=x>")]),
        ]
        page = admin_view._health_section(admin_view.build_health_model(day_records))
        self.assertNotIn("<img onerror=x>", page)

    def test_full_page_includes_health_section(self):
        model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES)
        model["health"] = admin_view.build_health_model(
            [("2026-06-11", [_hrec("daleys")])])
        page = admin_view.render_admin_html(model)
        self.assertIn("Scraper health", page)

    def test_full_page_renders_without_health_key(self):
        # Direct render calls (and old callers) without a health key still work.
        model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES)
        page = admin_view.render_admin_html(model)
        self.assertIn("No scrape-health records yet", page)

    def test_needs_review_section_renders_counts(self):
        report = {
            "generated_at": "2026-06-11T12:00:00+00:00",
            "nurseries": {
                "daleys": {"total": 600, "unclassified": 40,
                           "by_category": {"fruit": 560},
                           "examples": ["Mystery One", "Mystery Two"]},
            },
        }
        page = admin_view._needs_review_section(report)
        self.assertIn("daleys", page)
        self.assertIn("40", page)
        self.assertIn("Mystery One", page)
        self.assertIn("7%", page)  # 40/600

    def test_needs_review_empty_state(self):
        page = admin_view._needs_review_section(None)
        self.assertIn("No needs-review report yet", page)

    def test_full_page_includes_needs_review_section(self):
        model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES)
        page = admin_view.render_admin_html(model)
        self.assertIn("Needs review", page)

    def test_load_health_data_reads_from_disk(self):
        import tempfile
        from datetime import date
        from stocklib.scrape_health import append_record
        with tempfile.TemporaryDirectory() as tmp:
            health_dir = Path(tmp) / "scraper-health"
            append_record(_hrec("daleys"), health_dir)
            model = admin_view.load_health_data(Path(tmp), today=date.today())
            self.assertEqual(len(model["rows"]), 1)
            self.assertEqual(model["rows"][0]["nursery"], "daleys")


if __name__ == "__main__":
    unittest.main()
