"""
Tests for the per-variety alert engine (send_variety_alerts.py).

These pin the behaviour added when variety alerts became treestock's primary
capture channel:

  * a price-drop trigger alongside the restock one, gated on BOTH a percentage
    and a dollar floor so small wobbles do not send email;
  * a cooldown, because the old dedupe only covered the current day and stock
    flickering 0 -> >0 -> 0 -> >0 re-alerted forever (tamarillo-red went out 8
    separate times to each of two people);
  * restock beating price drop when both fire on the same variety, so nobody
    gets two emails about one plant on one day;
  * variant display titles slugging back to the variety they belong to, which
    is what maps a variant-level price comparison onto a watch.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import sqlite3
import sys
import tempfile
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


alerts = _load(SCRAPERS / "send_variety_alerts.py")

from cultivar_parsing import product_variety_slug  # noqa: E402
from stocklib import changes as changes_mod  # noqa: E402
from stocklib import variety_index as variety_index_mod  # noqa: E402


def _make_db(path: Path):
    """A watches DB shaped like the pre-alert_type production one, so the
    migration is exercised rather than assumed."""
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE watches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL,
        variety_slug TEXT NOT NULL, species_slug TEXT NOT NULL,
        variety_title TEXT NOT NULL, added_at TEXT NOT NULL,
        UNIQUE(email, variety_slug))""")
    con.execute("""CREATE TABLE sends (
        id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL,
        variety_slug TEXT NOT NULL, sent_at TEXT NOT NULL,
        UNIQUE(email, variety_slug, sent_at))""")
    con.commit()
    con.close()


class QualifyingDropTests(unittest.TestCase):
    """Both floors must clear: MIN_DROP_PCT and MIN_DROP_ABS."""

    def test_clears_both_floors(self):
        self.assertTrue(alerts.qualifying_drop(60.00, 50.00))   # 16.7%, $10

    def test_percentage_too_small(self):
        # $200 -> $190 is a $10 drop but only 5%.
        self.assertFalse(alerts.qualifying_drop(200.00, 190.00))

    def test_dollars_too_small(self):
        # $30 -> $27 is 10% but only $3.
        self.assertFalse(alerts.qualifying_drop(30.00, 27.00))

    def test_boundary_is_inclusive(self):
        # Exactly 10% and exactly $5.
        self.assertTrue(alerts.qualifying_drop(50.00, 45.00))

    def test_price_rise_never_qualifies(self):
        self.assertFalse(alerts.qualifying_drop(45.00, 60.00))

    def test_missing_or_junk_prices_do_not_fire(self):
        for old, new in ((None, 20.0), (20.0, None), ("POA", 20.0), (0, 0)):
            with self.subTest(old=old, new=new):
                self.assertFalse(alerts.qualifying_drop(old, new))


class CooldownTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "variety_watches.db"
        _make_db(self.db)
        self._orig = alerts.VARIETY_WATCHES_DB
        alerts.VARIETY_WATCHES_DB = self.db

    def tearDown(self):
        alerts.VARIETY_WATCHES_DB = self._orig
        self.tmp.cleanup()

    def test_migration_adds_alert_type_and_backfills_restock(self):
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO sends (email, variety_slug, sent_at) VALUES (?,?,?)",
                    ("a@example.com", "tamarillo-red", "2026-07-01"))
        con.commit()
        alerts.ensure_schema(con)
        cols = {r[1] for r in con.execute("PRAGMA table_info(sends)")}
        self.assertIn("alert_type", cols)
        row = con.execute("SELECT alert_type FROM sends").fetchone()
        self.assertEqual(row[0], alerts.RESTOCK)
        con.close()

    def test_migration_is_idempotent(self):
        con = sqlite3.connect(self.db)
        alerts.ensure_schema(con)
        alerts.ensure_schema(con)   # must not raise "duplicate column name"
        con.close()

    def test_repeat_inside_cooldown_is_suppressed(self):
        """The tamarillo-red bug: flickering stock re-alerting every time."""
        alerts.record_send("a@example.com", "tamarillo-red", "2026-07-01", alerts.RESTOCK)
        last = alerts.last_sent_map()
        self.assertTrue(alerts.in_cooldown(
            last, "a@example.com", "tamarillo-red", alerts.RESTOCK, "2026-07-20"))

    def test_repeat_after_cooldown_is_allowed(self):
        alerts.record_send("a@example.com", "tamarillo-red", "2026-07-01", alerts.RESTOCK)
        last = alerts.last_sent_map()
        self.assertFalse(alerts.in_cooldown(
            last, "a@example.com", "tamarillo-red", alerts.RESTOCK, "2026-08-05"))

    def test_cooldown_is_per_person(self):
        alerts.record_send("a@example.com", "tamarillo-red", "2026-07-01", alerts.RESTOCK)
        last = alerts.last_sent_map()
        self.assertFalse(alerts.in_cooldown(
            last, "b@example.com", "tamarillo-red", alerts.RESTOCK, "2026-07-02"))

    def test_cooldown_is_per_trigger(self):
        """A restock does not block a later price drop, only another restock."""
        alerts.record_send("a@example.com", "mango-r2e2", "2026-07-01", alerts.RESTOCK)
        last = alerts.last_sent_map()
        self.assertFalse(alerts.in_cooldown(
            last, "a@example.com", "mango-r2e2", alerts.PRICE_DROP, "2026-07-10"))

    def test_one_email_per_variety_per_day_across_triggers(self):
        """Same day is the one case where the triggers do block each other."""
        alerts.record_send("a@example.com", "mango-r2e2", "2026-07-01", alerts.RESTOCK)
        last = alerts.last_sent_map()
        self.assertTrue(alerts.sent_same_day(last, "a@example.com", "mango-r2e2", "2026-07-01"))
        self.assertFalse(alerts.sent_same_day(last, "a@example.com", "mango-r2e2", "2026-07-02"))


class PriceDropDetectionTests(unittest.TestCase):
    """End to end over real snapshot files, through stocklib.changes."""

    def _snapshot(self, day_dir: Path, price: float, available: bool = True):
        day_dir.parent.mkdir(parents=True, exist_ok=True)
        day_dir.write_text(json.dumps({
            "nursery_name": "Daleys Fruit Trees",
            "products": [{
                "title": "Mango - R2E2",
                "url": "https://daleys.example/mango-r2e2",
                # Daleys' FRUIT_FILTERS entry is category-mode, so a fixture
                # without this is filtered out exactly as the digest would
                # filter it.
                "category": "Fruit and Nut Trees",
                "variants": [{"sku": "R2E2-LG", "title": "Large",
                              "price": price, "available": available}],
            }],
        }))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_qualifying_drop_is_detected_and_mapped_to_the_variety(self):
        self._snapshot(self.data / "daleys" / "2026-08-13.json", 90.00)
        self._snapshot(self.data / "daleys" / "2026-08-14.json", 70.00)
        found = alerts.price_drops_by_variety(
            self.data, "2026-08-14", {"mango-r2e2"})
        self.assertIn("mango-r2e2", found)
        item = found["mango-r2e2"][0]
        self.assertEqual(item["old_price"], 90.00)
        self.assertEqual(item["price"], 70.00)
        self.assertEqual(item["nursery_name"], "Daleys Fruit Trees")

    def test_small_drop_is_ignored(self):
        self._snapshot(self.data / "daleys" / "2026-08-13.json", 90.00)
        self._snapshot(self.data / "daleys" / "2026-08-14.json", 87.00)
        self.assertEqual(
            alerts.price_drops_by_variety(self.data, "2026-08-14", {"mango-r2e2"}), {})

    def test_unwatched_variety_is_ignored(self):
        self._snapshot(self.data / "daleys" / "2026-08-13.json", 90.00)
        self._snapshot(self.data / "daleys" / "2026-08-14.json", 70.00)
        self.assertEqual(
            alerts.price_drops_by_variety(self.data, "2026-08-14", {"fig-black-genoa"}), {})

    def test_a_missing_snapshot_is_not_a_price_drop(self):
        """DEC-293: a nursery that did not report has not changed its prices."""
        self._snapshot(self.data / "daleys" / "2026-08-14.json", 70.00)
        self.assertEqual(
            alerts.price_drops_by_variety(self.data, "2026-08-14", {"mango-r2e2"}), {})


