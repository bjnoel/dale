#!/usr/bin/env python3
"""
Post-deploy smoke test for treestock.com.au.

Checks that key pages return 200 and are a reasonable size.
Sends an email alert via Resend if anything fails.

Usage:
    python3 smoke_test.py          # Run tests, send alert on failure
    python3 smoke_test.py --quiet  # Suppress pass output
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

SITE = "https://treestock.com.au"

# (path, min_bytes, expected_content_snippet)
PAGES = [
    ("/",               400_000, "treestock"),
    ("/digest.html",      5_000, "treestock"),
    ("/guide.html",      10_000, "rare fruit"),
    ("/species/mango.html", 5_000, "mango"),
    ("/sitemap.xml",      1_000, "treestock.com.au"),
]

# Subscribe API: POST with invalid email should return 4xx (server is alive)
API_CHECK = {
    "url": f"{SITE}/api/subscribe",
    "method": "POST",
    "body": b'{"email": "smoke-test-invalid@"}',
    "expected_status_range": (400, 499),
    "label": "/api/subscribe (alive check)",
}


def check_page(path: str, min_bytes: int, snippet: str, quiet: bool) -> list[str]:
    """Returns list of failure messages (empty = pass)."""
    url = f"{SITE}{path}"
    failures = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "treestock-smoketest/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as e:
        failures.append(f"{path}: HTTP {e.code} (expected 200)")
        return failures
    except Exception as e:
        failures.append(f"{path}: connection error — {e}")
        return failures

    if status != 200:
        failures.append(f"{path}: status {status} (expected 200)")
    if len(body) < min_bytes:
        failures.append(f"{path}: size {len(body):,} bytes (expected >= {min_bytes:,})")
    if snippet and snippet.lower() not in body.decode("utf-8", errors="replace").lower():
        failures.append(f"{path}: expected content '{snippet}' not found in response")

    if not failures and not quiet:
        print(f"  PASS  {path} — {len(body):,} bytes, status {status}")
    return failures


def check_api(quiet: bool) -> list[str]:
    """Check the subscribe API is alive by posting invalid data."""
    failures = []
    url = API_CHECK["url"]
    try:
        req = urllib.request.Request(
            url,
            data=API_CHECK["body"],
            headers={
                "Content-Type": "application/json",
                "User-Agent": "treestock-smoketest/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        failures.append(f"/api/subscribe: connection error — {e}")
        return failures

    lo, hi = API_CHECK["expected_status_range"]
    if not (lo <= status <= hi):
        failures.append(f"/api/subscribe: status {status} (expected 4xx — is server running?)")
    elif not quiet:
        print(f"  PASS  /api/subscribe — status {status} (server alive)")
    return failures


def send_alert(failures: list[str]) -> None:
    """Send email alert via notify.py's send_email function."""
    try:
        sys.path.insert(0, "/opt/dale/autonomous")
        from notify import send_email  # type: ignore
    except ImportError:
        print("WARNING: notify.py not found, can't send alert email", file=sys.stderr)
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    failure_list = "".join(f"<li>{f}</li>" for f in failures)
    html = f"""<h2>[ALERT] treestock.com.au smoke test failed</h2>
<p><strong>Time:</strong> {now}</p>
<p><strong>Failures ({len(failures)}):</strong></p>
<ul>{failure_list}</ul>
<p>Dashboard may be broken. Check the server and rebuild logs.</p>"""

    text = f"[ALERT] treestock.com.au smoke test failed — {now}\n\nFailures:\n" + "\n".join(f"- {f}" for f in failures)
    send_email(f"[ALERT] treestock.com.au smoke test failed ({len(failures)} issues)", html, text)


def main():
    quiet = "--quiet" in sys.argv
    all_failures = []

    print(f"Smoke testing {SITE}...")
    for path, min_bytes, snippet in PAGES:
        all_failures.extend(check_page(path, min_bytes, snippet, quiet))
    all_failures.extend(check_api(quiet))

    if all_failures:
        print(f"\nFAIL — {len(all_failures)} issue(s):")
        for f in all_failures:
            print(f"  - {f}")
        send_alert(all_failures)
        sys.exit(1)
    else:
        print(f"All smoke tests passed ({len(PAGES) + 1} checks).")
        sys.exit(0)


if __name__ == "__main__":
    main()
