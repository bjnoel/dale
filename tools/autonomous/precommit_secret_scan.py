#!/usr/bin/env python3
"""Block a commit that stages a literal credential.

The gate already existed and already worked. `config_scan.py` is the fail-closed
scanner for the weekly server-config snapshot, and fed the line that caused this
it blocks correctly:

    TOKEN = os.environ.get("SHOPIFY_ADMIN_API", "shpat_...")   -> blocked

What was missing was not detection, it was placement. The scanner only ran over
`infrastructure/`, so it never saw the path where the accident actually happens:
somebody types `git add -A` in a directory somebody else is also working in.

That has now happened twice with the same file. The first time (2026-08-11) a
human caught it in review and the lesson went into the decision log, which is
not a file anyone reads before running `git add`. The second time (2026-08-20)
nothing local caught it and the credential travelled all the way to GitHub,
where push protection refused it. A rule that only holds when someone remembers
it is not a rule, so this wires the existing scanner to the commit.

Scans the STAGED blob, not the working file: those differ whenever something was
staged and then edited, and the staged bytes are what a commit would publish.

Install (per clone, since hooks are not themselves cloned):

    git config core.hooksPath .githooks
"""

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from config_scan import scan_text  # noqa: E402 - sibling module, the shared gate

# Extensions judged as source rather than as config. In config, a sensitive NAME
# with a literal VALUE is the credential. In source, `TOKEN = os.environ.get(...)`
# is a reference and the correct way to write it, so those files are judged only
# on value-shaped detectors. See scan_text's `style` argument.
SOURCE_SUFFIXES = (".py", ".js", ".mjs", ".ts", ".jsx", ".tsx", ".sh", ".bash",
                   ".rb", ".go", ".java", ".cs", ".php", ".md", ".txt", ".json")

# Files whose "secrets" are deliberate test fixtures. Kept deliberately tiny:
# every entry here is a hole, and a growing allowlist means the scanner is
# miscalibrated rather than that the exceptions are real.
ALLOWLIST = frozenset({
    "tests/test_config_scan.py",       # feeds the scanner the shapes it must block
    "tests/test_precommit_secret_scan.py",
})

# Binary and vendored paths never carry a hand-written credential and would only
# produce noise.
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip",
                 ".woff", ".woff2", ".db", ".sqlite")
SKIP_PREFIXES = ("node_modules/", ".venv/")


def staged_paths():
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"],
        capture_output=True, text=True, check=True).stdout
    return [p for p in out.split("\0") if p]


def staged_blob(path):
    """The bytes git would commit, which are not always the bytes on disk."""
    result = subprocess.run(["git", "show", f":{path}"],
                            capture_output=True, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace")


def scan_staged(paths=None):
    findings = []
    for path in (staged_paths() if paths is None else paths):
        if path in ALLOWLIST:
            continue
        if path.endswith(SKIP_SUFFIXES) or path.startswith(SKIP_PREFIXES):
            continue
        text = staged_blob(path)
        if text is None or "\0" in text[:8000]:
            continue
        style = "source" if path.endswith(SOURCE_SUFFIXES) else "config"
        findings.extend(scan_text(text, source=path, style=style))
    return findings


def main():
    findings = scan_staged()
    if not findings:
        return 0
    print("\nCOMMIT BLOCKED: staged content looks like a credential.\n",
          file=sys.stderr)
    for f in findings:
        # describe() is the shared formatter and never includes the value.
        print(f"  {f.describe()}", file=sys.stderr)
    print("\nThe value itself is not printed, on purpose.\n"
          "  Move it to a gitignored .env or /opt/dale/secrets and read it at\n"
          "  runtime, then re-stage. If it is genuinely a fixture, add the path\n"
          "  to ALLOWLIST in tools/autonomous/precommit_secret_scan.py.\n"
          "  To bypass once, and only if you are certain: git commit --no-verify\n",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
