"""
The CSRF layer on the admin write path (DAL-284).

Authentication was never the gap. `cf_access_claims` verifies an RS256 signature
against Cloudflare's JWKS, checks audience and issuer, and fails closed. The gap
is that `_extract_cf_token` falls back to the `CF_Authorization` cookie, and a
cookie rides along on a cross-site request whether or not the user meant it.

MEASURED 2026-08-17 rather than assumed, because the plan says not to take the
mitigation on trust: an unauthenticated request to the Access-protected path
comes back with `CF_AppSession=...; Path=/; Secure; HttpOnly` and **no SameSite
attribute at all**. A cookie with no SameSite is Lax by *browser default*, which
is a property of the visitor's browser, not a guarantee the origin can make, and
Chrome's Lax-by-default still permits a cross-site POST within two minutes of
the cookie being set.

So these tests exist to pin the three controls that do NOT depend on the
browser's default. Each is independently sufficient to stop the classic attack,
and the tests treat each as if it were the only one.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import subscribe_server as ss

SECRET = "0" * 64
OTHER_SECRET = "1" * 64
SUBJECT = "b@bjnoel.com"
NOW = 1_786_939_855


class Headers(dict):
    """http.client-style case-insensitive get, which is what the handler sees."""

    def get(self, key, default=""):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class OriginCheckTests(unittest.TestCase):
    """Layer 1. Browsers always send Origin on POST, so a missing one is not a
    browser and gets no benefit of the doubt."""

    def test_our_own_origin_passes(self):
        self.assertTrue(ss.admin_post_origin_ok(
            Headers({"Origin": "https://treestock.com.au"})))

    def test_another_origin_is_refused(self):
        for origin in ("https://evil.example",
                       "https://treestock.com.au.evil.example",
                       "http://treestock.com.au",          # scheme matters
                       "https://beestock.com.au"):
            with self.subTest(origin=origin):
                self.assertFalse(ss.admin_post_origin_ok(Headers({"Origin": origin})))

    def test_a_missing_origin_is_refused_rather_than_waved_through(self):
        self.assertFalse(ss.admin_post_origin_ok(Headers({})))

    def test_sec_fetch_site_must_not_contradict_the_origin(self):
        """Belt and braces: a cross-site request that somehow carried our Origin
        would still be labelled cross-site by the browser itself."""
        for site, ok in (("same-origin", True), ("", True),
                         ("cross-site", False), ("same-site", False)):
            with self.subTest(site=site):
                h = Headers({"Origin": "https://treestock.com.au"})
                if site:
                    h["Sec-Fetch-Site"] = site
                self.assertEqual(ss.admin_post_origin_ok(h), ok)


class TokenTests(unittest.TestCase):
    """Layer 3. Another origin cannot read the page, so it cannot get the
    token. That is the property; these tests are about not giving it away."""

    def token(self, subject=SUBJECT, now=NOW, secret=SECRET):
        return ss.admin_csrf_token(subject, now=now, secret=secret)

    def test_a_fresh_token_verifies(self):
        self.assertTrue(ss.verify_admin_csrf(self.token(), SUBJECT, now=NOW,
                                             secret=SECRET))

    def test_a_token_for_someone_else_does_not_verify(self):
        """Bound to the JWT subject. Two people behind the same Access app must
        not be able to replay each other's tokens."""
        self.assertFalse(ss.verify_admin_csrf(self.token(subject="other@x.com"),
                                              SUBJECT, now=NOW, secret=SECRET))

    def test_a_token_signed_with_another_secret_does_not_verify(self):
        self.assertFalse(ss.verify_admin_csrf(self.token(secret=OTHER_SECRET),
                                              SUBJECT, now=NOW, secret=SECRET))

    def test_an_expired_token_does_not_verify(self):
        old = self.token(now=NOW - ss.ADMIN_CSRF_TTL_SECONDS - 1)
        self.assertFalse(ss.verify_admin_csrf(old, SUBJECT, now=NOW, secret=SECRET))

    def test_a_token_just_inside_the_ttl_still_verifies(self):
        edge = self.token(now=NOW - ss.ADMIN_CSRF_TTL_SECONDS + 5)
        self.assertTrue(ss.verify_admin_csrf(edge, SUBJECT, now=NOW, secret=SECRET))

    def test_a_future_dated_token_does_not_verify(self):
        """Forged, or a clock that moved. Either way not something to honour for
        the next eight hours."""
        self.assertFalse(ss.verify_admin_csrf(self.token(now=NOW + 3600),
                                              SUBJECT, now=NOW, secret=SECRET))

    def test_small_clock_skew_is_tolerated(self):
        self.assertTrue(ss.verify_admin_csrf(self.token(now=NOW + 30),
                                             SUBJECT, now=NOW, secret=SECRET))

    def test_garbage_does_not_verify_and_does_not_raise(self):
        for bad in ("", "x", "....", "abc.def", "9999999999999999999.aa",
                    "notanumber.aa", None):
            with self.subTest(bad=bad):
                self.assertFalse(ss.verify_admin_csrf(bad or "", SUBJECT, now=NOW,
                                                      secret=SECRET))

    def test_no_secret_means_no_token_and_no_verification(self):
        """Fails closed. A server that could not persist a secret must not mint
        tokens from an empty string, because then everyone can."""
        self.assertEqual(ss.admin_csrf_token(SUBJECT, now=NOW, secret=""), "")
        self.assertFalse(ss.verify_admin_csrf("1.2", SUBJECT, now=NOW, secret=""))

    def test_no_subject_means_no_token(self):
        self.assertEqual(ss.admin_csrf_token("", now=NOW, secret=SECRET), "")
        self.assertFalse(ss.verify_admin_csrf(self.token(), "", now=NOW,
                                              secret=SECRET))

    def test_the_admin_secret_is_not_the_unsubscribe_secret(self):
        """One secret signing two kinds of token means a bug in either lets you
        mint the other, and these protect completely different things.

        Checks the key the code actually reads, not the prose around it: an
        earlier version of this test matched the word in the docstring and would
        have passed with the two secrets merged."""
        from stocklib.mailer import get_unsubscribe_secret  # noqa: F401
        self.assertEqual(ss._ADMIN_SECRET_KEY, "ADMIN_CSRF_SECRET")
        self.assertNotEqual(ss._ADMIN_SECRET_KEY, "UNSUBSCRIBE_SECRET")
        code = [ln for ln in
                (SCRAPERS / "subscribe_server.py").read_text().splitlines()
                if "get_unsubscribe_secret" in ln and not ln.strip().startswith("#")]
        self.assertEqual(
            [ln for ln in code if "_admin" in ln or "csrf" in ln.lower()], [],
            "the admin token must not be derived from the unsubscribe secret")


