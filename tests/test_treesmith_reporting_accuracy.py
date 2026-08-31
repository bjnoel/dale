"""Regression tests for the two reporting defects Benedict spotted (DAL-265).

He said two things that did not add up: the weekly digest under-reported active
users against weeks in which a purchase happened, and he had personally added
more plants than the digest said existed in total. Both were real, and both are
the same failure: the digest counted an event stream rather than the thing the
event stream is a proxy for.

1. **Identity.** Every people-count was `count(DISTINCT distinct_id)`. PostHog
   issues a new `distinct_id` per anonymous device and aliases it onto a
   `person_id` on sign-in, reinstall or restore. One person in our data carries
   27 ids. Counting ids inflates installs (so every conversion rate built on
   that denominator is understated) and makes each phantom id look like someone
   who arrived once and never returned (so retention is understated too).

2. **Plants.** `plant_added` is captured from exactly one place in the app,
   `plant_form_screen.dart`. A plant created by importing a file or restoring a
   backup fires nothing. Counting the event counts plants typed in by hand, not
   plants owned. The truth was already in the payload and had never been read:
   `plant_added` carries `plant_count_after`.

These tests pin the rendered text, because per DEC-251 the render is the only
surface a human reads and the only place the two can disagree. They never touch
the network.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "autonomous"))

import treesmith_analytics as ta  # noqa: E402


def _metrics(identity=None, plants=None):
    """Minimal metrics dict with only identity and plants populated."""
    return {
        "installs": {"ok": True,
                     "data": {"this_week": 0, "prev_week": 0, "delta": None}},
        "active": {"ok": True, "data": {"wau": 0, "mau": 0}},
        "identity": {"ok": True,
                     "data": identity or {"ids": 0, "persons": 0, "phantom": 0,
                                          "inflation_pct": None}},
        "plants": {"ok": True,
                   "data": plants or {"owners": 0, "plants": 0,
                                      "observed_adds": 0, "unobserved": 0,
                                      "unobserved_pct": None}},
        "activation": {"ok": True,
                       "data": {"installs": 0, "activated": 0, "rate": None,
                                "coverage_start": None, "all_installs": 0,
                                "all_activated": 0, "all_rate": None}},
        "onboarding": {"ok": True,
                       "data": {"started": 0, "completed": 0, "rate": None}},
        "funnel": {"ok": True, "data": {"steps": [], "biggest_drop": None}},
        "paywall": {"ok": True,
                    "data": {"shown": 0, "purchased": 0, "dismissed": 0}},
        "purchases": {"ok": True, "data": {"buckets": [], "production": []}},
        # Revenue comes from RevenueCat (DEC-260); not exercised here,
        # so it renders as an error rather than a silent zero.
        "revenuecat": {"ok": False, "error": "not under test"},

        "reconciliation": {
            "ok": True,
            "data": {"via_paywall": 0, "via_purchase": 0, "agrees": True}},
        "retention": {"ok": True,
                      "data": {"cohort": 0, "returned": 0, "rate": None}},
        "top_screens": {"ok": True, "data": {"rows": []}},
        "backup": {"ok": True, "data": {"completed": 0, "failed": []}},
    }


def _render(**kw):
    text, _html = ta.render(_metrics(**kw))
    return text


class TestPeopleNotDeviceIds(unittest.TestCase):
    """The digest must count humans, and must show its working."""

    def test_queries_count_person_id_not_distinct_id(self):
        """The people-counting metrics are the whole point of the fix.

        Asserted against the query source rather than the output, because a
        wrong denominator produces a perfectly plausible-looking number and
        there is nothing in the render that could catch it.
        """
        import inspect
        for fn in (ta.m_installs, ta.m_active, ta.m_activation,
                   ta.m_funnel, ta.m_retention):
            src = inspect.getsource(fn)
            self.assertIn("person_id", src, f"{fn.__name__} lost person_id")
            self.assertNotIn("distinct_id", src,
                             f"{fn.__name__} reverted to counting device ids")

    def test_render_shows_the_gap_between_ids_and_people(self):
        out = _render(identity={"ids": 348, "persons": 297, "phantom": 51,
                                "inflation_pct": 17})
        self.assertIn("297 people across 348 ids", out)
        self.assertIn("51 phantom", out)
        self.assertIn("+17%", out)

    def test_no_events_says_so_rather_than_reporting_zero_drift(self):
        """An empty project is not a project with perfectly clean identities."""
        out = _render()
        self.assertIn("no events recorded", out)
        self.assertNotIn("0 phantom", out)

    def test_labels_say_people_not_devices(self):
        """The label is what Benedict reads; it has to match what was counted."""
        out = _render()
        self.assertIn("Active people", out)
        self.assertNotIn("Active devices", out)


class TestPlantsHeldVersusPlantsObserved(unittest.TestCase):
    """Plants owned is the real number; plant_added is a lossy proxy for it."""

    def test_reports_plants_held_not_just_add_events(self):
        out = _render(plants={"owners": 20, "plants": 291,
                              "observed_adds": 165, "unobserved": 126,
                              "unobserved_pct": 43})
        self.assertIn("291 across 20 people", out)

    def test_names_the_blind_spot_with_its_size_and_its_cause(self):
        """Benedict found this by noticing his own plants were missing.

        The digest has to surface the same discrepancy by itself, or the next
        instrumentation gap waits for someone to notice it by hand again.
        """
        out = _render(plants={"owners": 20, "plants": 291,
                              "observed_adds": 165, "unobserved": 126,
                              "unobserved_pct": 43})
        self.assertIn("126 of 291 = 43%", out)
        self.assertIn("plant_added fires only from the plant form", out)
        # The two other routes a plant can arrive by, named separately since
        # 2026-08-31: file import became observable via data_imported, and
        # restore-from-backup did not.
        self.assertIn("import", out)
        self.assertIn("restore", out)

    def test_silent_when_the_two_agree(self):
        """No warning to ignore on the week the instrumentation is complete."""
        out = _render(plants={"owners": 5, "plants": 40, "observed_adds": 40,
                              "unobserved": 0, "unobserved_pct": 0})
        self.assertIn("40 across 5 people", out)
        self.assertNotIn("Never seen being added", out)


class TestHtmlAndTextAgree(unittest.TestCase):
    """DEC-251: the two renders must not be able to say different things."""

    def test_both_carry_the_plant_gap(self):
        text, html = ta.render(_metrics(
            plants={"owners": 20, "plants": 291, "observed_adds": 165,
                    "unobserved": 126, "unobserved_pct": 43}))
        stripped = re.sub(r"<[^>]+>", " ", html)
        for needle in ("291", "126", "43%"):
            self.assertIn(needle, text)
            self.assertIn(needle, stripped)


if __name__ == "__main__":
    unittest.main()
