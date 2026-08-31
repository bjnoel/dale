"""Regression tests for the renamed-event defect Benedict spotted (2026-08-10).

He asked how the digest could show 0 people onboarded in a week when people were
clearly reaching the paywall. Both numbers were right and the metric was wrong.

`m_onboarding` and `m_funnel` queried `onboarding_started` / `onboarding_completed`.
The app stopped sending those: commit f0117ee replaced the old OnboardingFlow with
a welcome screen and renamed the events to `welcome_screen_shown` /
`welcome_screen_completed`. The old names last arrived 2026-07-30, when the final
1.0.9 user updated. The true figure that week was 15 shown / 15 completed = 100%.

The knock-on was worse than the missing line. `m_funnel` reads the same dead event
for its "onboarded" step, so the digest reported `Biggest drop: opened -> onboarded:
lost 22 (100%)` in red, as a total collapse of a funnel step that was in fact
converting at 100%.

Renaming the strings fixes today and rebuilds the trap for the next rename, because
a query against an event nobody sends returns 0 and 0 is a legal answer. So the
names now live in one dict, `EVENTS`, and `m_event_liveness` watches that same dict
every week: any name with real history and no recent events is reported as SILENT
rather than quietly floored to zero.

These tests pin the rendered text, because per DEC-251 the render is the only
surface a human reads. They never touch the network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "autonomous"))

import treesmith_analytics as ta  # noqa: E402


def _metrics(liveness=None, onboarding=None, funnel=None):
    """Minimal metrics dict: every section present, only the ones under test set.

    Mirrors the helper in test_treesmith_activation_coverage.py. Sections not
    exercised here render as errors rather than as silent zeros, so a stray
    assertion cannot pass against a fabricated 0.
    """
    unused = {"ok": False, "error": "not under test"}
    return {
        "liveness": {"ok": True, "data": liveness} if liveness else unused,
        "installs": {"ok": True,
                     "data": {"this_week": 0, "prev_week": 0, "delta": None}},
        "active": {"ok": True, "data": {"wau": 0, "mau": 0}},
        "identity": {"ok": True,
                     "data": {"ids": 0, "persons": 0, "phantom": 0,
                              "inflation_pct": None}},
        "plants": {"ok": True,
                   "data": {"owners": 0, "plants": 0, "observed_adds": 0,
                            "unobserved": 0, "unobserved_pct": None}},
        "activation": {"ok": True,
                       "data": {"installs": 0, "activated": 0, "rate": None,
                                "coverage_start": None, "all_installs": 0,
                                "all_activated": 0, "all_rate": None}},
        "onboarding": ({"ok": True, "data": onboarding} if onboarding
                       else {"ok": True, "data": {"started": 0, "completed": 0,
                                                  "rate": None}}),
        "funnel": ({"ok": True, "data": funnel} if funnel
                   else {"ok": True, "data": {"steps": [], "biggest_drop": None}}),
        "paywall": {"ok": True,
                    "data": {"shown": 0, "purchased": 0, "dismissed": 0}},
        "purchases": {"ok": True, "data": {"buckets": [], "production": []}},
        "revenuecat": unused,
        "reconciliation": {"ok": True,
                           "data": {"via_paywall": 0, "via_purchase": 0,
                                    "agrees": True}},
        "retention": {"ok": True,
                      "data": {"cohort": 0, "returned": 0, "rate": None}},
        "top_screens": {"ok": True, "data": {"rows": []}},
        "backup": {"ok": True, "data": {"completed": 0, "failed": []}},
    }


def _render(**kwargs):
    text, html = ta.render(_metrics(**kwargs))
    return text, html


class EventNamesTest(unittest.TestCase):
    """The names themselves. These are what actually broke."""

    def test_events_dict_is_the_single_source_of_truth(self):
        self.assertEqual(ta.EVENTS["welcome_shown"], "welcome_screen_shown")
        self.assertEqual(ta.EVENTS["welcome_completed"],
                         "welcome_screen_completed")

    def test_the_dead_onboarding_events_appear_nowhere_in_the_module(self):
        """The exact defect: querying an event the app no longer sends.

        Read the source rather than the queries, so a copy of the old name
        cannot survive anywhere in the file (a second query, a docstring
        example, a funnel step) and quietly start returning zeros again.
        """
        with open(ta.__file__) as f:
            source = f.read()
        # The names are legal inside comments explaining the bug, so strip
        # comment lines before looking for live references.
        code = "\n".join(
            line for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        for dead in ("'onboarding_started'", "'onboarding_completed'"):
            self.assertNotIn(
                dead, code,
                f"{dead} is a dead event; the app renamed it to "
                f"welcome_screen_* on 2026-07-02")

    def test_funnel_onboarded_step_reads_the_live_event(self):
        """m_funnel's steps are built from EVENTS, not from loose strings."""
        import inspect
        source = inspect.getsource(ta.m_funnel)
        self.assertIn('EVENTS["welcome_completed"]', source)


