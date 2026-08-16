"""
The acknowledgement email, and the throttle that makes it safe to send.

DEC-294 shipped a capture path with no consent step: nothing told you that you
had subscribed, so first contact could be weeks later when a restock finally
fired, at which point the alert reads as unsolicited mail.

Sending an email the moment an unauthenticated stranger names your address is
also exactly the lever an attacker would pull, so the throttle is part of the
feature rather than a polish pass on it. What is pinned:

  * one notice per address per hour, which caps a victim at 24 a day instead of
    one per watch created;
  * the notice lists EVERY variety the address watches, which is what makes
    "batched into the next one" true rather than a euphemism for "dropped";
  * re-watching something you already watch sends nothing;
  * the copy states that one alert covers BOTH triggers, because the DEC-294
    copy promised restocks only while the watch already fired on price drops;
  * canonical titles, escaped, same as the alert emails;
  * a failure to launch the sender does not consume the hour's allowance.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from email.message import Message
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


server = _load(SCRAPERS / "subscribe_server.py")
notice = _load(SCRAPERS / "send_watch_notice_email.py")

from stocklib.variety_index import INDEX_FILENAME, write_variety_index  # noqa: E402

INDEX_TITLES = {
    "avocado-hass": "Avocado - Hass",
    "mango-r2e2": "Mango - R2E2",
}


class FakeSubprocess:
    """Stands in for the subprocess module inside subscribe_server."""

    DEVNULL = -3

    def __init__(self, explode=False):
        self.launched = []
        self.explode = explode

    def Popen(self, args, **kwargs):
        if self.explode:
            raise OSError("no fork for you")
        self.launched.append(args)
        return object()


class FakeRequest(server.SubscribeHandler):
    def __init__(self, payload, client_ip="203.0.113.9"):
        self.path = "/api/watch-variety"
        self.client_address = (client_ip, 40000)
        body = json.dumps(payload).encode()
        self.rfile = io.BytesIO(body)
        msg = Message()
        msg["Content-Type"] = "application/json"
        msg["Content-Length"] = str(len(body))
        self.headers = msg
        self.status = None
        self.body = None

    def send_json(self, status, data):
        self.status, self.body = status, data

    def send_error(self, code, *a, **k):
        self.status, self.body = code, None


class NoticeThrottleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "variety_watches.db"
        self.index_path = root / INDEX_FILENAME
        self.log = root / "watch_notice_sends.json"
        write_variety_index(self.index_path, INDEX_TITLES)

        self._orig = (server.VARIETY_WATCHES_DB, server.VARIETY_INDEX_FILE,
                      server.WATCH_NOTICE_LOG, server.subprocess,
                      server.make_unsubscribe_token)
        server.VARIETY_WATCHES_DB = self.db
        server.VARIETY_INDEX_FILE = self.index_path
        server.WATCH_NOTICE_LOG = self.log
        self.fake = FakeSubprocess()
        server.subprocess = self.fake
        server.make_unsubscribe_token = lambda e, *a: "tok123"
        server.init_variety_watches_db()

    def tearDown(self):
        (server.VARIETY_WATCHES_DB, server.VARIETY_INDEX_FILE,
         server.WATCH_NOTICE_LOG, server.subprocess,
         server.make_unsubscribe_token) = self._orig
        self.tmp.cleanup()

    def watch(self, email="a@example.com", slug="avocado-hass"):
        req = FakeRequest({"email": email, "variety_slug": slug})
        req.do_POST()
        return req

    def test_a_new_watch_sends_a_notice(self):
        req = self.watch()
        self.assertEqual(req.status, 201)
        self.assertEqual(len(self.fake.launched), 1)
        args = self.fake.launched[0]
        self.assertIn("send_watch_notice_email.py", args[1])
        self.assertEqual(args[2:], ["a@example.com", "tok123", "avocado-hass"])

    def test_a_second_watch_inside_the_window_is_throttled(self):
        self.watch(slug="avocado-hass")
        self.watch(slug="mango-r2e2")
        self.assertEqual(len(self.fake.launched), 1)

    def test_the_window_expiring_lets_the_next_one_through(self):
        self.watch(slug="avocado-hass")
        stale = (datetime.now()
                 - timedelta(seconds=server.WATCH_NOTICE_RATE_LIMIT_SECONDS + 60))
        self.log.write_text(json.dumps({"a@example.com": stale.isoformat()}))
        self.watch(slug="mango-r2e2")
        self.assertEqual(len(self.fake.launched), 2)

    def test_the_throttle_is_per_address(self):
        self.watch(email="a@example.com")
        self.watch(email="b@example.com")
        self.assertEqual(len(self.fake.launched), 2)

    def test_re_watching_something_you_already_watch_sends_nothing(self):
        self.watch()
        self.fake.launched.clear()
        stale = (datetime.now()
                 - timedelta(seconds=server.WATCH_NOTICE_RATE_LIMIT_SECONDS + 60))
        self.log.write_text(json.dumps({"a@example.com": stale.isoformat()}))
        req = self.watch()
        self.assertEqual(req.status, 200)
        self.assertEqual(self.fake.launched, [])

    def test_a_failed_launch_does_not_consume_the_allowance(self):
        """The stamp is written before the launch (so an unwritable log fails
        closed), which means a spawn failure has to roll it back. Otherwise a
        transient failure costs the person their only acknowledgement for the
        next hour."""
        server.subprocess = FakeSubprocess(explode=True)
        self.watch()
        self.assertNotIn("a@example.com", json.loads(self.log.read_text()))
        server.subprocess = self.fake
        self.watch(slug="mango-r2e2")
        self.assertEqual(len(self.fake.launched), 1)

    def test_an_unwritable_log_means_no_send_at_all(self):
        """Fail CLOSED. This throttle protects a third party's inbox, so a log
        we cannot persist must stop the email, not wave it through: an
        unrecorded send has no throttle behind it and every subsequent watch
        would re-send."""
        server.WATCH_NOTICE_LOG = Path(self.tmp.name) / "nope" / "x.json"
        orig = server._save_json_log
        server._save_json_log = lambda *a: (_ for _ in ()).throw(OSError("read-only"))
        try:
            req = self.watch()
        finally:
            server._save_json_log = orig
        self.assertEqual(req.status, 201)      # the watch itself still works
        self.assertEqual(self.fake.launched, [])

    def test_an_unparseable_stamp_is_treated_as_never_sent(self):
        self.log.write_text(json.dumps({"a@example.com": "not a timestamp"}))
        self.watch()
        self.assertEqual(len(self.fake.launched), 1)

    def test_the_notice_log_is_a_separate_file_from_the_manage_link_log(self):
        """Sharing one would let a manage-link request suppress a consent
        acknowledgement, or the reverse."""
        self.assertNotEqual(server.WATCH_NOTICE_LOG, server.MANAGE_LINK_LOG)


class NoticeBodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "variety_watches.db"
        self.index_path = root / INDEX_FILENAME
        write_variety_index(self.index_path, INDEX_TITLES)
        con = sqlite3.connect(self.db)
        con.execute("""CREATE TABLE watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL,
            variety_slug TEXT NOT NULL, species_slug TEXT NOT NULL,
            variety_title TEXT NOT NULL, added_at TEXT NOT NULL,
            UNIQUE(email, variety_slug))""")
        con.commit()
        con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, slug, title, added_at):
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO watches (email, variety_slug, species_slug, "
                    "variety_title, added_at) VALUES (?,?,?,?,?)",
                    ("a@example.com", slug, slug.split("-")[0], title, added_at))
        con.commit()
        con.close()

    def build(self, new_slug=""):
        watches = notice.load_watches("a@example.com", self.db)
        return notice.build_html("a@example.com", "tok123", watches, new_slug,
                                 self.index_path)

    def test_it_says_one_alert_covers_both_triggers(self):
        """The DEC-294 copy promised restocks only, while the watch had already
        started firing on price drops as well."""
        self.add("avocado-hass", "Avocado - Hass", "2026-08-01T00:00:00")
        html = self.build("avocado-hass")
        self.assertIn("back into stock", html)
        self.assertIn("drops in price", html)

    def test_it_lists_every_watch_not_just_the_new_one(self):
        """This is what makes the throttle's "batched into the next notice"
        true instead of a euphemism for dropped."""
        self.add("avocado-hass", "Avocado - Hass", "2026-08-01T00:00:00")
        self.add("mango-r2e2", "Mango - R2E2", "2026-08-02T00:00:00")
        html = self.build("mango-r2e2")
        self.assertIn("Avocado - Hass", html)
        self.assertIn("Mango - R2E2", html)

    def test_it_leads_with_the_variety_just_added(self):
        self.add("avocado-hass", "Avocado - Hass", "2026-08-01T00:00:00")
        self.add("mango-r2e2", "Mango - R2E2", "2026-08-02T00:00:00")
        html = self.build("avocado-hass")
        self.assertIn("You're now watching Avocado - Hass", html)

    def test_it_carries_a_stop_link_per_watch_and_a_stop_everything_link(self):
        self.add("avocado-hass", "Avocado - Hass", "2026-08-01T00:00:00")
        html = self.build("avocado-hass")
        self.assertIn("variety=avocado-hass", html)
        self.assertIn("Stop all my treestock alerts", html)
        self.assertIn("/api/preferences?email=", html)

    def test_it_uses_canonical_titles_over_stored_ones(self):
        self.add("avocado-hass", "whatever the caller sent", "2026-08-01T00:00:00")
        html = self.build("avocado-hass")
        self.assertIn("Avocado - Hass", html)
        self.assertNotIn("whatever the caller sent", html)

    def test_a_hostile_stored_title_is_escaped(self):
        self.add("gone-forever", '<img src=x onerror="alert(1)">',
                 "2026-08-01T00:00:00")
        html = self.build("gone-forever")
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_no_em_dashes(self):
        self.add("avocado-hass", "Avocado - Hass", "2026-08-01T00:00:00")
        self.assertNotIn("—", self.build("avocado-hass"))

    def test_no_watches_means_no_send(self):
        """The watch can be removed between the server launching this and the
        process starting."""
        self.assertTrue(notice.send("a@example.com", "tok", dry_run=True,
                                    db_path=self.db, index_path=self.index_path))


if __name__ == "__main__":
    unittest.main()
