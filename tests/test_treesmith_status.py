"""
Tests for the Treesmith read-only mirror manifest (DAL-179).

Autonomous Dale used to have zero visibility into Benedict's Treesmith repos,
which is how DAL-174 and DAL-175 came to ask for RevenueCat and paywall code
that had already shipped. tools/autonomous/refresh_treesmith_status.py pulls
two read-only mirrors and writes a manifest that session-prompt.py renders.

The properties worth locking down:
  - A missing or unpullable mirror degrades to a recorded warning, never a
    crash. The session must still run.
  - The rendered prompt block stays compact. The whole point of a local mirror
    is that Dale reads files on demand rather than paying for them in every
    prompt, so a regression that dumps SPEC.md into the prompt should fail.
  - The block always tells the session the mirror is read-only.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"
sys.path.insert(0, str(AUTONOMOUS))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, AUTONOMOUS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


refresh = _load("refresh_treesmith_status", "refresh_treesmith_status.py")
session_prompt = _load("session_prompt", "session-prompt.py")


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_repo(path):
    """A local git repo with no remote, so pull --ff-only fails like an outage."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--quiet", "-b", "main")
    (path / "README.md").write_text("mirror fixture\n")
    _git(path, "add", "README.md")
    _git(path, "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--quiet", "-m", "fixture commit")
    return path


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self._saved_mirrors = dict(refresh.MIRRORS)
        self.addCleanup(lambda: refresh.MIRRORS.update(self._saved_mirrors))

    def _build(self, app_path, web_path, live=None):
        refresh.MIRRORS.clear()
        refresh.MIRRORS.update({"app": str(app_path), "web": str(web_path)})
        # Never let the unit tests reach out to Apple.
        saved = refresh.fetch_live_ios
        refresh.fetch_live_ios = lambda *a, **k: (live or {})
        try:
            return refresh.build_manifest()
        finally:
            refresh.fetch_live_ios = saved

    def test_missing_mirror_records_an_error_instead_of_raising(self):
        manifest = self._build(self.root / "nope-app", self.root / "nope-web")
        for key in ("app", "web"):
            self.assertIn("error", manifest["repos"][key])
            self.assertIn("DAL-179", manifest["repos"][key]["error"])

    def test_failed_pull_marks_stale_but_still_reports_head(self):
        app = _make_repo(self.root / "app")
        web = _make_repo(self.root / "web")
        manifest = self._build(app, web)

        entry = manifest["repos"]["app"]
        # No remote configured, so the pull cannot succeed.
        self.assertTrue(entry["stale"])
        self.assertNotIn("error", entry)
        # Staleness must not cost us the commit info: that is what tells a
        # session how far behind the mirror is.
        self.assertEqual(entry["commit_subject"], "fixture commit")
        self.assertTrue(entry["commit"])

    def test_app_details_parse_version_features_and_top_level_deps_only(self):
        app = _make_repo(self.root / "app")
        (app / "pubspec.yaml").write_text(
            "name: treesmith\n"
            "version: 1.0.9+55\n"
            "dependencies:\n"
            "  flutter:\n"
            "    sdk: flutter\n"
            "  purchases_flutter: ^10.6.0\n"
            "  sqflite: ^2.4.2\n"
            "dev_dependencies:\n"
            "  flutter_test:\n"
            "    sdk: flutter\n"
        )
        (app / "lib" / "features" / "pro").mkdir(parents=True)
        (app / "lib" / "features" / "plants").mkdir(parents=True)
        (app / ".last_released_build").write_text("52\n")

        details = refresh.app_details(str(app))
        self.assertEqual(details["version"], "1.0.9+55")
        self.assertEqual(details["features"], ["plants", "pro"])
        self.assertEqual(details["last_released_build"], "52")
        self.assertEqual(details["dependencies"], ["purchases_flutter", "sqflite"])
        # Nested keys are not packages, and dev_dependencies are out of scope.
        for leaked in ("sdk", "flutter", "flutter_test"):
            self.assertNotIn(leaked, details["dependencies"])

    def test_web_details_list_pages_recursively(self):
        web = _make_repo(self.root / "web")
        pages = web / "src" / "pages"
        (pages / "journal").mkdir(parents=True)
        (pages / "index.astro").write_text("")
        (pages / "features.astro").write_text("")
        (pages / "journal" / "index.astro").write_text("")
        (web / "src" / "content" / "journal").mkdir(parents=True)
        (web / "src" / "content" / "journal" / "one.md").write_text("")

        details = refresh.web_details(str(web))
        self.assertEqual(
            details["pages"],
            ["features.astro", "index.astro", "journal/index.astro"],
        )
        self.assertEqual(details["journal_entries"], ["one.md"])


