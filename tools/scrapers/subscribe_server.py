#!/usr/bin/env python3
"""
Minimal email subscription server for treestock.com.au stock alerts.

Runs as a tiny HTTP server that accepts POST /subscribe with an email address.
Stores subscribers in a JSON file. Designed to run behind Caddy reverse proxy.

Usage:
    python3 subscribe_server.py                    # Default port 8099
    python3 subscribe_server.py --port 8099

Caddy config addition:
    handle /api/subscribe {
        reverse_proxy localhost:8099
    }
    handle /api/preferences {
        reverse_proxy localhost:8099
    }
"""

import hashlib
import hmac
import html
import json
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import urllib.request
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlparse

import admin_view
import digest_archive
import nursery_inbound

from stocklib.mailer import (SUBSCRIBERS_FILE, get_unsubscribe_secret,
                             make_unsubscribe_token, load_subscribers)
from stocklib.variety_index import (DEFAULT_INDEX_PATH, get_variety_index,
                                    is_valid_slug)

try:
    import jwt  # PyJWT — validates the Cloudflare Access JWT on /admin
except ImportError:  # server fails closed (403) if PyJWT is missing
    jwt = None

SCRIPT_DIR = Path(__file__).parent

DATA_DIR = Path("/opt/dale/data")
PENDING_FILE = DATA_DIR / "pending_subscribers.json"
APP_ENV = Path("/opt/dale/secrets/app.env")
VARIETY_WATCHES_DB = DATA_DIR / "variety_watches.db"
MANAGE_LINK_LOG = DATA_DIR / "manage_link_sends.json"
# Sibling of the manage-link log, deliberately a separate file: the two
# throttles must not be able to suppress each other.
WATCH_NOTICE_LOG = DATA_DIR / "watch_notice_sends.json"
# Written by build_variety_pages.py. The server never parses cultivar names
# itself; it reads this map to decide whether a watched slug is real and to
# take the title from us rather than from the caller.
VARIETY_INDEX_FILE = DEFAULT_INDEX_PATH
PORT = 8099
CONFIRM_EXPIRY_HOURS = 48
MANAGE_LINK_RATE_LIMIT_SECONDS = 3600  # one manage-link email per address per hour
# One "you're now watching X" per address per hour. This is an abuse ceiling,
# not a courtesy: it caps what a forged-address attack can make a victim
# receive at 24 emails a day instead of one per watch created. The notice lists
# every variety the address watches, so a watch added inside a throttled window
# is acknowledged by the next notice rather than lost.
WATCH_NOTICE_RATE_LIMIT_SECONDS = 3600

# --- Abuse limits on watch creation ---------------------------------------
# Nothing sat between a script and 90 real inboxes: /api/watch-variety took a
# valid-looking email and inserted a live watch, with no cap, no rate limit and
# no body-size limit. These are the ceilings. Read the honesty note on
# _client_ip before treating the per-IP one as the control that holds.

