"""Guards on `graft_status_changed`, added to the app on 2026-10-22.

Until then a graft could not change status at all: a dead graft was deleted,
which `photo_deleted` and `graft_added` cannot see. The event carries one
property, `to_status` (`failed`, `active`, rarely `unknown`), so the digest
reports how often each direction is chosen. A `failed` count that stays at 0
after the release reaches users means nobody found the control; an `active`
count close to `failed` means people are marking grafts Failed by mistake.

These never touch the network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "autonomous"))
sys.path.insert(0, os.path.dirname(__file__))

import treesmith_analytics as ta  # noqa: E402
from test_treesmith_new_events import base_metrics  # noqa: E402


def _feature_usage(statuses, all_time=5, n_7d=3):
    return {"ok": True, "data": {
        "by_event": {
            "graft_added": {"all_time": 40, "n_7d": 1, "people_7d": 1},
            "graft_status_changed": {"all_time": all_time, "n_7d": n_7d,
                                     "people_7d": 1},
        },
        "grafts": [], "graft_statuses": statuses, "activities": [],
        "bulk": [], "photos": []}}


class GraftStatusRegistryTest(unittest.TestCase):

    def test_the_event_is_watched_for_silence(self):
        """Unregistered means unwatched: liveness only sees EVENTS."""
        self.assertIn("graft_status_changed", ta.EVENTS.values())

    def test_the_developer_test_events_do_not_make_it_silent(self):
        """The 3 events from the 2026-10-22 device test are history, but too
        little to call a quiet week a regression before the release ships."""
        self.assertGreater(ta.MIN_HISTORY, 3)


class GraftStatusRenderTest(unittest.TestCase):

    def test_each_direction_is_reported_with_its_counts(self):
        m = base_metrics()
        m["feature_usage"] = _feature_usage([
            {"to_status": "failed", "n_7d": 2, "all_time": 4},
            {"to_status": "active", "n_7d": 1, "all_time": 1},
        ])
        text, _ = ta.render(m)
        self.assertIn("graft_status_changed", text)
        self.assertIn("graft -> failed", text)
        self.assertIn("2 this week  ·  4 all time", text)
        self.assertIn("graft -> active", text)
        self.assertIn("1 this week  ·  1 all time", text)

    def test_a_direction_with_history_but_a_quiet_week_is_still_listed(self):
        """Low volume: the all-time figure is the useful one most weeks."""
        m = base_metrics()
        m["feature_usage"] = _feature_usage(
            [{"to_status": "failed", "n_7d": 0, "all_time": 3}], n_7d=0)
        text, _ = ta.render(m)
        self.assertIn("graft -> failed", text)
        self.assertIn("0 this week  ·  3 all time", text)

    def test_data_without_the_breakdown_still_renders(self):
        """An older metrics payload has no `graft_statuses` key."""
        m = base_metrics()
        data = _feature_usage([])
        del data["data"]["graft_statuses"]
        m["feature_usage"] = data
        text, _ = ta.render(m)
        self.assertIn("Feature usage", text)


if __name__ == "__main__":
    unittest.main()
