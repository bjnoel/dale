"""Google Play pre-launch robots are excluded from every digest query.

187 OnePlus8Pro "people" (one per release, never seen twice) made up about half
of PostHog's Android users and most of its paywall views. The filter is added
in `hogql()` itself so no metric can forget it. These tests never touch the
network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "autonomous"))

import treesmith_analytics as ta  # noqa: E402


class ExcludeRobotsTest(unittest.TestCase):

    def test_filter_lands_before_where(self):
        out = ta.exclude_robots("SELECT count() FROM events WHERE event = 'x'")
        self.assertIn("FROM events PREWHERE ", out)
        self.assertTrue(out.endswith("WHERE event = 'x'"))
        self.assertIn("'OnePlus8Pro'", out)
        self.assertIn("'sdk_gphone%'", out)

    def test_filter_lands_before_group_by_and_bracket(self):
        q = ("WITH f AS (SELECT person_id FROM events GROUP BY person_id) "
             "SELECT count() FROM f WHERE person_id IN "
             "(SELECT person_id FROM events)")
        out = ta.exclude_robots(q)
        self.assertEqual(out.count("PREWHERE"), 2)
        self.assertIn("PREWHERE", out.split("GROUP BY")[0])
        self.assertNotIn("FROM f PREWHERE", out)

    def test_null_model_is_kept(self):
        # A bare != on NULL is NULL and would drop every event without a model.
        self.assertIn("coalesce(properties.$device_model, '')", ta.robot_filter())

    def test_idempotent_and_does_not_touch_other_tables(self):
        once = ta.exclude_robots("SELECT 1 FROM events")
        self.assertEqual(ta.exclude_robots(once), once)
        self.assertEqual(ta.exclude_robots("SELECT 1 FROM events_archive"),
                         "SELECT 1 FROM events_archive")

    def test_hogql_filters_by_default_and_can_opt_out(self):
        sent = []

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"results": []}'

        def fake_urlopen(req, timeout=None):
            import json
            sent.append(json.loads(req.data)["query"]["query"])
            return Resp()

        orig = ta.urllib.request.urlopen
        ta.urllib.request.urlopen = fake_urlopen
        try:
            ta.hogql("https://h", "k", "SELECT 1 FROM events")
            ta.hogql("https://h", "k", "SELECT 1 FROM events", include_robots=True)
        finally:
            ta.urllib.request.urlopen = orig
        self.assertIn("PREWHERE", sent[0])
        self.assertNotIn("PREWHERE", sent[1])


if __name__ == "__main__":
    unittest.main()
