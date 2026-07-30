#!/usr/bin/env python3
"""Refresh the read-only Treesmith mirrors and write a status manifest (DAL-179).

Autonomous Dale runs on Hetzner and cannot see Benedict's Treesmith repos, which
led to tickets being filed for work that was already shipped (DAL-174, DAL-175
asked for RevenueCat and paywall code that had been integrated for weeks).

This pulls the two read-only mirrors and writes a compact manifest that
session-prompt.py renders into every session prompt. The manifest deliberately
stays small: the mirrors are on local disk, so a session that needs detail reads
the files directly instead of paying for them in every prompt.

Run from the cron wrapper before the session, not from inside the session.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

MIRRORS = {
    "app": "/opt/dale/treesmith-app",
    "web": "/opt/dale/treesmith-web",
}
OUTPUT = "/opt/dale/data/treesmith-status.json"


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def pull(repo):
    """Fast-forward the mirror. Returns (ok, message).

    A failed pull is not fatal: stale-but-present is far more useful than
    absent, and the manifest records the staleness so a session can see it.
    """
    code, _, err = git(repo, "pull", "--ff-only", "--quiet")
    if code == 0:
        return True, "ok"
    return False, (err.splitlines() or ["unknown error"])[-1][:200]


def head_info(repo):
    code, out, _ = git(repo, "log", "-1", "--format=%h%x1f%cI%x1f%s")
    if code != 0 or not out:
        return {}
    sha, date, subject = out.split("\x1f")
    return {"commit": sha, "commit_date": date, "commit_subject": subject}


def app_details(repo):
    """Flutter app: version, feature modules, monetisation-relevant packages."""
    details = {}

    pubspec = os.path.join(repo, "pubspec.yaml")
    deps = []
    if os.path.exists(pubspec):
        in_deps = False
        with open(pubspec) as f:
            for line in f:
                stripped = line.rstrip("\n")
                if stripped.startswith("version:"):
                    details["version"] = stripped.split(":", 1)[1].strip()
                if stripped.startswith("dependencies:"):
                    in_deps = True
                    continue
                if in_deps:
                    if stripped and not stripped.startswith((" ", "\t")):
                        in_deps = False
                        continue
                    # Exactly two spaces of indent is a package name. Deeper
                    # indents are that package's own keys (sdk:, git:, version:).
                    if stripped.startswith("  ") and not stripped.startswith("   "):
                        name = stripped.strip().split(":", 1)[0]
                        if name and name != "flutter":
                            deps.append(name)
    details["dependencies"] = sorted(set(deps))

    features_dir = os.path.join(repo, "lib", "features")
    if os.path.isdir(features_dir):
        details["features"] = sorted(
            d for d in os.listdir(features_dir)
            if os.path.isdir(os.path.join(features_dir, d))
        )

    build_file = os.path.join(repo, ".last_released_build")
    if os.path.exists(build_file):
        with open(build_file) as f:
            details["last_released_build"] = f.read().strip()[:40]

    docs = []
    for name in ("SPEC.md", "CLAUDE.md", "README.md", "store-listing-google-play.txt"):
        if os.path.exists(os.path.join(repo, name)):
            docs.append(name)
    docs_dir = os.path.join(repo, "docs")
    if os.path.isdir(docs_dir):
        docs.extend(f"docs/{n}" for n in sorted(os.listdir(docs_dir)))
    details["docs"] = docs

    return details


def web_details(repo):
    """Astro companion: which pages exist, and how many journal entries."""
    details = {}

    pages_dir = os.path.join(repo, "src", "pages")
    if os.path.isdir(pages_dir):
        pages = []
        for root, _dirs, files in os.walk(pages_dir):
            for name in files:
                if name.endswith((".astro", ".md", ".mdx", ".ts")):
                    rel = os.path.relpath(os.path.join(root, name), pages_dir)
                    pages.append(rel)
        details["pages"] = sorted(pages)

    for content_dir in ("src/content/journal", "src/content/posts"):
        full = os.path.join(repo, content_dir)
        if os.path.isdir(full):
            details["journal_entries"] = sorted(
                n for n in os.listdir(full) if n.endswith((".md", ".mdx"))
            )
            break

    return details


def build_manifest():
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": (
            "Read-only mirrors of Benedict's Treesmith repos (DAL-179). "
            "Push is disabled: Dale proposes app changes, Benedict commits them. "
            "Read files directly from the paths below rather than asking for them."
        ),
        "repos": {},
    }

    for key, path in MIRRORS.items():
        entry = {"path": path}
        if not os.path.isdir(os.path.join(path, ".git")):
            entry["error"] = "mirror missing (see DAL-179 to re-clone)"
            manifest["repos"][key] = entry
            continue

        ok, message = pull(path)
        entry["pull"] = message
        entry["stale"] = not ok
        entry.update(head_info(path))
        entry.update(app_details(path) if key == "app" else web_details(path))
        manifest["repos"][key] = entry

    return manifest


def main():
    manifest = build_manifest()

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    tmp = OUTPUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=2)
    os.replace(tmp, OUTPUT)

    errors = [k for k, v in manifest["repos"].items() if v.get("error")]
    print(f"Wrote {OUTPUT}")
    for key, entry in manifest["repos"].items():
        status = entry.get("error") or (
            f"{entry.get('commit', '?')} {entry.get('commit_date', '')}"
            + (" (STALE: pull failed)" if entry.get("stale") else "")
        )
        print(f"  {key}: {status}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
