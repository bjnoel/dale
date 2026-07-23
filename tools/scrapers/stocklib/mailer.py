"""
Shared email plumbing for the treestock senders and subscribe server.

These helpers existed as 4-7 hand-synced copies each across the send_* scripts,
subscribe_server.py and the detect_* alerters (DEC-232 follow-up). They had not
drifted into live bugs yet, but make_unsubscribe_token is security-critical
(one divergent copy = every unsubscribe/preferences link from that sender
breaks), so they now live here behind the anti-fork guard.

Path constants are the production /opt/dale layout, same as every consumer
hardcoded before. The sends-log helpers take the log path as a parameter
because each sender keeps its own log file (digest_sends.json,
species_alert_sends.json, ...), and tests monkeypatch those module-level path
constants.
"""
import hashlib
import hmac
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SECRETS_DIR = Path("/opt/dale/secrets")
DATA_DIR = Path("/opt/dale/data")
RESEND_ENV = SECRETS_DIR / "resend.env"
APP_ENV = SECRETS_DIR / "app.env"
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"

FROM_EMAIL = "alerts@mail.treestock.com.au"
FROM_NAME = "treestock.com.au"


def get_resend_api_key() -> str:
    with open(RESEND_ENV) as f:
        for line in f:
            line = line.strip()
            if line.startswith("RESEND_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise ValueError("RESEND_API_KEY not found in resend.env")


def get_unsubscribe_secret(create: bool = False) -> str:
    """Load the stable HMAC secret for unsubscribe/preferences tokens.

    create=True (the daily digest, the first sender to run each day) generates
    and persists a secret if none exists; everyone else fails soft with ""
    so tokens are never minted from a made-up secret the server won't have.
    """
    if APP_ENV.exists():
        with open(APP_ENV) as f:
            for line in f:
                line = line.strip()
                if line.startswith("UNSUBSCRIBE_SECRET="):
                    return line.split("=", 1)[1].strip()
    if not create:
        return ""
    import secrets as _secrets
    secret = _secrets.token_hex(32)
    APP_ENV.parent.mkdir(parents=True, exist_ok=True)
    with open(APP_ENV, "a") as f:
        f.write(f"UNSUBSCRIBE_SECRET={secret}\n")
    print(f"Generated new UNSUBSCRIBE_SECRET in {APP_ENV}")
    return secret


def make_unsubscribe_token(email: str, secret: str | None = None) -> str:
    """The deterministic HMAC token used by every preferences/unsubscribe
    link. Senders pass the secret they already loaded; the subscribe server
    omits it. An empty secret yields "" (fail closed), never a token minted
    from an empty key."""
    if secret is None:
        secret = get_unsubscribe_secret()
    if not secret:
        return ""
    return hmac.new(
        secret.encode(), email.lower().encode(), hashlib.sha256
    ).hexdigest()[:32]


def load_subscribers() -> list:
    if not SUBSCRIBERS_FILE.exists():
        return []
    with open(SUBSCRIBERS_FILE) as f:
        return json.load(f)


def load_sends_log(path: Path) -> dict:
    """Read a sender's already-sent log ({date_str: [...]}). Tolerant of a
    missing or corrupt file: losing the log means at worst a duplicate email,
    never a crashed send run."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_sends_log(path: Path, log: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(log, f, indent=2)


def send_email(api_key: str, to_email: str, subject: str, html_body: str,
               text_body: str = "", user_agent: str = "treestock/1.0",
               timeout: int = 15) -> bool:
    """Send a single email via the Resend API. Returns True on success."""
    payload = {
        "from": f"{FROM_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        payload["text"] = text_body
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
            print(f"  Sent to {to_email}: {result.get('id', 'ok')}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        print(f"  FAILED {to_email} ({e.code}): {error_body}", file=sys.stderr)
        return False