class VariantTitleSluggingTests(unittest.TestCase):
    """A variant-level comparison is only useful if its result maps back onto
    the cultivar someone actually watched."""

    def test_size_suffix_does_not_change_the_variety(self):
        self.assertEqual(product_variety_slug("Jujube - Shanxi Li (Large)"),
                         product_variety_slug("Jujube - Shanxi Li"))

    def test_changes_engine_carries_the_raw_product_title(self):
        """The reason price_drops_by_variety slugs from product_title: the
        display title for a default variant would slug to a different variety."""
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "2026-08-14.json"
            snap.write_text(json.dumps({"products": [{
                "title": "Fig - Violette de Bordeaux",
                "url": "https://example.com/fig",
                "variants": [{"sku": "F1", "title": "Default Title",
                              "price": 40.0, "available": True}],
            }]}))
            loaded = changes_mod.load_snapshot(Path(tmp), "2026-08-14")
        entry = next(iter(loaded.values()))
        self.assertEqual(entry["product_title"], "Fig - Violette de Bordeaux")
        self.assertEqual(product_variety_slug(entry["product_title"]),
                         "fig-violette-de-bordeaux")


class AlertFooterTests(unittest.TestCase):
    """The opt-out has to point at the system that is actually sending."""

    def test_footer_offers_a_working_per_variety_stop(self):
        html = alerts.inject_unsubscribe(
            "<html><body>x</body></html>", "a@example.com", "tok",
            variety_slug="mango-r2e2", variety_title="Mango - R2E2")
        self.assertIn("/stop-watching.html", html)
        self.assertIn("variety=mango-r2e2", html)
        self.assertIn("Stop watching Mango - R2E2", html)
        self.assertIn("Stop all my treestock alerts", html)

    def test_footer_never_points_at_the_digest_unsubscribe(self):
        """That route only knows subscribers.json, so for a watch-only
        recipient it reported "Not found" and kept sending."""
        html = alerts.inject_unsubscribe(
            "<html><body>x</body></html>", "a@example.com", "tok",
            variety_slug="mango-r2e2", variety_title="Mango - R2E2")
        self.assertNotIn("/unsubscribe.html", html)

    def test_stop_all_link_present_without_a_variety(self):
        html = alerts.inject_unsubscribe(
            "<html><body>x</body></html>", "a@example.com", "tok")
        self.assertIn("/stop-watching.html", html)
        self.assertNotIn("variety=", html)


