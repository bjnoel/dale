"""Guards on the super properties added to every event on 2026-08-31.

`pro_source`, `cloud_backup_source`, `is_sandbox` and the four *_bucket
properties are
attached to EVERY event, including events from users who have never signed in.
That is the whole point of them: on 2026-08-31 the app had 43 MAU against 28
lifetime `auth_completed` events, so a segment that only worked for identified
users would have been blind to nearly everyone.

Two ways to lose that, both of which fail silently rather than loudly, which is
why they are pinned here instead of left to review:

1. **Reading them from the person store.** They are EVENT properties. HogQL
   will happily accept `person.properties.pro_source`; it simply returns NULL for
   everybody, so the digest reports "no Pro users" rather than raising. A
   segment that reads as an unremarkable business fact is far more dangerous
   than one that errors.

2. **Treating an absent property as false.** No event before the 2026-08-31
   build carries any of them: the check returned 0 across all 15,401 events
   ever recorded. So `pro_source` absent means either "not Pro" or "this event
   predates the instrument", and adding those together is DEC-317 exactly. The
   denominator must come from events that carry the property.

These never touch the network.
"""

import ast
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "autonomous"))

import treesmith_analytics as ta  # noqa: E402

SOURCE_PATH = os.path.join(os.path.dirname(__file__), "..", "tools",
                           "autonomous", "treesmith_analytics.py")


def query_strings(path):
    """Every string literal in the module except docstrings.

    The queries live in triple-quoted strings, so a plain text scan of the
    file cannot be used: it also reads the comments and docstrings that
    explain the person-store trap, and those legitimately contain the exact
    phrase being banned. Scanning literals reaches the SQL and nothing else,
    which is the only place the mistake can actually do harm.

    f-string fragments are included: ast.walk descends into JoinedStr, so the
    literal parts of an f-string query are returned alongside plain strings.
    """
    with open(path) as f:
        tree = ast.parse(f.read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]


N = len(ta.SUPER_PROPERTIES)


def coverage_row(events, people, covered_events, covered_people):
    """One row shaped like the coverage query's result.

    Columns: total events, total people, then one event count per super
    property, then one people count per super property.
    """
    n = len(ta.SUPER_PROPERTIES)
    return ([events, people] + [covered_events] * n + [covered_people] * n)


class PersonScopedReadTest(unittest.TestCase):
    """The failure that would report every Pro user as not-Pro."""

    def test_no_query_reads_a_super_property_from_the_person_store(self):
        # The rendered digest cannot catch this: the query succeeds and
        # returns NULL for everyone, so it shows up as a flat population.
        literals = query_strings(SOURCE_PATH)
        for prop in ta.SUPER_PROPERTIES:
            pattern = r"person\s*\.\s*properties\s*\.\s*" + re.escape(prop)
            for text in literals:
                self.assertIsNone(
                    re.search(pattern, text),
                    f"{prop} is read from the person store. These are event "
                    f"properties and never reach it; a person-scoped read "
                    f"returns NULL for every user instead of erroring.")

    def test_no_query_uses_person_properties_at_all(self):
        """Broader net: no query should touch that store."""
        for text in query_strings(SOURCE_PATH):
            self.assertIsNone(re.search(r"person\s*\.\s*properties", text))

    def test_the_guard_reads_queries_and_not_the_comments_about_them(self):
        """The guard must survive the prose that explains the trap.

        The module comments name `person.properties.pro_source` deliberately, to
        say what not to do. A guard that tripped on its own documentation
        would be deleted rather than fixed, taking the real check with it.
        """
        self.assertTrue(any("JSONHas(properties" in t
                            for t in query_strings(SOURCE_PATH)))
        self.assertFalse(any("is a different store" in t
                             for t in query_strings(SOURCE_PATH)))

    def test_segments_query_event_properties(self):
        """The positive form: segmentation reads properties.<name>."""
        captured = []
        real = ta.hogql

        def fake(host, key, query):
            captured.append(query)
            if "JSONHas" in query and "count() AS events_7d" in query:
                # Coverage probe: report full coverage so the splits run.
                return [coverage_row(100, 10, 100, 10)]
            return [["none", 7, 70], ["paid", 3, 30]]

        ta.hogql = fake
        try:
            ta.m_segments("host", "key")
        finally:
            ta.hogql = real
        split_queries = [q for q in captured if "GROUP BY value" in q]
        self.assertTrue(split_queries)
        for q in split_queries:
            self.assertIn("properties.", q)
            self.assertNotIn("person.properties", q)