# Every POST this server accepts is a handful of fields. 8KB is far above any
# real payload and far below anything worth parsing from a stranger.
# One list, because there were four copies of it and this adds a fifth caller.
VALID_STATES = {"ALL", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT"}

# Every POST route this server answers. Named so a test can assert a new
# action landed on an existing path: a genuinely new endpoint also needs a
# Caddy allowlist entry, and forgetting that ships a 404 to real people.
ALLOWED_POST_PATHS = (
    "/subscribe", "/api/subscribe",
    "/watch-variety", "/api/watch-variety",
    "/unwatch-variety", "/api/unwatch-variety",
    "/wishlist", "/api/wishlist",
    "/request-manage-link", "/api/request-manage-link",
)

MAX_BODY_BYTES = 8192

# Bounds the blast radius of one forged address. Not spoofable, unlike the IP.
MAX_WATCHES_PER_ADDRESS = 50

# Generous on purpose: a collector adding alerts while browsing is the normal
# case and must not be throttled. It exists to make bulk creation expensive,
# not to police ordinary use.
WATCH_IP_LIMIT = 30
WATCH_IP_WINDOW_SECONDS = 3600

# Turnstile stays OFF until a secret exists in app.env (creating the keys is
# Benedict's job). The hook is here so enabling it is a secret plus nothing
# else, rather than a code change made under pressure.
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_TIMEOUT_SECONDS = 3

# CORS. Hygiene, NOT abuse protection: a browser enforces it and a script
# ignores it entirely, and these endpoints carry no cookie auth for a malicious
# site to ride. Narrowed from "*" anyway, because "*" advertises an intent to
# be called from anywhere that was never true.
ALLOWED_ORIGIN = "https://treestock.com.au"

VALID_CATEGORIES = ("new_products", "price_drops", "back_in_stock")
# Plant categories a subscriber can opt into (DAL-199). bush_tucker is OFF by
# default; "fruit" is the default everyone gets. Distinct from VALID_CATEGORIES
# above, which is the change-TYPE preference (restock / price drop / new).
VALID_PLANT_CATEGORIES = ("fruit", "bush_tucker")
DEFAULT_PLANT_CATEGORIES = ("fruit",)
VALID_FREQUENCIES = ("daily", "weekly", "off")


def init_variety_watches_db():
    """Initialise the SQLite DB for per-variety restock watches and wishlists."""
    VARIETY_WATCHES_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(VARIETY_WATCHES_DB)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            variety_slug TEXT NOT NULL,
            species_slug TEXT NOT NULL,
            variety_title TEXT NOT NULL,
            added_at TEXT NOT NULL,
            UNIQUE(email, variety_slug)
        );
        CREATE TABLE IF NOT EXISTS sends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            variety_slug TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            UNIQUE(email, variety_slug, sent_at)
        );
        CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            species_slug TEXT NOT NULL,
            added_at TEXT NOT NULL,
            UNIQUE(email, species_slug)
        );
        -- Per-IP rate-limit state. A table rather than a second JSON file
        -- because this DB is already open on the watch path, and because
        -- "DELETE WHERE ts < ?" is the pruning the JSON files do not get.
        -- Rows are deleted once they leave the window, so this holds at most
        -- an hour of addresses.
        -- State lives on the PERSON, not the watch. A column on `watches`
        -- would let one person's two watches disagree about where they live,
        -- and the alert sender asks the question once per address. Absent or
        -- 'ALL' means no filtering, which is what all 104 pre-existing
        -- watchers read as, so adding this changes nobody's mail until they
        -- set a state.
        CREATE TABLE IF NOT EXISTS watcher_prefs (
            email      TEXT PRIMARY KEY,
            state      TEXT NOT NULL DEFAULT 'ALL',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS watch_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            ts TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_watch_attempts_ip_ts
            ON watch_attempts(ip, ts);
    """)
    con.commit()
    con.close()


def turnstile_secret() -> str:
    """Empty until Benedict creates the keys and puts TURNSTILE_SECRET in
    app.env. Read per call rather than cached at import, so turning it on is a
    file edit and a service restart, not a deploy."""
    return _read_app_env("TURNSTILE_SECRET")


def turnstile_ok(token: str, remote_ip: str) -> bool:
    """Verify a Turnstile token, or pass when Turnstile is not configured.

    Passing when unconfigured is the whole point of the flag gate: the code
    path is live and exercised today as a no-op, so switching it on later
    cannot be the change that discovers a bug in it.

    The server is single-threaded, so the outbound call is bounded by a short
    timeout and a failure to reach Cloudflare passes rather than blocks. That
    is the right trade while this is a second line of defence behind the
    per-address cap; it would not be if it were the only one.
    """
    secret = turnstile_secret()
    if not secret:
        return True
    if not token:
        return False
    payload = urlencode({"secret": secret, "response": token,
                         "remoteip": remote_ip}).encode()
    try:
        with urllib.request.urlopen(
                urllib.request.Request(TURNSTILE_VERIFY_URL, data=payload),
                timeout=TURNSTILE_TIMEOUT_SECONDS) as resp:
            return bool(json.loads(resp.read()).get("success"))
    except Exception as e:
        print(f"Warning: Turnstile verification unreachable ({e}); allowing")
        return True


def verify_unsubscribe_token(email: str, token: str) -> bool:
    expected = make_unsubscribe_token(email)
    if not expected:
        return False
    return hmac.compare_digest(expected, token)


def make_confirm_token(email: str, state: str) -> str:
    """Generate a confirmation token bound to the email + chosen state."""
    secret = get_unsubscribe_secret()
    msg = f"confirm:{email.lower()}:{state.upper()}"
    return hmac.new(
        secret.encode(), msg.encode(), hashlib.sha256
    ).hexdigest()[:32]


def verify_confirm_token(email: str, state: str, token: str) -> bool:
    expected = make_confirm_token(email, state)
    return hmac.compare_digest(expected, token)


def load_pending() -> list:
    if PENDING_FILE.exists():
        with open(PENDING_FILE) as f:
            return json.load(f)
    return []


def save_pending(pending: list):
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_FILE, "w") as f:
        json.dump(pending, f, indent=2)


def purge_expired_pending(pending: list) -> list:
    """Remove pending entries older than CONFIRM_EXPIRY_HOURS."""
    now = datetime.now()
    cutoff_hours = CONFIRM_EXPIRY_HOURS
    fresh = []
    for entry in pending:
        try:
            requested = datetime.fromisoformat(entry["requested_at"])
            age_hours = (now - requested).total_seconds() / 3600
            if age_hours <= cutoff_hours:
                fresh.append(entry)
        except Exception:
            pass
    return fresh


def save_subscribers(subscribers: list):
    SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(subscribers, f, indent=2)


def is_valid_email(email: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))


def _load_manage_link_log() -> dict:
    return _load_json_log(MANAGE_LINK_LOG)


def _save_manage_link_log(log: dict):
    _save_json_log(MANAGE_LINK_LOG, log)


def _load_json_log(path: Path) -> dict:
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_json_log(path: Path, log: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(log, f, indent=2)


def _read_app_env(key: str) -> str:
    """Read a single KEY=value from app.env (same format as UNSUBSCRIBE_SECRET)."""
    if APP_ENV.exists():
        with open(APP_ENV) as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    return ""


def _normalize_cf_team_domain(value: str) -> str:
    """Accept either a full URL (https://team.cloudflareaccess.com) or a bare
    team slug (team) and return the full Access domain used as both the JWKS
    endpoint base and the expected JWT issuer."""
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}.cloudflareaccess.com"
    return value


_cf_jwks_client = None


def _get_cf_jwks_client(team_domain: str):
    """Cache a PyJWKClient for the Cloudflare Access team JWKS endpoint."""
    global _cf_jwks_client
    if _cf_jwks_client is None and jwt is not None:
        _cf_jwks_client = jwt.PyJWKClient(f"{team_domain}/cdn-cgi/access/certs")
    return _cf_jwks_client


def _extract_cf_token(headers) -> str:
    """CF Access injects the JWT as a header (and a cookie). Prefer the header."""
    token = headers.get("Cf-Access-Jwt-Assertion", "")
    if token:
        return token.strip()
    cookie = headers.get("Cookie", "")
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("CF_Authorization="):
            return part.split("=", 1)[1].strip()
    return ""


def cf_access_claims(headers) -> dict | None:
    """Validate the Cloudflare Access JWT and return its claims, or None.

    CF Access authenticates at the edge, but the origin is publicly reachable, so
    a direct-to-origin request would bypass it. Validating the signed
    Cf-Access-Jwt-Assertion here closes that hole. Fails closed (returns None)
    on any missing config, missing token, or verification error.

    Returns the claims rather than a bool because the admin write path needs the
    subject: a CSRF token bound to nobody is a CSRF token anybody can mint.
    """
    if jwt is None:
        print("CF Access check failed: PyJWT not installed", file=sys.stderr)
        return None
    team_domain = _normalize_cf_team_domain(_read_app_env("CF_ACCESS_TEAM_DOMAIN"))
    aud = _read_app_env("CF_ACCESS_AUD")
    if not team_domain or not aud:
        print(
            "CF Access check failed: CF_ACCESS_TEAM_DOMAIN/CF_ACCESS_AUD not set in app.env",
            file=sys.stderr,
        )
        return None
    token = _extract_cf_token(headers)
    if not token:
        return None
    try:
        signing_key = _get_cf_jwks_client(team_domain).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=aud,
            issuer=team_domain,
        )
    except Exception as e:
        print(f"CF Access verification failed: {e}", file=sys.stderr)
        return None


def verify_cf_access(headers) -> bool:
    """Boolean form, for the read-only pages that only need the gate."""
    return cf_access_claims(headers) is not None


def cf_access_subject(headers) -> str:
    """Who the verified JWT says this is. '' when unauthenticated."""
    claims = cf_access_claims(headers) or {}
    return str(claims.get("email") or claims.get("sub") or "")


# ---------------------------------------------------------------------------
# CSRF for the admin write path (DAL-284)
#
# Authentication was never the gap. `cf_access_claims` verifies an RS256
# signature against Cloudflare's JWKS, checks audience and issuer, and fails
# closed. The gap is that `_extract_cf_token` falls back to the
# `CF_Authorization` cookie, and a cookie rides along on a cross-site request
# whether or not the user meant to send one.
#
# MEASURED 2026-08-17, because the plan says verify rather than assume: an
# unauthenticated hit on https://treestock.com.au/admin/varieties comes back with
#
#     set-cookie: CF_AppSession=...; Expires=...; Path=/; Secure; HttpOnly
#
# with NO SameSite attribute at all (the login host's own CF_Session is
# explicitly SameSite=none). A cookie with no SameSite is Lax *by browser
# default*, which is a property of the visitor's browser and not something this
# server can know or enforce, and Chrome's Lax-by-default still permits a
# cross-site POST within two minutes of the cookie being set. `CF_Authorization`
# itself cannot be observed without completing the login, but it is issued by
# the same flow on the same host.
#
# So SameSite is defence in depth here, not the control. Three independent
# layers that do not depend on the browser's default:
#
#   1. Origin must equal the site. Browsers always send it on POST.
#   2. Content-Type must be application/json, which makes a cross-origin attempt
#      a preflighted request rather than a "simple" one. We answer no preflight
#      for a foreign origin, so it never reaches the handler.
#   3. A token bound to the JWT subject, rendered into the page and echoed back.
#      Another origin cannot read the page, so it cannot obtain the token.
#
# Any one of the three failing still leaves two.
# ---------------------------------------------------------------------------

ADMIN_CSRF_TTL_SECONDS = 8 * 3600
_ADMIN_SECRET_KEY = "ADMIN_CSRF_SECRET"


def _admin_csrf_secret(create: bool = True) -> str:
    """A stable secret in app.env, generated once.

    Separate from UNSUBSCRIBE_SECRET on purpose. One secret signing two kinds of
    token means a bug in either lets you mint the other, and these two protect
    completely different things.
    """
    existing = _read_app_env(_ADMIN_SECRET_KEY)
    if existing:
        return existing
    if not create:
        return ""
    import secrets as _secrets
    secret = _secrets.token_hex(32)
    try:
        APP_ENV.parent.mkdir(parents=True, exist_ok=True)
        with open(APP_ENV, "a") as f:
            f.write(f"{_ADMIN_SECRET_KEY}={secret}\n")
    except OSError as e:
        print(f"Could not persist {_ADMIN_SECRET_KEY}: {e}", file=sys.stderr)
        return ""
    print(f"Generated new {_ADMIN_SECRET_KEY} in {APP_ENV}")
    return secret


def admin_csrf_token(subject: str, now: int = None, secret: str = None) -> str:
    """`<issued>.<hmac>`, bound to the authenticated subject."""
    secret = _admin_csrf_secret() if secret is None else secret
    if not secret or not subject:
        return ""
    issued = int(time.time() if now is None else now)
    mac = hmac.new(secret.encode(), f"{subject}|{issued}".encode(),
                   hashlib.sha256).hexdigest()
    return f"{issued}.{mac}"


def verify_admin_csrf(token: str, subject: str, now: int = None,
                      secret: str = None) -> bool:
    """Constant-time check of a token against this subject, within the TTL."""
    secret = _admin_csrf_secret(create=False) if secret is None else secret
    if not secret or not subject or not token or "." not in token:
        return False
    issued_raw, _, mac = token.partition(".")
    try:
        issued = int(issued_raw)
    except ValueError:
        return False
    current = int(time.time() if now is None else now)
    # A future-dated token is a forged one, allowing a small skew for a clock
    # that moved between render and submit.
    if issued > current + 60 or current - issued > ADMIN_CSRF_TTL_SECONDS:
        return False
    expected = hmac.new(secret.encode(), f"{subject}|{issued}".encode(),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, mac)


def admin_post_origin_ok(headers) -> bool:
    """Layer 1. The request has to say it came from us.

    A missing Origin is refused rather than waved through. Every browser sends
    it on POST, so the only things it excludes are non-browser clients, and a
    non-browser client can use the header too.
    """
    if headers.get("Origin", "") != ALLOWED_ORIGIN:
        return False
    fetch_site = headers.get("Sec-Fetch-Site", "")
    return fetch_site in ("", "same-origin")


class SubscribeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = dict(parse_qsl(parsed.query))
        email = params.get("email", "").strip().lower()
        token = params.get("token", "").strip()

        # Read-only subscriber admin view. Gated by Cloudflare Access at the edge
        # AND by JWT validation here (so a direct-to-origin hit can't reach it).
        # /admin (business state), /admin/subscribers, /admin/nurseries. One
        # model, three views; the split keeps each page short enough to read.
        # rstrip only the trailing slash of a real subpath: "/" must stay "/",
        # or it would normalise to "" and fall through to the admin lookup.
        admin_path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
        if admin_path in admin_view.ADMIN_RENDERERS:
            claims = cf_access_claims(self.headers)
            if claims is None:
                self.send_html(403, "<h2>403 Forbidden</h2><p>This page is gated by Cloudflare Access.</p>")
                return
            try:
                render = admin_view.ADMIN_RENDERERS[admin_path]
                model = admin_view.load_admin_data()
                # The review page's buttons echo this back. Minted per render and
                # bound to whoever the JWT says is here, so it cannot be reused
                # from another origin or by another account.
                model["csrf"] = admin_csrf_token(
                    str(claims.get("email") or claims.get("sub") or ""))
                # ?q= narrows the review queues to one cultivar. Capped at a
                # slug's length: it only ever reaches a substring test against
                # slugs, and an unbounded query string on a page that renders
                # 2,700 rows is work a request should not be able to ask for.
                model["q"] = params.get("q", "")[:80]
                page = render(model)
            except Exception as e:
                print(f"Admin view render error: {e}", file=sys.stderr)
                self.send_html(500, "<h2>500</h2><p>Could not build the admin view.</p>")
                return
            self.send_admin_html(page)
            return

        # The variety inventory's data payload. Same Access gate, same read-only
        # posture; it exists because /admin/varieties covers 2,767 pages and the
        # ledger behind them is 3.1MB, so the detail is fetched and filtered in
        # the browser rather than inlined into the HTML.
        if admin_path in admin_view.ADMIN_JSON:
            if not verify_cf_access(self.headers):
                self.send_admin_json({"error": "forbidden"}, status=403)
                return
            try:
                payload = admin_view.ADMIN_JSON[admin_path](admin_view.load_admin_data())
            except Exception as e:
                print(f"Admin JSON build error: {e}", file=sys.stderr)
                self.send_admin_json({"error": "could not build the payload"}, status=500)
                return
            self.send_admin_json(payload)
            return

        # Archived daily digests. Same Cloudflare Access gate as /admin (the
        # Access app covers /admin and every subpath; verified 2026-08-10), and
        # the same fail-closed JWT check here for direct-to-origin hits.
        if parsed.path == "/admin/digest" or parsed.path.startswith("/admin/digest/"):
            if not verify_cf_access(self.headers):
                self.send_html(403, "<h2>403 Forbidden</h2><p>This page is gated by Cloudflare Access.</p>")
                return
            day = parsed.path[len("/admin/digest"):].strip("/") or None
            try:
                status, page = digest_archive.render_digest_page(day=day)
            except Exception as e:
                print(f"Digest archive render error: {e}", file=sys.stderr)
                self.send_html(500, "<h2>500</h2><p>Could not build the digest archive.</p>")
                return
            self.send_admin_html(page, status=status)
            return

        if parsed.path in ("/wishlist-counts", "/api/wishlist-counts"):
            try:
                con = sqlite3.connect(VARIETY_WATCHES_DB)
                rows = con.execute(
                    "SELECT species_slug, COUNT(*) as cnt FROM wishlist GROUP BY species_slug ORDER BY cnt DESC"
                ).fetchall()
                con.close()
            except sqlite3.Error as e:
                self.send_json(500, {"error": f"DB error: {e}"})
                return
            counts = {r[0]: r[1] for r in rows}
            self.send_json(200, counts)
            return

        if parsed.path in ("/confirm", "/api/confirm"):
            state = params.get("state", "ALL").upper().strip()
            if state not in VALID_STATES:
                state = "ALL"

            if not email or not token:
                self.send_html(400, "<h2>Invalid confirmation link.</h2><p>The link is missing required parameters.</p>")
                return

            if not verify_confirm_token(email, state, token):
                self.send_html(400, "<h2>Invalid or expired confirmation link.</h2><p>Please subscribe again at <a href='https://treestock.com.au'>treestock.com.au</a></p>")
                return

            # Check if pending entry exists
            pending = load_pending()
            pending = purge_expired_pending(pending)
            entry = next((p for p in pending if p["email"] == email and p.get("state", "ALL") == state), None)
            if not entry:
                # May have already been confirmed — check active subscribers
                subscribers = load_subscribers()
                if any(s["email"] == email for s in subscribers):
                    self.send_html(200, """<h2>Already subscribed!</h2>
<p>You're already receiving treestock.com.au stock alerts.</p>
<div style="margin-top:24px;padding:16px;border:1px solid #bbf7d0;background:#f0fdf4;border-radius:8px">
  <p style="margin:0 0 6px 0;font-weight:600;color:#065f46">Track the trees you buy</p>
  <p style="margin:0 0 10px 0;font-size:14px;color:#374151">
    Have a look at <strong>Treesmith</strong>, our mobile app for plant collectors. Catalog every plant, log grafts and harvests, capture growth photos over time.
  </p>
  <a href="https://treestock.com.au/treesmith.html?utm_source=treestock&amp;utm_medium=confirm_page&amp;utm_campaign=treesmith_launch"
     style="color:#065f46;font-weight:600">Learn more about Treesmith &rarr;</a>
</div>""")
                else:
                    self.send_html(400, "<h2>Confirmation link expired.</h2><p>Please subscribe again at <a href='https://treestock.com.au'>treestock.com.au</a></p>")
                return

            # Move from pending to active
            pending = [p for p in pending if not (p["email"] == email and p.get("state", "ALL") == state)]
            save_pending(pending)

            subscribers = load_subscribers()
            if not any(s["email"] == email for s in subscribers):
                subscribers.append({
                    "email": email,
                    "subscribed_at": datetime.now().isoformat(),
                    "state": state,
                })
                save_subscribers(subscribers)
                print(f"Confirmed subscriber: {email} (state={state}, total: {len(subscribers)})")

                # Send welcome email (non-blocking)
                welcome_script = SCRIPT_DIR / "send_welcome_email.py"
                if welcome_script.exists():
                    try:
                        subprocess.Popen(
                            [sys.executable, str(welcome_script), email],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    except Exception as ex:
                        print(f"Warning: could not launch welcome email: {ex}")

            self.send_confirm_success_page(email)
            return

        if parsed.path in ("/unsubscribe", "/api/unsubscribe"):
            if not email or not token or not verify_unsubscribe_token(email, token):
                self.send_html(400, "<h2>Invalid unsubscribe link.</h2><p>Please contact us at treestock.com.au</p>")
                return

            subscribers = load_subscribers()
            updated = [s for s in subscribers if s["email"] != email]
            if len(updated) < len(subscribers):
                save_subscribers(updated)
                print(f"Unsubscribed: {email}")
                self.send_html(200, f"<h2>Unsubscribed</h2><p>{email} has been removed from treestock.com.au alerts.</p>")
            else:
                self.send_html(200, "<h2>Not found</h2><p>That email wasn't in our list.</p>")
            return

        if parsed.path in ("/preferences", "/api/preferences"):
            if not email or not token or not verify_unsubscribe_token(email, token):
                self.send_html(400, "<h2>Invalid link.</h2><p>Please use the link from your email.</p>")
                return

            subscribers = load_subscribers()
            subscriber = next((s for s in subscribers if s["email"] == email), None)
            if not subscriber:
                # Watch-only address: holds variety alerts but never subscribed
                # to the digest. This used to 404, which made "Manage your
                # alerts" a dead link for the large majority of alert
                # recipients (83 of 89 at the time of writing). They get the
                # watch list and nothing else, because there are no digest
                # preferences to show.
                if self._get_variety_watches(email):
                    self.send_watch_only_page(email, token)
                else:
                    self.send_html(404, "<h2>Not found</h2><p>That email isn't in our subscriber list.</p>")
                return

            current_state = subscriber.get("state", "WA" if subscriber.get("wa_only") else "ALL")
            current_categories = subscriber.get("categories")
            if current_categories is None:
                current_categories = list(VALID_CATEGORIES)
            current_plant_categories = subscriber.get("plant_categories")
            if current_plant_categories is None:
                current_plant_categories = list(DEFAULT_PLANT_CATEGORIES)
            current_frequency = subscriber.get("frequency", "daily")
            if current_frequency not in VALID_FREQUENCIES:
                current_frequency = "daily"
            self.send_preferences_page(email, token, current_state, current_categories, current_plant_categories, current_frequency)
            return

        self.send_error(404)

    def _handle_resend_inbound(self):
        """Resend `email.received` webhook -> nursery touch log (DAL-273).

        Reads raw bytes rather than reusing the decoded body below, because the
        Svix signature covers the exact bytes received. Decoding and re-encoding
        round-trips for valid UTF-8, but a mismatch here means silently
        rejecting real mail, which is not a risk worth taking to share a line.
        """
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > 1_000_000:          # a metadata-only payload is ~1KB
            self.send_json(413, {"error": "payload too large"})
            return
        raw = self.rfile.read(length)

        headers = {
            "svix-id": self.headers.get("svix-id"),
            "svix-timestamp": self.headers.get("svix-timestamp"),
            "svix-signature": self.headers.get("svix-signature"),
        }

        try:
            result = nursery_inbound.handle(
                raw, headers,
                register_path=str(admin_view.NURSERY_CONTACTS_FILE))
        except nursery_inbound.InboundError as e:
            # Two distinct outcomes, deliberately different codes. A bad
            # signature is 401 and Resend keeps retrying, which is what we want
            # if we have merely misconfigured the secret. Anything else is a
            # message we will never want (not addressed to us, no nursery
            # matched), so 202 tells Resend to stop retrying it forever.
            reason = str(e)
            unauthorised = ("signature" in reason or "svix" in reason
                            or "secret" in reason or "timestamp" in reason)
            print(f"resend-inbound rejected: {reason}", file=sys.stderr)
            if unauthorised:
                self.send_json(401, {"error": "unauthorized"})
            else:
                self.send_json(202, {"status": "ignored"})
            return
        except Exception as e:  # noqa: BLE001 - never 500 a webhook into a retry storm
            print(f"resend-inbound error: {e}", file=sys.stderr)
            self.send_json(500, {"error": "internal"})
            return

        print(f"resend-inbound: {result}")
        self.send_json(200, {"status": result})

    def do_POST(self):
        path = self.path.split("?")[0]

        # Handled before the allowlist below because it needs the raw body.
        if path in ("/resend-inbound", "/api/resend-inbound"):
            self._handle_resend_inbound()
            return

        # The admin write path. Before the allowlist because it has its own,
        # much stricter gate; adding it to the public allowlist would be one
        # edit away from a public write endpoint.
        if path == admin_view.ADMIN_DECIDE_PATH:
            self._handle_admin_decide()
            return

        if path not in ALLOWED_POST_PATHS:
            self.send_error(404)
            return

        # Cap before reading, not after. Reading first and validating later
        # means a stranger decides how much memory this process allocates.
        try:
            content_length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            self.send_json(400, {"error": "Invalid Content-Length"})
            return
        if content_length > MAX_BODY_BYTES:
            self.send_json(413, {"error": "Payload too large"})
            return
        try:
            body = self.rfile.read(content_length).decode()
        except UnicodeDecodeError:
            self.send_json(400, {"error": "Invalid encoding"})
            return

        # Self-serve magic-link request: any email gets a uniform 200 so we don't
        # leak which addresses are subscribed. Only confirmed subscribers receive
        # an actual email, and we rate-limit at most one per hour per address.
        if path in ("/request-manage-link", "/api/request-manage-link"):
            try:
                if self.headers.get("Content-Type", "").startswith("application/json"):
                    payload = json.loads(body)
                    requested_email = payload.get("email", "")
                else:
                    requested_email = parse_qs(body).get("email", [""])[0]
            except (json.JSONDecodeError, KeyError):
                self.send_json(400, {"error": "Invalid request"})
                return

            requested_email = (requested_email or "").strip().lower()
            if not requested_email or not is_valid_email(requested_email):
                self.send_json(400, {"error": "Valid email required"})
                return

            generic_ok = {"message": "If that email is subscribed, a manage-alerts link is on its way."}

            send_log = _load_manage_link_log()
            last_sent_iso = send_log.get(requested_email)
            if last_sent_iso:
                try:
                    last_sent = datetime.fromisoformat(last_sent_iso)
                    if (datetime.now() - last_sent).total_seconds() < MANAGE_LINK_RATE_LIMIT_SECONDS:
                        # Already sent recently — return the same generic response so
                        # rate-limited and non-subscriber requests are indistinguishable.
                        print(f"Manage-link request rate-limited: {requested_email}")
                        self.send_json(200, generic_ok)
                        return
                except ValueError:
                    pass

            subscribers = load_subscribers()
            subscriber = next((s for s in subscribers if s["email"] == requested_email), None)
            # Watch-only addresses count. This looked only in subscribers.json,
            # so the ~83 people who hold variety watches and never subscribed
            # to the digest were told "a link is on its way" and got nothing:
            # the in-email footer link worked, the site's own link did not.
            # That is the large majority of alert recipients.
            if subscriber is None and not self._get_variety_watches(requested_email):
                print(f"Manage-link request for unknown address (silent): {requested_email}")
                self.send_json(200, generic_ok)
                return

            token = make_unsubscribe_token(requested_email)
            if not token:
                # Misconfigured server — surface the error but still return generic OK to caller.
                print(f"ERROR: UNSUBSCRIBE_SECRET missing; cannot send manage-link for {requested_email}", file=sys.stderr)
                self.send_json(200, generic_ok)
                return

            # Launch the send script non-blocking so the HTTP response returns fast.
            send_script = SCRIPT_DIR / "send_manage_link_email.py"
            if send_script.exists():
                try:
                    subprocess.Popen(
                        [sys.executable, str(send_script), requested_email, token],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception as ex:
                    print(f"Warning: could not launch manage-link email: {ex}", file=sys.stderr)
            else:
                print(f"ERROR: send_manage_link_email.py not found", file=sys.stderr)

            send_log[requested_email] = datetime.now().isoformat()
            _save_manage_link_log(send_log)
            print(f"Manage-link email queued: {requested_email}")
            self.send_json(200, generic_ok)
            return

        # Handle per-variety watch
        if path in ("/watch-variety", "/api/watch-variety"):
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_json(400, {"error": "Invalid JSON"})
                return
            email = data.get("email", "").strip().lower()
            variety_slug = data.get("variety_slug", "").strip()
            species_slug = data.get("species_slug", "").strip()
            # data["variety_title"] is read and discarded on purpose. It used
            # to be stored and then interpolated into the subject and body of
            # mail sent to every other watcher of this slug, which handed a
            # stranger the copy in our email. The title now comes from the
            # index the builder writes; see stocklib/variety_index.py.
            if not email or not is_valid_email(email):
                self.send_json(400, {"error": "Valid email required"})
                return
            if not variety_slug:
                self.send_json(400, {"error": "variety_slug required"})
                return
            if not is_valid_slug(variety_slug) or (species_slug and not is_valid_slug(species_slug)):
                self.send_json(400, {"error": "Invalid variety"})
                return
            # Honeypot. The field is hidden and off the tab order, so a person
            # never fills it and a bot that fills every input does. Answer as
            # if it worked: telling a bot which check it failed is free help.
            if (data.get("website") or "").strip():
                print(f"Honeypot tripped on watch attempt: {variety_slug}")
                self.send_json(201, {"message": "Alert set!", "variety_slug": variety_slug})
                return
            client_ip = self._client_ip()
            if not turnstile_ok((data.get("turnstile_token") or "").strip(), client_ip):
                self.send_json(403, {"error": "Verification failed"})
                return
            if self._watch_rate_limited(client_ip):
                print(f"Rate-limited watch attempt from {client_ip}")
                self.send_json(429, {"error": "Too many alerts set from here. "
                                              "Try again in an hour."})
                return
            index = get_variety_index(VARIETY_INDEX_FILE)
            variety_title = index.title(variety_slug)
            if variety_title is None:
                # Only treat "absent from the index" as "not a real variety"
                # when we actually have an index. A deploy restarts this
                # service before the builders run, so the file can legitimately
                # be missing for a few minutes and failing closed there would
                # drop real signups. The slug already passed is_valid_slug, so
                # the fallback title is safe to render either way.
                if index.available:
                    print(f"Rejected watch on unknown variety slug: {variety_slug}")
                    self.send_json(404, {"error": "Unknown variety"})
                    return
                variety_title = index.display_title(variety_slug)
                print(f"WARNING: {VARIETY_INDEX_FILE} missing or empty; "
                      f"accepting {variety_slug} with a slug-derived title")
            # Per-address cap. Checked after the slug resolves so a caller
            # cannot burn someone else's allowance with junk slugs, and skipped
            # when the address already watches this one so hitting the cap can
            # never turn an idempotent re-watch into an error.
            if self._watch_count(email) >= MAX_WATCHES_PER_ADDRESS:
                already = any(w["slug"] == variety_slug
                              for w in self._get_variety_watches(email))
                if not already:
                    print(f"Watch cap reached for {email} "
                          f"({MAX_WATCHES_PER_ADDRESS})")
                    self.send_json(429, {
                        "error": f"That address is already watching "
                                 f"{MAX_WATCHES_PER_ADDRESS} varieties, which "
                                 f"is the limit."})
                    return
            # Optional state, sent by dashboard.js when the visitor has already
            # picked one in the homepage state filter. Deliberately NOT a field
            # on the watch form: the digest signup has a state dropdown and took
            # 12 signups in five months, the email-only watch pill took 104, and
            # the one-tap flow is the thing that works. This costs the visitor
            # nothing and only fires when they have already told us.
            # Never downgrades an existing preference to ALL.
            watch_state = str(data.get("state") or "").upper()
            if watch_state and watch_state not in VALID_STATES:
                watch_state = ""

            added_at = datetime.now().isoformat()
            try:
                con = sqlite3.connect(VARIETY_WATCHES_DB)
                if watch_state and watch_state != "ALL":
                    con.execute(
                        "INSERT INTO watcher_prefs (email, state, updated_at) VALUES (?, ?, ?) "
                        "ON CONFLICT(email) DO UPDATE SET state=excluded.state, "
                        "updated_at=excluded.updated_at",
                        (email, watch_state, added_at),
                    )
                cur = con.execute(
                    "INSERT OR IGNORE INTO watches (email, variety_slug, species_slug, variety_title, added_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (email, variety_slug, species_slug, variety_title, added_at),
                )
                inserted = cur.rowcount > 0
                if not inserted:
                    # INSERT OR IGNORE leaves the existing row alone, including
                    # a title stored back when the client supplied it. Refresh
                    # it so re-watching heals the row.
                    con.execute(
                        "UPDATE watches SET variety_title = ? "
                        "WHERE email = ? AND variety_slug = ? AND variety_title != ?",
                        (variety_title, email, variety_slug, variety_title),
                    )
                con.commit()
                con.close()
            except sqlite3.Error as e:
                self.send_json(500, {"error": f"DB error: {e}"})
                return
            if inserted:
                print(f"Variety watch added: {email} -> {variety_slug}")
                # Only on a real insert. Re-watching something you already
                # watch is not news and must not cost an email.
                self._maybe_send_watch_notice(email, variety_slug)
                self.send_json(201, {"message": "Alert set!", "variety_slug": variety_slug})
            else:
                self.send_json(200, {"message": "Already watching", "variety_slug": variety_slug})
            return

        # Handle wishlist vote
        if path in ("/wishlist", "/api/wishlist"):
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_json(400, {"error": "Invalid JSON"})
                return
            email = data.get("email", "").strip().lower()
            species_slug = data.get("species_slug", "").strip().lower()
            if not email or not is_valid_email(email):
                self.send_json(400, {"error": "Valid email required"})
                return
            if not species_slug:
                self.send_json(400, {"error": "species_slug required"})
                return
            added_at = datetime.now().isoformat()
            try:
                con = sqlite3.connect(VARIETY_WATCHES_DB)
                cur = con.execute(
                    "INSERT OR IGNORE INTO wishlist (email, species_slug, added_at) VALUES (?, ?, ?)",
                    (email, species_slug, added_at),
                )
                con.commit()
                inserted = cur.rowcount > 0
                count = con.execute(
                    "SELECT COUNT(*) FROM wishlist WHERE species_slug = ?", (species_slug,)
                ).fetchone()[0]
                con.close()
            except sqlite3.Error as e:
                self.send_json(500, {"error": f"DB error: {e}"})
                return
            # A wishlist vote used to silently add the voter to
            # subscribers.json and fire a welcome email: no double opt-in, no
            # statement that voting subscribed you, and a second consent path
            # that contradicted the one DEC-294 settled on. Removed. Voting is
            # a vote. The table had 0 rows, so nobody was affected.
            if inserted:
                print(f"Wishlist vote: {email} -> {species_slug} (total: {count})")
                self.send_json(201, {"message": "Added to wishlist!", "species_slug": species_slug, "total": count})
            else:
                self.send_json(200, {"message": "Already on your wishlist", "species_slug": species_slug, "total": count})
            return

        # Handle per-variety unwatch
        if path in ("/unwatch-variety", "/api/unwatch-variety"):
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_json(400, {"error": "Invalid JSON"})
                return
            email = data.get("email", "").strip().lower()
            token = data.get("token", "").strip()
            variety_slug = data.get("variety_slug", "").strip()
            # `all: true` drops every watch this address holds. The alert email
            # offers it as "stop all my treestock alerts", so a recipient can
            # always get out in one step without knowing which watch is which.
            drop_all = bool(data.get("all"))
            if not email or not token or not verify_unsubscribe_token(email, token):
                self.send_json(403, {"error": "Invalid token"})
                return
            if not variety_slug and not drop_all:
                self.send_json(400, {"error": "variety_slug required"})
                return
            try:
                con = sqlite3.connect(VARIETY_WATCHES_DB)
                if drop_all:
                    cur = con.execute("DELETE FROM watches WHERE email = ?", (email,))
                else:
                    cur = con.execute(
                        "DELETE FROM watches WHERE email = ? AND variety_slug = ?",
                        (email, variety_slug),
                    )
                removed = cur.rowcount
                con.commit()
                con.close()
            except sqlite3.Error as e:
                self.send_json(500, {"error": f"DB error: {e}"})
                return
            if drop_all:
                print(f"All variety watches removed: {email} ({removed})")
                self.send_json(200, {"message": "All alerts removed", "removed": removed})
            else:
                print(f"Variety watch removed: {email} -> {variety_slug}")
                self.send_json(200, {"message": "Alert removed", "removed": removed})
            return

        # Support both form-encoded and JSON
        if self.headers.get("Content-Type", "").startswith("application/json"):
            try:
                data = json.loads(body)
                email = data.get("email", "").strip().lower()
                action = data.get("action", "subscribe").strip()
                token = data.get("token", "").strip()
            except json.JSONDecodeError:
                self.send_json(400, {"error": "Invalid JSON"})
                return
        else:
            params = parse_qs(body)
            email = params.get("email", [""])[0].strip().lower()
            action = params.get("action", ["subscribe"])[0].strip()
            token = params.get("token", [""])[0].strip()

        if not email or not is_valid_email(email):
            self.send_json(400, {"error": "Valid email required"})
            return

        # Handle unsubscribe (via form POST from unsubscribe.html)
        if action == "unsubscribe":
            if not verify_unsubscribe_token(email, token):
                self.send_html(400, "<h2>Invalid unsubscribe link.</h2><p>The link may have expired. Please contact us at <a href='https://treestock.com.au'>treestock.com.au</a></p>")
                return
            subscribers = load_subscribers()
            updated = [s for s in subscribers if s["email"] != email]
            if len(updated) < len(subscribers):
                save_subscribers(updated)
                print(f"Unsubscribed: {email}")
                self.send_html(200, f"<h2>Unsubscribed ✓</h2><p>{email} has been removed from treestock.com.au stock alerts.</p>")
            else:
                self.send_html(200, "<h2>Not found</h2><p>That email wasn't in our subscriber list.</p>")
            return

        # Set the state used to filter variety alerts. Separate action from
        # update_preferences because that one edits subscribers.json and 404s
        # for an address that is not a digest subscriber -- which is 98 of the
        # 104 watchers. Same path and same token, so no new endpoint and no
        # Caddy allowlist entry.
        if action == "update_watch_state":
            if not verify_unsubscribe_token(email, token):
                self.send_json(403, {"error": "Invalid token"})
                return
            is_json = self.headers.get("Content-Type", "").startswith("application/json")
            new_state = (data.get("state", "") if is_json
                         else params.get("state", [""])[0]).upper().strip()
            if new_state not in VALID_STATES:
                self.send_json(400, {"error": f"Invalid state. Must be one of: {', '.join(sorted(VALID_STATES))}"})
                return
            self._set_watch_state(email, new_state)
            print(f"Watch state updated: {email} -> {new_state}")
            self.send_json(200, {"message": "Alert state updated", "state": new_state})
            return

        # Handle preferences update
        if action == "update_preferences":
            if not verify_unsubscribe_token(email, token):
                self.send_json(403, {"error": "Invalid token"})
                return
            is_json = self.headers.get("Content-Type", "").startswith("application/json")
            if is_json:
                new_state = data.get("state", "").upper().strip()
                raw_categories = data.get("categories")
                raw_plant_categories = data.get("plant_categories")
                raw_frequency = data.get("frequency")
            else:
                new_state = params.get("state", [""])[0].upper().strip()
                raw_categories = params.get("categories")
                raw_plant_categories = params.get("plant_categories")
                raw_frequency = params.get("frequency", [None])[0]

            if new_state not in VALID_STATES:
                self.send_json(400, {"error": f"Invalid state. Must be one of: {', '.join(sorted(VALID_STATES))}"})
                return

            # Normalise categories: must be a list when provided.
            new_categories = None
            if raw_categories is not None:
                if not isinstance(raw_categories, list):
                    self.send_json(400, {"error": "categories must be a list"})
                    return
                seen = set()
                new_categories = []
                for c in raw_categories:
                    if c in VALID_CATEGORIES and c not in seen:
                        new_categories.append(c)
                        seen.add(c)

            # Normalise plant categories (DAL-199): must be a list when provided.
            new_plant_categories = None
            if raw_plant_categories is not None:
                if not isinstance(raw_plant_categories, list):
                    self.send_json(400, {"error": "plant_categories must be a list"})
                    return
                seen = set()
                new_plant_categories = []
                for c in raw_plant_categories:
                    if c in VALID_PLANT_CATEGORIES and c not in seen:
                        new_plant_categories.append(c)
                        seen.add(c)

            # Normalise frequency.
            new_frequency = None
            if raw_frequency is not None:
                raw_frequency = (raw_frequency or "").strip().lower()
                if raw_frequency and raw_frequency not in VALID_FREQUENCIES:
                    self.send_json(400, {"error": f"Invalid frequency. Must be one of: {', '.join(VALID_FREQUENCIES)}"})
                    return
                new_frequency = raw_frequency or None

            # Ticking no plant type at all silences the digest permanently
            # (send_digest.py skips the bucket), but nothing in the UI said so:
            # two daily subscribers sat in that state for 10+ days. "Off" is the
            # supported way to stop digests, so reject the ambiguous state.
            if new_plant_categories is not None and not new_plant_categories and new_frequency != "off":
                self.send_json(400, {
                    "error": "Select at least one plant type, or set frequency to "
                             "'off' to stop digest emails.",
                })
                return

            subscribers = load_subscribers()
            found = False
            for s in subscribers:
                if s["email"] == email:
                    s["state"] = new_state
                    s.pop("wa_only", None)
                    if new_categories is not None:
                        s["categories"] = new_categories
                    if new_plant_categories is not None:
                        s["plant_categories"] = new_plant_categories
                    if new_frequency is not None:
                        s["frequency"] = new_frequency
                    found = True
                    break
            if not found:
                self.send_json(404, {"error": "Subscriber not found"})
                return
            save_subscribers(subscribers)
            # 6 of the 104 watchers are also digest subscribers. If one of them
            # sets a state here, their variety alerts should honour it too
            # rather than quietly disagreeing with their digest.
            self._set_watch_state(email, new_state)
            log_extras = []
            if new_categories is not None:
                log_extras.append(f"categories={','.join(new_categories) or '(none)'}")
            if new_plant_categories is not None:
                log_extras.append(f"plant={','.join(new_plant_categories) or '(none)'}")
            if new_frequency is not None:
                log_extras.append(f"frequency={new_frequency}")
            extra = (" " + " ".join(log_extras)) if log_extras else ""
            print(f"Preferences updated: {email} → state={new_state}{extra}")
            self.send_json(200, {
                "message": "Preferences updated",
                "state": new_state,
                "categories": new_categories,
                "plant_categories": new_plant_categories,
                "frequency": new_frequency,
            })
            return

        # Handle subscribe (default) — double opt-in flow
        subscribers = load_subscribers()
        if any(s["email"] == email for s in subscribers):
            self.send_json(200, {"message": "Already subscribed", "email": email})
            return

        # Accept optional state from signup form
        if self.headers.get("Content-Type", "").startswith("application/json"):
            sub_state = data.get("state", "ALL").upper().strip()
        else:
            sub_state = params.get("state", ["ALL"])[0].upper().strip()
        if sub_state not in VALID_STATES:
            sub_state = "ALL"

        # Check for existing pending entry (don't spam confirmation emails)
        pending = purge_expired_pending(load_pending())
        if any(p["email"] == email and p.get("state", "ALL") == sub_state for p in pending):
            self.send_json(200, {"message": "Check your email, confirmation link already sent", "email": email})
            return

        # Add to pending and send confirmation email
        confirm_token = make_confirm_token(email, sub_state)
        pending.append({
            "email": email,
            "state": sub_state,
            "token": confirm_token,
            "requested_at": datetime.now().isoformat(),
        })
        save_pending(pending)

        print(f"Pending confirmation: {email} (state={sub_state})")

        # Send confirmation email (non-blocking)
        confirm_script = SCRIPT_DIR / "send_confirmation_email.py"
        if confirm_script.exists():
            try:
                subprocess.Popen(
                    [sys.executable, str(confirm_script), email, confirm_token, sub_state],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as ex:
                print(f"Warning: could not launch confirmation email: {ex}")

        self.send_json(202, {"message": "Check your email to confirm your subscription", "email": email})

    def do_OPTIONS(self):
        # The admin write answers no preflight at all. Today ALLOWED_ORIGIN is a
        # single host, so the generic answer below would already fail to match a
        # foreign origin and the browser would block the request. Saying no
        # explicitly means a later change that adds a second allowed origin for
        # the public widgets cannot quietly open the admin write with it.
        if self.path.split("?")[0] == admin_view.ADMIN_DECIDE_PATH:
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _client_ip(self) -> str:
        """Best guess at who is calling.

        BE HONEST ABOUT WHAT THIS IS WORTH. treestock.com.au is orange-clouded,
        so CF-Connecting-IP is present and correct for traffic that came
        through Cloudflare. The origin is also directly reachable, so anyone
        who finds its address can send whatever CF-Connecting-IP they like and
        the limit below evaporates.

        It raises the cost of casual abuse and nothing more. The controls that
        actually hold are MAX_WATCHES_PER_ADDRESS, which is not spoofable, and
        the notice-email throttle, which caps what a victim can be made to
        receive.
        """
        for header in ("CF-Connecting-IP", "X-Forwarded-For"):
            value = (self.headers.get(header) or "").strip()
            if value:
                # X-Forwarded-For is a chain; the first entry is the client.
                return value.split(",")[0].strip()[:64]
        try:
            return self.client_address[0]
        except (AttributeError, IndexError):
            return "unknown"

    def _watch_rate_limited(self, ip: str) -> bool:
        """True when `ip` has already had WATCH_IP_LIMIT attempts in the
        window. Records this attempt when it has not.

        Pruning happens on the same pass, so the table never accumulates: at
        most one window of addresses is retained, which is as long as the data
        is any use and no longer.
        """
        now = datetime.now()
        cutoff = (now - timedelta(seconds=WATCH_IP_WINDOW_SECONDS)).isoformat()
        try:
            con = sqlite3.connect(VARIETY_WATCHES_DB)
            con.execute("DELETE FROM watch_attempts WHERE ts < ?", (cutoff,))
            recent = con.execute(
                "SELECT COUNT(*) FROM watch_attempts WHERE ip = ? AND ts >= ?",
                (ip, cutoff),
            ).fetchone()[0]
            if recent >= WATCH_IP_LIMIT:
                con.commit()
                con.close()
                return True
            con.execute("INSERT INTO watch_attempts (ip, ts) VALUES (?, ?)",
                        (ip, now.isoformat()))
            con.commit()
            con.close()
            return False
        except sqlite3.Error as e:
            # Fail open: a limiter that 500s the endpoint when its own table
            # misbehaves is a worse outage than the abuse it prevents, and the
            # per-address cap is untouched by this.
            print(f"Warning: watch rate-limit check failed ({e}); allowing")
            return False

    def _set_watch_state(self, email: str, state: str) -> None:
        """Record the state used to filter this address's variety alerts.

        'ALL' is stored rather than deleted so the manage page can show that
        the choice was made deliberately, and so a later read cannot mistake
        "chose everywhere" for "never asked".
        """
        try:
            con = sqlite3.connect(VARIETY_WATCHES_DB)
            con.execute(
                "INSERT INTO watcher_prefs (email, state, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(email) DO UPDATE SET state=excluded.state, "
                "updated_at=excluded.updated_at",
                (email, state, datetime.now().isoformat()),
            )
            con.commit()
            con.close()
        except sqlite3.Error as e:
            print(f"WARNING: could not save watch state for {email}: {e}")

    def _get_watch_state(self, email: str) -> str:
        try:
            con = sqlite3.connect(VARIETY_WATCHES_DB)
            row = con.execute("SELECT state FROM watcher_prefs WHERE email = ?",
                              (email,)).fetchone()
            con.close()
            return row[0] if row else "ALL"
        except sqlite3.Error:
            return "ALL"

    def _watch_count(self, email: str) -> int:
        try:
            con = sqlite3.connect(VARIETY_WATCHES_DB)
            n = con.execute("SELECT COUNT(*) FROM watches WHERE email = ?",
                            (email,)).fetchone()[0]
            con.close()
            return n
        except sqlite3.Error:
            return 0

    def _maybe_send_watch_notice(self, email: str, variety_slug: str):
        """Acknowledge a new watch, at most once per address per hour.

        Nobody was told they had subscribed: first contact could be weeks
        later, when a restock finally fired, by which point the alert reads as
        unsolicited mail.

        Throttled because this is also the lever an attacker would pull. One
        forged address plus a loop was unbounded mail to a stranger; it is now
        24 a day worst case. The notice lists every variety the address
        watches, so a watch added inside a throttled window still gets
        acknowledged by the next one.
        """
        log = _load_json_log(WATCH_NOTICE_LOG)
        last = log.get(email)
        if last:
            try:
                elapsed = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
                if elapsed < WATCH_NOTICE_RATE_LIMIT_SECONDS:
                    print(f"Watch notice throttled for {email} "
                          f"({int(elapsed)}s since last)")
                    return
            except ValueError:
                pass    # unparseable stamp: treat as never sent

        token = make_unsubscribe_token(email)
        if not token:
            print("ERROR: UNSUBSCRIBE_SECRET missing; cannot send watch notice "
                  f"for {email}", file=sys.stderr)
            return

        script = SCRIPT_DIR / "send_watch_notice_email.py"
        if not script.exists():
            print(f"ERROR: {script} not found", file=sys.stderr)
            return

        # Stamp BEFORE launching, and treat a failure to stamp as a reason not
        # to send. This is a throttle protecting a third party's inbox, so it
        # has to fail closed: if the stamp cannot be persisted, an unwritable
        # log would otherwise mean every watch re-sends, which is the unbounded
        # mail this exists to prevent.
        previous = log.get(email)
        log[email] = datetime.now().isoformat()
        try:
            _save_json_log(WATCH_NOTICE_LOG, log)
        except OSError as ex:
            print(f"ERROR: could not record watch-notice send ({ex}); "
                  f"not sending, because an unrecorded send has no throttle",
                  file=sys.stderr)
            return

        try:
            subprocess.Popen(
                [sys.executable, str(script), email, token, variety_slug],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as ex:
            # Roll the stamp back so a transient spawn failure does not cost
            # this person their only acknowledgement for the next hour. Best
            # effort: if the rollback fails too, we stay on the safe side.
            print(f"Warning: could not launch watch notice: {ex}", file=sys.stderr)
            try:
                if previous is None:
                    log.pop(email, None)
                else:
                    log[email] = previous
                _save_json_log(WATCH_NOTICE_LOG, log)
            except OSError:
                pass
            return

        print(f"Watch notice queued: {email} -> {variety_slug}")

    def _get_variety_watches(self, email: str):
        """Get variety watches for an email from SQLite."""
        try:
            con = sqlite3.connect(VARIETY_WATCHES_DB)
            rows = con.execute(
                "SELECT variety_slug, variety_title, species_slug FROM watches WHERE email = ? ORDER BY added_at",
                (email.lower(),)
            ).fetchall()
            con.close()
            return [{"slug": r[0], "title": r[1], "species": r[2]} for r in rows]
        except sqlite3.Error:
            return []

    def send_confirm_success_page(self, email: str):
        """Confirmation success page with an embedded one-step preferences picker.

        Token is generated server-side from the just-confirmed email, so the
        picker submission is authenticated without anything sensitive in
        client-rendered HTML.
        """
        token = make_unsubscribe_token(email)

        body = f"""
<h2 style="color:#065f46;margin:0 0 8px">You're subscribed!</h2>
<p style="color:#374151;margin:0 0 20px">
  Your first digest will arrive tomorrow morning. You can fine-tune things below, or close this tab and the defaults (daily, fruit trees) will be used.
</p>

<form id="prefsForm" style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin:0 0 24px">

  <h3 style="color:#065f46;font-size:0.95rem;margin:0 0 8px">What plants?</h3>
  <div style="margin:0 0 16px">
    <label style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;cursor:pointer">
      <input type="checkbox" name="plant_categories" value="fruit" checked style="margin-top:4px">
      <span><strong>🍑 Fruit trees</strong>
        <br><span style="font-size:0.8rem;color:#6b7280">Rare and edible fruit, nut and berry stock</span></span>
    </label>
    <label style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;cursor:pointer">
      <input type="checkbox" name="plant_categories" value="bush_tucker" style="margin-top:4px">
      <span><strong>🌿 Bush tucker</strong>
        <br><span style="font-size:0.8rem;color:#6b7280">Australian native food plants: lemon myrtle, finger lime, warrigal greens and more</span></span>
    </label>
  </div>

  <h3 style="color:#065f46;font-size:0.95rem;margin:0 0 8px">How often?</h3>
  <div style="margin:0 0 16px">
    <label style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;cursor:pointer">
      <input type="radio" name="frequency" value="daily" checked style="margin-top:4px">
      <span><strong>Daily</strong>
        <br><span style="font-size:0.8rem;color:#6b7280">One email per day when any tracked change happens</span></span>
    </label>
    <label style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;cursor:pointer">
      <input type="radio" name="frequency" value="weekly" style="margin-top:4px">
      <span><strong>Weekly summary</strong>
        <br><span style="font-size:0.8rem;color:#6b7280">A single curated email on Sunday mornings</span></span>
    </label>
    <label style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;cursor:pointer">
      <input type="radio" name="frequency" value="off" style="margin-top:4px">
      <span><strong>Off</strong>
        <br><span style="font-size:0.8rem;color:#6b7280">No digest emails, but variety alerts still work</span></span>
    </label>
  </div>

  <h3 style="color:#065f46;font-size:0.95rem;margin:0 0 8px">What to include?</h3>
  <div style="margin:0 0 16px">
    <label style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;cursor:pointer">
      <input type="checkbox" name="categories" value="new_products" checked style="margin-top:4px">
      <span><strong>🆕 New listings</strong>
        <br><span style="font-size:0.8rem;color:#6b7280">First time a product appears on a nursery website</span></span>
    </label>
    <label style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;cursor:pointer">
      <input type="checkbox" name="categories" value="price_drops" checked style="margin-top:4px">
      <span><strong>📉 Price drops</strong>
        <br><span style="font-size:0.8rem;color:#6b7280">Existing items that became cheaper</span></span>
    </label>
    <label style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;cursor:pointer">
      <input type="checkbox" name="categories" value="back_in_stock" checked style="margin-top:4px">
      <span><strong>✅ Back in stock</strong>
        <br><span style="font-size:0.8rem;color:#6b7280">Items that were sold out and have returned</span></span>
    </label>
  </div>

  <button type="submit" style="background:#16a34a;color:white;border:none;padding:10px 24px;border-radius:8px;font-size:0.9rem;font-weight:600;cursor:pointer">
    Save preferences
  </button>
  <p id="prefsMsg" style="font-size:0.85rem;min-height:1.2em;margin:8px 0 0"></p>
</form>

<p style="color:#374151;margin:0 0 20px;font-size:0.95rem">
  Want alerts for a specific variety? <a href="https://treestock.com.au/species/" style="color:#065f46">Browse species pages</a>
  and click the bell on any cultivar.
</p>

<div style="margin-top:24px;padding:16px;border:1px solid #bbf7d0;background:#f0fdf4;border-radius:8px">
  <p style="margin:0 0 6px 0;font-weight:600;color:#065f46">Track the trees you buy</p>
  <p style="margin:0 0 10px 0;font-size:14px;color:#374151">
    treestock tells you where to buy a rare variety. <strong>Treesmith</strong>, our mobile app, helps you catalog every plant, log grafts and harvests, and capture growth photos over time.
  </p>
  <a href="https://treestock.com.au/treesmith.html?utm_source=treestock&amp;utm_medium=confirm_page&amp;utm_campaign=treesmith_launch"
     style="color:#065f46;font-weight:600">Learn more about Treesmith &rarr;</a>
</div>

<script>
document.getElementById('prefsForm').addEventListener('submit', async function(e) {{
  e.preventDefault();
  var freqEl = document.querySelector('#prefsForm input[name=frequency]:checked');
  var frequency = freqEl ? freqEl.value : 'daily';
  var categories = Array.from(document.querySelectorAll('#prefsForm input[name=categories]:checked')).map(function(el) {{ return el.value; }});
  var plant_categories = Array.from(document.querySelectorAll('#prefsForm input[name=plant_categories]:checked')).map(function(el) {{ return el.value; }});
  var msg = document.getElementById('prefsMsg');
  var btn = e.target.querySelector('button');
  btn.disabled = true;
  btn.textContent = 'Saving...';
  msg.style.color = '';
  msg.textContent = '';
  try {{
    var resp = await fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        email: {json.dumps(email)},
        token: {json.dumps(token)},
        action: 'update_preferences',
        state: {json.dumps(self._lookup_subscriber_state(email))},
        categories: categories,
        plant_categories: plant_categories,
        frequency: frequency
      }})
    }});
    var data = await resp.json();
    if (resp.ok) {{
      msg.style.color = '#065f46';
      msg.textContent = 'Saved. You can change these anytime via the link in any future email.';
      btn.textContent = 'Saved';
    }} else {{
      msg.style.color = '#dc2626';
      msg.textContent = data.error || 'Something went wrong.';
      btn.disabled = false;
      btn.textContent = 'Save preferences';
    }}
  }} catch (err) {{
    msg.style.color = '#dc2626';
    msg.textContent = 'Network error. Please try again.';
    btn.disabled = false;
    btn.textContent = 'Save preferences';
  }}
}});
</script>"""
        self.send_html(200, body)

    def _lookup_subscriber_state(self, email: str) -> str:
        """Read the current stored state for an email so we can echo it back in
        update_preferences (the endpoint requires a state value)."""
        subs = load_subscribers()
        for s in subs:
            if s["email"] == email:
                return s.get("state") or ("WA" if s.get("wa_only") else "ALL")
        return "ALL"

    def _variety_watch_rows(self, email: str) -> str:
        """Render the watch list as removable rows. Shared by the full
        preferences page and the watch-only page.

        Titles are shown from the canonical index where we have one, so a row
        for a watch created before the server owned titles reads the same as a
        row created today. A slug that has dropped out of the dataset keeps its
        stored title rather than vanishing, hence the escaping below: that
        stored value could still be whatever a caller once posted.

        The Remove button carries the slug in a data attribute and is wired up
        by a delegated listener on each page. It used to build an inline
        onclick out of the slug, which is a string-concatenated JS context and
        the wrong shape to defend even when the value is safe.
        """
        watches = self._get_variety_watches(email)
        if not watches:
            return '<p style="color:#9ca3af;font-size:0.85rem">None. Browse variety pages to add watches.</p>'
        index = get_variety_index(VARIETY_INDEX_FILE)
        rows = ""
        for vw in watches:
            safe_title = html.escape(index.display_title(vw["slug"], vw["title"]))
            rows += (
                f'<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;'
                f'border-bottom:1px solid #f3f4f6">'
                f'<span>{safe_title}</span>'
                f'<button type="button" class="remove-watch" data-slug="{html.escape(vw["slug"], quote=True)}" '
                f'style="background:none;border:1px solid #d1d5db;'
                f'color:#6b7280;padding:4px 12px;border-radius:6px;font-size:0.8rem;cursor:pointer">Remove</button>'
                f'</div>'
            )
        return rows

    def send_watch_only_page(self, email: str, token: str):
        """Manage page for an address that holds variety watches but is not a
        digest subscriber. No category or frequency controls, because neither
        applies: the only thing this person receives is variety alerts. State
        DOES apply, and this is where we ask for it -- not on the watch form,
        which stays one tap."""
        current_state = self._get_watch_state(email)
        options = "".join(
            f'<option value="{st}"{" selected" if st == current_state else ""}>'
            f'{"Anywhere in Australia" if st == "ALL" else st}</option>'
            for st in ["ALL"] + sorted(VALID_STATES - {"ALL"})
        )
        body = f"""