class LivenessRenderTest(unittest.TestCase):
    """The guard that makes the next rename visible instead of silent."""

    SILENT = {
        "silent": [{"event": "onboarding_completed",
                    "last_seen": "2026-07-30", "days_ago": 11,
                    "all_time": 152}],
        "awaiting": [],
        "never_seen": [],
    }

    def test_a_silent_event_is_named_with_its_last_seen_date(self):
        text, html = _render(liveness=self.SILENT)
        self.assertIn("onboarding_completed", text)
        self.assertIn("2026-07-30", text)
        self.assertIn("onboarding_completed", html)

    def test_a_silent_event_says_how_much_history_it_had(self):
        """152 events then nothing is a rename. 2 events then nothing is noise."""
        text, _ = _render(liveness=self.SILENT)
        self.assertIn("152", text)

    def test_all_live_renders_no_liveness_section_at_all(self):
        """This runs every week. Silence when healthy or it becomes wallpaper."""
        text, html = _render(liveness={"silent": [], "awaiting": [],
                                       "never_seen": []})
        self.assertNotIn("Event liveness", text)
        self.assertNotIn("Event liveness", html)

    def test_never_seen_is_distinguished_from_went_silent(self):
        """A typo and a rename both yield zero, and need different fixes."""
        text, _ = _render(liveness={
            "silent": [],
            "awaiting": [],
            "never_seen": [{"event": "welcom_screen_shown",
                            "declared": None, "days_waiting": None}],
        })
        self.assertIn("welcom_screen_shown", text)
        self.assertIn("never", text.lower())

    def test_the_warning_is_red_in_html(self):
        """RED next to *this* event, not merely somewhere on the page.

        Asserting `RED in html` passes on an unmodified digest, because other
        sections already render errors in red. Scope it to the fragment the
        event name sits in.
        """
        _, html = _render(liveness=self.SILENT)
        start = html.index("onboarding_completed")
        self.assertIn(f"color:{ta.RED}", html[start:start + 600])

    def test_a_failed_liveness_check_is_reported_not_swallowed(self):
        """An errored check is a blind spot; silence would read as 'healthy'."""
        metrics = _metrics()
        metrics["liveness"] = {"ok": False, "error": "HTTP 503"}
        text, _ = ta.render(metrics)
        self.assertIn("Event liveness", text)
        self.assertIn("503", text)

    def test_liveness_renders_above_growth(self):
        """A broken input must be read before the numbers built on it."""
        text, _ = _render(liveness=self.SILENT)
        self.assertLess(text.index("Event liveness"), text.index("Growth"))

    def test_a_missing_liveness_key_does_not_break_the_render(self):
        """Older callers and the four existing render tests omit the key."""
        metrics = _metrics()
        del metrics["liveness"]
        text, _ = ta.render(metrics)
        self.assertIn("TreeSmith Weekly", text)


class LivenessClassifierTest(unittest.TestCase):
    """Bucketing, exercised without the network via a stub hogql."""

    def _classify(self, rows):
        real = ta.hogql
        ta.hogql = lambda host, key, query: rows
        try:
            return ta.m_event_liveness("host", "key")
        finally:
            ta.hogql = real

    def test_event_with_history_and_no_recent_events_is_silent(self):
        data = self._classify([
            [name, "2026-08-09", 500, 50] for name in ta.EVENTS.values()
        ][:-1] + [["purchase_succeeded", "2026-07-30", 152, 0]])
        self.assertEqual([s["event"] for s in data["silent"]],
                         ["purchase_succeeded"])
        self.assertEqual(data["silent"][0]["all_time"], 152)
        self.assertEqual(data["silent"][0]["last_seen"], "2026-07-30")

    def test_low_volume_event_going_quiet_does_not_warn(self):
        """Below MIN_HISTORY a zero week is ordinary, not a rename."""
        rows = [[name, "2026-08-09", 500, 50] for name in ta.EVENTS.values()]
        rows[-1] = [rows[-1][0], "2026-07-30", ta.MIN_HISTORY - 1, 0]
        self.assertEqual(self._classify(rows)["silent"], [])

    def test_an_event_absent_from_the_result_set_is_never_seen(self):
        """An undeclared event that never arrives is a defect, not a rollout.

        The missing name is chosen from the events NOT in
        AWAITING_FIRST_EVENT. One that is awaiting its first event is
        deliberately routed to the grace bucket instead, which is the
        distinction AwaitingFirstEventTest covers.
        """
        established = [n for n in ta.EVENTS.values()
                       if n not in ta.AWAITING_FIRST_EVENT]
        missing = established[-1]
        rows = [[name, "2026-08-09", 500, 50]
                for name in ta.EVENTS.values() if name != missing]
        self.assertEqual([n["event"] for n in self._classify(rows)["never_seen"]],
                         [missing])

    def test_all_healthy_reports_nothing(self):
        rows = [[name, "2026-08-09", 500, 50] for name in ta.EVENTS.values()]
        data = self._classify(rows)
        self.assertEqual(data["silent"], [])
        self.assertEqual(data["never_seen"], [])
        self.assertEqual(data["awaiting"], [])


