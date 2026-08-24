"""
The homepage restriction badge must agree with registry.restriction_warning().

The bug (found 2026-08-24 on the Dwarf Moorpark Apricot row): dashboard.js
guarded the badge with `restricted.length > 0 && restricted.length < 3`, so a
nursery excluded from ALL of WA/NT/TAS showed no warning at all. That inverts
the intent -- the most restricted nurseries were the only silent ones.

Measured on the live dataset before the fix: a badge rendered for 4 of 27
nurseries (Daleys, Forever Seeds, Fruit Salad Trees, Heaven On Earth) and was
suppressed for 12 nurseries covering 5,086 of 9,150 products, among them
Ladybird (1,923), Ross Creek (1,098), Fruitopia (633) and PlantNet (110).

registry.restriction_warning() never had the cap, so the Python side was always
right and only the JS diverged. These tests pin the two together.

Run from repo root with:
    python3 -m unittest discover tests/
"""
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAPERS = REPO_ROOT / "tools" / "scrapers"
sys.path.insert(0, str(SCRAPERS))

from stocklib.registry import (  # noqa: E402
    LOCAL_DELIVERY, NURSERIES, QUARANTINE_STATES, restriction_warning,
)

DASHBOARD_JS = (SCRAPERS / "static" / "dashboard.js").read_text()

# Comments are stripped before the source assertions below. The comment above
# the fix names the clause it removed, on purpose -- that is documentation, not
# a reintroduction, and an earlier version of this test failed on its own
# explanation.
CODE_ONLY = "\n".join(
    line for line in DASHBOARD_JS.splitlines() if not line.lstrip().startswith("//")
)


class RestrictionWarningTests(unittest.TestCase):
    def test_a_nursery_reaching_none_of_them_still_gets_a_warning(self):
        # PlantNet: NSW/VIC/QLD/ACT. This is the row from the report.
        self.assertEqual(restriction_warning("plantnet"), "No WA/NT/TAS")

    def test_a_partly_restricted_nursery_names_only_what_it_misses(self):
        self.assertEqual(restriction_warning("ross-creek"), "No WA/NT/TAS")
        self.assertEqual(restriction_warning("daleys"), "No NT/TAS")

    def test_a_nationwide_nursery_gets_no_warning(self):
        self.assertEqual(restriction_warning("garden-express"), "")

    def test_most_tracked_nurseries_have_something_to_warn_about(self):
        """The suppressed set was the majority, which is why this mattered."""
        warned = [n.key for n in NURSERIES
                  if n.key not in LOCAL_DELIVERY and restriction_warning(n.key)]
        fully = [k for k in warned
                 if restriction_warning(k) == "No " + "/".join(QUARANTINE_STATES)]
        self.assertGreater(len(fully), len(warned) - len(fully),
                           "fully-restricted nurseries are the common case, so "
                           "suppressing them suppresses most of the signal")


class DashboardJsAgreesWithTheRegistryTests(unittest.TestCase):
    """dashboard.js reimplements the rule in the browser; it must not drift."""

    def test_the_length_cap_that_suppressed_the_badge_is_gone(self):
        # Not assertNotRegex: it embeds the whole 1,000-line file in the failure.
        self.assertFalse(
            re.search(r"restricted\.length\s*<\s*3", CODE_ONLY),
            "the `restricted.length < 3` clause is back; it hides the warning "
            "on exactly the nurseries that need it most",
        )

    def test_the_badge_still_renders_from_the_full_excluded_list(self):
        self.assertRegex(CODE_ONLY, r"No \$\{restricted\.join\('/'\)\}")

    def test_the_js_checks_the_same_three_quarantine_states(self):
        m = re.search(r"const restricted = \[([^\]]*)\]", CODE_ONLY)
        self.assertIsNotNone(m, "restricted list not found in dashboard.js")
        js_states = re.findall(r"'([A-Z]+)'", m.group(1))
        self.assertEqual(js_states, QUARANTINE_STATES)

    def test_local_delivery_nurseries_are_still_exempt(self):
        """A Perth-metro nursery gets 'Perth metro only', not 'No NT/TAS'."""
        self.assertRegex(CODE_ONLY, r"const shipsBadge = localArea \? ''")


if __name__ == "__main__":
    unittest.main()
