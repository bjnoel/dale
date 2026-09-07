"""Guards on the summary-first digest layout (2026-09-07).

The complaint this answers: the report was uniformly weighted, so finding out
whether anything was wrong meant reading twelve sections to the bottom, and
the permanent instrument caveats (a delivery rate that cannot exist, an event
still rolling out) read exactly like this week's findings.

What is pinned here is not the wording. It is the three properties that make
the top block safe to read on its own:

1. **Every alert reaches the top.** An alert that fires deep in a section and
   is not re-listed is worse than no summary at all, because the summary is
   then a promise that the reader has seen everything.
2. **The summary never invents a figure.** A metric that failed drops its row
   rather than printing a zero. DEC-249: an absence of measurement must not
   look like a clean result.
3. **A clean week says so out loud.** An empty attention block and a broken
   render look identical otherwise.

These never touch the network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "autonomous"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import treesmith_analytics as ta  # noqa: E402

# Reuse the zeroed metrics dict rather than a second copy of it: a fixture
# that drifts from the one every other digest test uses would pass against a
# shape render() no longer receives.
from test_treesmith_new_events import base_metrics  # noqa: E402


def _portability_with_failed_rows():
    """The 2026-09-07 shape: 4 imports, 2 of 141 rows rejected."""
    return {"ok": True, "data": {
        "exports_7d": 0, "exports": [],
        "imports_7d": 4, "imports": [
            {"format": "csv", "n_7d": 4, "plants_imported_7d": 69,
             "rows_imported_7d": 139, "all_time": 4}],
        "plants_imported_7d": 69, "plants_imported_all": 2,
        "rows_failed_7d": 2, "attempted_7d": 141, "success_pct": 99,
        "replaced_existing": 0}}


class TestAlertsReachTheTop(unittest.TestCase):
    def test_an_alert_fired_deep_in_a_section_is_listed_above_it(self):
        m = base_metrics()
        m["data_portability"] = _portability_with_failed_rows()
        text, _ = ta.render(m)

        self.assertIn("NEEDS ATTENTION (1)", text)
        self.assertIn("rows that failed to import", text)
        # Listed in the summary before the section that raised it.
        summary_at = text.index("NEEDS ATTENTION")
        section_at = text.index("Data portability")
        self.assertLess(summary_at, section_at)
        self.assertLess(text.index("rows that failed to import"), section_at)

    def test_the_detail_still_appears_against_the_figure(self):
        """The top block is an index, not a replacement. Moving the reasoning
        away from the number it is about is how a caveat stops being read."""
        m = base_metrics()
        m["data_portability"] = _portability_with_failed_rows()
        text, _ = ta.render(m)
        self.assertIn("a constraint clash and a parser problem look",
                      text[text.index("Data portability"):])

    def test_trust_alerts_outrank_product_alerts(self):
        """A stale input is read first because it decides whether the
        findings under it mean anything at all."""
        m = base_metrics()
        m["data_portability"] = _portability_with_failed_rows()
        m["reconciliation"] = {"ok": True, "data": {
            "via_paywall": 4, "via_purchase": 3, "agrees": False}}
        text, _ = ta.render(m)

        head = text[:text.index("Growth")]
        self.assertLess(head.index("purchase events disagree"),
                        head.index("rows that failed to import"))
        self.assertIn("Trust these numbers less", head)
        self.assertIn("Something happened to real users", head)

    def test_a_clean_week_says_so_rather_than_rendering_nothing(self):
        text, html = ta.render(base_metrics())
        self.assertIn("nothing flagged this week", text.lower())
        self.assertIn("Nothing flagged this week", html)


class TestHeadlineNeverInventsAFigure(unittest.TestCase):
    def test_a_failed_metric_drops_its_row_instead_of_printing_zero(self):
        m = base_metrics()
        m["installs"] = {"ok": False, "error": "posthog timeout"}
        rows = ta._headline(m)
        self.assertEqual([r[0] for r in rows if "install" in r[0].lower()], [])

    def test_the_headline_reads_the_same_numbers_the_sections_print(self):
        m = base_metrics()
        m["installs"] = {"ok": True, "data": {"this_week": 42, "prev_week": 14,
                                              "delta": 200, "all_time": 530}}
        m["funnel"] = {"ok": True, "data": {
            "steps": [], "biggest_drop": ("onboarded", "plant_added", 26, 63)}}
        text, _ = ta.render(m)
        head = text[:text.index("Growth")]
        self.assertIn("42", head)
        self.assertIn("63%", head)
        self.assertIn("onboarded -> plant_added", head)
        # And the section below still carries them.
        self.assertIn("42", text[text.index("Growth"):])

    def test_revenue_shows_the_week_and_all_time_together(self):
        """A zero week must never read as no revenue ever (DEC-260)."""
        m = base_metrics()
        m["purchases"] = {"ok": True, "data": {"buckets": [], "production": [
            {"currency": "AUD", "n_7d": 0, "n_all": 1,
             "revenue_7d": 0.0, "revenue_all": 39.99}]}}
        m["revenuecat"] = {"ok": True, "data": {
            "production_n": 4, "production_proceeds_usd": 70.04,
            "production_gross_usd": 102.57, "countries": [], "by_month": {},
            "platforms": {}, "sandbox_n": 0}}
        rows = dict((r[0], r[1]) for r in ta._headline(m))
        self.assertEqual(rows["Purchases (7d / all time)"], "0 / 4")
        self.assertEqual(rows["Revenue all time"], "US$70.04")


class TestNotesAreCollectedNotDeleted(unittest.TestCase):
    def test_a_permanent_caveat_moves_to_the_footer_and_survives(self):
        m = base_metrics()
        m["activation"] = {"ok": True, "data": {
            "installs": 42, "activated": 13, "rate": 31,
            "coverage_start": "2026-06-08", "all_installs": 221,
            "all_activated": 51, "all_rate": 23,
            "excluded_pre_coverage": 183}}
        text, html = ta.render(m)

        self.assertIn("activation unknown not zero", text)
        # Below the last section, not beside the figure it qualifies.
        self.assertLess(text.index("Backup health"),
                        text.index("activation unknown not zero"))
        # Collapsed in HTML rather than dropped.
        self.assertIn("<details", html)
        self.assertIn("activation unknown not zero", html)

    def test_no_notes_means_no_footer(self):
        _, html = ta.render(base_metrics())
        self.assertNotIn("<details", html)


if __name__ == "__main__":
    unittest.main()
