#!/usr/bin/env python3
"""Log nursery contacts from a BCC'd Resend inbound address (DAL-273).

Benedict BCCs `nursery@veliamsal.resend.app` on any email to or from a nursery.
Resend receives it, fires an `email.received` webhook at subscribe_server, and
this module turns that into a touch on the nursery relationship register, so the
register stays current without anyone logging anything by hand from a phone.

Three layers, kept separate so the logic is unit-testable without I/O:
  - verify_signature(...)   Svix HMAC check over the raw request body
  - build_record(...)       payload + register -> a touch record, or None
  - append_record(...)      the only function that writes

**This deliberately does NOT write the register.** `deploy.sh:89` copies the repo
copy of `data/nursery-contacts.json` over the data-dir copy on every deploy, and
`dale-runner.sh` deploys hourly, so anything written to the data dir is gone
within the hour. Records land in an append-only JSONL that no deploy touches;
`nursery_crm.py merge-inbound` folds them into the repo register, where git
history remains the audit log for who we contacted and when.

Why Resend and not a Fastmail IMAP app password: DEC-265. Fastmail's narrowest
mail scope is Mail (IMAP/POP/SMTP) as one bundle, so that credential could have
read Benedict's entire mailbox and sent as him. This account is separate, holds
nothing but nursery BCCs, and has no webhook other than ours.
"""

import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone

INBOUND_LOG = "/opt/dale/data/nursery-inbound.jsonl"
SECRET_ENV = "/opt/dale/secrets/resend-inbound.env"

# Svix rejects anything older than this to blunt replay attacks. Five minutes is
# Svix's own documented default.
TIMESTAMP_TOLERANCE_S = 5 * 60

# Our own inbound domain. A message that was not delivered to us is not ours to
# log, whatever its headers claim.
RECEIVING_DOMAIN = "veliamsal.resend.app"

# The `email.received` webhook carries metadata only, no body and no headers.
# For a BCC'd message the metadata recipients are the envelope, so the nursery
# Benedict actually wrote to appears nowhere in the payload: the first real BCC
# was rejected as "no nursery matched" with to/cc holding only our own inbound
# address. The real To and Cc live on the full message, which has to be fetched.
RECEIVED_API = "https://api.resend.com/emails/receive/{email_id}"
RECEIVED_FETCH_TIMEOUT_S = 10


class InboundError(Exception):
    """Rejected. The message is the reason, safe to log, never returned to the
    caller: a signature failure should not tell an attacker which check failed."""


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def load_signing_secret(path=SECRET_ENV):
    """Read RESEND_INBOUND_SIGNING_SECRET (whsec_...) from the secrets file."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("RESEND_INBOUND_SIGNING_SECRET="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def verify_signature(secret, svix_id, svix_timestamp, raw_body, signature_header,
                     now=None):
    """Svix webhook verification. Returns True or raises InboundError.

    Signed content is `{id}.{timestamp}.{body}`, HMAC-SHA256 with the base64
    -decoded portion of the secret after `whsec_`, digest base64-encoded. The
    header carries a space-delimited list of `v1,<sig>` pairs, because Svix
    sends several during a secret rotation.

    `raw_body` must be the exact bytes received. Re-serialising the parsed JSON
    changes key order and whitespace and the signature will never match.
    """
    if not secret:
        raise InboundError("no signing secret configured")
    if not (svix_id and svix_timestamp and signature_header):
        raise InboundError("missing svix headers")

    try:
        ts = int(svix_timestamp)
    except (TypeError, ValueError):
        raise InboundError("unparseable svix-timestamp")

    now = int(time.time() if now is None else now)
    if abs(now - ts) > TIMESTAMP_TOLERANCE_S:
        raise InboundError(f"timestamp outside tolerance ({now - ts}s)")

    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")

    try:
        key = base64.b64decode(secret.split("_", 1)[1])
    except (IndexError, ValueError):
        raise InboundError("malformed signing secret")

    signed = svix_id.encode() + b"." + svix_timestamp.encode() + b"." + raw_body
    expected = base64.b64encode(
        hmac.new(key, signed, hashlib.sha256).digest()).decode()

    for part in signature_header.split():
        version, _, candidate = part.partition(",")
        if version != "v1":
            continue
        # Constant-time: a plain == leaks how much of the signature matched.
        if hmac.compare_digest(candidate, expected):
            return True
    raise InboundError("no matching v1 signature")


# ---------------------------------------------------------------------------
# Payload -> touch record
# ---------------------------------------------------------------------------

def _addresses(payload_field):
    """Normalise a payload recipient field to a list of bare addresses."""
    if not payload_field:
        return []
    if isinstance(payload_field, str):
        payload_field = [payload_field]
    out = []
    for entry in payload_field:
        if not isinstance(entry, str):
            continue
        # "Name <a@b.com>" or "a@b.com"
        m = re.search(r"<([^>]+)>", entry)
        addr = (m.group(1) if m else entry).strip().lower()
        if "@" in addr:
            out.append(addr)
    return out


def _domain_of(address):
    return address.rsplit("@", 1)[-1].lower().lstrip(".")


def _register_domains(register):
    """{domain: key} for every nursery carrying one."""
    out = {}
    for n in (register or {}).get("nurseries", []):
        domain = (n.get("domain") or "").strip().lower()
        if domain:
            out[domain.removeprefix("www.")] = n.get("key")
    return out


def match_nursery(address, register):
    """Nursery key for an email address, or None.

    Matches the address's domain against the register, allowing subdomains
    (`orders.daleysfruit.com.au` matches `daleysfruit.com.au`) because nurseries
    send from all sorts of hosts, but never the reverse: a longer registered
    domain must not be matched by a shorter incoming one.
    """
    domain = _domain_of(address)
    if not domain:
        return None
    known = _register_domains(register)
    if domain in known:
        return known[domain]
    for registered, key in known.items():
        if domain.endswith("." + registered):
            return key
    return None


def load_api_key(path=SECRET_ENV):
    """Read RESEND_API_KEY for the inbound account from the secrets file."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("RESEND_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return None