class CoverageGateTest(unittest.TestCase):
    """An absent property is unknown, never false."""

    def _coverage(self, covered_events, events=1000, people=50,
                  covered_people=None):
        if covered_people is None:
            covered_people = covered_events
        real = ta.hogql
        ta.hogql = lambda h, k, q: [
            [events, people] + covered_events + covered_people]
        try:
            return ta.m_super_property_coverage("h", "k")
        finally:
            ta.hogql = real

    def test_no_event_carrying_the_properties_reports_any_false(self):
        """The state on 2026-08-31: declared, shipped to nobody yet."""
        cov = self._coverage([0] * N)
        self.assertFalse(cov["any"])
        self.assertEqual(cov["by_property"][ta.COVERAGE_PROBE]["events"], 0)

    def test_partial_coverage_is_reported_as_a_percentage(self):
        """Both builds in the field is the normal state during a rollout."""
        cov = self._coverage([400] * N, events=1000, people=50,
                             covered_people=[20] * N)
        self.assertTrue(cov["any"])
        self.assertEqual(cov["by_property"][ta.COVERAGE_PROBE]["pct"], 40)
        self.assertEqual(cov["by_property"][ta.COVERAGE_PROBE]["people_pct"], 40)
        # Events and people agree, which is what a build rollout looks like.
        self.assertIsNone(cov["skew"])

    def test_segments_returns_no_splits_when_nothing_carries_them(self):
        """Five empty distributions would read as five findings.

        A split of a population nobody can see must not render as a flat
        population, so m_segments returns coverage alone and the render
        prints nothing at all.
        """
        real = ta.hogql
        ta.hogql = lambda h, k, q: [coverage_row(1000, 50, 0, 0)]
        try:
            data = ta.m_segments("h", "k")
        finally:
            ta.hogql = real
        self.assertEqual(data["splits"], {})

    def test_split_denominator_comes_from_events_carrying_the_property(self):
        """Percentages are of the covered slice, not of all traffic."""
        real = ta.hogql

        def fake(host, key, query):
            if "count() AS events_7d" in query:
                # 1000 events this week, only 100 carry the properties.
                return [coverage_row(1000, 50, 100, 5)]
            return [["paid", 3, 30], ["none", 7, 70]]

        ta.hogql = fake
        try:
            data = ta.m_segments("h", "k")
        finally:
            ta.hogql = real
        rows = data["splits"][ta.COVERAGE_PROBE]["rows"]
        # 3 of 10 covered people, NOT 3 of the 50 people seen this week.
        self.assertEqual({r["value"]: r["pct"] for r in rows},
                         {"paid": 30, "none": 70})

    def test_every_split_query_filters_to_events_that_carry_the_property(self):
        captured = []
        real = ta.hogql

        def fake(host, key, query):
            captured.append(query)
            if "count() AS events_7d" in query:
                return [coverage_row(100, 10, 100, 10)]
            return [["none", 1, 1]]

        ta.hogql = fake
        try:
            ta.m_segments("h", "k")
        finally:
            ta.hogql = real
        for q in [q for q in captured if "GROUP BY value" in q]:
            self.assertIn("JSONHas(properties", q)