<h2 style="color:#065f46;margin:0 0 8px">Your variety alerts</h2>
<p style="color:#6b7280;font-size:0.9rem;margin:0 0 24px">{html.escape(email)}</p>

<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:14px 16px;margin:0 0 24px">
  <label for="watchState" style="display:block;font-weight:600;color:#065f46;margin:0 0 6px">
    Where do you want to buy?
  </label>
  <p style="color:#6b7280;font-size:0.85rem;margin:0 0 10px">
    Pick your state and we will only email you about stock you can actually
    get delivered there. Leave it on Anywhere to hear about every nursery.
  </p>
  <select id="watchState" style="padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;font-size:0.9rem">
    {options}
  </select>
  <button id="saveState" style="background:#15803d;border:none;color:white;padding:8px 16px;border-radius:8px;font-size:0.85rem;cursor:pointer;margin-left:8px">
    Save
  </button>
  <p id="stateMsg" style="font-size:0.85rem;min-height:1.2em;margin:8px 0 0"></p>
</div>

<p style="color:#6b7280;font-size:0.85rem;margin:0 0 8px">
  We email you when one of these comes back in stock, or drops in price, at any
  nursery we track that can reach you. Nothing else.
</p>
<div id="varietyWatches" style="margin:0 0 24px">
{self._variety_watch_rows(email)}
</div>

