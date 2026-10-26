"""
The homepage's script URLs change exactly when the scripts do.

build-dashboard.py used to version /dashboard.js and /data.js with ?v=YYYYMMDD.
A second deploy on the same day kept the same URL, so a browser that had loaded
the page earlier that day kept running the old script until the next day's
build. On 2026-10-26 the multi-word search fix was live on the server and on
Cloudflare and still absent in Chrome. Each ?v= is now a hash of the file it
names.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from golden_runner import FIXTURE_DATA, FIXTURE_DAY, FIXTURE_OVERRIDES, SCRAPERS  # noqa: E402

DASHBOARD_JS = SCRAPERS / "static" / "dashboard.js"


def _sha10(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:10]


class ScriptVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        env = dict(os.environ, TREESTOCK_TODAY=FIXTURE_DAY,
                   TREESTOCK_VARIETY_OVERRIDES=str(FIXTURE_OVERRIDES))
        # Exit code ignored for the same reason as golden_runner: production
        # size guards reject the small fixture after the files are written.
        subprocess.run(
            [sys.executable, str(SCRAPERS / "build-dashboard.py"),
             str(FIXTURE_DATA), str(cls.out), "--today", FIXTURE_DAY],
            capture_output=True, text=True, cwd=str(SCRAPERS), env=env)
        cls.html = (cls.out / "index.html").read_text()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def version_of(self, path):
        m = re.search(r'<script src="' + re.escape(path) + r'\?v=([^"]+)"', self.html)
        self.assertIsNotNone(m, f"no versioned <script> for {path}")
        return m.group(1)

    def test_dashboard_js_is_versioned_by_its_content(self):
        self.assertEqual(self.version_of("/dashboard.js"),
                         _sha10(DASHBOARD_JS.read_bytes()))

    def test_data_js_is_versioned_by_its_content(self):
        self.assertEqual(self.version_of("/data.js"),
                         _sha10((self.out / "data.js").read_bytes()))

    def test_neither_version_is_a_date(self):
        for path in ("/dashboard.js", "/data.js"):
            with self.subTest(path=path):
                self.assertNotRegex(self.version_of(path), r"^\d{8}$")


if __name__ == "__main__":
    unittest.main()
