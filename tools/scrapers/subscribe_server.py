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
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlparse

SCRIPT_DIR = Path(__file__).parent

SUBSCRIBERS_FILE = Path("/opt/dale/data/subscribers.json")
PENDING_FILE = Path("/opt/dale/data/pending_subscribers.json")
APP_ENV = Path("/opt/dale/secrets/app.env")
VARIETY_WATCHES_DB = Path("/opt/dale/data/variety_watches.db")
MANAGE_LINK_LOG = Path("/opt/dale/data/manage_link_sends.json")
PORT = 8099
CONFIRM_EXPIRY_HOURS = 48
MANAGE_LINK_RATE_LIMIT_SECONDS = 3600  # one manage-link email per address per hour

VALID_CATEGORIES = ("new_products", "price_drops", "back_in_stock")
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
    """)
    con.commit()
    con.close()


def get_unsubscribe_secret() -> str:
    if APP_ENV.exists():
        with open(APP_ENV) as f:
            for line in f:
                line = line.strip()
                if line.startswith("UNSUBSCRIBE_SECRET="):
                    return line.split("=", 1)[1].strip()
    return ""


def verify_unsubscribe_token(email: str, token: str) -> bool:
    secret = get_unsubscribe_secret()
    if not secret:
        return False
    expected = hmac.new(
        secret.encode(), email.lower().encode(), hashlib.sha256
    ).hexdigest()[:32]
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


def load_subscribers() -> list:
    if SUBSCRIBERS_FILE.exists():
        with open(SUBSCRIBERS_FILE) as f:
            return json.load(f)
    return []


def save_subscribers(subscribers: list):
    SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(subscribers, f, indent=2)


def is_valid_email(email: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email))


def _load_manage_link_log() -> dict:
    if MANAGE_LINK_LOG.exists():
        try:
            with open(MANAGE_LINK_LOG) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_manage_link_log(log: dict):
    MANAGE_LINK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(MANAGE_LINK_LOG, "w") as f:
        json.dump(log, f, indent=2)


class SubscribeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = dict(parse_qsl(parsed.query))
        email = params.get("email", "").strip().lower()
        token = params.get("token", "").strip()

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
            valid_states = {"ALL", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT"}
            if state not in valid_states:
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

            self.send_html(200, """
<h2 style="color:#065f46">You're subscribed!</h2>
<p>You'll receive your first stock digest next Monday morning.</p>
<p>You can <a href="https://treestock.com.au/species/" style="color:#065f46">browse species pages</a>
to set alerts for specific varieties.</p>
<div style="margin-top:24px;padding:16px;border:1px solid #bbf7d0;background:#f0fdf4;border-radius:8px">
  <p style="margin:0 0 6px 0;font-weight:600;color:#065f46">Track the trees you buy</p>
  <p style="margin:0 0 10px 0;font-size:14px;color:#374151">
    treestock tells you where to buy a rare variety. <strong>Treesmith</strong>, our mobile app, helps you catalog every plant, log grafts and harvests, and capture growth photos over time.
  </p>
  <a href="https://treestock.com.au/treesmith.html?utm_source=treestock&amp;utm_medium=confirm_page&amp;utm_campaign=treesmith_launch"
     style="color:#065f46;font-weight:600">Learn more about Treesmith &rarr;</a>