class RenderTest(unittest.TestCase):
    """What the reader actually sees, per DEC-251."""

    def _render(self, segments):
        from test_treesmith_new_events import base_metrics  # noqa: E402
        m = base_metrics()
        m["segments"] = {"ok": True, "data": segments}
        return ta.render(m)

    def test_nothing_renders_before_the_properties_arrive(self):
        text, _ = self._render({
            "coverage": {"events_7d": 1197, "people_7d": 32,
                         "covered_people": 0, "any": False,
                         "by_property": {p: {"events": 0, "pct": 0}
                                         for p in ta.SUPER_PROPERTIES}},
            "splits": {}})
        self.assertNotIn(ta.COVERAGE_PROBE, text)

    def test_splits_render_once_the_properties_arrive(self):
        text, _ = self._render({
            "coverage": {"events_7d": 1000, "people_7d": 40,
                         "covered_people": 40, "any": True,
                         "by_property": {p: {"events": 1000, "pct": 100}
                                         for p in ta.SUPER_PROPERTIES}},
            "splits": {ta.COVERAGE_PROBE: {"people": 40, "rows": [
                {"value": "none", "people": 37, "events": 900, "pct": 93},
                {"value": "paid", "people": 3, "events": 100, "pct": 8}]}}})
        self.assertIn(ta.COVERAGE_PROBE, text)
        self.assertIn("93%", text)

    def test_partial_coverage_is_stated_next_to_the_splits(self):
        """A split of 40% of traffic must not read as a split of all of it."""
        text, _ = self._render({
            "coverage": {"events_7d": 1000, "people_7d": 40,
                         "covered_people": 16, "any": True,
                         "by_property": {p: {"events": 400, "pct": 40}
                                         for p in ta.SUPER_PROPERTIES}},
            "splits": {ta.COVERAGE_PROBE: {"people": 16, "rows": [
                {"value": "none", "people": 16, "events": 400, "pct": 100}]}}})
        self.assertIn("40%", text)
        self.assertIn("not", text.lower())


class AnonymousCoverageTest(unittest.TestCase):
    """Coverage that reaches events but not people.

    The super properties exist to segment anonymous users, who are 85% of the
    people and a minority of the events: in the 28 days to 2026-08-31 the app
    had 71 anonymous people generating 2,382 events against 13 signed-in
    people generating 3,590. Properties that attached only once somebody
    signed in would therefore cover about 60% of events, which reads as an
    ordinary mid-rollout number, while missing 85% of the population.

    The event figure alone cannot tell that apart from a half-finished
    rollout. The gap between the two figures can.
    """

    def _cov(self, ev_pct, people_pct):
        real = ta.hogql
        ta.hogql = lambda h, k, q: [
            coverage_row(1000, 100, ev_pct * 10, people_pct)]
        try:
            return ta.m_super_property_coverage("h", "k")
        finally:
            ta.hogql = real

    def test_a_normal_rollout_reports_no_skew(self):
        """Events and people move together as people update."""
        self.assertIsNone(self._cov(40, 38)["skew"])

    def test_signed_in_only_properties_are_caught(self):
        """The 60%-of-events, 15%-of-people signature."""
        skew = self._cov(60, 15)["skew"]
        self.assertIsNotNone(skew)
        self.assertEqual(skew["events_pct"], 60)
        self.assertEqual(skew["people_pct"], 15)
        self.assertEqual(skew["gap"], 45)

    def test_full_coverage_reports_no_skew(self):
        self.assertIsNone(self._cov(100, 100)["skew"])

    def test_no_coverage_at_all_is_not_reported_as_skew(self):
        """Nothing has arrived yet. That is the awaiting state, not a skew."""
        self.assertIsNone(self._cov(0, 0)["skew"])

    def test_the_skew_is_rendered_in_red_and_names_the_cause(self):
        from test_treesmith_new_events import base_metrics  # noqa: E402
        m = base_metrics()
        m["segments"] = {"ok": True, "data": {
            "coverage": {"events_7d": 1000, "people_7d": 100,
                         "covered_people": 15, "any": True,
                         "by_property": {p: {"events": 600, "pct": 60,
                                             "people": 15, "people_pct": 15}
                                         for p in ta.SUPER_PROPERTIES},
                         "skew": {"events_pct": 60, "people_pct": 15,
                                  "gap": 45}},
            "splits": {}}}
        text, html = ta.render(m)
        self.assertIn("60% of events but only 15% of people", text)
        self.assertIn("signed-in", text)
        start = html.index("skewed toward heavy users")
        self.assertIn(f"color:{ta.RED}", html[max(0, start - 400):start + 200])

    def test_people_coverage_is_reported_beside_event_coverage(self):
        """Neither number is shown alone, so the gap is always visible."""
        from test_treesmith_new_events import base_metrics  # noqa: E402
        m = base_metrics()
        m["segments"] = {"ok": True, "data": {
            "coverage": {"events_7d": 1000, "people_7d": 100,
                         "covered_people": 38, "any": True,
                         "by_property": {p: {"events": 400, "pct": 40,
                                             "people": 38, "people_pct": 38}
                                         for p in ta.SUPER_PROPERTIES},
                         "skew": None},
            "splits": {}}}
        text, _ = ta.render(m)
        self.assertIn("40% of this week's 1,000 events", text)
        self.assertIn("38% of its 100 people", text)