class AlertEmailBodyTests(unittest.TestCase):
    PRODUCT = {
        "title": "Mango - R2E2 (Large)", "url": "https://daleys.example/r2e2",
        "nursery_key": "daleys", "nursery_name": "Daleys Fruit Trees",
        "price": 70.00, "old_price": 90.00, "available": True,
    }

    def test_price_drop_email_names_the_trigger(self):
        html = alerts.build_variety_alert_email(
            "Mango - R2E2", "mango-r2e2", [self.PRODUCT], alerts.PRICE_DROP)
        self.assertIn("just dropped in price", html)
        self.assertIn("$70.00", html)
        self.assertIn("$90.00", html)

    def test_restock_email_still_shows_the_old_price_as_context(self):
        html = alerts.build_variety_alert_email(
            "Mango - R2E2", "mango-r2e2", [self.PRODUCT], alerts.RESTOCK)
        self.assertIn("is now available", html)
        self.assertIn("$90.00", html)

    def test_no_em_dashes_in_alert_copy(self):
        for kind in (alerts.RESTOCK, alerts.PRICE_DROP):
            with self.subTest(kind=kind):
                html = alerts.build_variety_alert_email(
                    "Mango - R2E2", "mango-r2e2", [self.PRODUCT], kind)
                self.assertNotIn("—", html)

    def test_a_hostile_title_cannot_inject_markup(self):
        """A title reaching this function is either canonical or a stored
        legacy value, and the legacy ones were caller-supplied."""
        html = alerts.build_variety_alert_email(
            '<img src=x onerror="alert(1)">', "mango-r2e2",
            [self.PRODUCT], alerts.RESTOCK)
        # The escaped text still contains the word "onerror"; what matters is
        # that no tag and no attribute boundary survives.
        self.assertNotIn("<img", html)
        self.assertNotIn('onerror="', html)
        self.assertIn("&lt;img", html)

    def test_nursery_supplied_strings_are_escaped_too(self):
        """Not an injection worry, a rendering one: an unescaped & or < in a
        listing title breaks the email for everyone."""
        product = dict(self.PRODUCT,
                       title="Mango <R2E2> & friends",
                       nursery_name="Daleys & Sons")
        html = alerts.build_variety_alert_email(
            "Mango - R2E2", "mango-r2e2", [product], alerts.RESTOCK)
        self.assertIn("Mango &lt;R2E2&gt; &amp; friends", html)
        self.assertIn("Daleys &amp; Sons", html)

    def test_unsubscribe_footer_escapes_the_title(self):
        html = alerts.inject_unsubscribe(
            "<html><body>x</body></html>", "a@example.com", "tok",
            variety_slug="mango-r2e2", variety_title='<b>Mango</b>')
        self.assertNotIn("<b>Mango</b>", html)
        self.assertIn("&lt;b&gt;Mango&lt;/b&gt;", html)


class AlertIconTests(unittest.TestCase):
    """The two triggers were indistinguishable: same layout, same colours,
    differing only in a sentence of wording. Emoji rather than inline SVG
    because SVG is unreliable across mail clients and there is no plain-text
    part to fall back to."""

    PRODUCT = AlertEmailBodyTests.PRODUCT

    def test_restock_carries_the_bell(self):
        html = alerts.build_variety_alert_email(
            "Mango - R2E2", "mango-r2e2", [self.PRODUCT], alerts.RESTOCK)
        self.assertIn("\N{BELL}", html)
        self.assertNotIn("\N{CHART WITH DOWNWARDS TREND}", html)

    def test_price_drop_carries_the_falling_chart(self):
        html = alerts.build_variety_alert_email(
            "Mango - R2E2", "mango-r2e2", [self.PRODUCT], alerts.PRICE_DROP)
        self.assertIn("\N{CHART WITH DOWNWARDS TREND}", html)
        self.assertNotIn("\N{BELL}", html)

    def test_both_emails_say_the_alert_covers_both_triggers(self):
        """One watch fires on both, and the copy used to name only the one that
        had just fired."""
        for kind in (alerts.RESTOCK, alerts.PRICE_DROP):
            with self.subTest(kind=kind):
                html = alerts.build_variety_alert_email(
                    "Mango - R2E2", "mango-r2e2", [self.PRODUCT], kind)
                self.assertIn("covers both", html)

    def test_the_icon_survives_into_the_subject_line(self):
        """The subject is the only part visible before opening, so an icon that
        stops at the heading solves half the problem."""
        for kind, glyph in ((alerts.RESTOCK, "\N{BELL}"),
                            (alerts.PRICE_DROP, "\N{CHART WITH DOWNWARDS TREND}")):
            with self.subTest(kind=kind):
                icon = alerts.ALERT_ICON[kind]
                self.assertEqual(icon, glyph)
                subject = f"{icon} {alerts.subject_safe('Mango - R2E2')} is now available -- treestock.com.au"
                self.assertTrue(subject.startswith(glyph))
                self.assertIn(" -- ", subject)


