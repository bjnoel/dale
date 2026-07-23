"""Tests for stocklib.utm.outbound — the shared outbound-link UTM tagger."""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib.utm import outbound


class OutboundTest(unittest.TestCase):
    def test_plain_url(self):
        self.assertEqual(
            outbound("https://x.com/p/fig", "nursery-page"),
            "https://x.com/p/fig?utm_source=treestock&utm_medium=nursery-page")

    def test_existing_query_string(self):
        self.assertEqual(
            outbound("https://x.com/p?id=3", "compare"),
            "https://x.com/p?id=3&utm_source=treestock&utm_medium=compare")

    def test_campaign(self):
        self.assertEqual(
            outbound("https://x.com/p", "email", campaign="variety-alert"),
            "https://x.com/p?utm_source=treestock&utm_medium=email&utm_campaign=variety-alert")

    def test_empty_url_passthrough(self):
        self.assertEqual(outbound("", "referral"), "")

    def test_matches_legacy_inline_format(self):
        # The de-forked callers must produce byte-identical URLs to the old
        # inline one-liners, or golden pages / email templates would churn.
        url = "https://daleys.com.au/plant/1"
        legacy = url + ("&" if "?" in url else "?") + "utm_source=treestock&utm_medium=referral"
        self.assertEqual(outbound(url, "referral"), legacy)


if __name__ == "__main__":
    unittest.main()