if __name__ == "__main__":
    unittest.main()


class CoverageProbeTest(unittest.TestCase):
    """Coverage is read from the best covered property, never a fixed one.

    Real data broke the fixed version within three days. Build 65 shipped
    2026-08-31 sending the old `is_pro` spelling while this file had already
    moved to `pro_source`, so a probe pinned to `pro_source` read 0% while
    `is_sandbox` and the buckets sat at 7%, and the digest printed
    "0% coverage" directly above four populated splits.
    """

    def _cov(self, per_property):
        """per_property: {name: covered_event_count}."""
        ordered = [per_property.get(p, 0) for p in ta.SUPER_PROPERTIES]
        real = ta.hogql
        ta.hogql = lambda h, k, q: [[1000, 100] + ordered + ordered]
        try:
            return ta.m_super_property_coverage("h", "k")
        finally:
            ta.hogql = real

    def test_a_renamed_property_does_not_zero_the_headline(self):
        cov = self._cov({p: 95 for p in ta.SUPER_PROPERTIES
                         if p not in ("pro_source", "cloud_backup_source")})
        self.assertEqual(cov["by_property"]["pro_source"]["events"], 0)
        # Headline follows the properties that ARE arriving.
        self.assertEqual(cov["by_property"][cov["probe"]]["events"], 95)

    def test_the_disagreement_names_the_properties_that_are_behind(self):
        cov = self._cov({p: 95 for p in ta.SUPER_PROPERTIES
                         if p not in ("pro_source", "cloud_backup_source")})
        self.assertEqual(cov["spread"]["behind"],
                         ["cloud_backup_source", "pro_source"])
        self.assertEqual(cov["spread"]["high"], 95)

    def test_properties_agreeing_reports_no_spread(self):
        """The ordinary case: one register loop, identical coverage."""
        self.assertIsNone(self._cov({p: 95 for p in ta.SUPER_PROPERTIES})["spread"])

    def test_nothing_arrived_is_not_a_disagreement(self):
        self.assertIsNone(self._cov({})["spread"])

    def test_the_named_probe_wins_a_tie(self):
        """So the label is stable week to week when all are equal."""
        cov = self._cov({p: 95 for p in ta.SUPER_PROPERTIES})
        self.assertEqual(cov["probe"], ta.COVERAGE_PROBE)

    def test_the_disagreement_renders_in_red_above_the_splits(self):
        from test_treesmith_new_events import base_metrics  # noqa: E402
        m = base_metrics()
        m["segments"] = {"ok": True, "data": {
            "coverage": {"events_7d": 1397, "people_7d": 36,
                         "covered_people": 3, "any": True,
                         "probe": "is_sandbox",
                         "by_property": {p: {"events": 95, "pct": 7,
                                             "people": 3, "people_pct": 8}
                                         for p in ta.SUPER_PROPERTIES},
                         "skew": None,
                         "spread": {"high": 95, "low": 0,
                                    "behind": ["cloud_backup_source",
                                               "pro_source"]}},
            "splits": {}}}
        text, html = ta.render(m)
        self.assertIn("pro_source", text)
        self.assertIn("registered together", text)
        start = html.index("super properties disagree")
        self.assertIn(f"color:{ta.RED}", html[max(0, start - 400):start + 200])