</div>
""")
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
                self.send_html(404, "<h2>Not found</h2><p>That email isn't in our subscriber list.</p>")
                return

            current_state = subscriber.get("state", "WA" if subscriber.get("wa_only") else "ALL")
            current_categories = subscriber.get("categories")
            if current_categories is None:
                current_categories = list(VALID_CATEGORIES)
            current_frequency = subscriber.get("frequency", "daily")
            if current_frequency not in VALID_FREQUENCIES:
                current_frequency = "daily"
            self.send_preferences_page(email, token, current_state, current_categories, current_frequency)
            return

        self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in (
            "/subscribe", "/api/subscribe",
            "/watch-variety", "/api/watch-variety",
            "/unwatch-variety", "/api/unwatch-variety",
            "/wishlist", "/api/wishlist",
            "/request-manage-link", "/api/request-manage-link",
        ):
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()

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
            if subscriber is None:
                print(f"Manage-link request for non-subscriber (silent): {requested_email}")
                self.send_json(200, generic_ok)
                return

            secret = get_unsubscribe_secret()
            if not secret:
                # Misconfigured server — surface the error but still return generic OK to caller.
                print(f"ERROR: UNSUBSCRIBE_SECRET missing; cannot send manage-link for {requested_email}", file=sys.stderr)
                self.send_json(200, generic_ok)
                return
            token = hmac.new(
                secret.encode(), requested_email.encode(), hashlib.sha256
            ).hexdigest()[:32]

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
            variety_title = data.get("variety_title", "").strip()
            if not email or not is_valid_email(email):
                self.send_json(400, {"error": "Valid email required"})
                return
            if not variety_slug:
                self.send_json(400, {"error": "variety_slug required"})
                return
            added_at = datetime.now().isoformat()
            try:
                con = sqlite3.connect(VARIETY_WATCHES_DB)
                cur = con.execute(
                    "INSERT OR IGNORE INTO watches (email, variety_slug, species_slug, variety_title, added_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (email, variety_slug, species_slug, variety_title, added_at),
                )
                con.commit()
                inserted = cur.rowcount > 0
                con.close()
            except sqlite3.Error as e:
                self.send_json(500, {"error": f"DB error: {e}"})
                return
            if inserted:
                print(f"Variety watch added: {email} -> {variety_slug}")
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
            # Also subscribe this person if not already subscribed
            subscribers = load_subscribers()
            existing = next((s for s in subscribers if s["email"] == email), None)
            if not existing:
                subscribers.append({
                    "email": email,
                    "subscribed_at": datetime.now().isoformat(),
                    "state": "ALL",
                })
                save_subscribers(subscribers)
                print(f"New subscriber via wishlist: {email}")
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
            if not email or not token or not verify_unsubscribe_token(email, token):
                self.send_json(403, {"error": "Invalid token"})
                return
            if not variety_slug:
                self.send_json(400, {"error": "variety_slug required"})
                return
            try:
                con = sqlite3.connect(VARIETY_WATCHES_DB)
                con.execute(
                    "DELETE FROM watches WHERE email = ? AND variety_slug = ?",
                    (email, variety_slug),
                )
                con.commit()
                con.close()
            except sqlite3.Error as e:
                self.send_json(500, {"error": f"DB error: {e}"})
                return
            print(f"Variety watch removed: {email} -> {variety_slug}")
            self.send_json(200, {"message": "Alert removed"})
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

        # Handle preferences update
        if action == "update_preferences":
            if not verify_unsubscribe_token(email, token):
                self.send_json(403, {"error": "Invalid token"})
                return
            is_json = self.headers.get("Content-Type", "").startswith("application/json")
            if is_json:
                new_state = data.get("state", "").upper().strip()
                raw_categories = data.get("categories")
                raw_frequency = data.get("frequency")
            else:
                new_state = params.get("state", [""])[0].upper().strip()
                raw_categories = params.get("categories")
                raw_frequency = params.get("frequency", [None])[0]

            valid_states = {"ALL", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT"}
            if new_state not in valid_states:
                self.send_json(400, {"error": f"Invalid state. Must be one of: {', '.join(sorted(valid_states))}"})
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

            # Normalise frequency.
            new_frequency = None
            if raw_frequency is not None:
                raw_frequency = (raw_frequency or "").strip().lower()
                if raw_frequency and raw_frequency not in VALID_FREQUENCIES:
                    self.send_json(400, {"error": f"Invalid frequency. Must be one of: {', '.join(VALID_FREQUENCIES)}"})
                    return
                new_frequency = raw_frequency or None

            subscribers = load_subscribers()
            found = False
            for s in subscribers:
                if s["email"] == email:
                    s["state"] = new_state
                    s.pop("wa_only", None)
                    if new_categories is not None:
                        s["categories"] = new_categories
                    if new_frequency is not None:
                        s["frequency"] = new_frequency
                    found = True
                    break
            if not found:
                self.send_json(404, {"error": "Subscriber not found"})
                return
            save_subscribers(subscribers)
            log_extras = []
            if new_categories is not None:
                log_extras.append(f"categories={','.join(new_categories) or '(none)'}")
            if new_frequency is not None:
                log_extras.append(f"frequency={new_frequency}")
            extra = (" " + " ".join(log_extras)) if log_extras else ""
            print(f"Preferences updated: {email} → state={new_state}{extra}")
            self.send_json(200, {
                "message": "Preferences updated",
                "state": new_state,
                "categories": new_categories,
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
        valid_states = {"ALL", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT"}
        if sub_state not in valid_states:
            sub_state = "ALL"

        # Check for existing pending entry (don't spam confirmation emails)
        pending = purge_expired_pending(load_pending())
        if any(p["email"] == email and p.get("state", "ALL") == sub_state for p in pending):
            self.send_json(200, {"message": "Check your email — confirmation link already sent", "email": email})
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
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

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

    def _get_wishlist(self, email: str):
        """Get wishlist species votes for an email from SQLite."""
        try:
            con = sqlite3.connect(VARIETY_WATCHES_DB)
            rows = con.execute(
                "SELECT species_slug FROM wishlist WHERE email = ? ORDER BY added_at",
                (email.lower(),)
            ).fetchall()
            con.close()
            return [r[0] for r in rows]
        except sqlite3.Error:
            return []

    def send_preferences_page(
        self,
        email: str,
        token: str,
        current_state: str,
        current_categories,
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

        # Frequency radio buttons
        freq_options = [
            ("daily", "Daily", "One email per day when any tracked change happens"),
            ("weekly", "Weekly summary", "A single curated email on Sunday mornings"),
            ("off", "Off", "No digest emails — but variety alerts still work"),
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
        variety_watches = self._get_variety_watches(email)
        variety_items = ""
        if variety_watches:
            for vw in variety_watches:
                safe_title = vw["title"].replace('"', "&quot;").replace("<", "&lt;")
                variety_items += (
                    f'<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;'
                    f'border-bottom:1px solid #f3f4f6">'
                    f'<span>{safe_title}</span>'
                    f'<button onclick="removeVariety(\'{vw["slug"]}\')" style="background:none;border:1px solid #d1d5db;'
                    f'color:#6b7280;padding:4px 12px;border-radius:6px;font-size:0.8rem;cursor:pointer">Remove</button>'
                    f'</div>'
                )
        else:
            variety_items = '<p style="color:#9ca3af;font-size:0.85rem">None. Browse variety pages to add watches.</p>'

        # Wishlist (read-only for now)
        wishlist = self._get_wishlist(email)
        if wishlist:
            wishlist_items = "".join(
                f'<li style="padding:4px 0;color:#374151">{slug.replace("-", " ").title()}</li>'
                for slug in wishlist
            )
            wishlist_html = (
                f'<ul style="list-style:none;padding:0;margin:0 0 12px">{wishlist_items}</ul>'
                f'<p style="color:#9ca3af;font-size:0.8rem;margin:0">'
                f'These are species you upvoted for nurseries to stock. They\'ll trigger variety alerts when a matching cultivar appears.'
                f'</p>'
            )
        else:
            wishlist_html = '<p style="color:#9ca3af;font-size:0.85rem">No wishlist items yet. Upvote a species from any species page.</p>'

        body = f"""
