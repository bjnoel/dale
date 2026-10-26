"""
Multi-word search on the treestock homepage matches words in any order.

From 2026-06-01 (f1d94af, when the dashboard JS left the Python f-string in
build-dashboard.py) to 2026-10-26, the query was split with /\\s+/. Inside the
f-string that spelling produced /\s+/; copied verbatim into a .js file it is a
regex for a literal backslash then "s", so the query was never split and was
matched as one phrase. Measured on the live catalogue: "mango r2e2" found 1
listing, "r2e2 mango" 4, "genoa black" 0, against 12, 12 and 25 once fixed.

Runs static/dashboard.js under node against a stub DOM (tests/dashboard_harness.js).

Run from repo root with:
    python3 -m unittest discover tests/
"""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_JS = REPO_ROOT / "tools" / "scrapers" / "static" / "dashboard.js"
HARNESS = Path(__file__).resolve().parent / "dashboard_harness.js"
NODE = shutil.which("node")


def _product(title, nk, sl):
    return {"t": title, "n": nk.title(), "nk": nk, "sl": sl, "a": True,
            "p": 39.95, "cat": ""}


DATA = {
    "products": [
        _product("Mango - R2E2", "daleys", "mango"),
        _product("R2E2 Mango Fruit Tree", "fruitopia", "mango"),
        _product("Mango Kensington Pride", "daleys", "mango"),
        _product("Fig 'Black Genoa'", "daleys", "fig"),
    ],
    "nurseries": [
        {"key": "daleys", "name": "Daleys", "st": ["QLD"], "in_stock": 3},
        {"key": "fruitopia", "name": "Fruitopia", "st": ["QLD"], "in_stock": 1},
    ],
    "species_slugs": {
        "mango": {"slug": "mango", "name": "Mango"},
        "fig": {"slug": "fig", "name": "Fig"},
    },
    "hard_to_find": [],
}


@unittest.skipUnless(NODE, "node is not installed")
class WordOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name) / "data.json"
        cls.data.write_text(json.dumps(DATA))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def titles(self, q):
        out = subprocess.run(
            [NODE, str(HARNESS), str(DASHBOARD_JS), "?q=" + quote(q), str(self.data)],
            capture_output=True, text=True, check=True, timeout=30)
        html = json.loads(out.stdout)["html"]
        return set(re.findall(r'font-medium text-sm">([^<]*)', html))

    def test_both_word_orders_find_both_title_orders(self):
        both = {"Mango - R2E2", "R2E2 Mango Fruit Tree"}
        self.assertEqual(self.titles("mango r2e2"), both)
        self.assertEqual(self.titles("r2e2 mango"), both)

    def test_reversed_cultivar_words_still_match(self):
        self.assertEqual(self.titles("genoa black"), {"Fig 'Black Genoa'"})

    def test_every_word_must_match(self):
        self.assertEqual(self.titles("mango kensington"), {"Mango Kensington Pride"})

    def test_extra_spaces_are_not_a_word(self):
        self.assertEqual(self.titles("  r2e2   mango "),
                         {"Mango - R2E2", "R2E2 Mango Fruit Tree"})


class NoFStringEscapesLeftTests(unittest.TestCase):
    """The class of bug, not just the instance: a doubled backslash before a
    letter in a regex literal is an f-string escape that survived the move to
    a real .js file. Two did (the query split and the species-name fallback)."""

    def test_no_regex_literal_has_a_doubled_backslash_escape(self):
        js = DASHBOARD_JS.read_text()
        hits = [line.strip() for line in js.splitlines()
                if re.search(r"/[^/\n]*\\\\[a-zA-Z][^/\n]*/[gimsuy]*", line)]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