<button id="stopAll" style="background:none;border:1px solid #fca5a5;color:#dc2626;padding:8px 16px;border-radius:8px;font-size:0.85rem;cursor:pointer">
  Stop all my treestock alerts
</button>
<p id="stopMsg" style="font-size:0.85rem;min-height:1.2em;margin:8px 0 0"></p>

<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.8rem;color:#9ca3af">
  <a href="https://treestock.com.au" style="color:#6b7280">treestock.com.au</a>
</p>
<script>
document.getElementById('saveState').addEventListener('click', async function() {{
  const msg = document.getElementById('stateMsg');
  const btn = this;
  btn.disabled = true;
  try {{
    const resp = await fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        email: {json.dumps(email)}, token: {json.dumps(token)},
        action: 'update_watch_state',
        state: document.getElementById('watchState').value
      }})
    }});
    const data = await resp.json().catch(function() {{ return {{}}; }});
    if (resp.ok) {{
      msg.style.color = '#065f46';
      msg.textContent = data.state === 'ALL'
        ? 'Saved. You will hear about every nursery we track.'
        : 'Saved. We will only email you about stock you can get in ' + data.state + '.';
    }} else {{
      msg.style.color = '#dc2626';
      msg.textContent = data.error || 'Could not save that.';
    }}
  }} catch (err) {{
    msg.style.color = '#dc2626';
    msg.textContent = 'Network error.';
  }}
  btn.disabled = false;
}});
async function removeVariety(slug) {{
  try {{
    const resp = await fetch('/api/unwatch-variety', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email: {json.dumps(email)}, token: {json.dumps(token)}, variety_slug: slug}})
    }});
    if (resp.ok) location.reload();
    else document.getElementById('stopMsg').textContent = 'Could not remove that alert.';
  }} catch (err) {{ document.getElementById('stopMsg').textContent = 'Network error.'; }}
}}
document.getElementById('varietyWatches').addEventListener('click', function(e) {{
  const btn = e.target.closest('.remove-watch');
  if (btn) removeVariety(btn.dataset.slug);
}});
document.getElementById('stopAll').addEventListener('click', async function() {{
  const msg = document.getElementById('stopMsg');
  const btn = this;
  btn.disabled = true;
  try {{
    const resp = await fetch('/api/unwatch-variety', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{email: '{email}', token: '{token}', all: true}})
    }});
    if (resp.ok) {{
      msg.style.color = '#065f46';
      msg.textContent = 'Done. You will not get any more treestock alerts.';
      document.getElementById('varietyWatches').innerHTML = '';
      btn.style.display = 'none';
    }} else {{
      msg.style.color = '#dc2626';
      msg.textContent = 'Something went wrong.';
      btn.disabled = false;
    }}
  }} catch (err) {{
    msg.style.color = '#dc2626';
    msg.textContent = 'Network error.';
    btn.disabled = false;
  }}
}});
</script>"""
        self.send_html(200, body)

    def send_preferences_page(
        self,
        email: str,
        token: str,
        current_state: str,
        current_categories,
        current_plant_categories,
        current_frequency: str,
    ):
        states = ["ALL", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT"]
        state_labels = {
            "ALL": "All states (no filter)",
            "NSW": "New South Wales", "VIC": "Victoria", "QLD": "Queensland",
            "WA": "Western Australia", "SA": "South Australia",
            "TAS": "Tasmania", "NT": "Northern Territory", "ACT": "ACT",
        }
        options = "\n".join(
            f'<option value="{s}"{" selected" if s == current_state else ""}>{state_labels[s]}</option>'
            for s in states
        )

        # Category checkboxes
        current_cat_set = set(current_categories or [])
        category_labels = [
            ("new_products", "🆕 New listings", "First time a product appears on a nursery website"),
            ("price_drops", "📉 Price drops", "Existing items that became cheaper"),
            ("back_in_stock", "✅ Back in stock", "Items that were sold out and have returned"),
        ]
        category_rows = []
        for key, label, hint in category_labels:
            checked = " checked" if key in current_cat_set else ""
            category_rows.append(
                f'<label style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;cursor:pointer">'
                f'<input type="checkbox" name="categories" value="{key}"{checked} style="margin-top:4px">'
                f'<span><strong>{label}</strong>'
                f'<br><span style="font-size:0.8rem;color:#6b7280">{hint}</span></span>'
                f'</label>'
            )
        categories_html = "\n".join(category_rows)

        # Plant category checkboxes (DAL-199): which kinds of plant to follow.
        current_plant_set = set(current_plant_categories or [])
        plant_labels = [
            ("fruit", "🍑 Fruit trees", "Rare and edible fruit, nut and berry stock (the default)"),
            ("bush_tucker", "🌿 Bush tucker", "Australian native food plants: lemon myrtle, finger lime, warrigal greens and more"),
        ]
        plant_rows = []
        for key, label, hint in plant_labels:
            checked = " checked" if key in current_plant_set else ""
            plant_rows.append(
                f'<label style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;cursor:pointer">'
                f'<input type="checkbox" name="plant_categories" value="{key}"{checked} style="margin-top:4px">'
                f'<span><strong>{label}</strong>'
                f'<br><span style="font-size:0.8rem;color:#6b7280">{hint}</span></span>'
                f'</label>'
            )
        plant_categories_html = "\n".join(plant_rows)

        # Frequency radio buttons
        freq_options = [
            ("daily", "Daily", "One email per day when any tracked change happens"),
            ("weekly", "Weekly summary", "A single curated email on Sunday mornings"),
            ("off", "Off", "No digest emails, but variety alerts still work"),
        ]
        freq_rows = []
        for key, label, hint in freq_options:
            checked = " checked" if key == current_frequency else ""
            freq_rows.append(
                f'<label style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;cursor:pointer">'
                f'<input type="radio" name="frequency" value="{key}"{checked} style="margin-top:4px">'
                f'<span><strong>{label}</strong>'
                f'<br><span style="font-size:0.8rem;color:#6b7280">{hint}</span></span>'
                f'</label>'
            )
        frequency_html = "\n".join(freq_rows)

        # Get variety watches from SQLite
        variety_items = self._variety_watch_rows(email)

        # Variety alerts lead, digest settings follow. This page is reached
        # from the alert email, which is now the product: the person arriving
        # here came from a variety alert and wants the variety list, not a
        # state filter. It used to render digest settings first and put
        # "Variety alerts" last, below the save button.
        #
        # The digest block collapses when its frequency is "off", because that
        # is a subscriber who has already said they do not want it. Collapsed
        # rather than removed: the 12 real digest subscribers must still be
        # able to reach their settings, and so must anyone turning it back on.
        digest_off = current_frequency == "off"
        digest_open = "" if digest_off else " open"
        digest_summary = ("Digest emails (currently off)" if digest_off
                          else f"Digest emails ({html.escape(current_frequency)})")

        body = f"""
