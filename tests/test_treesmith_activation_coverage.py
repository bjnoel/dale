"""Regression tests for cohort-correct activation reporting (DAL-265, DEC-254).

DEC-252 reported "18 of 290 installs ever added a plant = 6%" and treated it as
the binding constraint on the whole of Track A. The denominator was wrong.
`plant_added` did not exist until 2026-06-08, but installs are counted from
2026-04-25, so 179 of those 290 devices could not have fired the event no matter
what the user did. Their activation is unknown, not zero.

The same analysis leaned on `plant_count_snapshot`, which only ever shipped in
builds 13-40 and stopped emitting around 2026-06-07, so "181 of 186 people have
never had a plant" describes April/May users of a long-superseded build.

The fix is not a better estimate, it is refusing to divide by a period the event
could not cover, and printing the coverage window next to the number so the
window cannot be silently widened again.

These tests pin the rendered output, because the render is the only surface a
human reads. They call render() with fabricated metrics and never touch the
network.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "autonomous"))

import treesmith_analytics as ta  # noqa: E402


def _metrics(activation):
    """Minimal metrics dict: every section present, only activation populated."""
    ok = {"ok": True, "data": {}}
    return {
        "installs": {"ok": True,
                     "data": {"this_week": 0, "prev_week": 0, "delta": None}},
        "active": {"ok": True, "data": {"wau": 0, "mau": 0}},
        "identity": {"ok": True,
                     "data": {"ids": 0, "persons": 0, "phantom": 0,
                              "inflation_pct": 0}},
        "plants": {"ok": True,
                   "data": {"owners": 0, "plants": 0, "observed_adds": 0,
                            "unobserved": 0, "unobserved_pct": None}},
        "activation": {"ok": True, "data": activation},
        "onboarding": {"ok": True,
                       "data": {"started": 0, "completed": 0, "rate": None}},
        "funnel": {"ok": True, "data": {"steps": [], "biggest_drop": None}},
        "paywall": {"ok": True,
                    "data": {"shown": 0, "purchased": 0, "dismissed": 0}},
        "purchases": {"ok": True, "data": {"buckets": [], "production": []}},
        "reconciliation": {
            "ok": True,
            "data": {"via_paywall": 0, "via_purchase": 0, "agrees": True}},
        "retention": {"ok": True,
                      "data": {"cohort": 0, "returned": 0, "rate": None}},
        "top_screens": {"ok": True, "data": {"rows": []}},
        "backup": ok | {"data": {"completed": 0, "failed": []}},
    }


def _text(html):
    """Strip tags so assertions read like what a human sees."""
    return re.sub(r"<[^>]+>", " ", html)


# The real shape of the data as of 2026-07-30.
REAL = {
    "installs": 25, "activated": 4, "rate": 16,
    "coverage_start": "2026-06-08",
    "all_installs": 111, "all_activated": 13, "all_rate": 12,
    "excluded_pre_coverage": 179,
}


class TestCoverageWindowIsVisible(unittest.TestCase):
    def test_all_time_line_names_the_date_the_event_started(self):
        """Without the date, the reader cannot tell what the rate covers."""
        text, html = ta.render(_metrics(REAL))
        out = _text(text + html)
        self.assertIn("2026-06-08", out)
        self.assertIn("13/111", out)

    def test_devices_predating_the_event_are_excluded_and_said_so(self):
        """The 179 must not silently vanish, and must not read as failures."""
        text, html = ta.render(_metrics(REAL))
        out = _text(text + html)
        self.assertIn("179", out)
        self.assertIn("unknown not zero", out)

    def test_the_wrong_denominator_never_appears(self):
        """290 installs was the DEC-252 denominator. It must not come back."""
        text, html = ta.render(_metrics(REAL))
        out = _text(text + html)
        self.assertNotIn("13/290", out)
        self.assertNotIn("/290", out)


class TestRateArithmetic(unittest.TestCase):
    def test_all_time_rate_uses_the_clipped_cohort(self):
        """13/111 is 12%, not 13/290 = 4%."""
        text, html = ta.render(_metrics(REAL))
        out = _text(text + html)
        self.assertIn("12%", out)
        self.assertNotIn("4%", out)

    def test_no_activation_events_reports_na_rather_than_zero_percent(self):
        """An absent event is not a 0% activation rate (DEC-249's lesson)."""
        empty = {"installs": 0, "activated": 0, "rate": None,
                 "coverage_start": None, "all_installs": 0,
                 "all_activated": 0, "all_rate": None}
        text, html = ta.render(_metrics(empty))
        out = _text(text + html)
        self.assertIn("n/a", out)
        self.assertNotIn("0%", out)

    def test_no_excluded_devices_omits_the_caveat_line(self):
        """Once every device postdates the event, the caveat is just noise."""
        clean = dict(REAL, excluded_pre_coverage=0)
        text, html = ta.render(_metrics(clean))
        out = _text(text + html)
        self.assertNotIn("unknown not zero", out)
        self.assertIn("13/111", out)


class TestWeeklyLineStillWorks(unittest.TestCase):
    def test_weekly_activation_is_unchanged(self):
        """The 7d cohort was already correct; this change must not move it."""
        text, html = ta.render(_metrics(REAL))
        out = _text(text + html)
        self.assertIn("4/25", out)
        self.assertIn("16%", out)


if __name__ == "__main__":
    unittest.main()
