"""
Scion watches: the same variety, a different kind of watch (2026-10-26).

Benedict: "scion wood always will attach to a variety, but it's a different
type of watch to just watching that variety". "Scion Wood Apple - Gala" is
wood of apple-gala, and a scion watch on apple-gala must fire on that stick
and never on the tree, nor a tree watch on the stick.
"""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from cultivar_parsing import scion_variety_slug
from stocklib.email_footer import watch_urls
from stocklib.watch_types import SCION, TREE, ensure_watch_type_schema, watch_page_url
import send_variety_alerts as alerts

OLD_SCHEMA = """
CREATE TABLE watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL,
    variety_slug TEXT NOT NULL, species_slug TEXT NOT NULL,
    variety_title TEXT NOT NULL, added_at TEXT NOT NULL,
    UNIQUE(email, variety_slug));
CREATE TABLE sends (
    id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL,
    variety_slug TEXT NOT NULL, sent_at TEXT NOT NULL,
    alert_type TEXT NOT NULL DEFAULT 'restock',
    UNIQUE(email, variety_slug, sent_at));
"""


class MigrationTest(unittest.TestCase):
    """The live DB held 301 watches and 125 sends in the old shape."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "w.db"
        con = sqlite3.connect(self.db)
        con.executescript(OLD_SCHEMA)
        con.execute("INSERT INTO watches VALUES (7, 'a@x.com', 'apple-gala', 'apple', 'Apple Gala', '2026-09-01')")
        con.execute("INSERT INTO sends VALUES (3, 'a@x.com', 'apple-gala', '2026-10-01', 'price_drop')")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_existing_rows_become_tree_watches_unchanged(self):
        con = sqlite3.connect(self.db)
        ensure_watch_type_schema(con)
        self.assertEqual(con.execute("SELECT * FROM watches").fetchall(),
                         [(7, "a@x.com", "apple-gala", "apple", "Apple Gala", "2026-09-01", "tree")])
        self.assertEqual(con.execute("SELECT * FROM sends").fetchall(),
                         [(3, "a@x.com", "apple-gala", "2026-10-01", "price_drop", "tree")])
        con.close()

    def test_a_tree_watcher_can_add_the_scion_watch_but_not_a_duplicate(self):
        con = sqlite3.connect(self.db)
        ensure_watch_type_schema(con)
        con.execute("INSERT INTO watches (email, variety_slug, species_slug, variety_title, added_at, watch_type) "
                    "VALUES ('a@x.com', 'apple-gala', 'apple', 'Apple Gala', '2026-10-26', 'scion')")
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("INSERT INTO watches (email, variety_slug, species_slug, variety_title, added_at, watch_type) "
                        "VALUES ('a@x.com', 'apple-gala', 'apple', 'Apple Gala', '2026-10-26', 'scion')")
        con.close()

    def test_idempotent(self):
        con = sqlite3.connect(self.db)
        ensure_watch_type_schema(con)
        ensure_watch_type_schema(con)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM watches").fetchone()[0], 1)
        con.close()


class ScionSlugTest(unittest.TestCase):
    def test_scion_listings_resolve_to_their_trees_variety(self):
        for title, slug in (("Scion Wood Apple - Gala", "apple-gala"),
                            ("Scion Wood Plum - Prune dAgen", "plum-prune-dagen"),
                            ("Adam's Pride Fig (1 x Cutting)", "fig-adam-s-pride"),
                            ("White Shahtoot Mulberry (3xCuttings)", "mulberry-white-shahtoot"),
                            ("Scion Wood  Mulberry - White Shahtoot", "mulberry-white-shahtoot")):
            with self.subTest(title=title):
                self.assertEqual(scion_variety_slug(title), slug)

    def test_no_variety_no_slug_and_trees_are_not_scion(self):
        self.assertIsNone(scion_variety_slug("Fig Cuttings"))
        self.assertIsNone(scion_variety_slug("Apple - Gala"))


def _snapshot(root, key, day, products):
    d = root / key
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{day}.json").write_text(json.dumps({
        "nursery": key, "nursery_name": key, "scraped_at": f"{day}T00:05:00",
        "products": products}))


class TreeAndScionStayApartTest(unittest.TestCase):
    """Daleys: Gala scion wood comes into stock; the Gala tree stays sold out."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        tree = {"title": "Apple - Gala", "url": "https://x/tree", "min_price": 45.0,
                "any_available": False, "category": "Fruit Trees/Apples"}
        scion = {"title": "Scion Wood Apple - Gala", "url": "https://x/scion", "min_price": 9.75,
                 "category": "Gardening Tools - Accessories/Scion Wood"}
        _snapshot(self.data, "daleys", "2026-07-01", [tree, dict(scion, any_available=False)])
        _snapshot(self.data, "daleys", "2026-07-02", [tree, dict(scion, any_available=True)])

    def tearDown(self):
        self.tmp.cleanup()

    def _restocked(self, watch_type):
        today = alerts.in_stock_by_variety_slug(
            alerts.load_nursery_data(self.data, "2026-07-02", watch_type), watch_type)
        before = alerts.in_stock_by_variety_slug(
            alerts.load_nursery_data(self.data, "2026-07-01", watch_type), watch_type)
        return {s for s in today if not before.get(s)}

    def test_scion_watch_fires_tree_watch_does_not(self):
        self.assertEqual(self._restocked(SCION), {"apple-gala"})
        self.assertEqual(self._restocked(TREE), set())


class SeparateCooldownTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = alerts.VARIETY_WATCHES_DB
        alerts.VARIETY_WATCHES_DB = Path(self.tmp.name) / "w.db"
        con = sqlite3.connect(alerts.VARIETY_WATCHES_DB)
        con.executescript(OLD_SCHEMA)
        con.close()

    def tearDown(self):
        alerts.VARIETY_WATCHES_DB = self._orig
        self.tmp.cleanup()

    def test_a_scion_alert_does_not_silence_the_tree_alert(self):
        alerts.record_send("a@x.com", "apple-gala", "2026-07-01", alerts.RESTOCK, SCION)
        last = alerts.last_sent_map()
        self.assertTrue(alerts.sent_same_day(last, "a@x.com", "apple-gala", "2026-07-01", SCION))
        self.assertFalse(alerts.sent_same_day(last, "a@x.com", "apple-gala", "2026-07-01", TREE))
        self.assertFalse(alerts.in_cooldown(last, "a@x.com", "apple-gala", alerts.RESTOCK,
                                            "2026-07-02", TREE))


class LinksTest(unittest.TestCase):
    def test_scion_watches_land_on_their_row_of_the_scion_page(self):
        self.assertEqual(watch_page_url("https://t", "apple-gala", SCION),
                         "https://t/scion-wood.html#scion-apple-gala")
        self.assertEqual(watch_page_url("https://t", "apple-gala", TREE),
                         "https://t/variety/apple-gala.html")

    def test_every_new_stop_link_names_its_type(self):
        # Stopping the tree alert must not take the scion watch with it; only
        # links sent before 2026-10-26 (no type) mean "both".
        tree, _, _ = watch_urls("a@x.com", "tok", "apple-gala", "Apple Gala")
        scion, _, _ = watch_urls("a@x.com", "tok", "apple-gala", "Apple Gala", watch_type=SCION)
        self.assertIn("&type=tree", tree)
        self.assertIn("&type=scion", scion)


if __name__ == "__main__":
    unittest.main()