def _header_addresses(message):
    """To and Cc addresses off a fetched message, however Resend spells them.

    The API has returned headers as a dict and as a list of {name, value} in
    different accounts, so both are read rather than guessing which we get.
    """
    out = []
    for field in ("to", "cc"):
        out += _addresses(message.get(field))

    headers = message.get("headers")
    if isinstance(headers, dict):
        for name, value in headers.items():
            if str(name).lower() in ("to", "cc"):
                out += _addresses([value] if isinstance(value, str) else value)
    elif isinstance(headers, list):
        for h in headers:
            if not isinstance(h, dict):
                continue
            if str(h.get("name", "")).lower() in ("to", "cc"):
                out += _addresses([h.get("value")])
    return out


def fetch_received(email_id, api_key, timeout=RECEIVED_FETCH_TIMEOUT_S):
    """Full inbound message from the Received emails API, or None.

    Never raises: this is a fallback on a path that has already failed to match,
    so a Resend outage must degrade to the old "no nursery matched" rejection
    rather than turn into a 500 and an infinite Svix retry loop.
    """
    if not email_id or not api_key:
        return None
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        RECEIVED_API.format(email_id=email_id),
        headers={"Authorization": f"Bearer {api_key}",
                 "Accept": "application/json",
                 "User-Agent": "dale-nursery-inbound/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return None
    return body.get("data") if isinstance(body.get("data"), dict) else body


def build_record(payload, register, receiving_domain=RECEIVING_DOMAIN,
                 fetch=None, api_key=None):
    """Turn an `email.received` payload into a touch record, or raise.

    Direction is read from where the nursery actually appears: in `from` means
    they wrote to us, in `to`/`cc` means we wrote to them. Guessing from the
    BCC'ing habit instead would mislabel every forwarded reply.
    """
    data = (payload or {}).get("data") or {}

    # Only log what was genuinely delivered to our inbound address. `to` can say
    # anything; `received_for` is Resend's envelope record of who it was for.
    delivered = _addresses(data.get("received_for")) or _addresses(data.get("bcc"))
    if receiving_domain and not any(
            _domain_of(a) == receiving_domain for a in delivered):
        raise InboundError(
            f"not delivered to {receiving_domain} (received_for={delivered})")

    sender = _addresses(data.get("from"))
    recipients = _addresses(data.get("to")) + _addresses(data.get("cc"))

    key, direction, counterparty = None, None, None
    for addr in sender:
        key = match_nursery(addr, register)
        if key:
            direction, counterparty = "in", addr
            break
    if not key:
        for addr in recipients:
            key = match_nursery(addr, register)
            if key:
                direction, counterparty = "out", addr
                break

    # Nothing matched the metadata. For a BCC that is the expected case, not an
    # error: the webhook's recipients are the envelope, so they are our own
    # inbound address and the nursery is only on the real To/Cc header. Fetch
    # the full message and try again before giving up.
    fetched = []
    if not key:
        fetch = fetch or fetch_received
        message = fetch(data.get("email_id"), api_key or load_api_key())
        if message:
            fetched = _header_addresses(message)
            for addr in fetched:
                key = match_nursery(addr, register)
                if key:
                    direction, counterparty = "out", addr
                    break

    if not key:
        raise InboundError(
            f"no nursery matched (from={sender}, to/cc={recipients}, "
            f"fetched to/cc={fetched})")

    day = str(data.get("created_at") or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        day = datetime.now(timezone.utc).date().isoformat()

    return {
        "nursery": key,
        "date": day,
        "direction": direction,
        "channel": "email",
        "by": "benedict" if direction == "out" else key,
        "summary": (data.get("subject") or "(no subject)").strip()[:200],
        "evidence": f"resend:{data.get('email_id') or data.get('message_id') or '?'}",
        "counterparty": counterparty,
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "merged": False,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def already_logged(record, path=INBOUND_LOG):
    """True if this evidence id is already on file. Resend retries a webhook
    until it gets a 2xx, so the same email arrives more than once by design."""
    evidence = record.get("evidence")
    if not evidence:
        return False
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    if json.loads(line).get("evidence") == evidence:
                        return True
                except json.JSONDecodeError:
                    continue
    except OSError:
        return False
    return False


def append_record(record, path=INBOUND_LOG):
    """Append one record. Returns False if it was already on file."""
    if already_logged(record, path):
        return False
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return True


def load_register(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"nurseries": []}


def handle(raw_body, headers, register_path, secret_path=SECRET_ENV,
           log_path=INBOUND_LOG):
    """Full path: verify, parse, match, append. Returns a short status string.

    Raises InboundError for anything rejected. The caller answers 202 for
    accepted-and-ignored cases so Resend stops retrying a message we will never
    want, and 401 only for a failed signature.
    """
    verify_signature(
        load_signing_secret(secret_path),
        headers.get("svix-id"), headers.get("svix-timestamp"),
        raw_body, headers.get("svix-signature"),
    )

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError):
        raise InboundError("body is not JSON")

    if payload.get("type") != "email.received":
        return f"ignored event {payload.get('type')}"

    record = build_record(payload, load_register(register_path))
    written = append_record(record, log_path)
    return (f"logged {record['direction']} touch for {record['nursery']}"
            if written else f"duplicate {record['evidence']}, ignored")