class CanonicalTitleTests(unittest.TestCase):
    """The display title comes from the builder's index, not from whoever
    watched the slug first."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / variety_index_mod.INDEX_FILENAME
        self._orig = alerts._VARIETY_INDEX

    def tearDown(self):
        alerts._VARIETY_INDEX = self._orig
        self.tmp.cleanup()

    def _index(self, titles):
        variety_index_mod.write_variety_index(self.path, titles)
        alerts._VARIETY_INDEX = variety_index_mod.VarietyIndex(self.path)

    def test_index_title_beats_the_first_watchers_string(self):
        self._index({"mango-r2e2": "Mango - R2E2"})
        watchers = {"mango-r2e2": [
            {"email": "a@example.com", "variety_title": "Mango R2E2 45L POT (PICKUP)"},
            {"email": "b@example.com", "variety_title": "irrelevant"},
        ]}
        self.assertEqual(alerts.display_title("mango-r2e2", watchers),
                         "Mango - R2E2")

    def test_unknown_slug_keeps_the_stored_title(self):
        """~12 watched slugs are already absent from live stock and so have no
        index entry. Their watchers keep a recognisable name."""
        self._index({"mango-r2e2": "Mango - R2E2"})
        watchers = {"gone-forever": [
            {"email": "a@example.com", "variety_title": "Gone - Forever"}]}
        self.assertEqual(alerts.display_title("gone-forever", watchers),
                         "Gone - Forever")

    def test_no_index_at_all_falls_back_rather_than_going_silent(self):
        alerts._VARIETY_INDEX = variety_index_mod.VarietyIndex(self.path)
        watchers = {"mango-r2e2": [
            {"email": "a@example.com", "variety_title": "Mango - R2E2"}]}
        self.assertEqual(alerts.display_title("mango-r2e2", watchers),
                         "Mango - R2E2")


class SubjectLineTests(unittest.TestCase):
    def test_newlines_and_control_characters_are_flattened(self):
        self.assertEqual(
            alerts.subject_safe("Mango\r\n - R2E2\tGrafted"),
            "Mango - R2E2 Grafted")

    def test_ordinary_titles_are_untouched(self):
        self.assertEqual(alerts.subject_safe("Mango - R2E2"), "Mango - R2E2")


class PreOrderWordingTests(unittest.TestCase):
    """A pre-order is available (you can order it) but not in stock (it ships
    in one to six months). Telling a watcher it "is now available" sends them
    to a listing that cannot fill their order today, which is the same class of
    wrong answer as the defect the Daleys feed switch fixed."""

    def test_all_preorder_listings(self):
        self.assertTrue(alerts.all_preorder([{"preorder": True}, {"preorder": True}]))

    def test_a_single_real_listing_beats_the_preorders(self):
        """Mixed means something is genuinely available, so keep the plain wording."""
        self.assertFalse(alerts.all_preorder([{"preorder": True}, {"preorder": False}]))

    def test_nurseries_that_do_not_report_the_state_read_as_not_preorder(self):
        """Every non-feed snapshot lacks the key; it must not flip the wording."""
        self.assertFalse(alerts.all_preorder([{"title": "Mango - R2E2"}]))

    def test_empty_is_not_preorder(self):
        self.assertFalse(alerts.all_preorder([]))

    def test_email_body_says_pre_order_not_available(self):
        html = alerts.build_variety_alert_email(
            "Sapodilla - Krasuey", "sapodilla-krasuey",
            [{"preorder": True, "nursery_name": "Daleys Fruit Tree Nursery",
              "title": "Sapodilla - Krasuey", "url": "https://x/", "price": 99.0}],
            alerts.RESTOCK)
        self.assertIn("open for pre-order", html)
        self.assertNotIn("is now available", html)

    def test_email_body_keeps_plain_wording_for_a_real_restock(self):
        html = alerts.build_variety_alert_email(
            "Sapodilla - Krasuey", "sapodilla-krasuey",
            [{"nursery_name": "Daleys Fruit Tree Nursery",
              "title": "Sapodilla - Krasuey", "url": "https://x/", "price": 99.0}],
            alerts.RESTOCK)
        self.assertIn("is now available", html)
        self.assertNotIn("open for pre-order", html)

    def test_the_email_quotes_the_wait_instead_of_sending_them_to_look(self):
        """Daleys publish the two waits, so the alert says which one it is.
        1-2 months from a seasonal catalogue, 1-6 once a graft has struck."""
        def body(wait_state):
            return alerts.build_variety_alert_email(
                "Blueberry - Climax", "blueberry-climax",
                [{"preorder": True, "wait_state": wait_state,
                  "nursery_name": "Daleys Fruit Tree Nursery",
                  "title": "Blueberry - Climax", "url": "https://x/",
                  "price": 19.9}],
                alerts.RESTOCK)

        self.assertIn("ready in one to two months", body("presale"))
        self.assertIn("ready in one to six months", body("preorder"))
        # A nursery that reports a wait with no name keeps the old wording
        # rather than inventing a number we were never given.
        self.assertIn("not ready to ship yet", body(None))

    def test_the_longer_wait_wins_when_listings_disagree(self):
        self.assertEqual(
            alerts.preorder_wait([{"wait_state": "presale"},
                                  {"wait_state": "preorder"}]),
            "ready in one to six months")


class PreOrderReachesTheWordingTests(unittest.TestCase):
    """The wording above was dead code for its whole life.

    all_preorder() reads `preorder` off the product dicts an alert carries, and
    those dicts are built by load_nursery_data(), which listed its keys
    explicitly and never included that one. So `all(p.get("preorder") ...)` was
    False on every alert ever sent, and a watcher whose variety opened for
    pre-order was told it "is now available" and clicked through to a plant up
    to six months away.

    The unit tests above could not catch it: they hand build_variety_alert_email
    a dict shape the pipeline never actually produces. This one starts from a
    snapshot on disk, which is the only shape that exists in production.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _snapshot(self, day: str, wait_state: str | None):
        day_dir = self.data / "daleys" / f"{day}.json"
        day_dir.parent.mkdir(parents=True, exist_ok=True)
        product = {
            "title": "Blueberry - Climax",
            "url": "https://daleys.example/blueberry-climax",
            "category": "Fruit Trees/Berries Vines and Climbers/Blueberry",
            "any_available": True,
            "min_price": 19.90,
            "variants": [{"sku": "687", "title": "2L", "price": 19.90,
                          "available": True}],
        }
        if wait_state:
            product["preorder"] = True
            product["wait_state"] = wait_state
        day_dir.write_text(json.dumps({
            "nursery_name": "Daleys Fruit Trees", "products": [product]}))

    def test_load_nursery_data_carries_the_preorder_state_through(self):
        self._snapshot("2026-08-27", "preorder")
        loaded = alerts.load_nursery_data(self.data, "2026-08-27")
        self.assertEqual(len(loaded), 1)
        self.assertTrue(loaded[0]["preorder"])
        self.assertEqual(loaded[0]["wait_state"], "preorder")
        self.assertTrue(alerts.all_preorder(loaded))

    def test_a_plain_in_stock_listing_still_reads_as_not_preorder(self):
        self._snapshot("2026-08-27", None)
        loaded = alerts.load_nursery_data(self.data, "2026-08-27")
        self.assertFalse(loaded[0]["preorder"])
        self.assertIsNone(loaded[0]["wait_state"])
        self.assertFalse(alerts.all_preorder(loaded))


