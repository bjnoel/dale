"""Regression tests for tools/autonomous/git_sync.sh.

These reproduce the 2026-08-13 deadlock directly. The bug was not that a push
failed; pushes fail routinely with three writers. The bug was that a rejected
push was logged and forgotten, and the next session's `git pull --ff-only`
could not resolve the divergence it left behind, so every subsequent run failed
identically until a human intervened.

The first two tests fail against the old behaviour and pass against the new.
The last three pin the safety properties, which matter more than the self-heal:
these functions run unattended, so they must never resolve a content conflict,
never rebase over uncommitted work, and never leave a rebase in progress.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

GIT_SYNC = Path(__file__).resolve().parent.parent / "tools" / "autonomous" / "git_sync.sh"

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, env=GIT_ENV, check=False,
    )


def call_git_sync(repo, func):
    """Source git_sync.sh in `repo` and run `func`. Returns (rc, rebased)."""
    script = (
        f'set -uo pipefail\n'
        f'cd "{repo}"\n'
        f'source "{GIT_SYNC}"\n'
        f'{func} /dev/null\n'
        f'rc=$?\n'
        f'echo "REBASED=$GIT_SYNC_REBASED"\n'
        f'exit $rc\n'
    )
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=GIT_ENV)
    rebased = "REBASED=1" in proc.stdout
    return proc.returncode, rebased


def commit_file(repo, name, content, message):
    (Path(repo) / name).write_text(content)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)


class GitSyncTestCase(unittest.TestCase):
    """Two clones of one origin, standing in for the server and the laptop."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)

        self.origin = root / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)],
                       check=True, env=GIT_ENV)

        self.server = root / "server"
        self.laptop = root / "laptop"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.server)],
                       check=True, env=GIT_ENV)

        commit_file(self.server, "seed.txt", "seed\n", "seed")
        git(self.server, "push", "-q", "origin", "main")

        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.laptop)],
                       check=True, env=GIT_ENV)

    def tearDown(self):
        self.tmp.cleanup()

    def origin_log(self):
        return git(self.origin, "log", "--format=%s", "main").stdout.strip().split("\n")

    def assertNoRebaseInProgress(self, repo):
        """A half-finished rebase is the state that breaks every later run."""
        git_dir = Path(repo) / ".git"
        for leftover in ("rebase-merge", "rebase-apply"):
            self.assertFalse((git_dir / leftover).exists(),
                             f"{leftover} left behind; repo is mid-rebase")


class TestPushSelfHeals(GitSyncTestCase):

    def test_rejected_push_rebases_and_retries(self):
        """The 2026-08-13 deadlock: laptop pushes first, server's push is rejected.

        Old behaviour logged 'will go with the next session' and stranded the
        commit. New behaviour rebases and lands it.
        """
        commit_file(self.laptop, "laptop.txt", "laptop\n", "laptop work")
        git(self.laptop, "push", "-q", "origin", "main")

        commit_file(self.server, "server.txt", "server\n", "server work")

        rc, rebased = call_git_sync(self.server, "git_sync_push")

        self.assertEqual(rc, 0, "push should self-heal")
        self.assertTrue(rebased, "should report that it took a rebase")
        self.assertIn("server work", self.origin_log())
        self.assertIn("laptop work", self.origin_log())
        self.assertNoRebaseInProgress(self.server)

    def test_clean_push_does_not_report_a_rebase(self):
        commit_file(self.server, "server.txt", "server\n", "server work")
        rc, rebased = call_git_sync(self.server, "git_sync_push")
        self.assertEqual(rc, 0)
        self.assertFalse(rebased, "no rebase was needed")
        self.assertIn("server work", self.origin_log())


class TestPullSelfHeals(GitSyncTestCase):

    def test_pull_rebases_own_unpushed_commits(self):
        """`git pull --ff-only` returned 1 here, which is what tripped the breaker."""
        commit_file(self.laptop, "laptop.txt", "laptop\n", "laptop work")
        git(self.laptop, "push", "-q", "origin", "main")

        commit_file(self.server, "server.txt", "server\n", "server work")

        # Confirm the old recovery path really does fail on this state.
        git(self.server, "fetch", "-q", "origin")
        old = git(self.server, "pull", "--ff-only", "origin", "main")
        self.assertNotEqual(old.returncode, 0, "precondition: --ff-only must fail here")

        rc, rebased = call_git_sync(self.server, "git_sync_pull")

        self.assertEqual(rc, 0, "pull should rebase its own work")
        self.assertTrue(rebased)
        self.assertNoRebaseInProgress(self.server)
        subjects = git(self.server, "log", "--format=%s").stdout.split("\n")
        self.assertIn("server work", subjects)
        self.assertIn("laptop work", subjects)

    def test_pull_is_a_noop_when_already_current(self):
        rc, rebased = call_git_sync(self.server, "git_sync_pull")
        self.assertEqual(rc, 0)
        self.assertFalse(rebased)


class TestSafetyProperties(GitSyncTestCase):

    def test_content_conflict_aborts_and_reports(self):
        """Never auto-resolve. Both sides append to the same file, as the
        decision log does every session."""
        commit_file(self.laptop, "shared.txt", "laptop line\n", "laptop edit")
        git(self.laptop, "push", "-q", "origin", "main")

        commit_file(self.server, "shared.txt", "server line\n", "server edit")

        rc, _ = call_git_sync(self.server, "git_sync_push")

        self.assertEqual(rc, 3, "a real conflict must return 3, not merge blindly")
        self.assertNoRebaseInProgress(self.server)
        self.assertNotIn("server edit", self.origin_log())
        # The commit must survive locally for a human to deal with.
        self.assertIn("server edit", git(self.server, "log", "--format=%s").stdout)

    def test_dirty_tree_is_refused(self):
        commit_file(self.laptop, "laptop.txt", "laptop\n", "laptop work")
        git(self.laptop, "push", "-q", "origin", "main")

        commit_file(self.server, "server.txt", "server\n", "server work")
        (Path(self.server) / "uncommitted.txt").write_text("do not lose me\n")
        git(self.server, "add", "uncommitted.txt")

        rc, _ = call_git_sync(self.server, "git_sync_push")

        self.assertEqual(rc, 1, "must refuse to rebase over uncommitted work")
        self.assertNoRebaseInProgress(self.server)
        self.assertTrue((Path(self.server) / "uncommitted.txt").exists())

    def test_pull_refuses_dirty_tree(self):
        commit_file(self.laptop, "laptop.txt", "laptop\n", "laptop work")
        git(self.laptop, "push", "-q", "origin", "main")

        commit_file(self.server, "server.txt", "server\n", "server work")
        (Path(self.server) / "uncommitted.txt").write_text("do not lose me\n")
        git(self.server, "add", "uncommitted.txt")

        rc, _ = call_git_sync(self.server, "git_sync_pull")

        self.assertEqual(rc, 1)
        self.assertNoRebaseInProgress(self.server)
        self.assertTrue((Path(self.server) / "uncommitted.txt").exists())


if __name__ == "__main__":
    unittest.main()