class UninstrumentedFunnelStepTest(unittest.TestCase):
    """A step whose event no code path emits is not a user behaviour.

    Found by the liveness guard on its first live run: `activity_logged` has
    never been recorded once, because the app declares captureActivityLogged
    and never calls it. Renaming the onboarding events alone would have moved
    the phantom "lost 100%" callout one row down rather than removing it.
    """

    # 4-tuples: the event name lets the render tell a step that was never
    # wired up from one that is declared and awaiting a release. `note_edited`
    # stands in for a genuinely uninstrumented step because every real funnel
    # event is now either live or in AWAITING_FIRST_EVENT.
    STEPS = [("opened", 22, True, "Application Opened"),
             ("onboarded", 15, True, "welcome_screen_completed"),
             ("plant_added", 10, True, "plant_added"),
             ("activity_logged", 0, False, "note_edited")]

    def test_uninstrumented_step_is_labelled_not_reported_as_zero(self):
        text, _ = _render(funnel={"steps": self.STEPS, "biggest_drop": None})
        self.assertIn("not instrumented", text)

    def test_a_step_awaiting_rollout_is_not_called_uninstrumented(self):
        """Declared-and-not-yet-arrived is a release state, not a defect.

        `activity_logged` was genuinely never wired up for months and the
        render was right to say so in red. It is now declared, so until the
        build lands the same zero means something different and must not be
        reported as the app failing to instrument itself.
        """
        steps = self.STEPS[:3] + [("activity_logged", 0, False,
                                   "activity_logged")]
        text, _ = _render(funnel={"steps": steps, "biggest_drop": None})
        self.assertIn("awaiting rollout", text)
        self.assertNotIn("not instrumented", text)

    def test_a_three_tuple_step_still_renders(self):
        """The render must survive a half-deployed pair of files."""
        text, _ = _render(funnel={
            "steps": [("opened", 5, True), ("onboarded", 0, False)],
            "biggest_drop": None})
        self.assertIn("not instrumented", text)

    def test_the_drop_into_an_uninstrumented_step_is_not_reported(self):
        """The real regression: no red 100% drop into an event that never fires.

        These are the live 2026-08-10 numbers. Before this fix the digest led
        with "plant_added -> activity_logged: lost 10 (100%)".
        """
        data = self._funnel([(22, 1893), (15, 38), (10, 204), (0, 0)])
        # Biggest ABSOLUTE drop among measurable steps: 22 -> 15 loses 7,
        # 15 -> 10 loses 5. The uninstrumented step is not scored at all.
        self.assertEqual(data["biggest_drop"], ("opened", "onboarded", 7, 32))
        self.assertEqual(data["steps"][-1],
                         ("activity_logged", 0, False, "activity_logged"))
        self.assertNotIn("activity_logged", data["biggest_drop"])

    def test_drops_between_instrumented_steps_still_reported(self):
        data = self._funnel([(100, 500), (90, 500), (10, 500), (5, 500)])
        self.assertEqual(data["biggest_drop"], ("onboarded", "plant_added",
                                                80, 89))

    def test_a_genuine_zero_on_an_instrumented_step_still_counts(self):
        """all_time > 0 means the event works, so 0 this week is real."""
        data = self._funnel([(22, 1893), (15, 38), (10, 204), (0, 60)])
        self.assertEqual(data["steps"][-1],
                         ("activity_logged", 0, True, "activity_logged"))
        self.assertEqual(data["biggest_drop"][:2],
                         ("plant_added", "activity_logged"))

    def _funnel(self, per_step):
        """Drive the real m_funnel with a stubbed hogql.

        m_funnel issues one query per step in order, each returning
        [[people_7d, all_time]].
        """
        real = ta.hogql
        seq = iter([[list(row)] for row in per_step])
        ta.hogql = lambda h, k, q: next(seq)
        try:
            return ta.m_funnel("host", "key")
        finally:
            ta.hogql = real


class OnboardingLineTest(unittest.TestCase):
    """The line Benedict actually asked about."""

    def test_real_numbers_render_as_a_rate_not_a_zero(self):
        text, _ = _render(onboarding={"started": 15, "completed": 15,
                                      "rate": 100})
        self.assertIn("15/15 = 100%", text)

    def test_no_starts_still_reports_na_rather_than_zero_percent(self):
        text, _ = _render(onboarding={"started": 0, "completed": 0,
                                      "rate": None})
        self.assertIn("0/0 = n/a", text)


if __name__ == "__main__":
    unittest.main()