<h2 style="color:#065f46;margin:0 0 8px">Manage your alerts</h2>
<p style="color:#6b7280;font-size:0.9rem;margin:0 0 24px">{email}</p>

<form id="prefsForm" style="margin:0">

  <h3 style="color:#374151;font-size:1rem;margin:0 0 8px">State filter</h3>
  <p style="color:#6b7280;font-size:0.85rem;margin:0 0 8px">
    Only show updates from nurseries that ship to your state.
  </p>
  <select id="stateSelect" style="padding:8px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:0.9rem;width:100%;max-width:320px;margin-bottom:24px">
    {options}
  </select>

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

<h3 style="color:#374151;font-size:1rem;margin:24px 0 8px">Variety restock alerts</h3>
<p style="color:#6b7280;font-size:0.85rem;margin:0 0 8px">
  Get emailed when these specific varieties come back in stock anywhere.
</p>
<div id="varietyWatches" style="margin:0 0 24px">
{variety_items}
</div>

<h3 style="color:#374151;font-size:1rem;margin:24px 0 8px">Wishlist</h3>
<div style="margin:0 0 24px">
{wishlist_html}
</div>

<hr style="margin:24px 0;border:none;border-top:1px solid #e5e7eb">
<p style="font-size:0.8rem;color:#9ca3af">
  <a href="https://treestock.com.au/unsubscribe?email={email}&token={token}" style="color:#dc2626">Unsubscribe from all</a>
  &middot; <a href="https://treestock.com.au" style="color:#6b7280">treestock.com.au</a>
</p>
<script>
document.getElementById('prefsForm').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const state = document.getElementById('stateSelect').value;
  const categories = Array.from(document.querySelectorAll('#categoryGroup input[type=checkbox]:checked')).map(function(el) {{ return el.value; }});
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
        frequency: frequency
      }})
    }});
    const data = await resp.json();
    if (resp.ok) {{
      msg.style.color = '#065f46';
      let parts = [];
      parts.push(state === 'ALL' ? 'all states' : state);
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
        email: '{email}',
        token: '{token}',
        variety_slug: slug
      }})
    }});
    if (resp.ok) location.reload();
    else alert('Failed to remove watch.');
  }} catch (err) {{ alert('Network error.'); }}
}}
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

    def send_json(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
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
