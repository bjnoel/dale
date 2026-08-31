"""Guards on the super properties added to every event on 2026-08-31.

`is_pro`, `has_cloud_backup`, `is_sandbox` and the four *_bucket properties are
attached to EVERY event, including events from users who have never signed in.
That is the whole point of them: on 2026-08-31 the app had 43 MAU against 28
lifetime `auth_completed` events, so a segment that only worked for identified
users would have been blind to nearly everyone.

Two ways to lose that, both of which fail silently rather than loudly, which is
why they are pinned here instead of left to review:

1. **Reading them from the person store.** They are EVENT properties. HogQL
   will happily accept `person.properties.is_pro`; it simply returns NULL for
   everybody, so the digest reports "no Pro users" rather than raising. A
   segment that reads as an unremarkable business fact is far more dangerous
   than one that errors.

2. **Treating an absent property as false.** No event before the 2026-08-31
   build carries any of them: the check returned 0 across all 15,401 events
   ever recorded. So `is_pro` absent means either "not Pro" or "this event
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

        The module comments name `person.properties.is_pro` deliberately, to
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
                return [[100, 10] + [100] * len(ta.SUPER_PROPERTIES) + [10]]
            return [["true", 7, 70], ["false", 3, 30]]

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

    def _coverage(self, covered_counts, events=1000):
        real = ta.hogql
        ta.hogql = lambda h, k, q: [
            [events, 50] + covered_counts + [0]]
        try:
            return ta.m_super_property_coverage("h", "k")
        finally:
            ta.hogql = real

    def test_no_event_carrying_the_properties_reports_any_false(self):
        """The state on 2026-08-31: declared, shipped to nobody yet."""
        cov = self._coverage([0] * len(ta.SUPER_PROPERTIES))
        self.assertFalse(cov["any"])
        self.assertEqual(cov["by_property"]["is_pro"]["events"], 0)

    def test_partial_coverage_is_reported_as_a_percentage(self):
        """Both builds in the field is the normal state during a rollout."""
        cov = self._coverage([400] * len(ta.SUPER_PROPERTIES), events=1000)
        self.assertTrue(cov["any"])
        self.assertEqual(cov["by_property"]["is_pro"]["pct"], 40)

    def test_segments_returns_no_splits_when_nothing_carries_them(self):
        """Five empty distributions would read as five findings.

        A split of a population nobody can see must not render as a flat
        population, so m_segments returns coverage alone and the render
        prints nothing at all.
        """
        real = ta.hogql
        ta.hogql = lambda h, k, q: [[1000, 50] + [0] * len(ta.SUPER_PROPERTIES) + [0]]
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
                return [[1000, 50] + [100] * len(ta.SUPER_PROPERTIES) + [50]]
            return [["true", 3, 30], ["false", 7, 70]]

        ta.hogql = fake
        try:
            data = ta.m_segments("h", "k")
        finally:
            ta.hogql = real
        rows = data["splits"]["is_pro"]["rows"]
        # 3 of 10 covered people, NOT 3 of the 50 people seen this week.
        self.assertEqual({r["value"]: r["pct"] for r in rows},
                         {"true": 30, "false": 70})

    def test_every_split_query_filters_to_events_that_carry_the_property(self):
        captured = []
        real = ta.hogql

        def fake(host, key, query):
            captured.append(query)
            if "count() AS events_7d" in query:
                return [[100, 10] + [100] * len(ta.SUPER_PROPERTIES) + [10]]
            return [["true", 1, 1]]

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
        self.assertNotIn("is_pro", text)

    def test_splits_render_once_the_properties_arrive(self):
        text, _ = self._render({
            "coverage": {"events_7d": 1000, "people_7d": 40,
                         "covered_people": 40, "any": True,
                         "by_property": {p: {"events": 1000, "pct": 100}
                                         for p in ta.SUPER_PROPERTIES}},
            "splits": {"is_pro": {"people": 40, "rows": [
                {"value": "false", "people": 37, "events": 900, "pct": 93},
                {"value": "true", "people": 3, "events": 100, "pct": 8}]}}})
        self.assertIn("is_pro", text)
        self.assertIn("93%", text)

    def test_partial_coverage_is_stated_next_to_the_splits(self):
        """A split of 40% of traffic must not read as a split of all of it."""
        text, _ = self._render({
            "coverage": {"events_7d": 1000, "people_7d": 40,
                         "covered_people": 16, "any": True,
                         "by_property": {p: {"events": 400, "pct": 40}
                                         for p in ta.SUPER_PROPERTIES}},
            "splits": {"is_pro": {"people": 16, "rows": [
                {"value": "false", "people": 16, "events": 400, "pct": 100}]}}})
        self.assertIn("40%", text)
        self.assertIn("not", text.lower())


if __name__ == "__main__":
    unittest.main()
