"""
DEC-294 hid the daily-digest signup site-wide behind
stocklib.flags.DIGEST_SIGNUP_ENABLED. It kept leaking back: on 2026-10-15 the
rare finds and state pages still rendered a subscribe box, the nursery pages
had a form whose JS never parsed, and two guides shipped the submit script with
no form. With the flag off, no built page may post to /api/subscribe.

The golden snapshots are what each builder renders (tests/test_golden.py keeps
them in step), so scanning them covers every builder in GOLDEN_CASES.
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "scrapers"))

from stocklib.flags import DIGEST_SIGNUP_ENABLED  # noqa: E402

GOLDEN = REPO_ROOT / "tests" / "golden" / "expected"


@unittest.skipIf(DIGEST_SIGNUP_ENABLED, "digest signup is switched on")
class DigestSignupHiddenTests(unittest.TestCase):
    def test_no_golden_page_posts_to_the_subscribe_endpoint(self):
        leaks = [str(p.relative_to(GOLDEN)) for p in GOLDEN.rglob("*.html")
                 if "/api/subscribe" in p.read_text()]
        self.assertEqual(leaks, [])

    def test_rare_and_location_goldens_exist(self):
        # Guard the guard: the scan above passes trivially if these vanish.
        self.assertTrue(list((GOLDEN / "rare_finds").rglob("*.html")))
        self.assertTrue(list((GOLDEN / "location").rglob("*.html")))


if __name__ == "__main__":
    unittest.main()
