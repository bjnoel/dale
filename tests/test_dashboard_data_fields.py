"""
Every product field in the homepage's data.js is one dashboard.js reads.

data.js is the whole catalogue (9,285 products, 390 KB compressed on
2026-10-26), results cannot render until it arrives, and it changes nightly, so
every returning visitor downloads it again each day. Genus ("g") and native
region ("r") were written onto every product and read by nothing, ~27 KB of
every visit. This keeps the next one out.

If a new field is meant for something other than dashboard.js, it belongs in a
different file, not in the payload every homepage visitor pays for.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
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


class DataFieldTests(unittest.TestCase):
    def test_every_product_field_is_read_by_dashboard_js(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, TREESTOCK_TODAY=FIXTURE_DAY,
                       TREESTOCK_VARIETY_OVERRIDES=str(FIXTURE_OVERRIDES))
            # Exit code ignored: production size guards reject the small
            # fixture after the files are written (see golden_runner).
            subprocess.run(
                [sys.executable, str(SCRAPERS / "build-dashboard.py"),
                 str(FIXTURE_DATA), tmp, "--today", FIXTURE_DAY],
                capture_output=True, text=True, cwd=str(SCRAPERS), env=env)
            data_js = (Path(tmp) / "data.js").read_text()

        m = re.fullmatch(r"window\.__DATA=JSON\.parse\((.*)\);", data_js.strip(), re.S)
        self.assertIsNotNone(m, "data.js is not in the expected JSON.parse form")
        products = json.loads(json.loads(m.group(1)))["products"]
        self.assertTrue(products)
        fields = {k for p in products for k in p}

        js = DASHBOARD_JS.read_text()
        unread = sorted(k for k in fields if not re.search(r"\." + re.escape(k) + r"\b", js))
        self.assertEqual(unread, [], "product fields in data.js that dashboard.js never reads")


if __name__ == "__main__":
    unittest.main()