<h2 style="color:#065f46;margin:0 0 8px">Manage your alerts</h2>
<p style="color:#6b7280;font-size:0.9rem;margin:0 0 24px">{html.escape(email)}</p>

<h3 style="color:#374151;font-size:1rem;margin:0 0 8px">Variety alerts</h3>
<p style="color:#6b7280;font-size:0.85rem;margin:0 0 8px">
  We email you when one of these comes back in stock, or drops in price, at any
  nursery we track. One alert covers both.
</p>
<div id="varietyWatches" style="margin:0 0 24px">
{variety_items}
</div>

<details{digest_open} style="margin:0 0 8px;border-top:1px solid #e5e7eb;padding-top:16px">
<summary style="cursor:pointer;color:#374151;font-size:1rem;font-weight:600;margin:0 0 16px">{digest_summary}</summary>

<form id="prefsForm" style="margin:0">

  <h3 style="color:#374151;font-size:1rem;margin:0 0 8px">State filter</h3>
  <p style="color:#6b7280;font-size:0.85rem;margin:0 0 8px">
    Only show updates from nurseries that ship to your state.
  </p>
  <select id="stateSelect" style="padding:8px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:0.9rem;width:100%;max-width:320px;margin-bottom:24px">
    {options}
  </select>

  <h3 style="color:#374151;font-size:1rem;margin:0 0 8px">Plant categories</h3>
  <p style="color:#6b7280;font-size:0.85rem;margin:0 0 8px">
    Which kinds of plant to follow. Fruit trees is the default; bush tucker (native food plants) is opt-in.
  </p>
  <div id="plantCategoryGroup" style="margin:0 0 24px">
    {plant_categories_html}
  </div>

  <h3 style="color:#374151;font-size:1rem;margin:0 0 8px">What to include</h3>
  <p style="color:#6b7280;font-size:0.85rem;margin:0 0 8px">
    Uncheck anything that's not useful to you. If you uncheck everything, you'll skip the digest entirely (variety alerts still work).
  </p>
  <div id="categoryGroup" style="margin:0 0 24px">
    {categories_html}
  </div>

  <h3 style="color:#374151;font-size:1rem;margin:0 0 8px">How often</h3>
  <div id="frequencyGroup" style="margin:0 0 24px">
    {frequency_html}
  </div>

  <button type="submit" style="background:#16a34a;color:white;border:none;padding:10px 24px;border-radius:8px;font-size:0.9rem;font-weight:600;cursor:pointer">
    Save preferences
  </button>
