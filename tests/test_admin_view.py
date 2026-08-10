"""
Tests for admin_view.build_admin_model — the pure aggregation behind the
read-only subscriber admin page (rendered by subscribe_server.py at /admin).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
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
        page = admin_view.render_subscribers_html(model, generated_at="2026-06-11 12:00")
        self.assertIn("noindex", page)
        self.assertIn("a@x.com", page)
        self.assertIn("Black Genoa Fig", page)
        self.assertIn("2026-06-11 12:00", page)

    def test_render_links_varieties_to_main_site(self):
        model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES)
        page = admin_view.render_subscribers_html(model)
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
        page = admin_view.render_subscribers_html(model)
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
        page = admin_view.render_nurseries_html(model)
        self.assertIn("Scraper health", page)

    def test_full_page_renders_without_health_key(self):
        # Direct render calls (and old callers) without a health key still work.
        model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES)
        page = admin_view.render_nurseries_html(model)
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
        page = admin_view.render_nurseries_html(model)
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



REGISTER = {
    "updated": "2026-08-03",
    "nurseries": [
        {
            "key": "daleys", "name": "Daleys", "status": "warm",
            "contact_name": "Correy", "email": "order@daleys.com.au",
            "touches": [
                {"date": "2026-04-25", "direction": "in", "by": "correy",
                 "channel": "email", "summary": "Warm reply"},
                {"date": "2026-03-30", "direction": "out", "by": "benedict",
                 "channel": "email", "summary": "Touch 1 goodwill intro"},
            ],
            "open_action": {"owner": "benedict", "what": "Touch 1.5 reply",
                            "since": "2026-04-25"},
            "notes": "Largest referral destination.",
        },
        {
            "key": "ladybird", "name": "Ladybird", "status": "not_contacted",
            "contact_form": "https://ladybird.example/contact", "touches": [],
        },
        {
            "key": "yalca", "name": "Yalca", "status": "contacted",
            "email": "info@yalca.com.au",
            "touches": [{"date": "2026-03-26", "direction": "out",
                         "by": "benedict", "channel": "email",
                         "summary": "Touch 1"}],
        },
    ],
}


class NurseryRegisterTests(unittest.TestCase):
    """The nursery relationship register on /admin (DAL-80)."""

    def model(self):
        from datetime import date
        return admin_view.build_nursery_model(REGISTER, today=date(2026, 8, 3))

    def test_totals(self):
        t = self.model()["totals"]
        self.assertEqual(t["nurseries"], 3)
        self.assertEqual(t["open_actions"], 1)
        self.assertEqual(t["never_contacted"], 1)

    def test_open_actions_sort_first_then_never_contacted(self):
        names = [r["name"] for r in self.model()["rows"]]
        self.assertEqual(names, ["Daleys", "Ladybird", "Yalca"])

    def test_undated_open_action_sorts_after_dated_ones(self):
        # An action with no "since" has an unknown age; it must not jump the
        # queue ahead of one we can prove has been open for 100 days.
        from datetime import date
        reg = {"updated": "2026-08-03", "nurseries": [
            {"key": "a", "name": "Aaa", "status": "not_contacted", "touches": [],
             "open_action": {"owner": "dale", "what": "no route found"}},
            {"key": "z", "name": "Zzz", "status": "warm", "touches": [],
             "open_action": {"owner": "benedict", "what": "reply",
                             "since": "2026-04-25"}},
        ]}
        model = admin_view.build_nursery_model(reg, today=date(2026, 8, 3))
        self.assertEqual([r["name"] for r in model["rows"]], ["Zzz", "Aaa"])

    def test_last_touch_is_the_newest_not_the_last_listed(self):
        # The fixture lists touches newest-first on purpose: the model must sort.
        row = self.model()["rows"][0]
        self.assertEqual(row["last_touch"], "2026-04-25")
        self.assertEqual(row["days_since"], 100)

    def test_touch_history_is_ordered_oldest_first(self):
        dates = [t["date"] for t in self.model()["rows"][0]["touches"]]
        self.assertEqual(dates, ["2026-03-30", "2026-04-25"])

    def test_never_contacted_has_no_last_touch(self):
        row = next(r for r in self.model()["rows"] if r["name"] == "Ladybird")
        self.assertIsNone(row["last_touch"])
        self.assertIsNone(row["days_since"])
        self.assertEqual(row["route"], "web form")

    def test_route_prefers_email(self):
        row = next(r for r in self.model()["rows"] if r["name"] == "Yalca")
        self.assertEqual(row["route"], "info@yalca.com.au")

    def test_missing_register_renders_a_named_absence_not_a_silent_gap(self):
        # DEC-249: an absence of data must not look like a zero.
        page = admin_view.render_nurseries_html(
            dict(admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES),
                 nurseries=None))
        self.assertIn("Nursery relationships", page)
        self.assertIn("No register deployed yet", page)

    def test_rendered_page_states_the_open_action_and_its_owner(self):
        # DEC-251: pin the text a human actually reads, not just the model.
        page = admin_view.render_nurseries_html(
            dict(admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES),
                 nurseries=self.model()))
        self.assertIn("1 open actions", page)
        self.assertIn("Touch 1.5 reply", page)
        self.assertIn("benedict", page)
        self.assertIn("Touch 1 goodwill intro", page)
        self.assertIn("Register updated 2026-08-03", page)

    def test_load_nursery_data_returns_none_when_file_absent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(admin_view.load_nursery_data(Path(tmp)))

    def test_load_nursery_data_reads_from_disk(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "nursery-contacts.json").write_text(json.dumps(REGISTER))
            model = admin_view.load_nursery_data(Path(tmp))
            self.assertEqual(model["totals"]["nurseries"], 3)


class TestNurserySectionTrim(unittest.TestCase):
    """The register used to render all 27 nurseries as two rows each, 55 rows at
    the top of /admin, when only 7 had an open action and 22 had never been
    contacted at all. Only the actionable ones stay visible now."""

    def _html(self):
        model = admin_view.build_nursery_model(REGISTER, date(2026, 8, 6))
        return admin_view._nursery_section(model)

    def _visible(self):
        """Everything before the collapsed block, i.e. what renders unexpanded."""
        return self._html().split("<details><summary>2 more")[0]

    def test_open_action_row_is_visible(self):
        self.assertIn("Daleys", self._visible())

    def test_quiet_nurseries_are_collapsed(self):
        visible = self._visible()
        self.assertNotIn("Ladybird", visible)
        self.assertNotIn("Yalca", visible)
        # ...but still present on the page, just behind the expander.
        self.assertIn("Ladybird", self._html())
        self.assertIn("Yalca", self._html())

    def test_collapsed_summary_counts_the_remainder(self):
        self.assertIn("2 more nurseries, nothing outstanding", self._html())

    def test_no_empty_history_expander(self):
        """Ladybird has no touches and no notes, so it gets no expander at all.
        Every never-contacted nursery used to render 'History (0)'."""
        self.assertNotIn("History (0)", self._html())

    def test_notes_only_nursery_is_labelled_notes_not_history(self):
        register = {"updated": "2026-08-03", "nurseries": [
            {"key": "n", "name": "NotesOnly", "status": "not_contacted",
             "touches": [], "notes": "Ships nationally."}]}
        html = admin_view._nursery_section(
            admin_view.build_nursery_model(register, date(2026, 8, 6)))
        self.assertIn("Notes", html)
        self.assertIn("Ships nationally.", html)
        self.assertNotIn("History (0)", html)

    def test_history_still_rendered_where_it_exists(self):
        html = self._html()
        self.assertIn("History (2)", html)   # Daleys
        self.assertIn("History (1)", html)   # Yalca
        self.assertIn("Touch 1 goodwill intro", html)

    def test_headline_counts_still_cover_everything(self):
        html = self._html()
        self.assertIn("3 nurseries", html)
        self.assertIn("1 open actions", html)

    def test_all_nurseries_actionable_means_no_collapsed_block(self):
        register = {"updated": "x", "nurseries": [
            {"key": "a", "name": "A", "status": "warm", "touches": [],
             "open_action": {"owner": "benedict", "what": "do", "since": "2026-01-01"}}]}
        html = admin_view._nursery_section(
            admin_view.build_nursery_model(register, date(2026, 8, 6)))
        self.assertNotIn("nothing outstanding", html)

    def test_no_open_actions_says_so(self):
        register = {"updated": "x", "nurseries": [
            {"key": "a", "name": "A", "status": "not_contacted", "touches": []}]}
        html = admin_view._nursery_section(
            admin_view.build_nursery_model(register, date(2026, 8, 6)))
        self.assertIn("No open actions", html)
        self.assertIn("1 more nursery, nothing outstanding", html)


class TestPageSplit(unittest.TestCase):
    """The complaint that started this: /admin was one long wall of text, and
    the nursery register owned the top of it. The answer used to be section
    order; since 2026-08-10 it is separate pages. What has to stay true is that
    the landing page carries the actionable state and nothing else."""

    def full_model(self):
        model = admin_view.build_admin_model(SUBSCRIBERS, PENDING, WATCHES)
        model["nurseries"] = admin_view.build_nursery_model(REGISTER, date(2026, 8, 6))
        model["business"] = SNAPSHOT
        model["health"] = admin_view.build_health_model(
            [("2026-06-11", [_hrec("daleys")])])
        return model

    def test_landing_page_is_business_state_only(self):
        html = admin_view.render_business_html(self.full_model())
        self.assertIn("Business state", html)
        # The three things that used to bury it.
        self.assertNotIn("Nursery relationships", html)
        self.assertNotIn("Scraper health", html)
        self.assertNotIn("Top watched varieties", html)

    def test_subscribers_page_has_no_nursery_or_business_sections(self):
        html = admin_view.render_subscribers_html(self.full_model())
        self.assertIn("Top watched varieties", html)
        self.assertNotIn("Nursery relationships", html)
        # The section, not the nav tab of the same name.
        self.assertNotIn("<h2>Business state</h2>", html)

    def test_nurseries_page_groups_register_with_scraper_health(self):
        html = admin_view.render_nurseries_html(self.full_model())
        self.assertIn("Nursery relationships", html)
        self.assertIn("Scraper health", html)
        self.assertIn("Needs review", html)
        self.assertNotIn("<h2>Business state</h2>", html)

    def test_every_page_carries_the_same_nav(self):
        model = self.full_model()
        for render in (admin_view.render_business_html,
                       admin_view.render_subscribers_html,
                       admin_view.render_nurseries_html):
            html = render(model)
            for path, label in admin_view.ADMIN_PAGES:
                with self.subTest(render=render.__name__, path=path):
                    self.assertIn(f'href="{path}"', html)
                    self.assertIn(label, html)

    def test_nav_marks_the_current_page_once(self):
        pairs = [
            ("/admin", admin_view.render_business_html),
            ("/admin/subscribers", admin_view.render_subscribers_html),
            ("/admin/nurseries", admin_view.render_nurseries_html),
        ]
        for path, render in pairs:
            with self.subTest(path=path):
                html = render(self.full_model())
                self.assertEqual(html.count('class="here"'), 1)
                self.assertIn(f'<a href="{path}" class="here">', html)

    def test_business_state_is_the_first_tab(self):
        # Actionable state still leads, now by tab order rather than by scroll.
        self.assertEqual(admin_view.ADMIN_PAGES[0][0], "/admin")

    def test_every_tab_has_a_renderer_or_is_the_digest(self):
        # A tab that 404s is worse than no tab. /admin/digest is served by
        # digest_archive, so it is the one legitimate absence here.
        for path, _ in admin_view.ADMIN_PAGES:
            with self.subTest(path=path):
                self.assertTrue(
                    path in admin_view.ADMIN_RENDERERS or path == "/admin/digest")


SNAPSHOT = {
    "generated_at": "2026-08-06T22:00:00+00:00",
    "waiting_on_benedict": [
        {"id": "DAL-177", "title": "Store description variant", "state": "Todo",
         "days": 101, "assigned": True},
        {"id": "DAL-274", "title": "Draft nursery replies", "state": "Backlog",
         "days": 3, "assigned": False},
    ],
    "verdicts_recent": [{
        "ticket": "DAL-219", "metric": "treesmith_downloads",
        "baseline": {"value": 49, "unit": "installs/28d"},
        "verdict": {"value": 61, "pct": 24.5, "call": "moved"},
    }],
    "verdicts_summary": {"awaiting": 4, "ungraded": 2, "next_due": "2026-09-01"},
    "traffic": {"sites": [{"site": "treestock.com.au", "month_visitors": 2926,
                           "month_change": 8, "week_visitors": 690,
                           "week_change": -3}]},
}


class TestBusinessSection(unittest.TestCase):
    """The /admin business block: the always-on 'what is true now' surface."""

    def test_load_marks_a_fresh_snapshot_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "business-snapshot.json").write_text(json.dumps(SNAPSHOT))
            snap = admin_view.load_business_data(
                Path(tmp), now=datetime.fromisoformat("2026-08-07T02:00:00+00:00"))
            self.assertFalse(snap["stale"])
            self.assertEqual(snap["age_hours"], 4.0)

    def test_load_marks_an_old_snapshot_stale(self):
        """A dead digest cron must not leave the page showing confident numbers
        as if they were current."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "business-snapshot.json").write_text(json.dumps(SNAPSHOT))
            snap = admin_view.load_business_data(
                Path(tmp), now=datetime.fromisoformat("2026-08-09T22:00:00+00:00"))
            self.assertTrue(snap["stale"])
            html = admin_view._business_section(snap)
            self.assertIn("Stale", html)

    def test_missing_snapshot_is_none_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(admin_view.load_business_data(Path(tmp)))
        self.assertIn("No snapshot yet", admin_view._business_section(None))

    def test_corrupt_snapshot_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "business-snapshot.json").write_text("{not json")
            self.assertIsNone(admin_view.load_business_data(Path(tmp)))

    def test_section_renders_waiting_verdicts_and_traffic(self):
        html = admin_view._business_section(SNAPSHOT)
        self.assertIn("DAL-177", html)
        self.assertIn("DAL-219", html)
        self.assertIn("treestock.com.au", html)
        self.assertIn("2926", html)

    def test_stale_row_gets_one_class_attribute_not_two(self):
        """A second `class` on the same tag is ignored by every browser, which
        would silently drop the over-30-days highlight."""
        html = admin_view._waiting_table(SNAPSHOT["waiting_on_benedict"])
        self.assertIn("class='num action'", html)
        self.assertNotIn("class='num' class=", html)

    def test_empty_waiting_list(self):
        self.assertIn("Nothing is blocked", admin_view._waiting_table([]))


if __name__ == "__main__":
    unittest.main()