if __name__ == "__main__":
    unittest.main()


class StateReachabilityTests(unittest.TestCase):
    """Which nurseries a watcher in a given state can actually buy from.

    Benedict's call (2026-08-24): local delivery and pickup within the
    watcher's own state count as reachable, because most of the WA rare-fruit
    community is Perth metro and a Guildford pickup is a real option. The email
    labels them so a Broome reader is not misled.
    """

    def test_no_state_reaches_everything(self):
        for state in ("", None, alerts.ANY_STATE):
            with self.subTest(state=state):
                self.assertTrue(alerts.reachable("ross-creek", state))

    def test_a_qld_only_nursery_is_unreachable_from_wa(self):
        self.assertFalse(alerts.reachable("ross-creek", "WA"))
        self.assertFalse(alerts.reachable("ladybird", "WA"))
        self.assertFalse(alerts.reachable("fruitopia", "WA"))

    def test_the_statewide_shippers_reach_wa(self):
        """Benedict asked to confirm this explicitly."""
        for key in ("daleys", "diggers", "garden-express", "fruit-salad-trees"):
            with self.subTest(nursery=key):
                self.assertTrue(alerts.reachable(key, "WA"))

    def test_perth_local_nurseries_count_as_wa(self):
        for key in ("guildford", "primal-fruits", "perth-mobile-nursery",
                    "all-season-plants-wa", "st-clements-citrus"):
            with self.subTest(nursery=key):
                self.assertTrue(alerts.reachable(key, "WA"))

    def test_an_unknown_nursery_is_not_assumed_reachable(self):
        self.assertFalse(alerts.reachable("no-such-nursery", "WA"))

    def test_listings_are_filtered_not_reordered(self):
        listings = [{"nursery_key": "daleys"}, {"nursery_key": "ross-creek"},
                    {"nursery_key": "guildford"}]
        self.assertEqual(alerts.listings_for_state(listings, "WA"),
                         [{"nursery_key": "daleys"}, {"nursery_key": "guildford"}])
        self.assertEqual(alerts.listings_for_state(listings, alerts.ANY_STATE), listings)

    def test_watchers_group_by_state_with_null_as_all(self):
        grouped = alerts.watchers_by_state([
            {"email": "a@x", "state": "WA"},
            {"email": "b@x", "state": None},
            {"email": "c@x", "state": "WA"},
            {"email": "d@x"},
        ])
        self.assertEqual(sorted(grouped), [alerts.ANY_STATE, "WA"])
        self.assertEqual(len(grouped["WA"]), 2)
        self.assertEqual(len(grouped[alerts.ANY_STATE]), 2)


