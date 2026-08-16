"""
Abuse ceilings on POST /api/watch-variety.

Before this, nothing sat between a script and 90 real inboxes: the endpoint
took any valid-looking email and inserted a live watch, with no token, no
confirmation, no rate limit, no cap and no body-size limit.

What is pinned here, and what each control is actually worth:

  * body cap, checked BEFORE the read, so a stranger does not choose how much
    memory this process allocates;
  * per-address watch cap, which is the control that holds, because an address
    cannot be spoofed the way a header can;
  * per-IP rate limit, which raises the cost of casual abuse and no more (the
    origin is directly reachable, so CF-Connecting-IP is forgeable);
  * honeypot, answered with a fake success so a bot learns nothing;
  * unknown-slug rejection, which is what stops the watch table filling with
    slugs no page will ever exist for;
  * the Turnstile hook, exercised as a no-op today so switching it on later
    cannot be the change that discovers a bug in it;
  * /api/wishlist no longer subscribing the voter to the digest behind their
    back.

This module also carries the request harness the rest of the server tests were
missing: SubscribeHandler with __init__ replaced, which is enough because
do_POST only touches headers, rfile and the send_* helpers.

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

INDEX_TITLES = {
    "avocado-hass": "Avocado - Hass",
    "mango-r2e2": "Mango - R2E2",
    "fig-pingo-de-mel": "Fig - Pingo De Mel",
}


class FakeRequest(server.SubscribeHandler):
    """A SubscribeHandler with the socket plumbing replaced.

    BaseHTTPRequestHandler.__init__ reads and dispatches a real request, so it
    is deliberately not called. do_POST only reaches self.path, self.headers,
    self.rfile, self.client_address and the send_* helpers.
    """

    def __init__(self, path="/api/watch-variety", payload=None, *,
                 headers=None, client_ip="203.0.113.9", raw=None,
                 declared_length=None):
        self.path = path
        self.client_address = (client_ip, 40000)
        body = raw if raw is not None else json.dumps(payload or {}).encode()
        self.rfile = io.BytesIO(body)
        msg = Message()
        msg["Content-Type"] = "application/json"
        msg["Content-Length"] = (str(len(body)) if declared_length is None
                                 else str(declared_length))
        for key, value in (headers or {}).items():
            msg[key] = value
        self.headers = msg
        self.status = None
        self.body = None

    def send_json(self, status, data):
        self.status, self.body = status, data

    def send_error(self, code, *args, **kwargs):
        self.status, self.body = code, None


class WatchEndpointCase(unittest.TestCase):
    """Temp DB + temp index, so nothing here touches /opt/dale."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "variety_watches.db"
        self.index_path = root / INDEX_FILENAME
        write_variety_index(self.index_path, INDEX_TITLES)

        self._orig = (server.VARIETY_WATCHES_DB, server.VARIETY_INDEX_FILE)
        server.VARIETY_WATCHES_DB = self.db
        server.VARIETY_INDEX_FILE = self.index_path
        server.init_variety_watches_db()

    def tearDown(self):
        server.VARIETY_WATCHES_DB, server.VARIETY_INDEX_FILE = self._orig
        self.tmp.cleanup()

    def post(self, payload=None, **kwargs):
        req = FakeRequest(payload=payload, **kwargs)
        req.do_POST()
        return req

    def rows(self):
        con = sqlite3.connect(self.db)
        out = con.execute(
            "SELECT email, variety_slug, variety_title FROM watches").fetchall()
        con.close()
        return out


class BodySizeTests(WatchEndpointCase):
    def test_an_oversized_declared_body_is_refused_before_it_is_read(self):
        req = self.post({"email": "a@example.com", "variety_slug": "avocado-hass"},
                        declared_length=server.MAX_BODY_BYTES + 1)
        self.assertEqual(req.status, 413)
        # The point of capping first: the body was never consumed.
        self.assertEqual(req.rfile.tell(), 0)

    def test_a_junk_content_length_is_a_400_not_a_500(self):
        req = self.post({"email": "a@example.com", "variety_slug": "avocado-hass"},
                        declared_length="not-a-number")
        self.assertEqual(req.status, 400)

    def test_an_ordinary_payload_is_unaffected(self):
        req = self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        self.assertEqual(req.status, 201)


