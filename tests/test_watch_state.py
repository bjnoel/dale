"""
Subscriber state on variety alerts: storage, capture, and the manage page.

Benedict, 2026-08-24: "they should never be emailed unless they can genuinely
buy it from WA". State lives on the PERSON, in watcher_prefs, not on the watch:
a column on `watches` would let one person's two watches disagree about where
they live.

The capture design is deliberately lopsided. The digest signup HAS a state
dropdown and took 12 signups in five months; the email-only watch pill took
104. So the pill gains no field. It forwards the state the visitor already
picked in the homepage filter if there is one, and the manage page asks
properly. All 104 existing watchers read as ALL, which is exactly the old
behaviour, so this changes nobody's mail until they choose.

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

from stocklib.variety_index import INDEX_FILENAME, write_variety_index  # noqa: E402

INDEX_TITLES = {"avocado-hass": "Avocado - Hass", "mango-r2e2": "Mango - R2E2"}


class FakeRequest(server.SubscribeHandler):
    def __init__(self, path="/api/watch-variety", payload=None, client_ip="203.0.113.9"):
        self.path = path
        self.client_address = (client_ip, 40000)
        body = json.dumps(payload or {}).encode()
        self.rfile = io.BytesIO(body)
        msg = Message()
        msg["Content-Type"] = "application/json"
        msg["Content-Length"] = str(len(body))
        self.headers = msg
        self.status = self.body = self.html = None

    def send_json(self, status, data):
        self.status, self.body = status, data

    def send_html(self, status, html):
        self.status, self.html = status, html

    def send_error(self, code, *a, **kw):
        self.status = code


class WatchStateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "variety_watches.db"
        self.index_path = root / INDEX_FILENAME
        write_variety_index(self.index_path, INDEX_TITLES)
        self._orig = (server.VARIETY_WATCHES_DB, server.VARIETY_INDEX_FILE,
                      server.WATCH_NOTICE_LOG, server.subprocess,
                      server.make_unsubscribe_token, server.verify_unsubscribe_token)
        server.VARIETY_WATCHES_DB = self.db
        server.VARIETY_INDEX_FILE = self.index_path
        server.WATCH_NOTICE_LOG = root / "watch_notice_sends.json"
        server.make_unsubscribe_token = lambda e, *a: "tok123"
        server.verify_unsubscribe_token = lambda e, t: t == "tok123"
        server.subprocess = type("FakeSubprocess", (), {
            "DEVNULL": -3, "Popen": lambda _s, args, **kw: None})()
        server.init_variety_watches_db()

    def tearDown(self):
        (server.VARIETY_WATCHES_DB, server.VARIETY_INDEX_FILE,
         server.WATCH_NOTICE_LOG, server.subprocess,
         server.make_unsubscribe_token, server.verify_unsubscribe_token) = self._orig
        self.tmp.cleanup()

    def post(self, payload, path="/api/watch-variety", ip="203.0.113.9"):
        req = FakeRequest(path=path, payload=payload, client_ip=ip)
        req.do_POST()
        return req

    def state_of(self, email):
        con = sqlite3.connect(self.db)
        row = con.execute("SELECT state FROM watcher_prefs WHERE email=?", (email,)).fetchone()
        con.close()
        return row[0] if row else None


class SchemaTests(WatchStateCase):
    def test_watcher_prefs_exists_after_init(self):
        con = sqlite3.connect(self.db)
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        self.assertIn("watcher_prefs", names)

    def test_init_is_idempotent(self):
        server.init_variety_watches_db()
        server.init_variety_watches_db()


class CaptureOnWatchTests(WatchStateCase):
    """The pill gains no field; it forwards a state the visitor already chose."""

    def test_a_watch_without_a_state_stores_none(self):
        r = self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        self.assertEqual(r.status, 201)
        self.assertIsNone(self.state_of("a@example.com"))

    def test_a_watch_carrying_the_filter_state_stores_it(self):
        r = self.post({"email": "b@example.com", "variety_slug": "avocado-hass",
                       "state": "WA"})
        self.assertEqual(r.status, 201)
        self.assertEqual(self.state_of("b@example.com"), "WA")

    def test_state_is_case_insensitive(self):
        self.post({"email": "c@example.com", "variety_slug": "avocado-hass", "state": "wa"})
        self.assertEqual(self.state_of("c@example.com"), "WA")

    def test_a_junk_state_is_ignored_not_an_error(self):
        """A bad value must not cost someone their alert. The watch is the
        thing they asked for; the state is a bonus we inferred."""
        r = self.post({"email": "d@example.com", "variety_slug": "avocado-hass",
                       "state": "ZZ"})
        self.assertEqual(r.status, 201)
        self.assertIsNone(self.state_of("d@example.com"))

    def test_all_is_not_written_as_a_choice(self):
        """'All states' is the filter's default, not a decision. Writing it
        would let a later real choice look like it was already made."""
        self.post({"email": "e@example.com", "variety_slug": "avocado-hass",
                   "state": "ALL"})
        self.assertIsNone(self.state_of("e@example.com"))

    def test_a_second_watch_does_not_clear_an_existing_state(self):
        self.post({"email": "f@example.com", "variety_slug": "avocado-hass", "state": "WA"})
        self.post({"email": "f@example.com", "variety_slug": "mango-r2e2"})
        self.assertEqual(self.state_of("f@example.com"), "WA")

    def test_a_later_watch_can_move_someone_who_moved(self):
        self.post({"email": "g@example.com", "variety_slug": "avocado-hass", "state": "WA"})
        self.post({"email": "g@example.com", "variety_slug": "mango-r2e2", "state": "VIC"})
        self.assertEqual(self.state_of("g@example.com"), "VIC")


class UpdateWatchStateTests(WatchStateCase):
    """The manage page's save button. A separate action from update_preferences
    because that one edits subscribers.json and 404s for an address that is not
    a digest subscriber, which is 98 of the 104 watchers."""

    def save(self, email, state, token="tok123"):
        return self.post({"email": email, "token": token,
                          "action": "update_watch_state", "state": state},
                         path="/api/subscribe")

    def test_a_watch_only_address_can_set_its_state(self):
        self.post({"email": "h@example.com", "variety_slug": "avocado-hass"})
        r = self.save("h@example.com", "WA")
        self.assertEqual(r.status, 200)
        self.assertEqual(self.state_of("h@example.com"), "WA")

    def test_all_can_be_chosen_back_deliberately(self):
        self.post({"email": "i@example.com", "variety_slug": "avocado-hass", "state": "WA"})
        self.save("i@example.com", "ALL")
        self.assertEqual(self.state_of("i@example.com"), "ALL")

    def test_a_bad_token_cannot_change_someone_elses_state(self):
        self.post({"email": "j@example.com", "variety_slug": "avocado-hass"})
        r = self.save("j@example.com", "WA", token="nope")
        self.assertEqual(r.status, 403)
        self.assertIsNone(self.state_of("j@example.com"))

    def test_an_invalid_state_is_rejected(self):
        r = self.save("k@example.com", "WESTERN AUSTRALIA")
        self.assertEqual(r.status, 400)

    def test_the_endpoint_is_on_an_already_allowed_path(self):
        """update_watch_state is an ACTION on /api/subscribe, not a new route.
        A new route also needs a Caddy allowlist entry, and forgetting that
        ships a 404 to real people. Caddy is not in this repo, so the cheap
        protection is not needing the entry at all."""
        self.assertIn("/api/subscribe", server.ALLOWED_POST_PATHS)
        self.assertNotIn("/api/set-state", server.ALLOWED_POST_PATHS)


class ManagePageTests(WatchStateCase):
    def _page(self, email):
        req = FakeRequest()
        req.send_watch_only_page(email, "tok123")
        return req.html or ""

    def test_the_page_offers_a_state_picker(self):
        self.post({"email": "m@example.com", "variety_slug": "avocado-hass"})
        html = self._page("m@example.com")
        self.assertIn("watchState", html)
        self.assertIn("Where do you want to buy?", html)
        self.assertIn("update_watch_state", html)

    def test_every_valid_state_is_offered(self):
        html = self._page("m@example.com")
        for st in server.VALID_STATES:
            with self.subTest(state=st):
                self.assertIn(f'value="{st}"', html)

    def test_the_current_choice_is_preselected(self):
        self.post({"email": "n@example.com", "variety_slug": "avocado-hass", "state": "VIC"})
        html = self._page("n@example.com")
        self.assertIn('value="VIC" selected', html)

    def test_someone_who_never_chose_sees_anywhere(self):
        self.post({"email": "o@example.com", "variety_slug": "avocado-hass"})
        html = self._page("o@example.com")
        self.assertIn('value="ALL" selected', html)


if __name__ == "__main__":
    unittest.main()
