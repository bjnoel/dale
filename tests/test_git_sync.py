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
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools" / "autonomous"
GIT_SYNC = TOOLS / "git_sync.sh"
UPTIME_MONITOR = TOOLS / "uptime_monitor.py"

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

    def test_pull_fast_forwards_when_purely_behind(self):
        """The commonest case of all, and the one that went untested.

        Benedict pushes from the laptop; the server holds nothing of its own and
        is strictly behind. Skipping the pull here and returning 0 is worse than
        returning non-zero, because nothing downstream can tell the difference:
        deploy.sh finds the same commit it deployed last hour and reports
        success, hourly, indefinitely. That ran from 2026-08-16 until it was
        found by hand a day later.
        """
        commit_file(self.laptop, "laptop.txt", "laptop\n", "laptop work")
        git(self.laptop, "push", "-q", "origin", "main")

        before = git(self.server, "rev-parse", "HEAD").stdout.strip()

        rc, rebased = call_git_sync(self.server, "git_sync_pull")

        self.assertEqual(rc, 0)
        self.assertFalse(rebased, "a fast-forward is not a rebase")
        after = git(self.server, "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(before, after, "HEAD did not move: the pull was skipped")
        self.assertIn("laptop work", git(self.server, "log", "--format=%s").stdout)
        self.assertNoRebaseInProgress(self.server)

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

    def test_pull_survives_a_concurrent_fetch(self):
        """The 2026-08-17 halt (DEC-299). Fails 20/20 against `git pull`.

        uptime_monitor.py fetches this repo every five minutes, so one of its
        fetches lands on :00 next to the session pull. A fetch truncates
        .git/FETCH_HEAD on start and appends when refs arrive; a second fetch
        starting inside that window leaves two "for-merge" lines behind, and
        `git pull --ff-only` reads the file and dies with "Cannot fast-forward
        to multiple branches" over a repo that is a clean fast-forward. Three
        of those tripped the breaker and halted Dale entirely.

        Merging origin/main instead of FETCH_HEAD is what makes this pass: a
        remote-tracking ref is never half-written.
        """
        commit_file(self.laptop, "laptop.txt", "laptop\n", "laptop work")
        git(self.laptop, "push", "-q", "origin", "main")
        base = git(self.server, "rev-parse", "HEAD").stdout.strip()

        racer = subprocess.Popen(
            ["bash", "-c", f'while :; do git -C "{self.server}" fetch -q origin; done'],
            env=GIT_ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            for attempt in range(5):
                git(self.server, "reset", "--hard", "-q", base)
                rc, _ = call_git_sync(self.server, "git_sync_pull")
                self.assertEqual(rc, 0, f"attempt {attempt}: pull lost a race with a fetch")
                self.assertEqual(
                    git(self.server, "rev-parse", "HEAD").stdout.strip(),
                    git(self.server, "rev-parse", "origin/main").stdout.strip(),
                    f"attempt {attempt}: HEAD did not reach origin/main",
                )
        finally:
            os.killpg(os.getpgid(racer.pid), signal.SIGKILL)
            racer.wait()


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


class TestFetchHeadIsLeftAlone(unittest.TestCase):
    """.git/FETCH_HEAD is one file shared by every git process in the repo, and
    the box runs four: the hourly session pull, the :15 inbound merge, the 04:20
    config snapshot, and uptime_monitor.py every five minutes. Reading it is a
    race by construction; writing it is a hazard to whoever is reading. Nothing
    here needs it, so nothing here touches it."""

    @staticmethod
    def code_lines(path):
        return [l for l in path.read_text().splitlines() if not l.strip().startswith("#")]

    def test_git_sync_never_runs_git_pull(self):
        offenders = [l for l in self.code_lines(GIT_SYNC) if "git pull" in l]
        self.assertEqual(
            offenders, [],
            "git pull decides what to merge by reading FETCH_HEAD. Use "
            "`git merge --ff-only origin/main` after an explicit fetch.")

    def test_shared_repo_fetches_do_not_write_fetch_head(self):
        for path in (GIT_SYNC, UPTIME_MONITOR):
            for line in self.code_lines(path):
                if "git fetch" in line or '_git("fetch"' in line:
                    self.assertIn(
                        "--no-write-fetch-head", line,
                        f"{path.name}: this fetch shares a repo with other git "
                        f"processes and must not truncate FETCH_HEAD under them")


if __name__ == "__main__":
    unittest.main()