</form>
<p id="prefsMsg" style="font-size:0.85rem;min-height:1.2em;margin:8px 0 24px"></p>
</details>

<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.8rem;color:#9ca3af">
  <a href="https://treestock.com.au/unsubscribe.html?email={quote(email)}&token={token}" style="color:#dc2626">Unsubscribe from all</a>
  &middot; <a href="https://treestock.com.au" style="color:#6b7280">treestock.com.au</a>
</p>
<script>
document.getElementById('prefsForm').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const state = document.getElementById('stateSelect').value;
  const categories = Array.from(document.querySelectorAll('#categoryGroup input[type=checkbox]:checked')).map(function(el) {{ return el.value; }});
  const plant_categories = Array.from(document.querySelectorAll('#plantCategoryGroup input[type=checkbox]:checked')).map(function(el) {{ return el.value; }});
  const freqEl = document.querySelector('#frequencyGroup input[type=radio]:checked');
  const frequency = freqEl ? freqEl.value : 'daily';
  const msg = document.getElementById('prefsMsg');
  const btn = e.target.querySelector('button');
  btn.disabled = true;
  btn.textContent = 'Saving...';
  try {{
    const resp = await fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        email: '{email}',
        token: '{token}',
        action: 'update_preferences',
        state: state,
        categories: categories,
        plant_categories: plant_categories,
        frequency: frequency
      }})
    }});
    const data = await resp.json();
    if (resp.ok) {{
      msg.style.color = '#065f46';
      let parts = [];
      parts.push(state === 'ALL' ? 'all states' : state);
      if (plant_categories.length === 0) {{
        parts.push('no plant types');
      }} else if (plant_categories.indexOf('bush_tucker') >= 0) {{
        parts.push(plant_categories.indexOf('fruit') >= 0 ? 'fruit + bush tucker' : 'bush tucker only');
      }} else {{
        parts.push('fruit only');
      }}
      if (frequency === 'off') {{
        parts.push('no digest emails');
      }} else {{
        parts.push(frequency + ' digest');
      }}
      if (categories.length === 0) {{
        parts.push('all categories muted');
      }} else if (categories.length < 3) {{
        parts.push(categories.length + ' categor' + (categories.length === 1 ? 'y' : 'ies'));
      }}
      msg.textContent = 'Saved: ' + parts.join(', ') + '.';
    }} else {{
      msg.style.color = '#dc2626';
      msg.textContent = data.error || 'Something went wrong.';
    }}
  }} catch (err) {{
    msg.style.color = '#dc2626';
    msg.textContent = 'Network error. Please try again.';
  }}
  btn.disabled = false;
  btn.textContent = 'Save preferences';
}});

