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


class BlocklistTests(unittest.TestCase):
    """Reads the committed state/ticket-blocklist.json, not a fixture."""

    def assertBlocked(self, title, description=""):
        hit = linear_update.check_blocklist(title, description)
        self.assertIsNotNone(hit, f"should be blocked: {title!r}")

    def assertAllowed(self, title, description=""):
        hit = linear_update.check_blocklist(title, description)
        self.assertIsNone(
            hit, f"should be allowed: {title!r} (matched {hit[0] if hit else None!r})"
        )

    def test_blocks_beestock(self):
        # DEC-230: beestock discontinued 2026-07-23
        self.assertBlocked("beestock: add subscribe CTA to compare pages")
        self.assertBlocked("Beestock price history charts")
        self.assertBlocked("Write a beginner beekeeping buying guide")
        self.assertBlocked("Re-enable the bee scraper cron")
        self.assertBlocked(
            "Audit archived sites", "Includes beestock.com.au category pages"
        )

    def test_blocks_existing_entries(self):
        self.assertBlocked("Tass1 Trees demo store")
        self.assertBlocked("Leeming Fruit Trees follow-up")
        self.assertBlocked("walkthrough: research 10 Perth SMB prospects")

    def test_no_bee_substring_false_positives(self):
        # "bee" as a bare pattern would match "been", "between", "beetle".
        # These are all legitimate treestock/Treesmith tickets.
        self.assertAllowed("treestock: species pages have been flat since June")
        self.assertAllowed("treestock: fix ordering between digest and species pages")
        self.assertAllowed("treestock: add fruit fly and beetle pest notes to guides")
        self.assertAllowed("Treesmith: App Store rating and review audit")
        self.assertAllowed(
            "treestock: bare-root season subscriber email",
            "Bare-root stock has been listed by 4 nurseries.",
        )


if __name__ == "__main__":
    unittest.main()
