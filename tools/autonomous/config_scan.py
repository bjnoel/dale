#!/usr/bin/env python3
"""
Secret scanner for the server-config snapshot (DAL-281).

snapshot-server-config.sh captures live server config into infrastructure/ and
commits it to a PUBLIC repo, unattended, every Monday. That is a standing
hazard rather than a one-off risk: the week after someone inlines a credential
into a unit file or a compose file, the job publishes it and nobody is in the
loop to notice.

So the snapshot fails closed, and this module is the gate. It lives outside the
shell script so it can be tested properly: scan_text is pure, and
tests/test_config_scan.py feeds it the shapes we actually expect to meet.

The design is one distinction: an assignment whose NAME looks sensitive and
whose VALUE is a literal.

    POSTGRES_PASSWORD=hunter2                      -> blocked
    POSTGRES_PASSWORD=${POSTGRES_PASSWORD}         -> fine, a reference
    EnvironmentFile=/opt/dale/secrets/lodgify.env  -> fine, a path
    # The token is in the request path             -> fine, prose

The last two are not hypothetical. gandon-hook.service carries that exact
EnvironmentFile line and the live Caddyfile carries that exact comment. A
scanner that greps for the word "token" blocks on both, and a gate that cries
wolf gets switched off within a month, which is worse than no gate at all.

Comments are deliberately NOT skipped: `# POSTGRES_PASSWORD=hunter2` is still a
published credential.
"""

import re
import sys

# Names that make a value worth protecting. Matched case-insensitively against
# the whole identifier, so DB_PASSWORD, POSTGRES_PASSWORD and password all hit.
SENSITIVE_NAME = re.compile(
    r"[A-Za-z0-9_]*"
    r"(PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|LICENSE_KEY|PRIVATE_KEY|ACCESS_KEY|CREDENTIALS?)"
    r"[A-Za-z0-9_]*",
    re.IGNORECASE,
)

# NAME = VALUE or NAME: VALUE, in env files, compose yaml, systemd units and
# shell. The value runs to end of line so a quoted value with spaces is caught.
ASSIGNMENT = re.compile(r"^(?P<indent>.*?)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*(?P<value>.*)$")

PEM_PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")
AWS_ACCESS_KEY_ID = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
BEARER_LITERAL = re.compile(r"(?i)\bBearer\s+(?![$<])[A-Za-z0-9._\-]{16,}")

# Values that are references, paths or obvious placeholders. None of these is a
# credential, and all of them appear in files we legitimately track.
SAFE_VALUE = re.compile(
    r"""^(
          \$\{.*\}          # ${VAR} and ${VAR:-default}
        | \$\(.*\)          # $(command)
        | \$[A-Za-z_][A-Za-z0-9_]*   # $VAR
        | /\S*              # an absolute path, e.g. an EnvironmentFile
        | <[^>]*>           # <placeholder> as used in docs
        | \*+               # ***
        | REDACTED|MASKED|CHANGEME|TODO|NONE|NULL|TRUE|FALSE|YES|NO
        )$""",
    re.IGNORECASE | re.VERBOSE,
)


class Finding:
    """One reason the snapshot must not be committed."""

    def __init__(self, source, line_no, kind, name, line):
        self.source = source
        self.line_no = line_no
        self.kind = kind
        self.name = name
        self.line = line

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"<Finding {self.source}:{self.line_no} {self.kind} {self.name}>"

    def describe(self):
        """One line for a log or an email. Never includes the value itself."""
        return f"{self.source}:{self.line_no}: {self.kind} in {self.name}"


def _strip_quotes(value):
    value = value.strip()
    # Drop a trailing yaml/shell comment only when the value is unquoted, so a
    # password containing a '#' is not silently truncated into looking safe.
    if value[:1] not in ("'", '"'):
        value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value


def _is_literal_secret(value):
    """True when `value` is an actual credential rather than a reference."""
    if not value:
        return False
    if SAFE_VALUE.match(value):
        return False
    return True


def scan_text(text, source="<text>"):
    """Return every reason `text` must not be published. Pure, no I/O."""
    findings = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        if PEM_PRIVATE_KEY.search(line):
            findings.append(Finding(source, line_no, "private key block", "PEM", line))
            continue
        if AWS_ACCESS_KEY_ID.search(line):
            findings.append(Finding(source, line_no, "AWS access key id", "AKIA", line))
            continue
        if BEARER_LITERAL.search(line):
            findings.append(Finding(source, line_no, "bearer token", "Authorization", line))
            continue

        match = ASSIGNMENT.match(line)
        if not match:
            continue

        name = match.group("name")
        if not SENSITIVE_NAME.fullmatch(name):
            continue

        if _is_literal_secret(_strip_quotes(match.group("value"))):
            findings.append(Finding(source, line_no, "literal secret", name, line))

    return findings


def scan_file(path):
    with open(path, "r", errors="replace") as handle:
        return scan_text(handle.read(), source=path)


def main(argv):
    if len(argv) < 2:
        print("usage: config_scan.py <file> [file ...]", file=sys.stderr)
        return 2

    findings = []
    for path in argv[1:]:
        try:
            findings.extend(scan_file(path))
        except OSError as exc:
            print(f"cannot read {path}: {exc}", file=sys.stderr)
            return 2

    for finding in findings:
        print(finding.describe())

    # Exit 1 on any finding so the caller can gate on it. Deliberately loud and
    # deliberately value-free: this output goes into a log and an email.
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