async function removeVariety(slug) {{
  if (!confirm('Stop watching this variety?')) return;
  try {{
    const resp = await fetch('/api/unwatch-variety', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        email: {json.dumps(email)},
        token: {json.dumps(token)},
        variety_slug: slug
      }})
    }});
    if (resp.ok) location.reload();
    else alert('Failed to remove watch.');
  }} catch (err) {{ alert('Network error.'); }}
}}
document.getElementById('varietyWatches').addEventListener('click', function(e) {{
  const btn = e.target.closest('.remove-watch');
  if (btn) removeVariety(btn.dataset.slug);
}});
</script>"""
        self.send_html(200, body)

    def send_html(self, status: int, body: str):
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>treestock.com.au</title>
<style>body{{font-family:-apple-system,sans-serif;max-width:500px;margin:80px auto;padding:16px}}</style>
</head><body>{body}<p><a href="https://treestock.com.au">← Back to treestock.com.au</a></p></body></html>"""
        encoded = html.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def send_admin_html(self, html_doc: str, status: int = 200):
        """Send a full pre-rendered HTML page (no site chrome); noindex + no-store."""
        encoded = html_doc.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _handle_admin_decide(self):
        """POST /admin/varieties/decide. The only write in the admin surface.

        Gate order is deliberate, cheapest and most-conclusive first, and every
        rejection is silent about why beyond a status code. See the CSRF block
        at the top of this module for what each layer is worth and, more to the
        point, for what was actually measured about SameSite rather than assumed.

        This writes an intent file. Nothing here touches the ledger, the pages,
        or the override file, so the worst outcome of a bug reaching this
        handler is a queued decision that tonight's build refuses.
        """
        # 1. Origin, and no CORS answer for anyone else.
        if not admin_post_origin_ok(self.headers):
            self.send_admin_json({"error": "bad origin"}, status=403)
            return
        # 2. JSON only, so a cross-origin attempt is preflighted rather than
        #    "simple", and we answer no preflight for a foreign origin.
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self.send_admin_json({"error": "expected application/json"}, status=415)
            return
        # 3. The Access JWT itself, fail-closed as everywhere else.
        claims = cf_access_claims(self.headers)
        if claims is None:
            self.send_admin_json({"error": "forbidden"}, status=403)
            return
        subject = str(claims.get("email") or claims.get("sub") or "")

        try:
            content_length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            self.send_admin_json({"error": "invalid Content-Length"}, status=400)
            return
        if content_length > MAX_BODY_BYTES:
            self.send_admin_json({"error": "payload too large"}, status=413)
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode())
            if not isinstance(payload, dict):
                raise ValueError("not an object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self.send_admin_json({"error": "invalid body"}, status=400)
            return

        # 4. The token, bound to this subject.
        if not verify_admin_csrf(str(payload.get("csrf") or ""), subject):
            self.send_admin_json({"error": "stale or missing token, reload"},
                                 status=403)
            return

        try:
            result = admin_view.apply_decisions(payload, by=subject)
        except admin_view.DecisionRefused as e:
            # A refusal is the system working: a stale stamp means the row moved
            # under the reviewer, and merging blind is how you retarget a
            # redirect that stopped being one.
            self.send_admin_json({"error": str(e)}, status=409)
            return
        except Exception as e:
            print(f"Admin decide error: {e}", file=sys.stderr)
            self.send_admin_json({"error": "could not record the decision"},
                                 status=500)
            return
        self.send_admin_json(result)

    def send_admin_json(self, data: dict, status: int = 200):
        """Admin data payload: compact, never cached, never cross-origin.

        Not send_json: that one sets Access-Control-Allow-Origin for the public
        widgets, and an Access-gated payload has no business advertising itself
        to another origin. Compact separators because the reason this is a
        separate request at all is its size.
        """
        body = json.dumps(data, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Quieter logging
        pass


def main():
    port = PORT
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        port = int(sys.argv[idx + 1])

    init_variety_watches_db()
    print(f"Variety watches DB initialised at {VARIETY_WATCHES_DB}")

    server = HTTPServer(("127.0.0.1", port), SubscribeHandler)
    print(f"Subscribe server listening on 127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")


if __name__ == "__main__":
    main()
