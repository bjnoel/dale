"""
Tests for tools/scrapers/purge_cloudflare.sh -- the Cloudflare edge-cache purge
run at the end of the nightly regen.

We can't exercise a real purge here (needs network + a live token); that's
verified by running the script on the server after deploy. What we pin is the
safety contract: a missing or incomplete secret must NEVER break the build --
the script skips and exits 0.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "scrapers" / "purge_cloudflare.sh"


class PurgeCloudflareTest(unittest.TestCase):
    def _run(self, secret_path):
        env = dict(os.environ, CLOUDFLARE_ENV=str(secret_path))
        return subprocess.run(["bash", str(SCRIPT)], env=env,
                              capture_output=True, text=True, timeout=30)

    def test_script_exists(self):
        self.assertTrue(SCRIPT.exists(), f"{SCRIPT} missing")

    def test_syntax_valid(self):
        r = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_secret_skips_gracefully(self):
        r = self._run("/nonexistent/cloudflare.env")
        self.assertEqual(r.returncode, 0)
        self.assertIn("skipping", (r.stderr + r.stdout).lower())

    def test_incomplete_secret_skips_gracefully(self):
        # Zone id present but no API token -> must skip, not error.
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("CLOUDFLARE_ZONE_ID_TREESTOCK=abc123\n")
            path = f.name
        try:
            r = self._run(path)
            self.assertEqual(r.returncode, 0)
            self.assertIn("skipping", (r.stderr + r.stdout).lower())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
