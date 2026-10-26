#!/usr/bin/env python3
"""Weekly: is any Docker image we run named in a published security advisory?

Plausible CE ran v3.2.0 until 2026-10-01, four and a half months past the fix
for CVE-2026-8467 (unauthenticated RCE via /storybook), and someone used it to
mine Monero from 2026-09-25. monthly_maintenance.py patches apt and reboots, but
images are pinned by tag in compose files, so nothing ever looked at them.

For each running container this reads the version actually running, reads the
upstream repo's GitHub security advisories, and flags any advisory whose
vulnerable range contains that version. It also notes when the registry holds a
newer build under the tag we run (a re-pull would change something), when an
exact tag has a newer release, and lists running images that are not in
WATCHED, so a new container cannot escape the check by being new. A newer build
that carries the same version (a base-image rebuild) is recorded as "info" and
does not send an email on its own.

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
MANIFEST_ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
])

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
    # GitHub, so only its version and image age are reported. Its security fixes
    # ship as minor releases under the same floating tag, so a newer build is
    # the only signal we get. version_env names the variable in the registry's
    # image config that says which release a build is: 2026-10-26 emailed "1 to
    # look at" for a rebuild of the same 16.15.
    "postgres": {"repo": None, "version": ["postgres", "--version"],
                 "version_env": "PG_VERSION"},
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
        m = re.fullmatch(r"\s*(>=|<=|>|<|=)?\s*v?(\d+(?:\.\d+)*)(?:-[A-Za-z]+)?\s*", clause)
        if not m:
            return None
        if not ops[m.group(1) or "="](_cmp(version, parse_version(m.group(2)))):
            return False
    return True


def applicable(vulns, version):
    """The advisory entries that speak for `version`'s release line.

    ClickHouse publishes one entry per line ("< 24.12.5.65" fixed in
    24.12.5.65, "< 25.1.5.5" fixed in 25.1.5.5, ...). Read flat, 24.12.6.70 is
    "< 25.1.5.5" and looks vulnerable although its own line was fixed at
    24.12.5.65 (a false alarm on the first live run, 2026-10-01). When an entry
    is patched within the running major.minor, only those entries count; when
    none is, every range applies, so a line too old to have its own fix is
    still caught."""
    same = [v for v in vulns
            if (parse_version(v.get("patched_versions") or "") or ())[:2] == version[:2]]
    return same or vulns


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "dale-image-advisories"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def split_image(image):
    """(registry host, repository, tag) for an image as `docker ps` prints it."""
    name, tag = image, "latest"
    if ":" in image.rsplit("/", 1)[-1]:
        name, tag = image.rsplit(":", 1)
    first = name.split("/", 1)[0]
    if "/" in name and ("." in first or ":" in first):
        return first, name.split("/", 1)[1], tag
    return "registry-1.docker.io", name if "/" in name else f"library/{name}", tag


def _registry_token(registry, repo):
    token_urls = {
        "registry-1.docker.io": "https://auth.docker.io/token?service=registry.docker.io"
                                f"&scope=repository:{repo}:pull",
        "ghcr.io": f"https://ghcr.io/token?scope=repository:{repo}:pull",
    }
    if registry not in token_urls:
        raise ValueError(f"no anonymous token flow known for {registry}")
    with urllib.request.urlopen(token_urls[registry], timeout=30) as resp:
        return json.loads(resp.read())["token"]


def registry_digest(image):
    """The digest the registry currently serves for this image's tag."""
    registry, repo, tag = split_image(image)
    token = _registry_token(registry, repo)
    req = urllib.request.Request(
        f"https://{registry}/v2/{repo}/manifests/{tag}", method="HEAD",
        headers={"Authorization": f"Bearer {token}", "Accept": MANIFEST_ACCEPT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.headers["Docker-Content-Digest"]


def registry_env(image, name, arch):
    """The value of env var `name` in the image config the registry serves for
    this image's tag on `arch`, or None if the config does not set it."""
    registry, repo, tag = split_image(image)
    token = _registry_token(registry, repo)

    def get(path, accept):
        req = urllib.request.Request(f"https://{registry}/v2/{repo}/{path}",
                                     headers={"Authorization": f"Bearer {token}", "Accept": accept})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    manifest = get(f"manifests/{tag}", MANIFEST_ACCEPT)
    if "manifests" in manifest:  # a multi-arch index: pick ours
        digest = next(m["digest"] for m in manifest["manifests"]
                      if m.get("platform", {}).get("architecture") == arch
                      and m.get("platform", {}).get("os") == "linux")
        manifest = get(f"manifests/{digest}", MANIFEST_ACCEPT)
    config = get(f"blobs/{manifest['config']['digest']}", "*/*")
    for kv in config.get("config", {}).get("Env") or []:
        key, _, value = kv.partition("=")
        if key == name:
            return value
    return None


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=True).stdout


def running_containers(_run=run):
    # `docker ps --format` has no image-id field; the container's inspect does.
    out = _run(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"])
    containers = [dict(zip(("name", "image"), line.split("\t")))
                  for line in out.splitlines() if line.strip()]
    for c in containers:
        c["image_id"] = _run(["docker", "inspect", "--format", "{{.Image}}", c["name"]]).strip()
    return containers


def image_info(image_id, _run=run):
    """(build time, the registry digests this image was pulled as, architecture)."""
    out = _run(["docker", "image", "inspect", image_id,
                "--format", "{{.Created}}\t{{json .RepoDigests}}\t{{.Architecture}}"]).strip()
    created, digests, arch = out.split("\t", 2)
    return (datetime.fromisoformat(created[:19]).replace(tzinfo=timezone.utc),
            {d.rsplit("@", 1)[-1] for d in json.loads(digests) or []}, arch)


def check(now=None, _run=run, _fetch=fetch_json, _digest=registry_digest, _env=registry_env):
    """Return the status dict. Findings carry a severity: "affected" (a known
    advisory covers what is running), "error" (could not tell), "notice", or
    "info" (recorded, never emailed on its own)."""
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

        # An exact tag (v3.2.1) asks whether a newer release exists: that is the
        # warning Plausible's four and a half months on v3.2.0 never got.
        exact = re.fullmatch(r"v?\d+\.\d+\.\d+", tag) is not None
        if exact and watch["repo"] and version:
            try:
                latest = _fetch(f"https://api.github.com/repos/{watch['repo']}/releases/latest")
                newest = parse_version(latest.get("tag_name"))
                if newest and _cmp(newest, version) > 0:
                    findings.append({"severity": "notice", "container": c["name"],
                                     "detail": f"running {vtext}; {latest['tag_name']} was released "
                                               f"{(latest.get('published_at') or '?')[:10]}"})
            except Exception as e:  # noqa: BLE001
                findings.append({"severity": "error", "container": c["name"],
                                 "detail": f"could not read the latest release of {watch['repo']}: {e}"})

        # Any tag: would a re-pull change anything? Build age cannot say. The
        # first version nagged about ClickHouse's 568-day-old image, but
        # 24.12-alpine had simply had its last build; a re-pull (2026-10-01)
        # returned the same digest. Comparing digests answers the real question.
        try:
            created, local, arch = image_info(c["image_id"], _run)
            entry["image_age_days"] = (now - created).days
            remote = _digest(c["image"])
            if remote not in local:
                findings.append(newer_build(c, remote, version, vtext, watch, arch, _env))
        except Exception as e:  # noqa: BLE001
            findings.append({"severity": "error", "container": c["name"],
                             "detail": f"could not compare {c['image']} with its registry: {e}"})

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
                vulns = applicable(adv.get("vulnerabilities") or [], version)
                ranges = [v.get("vulnerable_version_range") for v in vulns]
                verdicts = [in_range(version, r) for r in ranges]
                label = (f"{adv.get('ghsa_id')} ({adv.get('cve_id') or 'no CVE'}, "
                         f"{adv.get('severity')}): {adv.get('summary')}")
                if any(v is True for v in verdicts):
                    patched = ", ".join(sorted({v.get("patched_versions") or "?" for v in vulns}))
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


def newer_build(c, remote, version, vtext, watch, arch, _env):
    """The finding for a registry digest that differs from the one we pulled.

    A different digest is not a different release: postgres:16-alpine is
    rebuilt whenever Alpine patches a package, and on 2026-10-26 the checker
    emailed "1 to look at" for a rebuild that was still 16.15. Where the image
    config names its version, a same-version rebuild is "info" (recorded, not
    emailed) and a new version says which. Where it cannot tell, it says so as
    a notice rather than guessing either way."""
    base = {"container": c["name"]}
    short = remote[7:19]
    name = watch.get("version_env")
    if name and version:
        try:
            raw = _env(c["image"], name, arch)
        except Exception as e:  # noqa: BLE001
            raw, why = None, f"could not read its version: {e}"
        else:
            why = f"its config has no {name}"
        remote_version = parse_version(raw)
        if remote_version == version:
            return {**base, "severity": "info",
                    "detail": f"the registry rebuilt {c['image']} ({short}) without changing the "
                              f"version (still {vtext}); a re-pull is optional"}
        if remote_version:
            return {**base, "severity": "notice",
                    "detail": f"the registry now has {raw} under {c['image']} ({short}); running "
                              f"{vtext}. A re-pull would update it"}
        return {**base, "severity": "notice",
                "detail": f"the registry has a newer build of {c['image']} than the one running "
                          f"({short}), but {why}. A re-pull would update it"}
    return {**base, "severity": "notice",
            "detail": f"the registry has a newer build of {c['image']} than the "
                      f"one running ({short}); a re-pull would update it"}


def _advisory_summary(c, findings):
    if "advisories_read" not in c:
        return "advisories not checked (not published on GitHub)"
    n = c["advisories_read"]
    hits = sum(f["severity"] == "affected" and f["container"] == c["container"] for f in findings)
    read = f"{n} {'advisory' if n == 1 else 'advisories'} checked"
    if not n:
        return read
    return f"{read}, {hits or 'none'} affect{'s' if hits == 1 else ''} {c['version']}"


def actionable(status):
    return [f for f in status["findings"] if f["severity"] != "info"]


def render(status):
    rank = {"affected": 0, "error": 1, "notice": 2, "info": 3}
    lines = [f"Docker image security check, {status['checked_at']}", ""]
    for c in status["containers"]:
        lines.append(f"  {c['container']}: {c['image']} running {c['version']}, "
                     f"image {c.get('image_age_days', '?')} days old, "
                     f"{_advisory_summary(c, status['findings'])}")
    lines.append("")
    for f in sorted(status["findings"], key=lambda f: rank[f["severity"]]):
        lines.append(f"[{f['severity'].upper()}] {f['container']}: {f['detail']}"
                     + (f"\n    {f['url']}" if f.get("url") else ""))
    if not actionable(status):
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

    if actionable(status):
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
