"""
data.js.br and data.js.gz always hold exactly the data.js beside them.

Caddy serves the homepage dataset with `file_server { precompressed br gzip }`,
so it sends data.js.br in place of data.js whenever that file exists. A sidecar
left over from an earlier build would serve old stock under the new data.js's
URL, and nothing on the page would look wrong. build-dashboard.py removes the
old sidecars before it replaces data.js, then writes new ones from it.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import gzip
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from golden_runner import FIXTURE_DATA, FIXTURE_DAY, FIXTURE_OVERRIDES, SCRAPERS  # noqa: E402

BROTLI = shutil.which("brotli")


def _build(out: Path, path_env: str | None = None) -> None:
    env = dict(os.environ, TREESTOCK_TODAY=FIXTURE_DAY,
               TREESTOCK_VARIETY_OVERRIDES=str(FIXTURE_OVERRIDES))
    if path_env is not None:
        env["PATH"] = path_env
    # Exit code ignored: production size guards reject the small fixture
    # after the files are written (see golden_runner).
    subprocess.run(
        [sys.executable, str(SCRAPERS / "build-dashboard.py"),
         str(FIXTURE_DATA), str(out), "--today", FIXTURE_DAY],
        capture_output=True, text=True, cwd=str(SCRAPERS), env=env)


class PrecompressedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_gz_holds_exactly_data_js(self):
        _build(self.out)
        self.assertEqual(gzip.decompress((self.out / "data.js.gz").read_bytes()),
                         (self.out / "data.js").read_bytes())

    @unittest.skipUnless(BROTLI, "brotli is not installed")
    def test_br_holds_exactly_data_js(self):
        _build(self.out)
        raw = subprocess.run([BROTLI, "-d", "-c", str(self.out / "data.js.br")],
                             capture_output=True, check=True).stdout
        self.assertEqual(raw, (self.out / "data.js").read_bytes())

    def test_a_stale_br_never_survives_a_rebuild_without_brotli(self):
        """The dangerous case: brotli missing on a later build, yesterday's .br
        still there. It must go, not keep being served."""
        (self.out / "data.js.br").write_bytes(b"yesterday's stock")
        (self.out / "data.js.gz").write_bytes(b"yesterday's stock")
        no_brotli = tempfile.mkdtemp()
        try:
            _build(self.out, path_env=no_brotli)  # nothing on PATH, so no brotli
        finally:
            os.rmdir(no_brotli)
        self.assertFalse((self.out / "data.js.br").exists())
        self.assertEqual(gzip.decompress((self.out / "data.js.gz").read_bytes()),
                         (self.out / "data.js").read_bytes())

    def test_no_temp_files_are_left_behind(self):
        _build(self.out)
        self.assertEqual(sorted(p.name for p in self.out.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
