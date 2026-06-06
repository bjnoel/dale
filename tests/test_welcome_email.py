"""
Regression test: the subscriber welcome email must derive its nursery count from
the registry, not a hardcoded literal.

It used to hardcode "19 Australian nurseries", "19 nurseries tracked", and
"and 7 more" in build_welcome_html(). When Rayners Orchard was added (20th
nursery) those went stale and new subscribers were emailed the wrong count.
The count is now len(SHIPPING_MAP); this pins it so it can't silently drift on
the next nursery.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

import send_welcome_email
from shipping import SHIPPING_MAP


class WelcomeEmailCountTest(unittest.TestCase):
    def setUp(self):
        self.html = send_welcome_email.build_welcome_html(
            "test@example.com",
            "https://treestock.com.au/unsubscribe?t=x",
            "https://treestock.com.au/manage?t=x",
        )

    def test_count_matches_registry(self):
        n = len(SHIPPING_MAP)
        self.assertIn(f"{n} nurseries tracked across Australia", self.html)
        self.assertIn(f"across {n} Australian", self.html)

    def test_sample_list_remainder_is_dynamic(self):
        # The body lists 12 nurseries explicitly then "and N more".
        self.assertIn(f"and {len(SHIPPING_MAP) - 12} more", self.html)

    def test_no_stale_hardcoded_19(self):
        self.assertNotIn("19 nurseries tracked", self.html)
        self.assertNotIn("19 Australian", self.html)


if __name__ == "__main__":
    unittest.main()
