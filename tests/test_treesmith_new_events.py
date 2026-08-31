"""Guards on the events added to the app on 2026-08-31.

Ten event names were declared at once (reminders, grafts, zones, photo
deletion, bulk edits, import/export, and `activity_logged` finally being
called) while the live builds were 1.0.11 and none of them had ever fired: the
check on that date returned 0 occurrences across all 15,401 events recorded.

Everything here follows from that one fact. A digest that reports a
not-yet-released event and a never-wired-up event identically is the DEC-251
failure again, and this file pins the difference:

  awaiting    declared, inside its grace, reported in GREY. A rollout.
  never_seen  undeclared or past grace, reported in RED. A defect.

It also pins the four measurement traps that came with the batch: the
`location_added` ceiling, the onboarding alias overlap, the import route into
the plants blind spot, and the notification delivery rate that must never be
built.

These never touch the network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "autonomous"))

import treesmith_analytics as ta  # noqa: E402


def base_metrics():
    """Every section render() indexes directly, at zero.

    Sections read with .get() are left out on purpose so that a test asserting
    on one of them has to supply it, rather than passing against a fabricated
    empty dict.
    """
    unused = {"ok": False, "error": "not under test"}
    return {
        "liveness": {"ok": True, "data": {"silent": [], "awaiting": [],
                                          "never_seen": []}},
        "installs": {"ok": True, "data": {"this_week": 0, "prev_week": 0,
                                          "delta": None, "all_time": 0}},
        "active": {"ok": True, "data": {"wau": 0, "mau": 0}},
        "identity": {"ok": True, "data": {"ids": 0, "persons": 0,
                                          "phantom": 0, "inflation_pct": None}},
        "plants": {"ok": True, "data": {"owners": 0, "plants": 0,
                                        "observed_adds": 0, "imported_adds": 0,
                                        "explained": 0, "unobserved": 0,
                                        "unobserved_pct": None}},
        "activation": {"ok": True, "data": {"installs": 0, "activated": 0,
                                            "rate": None,
                                            "coverage_start": None,
                                            "all_installs": 0,
                                            "all_activated": 0,
                                            "all_rate": None}},
        "onboarding": {"ok": True, "data": {"started": 0, "completed": 0,
                                            "rate": None}},
        "funnel": {"ok": True, "data": {"steps": [], "biggest_drop": None}},
        "paywall": {"ok": True, "data": {"shown": 0, "purchased": 0,
                                         "dismissed": 0}},
        "purchases": {"ok": True, "data": {"buckets": [], "production": []}},
        "revenuecat": unused,
        "reconciliation": {"ok": True, "data": {"via_paywall": 0,
                                                "via_purchase": 0,
                                                "agrees": True}},
        "retention": {"ok": True, "data": {"cohort": 0, "returned": 0,
                                           "rate": None}},
        "top_screens": {"ok": True, "data": {"rows": []}},
        "backup": {"ok": True, "data": {"completed": 0, "failed": []}},
    }


class RegistryTest(unittest.TestCase):
    """The declaration itself, before any query runs."""

    NEW_EVENTS = (
        "reminder_notification_tapped", "reminder_sweep", "graft_added",
        "photo_deleted", "data_exported", "data_imported",
        "plants_bulk_edited", "activity_logged", "zone_added",
        "reminder_created",
    )

    def test_every_new_event_is_registered(self):
        """Unregistered means unwatched: liveness only sees EVENTS."""
        for name in self.NEW_EVENTS:
            self.assertIn(name, ta.EVENTS.values(), f"{name} not in EVENTS")

    def test_every_event_awaiting_its_first_arrival_is_also_registered(self):
        """A grace entry for an event nothing watches would never expire."""
        for name in ta.AWAITING_FIRST_EVENT:
            self.assertIn(name, ta.EVENTS.values())

    def test_retired_onboarding_names_are_not_watched_for_silence(self):
        """They are SUPPOSED to be dead. Watching them is a weekly false alarm."""
        for retired in ("onboarding_started", "onboarding_step_completed",
                        "onboarding_completed"):
            self.assertNotIn(retired, ta.EVENTS.values())

    def test_retired_names_are_still_reachable_for_windows_spanning_july(self):
        self.assertIn("onboarding_started",
                      ta.event_names("welcome_screen_shown"))
        self.assertIn("onboarding_completed",
                      ta.event_names("welcome_screen_completed"))

    def test_a_live_event_has_no_aliases(self):
        self.assertEqual(ta.event_names("plant_added"), ["plant_added"])


class AwaitingFirstEventTest(unittest.TestCase):
    """The third liveness state, and the deadline that stops it being forever."""

    def _classify(self, rows):
        real = ta.hogql
        ta.hogql = lambda h, k, q: rows
        try:
            return ta.m_event_liveness("h", "k")
        finally:
            ta.hogql = real

    def _rows_for_everything_except(self, missing):
        return [[n, "2026-08-30", 500, 50] for n in ta.EVENTS.values()
                if n not in missing]

    def test_declared_event_inside_grace_is_awaiting_not_a_defect(self):
        data = self._classify(self._rows_for_everything_except({"graft_added"}))
        self.assertEqual([a["event"] for a in data["awaiting"]], ["graft_added"])
        self.assertEqual(data["never_seen"], [])

    def test_declared_event_past_grace_becomes_a_real_alarm(self):
        """Six weeks after declaration, "not yet" is no longer credible."""
        real_days_since = ta._days_since
        ta._days_since = lambda d: ta.AWAITING_GRACE_DAYS + 1
        try:
            data = self._classify(
                self._rows_for_everything_except({"graft_added"}))
        finally:
            ta._days_since = real_days_since
        self.assertEqual(data["awaiting"], [])
        self.assertEqual([n["event"] for n in data["never_seen"]],
                         ["graft_added"])

    def test_an_event_that_arrives_leaves_the_awaiting_state_by_itself(self):
        """No edit to AWAITING_FIRST_EVENT is needed when a build lands.

        The dict is a declaration, not a state machine. Classification keys on
        what the data holds, so a stale row cannot suppress a later silence.
        """
        rows = [[n, "2026-08-30", 500, 50] for n in ta.EVENTS.values()]
        data = self._classify(rows)
        self.assertEqual(data["awaiting"], [])

    def test_a_landed_event_that_later_goes_quiet_is_silent_not_awaiting(self):
        """The dangerous case: still declared, but now has real history."""
        rows = [[n, "2026-08-30", 500, 50] for n in ta.EVENTS.values()
                if n != "graft_added"]
        rows.append(["graft_added", "2026-07-01", 400, 0])
        data = self._classify(rows)
        self.assertEqual([s["event"] for s in data["silent"]], ["graft_added"])
        self.assertEqual(data["awaiting"], [])

    def test_every_registered_event_lands_in_exactly_one_bucket(self):
        """The invariant that lets the new sections stay hidden safely.

        Those sections render nothing while their events are awaiting. That is
        only honest because absence is always reported here, so no event can
        become invisible by being missing from both places at once.
        """
        data = self._classify([])
        named = ([s["event"] for s in data["silent"]]
                 + [a["event"] for a in data["awaiting"]]
                 + [n["event"] for n in data["never_seen"]])
        self.assertEqual(sorted(named), sorted(set(ta.EVENTS.values())))
        self.assertEqual(len(named), len(set(named)))


class AwaitingRenderTest(unittest.TestCase):
    """Grey and compact, not ten red lines."""

    def _render(self, **liveness):
        m = base_metrics()
        m["liveness"] = {"ok": True, "data": {
            "silent": [], "awaiting": [], "never_seen": [], **liveness}}
        return ta.render(m)

    def _awaiting(self, *names, days=3):
        return [{"event": n, "declared": "2026-08-31", "days_waiting": days,
                 "grace_days": ta.AWAITING_GRACE_DAYS} for n in names]

    def test_awaiting_events_are_named(self):
        text, _ = self._render(awaiting=self._awaiting("graft_added",
                                                       "zone_added"))
        self.assertIn("graft_added", text)
        self.assertIn("zone_added", text)

    def test_awaiting_is_grey_not_red(self):
        """Red here would train the reader to skip a section that must be read."""
        _, html = self._render(awaiting=self._awaiting("graft_added"))
        start = html.index("Awaiting first event")
        self.assertIn(f"color:{ta.GREY}", html[start:start + 800])
        self.assertNotIn(f"color:{ta.RED}", html[start:start + 800])

    def test_ten_events_declared_together_collapse_to_one_line(self):
        """Ten copies of the same sentence is the wallpaper this avoids."""
        names = sorted(ta.AWAITING_FIRST_EVENT)
        text, _ = self._render(awaiting=self._awaiting(*names))
        self.assertEqual(text.count("declared 2026-08-31, none seen yet"), 1)
        for n in names:
            self.assertIn(n, text)

    def test_an_overdue_event_says_how_long_it_has_been_overdue(self):
        text, html = self._render(never_seen=[{
            "event": "graft_added", "declared": "2026-08-31",
            "days_waiting": 60}])
        self.assertIn("60d", text)
        start = html.index("graft_added")
        self.assertIn(f"color:{ta.RED}", html[start:start + 600])

    def test_the_section_is_silent_when_everything_is_live(self):
        text, _ = self._render()
        self.assertNotIn("Event liveness", text)


class HiddenWhileAwaitingTest(unittest.TestCase):
    """A section with no data yet is omitted; a quiet week is not."""

    def test_section_hidden_when_it_has_never_had_data(self):
        self.assertTrue(ta._hidden_while_awaiting(
            ("graft_added", "zone_added"), 0))

    def test_section_shown_once_any_event_has_ever_arrived(self):
        self.assertFalse(ta._hidden_while_awaiting(
            ("graft_added", "zone_added"), 1))

    def test_a_quiet_week_on_a_live_feature_is_still_reported(self):
        """Zero this week is a real reading and belongs in the email."""
        m = base_metrics()
        m["feature_usage"] = {"ok": True, "data": {
            "by_event": {"graft_added": {"all_time": 40, "n_7d": 0,
                                         "people_7d": 0}},
            "grafts": [], "activities": [], "bulk": [], "photos": []}}
        text, _ = ta.render(m)
        self.assertIn("Feature usage", text)
        self.assertIn("graft_added", text)

    def test_an_undeclared_event_is_never_hidden(self):
        """Only a declared event gets the benefit of the doubt."""
        self.assertFalse(ta._hidden_while_awaiting(("note_edited",), 0))

    def test_feature_section_absent_before_the_build_lands(self):
        m = base_metrics()
        m["feature_usage"] = {"ok": True, "data": {
            "by_event": {n: {"all_time": 0, "n_7d": 0, "people_7d": 0}
                         for n in ("graft_added", "zone_added")},
            "grafts": [], "activities": [], "bulk": [], "photos": []}}
        text, _ = ta.render(m)
        self.assertNotIn("Feature usage", text)


class NoDeliveryRateTest(unittest.TestCase):
    """The metric that must never exist.

    The app is only ever woken by a tap. A notification that was delivered and
    ignored is indistinguishable from one that was never delivered, so the
    denominator for a delivery rate is not observable on the device. Any such
    rate would be an invented denominator wearing a percent sign.
    """

    def _reminders(self, **over):
        data = {"all_time": 10, "created_total": 12, "scheduled_ok": 10,
                "by_status": [], "blocked": [], "taps_total": 4,
                "by_launch": [], "cold_taps": 3, "warm_taps": 1,
                "taps_per_scheduled": 40,
                "sweep": {"sweeps": 5, "people": 4, "active": 9,
                          "already_pending": 7, "scheduled": 2, "blocked": 0,
                          "failed": 0, "left_due": 3, "sweeps_with_due": 2}}
        data.update(over)
        m = base_metrics()
        m["reminders"] = {"ok": True, "data": data}
        return ta.render(m)

    def test_the_digest_never_claims_a_delivery_rate(self):
        """The phrase may appear only where it is being ruled out.

        Counting rather than banning outright: the digest has to SAY that no
        delivery rate exists, or its absence reads as an oversight somebody
        should helpfully fix. So every occurrence must be the negation.
        """
        lowered = self._reminders()[0].lower()
        self.assertEqual(lowered.count("delivery rate"),
                         lowered.count("no delivery rate"))
        self.assertEqual(lowered.count("no delivery rate"), 1)
        for banned in ("delivered %", "% delivered", "notifications delivered",
                       "delivery %", "% of notifications delivered"):
            self.assertNotIn(banned, lowered)

    def test_the_absence_is_explained_rather_than_left_looking_like_a_gap(self):
        text, _ = self._reminders()
        self.assertIn("No delivery rate", text)

    def test_left_due_is_labelled_as_the_ignored_proxy(self):
        text, _ = self._reminders()
        self.assertIn("ignored-proxy", text)
        self.assertIn("3", text)

    def test_taps_per_scheduled_is_qualified_as_not_a_share(self):
        """A repeating reminder fires many times, so this can exceed 100%."""
        text, _ = self._reminders(taps_per_scheduled=140)
        self.assertIn("140%", text)
        self.assertIn("not a share of notifications", text)

    def test_a_blocked_reminder_is_reported_in_red(self):
        """The user asked for it and will never get it. Product failure."""
        _, html = self._reminders(blocked=[
            {"status": "blocked", "blocker": "permission_denied",
             "n": 6, "people": 4}])
        start = html.index("permission_denied")
        self.assertIn(f"color:{ta.RED}", html[max(0, start - 400):start + 200])

    def test_reminder_created_is_the_denominator(self):
        captured = []
        real = ta.hogql

        def fake(host, key, query):
            captured.append(query)
            return []

        ta.hogql = fake
        try:
            ta.m_reminders("h", "k")
        finally:
            ta.hogql = real
        joined = " ".join(captured)
        self.assertIn("reminder_created", joined)
        self.assertIn("schedule_status", joined)


class LocationCeilingTest(unittest.TestCase):
    """location_added fired from 1 of 3 creation paths until 2026-08-31."""

    def _metric(self, rows, split=None):
        """m_locations issues two queries with different shapes.

        The summary comes back as one 6-column row; the pre/post split as one
        5-column row per window. A stub returning the same rows to both is
        what the first version of this test did, and it failed on an unpack
        rather than on the behaviour under test.
        """
        real = ta.hogql

        def fake(h, k, q):
            return split or [] if "GROUP BY post" in q else rows

        ta.hogql = fake
        try:
            return ta.m_locations("h", "k")
        finally:
            ta.hogql = real

    def test_all_ones_is_detected_as_a_ceiling(self):
        """The real 2026-08-31 data: 77 adds, every one reporting exactly 1."""
        d = self._metric([[77, 74, 1, 0, "2026-06-08", ""]])
        self.assertTrue(d["capped"])
        self.assertIsNone(d["boundary"])

    def test_a_ceiling_is_reported_as_the_instrument_not_as_users(self):
        m = base_metrics()
        m["locations"] = {"ok": True, "data": {
            "adds": 77, "people": 74, "max_after": 1, "above_one": 0,
            "first_seen": "2026-06-08", "capped": True, "boundary": None,
            "pre": None, "post": None}}
        text, _ = ta.render(m)
        self.assertIn("UNREADABLE", text)
        self.assertIn("1 of 3 creation paths", text)
        self.assertIn("Do not trend", text)

    def test_a_value_above_one_lifts_the_ceiling_and_dates_the_boundary(self):
        d = self._metric([[120, 90, 3, 15, "2026-06-08", "2026-09-14"]],
                         split=[[0, 77, 74, 1, 1.0], [1, 43, 20, 3, 1.8]])
        self.assertFalse(d["capped"])
        self.assertEqual(d["boundary"], "2026-09-14")
        # The two windows are kept apart, never concatenated into one trend.
        self.assertEqual(d["pre"]["max_after"], 1)
        self.assertEqual(d["post"]["max_after"], 3)

    def test_the_step_change_at_the_boundary_is_called_an_artefact(self):
        """A trend spanning the fix steps up for a measurement reason."""
        m = base_metrics()
        m["locations"] = {"ok": True, "data": {
            "adds": 120, "people": 90, "max_after": 3, "above_one": 15,
            "first_seen": "2026-06-08", "capped": False,
            "boundary": "2026-09-14",
            "pre": {"adds": 77, "people": 74, "max_after": 1, "avg_after": 1.0},
            "post": {"adds": 43, "people": 20, "max_after": 3,
                     "avg_after": 1.8}}}
        text, _ = ta.render(m)
        self.assertIn("2026-09-14", text)
        self.assertIn("artefact", text)
        self.assertIn("not because anyone", text)

    def test_no_location_events_at_all_is_not_a_ceiling_claim(self):
        d = self._metric([[0, 0, 0, 0, "", ""]])
        self.assertEqual(d["adds"], 0)


class ImportNarrowsThePlantBlindSpotTest(unittest.TestCase):
    """data_imported can see a route plant_added never could."""

    def test_imported_plants_count_as_explained(self):
        real = ta.hogql
        calls = []

        def fake(host, key, query):
            calls.append(query)
            if "per_person" in query:
                return [[47, 453]]
            if "plants_imported" in query:
                return [[60]]
            return [[335]]

        ta.hogql = fake
        try:
            d = ta.m_plants("h", "k")
        finally:
            ta.hogql = real
        self.assertEqual(d["imported_adds"], 60)
        self.assertEqual(d["explained"], 395)
        self.assertEqual(d["unobserved"], 58)

    def test_the_residual_is_still_reported_because_restore_is_unseen(self):
        """Import narrows the gap. It does not close it."""
        m = base_metrics()
        m["plants"] = {"ok": True, "data": {
            "owners": 47, "plants": 453, "observed_adds": 335,
            "imported_adds": 60, "explained": 395, "unobserved": 58,
            "unobserved_pct": 13}}
        text, _ = ta.render(m)
        self.assertIn("restore-from-backup still announces nothing", text)
        self.assertIn("58", text)

    def test_import_route_is_named_when_present(self):
        m = base_metrics()
        m["plants"] = {"ok": True, "data": {
            "owners": 47, "plants": 453, "observed_adds": 335,
            "imported_adds": 60, "explained": 395, "unobserved": 58,
            "unobserved_pct": 13}}
        text, _ = ta.render(m)
        self.assertIn("Arrived by import", text)


class AliasUnionTest(unittest.TestCase):
    """A window spanning July sees the population under two names."""

    def test_onboarding_query_unions_both_names(self):
        captured = []
        real = ta.hogql

        def fake(host, key, query):
            captured.append(query)
            return [[20, 19]]

        ta.hogql = fake
        try:
            ta.m_onboarding("h", "k")
        finally:
            ta.hogql = real
        q = captured[0]
        self.assertIn("welcome_screen_shown", q)
        self.assertIn("onboarding_started", q)
        self.assertIn("onboarding_completed", q)

    def test_the_union_counts_people_not_events(self):
        """Summing per-name counts double-counts the four-week overlap.

        `onboarding_started` ran to 2026-07-30 and `welcome_screen_shown`
        began 2026-07-02, so anyone who updated inside that window sends both.
        """
        captured = []
        real = ta.hogql

        def fake(host, key, query):
            captured.append(query)
            return [[20, 19]]

        ta.hogql = fake
        try:
            ta.m_onboarding("h", "k")
        finally:
            ta.hogql = real
        self.assertIn("count(DISTINCT", captured[0])
        self.assertNotIn("countIf(event = ", captured[0])

    def test_funnel_steps_union_their_retired_names(self):
        captured = []
        real = ta.hogql

        def fake(host, key, query):
            captured.append(query)
            return [[10, 100]]

        ta.hogql = fake
        try:
            ta.m_funnel("h", "k")
        finally:
            ta.hogql = real
        onboarded = [q for q in captured if "welcome_screen_completed" in q]
        self.assertTrue(onboarded)
        self.assertIn("onboarding_completed", onboarded[0])

    def test_funnel_steps_carry_their_event_name(self):
        """So the render can tell awaiting from never-instrumented."""
        real = ta.hogql
        ta.hogql = lambda h, k, q: [[10, 100]]
        try:
            data = ta.m_funnel("h", "k")
        finally:
            ta.hogql = real
        for step in data["steps"]:
            self.assertEqual(len(step), 4)
            self.assertIn(step[3], ta.EVENTS.values())


class DataPortabilityTest(unittest.TestCase):
    """Exports, imports, and rows that became nothing."""

    def _render(self, data):
        m = base_metrics()
        m["data_portability"] = {"ok": True, "data": data}
        return ta.render(m)

    BASE = {
        "exports": [{"format": "csv", "all_time": 9, "n_7d": 2, "people": 2,
                     "plants_exported_7d": 80, "plants_imported_7d": 0,
                     "rows_imported_7d": 0, "plants_imported_all": 0,
                     "replaced": 0}],
        "imports": [{"format": "csv", "all_time": 5, "n_7d": 1, "people": 1,
                     "plants_exported_7d": 0, "plants_imported_7d": 12,
                     "rows_imported_7d": 400, "plants_imported_all": 60,
                     "replaced": 1}],
        "exports_7d": 2, "imports_7d": 1, "plants_imported_7d": 12,
        "rows_imported_7d": 400, "plants_imported_all": 60,
        "replaced_existing": 1, "unconverted_rows": 388,
        "row_conversion_pct": 3,
    }

    def test_rows_that_became_nothing_are_flagged(self):
        """400 rows in, 12 plants out is a broken import, not light usage."""
        text, html = self._render(self.BASE)
        self.assertIn("388", text)
        self.assertIn("3%", text)
        start = html.index("became nothing")
        self.assertIn(f"color:{ta.RED}", html[max(0, start - 400):start + 200])

    def test_replacing_imports_are_counted_apart(self):
        """A replacing import overwrites; summing would double-count plants."""
        text, _ = self._render(self.BASE)
        self.assertIn("replaced an existing library", text)
        self.assertIn("count the same plants twice", text)

    def test_a_clean_import_raises_nothing(self):
        clean = dict(self.BASE, unconverted_rows=0, row_conversion_pct=100,
                     replaced_existing=0)
        text, _ = self._render(clean)
        self.assertNotIn("became nothing", text)

    def test_conversion_is_none_rather_than_zero_when_no_rows_were_read(self):
        real = ta.hogql
        ta.hogql = lambda h, k, q: []
        try:
            d = ta.m_data_portability("h", "k")
        finally:
            ta.hogql = real
        self.assertIsNone(d["row_conversion_pct"])


class DigestStillRendersTest(unittest.TestCase):
    """The whole email, with and without the new sections."""

    def test_render_survives_every_new_section_being_absent(self):
        text, _ = ta.render(base_metrics())
        self.assertIn("TreeSmith Weekly", text)

    def test_a_failed_new_metric_is_reported_not_swallowed(self):
        for key, title in (("reminders", "Reminders"),
                           ("feature_usage", "Feature usage"),
                           ("data_portability", "Data portability"),
                           ("locations", "Locations"),
                           ("segments", "Segments")):
            m = base_metrics()
            m[key] = {"ok": False, "error": "HTTP 503 boom"}
            text, _ = ta.render(m)
            self.assertIn("503", text, f"{title} swallowed its error")

    def test_every_new_metric_is_wired_into_main(self):
        path = os.path.join(os.path.dirname(__file__), "..", "tools",
                            "autonomous", "treesmith_analytics.py")
        with open(path) as f:
            source = f.read()
        main_body = source[source.index("    metrics = {"):]
        for fn in ("m_segments", "m_reminders", "m_feature_usage",
                   "m_data_portability", "m_locations"):
            self.assertIn(fn, main_body, f"{fn} is never called")


if __name__ == "__main__":
    unittest.main()
