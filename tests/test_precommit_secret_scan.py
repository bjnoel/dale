"""Guards for the pre-commit secret gate.

The scanner itself is `config_scan.py` and is tested by tests/test_config_scan.py.
What is tested here is the thing that was actually missing: that it runs over
STAGED content at commit time, in the one place the accident happens.

The accident, twice with the same file: `git add -A` in a directory somebody else
is also working in sweeps an untracked script into an unrelated commit. The first
time a human caught it in review. The second time nothing local caught it and a
live Shopify token reached GitHub, where push protection refused the push.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "tools" / "autonomous" / "precommit_secret_scan.py"
)
spec = importlib.util.spec_from_file_location("precommit_secret_scan", MODULE_PATH)
ps = importlib.util.module_from_spec(spec)
sys.modules["precommit_secret_scan"] = ps
spec.loader.exec_module(ps)

REPO = MODULE_PATH.resolve().parents[2]

# A token-shaped string that is not a real credential.
FAKE = "shpat_" + "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


class TestScanStaged(unittest.TestCase):
    """Driven through a real git repo, because the staged/working distinction
    is the whole point and cannot be faked with strings."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", self.repo, *args],
                              capture_output=True, text=True, check=True)

    def write(self, name, text):
        path = os.path.join(self.repo, name)
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(name) else None
        Path(path).write_text(text, encoding="utf-8")
        return name

    def scan(self, paths=None):
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            return ps.scan_staged(paths)
        finally:
            os.chdir(cwd)

    def test_the_exact_line_that_got_through_is_blocked(self):
        self.write("upload.py",
                   f'TOKEN = os.environ.get("SHOPIFY_ADMIN_API", "{FAKE}")\n')
        self.git("add", "upload.py")
        findings = self.scan()
        self.assertTrue(findings)
        self.assertEqual(findings[0].source, "upload.py")

    def test_a_swept_up_untracked_file_is_caught_by_add_dash_A(self):
        # The real shape of the accident: the file has nothing to do with the
        # commit and gets in because the add was broad.
        self.write("intended.py", "x = 1\n")
        self.write("swept.py", f'SHOPIFY_TOKEN = "{FAKE}"\n')
        self.git("add", "-A")
        sources = {f.source for f in self.scan()}
        self.assertIn("swept.py", sources)
        self.assertNotIn("intended.py", sources)

    def test_ordinary_code_commits_freely(self):
        # A gate that cries wolf gets switched off within a month.
        self.write("ok.py", "\n".join([
            "import os",
            'TOKEN = os.environ.get("SHOPIFY_ADMIN_API")',
            'API = f"https://{SHOP}/admin/api/2024-01"',
            "# the token is read at runtime, never inlined",
            'EnvironmentFile=/opt/dale/secrets/lodgify.env',
        ]) + "\n")
        self.git("add", "ok.py")
        self.assertEqual(self.scan(), [])

    def test_it_reads_the_staged_bytes_not_the_working_file(self):
        # Stage the secret, then clean the working copy. A scanner reading the
        # working tree sees nothing while the commit still publishes the token.
        self.write("late.py", f'SHOPIFY_TOKEN = "{FAKE}"\n')
        self.git("add", "late.py")
        self.write("late.py", 'SHOPIFY_TOKEN = os.environ["SHOPIFY_TOKEN"]\n')
        self.assertTrue(self.scan(), "scanned the working file instead of the index")

    def test_unstaged_files_are_not_scanned(self):
        self.write("untouched.py", f'SHOPIFY_TOKEN = "{FAKE}"\n')
        self.assertEqual(self.scan(), [])

    def test_binary_and_vendored_paths_are_skipped(self):
        self.write("logo.png", f'SHOPIFY_TOKEN = "{FAKE}"\n')
        self.git("add", "logo.png")
        self.assertEqual(self.scan(), [])


class TestTheReportItPrints(unittest.TestCase):
    """The blocking path must produce a message, not a traceback.

    Learned the hard way: the first version of main() referenced a field the
    Finding class does not have. The commit was still blocked, because a
    crashing hook exits non-zero -- but it blocked with a stack trace, which
    reads as "the hook is broken" and is exactly how a gate ends up bypassed
    with --no-verify. Asserting on findings alone never rendered them.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = self._tmp.name
        for args in (("init", "-q"), ("config", "user.email", "t@example.com"),
                     ("config", "user.name", "T")):
            subprocess.run(["git", "-C", self.repo, *args], check=True,
                           capture_output=True)
        Path(os.path.join(self.repo, "leak.py")).write_text(
            f'SHOPIFY_TOKEN = "{FAKE}"\n', encoding="utf-8")
        subprocess.run(["git", "-C", self.repo, "add", "leak.py"], check=True,
                       capture_output=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_main(self):
        import contextlib, io
        err, cwd = io.StringIO(), os.getcwd()
        os.chdir(self.repo)
        try:
            with contextlib.redirect_stderr(err):
                code = ps.main()
        finally:
            os.chdir(cwd)
        return code, err.getvalue()

    def test_it_exits_non_zero_and_names_the_file_and_line(self):
        code, err = self._run_main()
        self.assertEqual(code, 1)
        self.assertIn("leak.py:1", err)
        self.assertIn("COMMIT BLOCKED", err)

    def test_it_never_prints_the_credential_itself(self):
        # A hook that echoes the secret into a terminal, a CI log or a scrollback
        # has published it a second time.
        _, err = self._run_main()
        self.assertNotIn(FAKE, err)
        self.assertNotIn(FAKE[6:], err)

    def test_it_says_how_to_resolve(self):
        _, err = self._run_main()
        self.assertIn(".env", err)
        self.assertIn("--no-verify", err)

    def test_a_clean_index_exits_zero_and_says_nothing(self):
        subprocess.run(["git", "-C", self.repo, "reset", "-q"], check=True)
        Path(os.path.join(self.repo, "ok.py")).write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", self.repo, "add", "ok.py"], check=True,
                       capture_output=True)
        code, err = self._run_main()
        self.assertEqual(code, 0)
        self.assertEqual(err, "")


class TestWiring(unittest.TestCase):
    """The hook is only a gate if it is actually installed and executable."""

    def test_the_hook_exists_and_is_executable(self):
        hook = REPO / ".githooks" / "pre-commit"
        self.assertTrue(hook.exists(), "no .githooks/pre-commit")
        self.assertTrue(os.access(hook, os.X_OK), "hook is not executable")

    def test_the_hook_invokes_this_scanner(self):
        body = (REPO / ".githooks" / "pre-commit").read_text(encoding="utf-8")
        self.assertIn("precommit_secret_scan.py", body)

    def test_the_scanner_is_not_a_second_implementation(self):
        # config_scan.py is the single definition site for what a secret looks
        # like. A copy here would drift from the snapshot gate it shares a job
        # with, exactly the failure tests/test_no_forking.py exists to prevent.
        src = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("from config_scan import scan_text", src)
        for own in ("AKIA", "shpat_", "-----BEGIN"):
            self.assertNotIn(own, src.split('"""', 2)[-1],
                             f"{own} pattern restated here; import it instead")

    def test_the_allowlist_stays_small(self):
        # Every entry is a hole. A growing list means the scanner is
        # miscalibrated, not that the exceptions are real.
        self.assertLessEqual(len(ps.ALLOWLIST), 4)


if __name__ == "__main__":
    unittest.main()
