"""
Anti-drift guardrail: shared logic must live in stocklib/ and be imported, never
re-defined in a builder/scraper. This is what stops the "updated in one place,
not the others" problem from coming back (NON_PLANT_KEYWORDS was once 10 drifted
copies; SHIPPING_MAP/NURSERY_NAMES were three parallel dicts; the email footer
was two copies).

If this test fails, you copied a shared definition into a module instead of
importing it from stocklib. Move it back to the package.

Scope: top-level tools/scrapers/*.py plus stocklib/*.py. The bee/ subsite still
forks some of this (de-fork pending) and is intentionally not scanned yet.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"


def _scanned_files():
    files = sorted(SCRAPERS.glob("*.py"))            # top-level builders/scrapers/senders
    files += sorted((SCRAPERS / "stocklib").glob("*.py"))
    return files


# (definition regex, the single file allowed to define it). `[:=]` allows an
# optional type annotation (e.g. `SHIPPING_MAP: dict[...] = ...`). Imports start
# with `from`/`import`, so they never match these anchors.
GUARDS = [
    (re.compile(r"^NON_PLANT_KEYWORDS\s*[:=]"), "stocklib/classify.py"),
    (re.compile(r"^def inject_footer\b"), "stocklib/email_footer.py"),
    (re.compile(r"^SHIPPING_MAP\s*[:=]"), "stocklib/registry.py"),
    (re.compile(r"^NURSERY_NAMES\s*[:=]"), "stocklib/registry.py"),
]


class NoForkingTest(unittest.TestCase):
    def test_shared_symbols_are_defined_in_exactly_one_place(self):
        files = _scanned_files()
        self.assertTrue(files, "no files scanned")
        for rx, owner in GUARDS:
            definers = sorted(
                str(f.relative_to(SCRAPERS))
                for f in files
                if any(rx.search(line) for line in f.read_text().splitlines())
            )
            self.assertEqual(
                definers, [owner],
                f"{rx.pattern!r} must be defined only in {owner}, but was found in "
                f"{definers}. Shared logic lives in stocklib/ -- import it, don't copy it.",
            )

    def test_comparison_engine_not_re_forked(self):
        """The stock-change engine (variant_key / compare_snapshots) lives only in
        stocklib.changes; treestock AND beestock import it. Scans bee/ too, since
        that is where it had forked."""
        files = _scanned_files() + sorted((SCRAPERS / "bee").glob("*.py"))

        def definers(pattern):
            rx = re.compile(pattern)
            return sorted(
                str(f.relative_to(SCRAPERS))
                for f in files
                if any(rx.search(line) for line in f.read_text().splitlines())
            )

        self.assertEqual(definers(r"^def variant_key\b"), ["stocklib/changes.py"])
        self.assertEqual(definers(r"^def compare_snapshots\b"), ["stocklib/changes.py"])
        # the underscore-aliased forks are gone (all import `variant_key as _variant_key`)
        self.assertEqual(definers(r"^def _variant_key\b"), [])


if __name__ == "__main__":
    unittest.main()
