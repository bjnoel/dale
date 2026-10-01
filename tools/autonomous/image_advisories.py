#!/usr/bin/env python3
"""Weekly: is any Docker image we run named in a published security advisory?

Plausible CE ran v3.2.0 until 2026-10-01, four and a half months past the fix
for CVE-2026-8467 (unauthenticated RCE via /storybook), and someone used it to
mine Monero from 2026-09-25. monthly_maintenance.py patches apt and reboots, but
images are pinned by tag in compose files, so nothing ever looked at them.

For each running container this reads the version actually running, reads the
upstream repo's GitHub security advisories, and flags any advisory whose
vulnerable range contains that version. It also notes images that have not been
re-pulled in IMAGE_AGE_DAYS, and lists running images that are not in WATCHED,
so a new container cannot escape the check by being new.

A feed that cannot be read, or a range that cannot be parsed, is reported as
such, never as "no advisories" (DEC-317: a reading that looks the same either
way is not evidence). Writes data/image-advisories.json on every run, which the
daily digest reads, so a check that stops running shows up there too. Emails
only when there is something to act on.

Usage:
  image_advisories.py            # check, write status, email if needed
  image_advisories.py --dry-run  # check and print; no email, no status file
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("DALE_DATA_DIR", "/opt/dale/data"))
STATUS_FILE = DATA_DIR / "image-advisories.json"
IMAGE_AGE_DAYS = 120

# Image repository -> where its advisories are published, and how to read the
# running version. "tag" trusts the image tag; a list is run inside the
# container and the first dotted number in its output is the version.
WATCHED = {
    "ghcr.io/plausible/community-edition": {
        "repo": "plausible/analytics", "version": "tag"},
    "clickhouse/clickhouse-server": {
        "repo": "ClickHouse/ClickHouse",
        "version": ["clickhouse-client", "-q", "SELECT version()"]},
    # PostgreSQL publishes advisories at postgresql.org/support/security, not on
    # GitHub, so only its version and image age are reported.
    "postgres": {"repo": None, "version": ["postgres", "--version"]},
}


def parse_version(text):
    """First dotted number in `text` as a tuple of ints, or None."""
    m = re.search(r"(\d+(?:\.\d+)*)", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _cmp(a, b):
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return (a > b) - (a < b)


def in_range(version, range_str):
    """True/False if `version` is inside a GitHub vulnerable_version_range such
    as ">=3 and < 3.2.1" or ">= 24.1, < 24.3.18.7"; None if it cannot be read."""
    ops = {">=": lambda c: c >= 0, "<=": lambda c: c <= 0, ">": lambda c: c > 0,
           "<": lambda c: c < 0, "=": lambda c: c == 0}
    clauses = [c for c in re.split(r",|\band\b", range_str or "") if c.strip()]
    if not clauses:
        return None
    for clause in clauses:
        m = re.fullmatch(r"\s*(>=|<=|>|<|=)?\s*v?(\d+(?:\.\d+)*)\s*", clause)
        if not m:
            return None
        if not ops[m.group(1) or "="](_cmp(version, parse_version(m.group(2)))):
            return False
    return True


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "dale-image-advisories"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True).stdout


def running_containers(_run=run):
    out = _run(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.ImageID}}"])
    return [dict(zip(("name", "image", "image_id"), line.split("\t")))
            for line in out.splitlines() if line.strip()]


def image_created(image_id, _run=run):
    out = _run(["docker", "image", "inspect", image_id, "--format", "{{.Created}}"]).strip()
    return datetime.fromisoformat(out[:19]).replace(tzinfo=timezone.utc)


def check(now=None, _run=run, _fetch=fetch_json):
    """Return the status dict. Findings carry a severity: "affected" (a known
    advisory covers what is running), "error" (could not tell), "notice"."""
    now = now or datetime.now(timezone.utc)
    findings, checked = [], []
    for c in running_containers(_run):
        repo_name, _, tag = c["image"].rpartition(":") if ":" in c["image"] else (c["image"], "", "latest")
        watch = WATCHED.get(repo_name)
        if watch is None:
            findings.append({"severity": "notice", "container": c["name"],
                             "detail": f"{c['image']} is running but not in WATCHED, so no advisories are checked for it"})
            continue
        try:
            raw = tag if watch["version"] == "tag" else _run(
                ["docker", "exec", c["name"], *watch["version"]])
        except Exception as e:  # noqa: BLE001 -- any failure is reported, not swallowed
            raw = None
            findings.append({"severity": "error", "container": c["name"],
                             "detail": f"could not read the running version: {e}"})
        version = parse_version(raw)
        vtext = ".".join(map(str, version)) if version else "unknown"
        entry = {"container": c["name"], "image": c["image"], "version": vtext}

        try:
            age = (now - image_created(c["image_id"], _run)).days
            entry["image_age_days"] = age
            if age > IMAGE_AGE_DAYS:
                findings.append({"severity": "notice", "container": c["name"],
                                 "detail": f"{c['image']} was built {age} days ago and has not been re-pulled since"})
        except Exception as e:  # noqa: BLE001
            findings.append({"severity": "error", "container": c["name"],
                             "detail": f"could not read the image date: {e}"})

        if watch["repo"] and version:
            try:
                advisories = _fetch(f"https://api.github.com/repos/{watch['repo']}"
                                    "/security-advisories?per_page=100")
            except Exception as e:  # noqa: BLE001
                findings.append({"severity": "error", "container": c["name"],
                                 "detail": f"could not read advisories for {watch['repo']}: {e}"})
                advisories = []
            entry["advisories_read"] = len(advisories)
            for adv in advisories:
                if adv.get("withdrawn_at"):
                    continue
                ranges = [v.get("vulnerable_version_range") for v in adv.get("vulnerabilities") or []]
                verdicts = [in_range(version, r) for r in ranges]
                label = (f"{adv.get('ghsa_id')} ({adv.get('cve_id') or 'no CVE'}, "
                         f"{adv.get('severity')}): {adv.get('summary')}")
                if any(v is True for v in verdicts):
                    patched = ", ".join(sorted({v.get("patched_versions") or "?" for v in adv["vulnerabilities"]}))
                    findings.append({"severity": "affected", "container": c["name"],
                                     "detail": f"{vtext} is affected by {label}. Fixed in: {patched}",
                                     "url": adv.get("html_url")})
                elif not verdicts or any(v is None for v in verdicts):
                    findings.append({"severity": "error", "container": c["name"],
                                     "detail": f"could not read the affected range of {label}: {ranges}",
                                     "url": adv.get("html_url")})
        checked.append(entry)

    return {"checked_at": now.isoformat(timespec="seconds"), "containers": checked,
            "findings": findings}


def render(status):
    rank = {"affected": 0, "error": 1, "notice": 2}
    lines = [f"Docker image security check, {status['checked_at']}", ""]
    for c in status["containers"]:
        lines.append(f"  {c['container']}: {c['image']} running {c['version']}, "
                     f"image {c.get('image_age_days', '?')} days old, "
                     f"{c.get('advisories_read', 'no')} advisories read")
    lines.append("")
    for f in sorted(status["findings"], key=lambda f: rank[f["severity"]]):
        lines.append(f"[{f['severity'].upper()}] {f['container']}: {f['detail']}"
                     + (f"\n    {f['url']}" if f.get("url") else ""))
    if not status["findings"]:
        lines.append("Nothing to act on.")
    return "\n".join(lines)


def main():
    dry_run = "--dry-run" in sys.argv
    try:
        status = check()
    except Exception as e:  # noqa: BLE001
        status = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "containers": [], "findings": [{"severity": "error", "container": "(all)",
                                                  "detail": f"check crashed: {e!r}"}]}
    text = render(status)
    print(text)
    if dry_run:
        return
    STATUS_FILE.write_text(json.dumps(status, indent=2) + "\n")

    if status["findings"]:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from notify import send_email
        send_email(subject_for(status), f"<pre>{text}</pre>", text)


def subject_for(status):
    count = {s: sum(f["severity"] == s for f in status["findings"])
             for s in ("affected", "error", "notice")}
    if count["affected"]:
        return f"SECURITY: {count['affected']} advisory affects a running service"
    if count["error"]:
        return "Docker image check could not complete"
    return f"Docker images: {count['notice']} to look at"


if __name__ == "__main__":
    main()
