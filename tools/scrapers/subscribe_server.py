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
APP_ENV = Path("/opt/dale/secrets/app.env")
VARIETY_WATCHES_DB = Path("/opt/dale/data/variety_watches.db")
PORT = 8099


def init_variety_watches_db():
    """Initialise the SQLite DB for per-variety restock watches."""
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


class SubscribeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = dict(parse_qsl(parsed.query))
        email = params.get("email", "").strip().lower()
        token = params.get("token", "").strip()

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
            self.send_preferences_page(email, token, current_state)
            return

        self.send_error(404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/subscribe", "/api/subscribe", "/watch-variety", "/api/watch-variety", "/unwatch-variety", "/api/unwatch-variety"):
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()

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

        # Handle watch (species restock alert)
        if action == "watch":
            species = data.get("species", "").strip().lower() if self.headers.get("Content-Type", "").startswith("application/json") else params.get("species", [""])[0].strip().lower()
            if not species:
                self.send_json(400, {"error": "Species slug required"})
                return
            subscribers = load_subscribers()
            existing = next((s for s in subscribers if s["email"] == email), None)
            if existing:
                watch_list = existing.get("watch_species", [])
                if species in watch_list:
                    self.send_json(200, {"message": "Already watching", "email": email, "species": species})
                    return
                existing.setdefault("watch_species", []).append(species)
            else:
                subscribers.append({
                    "email": email,
                    "subscribed_at": datetime.now().isoformat(),
                    "state": "ALL",
                    "watch_species": [species],
                })
            save_subscribers(subscribers)
            print(f"Watch added: {email} → {species}")
            self.send_json(201, {"message": "Alert set!", "email": email, "species": species})
            return

        # Handle preferences update
        if action == "update_preferences":
            if not verify_unsubscribe_token(email, token):
                self.send_json(403, {"error": "Invalid token"})
                return
            if self.headers.get("Content-Type", "").startswith("application/json"):
                new_state = data.get("state", "").upper().strip()
            else:
                new_state = params.get("state", [""])[0].upper().strip()
            valid_states = {"ALL", "NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT"}
            if new_state not in valid_states:
                self.send_json(400, {"error": f"Invalid state. Must be one of: {', '.join(sorted(valid_states))}"})
                return
            subscribers = load_subscribers()
            found = False
            for s in subscribers:
                if s["email"] == email:
                    s["state"] = new_state
                    s.pop("wa_only", None)
                    found = True
                    break
            if not found:
                self.send_json(404, {"error": "Subscriber not found"})
                return
            save_subscribers(subscribers)
            print(f"Preferences updated: {email} → state={new_state}")
            self.send_json(200, {"message": "Preferences updated", "state": new_state})
            return

        # Handle unwatch species
        if action == "unwatch_species":
            if not verify_unsubscribe_token(email, token):
                self.send_json(403, {"error": "Invalid token"})
                return
            species = data.get("species", "").strip().lower() if self.headers.get("Content-Type", "").startswith("application/json") else params.get("species", [""])[0].strip().lower()
            if not species:
                self.send_json(400, {"error": "Species slug required"})
                return
            subscribers = load_subscribers()
            for s in subscribers:
                if s["email"] == email:
                    watch_list = s.get("watch_species", [])
                    if species in watch_list:
                        watch_list.remove(species)
                    break
            save_subscribers(subscribers)
            print(f"Species watch removed: {email} → {species}")
            self.send_json(200, {"message": "Watch removed", "species": species})
            return

        # Handle subscribe (default)
        subscribers = load_subscribers()
        existing = [s for s in subscribers if s["email"] == email]

        if existing:
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

        subscribers.append({
            "email": email,
            "subscribed_at": datetime.now().isoformat(),
            "state": sub_state,
        })
        save_subscribers(subscribers)

        print(f"New subscriber: {email} (total: {len(subscribers)})")

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

        self.send_json(201, {"message": "Subscribed!", "email": email})

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

    def send_preferences_page(self, email: str, token: str, current_state: str):
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

        # Get species watches from subscriber record
        subscribers = load_subscribers()
        subscriber = next((s for s in subscribers if s["email"] == email), None)
        watch_species = subscriber.get("watch_species", []) if subscriber else []

        species_items = ""
        if watch_species:
            for sp in watch_species:
                display = sp.replace("-", " ").title()
                species_items += (
                    f'<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;'
                    f'border-bottom:1px solid #f3f4f6">'
                    f'<span>{display}</span>'
                    f'<button onclick="removeSpecies(\'{sp}\')" style="background:none;border:1px solid #d1d5db;'
                    f'color:#6b7280;padding:4px 12px;border-radius:6px;font-size:0.8rem;cursor:pointer">Remove</button>'
                    f'</div>'
                )
        else:
            species_items = '<p style="color:#9ca3af;font-size:0.85rem">None. Browse species pages to add watches.</p>'

        # Get variety watches from SQLite
        variety_watches = self._get_variety_watches(email)
        variety_items = ""
        if variety_watches:
            for vw in variety_watches:
                variety_items += (
                    f'<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;'
                    f'border-bottom:1px solid #f3f4f6">'
                    f'<span>{vw["title"]}</span>'
                    f'<button onclick="removeVariety(\'{vw["slug"]}\')" style="background:none;border:1px solid #d1d5db;'
                    f'color:#6b7280;padding:4px 12px;border-radius:6px;font-size:0.8rem;cursor:pointer">Remove</button>'
                    f'</div>'
                )
        else:
            variety_items = '<p style="color:#9ca3af;font-size:0.85rem">None. Browse variety pages to add watches.</p>'

        body = f"""
<h2 style="color:#065f46;margin:0 0 8px">Manage your alerts</h2>
<p style="color:#6b7280;font-size:0.9rem;margin:0 0 20px">{email}</p>

<h3 style="color:#374151;font-size:1rem;margin:0 0 8px">State filter</h3>
<p style="color:#6b7280;font-size:0.85rem;margin:0 0 12px">
  Only see stock updates from nurseries that ship to your state.
</p>
<form id="prefsForm" style="margin:0 0 24px">
  <select id="stateSelect" style="padding:8px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:0.9rem;width:100%;max-width:300px">
    {options}
  </select>
  <br>
  <button type="submit" style="margin-top:8px;background:#16a34a;color:white;border:none;padding:8px 20px;border-radius:8px;font-size:0.85rem;font-weight:600;cursor:pointer">
    Save
  </button>
</form>
<p id="prefsMsg" style="font-size:0.85rem;min-height:1.2em;margin:0 0 16px"></p>

<h3 style="color:#374151;font-size:1rem;margin:0 0 8px">Species restock alerts</h3>
<p style="color:#6b7280;font-size:0.85rem;margin:0 0 8px">
  Get emailed when any variety of these species comes back in stock.
</p>
<div id="speciesWatches" style="margin:0 0 24px">
{species_items}
</div>

<h3 style="color:#374151;font-size:1rem;margin:0 0 8px">Variety restock alerts</h3>
<p style="color:#6b7280;font-size:0.85rem;margin:0 0 8px">
  Get emailed when these specific varieties come back in stock.
</p>
<div id="varietyWatches" style="margin:0 0 24px">
{variety_items}
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
        state: state
      }})
    }});
    const data = await resp.json();
    if (resp.ok) {{
      msg.style.color = '#065f46';
      msg.textContent = 'Saved! Next digest will show ' + (state === 'ALL' ? 'all states' : state) + '.';
    }} else {{
      msg.style.color = '#dc2626';
      msg.textContent = data.error || 'Something went wrong.';
    }}
  }} catch (err) {{
    msg.style.color = '#dc2626';
    msg.textContent = 'Network error. Please try again.';
  }}
  btn.disabled = false;
  btn.textContent = 'Save';
}});

async function removeSpecies(slug) {{
  if (!confirm('Stop watching ' + slug.replace(/-/g, ' ') + '?')) return;
  try {{
    const resp = await fetch('/api/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{
        email: '{email}',
        token: '{token}',
        action: 'unwatch_species',
        species: slug
      }})
    }});
    if (resp.ok) location.reload();
    else alert('Failed to remove watch.');
  }} catch (err) {{ alert('Network error.'); }}
}}

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