class SlugValidationTests(WatchEndpointCase):
    def test_a_known_slug_is_accepted_with_our_own_title(self):
        req = self.post({"email": "a@example.com", "variety_slug": "avocado-hass",
                         "variety_title": "anything the caller likes"})
        self.assertEqual(req.status, 201)
        self.assertEqual(self.rows(), [("a@example.com", "avocado-hass",
                                        "Avocado - Hass")])

    def test_an_unknown_slug_is_rejected(self):
        """Otherwise the table fills with slugs no page will ever exist for,
        and every one of those is an alert that can never fire."""
        req = self.post({"email": "a@example.com", "variety_slug": "not-a-variety"})
        self.assertEqual(req.status, 404)
        self.assertEqual(self.rows(), [])

    def test_a_malformed_slug_is_rejected_before_any_lookup(self):
        for slug in ("<script>", "Avocado-Hass", "avocado hass", "a" * 200):
            with self.subTest(slug=slug):
                req = self.post({"email": "a@example.com", "variety_slug": slug})
                self.assertEqual(req.status, 400)
        self.assertEqual(self.rows(), [])

    def test_a_malformed_species_slug_is_rejected(self):
        req = self.post({"email": "a@example.com", "variety_slug": "avocado-hass",
                         "species_slug": "<script>"})
        self.assertEqual(req.status, 400)

    def test_a_repeat_watch_is_idempotent(self):
        self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        req = self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        self.assertEqual(req.status, 200)
        self.assertEqual(len(self.rows()), 1)

    def test_a_repeat_watch_heals_a_title_stored_before_we_owned_them(self):
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO watches (email, variety_slug, species_slug, "
                    "variety_title, added_at) VALUES (?,?,?,?,?)",
                    ("a@example.com", "avocado-hass", "avocado",
                     "<b>whatever</b>", "2026-01-01T00:00:00"))
        con.commit()
        con.close()
        self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        self.assertEqual(self.rows(), [("a@example.com", "avocado-hass",
                                        "Avocado - Hass")])


class HoneypotTests(WatchEndpointCase):
    def test_a_filled_honeypot_looks_like_success_and_writes_nothing(self):
        req = self.post({"email": "bot@example.com",
                         "variety_slug": "avocado-hass",
                         "website": "http://spam.example"})
        self.assertEqual(req.status, 201)
        self.assertEqual(self.rows(), [])

    def test_an_empty_honeypot_is_the_normal_path(self):
        req = self.post({"email": "a@example.com",
                         "variety_slug": "avocado-hass", "website": ""})
        self.assertEqual(req.status, 201)
        self.assertEqual(len(self.rows()), 1)


class PerAddressCapTests(WatchEndpointCase):
    def _fill(self, email, n):
        con = sqlite3.connect(self.db)
        for i in range(n):
            con.execute("INSERT INTO watches (email, variety_slug, species_slug, "
                        "variety_title, added_at) VALUES (?,?,?,?,?)",
                        (email, f"filler-{i}", "filler", f"Filler {i}",
                         "2026-01-01T00:00:00"))
        con.commit()
        con.close()

    def test_a_new_watch_past_the_cap_is_refused(self):
        self._fill("a@example.com", server.MAX_WATCHES_PER_ADDRESS)
        req = self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        self.assertEqual(req.status, 429)

    def test_the_cap_does_not_break_a_re_watch_of_something_already_held(self):
        """Hitting the cap must never turn an idempotent request into an
        error: the person would see a failure for an alert they already have."""
        self._fill("a@example.com", server.MAX_WATCHES_PER_ADDRESS - 1)
        self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        req = self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        self.assertEqual(req.status, 200)

    def test_the_cap_is_per_address(self):
        self._fill("a@example.com", server.MAX_WATCHES_PER_ADDRESS)
        req = self.post({"email": "b@example.com", "variety_slug": "avocado-hass"})
        self.assertEqual(req.status, 201)


