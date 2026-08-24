"""Search Console auth: service account only, and no quota-project header.

Both facts are load-bearing and both fail quietly if they regress.

The personal OAuth token was Benedict's own Google credential, reaching all 13
properties on his account including three with nothing to do with Dale. Every
live script moved to the service account on 2026-08-24 so the token could be
revoked. A script that reaches for the file again works fine until he revokes
it, then fails on a Sunday cron nobody is watching.

The x-goog-user-project header is the trap in the other direction. The OAuth
path required it; a service-account token sent with it gets a 403 that reads
like a Search Console permissions problem and is actually a serviceusage IAM
one, which sends you off granting roles that were never needed.
"""

import ast
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"

import sys
sys.path.insert(0, str(SCRAPERS))
from stocklib import gsc_auth  # noqa: E402


def live_python_files():
    """Every script that actually runs. bee/ is frozen with beestock (DEC-230)."""
    files = sorted(SCRAPERS.glob("*.py"))
    files += sorted((SCRAPERS / "stocklib").glob("*.py"))
    files += sorted(AUTONOMOUS.glob("*.py"))
    return files


def executable_source(path):
    """Source with docstrings and comments removed.

    Both guards below look for a literal string, and gsc_auth.py's own docstring
    explains why that string is forbidden. Matching on prose would make the
    documentation fail the test it documents, and the obvious fix, deleting the
    explanation, is the worst outcome available. Comments go too, via unparse.
    """
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


class NoPersonalTokenTest(unittest.TestCase):
    def test_no_live_script_reads_the_personal_oauth_token(self):
        offenders = [
            f.relative_to(REPO_ROOT)
            for f in live_python_files()
            if "gsc-oauth-credentials" in executable_source(f)
        ]
        self.assertEqual(
            offenders, [],
            "These read Benedict's personal Google token. Use "
            "stocklib.gsc_auth.gsc_credentials() instead, or the file breaks "
            "the moment he revokes it: " + ", ".join(str(o) for o in offenders),
        )

    def test_no_live_script_sends_the_quota_project_header(self):
        offenders = [
            f.relative_to(REPO_ROOT)
            for f in live_python_files()
            if "x-goog-user-project" in executable_source(f)
        ]
        self.assertEqual(
            offenders, [],
            "A service-account token sent with x-goog-user-project 403s with a "
            "serviceusage error that looks like a GSC permissions failure: "
            + ", ".join(str(o) for o in offenders),
        )


class ScopeTest(unittest.TestCase):
    def _load_with(self, **kwargs):
        with mock.patch.object(
            gsc_auth.service_account.Credentials, "from_service_account_file"
        ) as loader:
            loader.return_value = mock.Mock()
            gsc_auth.gsc_credentials(**kwargs)
            return loader.call_args

    def test_defaults_to_readonly(self):
        """Inspection and analytics need no write scope (verified live 2026-08-24)."""
        _, kwargs = self._load_with()
        self.assertEqual(kwargs["scopes"], [gsc_auth.READONLY_SCOPE])

    def test_write_is_opt_in(self):
        _, kwargs = self._load_with(write=True)
        self.assertEqual(kwargs["scopes"], [gsc_auth.WRITE_SCOPE])

    def test_credentials_are_refreshed_before_use(self):
        """An unrefreshed service-account credential has creds.token None."""
        with mock.patch.object(
            gsc_auth.service_account.Credentials, "from_service_account_file"
        ) as loader:
            creds = mock.Mock()
            loader.return_value = creds
            gsc_auth.gsc_credentials()
            creds.refresh.assert_called_once()


class HeaderTest(unittest.TestCase):
    def test_auth_headers_carry_the_token_and_nothing_else(self):
        creds = mock.Mock(token="tok123")
        self.assertEqual(gsc_auth.auth_headers(creds), {"Authorization": "Bearer tok123"})

    def test_extra_headers_merge_without_reintroducing_the_quota_project(self):
        creds = mock.Mock(token="tok123")
        headers = gsc_auth.auth_headers(creds, {"Content-Type": "application/json"})
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertNotIn("x-goog-user-project", headers)


class CallSiteTest(unittest.TestCase):
    """The migrated scripts must not have kept a private credential builder."""

    def test_migrated_scripts_import_the_shared_helper(self):
        for name in ("gsc_analysis.py", "gsc_submit.py"):
            src = (SCRAPERS / name).read_text()
            self.assertIn("from stocklib.gsc_auth import", src, f"{name} lost the import")

    def test_migrated_scripts_parse_and_define_no_local_credential_builder(self):
        for name in ("gsc_analysis.py", "gsc_submit.py"):
            tree = ast.parse((SCRAPERS / name).read_text())
            defined = {
                n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
            }
            self.assertNotIn("get_credentials", defined, f"{name} rebuilt its own")
            self.assertNotIn("get_oauth_credentials", defined, f"{name} rebuilt its own")
            self.assertNotIn("make_headers", defined, f"{name} rebuilt its own")


if __name__ == "__main__":
    unittest.main()
