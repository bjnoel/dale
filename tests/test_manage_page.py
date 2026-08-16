"""
The manage page, for the people who actually use it.

Two defects, both stemming from the page predating variety alerts being the
product:

  * /api/request-manage-link only looked in subscribers.json, so the ~83
    watch-only addresses (the large majority of alert recipients) were told
    "a link is on its way" and got nothing. The in-email footer link worked;
    the site's own link did not.
  * The page led with digest settings and put "Variety alerts" last, below the
    save button, on the page reached from the alert that is now the product.

Pinned here, including the parts that must NOT change: the uniform 200 that
stops the endpoint leaking which addresses are known, and the 1/hour throttle.

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

from stocklib.variety_index import INDEX_FILENAME, write_variety_index  # noqa: E402

INDEX_TITLES = {"avocado-hass": "Avocado - Hass", "mango-r2e2": "Mango - R2E2"}


class FakeRequest(server.SubscribeHandler):
    def __init__(self, path, payload):
        self.path = path
        self.client_address = ("203.0.113.9", 40000)
        body = json.dumps(payload).encode()
        self.rfile = io.BytesIO(body)
        msg = Message()
        msg["Content-Type"] = "application/json"
        msg["Content-Length"] = str(len(body))
        self.headers = msg
        self.status = None
        self.body = None
        self.html = None

    def send_json(self, status, data):
        self.status, self.body = status, data

    def send_html(self, status, body):
        self.status, self.html = status, body

    def send_error(self, code, *a, **k):
        self.status = code


class ManageLinkCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "variety_watches.db"
        self.index_path = root / INDEX_FILENAME
        self.link_log = root / "manage_link_sends.json"
        write_variety_index(self.index_path, INDEX_TITLES)

        self._orig = (server.VARIETY_WATCHES_DB, server.VARIETY_INDEX_FILE,
                      server.MANAGE_LINK_LOG, server.subprocess,
                      server.make_unsubscribe_token, server.load_subscribers)
        server.VARIETY_WATCHES_DB = self.db
        server.VARIETY_INDEX_FILE = self.index_path
        server.MANAGE_LINK_LOG = self.link_log
        server.make_unsubscribe_token = lambda e, *a: "tok123"
        self.subscribers = []
        server.load_subscribers = lambda: self.subscribers
        self.spawned = []
        server.subprocess = type("FakeSubprocess", (), {
            "DEVNULL": -3,
            "Popen": lambda _s, args, **kw: self.spawned.append(args),
        })()
        server.init_variety_watches_db()

    def tearDown(self):
        (server.VARIETY_WATCHES_DB, server.VARIETY_INDEX_FILE,
         server.MANAGE_LINK_LOG, server.subprocess,
         server.make_unsubscribe_token, server.load_subscribers) = self._orig
        self.tmp.cleanup()

    def add_watch(self, email, slug="avocado-hass"):
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO watches (email, variety_slug, species_slug, "
                    "variety_title, added_at) VALUES (?,?,?,?,?)",
                    (email, slug, "avocado", INDEX_TITLES[slug],
                     "2026-08-01T00:00:00"))
        con.commit()
        con.close()

    def request_link(self, email):
        req = FakeRequest("/api/request-manage-link", {"email": email})
        req.do_POST()
        return req


class RequestManageLinkTests(ManageLinkCase):
    def test_a_watch_only_address_now_gets_a_link(self):
        """The bug: 83 of 89 alert recipients hold watches and never subscribed
        to the digest, and every one of them got silence from this form."""
        self.add_watch("watcher@example.com")
        req = self.request_link("watcher@example.com")
        self.assertEqual(req.status, 200)
        self.assertEqual(len(self.spawned), 1)
        self.assertIn("send_manage_link_email.py", self.spawned[0][1])

    def test_a_digest_subscriber_still_gets_a_link(self):
        self.subscribers = [{"email": "sub@example.com", "state": "ALL"}]
        self.request_link("sub@example.com")
        self.assertEqual(len(self.spawned), 1)

    def test_an_unknown_address_gets_the_same_200_and_no_email(self):
        """Uniform response on purpose: a different status or message here
        turns the form into an oracle for which addresses we hold."""
        req = self.request_link("nobody@example.com")
        self.assertEqual(req.status, 200)
        self.assertEqual(self.spawned, [])

    def test_the_response_body_is_identical_known_or_not(self):
        self.add_watch("watcher@example.com")
        known = self.request_link("watcher@example.com")
        unknown = self.request_link("nobody@example.com")
        self.assertEqual(known.body, unknown.body)

    def test_the_hourly_throttle_still_applies_to_watch_only_addresses(self):
        self.add_watch("watcher@example.com")
        self.request_link("watcher@example.com")
        self.request_link("watcher@example.com")
        self.assertEqual(len(self.spawned), 1)

    def test_the_throttle_releases_after_the_window(self):
        self.add_watch("watcher@example.com")
        self.request_link("watcher@example.com")
        stale = (datetime.now()
                 - timedelta(seconds=server.MANAGE_LINK_RATE_LIMIT_SECONDS + 60))
        self.link_log.write_text(json.dumps({"watcher@example.com": stale.isoformat()}))
        self.request_link("watcher@example.com")
        self.assertEqual(len(self.spawned), 2)

    def test_a_bad_address_is_still_rejected(self):
        req = self.request_link("not-an-email")
        self.assertEqual(req.status, 400)


class PreferencesPageOrderTests(ManageLinkCase):
    def render(self, frequency="daily"):
        req = FakeRequest("/api/preferences", {})
        req.send_preferences_page("sub@example.com", "tok123", "ALL",
                                  ["new_products"], ["fruit"], frequency)
        return req.html

    def test_variety_alerts_render_before_digest_settings(self):
        """This page is reached from the variety alert, which is the product."""
        html = self.render()
        self.assertLess(html.index("Variety alerts"), html.index("State filter"))

    def test_the_digest_block_is_open_for_an_active_subscriber(self):
        html = self.render(frequency="daily")
        self.assertIn("<details open", html)
        self.assertIn("Digest emails (daily)", html)

    def test_the_digest_block_collapses_when_frequency_is_off(self):
        html = self.render(frequency="off")
        self.assertNotIn("<details open", html)
        self.assertIn("Digest emails (currently off)", html)

    def test_collapsed_is_not_deleted(self):
        """The 12 real digest subscribers must still be able to reach their
        settings, and so must anyone turning the digest back on."""
        html = self.render(frequency="off")
        self.assertIn('id="prefsForm"', html)
        self.assertIn('id="stateSelect"', html)
        self.assertIn('id="frequencyGroup"', html)

    def test_the_save_handler_still_finds_its_inputs(self):
        """The form moved inside a <details>, which keeps its children in the
        DOM when closed. If that ever became a template that omits them, the
        save button would silently post empty preferences."""
        html = self.render(frequency="off")
        for selector in ("#categoryGroup input", "#plantCategoryGroup input",
                         "#frequencyGroup input"):
            with self.subTest(selector=selector):
                self.assertIn(selector, html)

    def test_no_em_dashes(self):
        self.assertNotIn("—", self.render())


class ManageHtmlCopyTests(unittest.TestCase):
    PAGE = (SCRAPERS / "static" / "manage.html").read_text()

    def test_it_no_longer_says_the_email_you_used_to_subscribe(self):
        """It serves watchers now, and most of them never subscribed to
        anything."""
        self.assertNotIn("the email you used to subscribe", self.PAGE)

    def test_it_mentions_the_varieties_you_are_watching(self):
        self.assertIn("watching", self.PAGE)

    def test_no_em_dashes(self):
        self.assertNotIn("—", self.PAGE)


if __name__ == "__main__":
    unittest.main()
