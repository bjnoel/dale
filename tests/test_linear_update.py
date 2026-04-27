"""
Tests for tools/autonomous/linear_update.py.

Regression coverage for one bug (2026-04-27):
  An autonomous Dale session posted "Dale: -" comments to DAL-167,
  DAL-169, and DAL-171. cmd_comment had no validation, so the model
  could call `linear_update.py comment DAL-X "-"` and the script would
  prefix and post it as if real content. _is_meaningful_comment now
  rejects empty/punctuation-only bodies.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTONOMOUS = REPO_ROOT / "tools" / "autonomous"
sys.path.insert(0, str(AUTONOMOUS))

spec = importlib.util.spec_from_file_location(
    "linear_update", AUTONOMOUS / "linear_update.py"
)
linear_update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linear_update)


class IsMeaningfulCommentTests(unittest.TestCase):
    def test_rejects_empty(self):
        self.assertFalse(linear_update._is_meaningful_comment(""))
        self.assertFalse(linear_update._is_meaningful_comment("   "))

    def test_rejects_dash_only(self):
        # The actual bug body
        self.assertFalse(linear_update._is_meaningful_comment("-"))
        self.assertFalse(linear_update._is_meaningful_comment("Dale: -"))
        self.assertFalse(linear_update._is_meaningful_comment("Dale:-"))

    def test_rejects_punctuation_only(self):
        self.assertFalse(linear_update._is_meaningful_comment("..."))
        self.assertFalse(linear_update._is_meaningful_comment("Dale: ..."))
        self.assertFalse(linear_update._is_meaningful_comment("???"))

    def test_rejects_prefix_with_only_whitespace(self):
        self.assertFalse(linear_update._is_meaningful_comment("Dale:   "))
        self.assertFalse(linear_update._is_meaningful_comment("Dale:"))

    def test_accepts_real_content(self):
        self.assertTrue(linear_update._is_meaningful_comment("Done."))
        self.assertTrue(
            linear_update._is_meaningful_comment("Dale: Finished, see commit abc123.")
        )
        # Mixed punctuation + words is fine
        self.assertTrue(linear_update._is_meaningful_comment("OK!"))
        # Even one alphanumeric character counts as meaningful
        self.assertTrue(linear_update._is_meaningful_comment("Dale: a"))


if __name__ == "__main__":
    unittest.main()
