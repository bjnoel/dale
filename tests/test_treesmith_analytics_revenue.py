"""Regression tests for the TreeSmith weekly digest money reporting (DAL-266).

DEC-252 found two production purchases sitting in PostHog that no digest had
ever surfaced. The digest was not missing the data, it was reporting it in a
way that made it invisible:

1. Purchases were reported on a rolling 7-day window with no cumulative line,
   so each sale appeared in exactly one Monday email and then aged out.
2. Environment was inferred with coalesce(environment, 'production'), which
   relabels untagged events as real sales. Tagging only began 2026-07-01.

These tests pin the rendered output, because the render is the only surface a
human ever reads. They exercise render() with fabricated metrics and never
touch the network.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "tools", "autonomous"))

import treesmith_analytics as ta  # noqa: E402


def _metrics(purchases, reconciliation=None):
    """Minimal metrics dict: every section present, only purchases populated."""
    ok = {"ok": True, "data": {}}
    return {
        "installs": {"ok": True,
                     "data": {"this_week": 0, "prev_week": 0, "delta": None}},
        "active": {"ok": True, "data": {"wau": 0, "mau": 0}},
        "activation": {"ok": True,
                       "data": {"installs": 0, "activated": 0, "rate": None}},
        "onboarding": {"ok": True,
                       "data": {"started": 0, "completed": 0, "rate": None}},
        "funnel": {"ok": True, "data": {"steps": [], "biggest_drop": None}},
        "paywall": {"ok": True,
                    "data": {"shown": 3, "purchased": 1, "dismissed": 2}},
        "purchases": {"ok": True, "data": purchases},
        "reconciliation": reconciliation or {
            "ok": True,
            "data": {"via_paywall": 2, "via_purchase": 2, "agrees": True}},
        "retention": {"ok": True,
                      "data": {"cohort": 0, "returned": 0, "rate": None}},
        "top_screens": {"ok": True, "data": {"rows": []}},
        "backup": ok | {"data": {"completed": 0, "failed": []}},
    }


def _buckets(rows):
    b = [dict(zip(("env", "currency", "n_all", "revenue_all",
                   "n_7d", "revenue_7d"), r)) for r in rows]
    return {"buckets": b, "production": [x for x in b if x["env"] == "production"]}


class TestSaleCannotAgeOut(unittest.TestCase):
    def test_old_production_sale_still_shown_when_week_is_empty(self):
        """The DEC-252 case: sales exist, none this week. Must still appear."""
        data = _buckets([
            ("production", "AUD", 1, 39.99, 0, 0.0),
            ("production", "USD", 1, 24.99, 0, 0.0),
        ])
        text, _ = ta.render(_metrics(data))
        self.assertIn("Purchases ALL TIME (production)", text)
        # Two all-time sales must be visible even though this week is zero.
        self.assertRegex(text, r"Purchases ALL TIME \(production\)\s+2")
        self.assertRegex(text, r"Purchases this week \(production\)\s+0")
        self.assertIn("39.99", text)
        self.assertIn("24.99", text)

    def test_zero_state_says_none_rather_than_omitting_the_line(self):
        text, _ = ta.render(_metrics(_buckets([])))
        self.assertRegex(text, r"Purchases ALL TIME \(production\)\s+0")
        self.assertIn("none recorded", text)


class TestUntaggedIsNotRevenue(unittest.TestCase):
    def test_untagged_never_counted_as_production(self):
        """The old coalesce() turned these 13 test purchases into 'sales'."""
        data = _buckets([
            ("production", "AUD", 1, 39.99, 0, 0.0),
            ("untagged", "?", 13, 0.0, 0, 0.0),
        ])
        text, _ = ta.render(_metrics(data))
        self.assertRegex(text, r"Purchases ALL TIME \(production\)\s+1")
        self.assertIn("Excluded: untagged", text)

    def test_sandbox_is_excluded_but_still_visible(self):
        data = _buckets([("sandbox", "AUD", 1, 9.99, 0, 0.0)])
        text, _ = ta.render(_metrics(data))
        self.assertRegex(text, r"Purchases ALL TIME \(production\)\s+0")
        # Excluded, but not silently: a hidden sandbox counter is how the
        # old version made its production counter untrustworthy.
        self.assertIn("Excluded: sandbox", text)


class TestReconciliation(unittest.TestCase):
    def test_divergence_is_reported_loudly(self):
        data = _buckets([("production", "AUD", 1, 39.99, 0, 0.0)])
        recon = {"ok": True,
                 "data": {"via_paywall": 5, "via_purchase": 1, "agrees": False}}
        text, html = ta.render(_metrics(data, recon))
        self.assertIn("One of them is dropping events", text)
        self.assertIn(ta.RED, html)

    def test_agreement_is_silent(self):
        data = _buckets([("production", "AUD", 1, 39.99, 0, 0.0)])
        text, _ = ta.render(_metrics(data))
        self.assertNotIn("dropping events", text)


class TestPaywallSectionReportsReachNotMoney(unittest.TestCase):
    def test_paywall_no_longer_claims_an_environment_split(self):
        """paywall_result has no price and was untagged before 2026-07-01."""
        text, _ = ta.render(_metrics(_buckets([])))
        self.assertIn("Paywall views (7d)", text)
        self.assertNotIn("Purchases (sandbox, excluded)", text)


class TestArgumentHandling(unittest.TestCase):
    def test_unknown_argument_exits_rather_than_emailing(self):
        """--help used to fall through to the email path (DEC-252)."""
        argv = sys.argv
        try:
            sys.argv = ["treesmith_analytics.py", "--bogus"]
            with self.assertRaises(SystemExit) as cm:
                ta.main()
            self.assertEqual(cm.exception.code, 2)
        finally:
            sys.argv = argv


if __name__ == "__main__":
    unittest.main()