class PerIpRateLimitTests(WatchEndpointCase):
    def test_the_limit_bites_after_the_allowance(self):
        for i in range(server.WATCH_IP_LIMIT):
            req = self.post({"email": f"a{i}@example.com",
                             "variety_slug": "avocado-hass"})
            self.assertIn(req.status, (200, 201), f"attempt {i} was {req.status}")
        req = self.post({"email": "one-too-many@example.com",
                         "variety_slug": "avocado-hass"})
        self.assertEqual(req.status, 429)

    def test_a_different_address_gets_its_own_allowance(self):
        for i in range(server.WATCH_IP_LIMIT):
            self.post({"email": f"a{i}@example.com", "variety_slug": "avocado-hass"})
        req = self.post({"email": "b@example.com", "variety_slug": "avocado-hass"},
                        client_ip="198.51.100.4")
        self.assertEqual(req.status, 201)

    def test_attempts_outside_the_window_are_pruned_not_kept(self):
        """The table holds at most one window of addresses. It is a rate
        limiter, not a log of who visited."""
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO watch_attempts (ip, ts) VALUES (?, ?)",
                    ("203.0.113.9", "2020-01-01T00:00:00"))
        con.commit()
        con.close()
        self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        con = sqlite3.connect(self.db)
        stale = con.execute("SELECT COUNT(*) FROM watch_attempts WHERE ts < ?",
                            ("2021-01-01",)).fetchone()[0]
        con.close()
        self.assertEqual(stale, 0)

    def test_a_rejected_request_does_not_consume_the_allowance(self):
        """Validation runs first, so junk is cheap for us and does not let a
        caller burn their own budget into a lockout they can complain about."""
        for _ in range(server.WATCH_IP_LIMIT + 5):
            self.post({"email": "not-an-email", "variety_slug": "avocado-hass"})
        req = self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        self.assertEqual(req.status, 201)


class ClientIpTests(WatchEndpointCase):
    def test_cf_connecting_ip_wins(self):
        req = FakeRequest(headers={"CF-Connecting-IP": "192.0.2.1",
                                   "X-Forwarded-For": "198.51.100.1"},
                          client_ip="10.0.0.1")
        self.assertEqual(req._client_ip(), "192.0.2.1")

    def test_x_forwarded_for_uses_the_first_entry(self):
        req = FakeRequest(headers={"X-Forwarded-For": "198.51.100.1, 10.0.0.5"},
                          client_ip="10.0.0.1")
        self.assertEqual(req._client_ip(), "198.51.100.1")

    def test_falls_back_to_the_peer_address(self):
        req = FakeRequest(client_ip="10.0.0.1")
        self.assertEqual(req._client_ip(), "10.0.0.1")

    def test_a_forged_header_is_accepted_which_is_the_known_limitation(self):
        """Documenting the hole rather than pretending it is closed: the origin
        is directly reachable, so this header is attacker-controlled. The
        per-address cap is what actually bounds abuse."""
        req = FakeRequest(headers={"CF-Connecting-IP": "not even an address"})
        self.assertEqual(req._client_ip(), "not even an address")


class TurnstileTests(WatchEndpointCase):
    def test_no_secret_configured_means_the_hook_passes(self):
        self.assertTrue(server.turnstile_ok("", "203.0.113.9"))
        req = self.post({"email": "a@example.com", "variety_slug": "avocado-hass"})
        self.assertEqual(req.status, 201)

    def test_a_configured_secret_with_no_token_fails_closed(self):
        orig = server.turnstile_secret
        server.turnstile_secret = lambda: "a-secret"
        try:
            self.assertFalse(server.turnstile_ok("", "203.0.113.9"))
            req = self.post({"email": "a@example.com",
                             "variety_slug": "avocado-hass"})
            self.assertEqual(req.status, 403)
        finally:
            server.turnstile_secret = orig

    def test_the_flag_is_off_in_the_repo(self):
        """If a secret ever gets committed here, this fails loudly."""
        source = (SCRAPERS / "subscribe_server.py").read_text()
        self.assertIn("TURNSTILE_SECRET", source)
        self.assertNotIn("0x4AAAAA", source)   # Cloudflare key prefix


class WishlistConsentTests(WatchEndpointCase):
    def test_a_wishlist_vote_no_longer_subscribes_the_voter(self):
        """It used to write into subscribers.json and fire a welcome email with
        no double opt-in and no statement that voting subscribed you, which is
        a second consent path contradicting the one DEC-294 settled on."""
        calls = []
        orig = server.save_subscribers
        server.save_subscribers = lambda subs: calls.append(subs)
        try:
            req = self.post({"email": "voter@example.com",
                             "species_slug": "cherimoya"},
                            path="/api/wishlist")
            self.assertEqual(req.status, 201)
        finally:
            server.save_subscribers = orig
        self.assertEqual(calls, [])


class CorsTests(WatchEndpointCase):
    def test_the_wildcard_origin_is_gone(self):
        source = (SCRAPERS / "subscribe_server.py").read_text()
        self.assertNotIn('"Access-Control-Allow-Origin", "*"', source)
        self.assertEqual(server.ALLOWED_ORIGIN, "https://treestock.com.au")


if __name__ == "__main__":
    unittest.main()