class StateAwareTriggerTests(unittest.TestCase):
    """The two failure modes this replaces, both measured live on 2026-08-24
    when 21 of 36 watched-and-in-stock varieties were unbuyable from WA."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "variety_watches.db"
        _make_db(self.db)
        self._orig = alerts.VARIETY_WATCHES_DB
        alerts.VARIETY_WATCHES_DB = self.db

    def tearDown(self):
        alerts.VARIETY_WATCHES_DB = self._orig
        self.tmp.cleanup()

    def _watch(self, email, slug, state=None):
        con = sqlite3.connect(self.db)
        alerts.ensure_schema(con)
        con.execute("INSERT OR IGNORE INTO watches "
                    "(email, variety_slug, species_slug, variety_title, added_at) "
                    "VALUES (?,?,?,?,?)", (email, slug, "avocado", slug, "2026-08-01"))
        if state:
            con.execute("INSERT INTO watcher_prefs (email, state, updated_at) "
                        "VALUES (?,?,?)", (email, state, "2026-08-01"))
        con.commit()
        con.close()

    def test_state_is_read_onto_the_watch(self):
        self._watch("perth@example.com", "avocado-shepard", "WA")
        self._watch("anywhere@example.com", "avocado-shepard")
        by_email = {w["email"]: w["state"] for w in alerts.load_watches()}
        self.assertEqual(by_email["perth@example.com"], "WA")
        self.assertEqual(by_email["anywhere@example.com"], alerts.ANY_STATE)

    def test_watcher_prefs_is_created_on_a_db_that_predates_it(self):
        """The live DB has never had this table. load_watches LEFT JOINs it."""
        con = sqlite3.connect(self.db)
        con.execute("DROP TABLE IF EXISTS watcher_prefs")
        con.commit()
        con.close()
        self._watch("a@example.com", "avocado-hass")
        self.assertEqual(alerts.load_watches()[0]["state"], alerts.ANY_STATE)

    # --- the two failure modes, as data ---------------------------------

    QLD_ONLY = [{"nursery_key": "fruitopia", "nursery_name": "Fruitopia"},
                {"nursery_key": "ladybird", "nursery_name": "Ladybird"}]
    PERTH = [{"nursery_key": "guildford", "nursery_name": "Guildford"}]

    def test_false_alert_a_wa_watcher_sees_no_restock_from_a_qld_only_nursery(self):
        """avocado-pinkerton: emailed "back in stock" at Ross Creek, which
        cannot ship to WA. A dead link."""
        self.assertEqual(alerts.listings_for_state(self.QLD_ONLY, "WA"), [])

    def test_silent_miss_a_wa_arrival_fires_even_though_the_global_count_never_hits_zero(self):
        """The worse one, and the reason state filters the TRIGGER.

        avocado-shepard was in stock at Fruitopia and Ladybird, neither of
        which ships WA. Yesterday's global count was 2. When Guildford in Perth
        lists one it goes 2 -> 3, never 0, so the old global test never fired
        and a Perth watcher was never told.
        """
        yesterday = self.QLD_ONLY
        today = self.QLD_ONLY + self.PERTH

        # Globally there is no restock: 2 -> 3, never zero.
        self.assertGreater(len(alerts.listings_for_state(yesterday, alerts.ANY_STATE)), 0)
        self.assertGreater(len(alerts.listings_for_state(today, alerts.ANY_STATE)), 0)

        # For WA it is exactly the 0 -> 1 the alert exists for.
        self.assertEqual(len(alerts.listings_for_state(yesterday, "WA")), 0)
        self.assertEqual(len(alerts.listings_for_state(today, "WA")), 1)

    # --- the email ------------------------------------------------------

    def test_the_email_labels_a_perth_metro_nursery(self):
        html = alerts.build_variety_alert_email(
            "Avocado - Shepard", "avocado-shepard",
            [{"nursery_key": "guildford", "nursery_name": "Guildford Garden Centre",
              "title": "Avocado Shepard", "url": "https://x/", "price": 89.0}],
            alerts.RESTOCK, "WA")
        self.assertIn("Perth metro only", html)

    def test_the_email_carries_the_per_state_shipping_caveat(self):
        html = alerts.build_variety_alert_email(
            "Avocado - Hass", "avocado-hass",
            [{"nursery_key": "daleys", "nursery_name": "Daleys",
              "title": "Avocado Hass", "url": "https://x/", "price": 49.0}],
            alerts.RESTOCK, "WA")
        self.assertIn("seasonal window", html)

    def test_an_unrestricted_shipper_gets_no_caveat_line(self):
        html = alerts.build_variety_alert_email(
            "Avocado - Hass", "avocado-hass",
            [{"nursery_key": "ross-creek", "nursery_name": "Ross Creek",
              "title": "Avocado Hass", "url": "https://x/", "price": 49.0}],
            alerts.RESTOCK, "QLD")
        self.assertNotIn("#b45309", html)

    def test_a_missing_nursery_key_costs_a_caveat_not_the_email(self):
        html = alerts.build_variety_alert_email(
            "Avocado - Hass", "avocado-hass",
            [{"nursery_name": "Somewhere", "title": "Avocado Hass",
              "url": "https://x/", "price": 49.0}],
            alerts.RESTOCK, "WA")
        self.assertIn("Avocado Hass", html)
