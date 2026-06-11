"""
Tests for the Cloudflare Access team-domain normalisation in subscribe_server.py.

The /admin route accepts CF_ACCESS_TEAM_DOMAIN as either a full URL or a bare
team slug; both must resolve to the same Access domain (used as the JWKS base
and the expected JWT issuer).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


subscribe_server = _load(SCRAPERS / "subscribe_server.py")
_normalize = subscribe_server._normalize_cf_team_domain


class NormalizeTeamDomainTest(unittest.TestCase):
    def test_bare_slug_expands(self):
        self.assertEqual(_normalize("bjn"), "https://bjn.cloudflareaccess.com")

    def test_full_url_unchanged(self):
        self.assertEqual(
            _normalize("https://bjn.cloudflareaccess.com"),
            "https://bjn.cloudflareaccess.com",
        )

    def test_trailing_slash_stripped(self):
        self.assertEqual(
            _normalize("https://bjn.cloudflareaccess.com/"),
            "https://bjn.cloudflareaccess.com",
        )

    def test_whitespace_stripped(self):
        self.assertEqual(_normalize("  bjn  "), "https://bjn.cloudflareaccess.com")

    def test_empty_and_none(self):
        self.assertEqual(_normalize(""), "")
        self.assertEqual(_normalize(None), "")


if __name__ == "__main__":
    unittest.main()
