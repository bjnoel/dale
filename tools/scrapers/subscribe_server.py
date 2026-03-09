#!/usr/bin/env python3
"""
Minimal email subscription server for scion.exchange stock alerts.

Runs as a tiny HTTP server that accepts POST /subscribe with an email address.
Stores subscribers in a JSON file. Designed to run behind Caddy reverse proxy.

Usage:
    python3 subscribe_server.py                    # Default port 8099
    python3 subscribe_server.py --port 8099

Caddy config addition:
    handle /api/subscribe {
        reverse_proxy localhost:8099
    }
"""

import json
import re
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs

SUBSCRIBERS_FILE = Path("/opt/dale/data/subscribers.json")
PORT = 8099


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
    def do_POST(self):
        if self.path != "/subscribe":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()

        # Support both form-encoded and JSON
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
        existing = [s for s in subscribers if s["email"] == email]

        if existing:
            self.send_json(200, {"message": "Already subscribed", "email": email})
            return

        subscribers.append({
            "email": email,
            "subscribed_at": datetime.now().isoformat(),
            "wa_only": True,  # Default to WA-focused alerts
        })
        save_subscribers(subscribers)

        print(f"New subscriber: {email} (total: {len(subscribers)})")
        self.send_json(201, {"message": "Subscribed!", "email": email})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

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

    server = HTTPServer(("127.0.0.1", port), SubscribeHandler)
    print(f"Subscribe server listening on 127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")


if __name__ == "__main__":
    main()