class WiringTests(unittest.TestCase):
    """The gates exist AND are actually in front of the handler. A perfect check
    nobody calls is the failure mode these are for."""

    def source(self):
        return (SCRAPERS / "subscribe_server.py").read_text()

    def test_the_write_path_is_not_in_the_public_post_allowlist(self):
        src = self.source()
        allowlist = src[src.index("def do_POST"):src.index("Cap before reading")]
        self.assertNotIn("/admin/varieties/decide", allowlist.split("if path not in")[-1])

    def test_the_handler_checks_origin_content_type_jwt_and_token(self):
        src = self.source()
        body = src[src.index("def _handle_admin_decide"):
                   src.index("def send_admin_json")]
        for needle in ("admin_post_origin_ok", "application/json",
                       "cf_access_claims", "verify_admin_csrf"):
            with self.subTest(needle=needle):
                self.assertIn(needle, body)

    def test_the_gates_come_before_the_body_is_read(self):
        """Order matters: reading the body first lets a stranger decide how much
        memory this process allocates before any check has run."""
        src = self.source()
        body = src[src.index("def _handle_admin_decide"):
                   src.index("def send_admin_json")]
        self.assertLess(body.index("admin_post_origin_ok"), body.index("rfile.read"))
        self.assertLess(body.index("cf_access_claims"), body.index("rfile.read"))

    def test_the_write_path_answers_no_cors_preflight(self):
        src = self.source()
        opts = src[src.index("def do_OPTIONS"):src.index("def _client_ip")]
        self.assertIn("ADMIN_DECIDE_PATH", opts)
        self.assertLess(opts.index("ADMIN_DECIDE_PATH"),
                        opts.index("Access-Control-Allow-Origin"))

    def test_a_refusal_is_a_409_and_never_a_partial_write(self):
        src = self.source()
        body = src[src.index("def _handle_admin_decide"):
                   src.index("def send_admin_json")]
        self.assertIn("DecisionRefused", body)
        self.assertIn("409", body)

    def test_verify_cf_access_still_works_for_the_read_only_pages(self):
        """Refactoring it to return claims must not have changed the boolean
        contract every read page depends on."""
        self.assertFalse(ss.verify_cf_access(Headers({})))


if __name__ == "__main__":
    unittest.main()
