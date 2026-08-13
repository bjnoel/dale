"""Tests for tools/autonomous/snapshot-server-config.sh (DAL-281).

The script runs unattended, weekly, and commits to a public repo. The property
that matters most is not that it captures config correctly; it is that it
refuses to when the capture contains a credential. So the blocking path is
tested harder than the happy path: it must exit non-zero, write nothing into the
working tree, commit nothing, and tell a person.

The script takes its paths from the environment (DALE_REPO, DALE_SCANNER,
DALE_NOTIFY, DALE_LOG) and DALE_SNAPSHOT_STAGING substitutes fixture files for
the live server read, so all of this runs against a throwaway git repo with no
server involved.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools" / "autonomous"
SCRIPT = TOOLS / "snapshot-server-config.sh"
SCANNER = TOOLS / "config_scan.py"
GIT_SYNC = TOOLS / "git_sync.sh"

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}

NOTIFY_STUB = """#!/usr/bin/env python3
import os, sys
with open(os.environ["NOTIFY_LOG"], "a") as fh:
    fh.write("\\x00".join(sys.argv[1:]) + "\\n")
"""

CLEAN_CRONTAB = "0 * * * * /opt/dale/autonomous/dale-runner.sh\n"
CLEAN_UNIT = "[Service]\nUser=dale\nExecStart=/usr/bin/python3 /opt/dale/scrapers/subscribe_server.py\n"
CLEAN_COMPOSE = "services:\n  db:\n    environment:\n      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}\n"
LEAKY_COMPOSE = "services:\n  db:\n    environment:\n      - POSTGRES_PASSWORD=hunter2literal\n"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
        env={**os.environ, **GIT_ENV}, check=False,
    )


class SnapshotHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.origin)], check=True)

        self.repo = root / "repo"
        subprocess.run(
            ["git", "clone", "-q", str(self.origin), str(self.repo)],
            check=True, env={**os.environ, **GIT_ENV},
        )

        # The repo needs the pieces the script reaches for by path.
        auto = self.repo / "tools" / "autonomous"
        auto.mkdir(parents=True)
        (auto / "git_sync.sh").write_text(GIT_SYNC.read_text())
        (auto / "config_scan.py").write_text(SCANNER.read_text())
        self.notify = auto / "notify_stub.py"
        self.notify.write_text(NOTIFY_STUB)

        self.infra = self.repo / "infrastructure"
        self.infra.mkdir()
        (self.infra / "README.md").write_text("hand-written, must survive\n")

        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "seed")
        git(self.repo, "branch", "-M", "main")
        git(self.repo, "push", "-q", "-u", "origin", "main")

        self.log = root / "cron.log"
        self.notify_log = root / "notify.log"
        self.staging = root / "staging"
        (self.staging / "systemd").mkdir(parents=True)
        (self.staging / "plausible").mkdir(parents=True)

    def stage(self, compose=CLEAN_COMPOSE, crontab=CLEAN_CRONTAB):
        (self.staging / "crontab.txt").write_text(crontab)
        (self.staging / "systemd" / "subscribe-server.service").write_text(CLEAN_UNIT)
        (self.staging / "plausible" / "docker-compose.yml").write_text(compose)

    def run_script(self, *args):
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True, text=True,
            env={
                **os.environ, **GIT_ENV,
                "DALE_REPO": str(self.repo),
                "DALE_LOG": str(self.log),
                "DALE_NOTIFY": str(self.notify),
                "DALE_SCANNER": str(self.repo / "tools" / "autonomous" / "config_scan.py"),
                "DALE_SNAPSHOT_STAGING": str(self.staging),
                "NOTIFY_LOG": str(self.notify_log),
            },
        )

    def commit_count(self):
        return int(git(self.repo, "rev-list", "--count", "HEAD").stdout.strip())

    def alerts(self):
        if not self.notify_log.exists():
            return []
        return [l for l in self.notify_log.read_text().splitlines() if l.strip()]


class CleanCapture(SnapshotHarness):
    def test_captures_commits_and_pushes(self):
        self.stage()
        before = self.commit_count()

        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)

        self.assertEqual((self.infra / "crontab.txt").read_text(), CLEAN_CRONTAB)
        self.assertEqual(
            (self.infra / "plausible" / "docker-compose.yml").read_text(), CLEAN_COMPOSE
        )
        self.assertEqual(self.commit_count(), before + 1)

        # And it actually reached origin, rather than sitting local like the
        # DEC-285 bug this job's push path was written to avoid.
        self.assertEqual(
            git(self.repo, "rev-parse", "HEAD").stdout,
            git(self.repo, "rev-parse", "origin/main").stdout,
        )

    def test_hand_written_readme_survives(self):
        self.stage()
        self.run_script()
        self.assertEqual((self.infra / "README.md").read_text(), "hand-written, must survive\n")

    def test_drift_is_reported_to_a_person(self):
        self.stage()
        self.run_script()
        self.assertTrue(self.alerts(), "a config change must email, not only log")

    def test_unchanged_config_is_a_silent_no_op(self):
        self.stage()
        self.run_script()
        after_first = self.commit_count()
        alerts_after_first = len(self.alerts())

        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commit_count(), after_first, "second run must not commit")
        self.assertEqual(len(self.alerts()), alerts_after_first, "second run must not email")
        self.assertEqual(git(self.repo, "status", "--porcelain").stdout, "")


class SecretGate(SnapshotHarness):
    """The property the whole job hangs on: it fails closed."""

    def test_literal_secret_blocks_the_run(self):
        self.stage(compose=LEAKY_COMPOSE)
        before = self.commit_count()

        result = self.run_script()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.commit_count(), before, "must not commit a captured secret")

    def test_literal_secret_writes_nothing_into_the_working_tree(self):
        self.stage(compose=LEAKY_COMPOSE)
        self.run_script()

        self.assertFalse(
            (self.infra / "plausible" / "docker-compose.yml").exists(),
            "the leaked file must not be written into the repo at all",
        )
        self.assertFalse(
            (self.infra / "crontab.txt").exists(),
            "a finding in one file must abort the whole capture, not just skip that file",
        )
        self.assertEqual(git(self.repo, "status", "--porcelain").stdout, "")

    def test_block_alerts_without_leaking_the_value(self):
        self.stage(compose=LEAKY_COMPOSE)
        self.run_script()

        alerts = self.alerts()
        self.assertTrue(alerts, "a blocked snapshot must reach a person")
        body = "\n".join(alerts)
        self.assertIn("POSTGRES_PASSWORD", body)
        self.assertNotIn("hunter2literal", body, "the alert must not repeat the credential")

    def test_block_does_not_leak_the_value_into_the_log(self):
        self.stage(compose=LEAKY_COMPOSE)
        self.run_script()
        self.assertNotIn("hunter2literal", self.log.read_text())

    def test_empty_capture_is_refused(self):
        # An empty capture is indistinguishable from "the server has no config",
        # which would otherwise commit a deletion of everything we track.
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.alerts())


class CheckMode(SnapshotHarness):
    def test_reports_drift_and_writes_nothing(self):
        self.stage()
        before = self.commit_count()

        result = self.run_script("--check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("DRIFT: crontab.txt", result.stdout)
        self.assertEqual(self.commit_count(), before)
        self.assertFalse((self.infra / "crontab.txt").exists())
        self.assertEqual(git(self.repo, "status", "--porcelain").stdout, "")

    def test_reports_clean_after_a_snapshot(self):
        self.stage()
        self.run_script()

        result = self.run_script("--check")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("clean", result.stdout)

    def test_rejects_an_unknown_argument(self):
        self.stage()
        result = self.run_script("--wat")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
