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


if __name__ == "__main__":
    unittest.main()