class LiveStoreTests(unittest.TestCase):
    """The repo cannot tell you what the store serves.

    `.last_released_build` is stamped by the deploy script, so a build that is
    in review, TestFlight-only or pulled still bumps it. On 2026-08-12 the
    manifest said "1.0.10+59 (last released build 59)" while both storefronts
    served 1.0.9, and the session prompt carried that into the session as
    though the staged DEC-274 store-copy corrections were live. They were not.
    """

    def test_release_gap_names_the_storefronts_that_are_behind(self):
        gap = refresh.release_gap("1.0.10+59", {
            "au": {"version": "1.0.9"},
            "us": {"version": "1.0.9"},
        })
        self.assertIsNotNone(gap)
        self.assertIn("1.0.10", gap)
        self.assertIn("1.0.9", gap)
        self.assertIn("AU", gap)
        self.assertIn("US", gap)
        self.assertIn("NOT live", gap)

    def test_release_gap_is_silent_once_the_build_actually_ships(self):
        self.assertIsNone(refresh.release_gap("1.0.10+59", {
            "au": {"version": "1.0.10"},
            "us": {"version": "1.0.10"},
        }))

    def test_a_failed_lookup_is_not_mistaken_for_agreement(self):
        # An unreachable store must not silently read as "in sync". If we
        # cannot see one storefront we can still report on the other.
        gap = refresh.release_gap("1.0.10+59", {
            "au": {"error": "lookup failed: URLError"},
            "us": {"version": "1.0.9"},
        })
        self.assertIn("US", gap)
        self.assertNotIn("AU", gap)

    def test_lookup_failure_degrades_to_a_recorded_error(self):
        def boom(*_a, **_k):
            raise TimeoutError("no network")

        saved = refresh.urllib.request.urlopen
        refresh.urllib.request.urlopen = boom
        try:
            live = refresh.fetch_live_ios(timeout=1)
        finally:
            refresh.urllib.request.urlopen = saved
        for country in refresh.STORE_COUNTRIES:
            self.assertIn("error", live[country])
        self.assertIn("checked_at", live)


class PromptBlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _write(self, manifest):
        (self.data / "treesmith-status.json").write_text(json.dumps(manifest))
        return session_prompt.get_treesmith_status(str(self.data))

    def test_absent_manifest_points_at_the_refresh_script(self):
        block = session_prompt.get_treesmith_status(str(self.data))
        self.assertIn("refresh_treesmith_status.py", block)
        self.assertIn("DAL-179", block)

    def test_block_states_read_only_and_names_both_paths(self):
        block = self._write({
            "generated_at": "2026-07-30T04:00:00+00:00",
            "repos": {
                "app": {
                    "path": "/opt/dale/treesmith-app",
                    "commit": "abc1234",
                    "commit_date": "2026-07-30T10:25:00+08:00",
                    "commit_subject": "Rebuild releases",
                    "version": "1.0.9+55",
                    "last_released_build": "52",
                    "features": ["plants", "pro"],
                    "dependencies": ["purchases_flutter"] * 40,
                    "docs": ["SPEC.md"] * 20,
                },
                "web": {
                    "path": "/opt/dale/treesmith-web",
                    "commit": "def5678",
                    "commit_date": "2026-07-27T13:03:54+08:00",
                    "commit_subject": "Correct guidance",
                    "pages": ["index.astro", "features.astro"],
                },
            },
        })
        self.assertIn("READ-ONLY", block)
        self.assertIn("/opt/dale/treesmith-app", block)
        self.assertIn("/opt/dale/treesmith-web", block)
        self.assertIn("1.0.9+55", block)
        self.assertIn("plants, pro", block)

    def test_block_stays_compact(self):
        # A local mirror exists so sessions can read files on demand. If this
        # block starts inlining file contents, the mirror has stopped paying
        # for itself and every session prompt gets more expensive.
        block = self._write({
            "generated_at": "2026-07-30T04:00:00+00:00",
            "repos": {
                "app": {
                    "path": "/opt/dale/treesmith-app",
                    "commit": "abc1234",
                    "commit_date": "2026-07-30T10:25:00+08:00",
                    "commit_subject": "x",
                    "version": "1.0.9+55",
                    "features": [f"feature{i}" for i in range(9)],
                    "dependencies": [f"pkg{i}" for i in range(40)],
                    "docs": [f"docs/{i}.md" for i in range(15)],
                },
                "web": {
                    "path": "/opt/dale/treesmith-web",
                    "commit": "def5678",
                    "commit_date": "2026-07-27T13:03:54+08:00",
                    "commit_subject": "y",
                    "pages": [f"page{i}.astro" for i in range(11)],
                    "journal_entries": [f"{i}.md" for i in range(3)],
                },
            },
        })
        self.assertLessEqual(len(block.splitlines()), 25)
        self.assertLessEqual(len(block), 2000)

    def test_stale_mirror_is_flagged_in_the_prompt(self):
        block = self._write({
            "generated_at": "2026-07-30T04:00:00+00:00",
            "repos": {
                "app": {
                    "path": "/opt/dale/treesmith-app",
                    "stale": True,
                    "commit": "abc1234",
                    "commit_date": "2026-07-20T00:00:00+08:00",
                    "commit_subject": "x",
                },
            },
        })
        self.assertIn("STALE", block)

    def test_prompt_says_what_the_store_serves_and_flags_an_unshipped_build(self):
        block = self._write({
            "generated_at": "2026-08-12T00:21:49+00:00",
            "repos": {
                "app": {
                    "path": "/opt/dale/treesmith-app",
                    "commit": "f20a064",
                    "commit_date": "2026-08-10T10:43:44+00:00",
                    "commit_subject": "Auto-update CI goldens",
                    "version": "1.0.10+59",
                    "last_released_build": "59",
                },
            },
            "live_store": {
                "ios": {
                    "au": {"version": "1.0.9", "name": "TreeSmith: Plant Graft "
                           "Tracker", "released": "2026-07-28", "ratings": 0},
                    "us": {"version": "1.0.9", "name": "TreeSmith",
                           "released": "2026-07-28", "ratings": 0},
                },
                "unreleased": "repo is at 1.0.10 but the App Store serves "
                              "1.0.9 on AU, US: 1.0.10 is NOT live",
            },
        })
        # The repo markers must not read as store facts.
        self.assertIn("NOT the store", block)
        # The store version has to be present and attributed to the store.
        self.assertIn("LIVE ON THE APP STORE", block)
        self.assertIn("1.0.9", block)
        self.assertIn("NOT live", block)
        # The two names differing is how a session sees en-US is still live.
        self.assertIn("TreeSmith: Plant Graft Tracker", block)

    def test_unreachable_store_reads_as_unknown_not_as_agreement(self):
        block = self._write({
            "generated_at": "2026-08-12T00:21:49+00:00",
            "repos": {"app": {"path": "/opt/dale/treesmith-app",
                              "commit": "f20a064", "commit_date": "2026-08-10",
                              "commit_subject": "x", "version": "1.0.10+59"}},
            "live_store": {"ios": {"au": {"error": "lookup failed: URLError"}}},
        })
        self.assertIn("unknown", block)
        self.assertIn("lookup failed", block)

    def test_missing_mirror_surfaces_the_error_in_the_prompt(self):
        block = self._write({
            "generated_at": "2026-07-30T04:00:00+00:00",
            "repos": {
                "app": {"path": "/opt/dale/treesmith-app", "error": "mirror missing"},
            },
        })
        self.assertIn("mirror missing", block)


class DeployedMirrorTests(unittest.TestCase):
    """Guards on the live mirrors. Skipped anywhere they are not cloned."""

    MIRRORS = ("/opt/dale/treesmith-app", "/opt/dale/treesmith-web")

    def test_push_is_disabled_on_every_mirror(self):
        for path in self.MIRRORS:
            if not Path(path, ".git").is_dir():
                self.skipTest(f"{path} not cloned on this machine")
            result = subprocess.run(
                ["git", "-C", path, "remote", "get-url", "--push", "origin"],
                capture_output=True, text=True,
            )
            self.assertIn("DISABLED", result.stdout,
                          f"{path} has a live push URL: Dale must not be able "
                          f"to push to Benedict's Treesmith repos")
            hook = Path(path, ".git", "hooks", "pre-push")
            self.assertTrue(hook.is_file(), f"{path} is missing its pre-push guard")


if __name__ == "__main__":
    unittest.main()
