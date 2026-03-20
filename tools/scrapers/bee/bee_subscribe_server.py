#!/usr/bin/env python3
"""
Minimal email subscription server for beestock.com.au price alerts.

Runs as a tiny HTTP server on port 8098. Accepts POST /subscribe with email.
Stores subscribers in a JSON file. Runs behind Caddy reverse proxy.

Usage:
    python3 bee_subscribe_server.py          # Default port 8098
    python3 bee_subscribe_server.py --port 8098

Caddy config addition:
    handle /api/subscribe {
        reverse_proxy localhost:8098
    }
    handle /api/unsubscribe {
        reverse_proxy localhost:8098
    }
"""

import hashlib
import hmac
import json
import re
import subprocess
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlparse

SCRIPT_DIR = Path(__file__).parent

SUBSCRIBERS_FILE = Path("/opt/dale/data/bee-subscribers.json")
APP_ENV = Path("/opt/dale/secrets/app.env")
PORT = 8098
SITE_URL = "https://beestock.com.au"
SITE_NAME = "beestock.com.au"


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


class BeeSubscribeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = dict(parse_qsl(parsed.query))
        email = params.get("email", "").strip().lower()
        token = params.get("token", "").strip()

        if parsed.path in ("/unsubscribe", "/api/unsubscribe"):
            if not email or not token or not verify_unsubscribe_token(email, token):
                self.send_html(400, "<h2>Invalid unsubscribe link.</h2><p>Please visit beestock.com.au</p>")
                return

            subscribers = load_subscribers()
            updated = [s for s in subscribers if s["email"] != email]
            if len(updated) < len(subscribers):
                save_subscribers(updated)
                print(f"Unsubscribed: {email}")
                self.send_html(200, f"<h2>Unsubscribed</h2><p>{email} has been removed from beestock.com.au alerts.</p>")
            else:
                self.send_html(200, "<h2>Not found</h2><p>That email wasn't in our list.</p>")
            return

        self.send_error(404)

    def do_POST(self):
        if self.path not in ("/subscribe", "/api/subscribe"):
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()

        if self.headers.get("Content-Type", "").startswith("application/json"):
            try:
                data = json.loads(body)
                email = data.get("email", "").strip().lower()
            except json.JSONDecodeError:
                self.send_json(400, {"error": "Invalid JSON"})
                return
        else:
            params = parse_qs(body)
            email = params.get("email", [""])[0].strip().lower()

        if not email or not is_valid_email(email):
            self.send_json(400, {"error": "Valid email required"})
            return

        subscribers = load_subscribers()

        if any(s["email"] == email for s in subscribers):
            self.send_json(200, {"message": "Already subscribed", "email": email})
            return

        subscribers.append({
            "email": email,
            "subscribed_at": datetime.now().isoformat(),
        })
        save_subscribers(subscribers)

        print(f"New subscriber: {email} (total: {len(subscribers)})")

        # Send welcome email (non-blocking)
        welcome_script = SCRIPT_DIR / "send_bee_welcome_email.py"
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

    def send_json(self, code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, code: int, body_html: str):
        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>beestock.com.au</title>
<style>body{{font-family:sans-serif;max-width:480px;margin:60px auto;padding:20px;color:#374151;}}</style>
</head><body>{body_html}
<p><a href="{SITE_URL}">&larr; Back to beestock.com.au</a></p>
</body></html>"""
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")


def main():
    port = PORT
    if len(sys.argv) > 1:
        if sys.argv[1] == "--port" and len(sys.argv) > 2:
            port = int(sys.argv[2])

    server = HTTPServer(("127.0.0.1", port), BeeSubscribeHandler)
    print(f"Bee subscribe server running on port {port}")
    print(f"Subscribers file: {SUBSCRIBERS_FILE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
